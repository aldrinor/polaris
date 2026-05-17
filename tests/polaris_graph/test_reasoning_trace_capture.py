"""I-gen-004 (#496): reasoning-trace capture + collector tests.

Pins the operator-directed invariant (transparency directive 2026-05-14):
DeepSeek V4 Pro's raw reasoning channel is captured to a SEPARATE per-run
artifact (``reasoning_trace.jsonl``), never merged into ``report.md`` /
verified prose, and never ``strict_verify``'d.

These exercise the REAL production functions — the ``ReasoningTraceCollector``
and the ``openrouter_client`` capture / finalize helpers
(``_capture_reasoning_trace`` / ``_finalize_reasoning_trace``) that run inside
``_call_impl`` / ``generate()``. No HTTP layer is mocked: the tests drive the
capture machinery directly with a real collector wired as the sink, which is
exactly what the run orchestrator does at run start.
"""
from __future__ import annotations

import json
from dataclasses import asdict, fields

import pytest

from src.polaris_graph.generator.reasoning_trace import (
    REASONING_TRACE_FILENAME,
    ReasoningTraceCollector,
    ReasoningTraceRecord,
)
from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    _capture_reasoning_trace,
    _finalize_reasoning_trace,
    set_reasoning_call_context,
    set_reasoning_sink,
)


def _make_response(*, content: str = "", reasoning: str = "") -> LLMResponse:
    """A raw provider response shaped like one the client builds in
    ``_call_impl`` right before ``_capture_reasoning_trace`` fires."""
    return LLMResponse(
        content=content,
        reasoning=reasoning,
        input_tokens=10,
        output_tokens=20,
        reasoning_tokens=30,
        model="deepseek/deepseek-v4-pro",
        duration_ms=100.0,
    )


@pytest.fixture(autouse=True)
def _reset_reasoning_context():
    """The sink + call-context are ContextVars — reset them around every
    test so nothing leaks across cases."""
    set_reasoning_sink(None)
    set_reasoning_call_context()
    yield
    set_reasoning_sink(None)
    set_reasoning_call_context()


# --- Test 1: separation invariant -------------------------------------------

def test_reasoning_trace_is_a_separate_artifact(tmp_path):
    """flush() writes the reasoning trace as its OWN file and nothing else.

    The reasoning channel is physically a distinct artifact — it cannot
    leak into report.md / verified_report.json because the collector's
    only writer is flush(), and flush() writes exactly one file.
    """
    collector = ReasoningTraceCollector()
    collector.record(
        section="Mechanism",
        call_type="section",
        model="deepseek/deepseek-v4-pro",
        reasoning_text="DISTINCTIVE_COT_MARKER — the model's scratch thinking",
        content_text="The verified prose that ships in report.md.",
    )
    out_path = collector.flush(tmp_path)

    written = sorted(p.name for p in tmp_path.iterdir())
    assert written == [REASONING_TRACE_FILENAME], (
        f"flush must write exactly {REASONING_TRACE_FILENAME!r}; got {written}"
    )

    rows = [
        json.loads(ln)
        for ln in out_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["reasoning_text"].startswith("DISTINCTIVE_COT_MARKER")
    assert rows[0]["content_text"] == "The verified prose that ships in report.md."


# --- Test 2: V4-Pro content='' + reasoning promoted -------------------------

def test_v4_pro_content_empty_reasoning_promoted_is_recorded():
    """V4-Pro shape (content empty, reasoning carries the answer): the raw
    response is captured, and once generate() promotes reasoning->content
    the record is finalized content_source=promoted_from_reasoning."""
    collector = ReasoningTraceCollector()
    set_reasoning_sink(collector)
    set_reasoning_call_context(
        section="Mechanism", call_type="section", attempt_n=1,
    )

    reasoning = "SENTINEL_REASONING describing tirzepatide mechanism. " * 20
    resp = _make_response(content="", reasoning=reasoning)
    _capture_reasoning_trace(resp, "", resp.reasoning)

    assert resp.trace_call_id is not None, "capture must tag the response"
    # generate() I-bug-088 recovery promotes reasoning -> content, then:
    _finalize_reasoning_trace(
        resp.trace_call_id,
        content_source="promoted_from_reasoning",
        content_text=reasoning,
    )

    recs = collector.records()
    assert len(recs) == 1
    assert recs[0].content_source == "promoted_from_reasoning"
    assert recs[0].content_text == reasoning
    assert recs[0].reasoning_text == reasoning


# --- Test 3: internal generate_retry — every attempt recorded ---------------

def test_generate_retry_records_every_attempt():
    """The internal retry path captures one record per attempt; the
    superseded attempt is finalized status=retry, the retry links to it
    via parent_call_id."""
    collector = ReasoningTraceCollector()
    set_reasoning_sink(collector)

    set_reasoning_call_context(
        section="Outline", call_type="outline", attempt_n=1,
    )
    r1 = _make_response(content="", reasoning="sparse first-attempt reasoning")
    _capture_reasoning_trace(r1, "", r1.reasoning)
    # generate() decides to retry — the superseded attempt is finalized:
    _finalize_reasoning_trace(r1.trace_call_id, status="retry")

    set_reasoning_call_context(
        section="Outline", call_type="outline", attempt_n=2,
        parent_call_id=r1.trace_call_id,
    )
    r2 = _make_response(content="recovered outline", reasoning="")
    _capture_reasoning_trace(r2, "recovered outline", "")

    recs = collector.records()
    assert len(recs) == 2, "both the superseded attempt and the retry recorded"
    assert [r.status for r in recs] == ["retry", "ok"]
    assert [r.attempt_n for r in recs] == [1, 2]
    assert recs[1].parent_call_id == r1.trace_call_id


# --- Test 4: ReasoningFirstTruncationError path -----------------------------

def test_reasoning_first_truncation_is_recorded_before_raise():
    """A reasoning-first response that ran out of budget is captured and
    finalized status=truncated BEFORE generate() raises
    ReasoningFirstTruncationError — the reasoning is preserved even though
    the call 'fails'."""
    collector = ReasoningTraceCollector()
    set_reasoning_sink(collector)
    set_reasoning_call_context(section="Efficacy", call_type="section")

    truncated_reasoning = "The model planned the section but ran out of budget"
    resp = _make_response(content="", reasoning=truncated_reasoning)
    _capture_reasoning_trace(resp, "", truncated_reasoning)
    # generate() detects the truncation shape and finalizes before raising:
    _finalize_reasoning_trace(resp.trace_call_id, status="truncated")

    recs = collector.records()
    assert len(recs) == 1
    assert recs[0].status == "truncated"
    assert recs[0].reasoning_text == truncated_reasoning, (
        "the truncated reasoning is preserved despite the call failing"
    )


# --- Test 5: non-reasoning model + capture gating ---------------------------

def test_non_reasoning_model_uniform_schema_and_capture_gating():
    """A non-reasoning model still gets a record (empty reasoning_text,
    uniform 15-field schema). And a call with NO generator context
    (evaluator / retrieval calls) is NOT captured."""
    collector = ReasoningTraceCollector()
    set_reasoning_sink(collector)
    set_reasoning_call_context(section="Summary", call_type="section")

    resp = _make_response(content="A plain answer, no chain-of-thought.", reasoning="")
    _capture_reasoning_trace(resp, resp.content, "")

    recs = collector.records()
    assert len(recs) == 1
    assert recs[0].reasoning_text == ""
    assert recs[0].content_text == "A plain answer, no chain-of-thought."

    record_dict = asdict(recs[0])
    schema = {f.name for f in fields(ReasoningTraceRecord)}
    assert set(record_dict) == schema, "record must carry the full uniform schema"
    assert len(schema) == 15, "I-gen-004 record schema is 15 fields"
    json.dumps(record_dict)  # must be JSON-serializable for the jsonl

    # Gating: clear the call-context (an evaluator / retrieval call) — capture
    # must no-op even though the sink is still registered.
    set_reasoning_call_context()
    resp2 = _make_response(content="evaluator output", reasoning="evaluator cot")
    _capture_reasoning_trace(resp2, "evaluator output", "evaluator cot")
    assert resp2.trace_call_id is None, "no call-context => no capture"
    assert len(collector.records()) == 1, "evaluator call left the trace untouched"


# --- Test 6: long reasoning_text is NOT truncated ---------------------------

def test_long_reasoning_text_is_not_truncated(tmp_path):
    """reasoning_trace.jsonl stores the WHOLE reasoning log — flush()
    performs no truncation, regardless of length (Codex iter-3 P2 #5:
    must not reuse the existing 50k-capped reasoning_capture path)."""
    collector = ReasoningTraceCollector()
    huge_reasoning = "x" * 200_000
    collector.record(
        section="Mechanism",
        call_type="section",
        model="deepseek/deepseek-v4-pro",
        reasoning_text=huge_reasoning,
        content_text="a short verified answer",
    )
    out_path = collector.flush(tmp_path)

    rows = [
        json.loads(ln)
        for ln in out_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert len(rows[0]["reasoning_text"]) == 200_000, (
        "the full reasoning log must round-trip with no truncation"
    )
