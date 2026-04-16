"""Phase 1 smoke test: verify LoopbackLLMClient produces pending files and blocks.

Spawns a background task that calls client.generate(), watches loopback/pending/
for the request file, writes a canned response, confirms client returns.

Proves the loopback mechanism works end-to-end at the client layer.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)

# Force loopback on for this test
os.environ["PG_LOOPBACK_MODE"] = "1"

from src.polaris_graph.llm.loopback_client import (
    LoopbackLLMClient, PENDING_DIR, RESPONSES_DIR,
)


async def main():
    print("=" * 72)
    print("  Phase 1: LoopbackLLMClient smoke test")
    print("=" * 72)

    # Clean the dirs to ensure deterministic state
    for d in (PENDING_DIR, RESPONSES_DIR):
        for f in d.glob("*.json"):
            f.unlink()

    client = LoopbackLLMClient(session_id="smoke_test")

    async def caller():
        """Make one generate call — should block until response appears."""
        t0 = time.time()
        response = await client.generate(
            prompt="Say hello in 3 words.",
            system="You are a minimal test responder.",
            max_tokens=128,
            timeout=30.0,
        )
        elapsed = time.time() - t0
        return response, elapsed

    async def responder():
        """Watch pending/, write response, confirm cleanup."""
        # Wait for a pending file to appear (should be within ~1s)
        deadline = time.time() + 10
        req_path = None
        while time.time() < deadline:
            pending = list(PENDING_DIR.glob("req_*.json"))
            if pending:
                req_path = pending[0]
                break
            await asyncio.sleep(0.2)

        if req_path is None:
            print("[FAIL] No pending file appeared within 10s")
            return False

        print(f"[OK] Pending file appeared: {req_path.name}")

        # Read request to confirm structure
        with open(req_path, encoding="utf-8") as f:
            req = json.load(f)
        print(f"[OK] Request structure: call_type={req.get('call_type')}, "
              f"prompt_len={len(req.get('prompt',''))}, "
              f"system_len={len(req.get('system',''))}")

        # Write response
        req_id = req["request_id"]
        resp_path = RESPONSES_DIR / f"resp_{req_id}.json"
        with open(resp_path, "w", encoding="utf-8") as f:
            json.dump({
                "content": "hello from smoke",
                "reasoning": "",
                "input_tokens": 10,
                "output_tokens": 5,
            }, f)
        print(f"[OK] Response written: {resp_path.name}")
        return True

    # Run caller + responder concurrently
    caller_task = asyncio.create_task(caller())
    responder_task = asyncio.create_task(responder())

    responded = await responder_task
    if not responded:
        caller_task.cancel()
        print("[FAIL] Responder did not complete")
        return 1

    try:
        response, elapsed = await asyncio.wait_for(caller_task, timeout=5.0)
    except asyncio.TimeoutError:
        print("[FAIL] Client did not return after response was written")
        return 1

    print(f"[OK] Client returned in {elapsed:.2f}s")
    print(f"[OK] Response content: '{response.content}'")
    print(f"[OK] Response tokens in/out: {response.input_tokens}/{response.output_tokens}")

    # Assertions
    checks = {
        "pending_appeared": True,
        "content_propagated": response.content == "hello from smoke",
        "tokens_recorded": response.input_tokens == 10 and response.output_tokens == 5,
        "archived": not (RESPONSES_DIR / f"resp_{response.raw_response['request_id']}.json").exists(),
    }
    print()
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    print(f"\n  SUMMARY: {passed}/{total}")
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(asyncio.run(main()))
