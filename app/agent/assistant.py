import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.agent.tools import AgentBookingTools, TICKETING_TOOLS_DEFINITIONS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are TicketAI, an expert conversational ticketing and booking concierge.
Your primary role is to assist users in discovering events, browsing available seats and pricing tiers, securing concurrency-safe holds, and confirming their ticket reservations.

Follow these booking principles:
1. When a user asks about events, use `search_events` to look up live events.
2. When a user is interested in an event, use `get_event_seats` to check real-time available seats and pricing tiers.
3. To reserve seats, always require the user's name, email, and specific seat IDs, then invoke `hold_ticket_seats`. Inform them that seats are held for 10 minutes.
4. When they agree to finalize or say confirm, call `confirm_booking` with the booking reference.
5. If they want to check their reservation, use `check_booking_status`.
6. Be friendly, concise, and helpful. Always quote prices clearly.
"""

# In-memory session chat history cache: session_id -> list of messages
_session_history: Dict[str, List[Dict[str, Any]]] = {}


class TicketingAIAssistant:
    def __init__(self, db: AsyncSession, session_id: str = "default-session"):
        self.db = db
        self.session_id = session_id
        self.tools = AgentBookingTools(db)

    def _get_history(self) -> List[Dict[str, Any]]:
        if self.session_id not in _session_history:
            _session_history[self.session_id] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
        return _session_history[self.session_id]

    async def execute_tool_call(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the appropriate tool method based on LLM function call."""
        if function_name == "search_events":
            return await self.tools.search_events(
                query=arguments.get("query"),
                city=arguments.get("city"),
                category=arguments.get("category"),
            )
        elif function_name == "get_event_seats":
            return await self.tools.get_event_seats(
                event_id=int(arguments.get("event_id")),
                tier_name=arguments.get("tier_name"),
            )
        elif function_name == "hold_ticket_seats":
            return await self.tools.hold_ticket_seats(
                event_id=int(arguments.get("event_id")),
                seat_ids=[int(s) for s in arguments.get("seat_ids", [])],
                customer_name=arguments.get("customer_name"),
                customer_email=arguments.get("customer_email"),
                customer_phone=arguments.get("customer_phone"),
            )
        elif function_name == "confirm_booking":
            return await self.tools.confirm_booking(
                booking_reference=arguments.get("booking_reference")
            )
        elif function_name == "check_booking_status":
            return await self.tools.check_booking_status(
                booking_reference=arguments.get("booking_reference")
            )
        else:
            return {"error": f"Unknown tool: {function_name}"}

    async def process_message(
        self,
        user_message: str,
        user_email: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Main agent processing loop with tool calling and fallback."""
        history = self._get_history()

        # Augment with user metadata if provided
        user_content = user_message
        if user_email and user_name:
            user_content += f"\n[User Info: Name='{user_name}', Email='{user_email}']"

        history.append({"role": "user", "content": user_content})

        # Try LLM Provider
        provider = settings.LLM_PROVIDER.lower()
        if provider == "openai" and settings.OPENAI_API_KEY:
            return await self._process_openai(history)
        elif provider == "gemini" and settings.GOOGLE_API_KEY:
            return await self._process_gemini(history)
        else:
            # Fallback heuristic processor when running without API keys
            return await self._process_heuristic_agent(user_message, user_email, user_name)

    async def _process_openai(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute OpenAI Function Calling loop with openai package."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL_NAME,
                messages=history,
                tools=TICKETING_TOOLS_DEFINITIONS,
                tool_choice="auto",
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                # Handle first tool call
                tool_call = msg.tool_calls[0]
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                logger.info(f"OpenAI invoking tool: {fn_name} with args: {fn_args}")
                tool_result = await self.execute_tool_call(fn_name, fn_args)

                # Feed result back to LLM for conversational final answer
                history.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [tool_call.model_dump()],
                })
                history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": json.dumps(tool_result),
                })

                second_resp = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL_NAME,
                    messages=history,
                )
                final_content = second_resp.choices[0].message.content
                history.append({"role": "assistant", "content": final_content})

                return {
                    "reply": final_content,
                    "action_taken": fn_name,
                    "data": tool_result,
                }
            else:
                history.append({"role": "assistant", "content": msg.content})
                return {
                    "reply": msg.content or "How can I help you find or book tickets today?",
                    "action_taken": None,
                    "data": None,
                }
        except Exception as e:
            logger.error(f"OpenAI agent error: {e}. Falling back to rule engine.")
            return await self._process_heuristic_agent(history[-1]["content"])

    async def _process_gemini(self, history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute Gemini LLM processing."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GOOGLE_API_KEY)
            model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
            
            # Simple Gemini prompt pass-through with tool augmentation
            prompt = f"{SYSTEM_PROMPT}\nUser Request: {history[-1]['content']}"
            resp = await model.generate_content_async(prompt)
            reply = resp.text
            return {
                "reply": reply,
                "action_taken": None,
                "data": None,
            }
        except Exception as e:
            logger.error(f"Gemini agent error: {e}. Falling back to rule engine.")
            return await self._process_heuristic_agent(history[-1]["content"])

    async def _process_heuristic_agent(
        self,
        message: str,
        user_email: Optional[str] = None,
        user_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Built-in intelligent rule engine for testing & demonstration when LLM API keys are not supplied.
        Handles search, seat queries, hold, confirmation, and status checks.
        """
        msg = message.lower()

        # 1. Booking confirmation
        if "confirm" in msg:
            import re
            match = re.search(r"BKG-[A-Z0-9]+", message, re.IGNORECASE)
            if match:
                ref = match.group(0).upper()
                result = await self.tools.confirm_booking(ref)
                if result.get("success"):
                    return {
                        "reply": result["message"],
                        "action_taken": "confirm_booking",
                        "data": result,
                    }
                else:
                    return {
                        "reply": f"Could not confirm booking: {result.get('error')}",
                        "action_taken": "confirm_booking",
                        "data": result,
                    }
            return {
                "reply": "Please provide the booking reference code you'd like to confirm (e.g., 'confirm BKG-A1B2C3D4').",
                "action_taken": None,
                "data": None,
            }

        # 2. Check booking status
        if "status" in msg or "check booking" in msg or "my ticket" in msg:
            import re
            match = re.search(r"BKG-[A-Z0-9]+", message, re.IGNORECASE)
            if match:
                ref = match.group(0).upper()
                result = await self.tools.check_booking_status(ref)
                return {
                    "reply": f"Booking details for {ref}:\nEvent: {result.get('event')}\nStatus: {result.get('status')}\nTotal: ${result.get('total_amount', 0):.2f}\nSeats: {', '.join(result.get('seats', []))}",
                    "action_taken": "check_booking_status",
                    "data": result,
                }
            return {
                "reply": "To check your booking status, please provide your booking reference (e.g., BKG-12345678).",
                "action_taken": None,
                "data": None,
            }

        # 3. Hold / Reserve seats
        if "hold" in msg or "book" in msg or "reserve" in msg:
            # Check if event id is mentioned
            import re
            event_match = re.search(r"event\s*(\d+)", msg)
            seat_matches = re.findall(r"seat\s*(\d+)", msg)
            if not seat_matches:
                seat_matches = re.findall(r"\b(\d+)\b", msg)

            if event_match and seat_matches:
                ev_id = int(event_match.group(1))
                s_ids = [int(s) for s in seat_matches if int(s) != ev_id]
                if s_ids:
                    name = user_name or "Guest Customer"
                    email = user_email or "guest@example.com"
                    result = await self.tools.hold_ticket_seats(
                        event_id=ev_id,
                        seat_ids=s_ids,
                        customer_name=name,
                        customer_email=email,
                    )
                    if result.get("success"):
                        return {
                            "reply": result["message"],
                            "action_taken": "hold_ticket_seats",
                            "data": result,
                        }
                    else:
                        return {
                            "reply": f"⚠️ Could not reserve seats: {result.get('error')}",
                            "action_taken": "hold_ticket_seats",
                            "data": result,
                        }

        # 4. View seats / inventory
        if "seat" in msg or "view seats" in msg or "tickets for" in msg:
            import re
            ev_match = re.search(r"(\d+)", msg)
            ev_id = int(ev_match.group(1)) if ev_match else 1
            result = await self.tools.get_event_seats(event_id=ev_id)
            if "error" in result:
                return {"reply": result["error"], "action_taken": None, "data": None}
            sample = [f"{s['seat_number']} (${s['price']:.0f})" for s in result.get("sample_available_seats", [])[:8]]
            return {
                "reply": (
                    f"Available seats for '{result.get('title')}' (Event ID: {ev_id}):\n"
                    f"Total available: {result.get('total_available')}\n"
                    f"Sample seats: {', '.join(sample)}\n\n"
                    f"To hold seats, say: 'Hold seat <seat_id> for event {ev_id}'."
                ),
                "action_taken": "get_event_seats",
                "data": result,
            }

        # 5. Search events (default discovery)
        events = await self.tools.search_events()
        if not events:
            return {
                "reply": "Hello! I am your AI ticketing assistant. There are currently no scheduled events in the system.",
                "action_taken": None,
                "data": None,
            }

        event_lines = [
            f"• [{e['event_id']}] {e['title']} @ {e['venue']} ({e['city']}) on {e['date']} — Starting from ${e['tiers'][0]['price']:.0f}"
            for e in events[:5]
        ]
        return {
            "reply": (
                "👋 Welcome! Here are the featured upcoming events:\n\n"
                + "\n".join(event_lines)
                + "\n\nAsk me to 'Show seats for event <ID>' or 'Hold seat <ID> for event <ID>' to start booking!"
            ),
            "action_taken": "search_events",
            "data": events,
        }

