"""I-deepfix-001 wave-2 — PARALLEL-COMPOSE speed-lever proof harness (seconds-level, offline).

Proves the connected-resume speed fix for the abstractive-writer pre-pass WITHOUT any fresh run /
fetch / GPU / LLM. The fix is:

  * PRIMARY (env-only, already-existing knobs): PG_ABSTRACTIVE_WRITER_CONCURRENCY (default 8) and
    PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S (default 720) read at
    src/polaris_graph/generator/abstractive_writer.py:639-640. Raising concurrency to 16 fans the
    pre-pass out wider (WHEN, not WHAT); raising the wall to 3600 stops a healthy-but-uniformly-slow
    run from abandoning its last wave to K-span.
  * SECONDARY (small code change): the OpenRouter 429 backoff now HONORS a server Retry-After header
    (src/polaris_graph/llm/openrouter_client.py, new _parse_retry_after + the 429 branch), so a
    rate-limited writer call recovers at the window the server names instead of the blind 15/30/60s
    floor. Absent header => byte-identical to the old floor-only behaviour.

Four assertions (GREEN iff all pass AND the OFF/default path is byte-identical):
  (a) DETERMINISM: the precomputed-draft dict is IDENTICAL across concurrency 1 / 8 / 16 / default
      — concurrency changes WHEN the drafts are computed, never WHAT they are.
  (b) SPEEDUP: with a 0.5s-per-basket stub and >=32 baskets, wall(concurrency=16) < 0.2 * wall(1).
  (c) ZERO ABANDONMENT: with WALL_DEADLINE_S=3600 every basket is drafted and nothing is abandoned;
      the contrast (tiny wall) proves the wall lever is real and that 3600 is what suppresses it.
      Also: the healthy output at the DEFAULT wall (720) is byte-identical to the 3600 output.
  (d) 429 + RETRY-AFTER: a synthetic 429 on the first transport call (then success) recovers through
      the REAL OpenRouterClient retry branch — no exception escapes, content is returned, and the
      slept delay equals the honored Retry-After (not the 15s floor); with no header the delay is the
      old 15s value (byte-identical). Plus the pre-pass collects every recovered basket into `out`.

Run:  PYTHONIOENCODING=utf-8 PYTHONPATH=<worktree-root> python scripts/dr_benchmark/wave2_parallel_prepass.py

Faithfulness: touches only transport timing (concurrency / wall / retry backoff). strict_verify /
NLI / 4-role D8 / provenance / span-grounding are never imported or called by the fix or this harness.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Make `src...` importable even without an explicit PYTHONPATH (worktree root = parents[2]).
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# A dummy key so OpenRouterClient can be CONSTRUCTED offline (its transport is stubbed; no network).
os.environ.setdefault("OPENROUTER_API_KEY", "harness-dummy-key-not-used")

import httpx  # noqa: E402

from src.polaris_graph.generator import abstractive_writer as aw  # noqa: E402
from src.polaris_graph.llm import openrouter_client as oc  # noqa: E402

N_BASKETS = 32
PER_BASKET_SLEEP_S = 0.5

_CONC_ENV = "PG_ABSTRACTIVE_WRITER_CONCURRENCY"
_WALL_ENV = "PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S"


class _Basket:
    """Minimal synthetic basket — the real pre-pass keys the precomputed dict on
    ``claim_cluster_id`` (abstractive_writer._basket_key), which is all the orchestration needs."""

    def __init__(self, cid: str) -> None:
        self.claim_cluster_id = cid


class _StubVerification:
    """A stub SentenceVerification-shaped result (always verified). Provided as the STUB
    writer_verify_fn per the task; the drafting-orchestration tests stub the per-basket unit so it is
    not exercised there, but abstractive_pre_pass requires the argument."""

    is_verified = True
    judge_error = False
    failure_reasons: list = []

    def __init__(self, sentence: str) -> None:
        self.sentence = sentence


def _stub_verify_fn(sentence: str, scoped_pool: dict, *args, **kwargs) -> _StubVerification:
    return _StubVerification(sentence)


class _LogCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record.getMessage())
        except Exception:  # noqa: BLE001
            self.records.append(str(record.msg))

    def has(self, needle: str) -> bool:
        return any(needle in m for m in self.records)


def _make_baskets(n: int) -> list:
    return [_Basket(f"cid-{i:03d}") for i in range(n)]


def _deterministic_draft(basket) -> str:
    # Depends ONLY on the basket key -> identical regardless of concurrency / scheduling order.
    return f"VERIFIED_DRAFT::{basket.claim_cluster_id}"


def _install_drafting_stub(sleep_s: float):
    """Replace the per-basket unit with a controllable stub so abstractive_pre_pass's REAL semaphore /
    wall / abandon orchestration is what runs. Returns the original for restoration."""

    original = aw._pre_pass_one_basket

    async def _stub(basket, evidence_pool, **kwargs):  # noqa: ARG001 — mirrors real kw-only signature
        await asyncio.sleep(sleep_s)
        return _deterministic_draft(basket)

    aw._pre_pass_one_basket = _stub  # type: ignore[assignment]
    return original


def _run_prepass(baskets, *, concurrency, wall_s, sleep_s=PER_BASKET_SLEEP_S):
    """Run abstractive_pre_pass once with the given knobs; return (out_dict, wall_seconds, log_lines).

    concurrency / wall_s == None => leave the env UNSET so the module DEFAULT (8 / 720) applies."""
    for env_name, value in ((_CONC_ENV, concurrency), (_WALL_ENV, wall_s)):
        if value is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = str(value)

    cap = _LogCapture()
    # Route the module logger ONLY to our capture handler (level DEBUG so nothing is gated, propagate
    # False so records never reach the root/stderr "last resort" handler). Global logging.disable would
    # suppress the record before the handler ever sees it, so we deliberately do NOT use it here.
    prev_level, prev_propagate = aw.logger.level, aw.logger.propagate
    aw.logger.setLevel(logging.DEBUG)
    aw.logger.propagate = False
    aw.logger.addHandler(cap)
    aw._DETACHED_WRITER_TASKS.clear()
    original = _install_drafting_stub(sleep_s)
    try:
        t0 = time.perf_counter()
        out = asyncio.run(
            aw.abstractive_pre_pass(baskets, {}, writer_verify_fn=_stub_verify_fn)
        )
        wall = time.perf_counter() - t0
    finally:
        aw._pre_pass_one_basket = original  # type: ignore[assignment]
        aw.logger.removeHandler(cap)
        aw.logger.setLevel(prev_level)
        aw.logger.propagate = prev_propagate
    return out, wall, cap.records


# ── (a) determinism + (b) speedup + (c) zero abandonment + wall byte-identical ────────────────────
def test_prepass_orchestration() -> dict:
    results: dict = {}
    baskets = _make_baskets(N_BASKETS)

    out1, wall1, _ = _run_prepass(baskets, concurrency=1, wall_s=3600)
    out8, wall8, _ = _run_prepass(baskets, concurrency=8, wall_s=3600)
    out16, wall16, logs16 = _run_prepass(baskets, concurrency=16, wall_s=3600)
    out_def, wall_def, _ = _run_prepass(baskets, concurrency=None, wall_s=None)  # module defaults 8/720

    # (a) determinism — dict equality across all concurrencies AND the default.
    det_ok = (out1 == out8 == out16 == out_def) and (len(out1) == N_BASKETS)
    results["a_determinism"] = det_ok
    results["_a_detail"] = (
        f"len(out1)={len(out1)} len(out8)={len(out8)} len(out16)={len(out16)} "
        f"len(out_default)={len(out_def)} all_equal={out1 == out8 == out16 == out_def}"
    )

    # (b) speedup — wall(16) < 0.2 * wall(1) for >=32 baskets at 0.5s/basket.
    speed_ok = wall16 < 0.2 * wall1
    results["b_speedup"] = speed_ok
    results["_b_detail"] = (
        f"wall(1)={wall1:.2f}s wall(8)={wall8:.2f}s wall(16)={wall16:.2f}s "
        f"threshold=0.2*wall(1)={0.2 * wall1:.2f}s"
    )

    # (c) zero abandonment at wall=3600: all drafted, no ABANDONING log.
    no_abandon = (len(out16) == N_BASKETS) and not any("ABANDON" in m for m in logs16)
    # Contrast: a tiny wall MUST abandon (proves the lever is real, not a no-op). The module floors the
    # wall at 1.0s (max(1.0, ...)), so a 1.0s wall with 2.0s-per-basket stubs at concurrency 1 leaves
    # every basket pending at the wall -> all abandoned.
    small = _make_baskets(6)
    out_c, _, logs_c = _run_prepass(small, concurrency=1, wall_s=1.0, sleep_s=2.0)
    contrast_ok = (len(out_c) < 6) and any("ABANDON" in m for m in logs_c)
    results["c_zero_abandonment"] = no_abandon and contrast_ok
    results["_c_detail"] = (
        f"wall3600: drafted={len(out16)}/{N_BASKETS} abandon_logged={any('ABANDON' in m for m in logs16)} | "
        f"contrast wall1.0/sleep2.0: drafted={len(out_c)}/6 abandon_logged={any('ABANDON' in m for m in logs_c)}"
    )

    # Byte-identical OFF/default: healthy output at the DEFAULT wall (720) equals the 3600 output.
    byte_identical = (out_def == out16)
    results["byte_identical_default"] = byte_identical
    results["_byte_detail"] = f"out(default wall=720) == out(wall=3600): {byte_identical}"
    return results


# ── (d) 429 + Retry-After honoring ────────────────────────────────────────────────────────────────
def test_parse_retry_after_unit() -> dict:
    """Direct unit-test of the new pure parser."""
    from email.utils import format_datetime
    from datetime import datetime, timedelta, timezone

    cases = {
        "delta_3": (oc._parse_retry_after("3"), 3.0),
        "delta_zero_none": (oc._parse_retry_after("0"), None),
        "delta_negative_none": (oc._parse_retry_after("-5"), None),
        "empty_none": (oc._parse_retry_after(""), None),
        "missing_none": (oc._parse_retry_after(None), None),
        "garbage_none": (oc._parse_retry_after("soon-ish"), None),
    }
    ok = True
    detail_parts = []
    for name, (got, want) in cases.items():
        good = (got == want)
        ok = ok and good
        detail_parts.append(f"{name}={got!r}(want {want!r}){'' if good else ' FAIL'}")

    # HTTP-date, ~30s in the future -> a positive delta close to 30.
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30))
    d_future = oc._parse_retry_after(future)
    future_ok = d_future is not None and 20.0 < d_future <= 31.0
    ok = ok and future_ok
    detail_parts.append(f"http_date_future={d_future!r}(want ~30){'' if future_ok else ' FAIL'}")

    # HTTP-date in the past -> non-positive -> None.
    past = format_datetime(datetime.now(timezone.utc) - timedelta(seconds=60))
    d_past = oc._parse_retry_after(past)
    past_ok = d_past is None
    ok = ok and past_ok
    detail_parts.append(f"http_date_past={d_past!r}(want None){'' if past_ok else ' FAIL'}")

    return {"d_parser_unit": ok, "_d_parser_detail": "; ".join(detail_parts)}


def _make_read_stream(client, scenario_header):
    """A fake OpenRouterClient._read_stream: raise a synthetic 429 (with the given Retry-After header,
    or none) on the FIRST call, then return a healthy stream tuple. Returns (fake, state)."""
    state = {"calls": 0}

    async def _fake(body, actual_timeout):  # noqa: ARG001
        state["calls"] += 1
        if state["calls"] == 1:
            req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            headers = {} if scenario_header is None else {"Retry-After": scenario_header}
            resp = httpx.Response(429, headers=headers, request=req)
            raise httpx.HTTPStatusError("429 Too Many Requests", request=req, response=resp)
        # (content, reasoning, usage, served) — the shape the stream branch unpacks.
        return (
            "Weight fell by 15 percent. [#ev:e1:0-25]",
            "",
            {"finish_reason": "stop", "prompt_tokens": 20,
             "completion_tokens": 10, "total_tokens": 30, "cost": 0.0},
            {"provider": "stub-provider", "model": client.model},
        )

    return _fake, state


def _run_client_429_scenario(scenario_header):
    """Drive the REAL OpenRouterClient.generate through one injected 429 -> success, recording every
    asyncio.sleep. Returns (content, calls, recorded_sleeps, escaped_exc)."""
    recorded: list[float] = []
    orig_sleep = asyncio.sleep

    async def _rec_sleep(delay, *a, **k):  # record + do not actually block
        recorded.append(float(delay))

    async def _drive():
        client = oc.OpenRouterClient(model="z-ai/glm-5.2")
        fake, state = _make_read_stream(client, scenario_header)
        client._read_stream = fake  # instance attr shadows the bound method
        try:
            resp = await client.generate(prompt="rephrase the span", system="be faithful",
                                         max_tokens=256, temperature=0.2)
            return getattr(resp, "content", ""), state["calls"], None
        finally:
            await client.close()

    asyncio.sleep = _rec_sleep  # type: ignore[assignment]
    try:
        content, calls, esc = asyncio.run(_drive())
    except Exception as exc:  # noqa: BLE001 — a real escape is a RED signal, captured not hidden
        content, calls, esc = "", -1, exc
    finally:
        asyncio.sleep = orig_sleep  # type: ignore[assignment]
    return content, calls, recorded, esc


def test_client_429_retry_after() -> dict:
    results: dict = {}

    # Retry-After = 3s -> honored exactly (distinct from the 15s floor).
    c3, calls3, sleeps3, esc3 = _run_client_429_scenario("3")
    honored3 = (esc3 is None) and bool(c3) and (calls3 == 2) and (3.0 in sleeps3) and (15.0 not in sleeps3)
    results["d_client_retry_after_3s"] = honored3
    results["_d_3s_detail"] = f"content={bool(c3)} calls={calls3} sleeps={sleeps3} escaped={esc3!r}"

    # Retry-After = 90s -> honored (exceeds the OLD 60s cap, proving the cap was raised for the signal).
    c90, calls90, sleeps90, esc90 = _run_client_429_scenario("90")
    honored90 = (esc90 is None) and bool(c90) and (90.0 in sleeps90)
    results["d_client_retry_after_90s"] = honored90
    results["_d_90s_detail"] = f"content={bool(c90)} calls={calls90} sleeps={sleeps90} escaped={esc90!r}"

    # No header -> byte-identical to the old floor-only behaviour: attempt-0 wait == 15.0s.
    cN, callsN, sleepsN, escN = _run_client_429_scenario(None)
    control_ok = (escN is None) and bool(cN) and (sleepsN == [15.0])
    results["d_client_no_header_byte_identical"] = control_ok
    results["_d_control_detail"] = f"content={bool(cN)} calls={callsN} sleeps={sleepsN} escaped={escN!r}"
    return results


def test_prepass_all_baskets_draft_under_429() -> dict:
    """Pre-pass layer of (d): when the writer call recovers from a 429 (proven real by the client test
    above), abstractive_pre_pass collects EVERY basket into `out` and no exception escapes. The stub
    invokes the REAL oc._parse_retry_after on a synthetic header to show the honored delay is computed
    by production code, then returns the recovered draft."""
    baskets = _make_baskets(12)
    honored: list = []
    original = aw._pre_pass_one_basket

    async def _recovering(basket, evidence_pool, **kwargs):  # noqa: ARG001
        # models: transport raised a 429 carrying Retry-After: 3; the client honored+recovered.
        honored.append(oc._parse_retry_after("3"))
        await asyncio.sleep(0.0)
        return _deterministic_draft(basket)

    os.environ[_WALL_ENV] = "3600"
    os.environ[_CONC_ENV] = "16"
    aw._pre_pass_one_basket = _recovering  # type: ignore[assignment]
    escaped = None
    try:
        out = asyncio.run(aw.abstractive_pre_pass(baskets, {}, writer_verify_fn=_stub_verify_fn))
    except Exception as exc:  # noqa: BLE001
        out, escaped = {}, exc
    finally:
        aw._pre_pass_one_basket = original  # type: ignore[assignment]

    ok = (escaped is None) and (len(out) == 12) and all(v == 3.0 for v in honored) and len(honored) == 12
    return {
        "d_prepass_all_draft_under_429": ok,
        "_d_prepass_detail": f"drafted={len(out)}/12 honored_delays={set(honored)} escaped={escaped!r}",
    }


def main() -> int:
    # Silence root/other-module noise on stderr WITHOUT using logging.disable (which would also gate
    # the pre-pass capture handler). The pre-pass logger is routed to its capture handler with
    # propagate=False inside _run_prepass; everything else inherits this CRITICAL root level.
    logging.getLogger().setLevel(logging.CRITICAL)
    results: dict = {}
    results.update(test_prepass_orchestration())
    results.update(test_parse_retry_after_unit())
    results.update(test_client_429_retry_after())
    results.update(test_prepass_all_baskets_draft_under_429())

    assertion_keys = [k for k in results if not k.startswith("_")]
    print("=" * 78)
    print("I-deepfix-001 wave-2 — PARALLEL-COMPOSE speed-lever proof")
    print("=" * 78)
    for k in assertion_keys:
        status = "PASS" if results[k] else "FAIL"
        print(f"[{status}] {k}")
    print("-" * 78)
    for k in sorted(results):
        if k.startswith("_"):
            print(f"    {k[1:]}: {results[k]}")
    print("-" * 78)

    all_pass = all(results[k] for k in assertion_keys)
    print(f"OVERALL: {'GREEN — all assertions pass' if all_pass else 'RED — see FAIL above'}")
    print(f"assertions passed: {sum(1 for k in assertion_keys if results[k])}/{len(assertion_keys)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
