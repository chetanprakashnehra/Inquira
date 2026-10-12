from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models import ChatSession, User, KnowledgeBase, ChatMessage
from schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageResponse,
)

router = APIRouter(
    prefix="/sessions",
    tags=["Chat Sessions"],
)


@router.post(
    "",
    response_model=ChatSessionResponse,
)
async def create_session(
    request: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == request.knowledge_base_id,
            KnowledgeBase.user_id == current_user.id,
        )
    )

    knowledge_base = result.scalar_one_or_none()

    if knowledge_base is None:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    session = ChatSession(
        user_id=current_user.id,
        knowledge_base_id=request.knowledge_base_id,
        title=request.title,
    )

    db.add(session)
    await db.commit()
    await db.refresh(session)

    return session


@router.get(
    "",
    response_model=list[ChatSessionResponse],
)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
    )

    return result.scalars().all()


@router.get(
    "/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )

    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
    )

    return result.scalars().all()