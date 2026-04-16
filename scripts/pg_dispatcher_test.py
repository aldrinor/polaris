"""Test the loopback dispatcher: drop synthetic pending requests, verify
classification and auto-serve behavior for each tier.
"""
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOOPBACK_DIR = Path(os.getenv("PG_LOOPBACK_DIR", "loopback"))
PENDING = LOOPBACK_DIR / "pending"
RESPONSES = LOOPBACK_DIR / "responses"
DONE = LOOPBACK_DIR / "done"

for d in (PENDING, RESPONSES, DONE):
    d.mkdir(parents=True, exist_ok=True)

# Clean
for d in (PENDING, RESPONSES):
    for f in d.glob("*.json"):
        f.unlink()


def make_request(schema: str, prompt: str, call_type: str = "") -> str:
    req_id = uuid.uuid4().hex[:12]
    ct = call_type or (f"structured:{schema}" if schema else "generate")
    req = {
        "request_id": req_id,
        "call_type": ct,
        "schema_name": schema or None,
        "schema_json": None,
        "system": "You are a test system",
        "prompt": prompt,
        "max_tokens": 2048,
        "temperature": 0.0,
        "reasoning_exclude": True,
        "timestamp": time.time(),
    }
    path = PENDING / f"req_{req_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(req, f, indent=2)
    return req_id


async def main():
    print("=" * 72)
    print("  Dispatcher test — 5 synthetic requests across all tiers")
    print("=" * 72)

    # Drop 5 requests: Tier A (2), Tier B (2), Tier C (1)
    reqs = [
        ("QueryPlan",            "intermittent fasting and weight loss",  "A"),
        ("SearchRefinement",     "refine these queries",                   "A"),
        ("SourceAnalysisBatch",  "analyze these sources",                  "B"),
        ("VerificationBatch",    "verify these claims",                    "B"),
        ("ReportOutline",        "generate outline for IF review",         "C"),
    ]
    req_ids = []
    for schema, prompt, expected in reqs:
        rid = make_request(schema, prompt)
        req_ids.append((rid, schema, expected))
        print(f"  dropped req_{rid} schema={schema} expected_tier={expected}")

    print("\n  Starting dispatcher in background for 8 seconds...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "scripts/loopback_dispatcher.py",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )

    captured = bytearray()
    start = time.time()

    async def drain():
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            captured.extend(chunk)

    drain_task = asyncio.create_task(drain())

    # Wait up to 8 seconds
    while time.time() - start < 8:
        await asyncio.sleep(0.5)

    # Shut down
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    drain_task.cancel()

    output = captured.decode("utf-8", errors="replace")

    # Check outcomes
    print("\n  Results:")
    results = {}
    for rid, schema, expected in req_ids:
        resp = RESPONSES / f"resp_{rid}.json"
        done_req = DONE / f"req_{rid}.json"
        pending_still = PENDING / f"req_{rid}.json"

        if expected == "A":
            # Should have been served → response file exists
            served = resp.exists()
            if not served:
                # Also check done/ in case of race
                served = done_req.exists()
            ok = served
            results[rid] = (ok, f"Tier A: response_written={resp.exists()} pending_cleared={not pending_still.exists()}")
        else:
            # Should have been announced → still pending, banner in output
            banner = f"OPERATOR NEEDED — TIER {expected}" in output and rid in output
            ok = banner and pending_still.exists()
            results[rid] = (ok, f"Tier {expected}: banner_seen={banner} still_pending={pending_still.exists()}")

    for rid, (ok, msg) in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] req_{rid}: {msg}")

    passed = sum(1 for ok, _ in results.values() if ok)
    total = len(results)
    print(f"\n  SUMMARY: {passed}/{total}")
    print("=" * 72)

    # Dump dispatcher output for diagnostics
    print("\n[dispatcher output - last 1500 chars]")
    print(output[-1500:])
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
