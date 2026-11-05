"""
==============================================================================
CONCURRENCY STRESS TEST & ANTI-OVERBOOKING VERIFICATION DEMO
Simulates 20 simultaneous users hammering the backend to book the EXACT SAME SEAT.
Proves that Redis Distributed Locks & DB row locking prevent double-booking.
==============================================================================
"""
import asyncio
import time
from sqlalchemy import select
from app.core.database import AsyncSessionLocal, init_db
from app.models.seat import Seat, SeatStatus
from app.services.booking_service import BookingService
from scripts.seed_data import seed


async def attempt_hold(user_idx: int, event_id: int, target_seat_id: int) -> dict:
    """Simulate a single user attempting to hold the high-demand seat."""
    async with AsyncSessionLocal() as session:
        email = f"user_{user_idx}@concurrency-test.com"
        name = f"Contender #{user_idx}"
        try:
            booking = await BookingService.hold_seats(
                db=session,
                event_id=event_id,
                seat_ids=[target_seat_id],
                user_email=email,
                user_name=name,
            )
            return {
                "user": name,
                "success": True,
                "status": "ACQUIRED_HOLD",
                "reference": booking.booking_reference,
            }
        except Exception as e:
            return {
                "user": name,
                "success": False,
                "status": "REJECTED_CONFLICT",
                "error": str(e),
            }


async def run_stress_test(num_concurrent_users: int = 20):
    print("=" * 80)
    print(f"🔥 ANTI-OVERBOOKING CONCURRENCY STRESS TEST ({num_concurrent_users} Parallel Contenders)")
    print("=" * 80)

    # 1. Ensure DB is seeded
    await seed()

    # 2. Pick a single target seat
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Seat)
            .where(Seat.status == SeatStatus.AVAILABLE.value)
            .order_by(Seat.id.asc())
        )
        res = await session.execute(stmt)
        seat = res.scalars().first()
        if not seat:
            print("No available seat found to test. Resetting seats to AVAILABLE...")
            from sqlalchemy import update
            await session.execute(update(Seat).values(status=SeatStatus.AVAILABLE.value, hold_expires_at=None))
            await session.commit()
            seat = (await session.execute(stmt)).scalars().first()

        event_id = seat.event_id
        target_seat_id = seat.id
        seat_num = seat.seat_number

    print(f"🎯 Target Seat: ID={target_seat_id} ({seat_num}) for Event ID={event_id}")
    print(f"🚀 Firing {num_concurrent_users} concurrent requests at the exact same millisecond...\n")

    t0 = time.time()
    # Execute all 20 attempts concurrently using asyncio.gather
    tasks = [
        attempt_hold(user_idx=i, event_id=event_id, target_seat_id=target_seat_id)
        for i in range(1, num_concurrent_users + 1)
    ]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - t0

    # 3. Analyze Results
    successes = [r for r in results if r["success"]]
    conflicts = [r for r in results if not r["success"]]

    print("📊 RESULTS BREAKDOWN:")
    print("-" * 50)
    for r in results:
        status_icon = "✅" if r["success"] else "🛡️"
        extra = f"-> Ref: {r.get('reference')}" if r["success"] else f"-> {r.get('error')[:60]}..."
        print(f"  {status_icon} {r['user']}: {r['status']} {extra}")

    print("-" * 50)
    print(f"⏱️ Total Execution Time: {elapsed:.3f} seconds")
    print(f"✅ Successful Holds: {len(successes)} (Expected: exactly 1)")
    print(f"🛡️ Gracefully Blocked: {len(conflicts)} (Expected: {num_concurrent_users - 1})")

    # 4. Assert Anti-Overbooking Integrity
    assert len(successes) == 1, f"CRITICAL FAILURE: Expected 1 hold, got {len(successes)} (Overbooking occurred!)"
    assert len(conflicts) == num_concurrent_users - 1, "Unexpected conflict count."

    print("\n🎉 VERIFICATION PASSED: ZERO OVERBOOKING DETECTED!")
    print("Redis Distributed Lock and PostgreSQL row locking successfully prevented race conditions.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_stress_test(20))

