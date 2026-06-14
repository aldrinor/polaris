"""I-arch-004 A1 (#1248): section-generation crash isolation.

Regression for the drb_72 death: a single V30 section hit the smoke-inherited 600s wall-clock
twice, the bare ``asyncio.gather`` re-raised the TimeoutError, sibling sections were cancelled,
and a 3h20m / $6.74 run was discarded as ``error_unexpected``.

The fix isolates ONLY transient failures (timeout / socket stall) into VISIBLE gap-stubs, while
letting the hard gates (CredibilityPassError / BudgetExceededError) and programming/config defects
propagate fail-fast (cancelling siblings). Codex diff-gate iter-1 P1-1/P1-2/P1-3.
"""

import asyncio

import httpx
import pytest

from src.polaris_graph.generator.multi_section_generator import (
    SectionResult,
    _gather_sections_isolated,
    _section_failure_to_gap_stub,
)
from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
from src.polaris_graph.llm.openrouter_client import BudgetExceededError


class _Plan:
    def __init__(self, title):
        self.title = title
        self.focus = "focus"
        self.ev_ids = ["e1", "e2"]
        self.archetype = "evidence_synthesis"


def _real_section(plan):
    return SectionResult(
        title=plan.title,
        focus=plan.focus,
        ev_ids_assigned=plan.ev_ids,
        raw_draft="draft",
        rewritten_draft="draft",
        verified_text="A real verified sentence [#ev:e1:0-10].",
        biblio_slice=[],
        sentences_verified=2,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )


# ---- mapper: a transient failure becomes a VISIBLE gap-stub (P1-1) ----

def test_gap_stub_is_visible_and_zero_verified():
    stub = _section_failure_to_gap_stub(
        _Plan("Efficacy"),
        TimeoutError("section generation exceeded 600s wall-clock x2"),
    )
    assert stub.is_gap_stub is True
    # P1-1: dropped_due_to_failure MUST be False so assembly's `if not sr.dropped_due_to_failure`
    # filter RENDERS the gap (True would silently omit the planned section).
    assert stub.dropped_due_to_failure is False
    assert stub.sentences_verified == 0
    assert stub.title == "Efficacy"
    assert "section_generation_failed" in stub.error
    assert "TimeoutError" in stub.error


# ---- gather: transient isolation keeps siblings alive ----

def test_one_transient_failure_does_not_cancel_siblings():
    plans = [_Plan("A"), _Plan("B_times_out"), _Plan("C")]

    async def runner_for(plan):
        if plan.title == "B_times_out":
            raise TimeoutError("section generation exceeded 600s wall-clock x2")
        await asyncio.sleep(0)
        return _real_section(plan)

    results = asyncio.run(_gather_sections_isolated(plans, runner_for))

    assert len(results) == 3  # index alignment preserved
    assert results[0].sentences_verified == 2 and results[0].is_gap_stub is False  # A survived
    assert results[1].is_gap_stub is True and results[1].sentences_verified == 0   # B gap-stub
    assert results[2].sentences_verified == 2 and results[2].is_gap_stub is False  # C NOT cancelled


# ---- P1-2: programming defects must NOT be masked as gaps ----

def test_programming_defect_propagates_not_stubbed():
    async def runner_for(plan):
        raise AttributeError("a real programming bug")

    with pytest.raises(AttributeError):
        asyncio.run(_gather_sections_isolated([_Plan("A")], runner_for))


# ---- P1-3: hard-gate exceptions propagate AND cancel siblings (fail-fast) ----

def test_budget_exceeded_propagates_and_cancels_siblings():
    progress = {"sibling_started": False, "sibling_finished": False, "sibling_cancelled": False}

    async def runner_for(plan):
        if plan.title == "budget":
            raise BudgetExceededError("over $25 cap")
        progress["sibling_started"] = True
        try:
            await asyncio.sleep(5)  # long; must be EXPLICITLY cancelled by the failing sibling
        except asyncio.CancelledError:
            progress["sibling_cancelled"] = True
            raise
        progress["sibling_finished"] = True
        return _real_section(plan)

    with pytest.raises(BudgetExceededError):
        asyncio.run(_gather_sections_isolated([_Plan("sibling"), _Plan("budget")], runner_for))

    # fail-fast: the sibling was EXPLICITLY cancelled before completing (no extra spend), not merely
    # torn down by asyncio.run at loop close.
    assert progress["sibling_finished"] is False
    assert progress["sibling_cancelled"] is True


def test_credibility_pass_error_propagates_fail_loud():
    async def runner_for(plan):
        raise CredibilityPassError("coverage gap during section")

    with pytest.raises(CredibilityPassError):
        asyncio.run(_gather_sections_isolated([_Plan("A")], runner_for))


# ---- the REAL httpx transport failures the OpenRouter client re-raises are isolated (Codex iter-3) ----

@pytest.mark.parametrize("exc", [
    httpx.RemoteProtocolError("peer closed connection mid-stream"),  # the exact drb_72-class disconnect
    httpx.ConnectError("connection refused"),
    httpx.ReadError("truncated body read"),
    httpx.ReadTimeout("read timed out"),  # subclass of httpx.TimeoutException
])
def test_httpx_transport_failure_is_isolated_as_gap_stub(exc):
    plans = [_Plan("A"), _Plan("net")]

    async def runner_for(plan):
        if plan.title == "net":
            raise exc
        await asyncio.sleep(0)
        return _real_section(plan)

    results = asyncio.run(_gather_sections_isolated(plans, runner_for))
    assert results[0].is_gap_stub is False  # sibling survives
    assert results[1].is_gap_stub is True   # transport failure -> visible gap


def test_filenotfound_propagates_not_stubbed():
    # Codex iter-3: the broad OSError was removed so a config/filesystem defect (FileNotFoundError is
    # an OSError subclass) is NOT masked as a content gap — it must propagate fail-loud.
    async def runner_for(plan):
        raise FileNotFoundError("missing config file")

    with pytest.raises(FileNotFoundError):
        asyncio.run(_gather_sections_isolated([_Plan("A")], runner_for))


def test_http_status_error_propagates_not_stubbed():
    # A real 4xx/5xx response (httpx.HTTPStatusError) is NOT a transport transient -> propagate.
    async def runner_for(plan):
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_gather_sections_isolated([_Plan("A")], runner_for))
