"""
Pass 2 remediation tests:

  B-201 (blocker): ambient run_id + run_cost were module globals,
                   stomped under asyncio.gather. Fix: ContextVar.
  M-209 (medium):  limitations verifier matched numbers anywhere in
                   telemetry, not bound to metric key. Fix: require
                   number to appear on a line mentioning a metric key.
  N-302 (minor):   selector over-filled past max_rows when floors
                   applied. Fix: max_rows is now a hard cap.
"""
from __future__ import annotations

import asyncio

import pytest


# ─────────────────────────────────────────────────────────────────
# B-201: concurrent asyncio.gather isolation via ContextVar
# ─────────────────────────────────────────────────────────────────

def test_b201_current_run_id_isolated_per_async_task() -> None:
    """Codex pass-2 reproducer: two async tasks setting different
    run_ids should NOT stomp each other. With ContextVar, each task
    has its own context."""
    from src.polaris_graph.llm.openrouter_client import (
        set_current_run_id,
        current_run_id,
    )

    async def task_a() -> tuple[str, str | None]:
        set_current_run_id("run_A")
        await asyncio.sleep(0.05)
        # After task B has had time to set its own run_id, A's should
        # still be run_A.
        return ("A", current_run_id())

    async def task_b() -> tuple[str, str | None]:
        await asyncio.sleep(0.01)
        set_current_run_id("run_B")
        await asyncio.sleep(0.08)
        return ("B", current_run_id())

    async def main() -> list:
        return await asyncio.gather(task_a(), task_b())

    results = asyncio.run(main())
    # Convert to dict for readability
    rids = {label: rid for label, rid in results}
    assert rids["A"] == "run_A", (
        f"Task A's run_id was stomped: got {rids['A']}, expected run_A"
    )
    assert rids["B"] == "run_B"


def test_b201_run_cost_isolated_per_async_task() -> None:
    """Two concurrent tasks each tracking cost don't cross-contaminate."""
    from src.polaris_graph.llm.openrouter_client import (
        _add_run_cost,
        current_run_cost,
        reset_run_cost,
    )

    async def task_a() -> float:
        reset_run_cost()
        _add_run_cost(1.0)
        await asyncio.sleep(0.05)
        _add_run_cost(0.5)
        return current_run_cost()

    async def task_b() -> float:
        await asyncio.sleep(0.01)
        reset_run_cost()
        _add_run_cost(10.0)
        await asyncio.sleep(0.08)
        _add_run_cost(5.0)
        return current_run_cost()

    async def main() -> list:
        return await asyncio.gather(task_a(), task_b())

    a_cost, b_cost = asyncio.run(main())
    assert abs(a_cost - 1.5) < 0.001, f"Task A cost polluted: got {a_cost}"
    assert abs(b_cost - 15.0) < 0.001, f"Task B cost polluted: got {b_cost}"


def test_b201_openrouter_client_session_id_reflects_task_ambient(
    monkeypatch,
) -> None:
    """OpenRouterClient created inside a task picks up that task's
    ambient run_id, not a sibling task's."""
    from src.polaris_graph.llm import openrouter_client as mod
    monkeypatch.setattr(mod, "OPENROUTER_API_KEY", "sk-test")

    results: dict[str, str] = {}

    async def task_a():
        mod.set_current_run_id("A_run")
        await asyncio.sleep(0.02)
        client = mod.OpenRouterClient(model="m")
        results["A"] = client.usage.session_id

    async def task_b():
        await asyncio.sleep(0.01)
        mod.set_current_run_id("B_run")
        await asyncio.sleep(0.02)
        client = mod.OpenRouterClient(model="m")
        results["B"] = client.usage.session_id

    async def _runner():
        await asyncio.gather(task_a(), task_b())
    asyncio.run(_runner())
    assert results["A"] == "A_run"
    assert results["B"] == "B_run"


# ─────────────────────────────────────────────────────────────────
# M-209: limitations verifier metric-key binding
# ─────────────────────────────────────────────────────────────────

def test_m209_t_cell_count_not_spuriously_matched_by_http_status() -> None:
    """Codex pass-2 reproducer: 'T-cell count of 500' must NOT pass when
    telemetry says 'http_status: 500' but no 'T-cell' metric is in the
    telemetry block."""
    from src.polaris_graph.generator.provenance_generator import (
        verify_limitations_sentence_against_telemetry,
    )
    v = verify_limitations_sentence_against_telemetry(
        "Limitations: T-cell count of 500 was underrepresented.",
        "http_status: 500\ntier_distribution:\n  T1: 9%\n",
    )
    assert v.is_verified is False, (
        "T-cell 500 must not match http_status 500 — metric key binding failed"
    )


def test_m209_number_on_metric_line_still_verifies() -> None:
    """A number that actually appears on a metric-annotated line still
    verifies correctly (backward compat)."""
    from src.polaris_graph.generator.provenance_generator import (
        verify_limitations_sentence_against_telemetry,
    )
    v = verify_limitations_sentence_against_telemetry(
        "Limitations: only 9% of sources are T1 primary studies.",
        "tier_distribution:\n  T1: 9%\n  T5: 50%\n",
    )
    assert v.is_verified is True


def test_m209_rel_diff_line_matches() -> None:
    """rel_diff lines are tagged as metric-bearing."""
    from src.polaris_graph.generator.provenance_generator import (
        verify_limitations_sentence_against_telemetry,
    )
    v = verify_limitations_sentence_against_telemetry(
        "Sources disagree with rel_diff 16.8% on weight loss.",
        "contradictions_detected: 1\n"
        "  - semaglutide / weight_loss: rel_diff 16.8%, severity=medium\n",
    )
    assert v.is_verified is True


# ─────────────────────────────────────────────────────────────────
# N-302: evidence selector honors max_rows as hard cap
# ─────────────────────────────────────────────────────────────────

def test_n302_selector_respects_max_rows_even_with_floors() -> None:
    """Codex pass-2 reproducer: max_rows=2 with T1/T2/T3/T7 pool should
    return exactly 2 rows, not 3 (floor preservation shouldn't exceed cap)."""
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )
    rows = [
        {"evidence_id": t, "source_url": t, "statement": "x y z", "tier": t}
        for t in ["T1", "T2", "T3", "T7"]
    ]
    result = select_evidence_for_generation(
        research_question="x y z",
        protocol=None,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=2,
    )
    assert len(result.selected_rows) <= 2, (
        f"Selector must not exceed max_rows. Got {len(result.selected_rows)}"
    )


def test_n302_selector_respects_max_rows_1() -> None:
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )
    rows = [
        {"evidence_id": t, "source_url": t, "statement": "x y z", "tier": t}
        for t in ["T1", "T2", "T3"]
    ]
    result = select_evidence_for_generation(
        research_question="x y z",
        protocol=None,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=1,
    )
    assert len(result.selected_rows) <= 1
    # Highest priority (T1) should win the single slot
    assert result.selected_rows[0]["tier"] == "T1"


def test_n302_selector_with_generous_max_rows_preserves_floors() -> None:
    """When max_rows is LARGER than the pool's present-HV tier count,
    floors ARE preserved (original behavior)."""
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )
    rows = [
        {"evidence_id": f"ev_{i}", "source_url": f"u_{i}",
         "statement": "x y z", "tier": tier}
        for i, tier in enumerate(["T1", "T2", "T3"] + ["T7"] * 20)
    ]
    result = select_evidence_for_generation(
        research_question="x y z",
        protocol=None,
        classified_sources=[],
        evidence_rows=rows,
        max_rows=10,
    )
    assert len(result.selected_rows) == 10
    # T1/T2/T3 floors preserved (each >=1)
    tiers = [r["tier"] for r in result.selected_rows]
    assert "T1" in tiers
    assert "T2" in tiers
    assert "T3" in tiers
