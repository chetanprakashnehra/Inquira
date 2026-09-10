import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    KnowledgeBaseResponse,
    KnowledgeBaseDetailResponse,
)

router = APIRouter(prefix="/knowledge-bases", tags=["Knowledge Bases"])


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    kb_in: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new private knowledge base for the authenticated user."""
    kb = KnowledgeBase(
        user_id=current_user.id,
        name=kb_in.name,
        description=kb_in.description
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    
    response = KnowledgeBaseResponse.model_validate(kb)
    response.document_count = 0
    return response


@router.get("", response_model=List[KnowledgeBaseResponse])
async def list_knowledge_bases(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all knowledge bases belonging to current user."""
    # Query knowledge bases with document counts
    stmt = (
        select(
            KnowledgeBase,
            func.count(Document.id).label("doc_count")
        )
        .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .where(KnowledgeBase.user_id == current_user.id)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    
    responses = []
    for kb, doc_count in rows:
        resp = KnowledgeBaseResponse.model_validate(kb)
        resp.document_count = doc_count
        responses.append(resp)
    return responses


@router.get("/{kb_id}", response_model=KnowledgeBaseDetailResponse)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get single knowledge base details."""
    stmt = (
        select(KnowledgeBase, func.count(Document.id).label("doc_count"))
        .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
        .group_by(KnowledgeBase.id)
    )
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    
    kb, doc_count = row
    resp = KnowledgeBaseDetailResponse.model_validate(kb)
    resp.document_count = doc_count
    return resp


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    kb_in: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update knowledge base name or description."""
    stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    
    if kb_in.name is not None:
        kb.name = kb_in.name
    if kb_in.description is not None:
        kb.description = kb_in.description
    
    await db.commit()
    await db.refresh(kb)
    return kb


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete knowledge base and all associated documents and vector chunks."""
    stmt = select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id)
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    
    await db.delete(kb)
    await db.commit()
    return None
