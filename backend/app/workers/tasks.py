import asyncio
import os
import uuid
import logging
from sqlalchemy import select, update
from app.workers.celery_app import celery
from app.core.database import AsyncSessionLocal
from app.models.document import Document
from app.models.chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.models.log import ApplicationLog
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
from app.services.embedding import embedding_service
from app.rag.retrieval.qdrant_client import qdrant_store
from app.core.redis import publish_progress

logger = logging.getLogger(__name__)


def run_async(coro):
    """Utility to run an async coroutine inside a synchronous Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery.task(bind=True, max_retries=3, default_retry_delay=15)
def process_document(self, document_id_str: str):
    """Celery task to asynchronously parse, chunk, embed, and index a document."""
    return run_async(_async_process_document(self, document_id_str))


async def _async_process_document(task, document_id_str: str):
    doc_uuid = uuid.UUID(document_id_str)
    channel = f"doc_progress:{document_id_str}"

    async with AsyncSessionLocal() as db:
        # 1. Fetch document and KB information
        stmt = (
            select(Document, KnowledgeBase.user_id)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(Document.id == doc_uuid)
        )
        result = await db.execute(stmt)
        row = result.first()
        if not row:
            logger.error(f"Document {document_id_str} not found in database.")
            return {"status": "error", "message": "Document not found"}

        doc, user_id = row
        doc_id = doc.id
        doc_file_path = doc.file_path
        doc_file_type = doc.file_type
        doc_file_name = doc.file_name
        doc_kb_id = doc.knowledge_base_id
        user_id_str = str(user_id)

        try:
            # Update status to PROCESSING
            await db.execute(
                update(Document).where(Document.id == doc_uuid).values(status="PROCESSING")
            )
            await db.commit()
            await publish_progress(channel, {"status": "PROCESSING", "progress": 10, "message": "Starting document parsing..."})

            # 2. Parse, chunk, and embed in background thread to never block async loop
            await publish_progress(channel, {"status": "PROCESSING", "progress": 25, "message": "Extracting text and chunking..."})

            def _parse_and_embed():
                pages = DocumentParser.parse_file(doc_file_path, doc_file_type)
                chunker = DocumentChunker()
                chunks = chunker.chunk_pages(pages)
                if not chunks:
                    raise ValueError("No extractable text or chunks produced from document.")
                chunk_texts = [c.content for c in chunks]
                dense = embedding_service.get_dense_embeddings(chunk_texts)
                sparse = embedding_service.get_sparse_embeddings(chunk_texts)
                return chunks, dense, sparse

            chunks, dense_vectors, sparse_vectors = await asyncio.to_thread(_parse_and_embed)

            # 3. Prepare Qdrant points and DB records
            await publish_progress(channel, {"status": "PROCESSING", "progress": 70, "message": "Indexing vectors into Qdrant Cloud..."})
            point_ids = []
            payloads = []
            db_chunks = []

            for i, chunk in enumerate(chunks):
                point_id = str(uuid.uuid4())
                point_ids.append(point_id)
                payloads.append({
                    "user_id": user_id_str,
                    "knowledge_base_id": str(doc_kb_id),
                    "document_id": str(doc_id),
                    "file_name": doc_file_name,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content
                })
                db_chunks.append(
                    DocumentChunk(
                        document_id=doc_id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        content=chunk.content,
                        qdrant_point_id=uuid.UUID(point_id),
                        token_count=chunk.token_count
                    )
                )

            # Upsert into Qdrant via thread to prevent event loop blocking
            await asyncio.to_thread(
                qdrant_store.upsert_chunks,
                point_ids=point_ids,
                dense_vectors=dense_vectors,
                sparse_vectors=sparse_vectors,
                payloads=payloads
            )

            # Insert chunks into relational DB and mark INDEXED
            db.add_all(db_chunks)
            await db.execute(
                update(Document)
                .where(Document.id == doc_uuid)
                .values(status="INDEXED", chunk_count=len(chunks), error_message=None)
            )
            await db.commit()

            await publish_progress(channel, {
                "status": "INDEXED",
                "progress": 100,
                "message": f"Successfully indexed {len(chunks)} chunks.",
                "chunk_count": len(chunks)
            })
            return {"status": "success", "chunks_indexed": len(chunks)}

        except Exception as exc:
            logger.error(f"Error processing document {document_id_str}: {exc}", exc_info=True)
            await db.execute(
                update(Document)
                .where(Document.id == doc_uuid)
                .values(status="FAILED", error_message=str(exc))
            )
            
            # Record in application_logs
            app_log = ApplicationLog(
                level="ERROR",
                source="celery.tasks.process_document",
                message=f"Failed to process document {doc_file_name}: {str(exc)}",
                metadata_json={"document_id": document_id_str, "file_path": doc_file_path}
            )
            db.add(app_log)
            await db.commit()

            await publish_progress(channel, {
                "status": "FAILED",
                "progress": 0,
                "error": str(exc),
                "message": "Document indexing failed."
            })

            # Check if task should retry (only for actual Celery tasks)
            if hasattr(task, "request") and getattr(task.request, "retries", 0) < getattr(task, "max_retries", 0):
                if hasattr(task, "retry"):
                    raise task.retry(exc=exc)
            return {"status": "failed", "error": str(exc)}


@celery.task
def delete_document_task(document_id_str: str, file_path: str = None):
    """Celery task to clean up Qdrant points and remove physical files on document deletion."""
    try:
        # Delete from Qdrant
        qdrant_store.delete_by_document(document_id_str)
        # Remove physical file if path supplied
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                logger.warning(f"Could not delete physical file at {file_path}: {e}")
        return {"status": "success", "deleted_document_id": document_id_str}
    except Exception as e:
        logger.error(f"Error in delete_document_task for {document_id_str}: {e}")
        return {"status": "error", "error": str(e)}
