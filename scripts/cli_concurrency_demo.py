"""
==============================================================================
HIGH-CONCURRENCY ANTI-OVERBOOKING STRESS TEST (Zero-Dependency)
Simulates 20 concurrent threads hammering to hold the EXACT SAME SEAT.
Proves that Distributed Locks prevent race-condition double-booking.
==============================================================================
"""
import concurrent.futures
import time
from scripts.cli_chat_assistant import tool_hold_seats, DB

def worker_attempt_hold(user_id):
    """Simulates an individual user attempting to grab Seat 101."""
    res = tool_hold_seats(
        event_id=1,
        seat_ids=[101],
        user_name=f"Contender #{user_id}",
        user_email=f"user{user_id}@test.com"
    )
    return user_id, res

def run_concurrency_stress_test(num_contenders=20):
    print("=" * 75)
    print(f"🔥 ANTI-OVERBOOKING CONCURRENCY STRESS TEST ({num_contenders} Parallel Contenders)")
    print("=" * 75)
    print("🎯 Target Seat: ID=101 (VIP-01) for Event #1 (Coldplay World Tour)")
    print(f"🚀 Firing {num_contenders} simultaneous requests simultaneously...\n")

    t0 = time.time()
    results = []

    # Fire all 20 attempts concurrently across thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_contenders) as executor:
        futures = [executor.submit(worker_attempt_hold, i) for i in range(1, num_contenders + 1)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    elapsed = time.time() - t0

    # Sort by user ID
    results.sort(key=lambda x: x[0])

    successes = [r for r in results if r[1].get("success")]
    failures = [r for r in results if not r[1].get("success")]

    print("📊 CONCURRENCY RESULTS BREAKDOWN:")
    print("-" * 55)
    for uid, res in results:
        if res.get("success"):
            print(f"  ✅ Contender #{uid:02d}: GRANTED HOLD -> Ref: {res['booking_reference']} (${res['total_amount']:.0f})")
        else:
            print(f"  🛡️ Contender #{uid:02d}: BLOCKED CONFLICT -> {res.get('error')}")

    print("-" * 55)
    print(f"⏱️ Total Execution Time: {elapsed:.4f} seconds")
    print(f"✅ Successful Holds: {len(successes)} (Expected: exactly 1)")
    print(f"🛡️ Gracefully Blocked: {len(failures)} (Expected: {num_contenders - 1})")

    assert len(successes) == 1, f"CRITICAL FAILURE: Expected 1 hold, got {len(successes)} (Double booking occurred!)"
    assert len(failures) == num_contenders - 1, "Unexpected failure count"

    print("\n🎉 VERIFICATION PASSED: ZERO DOUBLE-BOOKING DETECTED!")
    print("Anti-overbooking concurrency lock successfully protected the seat inventory.")
    print("=" * 75)

if __name__ == "__main__":
    run_concurrency_stress_test(20)

