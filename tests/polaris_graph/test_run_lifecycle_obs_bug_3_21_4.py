"""Run-lifecycle observability + crash-safety tests (BUG-3 / BUG-21 / BUG-4, #1262).

These exercise the three run-orchestration fixes in ``scripts/run_honest_sweep_r3.py``:

- BUG-3  — the generation-phase heartbeat ticker re-stamps run_status.json so a tailer sees
           real progress instead of a frozen ``generation_started`` for the ~1.5-2h phase, AND
           the verification-loop counters (claims_verified/claims_total) populate (not None).
- BUG-21 — a ``run_one_query`` ENTRY-SETUP failure (e.g. a reasoning-collector init raise)
           still writes a TERMINAL ``manifest.json`` with ``status=error_*`` (+ exception type/
           phase) and re-raises, instead of leaving run_status.json frozen with no terminal
           artifact (the drb_76 silent-death class). MANDATORY regression test.
- BUG-4  — the manifest ``retrieval`` section carries a ``retrieval_caps`` disclosure block
           (candidates_discovered / fetched / dropped_pre_fetch / search_truncations) so a
           capped breadth is visible + auditable.

SPEND-FREE / OFFLINE: no network, no real pipeline, no paid call. Drives the real module
helpers + a monkeypatched entry-setup failure. NO unittest.mock (per CLAUDE.md §9.4) — uses
real callables + monkeypatch + tmp_path. Serialized per §8.4 (pure-python, no heavy ML).

Faithfulness: every assertion here is about observability / crash-safety / disclosure. None
of the code under test touches a span, provenance, strict_verify / NLI / 4-role check, or any
verdict; these tests do not relax any faithfulness gate.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import time

import pytest

from src.polaris_graph.telemetry import run_status_heartbeat as hb

sweep = importlib.import_module("scripts.run_honest_sweep_r3")


# ─────────────────────────────────────────────────────────────────────────────
# BUG-3 — generation-phase heartbeat ticker is NOT frozen + the cadence helper
# ─────────────────────────────────────────────────────────────────────────────
def test_generation_tick_cadence_default_and_env(monkeypatch):
    """The tick cadence defaults to a positive value (ticker ON) and is env-overridable;
    a non-positive / unparseable value returns 0.0 = DISABLED (LAW VI)."""
    monkeypatch.delenv(sweep._GENERATION_HEARTBEAT_TICK_ENV, raising=False)
    assert sweep.generation_heartbeat_tick_seconds() > 0  # default ON

    monkeypatch.setenv(sweep._GENERATION_HEARTBEAT_TICK_ENV, "5")
    assert sweep.generation_heartbeat_tick_seconds() == 5.0

    monkeypatch.setenv(sweep._GENERATION_HEARTBEAT_TICK_ENV, "0")
    assert sweep.generation_heartbeat_tick_seconds() == 0.0  # disabled, not frozen-forever

    monkeypatch.setenv(sweep._GENERATION_HEARTBEAT_TICK_ENV, "not-a-number")
    assert sweep.generation_heartbeat_tick_seconds() > 0  # falls back to default, never crashes


def test_generation_ticker_restamps_heartbeat_not_frozen(tmp_path, monkeypatch):
    """The background ticker re-stamps run_status.json during the long single generation
    await, so ``last_update_utc`` ADVANCES (not frozen) and stage reflects the live sub-phase.

    Drives the REAL ``_periodic_heartbeat_ticker`` against a REAL ``_hb``-style closure that
    writes the REAL heartbeat file (the same ``write_heartbeat`` the run uses)."""
    run_dir = tmp_path / "run"
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)

    started = time.monotonic()
    stages_seen: list[str] = []

    def _hb(stage: str, **kw) -> None:
        stages_seen.append(stage)
        hb.write_heartbeat(
            run_dir=run_dir, run_id="SWEEP_test_0001", slug="drb_72",
            query_index=1, query_total=5, stage=stage,
            started_monotonic=started, running_cost_usd=1.23, budget_cap_usd=25.0,
        )

    async def _drive() -> None:
        ticker = asyncio.ensure_future(
            sweep._periodic_heartbeat_ticker(_hb, "generation_in_progress", 0.02)
        )
        # Simulate the long generation await: let several ticks fire, capturing the
        # heartbeat between them to prove the timestamp advances (not frozen).
        await asyncio.sleep(0.05)
        first = json.loads((run_dir / hb.RUN_STATUS_FILENAME).read_text(encoding="utf-8"))
        await asyncio.sleep(0.07)
        second = json.loads((run_dir / hb.RUN_STATUS_FILENAME).read_text(encoding="utf-8"))
        ticker.cancel()
        try:
            await ticker
        except asyncio.CancelledError:
            pass
        return first, second

    first, second = asyncio.run(_drive())

    # The ticker actually fired (multiple ticks) — NOT frozen at a single stamp.
    assert stages_seen.count("generation_in_progress") >= 2
    # The stage reflects the live sub-phase, not the frozen "generation_started".
    assert first["stage"] == "generation_in_progress"
    # last_update_utc / elapsed_s ADVANCE between reads (proves liveness, not a frozen file).
    assert second["last_update_utc"] >= first["last_update_utc"]
    assert second["elapsed_s"] >= first["elapsed_s"]


def test_ticker_disabled_when_interval_non_positive(tmp_path):
    """interval<=0 (env disabled) returns immediately and writes NO ticks — the existing
    stage transitions still work; only the intra-phase refresh is off."""
    calls: list[str] = []

    async def _drive() -> None:
        await sweep._periodic_heartbeat_ticker(lambda s, **k: calls.append(s), "x", 0.0)

    asyncio.run(_drive())
    assert calls == []  # disabled ticker is a clean no-op, not a crash


def test_verification_loop_counters_populate_not_null(tmp_path, monkeypatch):
    """BUG-3 (verification half): the four_role progress callback shape populates
    ``claims_verified`` / ``claims_total`` in run_status.json — they are NOT left null while
    per-claim verification runs (the frozen-counters symptom). Exercises the REAL writer with
    the SAME kwargs the in-run ``_hb_claims`` callback passes."""
    run_dir = tmp_path / "run"
    mirror = tmp_path / "state" / "run_status.json"
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(mirror))
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)

    # Simulate the per-claim verification loop ticking progress (done of n).
    for done in (1, 4, 9):
        hb.write_heartbeat(
            run_dir=run_dir, run_id="SWEEP_test_0001", slug="drb_72",
            query_index=1, query_total=5, stage="four_role_progress",
            started_monotonic=time.monotonic() - 30.0,
            running_cost_usd=4.21, budget_cap_usd=25.0,
            claims_verified=done, claims_total=12,
        )
    payload = json.loads((run_dir / hb.RUN_STATUS_FILENAME).read_text(encoding="utf-8"))
    assert payload["stage"] == "four_role_progress"
    assert payload["claims_verified"] == 9  # last tick — NOT null/frozen
    assert payload["claims_total"] == 12


# ─────────────────────────────────────────────────────────────────────────────
# BUG-21 — an entry-setup crash ALWAYS produces a terminal error_* manifest
# ─────────────────────────────────────────────────────────────────────────────
def test_write_terminal_error_manifest_helper(tmp_path):
    """The terminal-manifest helper writes status=error_<phase> + exception type/phase, and
    NEVER raises (returns None when no run_dir)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    q = {"slug": "drb_76", "domain": "clinical", "question": "Q?"}
    exc = ValueError("corpus snapshot is corrupt")

    out = sweep.write_terminal_error_manifest(run_dir, q, "RUN_X", exc, "retrieval_done")
    assert out is not None
    written = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert written["status"] == "error_retrieval_done"
    assert written["status"].startswith("error_")
    assert written["error_type"] == "ValueError"
    assert "corrupt" in written["error"]
    assert written["phase"] == "retrieval_done"
    # never raises when there is no run_dir to write to:
    assert sweep.write_terminal_error_manifest(None, q, "RUN_X", exc, "started") is None


def test_terminal_status_value_is_error_family():
    """The terminal status uses the ``error_`` prefix family (consistent with the unified
    taxonomy's ``error_unexpected``), so a downstream status reader classifies it as an error,
    never silently as a success/abort."""
    # error_unexpected is the canonical error family the manifest taxonomy already ships.
    assert "error_unexpected" in sweep.UNIFIED_STATUS_VALUES
    assert "error_unexpected".startswith("error_")


def test_entry_setup_crash_writes_terminal_manifest_and_reraises(tmp_path, monkeypatch):
    """MANDATORY regression (BUG-21): a failure in run_one_query's ENTRY SETUP (before the big
    outer try) — here a reasoning-collector init raise — must STILL write a terminal
    ``manifest.json`` with ``status=error_*`` AND re-raise, so no catchable failure leaves
    run_status.json frozen forever with no terminal artifact (the drb_76 silent-death class).

    Drives the REAL ``run_one_query`` with the reasoning-trace collector monkeypatched to raise
    at construction (a deterministic offline entry-setup failure)."""
    monkeypatch.delenv(hb.HEARTBEAT_ENABLED_ENV, raising=False)
    monkeypatch.setenv(hb.RUN_STATUS_PATH_ENV, str(tmp_path / "state" / "run_status.json"))

    # Make the entry-setup ReasoningTraceCollector construction raise — patched at its SOURCE
    # module (run_one_query imports it locally), a real offline failure inside the guarded region.
    import src.polaris_graph.generator.reasoning_trace as _rt_mod

    class _BoomCollector:
        def __init__(self, *a, **k):
            raise RuntimeError("entry-setup boom (simulated reasoning-collector init failure)")

    monkeypatch.setattr(_rt_mod, "ReasoningTraceCollector", _BoomCollector)

    out_root = tmp_path / "out"
    q = {"slug": "drb_76", "domain": "clinical", "question": "Does X cause Y?"}

    with pytest.raises(RuntimeError, match="entry-setup boom"):
        asyncio.run(sweep.run_one_query(q, out_root))

    # The terminal manifest MUST exist for the run_dir (out_root/domain/slug).
    run_dir = out_root / "clinical" / "drb_76"
    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists(), "entry-setup crash left NO terminal manifest (silent death)"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written["status"].startswith("error_"), written["status"]
    assert written["error_type"] == "RuntimeError"
    assert "boom" in written["error"]

    # And run_status.json is NOT frozen at a non-terminal stage — it carries a terminal error_*.
    status_path = run_dir / hb.RUN_STATUS_FILENAME
    assert status_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["stage"].startswith("error_"), status["stage"]


# ─────────────────────────────────────────────────────────────────────────────
# BUG-4 — the retrieval_caps disclosure block is present + populated
# ─────────────────────────────────────────────────────────────────────────────
def test_retrieval_caps_block_present_and_populated(monkeypatch):
    """The manifest's retrieval section carries a populated ``retrieval_caps`` disclosure block
    so a CAPPED breadth (pre_filter >> fetched) is visible + auditable. DISCLOSURE only — the
    caps themselves are unchanged."""
    monkeypatch.setenv("PG_LIVE_FETCH_CAP", "100")

    from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult

    # The reported drb-style funnel: 1299 discovered, only 623 fetched (a capped run).
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[],
        total_candidates_pre_filter=1299, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=700, candidates_fetched=623,
        candidates_failed_fetch=5,
        corpus_truncated=False,
        drop_reasons={"offtopic": 600, "rerank_not_selected": 71},
    )
    sec = sweep._retrieval_manifest_section(r)
    assert "retrieval_caps" in sec
    caps = sec["retrieval_caps"]
    assert caps["candidates_discovered"] == 1299
    assert caps["fetched"] == 623
    # dropped_pre_fetch = discovered - fetched - failed = 1299 - 623 - 5 = 671 (the throttle magnitude).
    assert caps["dropped_pre_fetch"] == 671
    assert isinstance(caps["search_truncations"], list) and caps["search_truncations"]
    # The fetch cap BIT (1299 discovered > 100 cap) — the silent-throttle signal made explicit.
    fetch_entry = next(
        e for e in caps["search_truncations"] if e["cap"] == "PG_LIVE_FETCH_CAP"
    )
    assert fetch_entry["value"] == 100
    assert fetch_entry["bit"] is True


def test_retrieval_caps_bit_false_when_cap_not_exceeded(monkeypatch):
    """When the discovered pool fits under the fetch cap, the cap did NOT bite — disclosed
    honestly as bit=False (no fabricated throttle)."""
    monkeypatch.setenv("PG_LIVE_FETCH_CAP", "1000")
    from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult

    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[],
        total_candidates_pre_filter=40, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=40, candidates_fetched=40,
        candidates_failed_fetch=0,
    )
    caps = sweep._retrieval_manifest_section(r)["retrieval_caps"]
    fetch_entry = next(
        e for e in caps["search_truncations"] if e["cap"] == "PG_LIVE_FETCH_CAP"
    )
    assert fetch_entry["bit"] is False
    assert caps["dropped_pre_fetch"] == 0  # nothing lost pre-fetch


def test_retrieval_caps_backward_compatible_with_stub():
    """A pre-existing retrieval-like object without the new attrs still yields a valid
    retrieval_caps block via getattr defaults — never a KeyError/AttributeError."""

    class _OldRetr:
        total_candidates_pre_filter = 0
        candidates_total = 0
        candidates_fetched = 0
        candidates_failed_fetch = 0

    caps = sweep._retrieval_manifest_section(_OldRetr())["retrieval_caps"]
    assert caps["candidates_discovered"] == 0
    assert caps["dropped_pre_fetch"] == 0
    assert caps["corpus_truncated"] is False
    assert isinstance(caps["search_truncations"], list)
