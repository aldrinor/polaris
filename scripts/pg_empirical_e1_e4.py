"""E1-E4 empirical tests for GLM-5.1 reasoning API compliance.

Per plan S1/S3 dependencies. These tests determine whether GLM-5.1 honors
OpenRouter's reasoning.max_tokens, reasoning.effort, reasoning.exclude, and
whether 429 responses include Retry-After / X-RateLimit-Reset headers.

Results drive S1 final shape — whether we pivot to non-reasoning model for
prose writing, or keep GLM-5.1 with API-level pool separation.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "z-ai/glm-5.1"
URL = "https://openrouter.ai/api/v1/chat/completions"


def _scaffolding_markers(text: str) -> int:
    """Count scaffolding patterns in a response (0 = clean prose)."""
    markers = [
        "1. **Analyze the Request",
        "**Review Claims:**",
        "**Plan the Section:**",
        "**Drafting",
        "LENS 1",
        "LENS 2",
        "Let me",
        "I need to",
        "I must",
    ]
    return sum(1 for m in markers if m in text)


PROSE_PROMPT = (
    "Write ONE paragraph (5-8 sentences) about intermittent fasting and "
    "insulin sensitivity based on these two findings: "
    "(1) 10-RCT meta-analysis n=701, fasting glucose SMD=-0.51, 95%% CI [-0.81, -0.20], p=0.001. "
    "(2) Alternate-day fasting 6.8%% fasting-glucose reduction in 8 weeks. "
    "Academic register, third person, no planning, no meta-commentary, no lists. "
    "Just the paragraph."
)


async def _call(client: httpx.AsyncClient, body: dict, label: str) -> dict:
    t0 = time.time()
    try:
        r = await client.post(
            URL,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=body,
            timeout=180.0,
        )
    except Exception as e:
        return {"label": label, "error": str(e), "elapsed": time.time() - t0}

    elapsed = time.time() - t0
    try:
        data = r.json()
    except Exception:
        return {"label": label, "status": r.status_code, "error": "non-JSON", "elapsed": elapsed}

    if r.status_code != 200:
        return {
            "label": label,
            "status": r.status_code,
            "error": data.get("error"),
            "headers": {k: r.headers.get(k) for k in ["retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"] if r.headers.get(k)},
            "elapsed": elapsed,
        }

    msg = (data.get("choices") or [{}])[0].get("message", {})
    usage = data.get("usage", {})
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""

    comp_details = usage.get("completion_tokens_details") or {}
    reasoning_tokens = comp_details.get("reasoning_tokens") or usage.get("reasoning_tokens") or 0
    content_tokens = max((usage.get("completion_tokens") or 0) - reasoning_tokens, 0)

    return {
        "label": label,
        "status": 200,
        "elapsed": elapsed,
        "content_chars": len(content),
        "reasoning_chars": len(reasoning),
        "content_tokens": content_tokens,
        "reasoning_tokens": reasoning_tokens,
        "completion_tokens_total": usage.get("completion_tokens", 0),
        "scaffolding_markers": _scaffolding_markers(content),
        "content_sample": (content[:300] + "...") if len(content) > 300 else content,
        "reasoning_sample_head": (reasoning[:150] + "...") if len(reasoning) > 150 else reasoning,
    }


async def e1_reasoning_max_tokens_cap():
    """E1: Does GLM-5.1 honor reasoning.max_tokens=4096 with max_tokens=16384?

    PASS: reasoning_tokens < 4500 AND content_chars > 500
    FAIL: if reasoning > 4500 (cap ignored) or content < 500 (truncation)
    """
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROSE_PROMPT}],
        "max_tokens": 16384,
        "reasoning": {"effort": "high", "max_tokens": 4096},
    }
    async with httpx.AsyncClient() as client:
        return await _call(client, body, "E1_reasoning_max_tokens_cap")


async def e2_reasoning_effort_low():
    """E2: Does GLM-5.1 honor reasoning.effort=low? Expect cheap reasoning.

    PASS: reasoning_tokens < 2000 AND content_tokens > 800
    FAIL: if reasoning > 2000 (effort ignored) or content < 800 (starvation)
    """
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROSE_PROMPT}],
        "max_tokens": 16384,
        "reasoning": {"effort": "low"},
    }
    async with httpx.AsyncClient() as client:
        return await _call(client, body, "E2_reasoning_effort_low")


async def e3_rate_limit_headers():
    """E3: Does a 429 response include Retry-After / X-RateLimit-Reset?

    Sends 30 concurrent calls to trigger throttle. Inspects headers on any 429.
    PASS: at least one 429 with Retry-After OR X-RateLimit-Reset
    FAIL: no 429s (can't test) OR 429 with no headers (sleep blindly)
    """
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say hi."}],
        "max_tokens": 64,
    }
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_call(client, body, f"e3_burst_{i}") for i in range(30)],
            return_exceptions=True,
        )
    rate_limits = [r for r in results if isinstance(r, dict) and r.get("status") == 429]
    return {
        "label": "E3_rate_limit_headers",
        "total_requests": 30,
        "429_count": len(rate_limits),
        "sample_429_headers": rate_limits[0].get("headers") if rate_limits else None,
        "other_statuses": {
            r.get("status", "err") for r in results if isinstance(r, dict)
        },
    }


async def e4_reasoning_exclude_true():
    """E4: Does reasoning.exclude=true produce non-empty content on GLM-5.1?

    Expected failure per community reports (CherryStudio #12473).
    PASS: content_chars > 500 (model honors exclude, routes to content)
    FAIL: content_chars < 100 (model ignores exclude, reasoning_content empty too)
    """
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROSE_PROMPT}],
        "max_tokens": 16384,
        "reasoning": {"effort": "high", "exclude": True},
    }
    async with httpx.AsyncClient() as client:
        return await _call(client, body, "E4_reasoning_exclude_true")


async def main():
    if not API_KEY:
        print("[FAIL] OPENROUTER_API_KEY not set")
        sys.exit(1)

    print("=" * 70)
    print(f"E1-E4 EMPIRICAL TESTS — model={MODEL}")
    print("=" * 70)

    # E1, E2, E4 run sequentially (cheap, informational)
    # E3 runs burst, skip if we don't want to waste credits
    run_e3 = os.getenv("RUN_E3", "1") == "1"

    print("\n[E1] reasoning.max_tokens=4096 cap ...")
    r1 = await e1_reasoning_max_tokens_cap()
    print(json.dumps(r1, indent=2, default=str))

    print("\n[E2] reasoning.effort=low ...")
    r2 = await e2_reasoning_effort_low()
    print(json.dumps(r2, indent=2, default=str))

    print("\n[E4] reasoning.exclude=true ...")
    r4 = await e4_reasoning_exclude_true()
    print(json.dumps(r4, indent=2, default=str))

    if run_e3:
        print("\n[E3] 429 header burst test (30 concurrent calls) ...")
        r3 = await e3_rate_limit_headers()
        print(json.dumps(r3, indent=2, default=str))
    else:
        print("\n[E3] SKIPPED (set RUN_E3=1 to enable)")
        r3 = {"label": "E3_rate_limit_headers", "skipped": True}

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    # E1 verdict
    e1_pass = (
        r1.get("status") == 200
        and r1.get("reasoning_tokens", 9999) < 4500
        and r1.get("content_chars", 0) > 500
    )
    print(f"E1 reasoning.max_tokens cap honored:   "
          f"{'PASS' if e1_pass else 'FAIL'} "
          f"(reasoning_tokens={r1.get('reasoning_tokens')}, "
          f"content_chars={r1.get('content_chars')})")

    # E2 verdict
    e2_pass = (
        r2.get("status") == 200
        and r2.get("reasoning_tokens", 9999) < 2000
        and r2.get("content_tokens", 0) > 800
    )
    print(f"E2 reasoning.effort=low honored:       "
          f"{'PASS' if e2_pass else 'FAIL'} "
          f"(reasoning_tokens={r2.get('reasoning_tokens')}, "
          f"content_tokens={r2.get('content_tokens')})")

    # E4 verdict
    e4_pass = r4.get("status") == 200 and r4.get("content_chars", 0) > 500
    print(f"E4 reasoning.exclude=true content OK:  "
          f"{'PASS' if e4_pass else 'FAIL'} "
          f"(content_chars={r4.get('content_chars')}, "
          f"reasoning_chars={r4.get('reasoning_chars')})")

    # E3 verdict
    if run_e3:
        e3_pass = r3.get("429_count", 0) > 0 and r3.get("sample_429_headers")
        e3_note = (
            f"(429_count={r3.get('429_count')}, "
            f"headers={r3.get('sample_429_headers')})"
            if r3.get("429_count")
            else "(no 429s triggered — cannot determine)"
        )
        print(f"E3 429 response headers present:       "
              f"{'PASS' if e3_pass else 'INCONCLUSIVE'} {e3_note}")

    print()
    print("IMPLICATIONS FOR S1:")
    if e1_pass and e4_pass:
        print("  ✅ S1 primary mechanism (reasoning.exclude + max_tokens cap) VIABLE as designed")
    elif e1_pass and not e4_pass:
        print("  ⚠ S1 reasoning.max_tokens cap works, but reasoning.exclude DOES NOT")
        print("     → S1 keeps reasoning_content extraction as the routing path, with max_tokens cap")
        print("     → S2 (quality gate detector) becomes PRIMARY defense against CoT leakage")
    elif not e1_pass:
        print("  ❌ GLM-5.1 IGNORES reasoning.max_tokens cap")
        if e2_pass:
            print("     → S1 falls back to effort-only lowering (S1 still useful)")
        else:
            print("     → GLM-5.1 UNSUITABLE for prose generation via effort/cap levers")
            print("     → PIVOT: switch section-write to non-reasoning model")
            print("       (qwen/qwen3.5-plus, anthropic/claude-haiku). Keep GLM-5.1 for analysis.")

    # Write results
    out = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": MODEL,
        "e1": r1,
        "e2": r2,
        "e3": r3 if run_e3 else {"skipped": True},
        "e4": r4,
        "verdicts": {
            "e1_pass": e1_pass,
            "e2_pass": e2_pass,
            "e4_pass": e4_pass,
        },
    }
    out_path = Path("C:/POLARIS/logs/empirical_e1_e4_results.json")
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[saved] {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
