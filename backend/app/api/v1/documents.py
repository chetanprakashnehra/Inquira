import os
import uuid
import shutil
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.core.redis import subscribe_progress
from app.config import settings
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.schemas.document import (
    DocumentResponse,
    DocumentUploadResponse,
    DocumentChunkResponse,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background_tasks: BackgroundTasks,
    knowledge_base_id: uuid.UUID = Form(...),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload one or multiple documents to a knowledge base and trigger async ingestion."""
    # 1. Verify Knowledge Base ownership
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    )
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge Base not found")

    # 2. Validate file count
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Exceeded max files per request limit ({settings.MAX_FILES_PER_REQUEST})"
        )

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    created_docs: List[Document] = []
    doc_ids_to_process: List[str] = []

    for file in files:
        # Validate filename and extension
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename)[1].lower()
        
        # Save file to upload directory
        file_id = uuid.uuid4()
        saved_filename = f"{file_id}_{filename}"
        file_path = os.path.join(settings.UPLOAD_DIR, saved_filename)
        
        # Stream file to disk and measure size
        size_bytes = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunk
                size_bytes += len(chunk)
                if size_bytes > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"File {filename} exceeds maximum size limit of {settings.MAX_UPLOAD_SIZE_MB}MB"
                    )
                buffer.write(chunk)

        # Create Document record
        doc = Document(
            id=file_id,
            knowledge_base_id=knowledge_base_id,
            file_name=filename,
            file_type=ext.replace(".", "") or "txt",
            file_size_bytes=size_bytes,
            file_path=file_path,
            status="PENDING",
            chunk_count=0
        )
        db.add(doc)
        created_docs.append(doc)
        doc_ids_to_process.append(str(doc.id))

    await db.commit()
    for doc in created_docs:
        await db.refresh(doc)

    # Dispatch document processing asynchronously
    from app.workers.tasks import _async_process_document

    class LocalTaskRunner:
        class Request:
            retries = 0
        request = Request()
        max_retries = 1
        def retry(self, exc=None): pass

    local_runner = LocalTaskRunner()

    if getattr(settings, "USE_CELERY", False):
        try:
            from app.workers.tasks import process_document
            for doc_id_str in doc_ids_to_process:
                process_document.delay(doc_id_str)
        except Exception as e:
            logger.warning(f"Could not dispatch to Celery broker ({e}). Running via FastAPI BackgroundTasks.")
            for doc_id_str in doc_ids_to_process:
                background_tasks.add_task(_async_process_document, local_runner, doc_id_str)
    else:
        # Standalone / Cloud Native background execution
        for doc_id_str in doc_ids_to_process:
            background_tasks.add_task(_async_process_document, local_runner, doc_id_str)

    return DocumentUploadResponse(
        message=f"Successfully queued {len(created_docs)} documents for ingestion.",
        documents=[DocumentResponse.model_validate(d) for d in created_docs]
    )


@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    knowledge_base_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all documents within a knowledge base."""
    # Verify KB ownership
    kb_stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    )
    kb_res = await db.execute(kb_stmt)
    if not kb_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    stmt = select(Document).where(Document.knowledge_base_id == knowledge_base_id).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get single document details and processing status."""
    stmt = (
        select(Document)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(Document.id == document_id, KnowledgeBase.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.get("/{document_id}/progress")
async def stream_document_progress(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Server-Sent Events (SSE) endpoint to stream real-time document indexing progress."""
    stmt = (
        select(Document)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(Document.id == document_id, KnowledgeBase.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    channel = f"doc_progress:{str(document_id)}"
    return StreamingResponse(
        subscribe_progress(channel),
        media_type="text/event-stream"
    )


@router.get("/{document_id}/chunks", response_model=List[DocumentChunkResponse])
async def get_document_chunks(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all parsed chunks for a document."""
    stmt = (
        select(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(Document.id == document_id, KnowledgeBase.user_id == current_user.id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return [DocumentChunkResponse.model_validate(c) for c in chunks]


@router.delete("/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document, remove its vector embeddings from Qdrant, and delete physical files."""
    stmt = (
        select(Document)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(Document.id == document_id, KnowledgeBase.user_id == current_user.id)
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = doc.file_path
    doc_id_str = str(doc.id)

    # Delete relational record (cascades to chunks)
    await db.delete(doc)
    await db.commit()

    # Dispatch deletion task for vector cleanup and disk cleanup
    from app.workers.tasks import delete_document_task
    try:
        delete_document_task.delay(doc_id_str, file_path)

    except Exception:
        delete_document_task(doc_id_str, file_path)

    return {"message": "Document deletion scheduled successfully."}
