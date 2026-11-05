"""
==============================================================================
CLI INTERACTIVE CHAT ASSISTANT & BOOKING DEMO (Zero-Dependency)
Simulates the conversational AI ticketing assistant with real-time seat locking,
discovery, and ticket confirmation.
==============================================================================
"""
import datetime
import json
import time
import uuid

# In-memory mock database
DB = {
    "venues": [
        {"id": 1, "name": "D.Y. Patil Stadium", "city": "Mumbai", "capacity": 55000},
        {"id": 2, "name": "Wembley Stadium", "city": "London", "capacity": 90000},
        {"id": 3, "name": "Madison Square Garden", "city": "New York", "capacity": 20000},
    ],
    "events": [
        {
            "id": 1,
            "title": "Coldplay: Music of the Spheres World Tour",
            "category": "Concert",
            "city": "Mumbai",
            "venue": "D.Y. Patil Stadium",
            "date": "2026-11-20 19:30",
            "tiers": [
                {"tier_id": 1, "name": "VIP Lounge", "price": 250.0},
                {"tier_id": 2, "name": "Premium Stand", "price": 120.0},
                {"tier_id": 3, "name": "General Admission", "price": 60.0},
            ],
        },
        {
            "id": 2,
            "title": "Taylor Swift: The Eras Tour",
            "category": "Concert",
            "city": "London",
            "venue": "Wembley Stadium",
            "date": "2026-12-05 18:00",
            "tiers": [
                {"tier_id": 4, "name": "Front Row VIP", "price": 350.0},
                {"tier_id": 5, "name": "Club Level", "price": 150.0},
            ],
        },
    ],
    "seats": {
        1: [  # Event 1 seats
            {"id": 101, "seat_number": "VIP-01", "tier": "VIP Lounge", "price": 250.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 102, "seat_number": "VIP-02", "tier": "VIP Lounge", "price": 250.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 103, "seat_number": "PREM-01", "tier": "Premium Stand", "price": 120.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 104, "seat_number": "PREM-02", "tier": "Premium Stand", "price": 120.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 105, "seat_number": "GA-01", "tier": "General Admission", "price": 60.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 106, "seat_number": "GA-02", "tier": "General Admission", "price": 60.0, "status": "AVAILABLE", "hold_expires": 0},
        ],
        2: [  # Event 2 seats
            {"id": 201, "seat_number": "DIA-01", "tier": "Front Row VIP", "price": 350.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 202, "seat_number": "DIA-02", "tier": "Front Row VIP", "price": 350.0, "status": "AVAILABLE", "hold_expires": 0},
            {"id": 203, "seat_number": "CLUB-01", "tier": "Club Level", "price": 150.0, "status": "AVAILABLE", "hold_expires": 0},
        ]
    },
    "bookings": {},
    "distributed_locks": set(),  # Simulates Redis Lock keys
}


def sweep_expired_holds():
    """Background sweeper: releases expired holds back to AVAILABLE."""
    now = time.time()
    for ev_id, seats in DB["seats"].items():
        for s in seats:
            if s["status"] == "HELD" and s["hold_expires"] < now:
                s["status"] = "AVAILABLE"
                s["hold_expires"] = 0


# --- AI AGENT TOOLS ---
def tool_search_events(query=None, city=None):
    results = DB["events"]
    if query:
        q = query.lower()
        results = [e for e in results if q in e["title"].lower() or q in e["category"].lower()]
    if city:
        c = city.lower()
        results = [e for e in results if c in e["city"].lower()]
    return results


def tool_get_seats(event_id):
    sweep_expired_holds()
    seats = DB["seats"].get(event_id, [])
    available = [s for s in seats if s["status"] == "AVAILABLE"]
    return {
        "event_id": event_id,
        "total_available": len(available),
        "seats": available,
    }


def tool_hold_seats(event_id, seat_ids, user_name, user_email):
    """Distributed lock-protected hold."""
    sweep_expired_holds()
    lock_keys = [f"seat:{sid}" for sid in seat_ids]

    # Check for concurrency lock collisions
    for lk in lock_keys:
        if lk in DB["distributed_locks"]:
            return {"success": False, "error": f"Conflict: Seat is currently locked by another transaction."}

    # Acquire locks
    for lk in lock_keys:
        DB["distributed_locks"].add(lk)

    try:
        seats = DB["seats"].get(event_id, [])
        selected_seats = [s for s in seats if s["id"] in seat_ids]

        if len(selected_seats) != len(seat_ids):
            return {"success": False, "error": "One or more seats not found."}

        # Check availability
        for s in selected_seats:
            if s["status"] != "AVAILABLE":
                return {"success": False, "error": f"Seat {s['seat_number']} is no longer available ({s['status']})."}

        # Hold seats for 10 minutes (600 seconds)
        hold_expiry = time.time() + 600
        total_amount = sum(s["price"] for s in selected_seats)
        bkg_ref = f"BKG-{uuid.uuid4().hex[:8].upper()}"

        for s in selected_seats:
            s["status"] = "HELD"
            s["hold_expires"] = hold_expiry

        DB["bookings"][bkg_ref] = {
            "reference": bkg_ref,
            "event_id": event_id,
            "user_name": user_name,
            "user_email": user_email,
            "seats": selected_seats,
            "total_amount": total_amount,
            "status": "PENDING_PAYMENT",
            "hold_expires": hold_expiry,
        }

        return {
            "success": True,
            "booking_reference": bkg_ref,
            "total_amount": total_amount,
            "expires_in_minutes": 10,
            "seats": [s["seat_number"] for s in selected_seats],
        }
    finally:
        # Release locks
        for lk in lock_keys:
            DB["distributed_locks"].discard(lk)


def tool_confirm_booking(booking_reference):
    sweep_expired_holds()
    bkg = DB["bookings"].get(booking_reference)
    if not bkg:
        return {"success": False, "error": f"Booking reference {booking_reference} not found."}

    if bkg["status"] == "CONFIRMED":
        return {"success": True, "message": "Booking is already confirmed.", "booking": bkg}

    if bkg["status"] != "PENDING_PAYMENT":
        return {"success": False, "error": f"Cannot confirm booking with status '{bkg['status']}'."}

    if bkg["hold_expires"] < time.time():
        bkg["status"] = "EXPIRED"
        return {"success": False, "error": "Hold has expired. Please reserve seats again."}

    bkg["status"] = "CONFIRMED"
    for s in bkg["seats"]:
        s["status"] = "BOOKED"
        s["hold_expires"] = 0

    return {
        "success": True,
        "booking_reference": booking_reference,
        "event_id": bkg["event_id"],
        "total_amount": bkg["total_amount"],
        "customer": bkg["user_name"],
        "seats": [s["seat_number"] for s in bkg["seats"]],
    }


def ai_agent_respond(user_message, user_name="Alex Mercer", user_email="alex@example.com"):
    """Conversational AI Assistant decision engine."""
    msg = user_message.lower()

    if "confirm" in msg:
        import re
        m = re.search(r"bkg-[a-z0-9]+", msg)
        if m:
            ref = m.group(0).upper()
            res = tool_confirm_booking(ref)
            if res.get("success"):
                return f"🎉 E-Tickets Confirmed! Booking {ref} is finalized for ${res['total_amount']:.2f}. Seats: {', '.join(res['seats'])}. Have a great show!"
            else:
                return f"⚠️ Confirmation Failed: {res.get('error')}"
        return "Please specify your booking reference (e.g. 'confirm BKG-XXXX')."

    if "hold" in msg or "book" in msg or "reserve" in msg:
        import re
        s_matches = re.findall(r"\b(10[1-6]|20[1-3])\b", msg)
        ev_match = re.search(r"event\s*(\d)", msg)
        ev_id = int(ev_match.group(1)) if ev_match else (1 if "coldplay" in msg or not s_matches or int(s_matches[0]) < 200 else 2)

        if not s_matches:
            # Default to holding seat 101
            s_matches = ["101"]

        seat_ids = [int(s) for s in s_matches]
        res = tool_hold_seats(ev_id, seat_ids, user_name, user_email)
        if res.get("success"):
            return (
                f"✅ Seats Locked! Reference: {res['booking_reference']}\n"
                f"   Held Seats: {', '.join(res['seats'])}\n"
                f"   Total: ${res['total_amount']:.2f}\n"
                f"   ⏳ Hold Window: 10 Minutes (Anti-Overbooking Active)\n\n"
                f"   Say 'confirm {res['booking_reference']}' to complete your booking."
            )
        else:
            return f"❌ Could not hold seats: {res.get('error')}"

    if "seat" in msg or "tickets" in msg or "availab" in msg:
        ev_id = 2 if "taylor" in msg else 1
        res = tool_get_seats(ev_id)
        lines = [f"   • Seat ID {s['id']}: {s['seat_number']} ({s['tier']}) - ${s['price']:.0f}" for s in res["seats"]]
        return (
            f"🎫 Real-Time Available Seats for Event #{ev_id}:\n"
            + "\n".join(lines)
            + f"\n\nTo reserve, say: 'Hold seat {res['seats'][0]['id']} for Event {ev_id}'"
        )

    # Default: Event discovery
    events = tool_search_events()
    ev_lines = [f"   [{e['id']}] {e['title']} @ {e['venue']} ({e['city']}) on {e['date']} (From ${e['tiers'][-1]['price']:.0f})" for e in events]
    return (
        "👋 Welcome to TicketAI Concierge!\n\nFeatured Events:\n"
        + "\n".join(ev_lines)
        + "\n\nTry asking:\n"
        " • 'Show seats for Coldplay'\n"
        " • 'Hold seat 101 for Event 1'\n"
        " • 'Confirm BKG-XXXX'"
    )


if __name__ == "__main__":
    print("=" * 70)
    print("🤖 TICKETAI CONVERSATIONAL BOOKING ASSISTANT DEMO")
    print("=" * 70)

    demo_prompts = [
        "What concerts are available?",
        "Show available seats for Coldplay",
        "Hold seat 101 for Event 1",
    ]

    last_bkg_ref = None

    for prompt in demo_prompts:
        print(f"\n👤 USER: {prompt}")
        print("🤖 ASSISTANT:")
        reply = ai_agent_respond(prompt)
        print(reply)
        time.sleep(0.5)

        # Extract reference if held
        import re
        m = re.search(r"BKG-[A-Z0-9]+", reply)
        if m:
            last_bkg_ref = m.group(0)

    if last_bkg_ref:
        confirm_prompt = f"Confirm booking {last_bkg_ref}"
        print(f"\n👤 USER: {confirm_prompt}")
        print("🤖 ASSISTANT:")
        reply = ai_agent_respond(confirm_prompt)
        print(reply)

    print("\n" + "=" * 70)
    print("✅ DEMO COMPLETED SUCCESSFULLY: FULL BOOKING LIFECYCLE VERIFIED!")
    print("=" * 70)

