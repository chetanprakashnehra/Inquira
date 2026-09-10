import json
import uuid
import logging
from typing import List, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db, AsyncSessionLocal
from app.core.dependencies import get_current_active_user, limiter
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.chat import ChatSession, ChatMessage
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatMessageResponse,
    ChatQueryRequest,
    Citation,
)
from app.rag.graph import rag_graph
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat & RAG"])


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    session_in: ChatSessionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat session bound to a knowledge base."""
    # Verify KB ownership
    kb_stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == session_in.knowledge_base_id,
        KnowledgeBase.user_id == current_user.id
    )
    kb_res = await db.execute(kb_stmt)
    if not kb_res.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    session = ChatSession(
        knowledge_base_id=session_in.knowledge_base_id,
        user_id=current_user.id,
        title=session_in.title or "New Conversation"
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionResponse.model_validate(session)


@router.get("/sessions", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    knowledge_base_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """List all chat sessions for a specific knowledge base."""
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.knowledge_base_id == knowledge_base_id,
            ChatSession.user_id == current_user.id
        )
        .order_by(ChatSession.created_at.desc())
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve all messages and citations for a chat session."""
    stmt = (
        select(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/query")
async def query_chat_session(
    session_id: uuid.UUID,
    query_in: ChatQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a question into the LangGraph Agentic RAG workflow.
    Streams answer tokens and citations back via Server-Sent Events (SSE).
    """
    # 1. Verify session exists and belongs to user
    stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    # 2. Fetch recent conversation history (sliding window)
    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.CHAT_HISTORY_WINDOW)
    )
    msg_res = await db.execute(msg_stmt)
    recent_msgs = list(reversed(msg_res.scalars().all()))

    chat_history = [{"role": m.role, "content": m.content} for m in recent_msgs]

    # 3. Save User message to DB
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=query_in.query,
        citations=None,
        token_count=max(1, len(query_in.query) // 4)
    )
    db.add(user_message)
    await db.commit()

    # 4. Stream response generator
    async def sse_stream_generator() -> AsyncGenerator[str, None]:
        # Initial state
        initial_state = {
            "query": query_in.query,
            "knowledge_base_id": str(session.knowledge_base_id),
            "user_id": str(current_user.id),
            "chat_history": chat_history,
            "intent": "rag",
            "rewritten_query": query_in.query,
            "hyde_document": None,
            "retrieved_dense": [],
            "retrieved_sparse": [],
            "fused_candidates": [],
            "ranked_chunks": [],
            "generated_response": "",
            "citations": [],
            "verification_score": 1.0,
            "is_verified": True,
            "retry_count": 0,
            "final_output": ""
        }

        yield f"data: {json.dumps({'type': 'status', 'stage': 'planning', 'message': 'Analyzing query & planning retrieval...'})}\n\n"

        # Execute LangGraph workflow
        try:
            final_state = await rag_graph.ainvoke(initial_state)
            
            # Send status update for retrieved sources
            ranked = final_state.get("ranked_chunks", [])
            citations = final_state.get("citations", [])
            yield f"data: {json.dumps({'type': 'status', 'stage': 'retrieval_complete', 'sources_count': len(ranked), 'citations': citations})}\n\n"

            # Stream generated tokens in small chunks
            final_text = final_state.get("final_output", "")
            words = final_text.split(" ")
            for i, word in enumerate(words):
                chunk = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            # Send final verification & completion event
            verification_score = final_state.get("verification_score", 1.0)
            yield f"data: {json.dumps({'type': 'done', 'verification_score': verification_score, 'citations': citations})}\n\n"

            # Persist assistant response to DB
            async with AsyncSessionLocal() as write_db:
                assistant_message = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=final_text,
                    citations=citations,
                    token_count=max(1, len(final_text) // 4)
                )
                write_db.add(assistant_message)
                await write_db.commit()

        except Exception as e:
            logger.error(f"Error executing RAG LangGraph workflow: {e}", exc_info=True)
            err_msg = "An error occurred while generating the answer. Please try again."
            yield f"data: {json.dumps({'type': 'error', 'message': err_msg})}\n\n"

    if query_in.stream:
        return StreamingResponse(sse_stream_generator(), media_type="text/event-stream")
    else:
        # Non-streaming JSON response
        initial_state = {
            "query": query_in.query,
            "knowledge_base_id": str(session.knowledge_base_id),
            "user_id": str(current_user.id),
            "chat_history": chat_history,
            "intent": "rag",
            "rewritten_query": query_in.query,
            "hyde_document": None,
            "retrieved_dense": [],
            "retrieved_sparse": [],
            "fused_candidates": [],
            "ranked_chunks": [],
            "generated_response": "",
            "citations": [],
            "verification_score": 1.0,
            "is_verified": True,
            "retry_count": 0,
            "final_output": ""
        }
        final_state = await rag_graph.ainvoke(initial_state)
        final_text = final_state.get("final_output", "")
        citations = final_state.get("citations", [])

        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=final_text,
            citations=citations,
            token_count=max(1, len(final_text) // 4)
        )
        db.add(assistant_message)
        await db.commit()
        await db.refresh(assistant_message)

        return ChatMessageResponse.model_validate(assistant_message)
