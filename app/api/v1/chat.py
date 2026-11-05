from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.agent.assistant import TicketingAIAssistant

router = APIRouter(prefix="/chat", tags=["AI Conversational Assistant"])


@router.post("", response_model=ChatResponse, summary="Chat with Ticketing AI Assistant")
async def chat_with_assistant(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Conversational AI agent endpoint powered by LLM tool calling.
    Assists users in discovering events, viewing seats, reserving holds,
    and finalizing bookings through interactive dialogue.
    """
    assistant = TicketingAIAssistant(db=db, session_id=payload.session_id)
    result = await assistant.process_message(
        user_message=payload.message,
        user_email=payload.user_email,
        user_name=payload.user_name,
    )
    return ChatResponse(
        reply=result["reply"],
        session_id=payload.session_id,
        action_taken=result.get("action_taken"),
        data=result.get("data"),
    )

