"""W4 regression tests for the REAL ``_wrap_execute_python`` body (tool_registry.py:547-640).

WHY THIS FILE EXISTS (Fable, round-1 gate): every pre-existing execute_python test
(``tests/polaris_graph/outline/test_outline_agent_w3.py``:150,171) registers an inline async
fake UNDER THE REGISTRY NAME ``execute_python``, overwriting the real executor. Those tests
therefore prove only that the OutlineAgent DISPATCH hands a non-None code-model client to
whatever is registered — the executor body itself (the no-client guard at :561, the timeout
path, the success mapping of summary/statistics/insights into ToolResult) was executed by
ZERO tests. ``grep -rn generate_and_execute_analysis tests/`` returned nothing. The tool could
be bricked one layer below the dispatch without a single test going red.

These tests call the REAL ``_wrap_execute_python`` and monkeypatch ONLY its collaborator,
``code_executor.generate_and_execute_analysis`` (the wrapper imports it lazily INSIDE the
function, so patching the attribute on the code_executor module is what the wrapper resolves).
No registry name is overwritten. No network, no sandbox.
"""

from __future__ import annotations

import asyncio

import pytest

import src.polaris_graph.tools.code_executor as code_executor
from src.polaris_graph.tools.tool_registry import ToolResult, _wrap_execute_python


class _Client:
    """Any truthy non-None object — the wrapper only checks ``if not client``."""


EV_STORE = {
    "ev_1": {"statement": "TELUS reported a 6.0% discount rate.", "source_url": "http://a"},
    "ev_2": {"statement": "Capex was $1.548 billion.", "source_url": "http://b"},
}


def _patch_codegen(monkeypatch, fn) -> list[dict]:
    """Patch the REAL collaborator and record the kwargs the real wrapper passes it."""
    calls: list[dict] = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return await fn(**kwargs)

    monkeypatch.setattr(code_executor, "generate_and_execute_analysis", _spy)
    return calls


# --------------------------------------------------------------------------- (a) success


def test_success_maps_summary_statistics_and_insights_into_toolresult(monkeypatch):
    """The success mapping at tool_registry.py:~620-640 is what makes the tool net-POSITIVE.

    If it drops ``statistics``, a computed number is silently lost and the planner sees an
    OK step with no number in it (exactly the W4 bug, one layer up).
    """
    async def _ok(**kwargs):
        return {
            "success": True,
            "result": {
                "summary": "The 30-year NPV is $1234567.89 given the cited discount rate.",
                "statistics": {"npv": 1234567.89, "discount_rate": 0.06},
                "insights": ["NPV is positive under every sourced discount rate."],
            },
            "charts": [{"image_base64": "iVBORw0KGgo="}],
        }

    calls = _patch_codegen(monkeypatch, _ok)

    result = asyncio.run(_wrap_execute_python(
        evidence_store=EV_STORE,
        data_points=[{"evidence_id": "ev_1", "value": 6.0}, {"evidence_id": "ev_2", "value": 1.548}],
        client=_Client(),
        question="compute the 30-year NPV",
        research_context="TELUS 30yr NPV?",
    ))

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.tool_name == "execute_python"
    assert result.error is None

    # THE load-bearing assertion: the computed number survives into ToolResult.statistics
    # VERBATIM (this is the field the notebook digest reads and the planner sees).
    assert result.statistics == {"npv": 1234567.89, "discount_rate": 0.06}
    assert result.insights == ["NPV is positive under every sourced discount rate."]
    assert "1234567.89" in result.markdown  # summary -> markdown, unmangled
    assert result.charts == [{"image_base64": "iVBORw0KGgo="}]

    # _cite_inline stamped the evidence ids onto the number-bearing paragraph, and the ids
    # came from the data_points (which take precedence over the evidence_store branch).
    assert result.source_evidence_ids == ["ev_1", "ev_2"]
    assert "[CITE:ev_1]" in result.markdown

    # the real wrapper actually invoked the real collaborator, with the caller's question
    assert len(calls) == 1
    assert calls[0]["analysis_question"] == "compute the 30-year NPV"
    assert calls[0]["research_context"] == "TELUS 30yr NPV?"


def test_success_falls_back_to_evidence_store_when_there_are_no_data_points(monkeypatch):
    """No data_points -> the wrapper builds input rows from the evidence_store (:573-581)."""
    async def _ok(**kwargs):
        return {"success": True, "result": {"summary": "n=2 rows seen.", "statistics": {"n": 2}}}

    calls = _patch_codegen(monkeypatch, _ok)

    result = asyncio.run(_wrap_execute_python(
        evidence_store=EV_STORE, data_points=[], client=_Client(),
    ))

    assert result.success is True
    assert result.statistics == {"n": 2}
    assert result.source_evidence_ids == ["ev_1", "ev_2"]
    assert [r["evidence_id"] for r in calls[0]["evidence_data"]] == ["ev_1", "ev_2"]


# --------------------------------------------------------------------------- (b) no client


def test_no_client_returns_the_no_llm_client_available_failure(monkeypatch):
    """tool_registry.py:561 — the guard the W3 dispatch fix existed to stop tripping.

    This is the exact ToolResult that made execute_python fail 100% of calls before W3. It
    must stay a clean success=False ToolResult (never a raise), because the OutlineAgent
    routes it to the gap ledger as UNFILLED.
    """
    called: list[int] = []

    async def _never(**kwargs):
        called.append(1)
        return {"success": True, "result": {}}

    monkeypatch.setattr(code_executor, "generate_and_execute_analysis", _never)

    result = asyncio.run(_wrap_execute_python(
        evidence_store=EV_STORE, data_points=[], client=None,
    ))

    assert result.success is False
    assert result.tool_name == "execute_python"
    assert result.error == "No LLM client available"
    assert "LLM client required" in result.markdown
    assert result.statistics == {}
    assert not called, "the codegen collaborator must not be reached without a client"


# --------------------------------------------------------------------------- (c) timeout


def test_timeout_returns_the_timeout_toolresult(monkeypatch):
    """asyncio.TimeoutError path (:600-606): a hung sandbox must degrade, never propagate."""
    async def _hang(**kwargs):
        await asyncio.sleep(30)
        return {"success": True, "result": {}}

    _patch_codegen(monkeypatch, _hang)
    monkeypatch.setenv("PG_REACT_TOOL_TIMEOUT", "1")  # LAW VI: the knob is env-tunable

    result = asyncio.run(_wrap_execute_python(
        evidence_store=EV_STORE, data_points=[], client=_Client(),
    ))

    assert result.success is False
    assert result.tool_name == "execute_python"
    assert result.error == "Timeout after 1s"
    assert "timed out" in result.markdown
    assert result.statistics == {}


def test_codegen_failure_dict_returns_a_failed_toolresult(monkeypatch):
    """result['success'] is False (:608-614) -> failed ToolResult carrying the error."""
    async def _fail(**kwargs):
        return {"success": False, "error": "ZeroDivisionError: division by zero"}

    _patch_codegen(monkeypatch, _fail)

    result = asyncio.run(_wrap_execute_python(
        evidence_store=EV_STORE, data_points=[], client=_Client(),
    ))

    assert result.success is False
    assert result.error == "ZeroDivisionError: division by zero"
    assert "ZeroDivisionError" in result.markdown
