
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent import run_agent
from auth import get_current_user
from database import get_db
from models import ChatMessage, ChatSession, User
from schemas import ChatRequest, ChatResponse


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


# ============================================================
# HELPER: CONVERT RESULTS INTO JSON-SAFE DATA
# ============================================================

def make_json_safe(value):
    """Convert Pydantic models and nested data into JSON-safe values."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")

    if hasattr(value, "dict"):
        return value.dict()

    if isinstance(value, list):
        return [make_json_safe(item) for item in value]

    if isinstance(value, dict):
        return {
            key: make_json_safe(item)
            for key, item in value.items()
        }

    return value


# ============================================================
# HELPER: VALIDATE SESSION OWNERSHIP
# ============================================================

async def get_user_session(
    session_id,
    current_user: User,
    db: AsyncSession,
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
            detail="Chat session not found",
        )

    return session


# ============================================================
# HELPER: LOAD CONVERSATION HISTORY
# ============================================================

async def get_chat_history(
    session_id,
    db: AsyncSession,
):
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )

    messages = result.scalars().all()

    return [
        {
            "role": message.role,
            "content": message.content,
        }
        for message in messages
    ]


# ============================================================
# HELPER: SAVE CHAT MESSAGE
# ============================================================

async def save_message(
    session_id,
    role: str,
    content: str,
    db: AsyncSession,
):
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
    )

    db.add(message)
    await db.commit()

    return message


# ============================================================
# NORMAL CHAT ENDPOINT
# POST /chat
# ============================================================

@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. Validate session ownership
    session = await get_user_session(
        request.session_id,
        current_user,
        db,
    )

    # 2. Load previous conversation
    history = await get_chat_history(
        session.id,
        db,
    )

    # 3. Save user question
    await save_message(
        session_id=session.id,
        role="user",
        content=request.question,
        db=db,
    )

    # 4. Run the complete LangGraph RAG workflow
    result = await run_agent(
        question=request.question,
        knowledge_base_id=str(session.knowledge_base_id),
        history=history,
    )

    answer = result["answer"]

    # Support the current agent's result key
    # and the alternative key if the agent is updated later.
    supported = result.get(
        "is_supported",
        result.get("supported", False),
    )

    citations = make_json_safe(
        result.get("citations", [])
    )

    retry_count = result.get("retry_count", 0)

    # 5. Save assistant answer
    await save_message(
        session_id=session.id,
        role="assistant",
        content=answer,
        db=db,
    )

    # 6. Return structured response
    return ChatResponse(
        answer=answer,
        citations=citations,
        supported=supported,
        retry_count=retry_count,
    )



# ============================================================
# STREAMING CHAT ENDPOINT
# POST /chat/stream
# ============================================================

@router.post("/stream")
async def stream_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await get_user_session(
        request.session_id,
        current_user,
        db,
    )

    history = await get_chat_history(
        session.id,
        db,
    )

    await save_message(
        session_id=session.id,
        role="user",
        content=request.question,
        db=db,
    )

    session_id = session.id
    knowledge_base_id = str(session.knowledge_base_id)
    question = request.question

    async def event_generator():
        # Flush initial progress event to immediately commit HTTP 200 headers to the browser
        yield (
            f"data: {json.dumps({'type': 'progress', 'status': 'started', 'node': 'init', 'message': 'Connecting to agent', 'retry_count': 0})}\n\n"
        )

        try:
            from agent import stream_agent
            from database import SessionLocal

            async for event in stream_agent(
                question=question,
                knowledge_base_id=knowledge_base_id,
                history=history,
            ):
                # Save the final answer to conversation history in an independent session.
                if event["type"] == "result":
                    try:
                        async with SessionLocal() as save_db:
                            await save_message(
                                session_id=session_id,
                                role="assistant",
                                content=event["answer"],
                                db=save_db,
                            )
                    except Exception as db_exc:
                        logging.warning(f"Could not persist assistant message: {db_exc}")

                    event = {
                        "type": "done",
                        "answer": event["answer"],
                        "citations": make_json_safe(
                            event["citations"]
                        ),
                        "supported": event.get("is_supported", False),
                        "is_supported": event.get("is_supported", False),
                        "retry_count": event.get("retry_count", 0),
                    }

                yield (
                    f"data: {json.dumps(make_json_safe(event))}\n\n"
                )

        except Exception as exc:
            logging.exception("Chat streaming failed")

            yield (
                "data: "
                + json.dumps({
                    "type": "error",
                    "message": f"Unable to generate the answer: {str(exc)}",
                })
                + "\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
