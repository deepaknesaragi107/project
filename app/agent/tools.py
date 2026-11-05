import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.event_service import EventService
from app.services.booking_service import BookingService


class AgentBookingTools:
    """Execution bridge between LLM Function Calling and Backend Services."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_events(
        self,
        query: Optional[str] = None,
        city: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search available events, concerts, shows, and games."""
        events = await EventService.list_events(self.db, query=query, city=city, category=category, limit=10)
        output = []
        for ev in events:
            tiers = [
                {"tier_id": t.id, "name": t.name, "price": float(t.price), "total_seats": t.total_seats}
                for t in ev.tiers
            ]
            output.append({
                "event_id": ev.id,
                "title": ev.title,
                "category": ev.category,
                "date": ev.event_date.strftime("%Y-%m-%d %H:%M"),
                "venue": ev.venue.name,
                "city": ev.venue.city,
                "tiers": tiers,
            })
        return output

    async def get_event_seats(
        self,
        event_id: int,
        tier_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch currently available seats for an event to show to the customer."""
        seats = await EventService.get_available_seats(self.db, event_id=event_id, tier_name=tier_name)
        event = await EventService.get_event_by_id(self.db, event_id)
        if not event:
            return {"error": f"Event ID {event_id} not found."}

        available_list = [
            {
                "seat_id": s.id,
                "seat_number": s.seat_number,
                "row": s.row,
                "tier": s.tier.name,
                "price": float(s.tier.price),
            }
            for s in seats[:30]  # Return top 30 available
        ]

        return {
            "event_id": event.id,
            "title": event.title,
            "total_available": len(seats),
            "sample_available_seats": available_list,
        }

    async def hold_ticket_seats(
        self,
        event_id: int,
        seat_ids: List[int],
        customer_name: str,
        customer_email: str,
        customer_phone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Concurrency-safe hold on seats using Redis distributed lock.
        Creates a temporary hold for 10 minutes.
        """
        try:
            booking = await BookingService.hold_seats(
                db=self.db,
                event_id=event_id,
                seat_ids=seat_ids,
                user_email=customer_email,
                user_name=customer_name,
                user_phone=customer_phone,
            )
            return {
                "success": True,
                "booking_reference": booking.booking_reference,
                "status": booking.status,
                "total_amount": float(booking.total_amount),
                "hold_expires_at": booking.hold_expires_at.isoformat() if booking.hold_expires_at else None,
                "message": (
                    f"Successfully held {len(seat_ids)} seat(s)! "
                    f"Booking Reference: {booking.booking_reference}. "
                    f"Total: ${float(booking.total_amount):.2f}. "
                    f"This hold expires in 10 minutes. Please confirm to finalize."
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def confirm_booking(self, booking_reference: str) -> Dict[str, Any]:
        """Finalize and confirm the ticket reservation after user agrees."""
        try:
            booking = await BookingService.confirm_booking(self.db, booking_reference=booking_reference)
            return {
                "success": True,
                "booking_reference": booking.booking_reference,
                "status": booking.status,
                "event": booking.event.title,
                "total_paid": float(booking.total_amount),
                "message": (
                    f"🎉 Booking {booking.booking_reference} confirmed for '{booking.event.title}'! "
                    f"E-tickets have been issued."
                ),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check_booking_status(self, booking_reference: str) -> Dict[str, Any]:
        """Look up the status and details of an existing ticket reservation."""
        booking = await BookingService.get_booking_by_reference(self.db, booking_reference)
        if not booking:
            return {"error": f"Booking {booking_reference} not found."}

        seats = [f"{item.seat.seat_number} ({item.seat.tier.name})" for item in booking.items]
        return {
            "booking_reference": booking.booking_reference,
            "status": booking.status,
            "event": booking.event.title,
            "customer": booking.user.full_name,
            "email": booking.user.email,
            "total_amount": float(booking.total_amount),
            "seats": seats,
            "hold_expires_at": booking.hold_expires_at.isoformat() if booking.hold_expires_at else None,
        }


# Tool definitions for LLM function calling
TICKETING_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Search upcoming events, concerts, shows, sports matches, and festivals by keyword, city, or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query like artist or event title, e.g. 'Coldplay'"},
                    "city": {"type": "string", "description": "City where the event is taking place, e.g. 'Mumbai', 'New York'"},
                    "category": {"type": "string", "description": "Category e.g. 'Concert', 'Sports', 'Theater'"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event_seats",
            "description": "Fetch real-time available seats and pricing tiers for a specific event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer", "description": "The numeric ID of the event"},
                    "tier_name": {"type": "string", "description": "Optional tier name e.g. 'VIP', 'Standard'"}
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hold_ticket_seats",
            "description": "Place a concurrency-safe temporary hold (10 min) on selected seats for a customer using distributed locks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "integer", "description": "The event ID"},
                    "seat_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of numeric seat IDs to reserve"
                    },
                    "customer_name": {"type": "string", "description": "Customer's full name"},
                    "customer_email": {"type": "string", "description": "Customer's valid email address"},
                    "customer_phone": {"type": "string", "description": "Optional phone number"}
                },
                "required": ["event_id", "seat_ids", "customer_name", "customer_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_booking",
            "description": "Confirm and finalize a previously held booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_reference": {"type": "string", "description": "The booking reference code e.g. 'BKG-ABCD1234'"}
                },
                "required": ["booking_reference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_booking_status",
            "description": "Retrieve status and details of an existing reservation by booking reference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_reference": {"type": "string", "description": "Booking reference code e.g. 'BKG-ABCD1234'"}
                },
                "required": ["booking_reference"],
            },
        },
    },
]

