"""I-arch-004 A3 — F18 / F18b / F21 / F28 / F29 unit tests.  NO network / NO spend.

Covers (offline, deterministic):

  F28  evidence_distiller micro-batching (PG_DISTILL_MICROBATCH_SIZE > 1):
       - size>1 sends ONE MAP call for N>1 cache-miss sources;
       - each finding is validated against ITS OWN source's direct_quote (a
         support_quote present only in source B but CLAIMED under source A is
         REJECTED — cross-source provenance contamination guard);
       - a batch-level MAP failure -> a coverage row for EVERY source in the
         batch (no source disappears);
       - a source whose key is OMITTED from the batch response -> fail-closed;
       - per-source cache granularity is unchanged (a cache HIT bypasses batching).

  F21  research_question threading:
       - the legacy _call_section prompt carries the REAL research_question,
         not the "(see overall corpus)" placeholder; empty -> placeholder;
       - render_reduce_user / _render_map_user carry it as FRAMING-ONLY;
       - distill_section_evidence forwards it into the MAP prompt.

  F18  the distiller's bounded async pool (Semaphore) caps concurrency at
       PG_DISTILL_MAX_PARALLEL even across micro-batches.

  F18b live_retriever PG_CORPUS_TRUNCATION_POLICY (warn / repair / fail_closed).

  F29  the M-44 injection cap honors PG_MAX_EV_PER_SECTION at the CALL site
       (call-time env read, not the bare literal 20).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

import pytest

import src.polaris_graph.clinical_generator.strict_verify as strict_verify_mod
from src.polaris_graph.generator import evidence_distiller as ed
from src.polaris_graph.generator.evidence_distiller import (
    SectionDistillate,
    distill_section_evidence,
    render_reduce_user,
    _render_map_user,
    _render_map_batch_user,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@dataclass
class _Section:
    title: str
    focus: str


_SECTION = _Section(title="Safety", focus="adverse events of the intervention")
_RQ = "What are the cardiovascular safety risks of tirzepatide in T2D adults?"

# Two distinct sources with DISTINCT direct_quotes so cross-source routing is
# observable: a support_quote from B does NOT occur in A and vice versa.
_QUOTE_A = (
    "Serious adverse events occurred in 7.0 percent of tirzepatide patients. "
    "Discontinuation due to adverse events was 5.1 percent."
)
_QUOTE_B = (
    "Pancreatitis was reported in 0.2 percent of participants in the trial. "
    "Gallbladder disease occurred in 1.5 percent of the treated group."
)
_EV_A = {
    "evidence_id": "ev_a", "tier": "T1",
    "statement": "Tirzepatide safety summary",
    "direct_quote": _QUOTE_A, "source_url": "https://example.org/a",
}
_EV_B = {
    "evidence_id": "ev_b", "tier": "T1",
    "statement": "Tirzepatide adverse events",
    "direct_quote": _QUOTE_B, "source_url": "https://example.org/b",
}
_POOL = {"ev_a": _EV_A, "ev_b": _EV_B}


class _FakeJudge:
    def __init__(self, verdict: str = "ENTAILED"):
        self._v = verdict

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        return self._v, "ok"


def _enforce_entailment(monkeypatch, verdict: str = "ENTAILED") -> None:
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setattr(strict_verify_mod, "_get_judge", lambda: _FakeJudge(verdict),
                        raising=True)


def _tmp_cache(monkeypatch) -> None:
    import pathlib
    import tempfile
    d = tempfile.mkdtemp()
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: pathlib.Path(d))


def _install_batch_client(monkeypatch, *, by_source: dict, captured: dict | None = None,
                          calls: list | None = None, raise_exc: Exception | None = None,
                          content_override: str | None = None):
    """Monkeypatch OpenRouterClient so a MAP call returns a by_source-keyed payload.

    Records the rendered user prompt + a call counter so concurrency / batching /
    prompt-content can be asserted. The SAME fake serves the single-source path
    (which sends {"findings":[...]}) by reflecting whichever shape the prompt asks
    for: when the rendered prompt contains the batch envelope marker we return the
    by_source payload, otherwise we return the lone source's findings list.
    """
    import src.polaris_graph.llm.openrouter_client as orc

    captured = captured if captured is not None else {}
    calls = calls if calls is not None else []

    class _Resp:
        def __init__(self, body):
            self.content = body
            self.reasoning = None
            self.input_tokens = 13
            self.output_tokens = 9

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *a, **k):
            if raise_exc is not None:
                raise raise_exc
            msgs = k.get("messages") or (a[0] if a else [])
            user = ""
            for m in msgs:
                if m.get("role") == "user":
                    user = m.get("content", "")
            captured["user"] = user
            calls.append(user)
            if content_override is not None:
                return _Resp(content_override)
            if "by_source" in user:
                return _Resp(json.dumps({"by_source": by_source}))
            # single-source path: find which evidence_id this prompt is for
            for eid, entry in by_source.items():
                if f"EVIDENCE_ID: {eid}" in user:
                    return _Resp(json.dumps(entry))
            return _Resp(json.dumps({"no_relevant_findings": True,
                                     "no_relevant_reason": "x", "findings": []}))

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient, raising=True)
    return captured, calls


# ---------------------------------------------------------------------------
# F28 — micro-batch size>1 issues ONE call for N sources
# ---------------------------------------------------------------------------

def test_f28_microbatch_one_call_for_two_sources(monkeypatch):
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.setenv("PG_DISTILL_MICROBATCH_SIZE", "2")
    by_source = {
        "ev_a": {"no_relevant_findings": False, "findings": [{
            "claim": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "support_quote": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "span_start": 0, "span_end": 0, "numbers": ["7.0"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
        "ev_b": {"no_relevant_findings": False, "findings": [{
            "claim": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "support_quote": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "span_start": 0, "span_end": 0, "numbers": ["0.2"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
    }
    _captured, calls = _install_batch_client(monkeypatch, by_source=by_source)

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_A, _EV_B], _POOL, model="m",
    ))
    # ONE batched MAP call for the two cache-miss sources.
    assert len(calls) == 1
    assert "by_source" in calls[0]
    # Both sources accounted for, each with its own finding.
    eids = {f.evidence_id for f in dist.findings}
    assert eids == {"ev_a", "ev_b"}
    assert {c.evidence_id for c in dist.coverage} == {"ev_a", "ev_b"}


def test_f28_cross_source_support_quote_rejected(monkeypatch):
    """A finding CLAIMED under ev_a whose support_quote belongs ONLY to ev_b's
    direct_quote must be REJECTED — validation routes each finding to its OWN
    source's text. Provenance contamination cannot pass through batching."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.setenv("PG_DISTILL_MICROBATCH_SIZE", "2")
    by_source = {
        # ev_a's finding cites text that exists ONLY in ev_b (_QUOTE_B) -> reject.
        "ev_a": {"no_relevant_findings": False, "findings": [{
            "claim": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "support_quote": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "span_start": 0, "span_end": 0, "numbers": ["0.2"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
        # ev_b's finding is genuinely from ev_b -> kept.
        "ev_b": {"no_relevant_findings": False, "findings": [{
            "claim": "Gallbladder disease occurred in 1.5 percent of the treated group.",
            "support_quote": "Gallbladder disease occurred in 1.5 percent of the treated group.",
            "span_start": 0, "span_end": 0, "numbers": ["1.5"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
    }
    _install_batch_client(monkeypatch, by_source=by_source)

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_A, _EV_B], _POOL, model="m",
    ))
    # ev_a's cross-source claim is rejected -> validation_failed; ev_b kept.
    kept_eids = {f.evidence_id for f in dist.findings}
    assert kept_eids == {"ev_b"}, "cross-source support_quote must not pass"
    cov_a = next(c for c in dist.coverage if c.evidence_id == "ev_a")
    assert cov_a.status == "validation_failed"
    cov_b = next(c for c in dist.coverage if c.evidence_id == "ev_b")
    assert cov_b.status == "mapped"


def test_f28_batch_map_failure_emits_coverage_for_all_sources(monkeypatch):
    """A batch-level live MAP exception -> EVERY source in the batch gets a
    map_failed coverage row (no source silently disappears)."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.setenv("PG_DISTILL_MICROBATCH_SIZE", "3")
    _install_batch_client(monkeypatch, by_source={},
                          raise_exc=RuntimeError("provider 500"))

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_A, _EV_B], _POOL, model="m",
    ))
    assert dist.findings == []
    assert {c.evidence_id for c in dist.coverage} == {"ev_a", "ev_b"}
    assert all(c.status == "map_failed" for c in dist.coverage)


def test_f28_source_omitted_from_batch_response_fail_closed(monkeypatch):
    """If the model returns by_source with ev_a but OMITS ev_b's key entirely,
    ev_b is fail-closed map_failed — never silently dropped."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.setenv("PG_DISTILL_MICROBATCH_SIZE", "2")
    by_source = {
        "ev_a": {"no_relevant_findings": False, "findings": [{
            "claim": "Discontinuation due to adverse events was 5.1 percent.",
            "support_quote": "Discontinuation due to adverse events was 5.1 percent.",
            "span_start": 0, "span_end": 0, "numbers": ["5.1"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
        # ev_b deliberately omitted.
    }
    _install_batch_client(monkeypatch, by_source=by_source)

    dist = asyncio.run(distill_section_evidence(
        _SECTION, [_EV_A, _EV_B], _POOL, model="m",
    ))
    assert {c.evidence_id for c in dist.coverage} == {"ev_a", "ev_b"}
    cov_b = next(c for c in dist.coverage if c.evidence_id == "ev_b")
    assert cov_b.status == "map_failed"
    assert "missing" in cov_b.reason


def test_f28_cache_hit_bypasses_batching(monkeypatch):
    """A pre-populated per-source cache entry is a HIT that bypasses the live
    batch call (cache granularity unchanged by F28)."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.setenv("PG_DISTILL_MICROBATCH_SIZE", "2")
    by_source = {
        "ev_a": {"no_relevant_findings": False, "findings": [{
            "claim": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "support_quote": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "span_start": 0, "span_end": 0, "numbers": ["7.0"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
        "ev_b": {"no_relevant_findings": False, "findings": [{
            "claim": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "support_quote": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "span_start": 0, "span_end": 0, "numbers": ["0.2"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
    }
    _, calls = _install_batch_client(monkeypatch, by_source=by_source)

    # Run 1 populates the per-source cache.
    asyncio.run(distill_section_evidence(_SECTION, [_EV_A, _EV_B], _POOL, model="m"))
    n_calls_run1 = len(calls)
    assert n_calls_run1 == 1  # one batch call

    # Run 2 with the SAME cache dir: both sources hit -> NO live call.
    dist2 = asyncio.run(distill_section_evidence(_SECTION, [_EV_A, _EV_B], _POOL, model="m"))
    assert len(calls) == n_calls_run1, "cache hits must not issue another MAP call"
    assert dist2.cache_hits == 2
    assert {f.evidence_id for f in dist2.findings} == {"ev_a", "ev_b"}


def test_f28_size_one_is_single_source_path(monkeypatch):
    """size==1 (default) issues one MAP call PER source (byte-identical path)."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.delenv("PG_DISTILL_MICROBATCH_SIZE", raising=False)
    by_source = {
        "ev_a": {"no_relevant_findings": False, "findings": [{
            "claim": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "support_quote": "Serious adverse events occurred in 7.0 percent of tirzepatide patients.",
            "span_start": 0, "span_end": 0, "numbers": ["7.0"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
        "ev_b": {"no_relevant_findings": False, "findings": [{
            "claim": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "support_quote": "Pancreatitis was reported in 0.2 percent of participants in the trial.",
            "span_start": 0, "span_end": 0, "numbers": ["0.2"],
            "entities": [], "caveat": "", "contradiction_key": "", "source_tier": "T1",
        }]},
    }
    _, calls = _install_batch_client(monkeypatch, by_source=by_source)
    dist = asyncio.run(distill_section_evidence(_SECTION, [_EV_A, _EV_B], _POOL, model="m"))
    # size 1 -> two single-source calls, NOT a batch envelope.
    assert len(calls) == 2
    assert all("by_source" not in c for c in calls)
    assert {f.evidence_id for f in dist.findings} == {"ev_a", "ev_b"}


# ---------------------------------------------------------------------------
# F18 — bounded async pool caps concurrency
# ---------------------------------------------------------------------------

def test_f18_bounded_pool_caps_concurrency(monkeypatch):
    """With PG_DISTILL_MAX_PARALLEL=1 and 4 single-source sources, never more than
    one MAP call is in flight at a time."""
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.delenv("PG_DISTILL_MICROBATCH_SIZE", raising=False)
    monkeypatch.setenv("PG_DISTILL_MAX_PARALLEL", "1")

    import src.polaris_graph.llm.openrouter_client as orc

    state = {"inflight": 0, "max_inflight": 0}

    evs = [
        {"evidence_id": f"ev_{i}", "tier": "T1", "statement": "s",
         "direct_quote": f"Adverse events occurred in {i}.0 percent of patients.",
         "source_url": "u"}
        for i in range(4)
    ]
    pool = {e["evidence_id"]: e for e in evs}

    class _Resp:
        content = json.dumps({"no_relevant_findings": True,
                              "no_relevant_reason": "x", "findings": []})
        reasoning = None
        input_tokens = 1
        output_tokens = 1

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *a, **k):
            state["inflight"] += 1
            state["max_inflight"] = max(state["max_inflight"], state["inflight"])
            await asyncio.sleep(0.01)
            state["inflight"] -= 1
            return _Resp()

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient, raising=True)
    asyncio.run(distill_section_evidence(_Section("Safety", "f"), evs, pool, model="m"))
    assert state["max_inflight"] == 1


# ---------------------------------------------------------------------------
# F21 — research_question threading (framing only)
# ---------------------------------------------------------------------------

def test_f21_map_user_prompt_carries_research_question(monkeypatch):
    out = _render_map_user(
        section_title="Safety", section_focus="f", evidence_id="ev_a",
        tier="T1", statement="s", direct_quote=_QUOTE_A, atom_rows="(none)",
        research_question=_RQ,
    )
    assert "RESEARCH_QUESTION" in out and _RQ in out
    assert "framing only" in out
    # Empty -> byte-identical (no RESEARCH_QUESTION line).
    out0 = _render_map_user(
        section_title="Safety", section_focus="f", evidence_id="ev_a",
        tier="T1", statement="s", direct_quote=_QUOTE_A, atom_rows="(none)",
    )
    assert "RESEARCH_QUESTION" not in out0


def test_f21_reduce_user_prompt_carries_research_question():
    dist = SectionDistillate(
        section_title="Safety", section_focus="f", findings=[], coverage=[],
        contradiction_clusters=[], atom_catalog={},
    )
    out = render_reduce_user(dist, research_question=_RQ)
    assert "RESEARCH_QUESTION" in out and _RQ in out
    assert "NOT a citable source" in out
    out0 = render_reduce_user(dist)
    assert "RESEARCH_QUESTION" not in out0


def test_f21_distill_forwards_research_question_into_map_prompt(monkeypatch):
    _enforce_entailment(monkeypatch)
    _tmp_cache(monkeypatch)
    monkeypatch.delenv("PG_DISTILL_MICROBATCH_SIZE", raising=False)
    captured, _ = _install_batch_client(monkeypatch, by_source={
        "ev_a": {"no_relevant_findings": True, "no_relevant_reason": "x", "findings": []},
    })
    asyncio.run(distill_section_evidence(
        _SECTION, [_EV_A], _POOL, model="m", research_question=_RQ,
    ))
    assert _RQ in captured["user"]


def test_f21_legacy_call_section_uses_real_research_question(monkeypatch):
    """The legacy _call_section prompt threads the real research_question instead of
    the '(see overall corpus)' placeholder; empty falls back to the placeholder."""
    import src.polaris_graph.llm.openrouter_client as orc
    from src.polaris_graph.generator.multi_section_generator import (
        SectionPlan, _call_section,
    )
    monkeypatch.delenv("PG_SECTION_DISTILL", raising=False)
    captured = {}

    class _Resp:
        content = "Adverse events occurred in 7.0 percent of patients [ev_a]."
        input_tokens = 1
        output_tokens = 1
        reasoning = None

    class _C:
        def __init__(self, *a, **k):
            pass

        async def generate(self, prompt, system, max_tokens, temperature, **k):
            captured["prompt"] = prompt
            return _Resp()

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _C, raising=True)
    sec = SectionPlan(title="Safety", focus="f", ev_ids=["ev_a"])
    asyncio.run(_call_section(
        sec, [_EV_A], "deepseek/deepseek-v4-pro", 0.3, 4096,
        research_question=_RQ,
    ))
    assert _RQ in captured["prompt"]
    assert "(see overall corpus)" not in captured["prompt"]

    # Empty -> byte-identical placeholder.
    captured.clear()
    asyncio.run(_call_section(
        sec, [_EV_A], "deepseek/deepseek-v4-pro", 0.3, 4096,
    ))
    assert "(see overall corpus)" in captured["prompt"]


# ---------------------------------------------------------------------------
# F18b — corpus truncation policy
# ---------------------------------------------------------------------------

def test_f18b_policy_helper_values(monkeypatch):
    from src.polaris_graph.retrieval.live_retriever import _corpus_truncation_policy
    monkeypatch.delenv("PG_CORPUS_TRUNCATION_POLICY", raising=False)
    assert _corpus_truncation_policy() == "warn"  # default
    for v in ("warn", "repair", "fail_closed"):
        monkeypatch.setenv("PG_CORPUS_TRUNCATION_POLICY", v)
        assert _corpus_truncation_policy() == v
    monkeypatch.setenv("PG_CORPUS_TRUNCATION_POLICY", "garbage")
    assert _corpus_truncation_policy() == "warn"  # unknown -> default
    monkeypatch.setenv("PG_CORPUS_TRUNCATION_POLICY", "FAIL_CLOSED")
    assert _corpus_truncation_policy() == "fail_closed"  # case-insensitive


def test_f18b_error_type_exists():
    from src.polaris_graph.retrieval.live_retriever import CorpusTruncationError
    assert issubclass(CorpusTruncationError, RuntimeError)


def test_f18b_loop_wires_all_three_branches():
    """Regression guard: the post-fetch loop must branch on the policy at the
    deadline check — repair continues, fail_closed raises, warn breaks. Pins the
    in-run gate so a future edit cannot silently revert to flag+break only.

    Reads the SOURCE FILE directly (inspect.getsource collapses on large modules
    in some environments)."""
    import pathlib
    import src.polaris_graph.retrieval.live_retriever as lr
    text = pathlib.Path(lr.__file__).read_text(encoding="utf-8")
    assert "_corpus_truncation_policy()" in text
    assert '_trunc_policy == "repair"' in text
    assert '_trunc_policy == "fail_closed"' in text
    assert "raise CorpusTruncationError(" in text


# ---------------------------------------------------------------------------
# F29 — M-44 injection cap honors PG_MAX_EV_PER_SECTION at the CALL site
# ---------------------------------------------------------------------------

def test_f29_m44_call_site_reads_env_call_time(monkeypatch):
    """The M-44 injection cap must be read from PG_MAX_EV_PER_SECTION at CALL time.
    Drive the helper with the EXACT call-site expression and prove env wins per
    call (not a frozen import-time literal)."""
    from src.polaris_graph.generator.multi_section_generator import (
        SectionPlan, _m44_inject_primaries_into_outline,
    )

    def _call_site_cap() -> int:
        return int(os.getenv("PG_MAX_EV_PER_SECTION", "30"))

    # Section holding 5 rows; primary should SWAP in only when cap<=5.
    plans = [SectionPlan(title="Efficacy", focus="f",
                         ev_ids=[f"ev_{i}" for i in range(5)])]
    primary = {"SURPASS-2": ["ev_primary"]}

    # env=5 -> cap 5 -> at-cap -> SWAP (drops ev_4).
    monkeypatch.setenv("PG_MAX_EV_PER_SECTION", "5")
    updated, log = _m44_inject_primaries_into_outline(
        plans, primary, max_ev_per_section=_call_site_cap(),
    )
    assert len(updated[0].ev_ids) == 5
    assert updated[0].ev_ids[0] == "ev_primary"
    assert any(e["action"].startswith("swap_in_for_") for e in log)

    # env=30 (or unset) -> cap 30 -> NOT at cap -> INJECT (grows to 6, no drop).
    monkeypatch.setenv("PG_MAX_EV_PER_SECTION", "30")
    updated2, log2 = _m44_inject_primaries_into_outline(
        plans, primary, max_ev_per_section=_call_site_cap(),
    )
    assert len(updated2[0].ev_ids) == 6
    assert "ev_4" in updated2[0].ev_ids  # nothing evicted
    assert any(e["action"] == "injected" for e in log2)


def test_f29_call_site_source_uses_env_not_bare_default():
    """Regression guard: the production M-44 call site must pass
    PG_MAX_EV_PER_SECTION (not rely on the helper's bare default 20). This
    pins the fix so a future edit cannot silently re-introduce the 20 literal.

    Reads the SOURCE FILE directly (not inspect.getsource, which collapses on this
    ~7k-line module in some environments) and asserts the env-read cap appears in
    the same statement as the _m44 call."""
    import pathlib
    import src.polaris_graph.generator.multi_section_generator as msg
    text = pathlib.Path(msg.__file__).read_text(encoding="utf-8")
    assert "_m44_inject_primaries_into_outline(" in text
    # The call site threads the env-read cap, read at CALL time.
    assert 'max_ev_per_section=int(os.getenv("PG_MAX_EV_PER_SECTION", "30"))' in text
