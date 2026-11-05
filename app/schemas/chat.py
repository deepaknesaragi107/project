from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role: 'user', 'assistant', 'system', or 'tool'")
    content: str = Field(..., description="Message text content")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User query or command for the booking assistant")
    session_id: Optional[str] = Field(default="default-session", description="Session ID for conversation history")
    user_email: Optional[str] = Field(default=None, description="Email of the customer for quick bookings")
    user_name: Optional[str] = Field(default=None, description="Full name of the customer")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Assistant response text")
    session_id: str
    action_taken: Optional[str] = Field(default=None, description="Name of action executed (e.g., 'hold_seats', 'search_events')")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Structured data payload (e.g. held booking details, search results)")

