"""I-cap-002 feature 4/4 (#1060): tests for the NLI benchmark annotator.

Offline + torch-free: the NLI scorer + ``load_nli_model`` are MOCKED via monkeypatch, so no
torch/minicheck is imported (CLAUDE.md §8.4 — the live model runs only on the VM).

Covers: (a) pair-building cleans ``[#ev:...]`` tokens and concatenates ALL cited spans (Codex
brief-gate P2.1+P2.2); (b) the ok-path flags a low-prob sentence as disputed; (c) the
model-unavailable path RAISES (no silent clean pass — LAW II); (d) the FaithLens ``.infer`` API split
(P2.3).
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from src.polaris_graph.retrieval import nli_benchmark_annotator as nba
from src.polaris_graph.retrieval.nli_benchmark_annotator import (
    NliUnavailableError,
    annotate_nli_entailment,
    build_nli_pairs,
)


# --------------------------------------------------------------------------- #
# build_nli_pairs — cleaning + multi-span concat
# --------------------------------------------------------------------------- #

def test_pairs_clean_tokens_and_concat_all_spans():
    ev_pool = {
        "ev_000": {"full_text": "Aspirin reduced mortality by 12% in the trial."},
        "ev_001": {"full_text": "No serious adverse events were reported."},
    }
    kept = [{
        "sentence": "Aspirin reduced mortality and was safe [#ev:ev_000:0-46][#ev:ev_001:0-40]",
        "section": "Efficacy",
        "tokens": [
            {"evidence_id": "ev_000", "start": 0, "end": 46},
            {"evidence_id": "ev_001", "start": 0, "end": 40},
        ],
    }]
    pairs = build_nli_pairs(kept, ev_pool)
    assert len(pairs) == 1
    # citation tokens are stripped from the claim (P2.1)
    assert "[#ev:" not in pairs[0]["sentence"]
    assert pairs[0]["sentence"] == "Aspirin reduced mortality and was safe"
    # BOTH cited spans are concatenated into the premise (P2.2)
    assert "Aspirin reduced mortality by 12%" in pairs[0]["span"]
    assert "No serious adverse events" in pairs[0]["span"]
    assert pairs[0]["section"] == "Efficacy"


def test_pairs_strip_calc_and_atom_artifacts():
    # Codex diff-gate iter-1 P2.3: [#calc:...] tokens and (atom_NNN) markers must be stripped from the
    # claim or they create false NLI disputes (the cited span won't entail those artifacts).
    ev_pool = {"ev_000": {"direct_quote": "Total cost fell to 4.2 million dollars."}}
    kept = [{
        "sentence": "Cost fell to $4.2M [#calc:m1:abc123:tco] (atom_007) [#ev:ev_000:0-39]",
        "tokens": [{"evidence_id": "ev_000", "start": 0, "end": 39}],
    }]
    pairs = build_nli_pairs(kept, ev_pool)
    assert len(pairs) == 1
    assert "[#calc:" not in pairs[0]["sentence"]
    assert "atom_007" not in pairs[0]["sentence"]
    assert "[#ev:" not in pairs[0]["sentence"]
    assert pairs[0]["sentence"] == "Cost fell to $4.2M"


def test_pairs_prefer_direct_quote_over_full_text_for_span():
    # Codex diff-gate iter-1 P2.1: offsets index into direct_quote/statement (what strict_verify
    # validates) — a row with BOTH must slice direct_quote, not full_text.
    ev_pool = {"ev_000": {
        "direct_quote": "ABCDEFGHIJ",                 # offsets 0-5 -> "ABCDE"
        "full_text": "zzzzzzzzzzzzzzzzzzzz",           # different bytes; must NOT be sliced
    }}
    kept = [{"sentence": "claim", "tokens": [{"evidence_id": "ev_000", "start": 0, "end": 5}]}]
    pairs = build_nli_pairs(kept, ev_pool)
    assert pairs[0]["span"] == "ABCDE"


def test_pairs_skip_when_no_resolvable_span_or_empty_claim():
    ev_pool = {"ev_000": {"full_text": "short"}}
    kept = [
        {"sentence": "[#ev:ev_000:0-5]", "tokens": [{"evidence_id": "ev_000", "start": 0, "end": 5}]},  # claim empty after strip
        {"sentence": "Claim with bad span", "tokens": [{"evidence_id": "ev_000", "start": 0, "end": 999}]},  # span out of range
        {"sentence": "Claim with missing ev", "tokens": [{"evidence_id": "nope", "start": 0, "end": 3}]},
    ]
    assert build_nli_pairs(kept, ev_pool) == []
    assert build_nli_pairs([], {}) == []


# --------------------------------------------------------------------------- #
# annotate_nli_entailment — scoring + fail-loud
# --------------------------------------------------------------------------- #

class _FakeJudge:
    """Mimics entailment_judge._EntailmentJudge: `judge(sentence, span) -> (verdict, reason)`.

    I-wire-012 (#1326): the annotator now scores pairs in PARALLEL (default PG_NLI_JUDGE_CONCURRENCY=12),
    so a verdict source MUST be thread-safe AND completion-order-independent. `by_sentence` maps each
    sentence text to its verdict (deterministic under any interleaving — the assertion contract). The
    legacy positional `verdicts` queue is kept (lock-guarded) for the single-pair / raise-path tests where
    order is irrelevant. `_model` mirrors the real attribute the annotator reports."""
    _model = "google/gemma-4-31b-it"

    def __init__(self, verdicts=None, *, raise_exc=None, by_sentence=None):
        self._verdicts = list(verdicts or [])
        self._raise_exc = raise_exc
        self._by_sentence = dict(by_sentence or {})
        self._lock = threading.Lock()

    def judge(self, sentence, span):
        if self._raise_exc is not None:
            raise self._raise_exc
        if self._by_sentence:
            return self._by_sentence[sentence], "reason-text"
        with self._lock:
            return self._verdicts.pop(0), "reason-text"


def _patch_judge(monkeypatch, judge):
    # The annotator does `from ...entailment_judge import _get_judge` INSIDE the async function, so
    # patching the module attribute before the call binds the fake at call time (no OpenRouter call).
    import src.polaris_graph.llm.entailment_judge as ej
    monkeypatch.setattr(ej, "_get_judge", lambda: judge)


def test_ok_path_maps_verdicts_to_counts(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    # I-wire-012: 3 pairs hit the PARALLEL path at the default concurrency, so map verdicts BY SENTENCE
    # (completion-order-independent) — proves the input-order-preserving aggregation maps correctly.
    _patch_judge(monkeypatch, _FakeJudge(by_sentence={
        "grounded": "ENTAILED", "adds a fact": "NEUTRAL", "contradicts": "CONTRADICTED",
    }))
    pairs = [
        {"sentence": "grounded", "span": "s", "section": "A", "evidence_id": "e0"},
        {"sentence": "adds a fact", "span": "s", "section": "B", "evidence_id": "e1"},
        {"sentence": "contradicts", "span": "s", "section": "C", "evidence_id": "e2"},
    ]
    out = asyncio.run(annotate_nli_entailment(pairs))
    assert out["nli_status"] == "ok"
    assert out["judge"] == "llm_entailment"
    assert out["model"] == "google/gemma-4-31b-it"
    assert out["sentences_checked"] == 3
    assert (out["entailed_count"], out["neutral_count"], out["contradicted_count"]) == (1, 1, 1)
    assert out["disputed_count"] == 2                       # NEUTRAL + CONTRADICTED
    verdicts = {d["sentence"]: d["verdict"] for d in out["disputed"]}
    assert verdicts == {"adds a fact": "NEUTRAL", "contradicts": "CONTRADICTED"}
    assert out["advisory"] is True


def test_unavailable_when_no_api_key(monkeypatch):
    # Missing OPENROUTER_API_KEY -> FAIL-LOUD NliUnavailableError (surfaced, never a silent pass);
    # the judge is NOT even constructed.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _patch_judge(monkeypatch, _FakeJudge(["ENTAILED"]))   # must NOT be reached
    pairs = [{"sentence": "x", "span": "y", "section": "A", "evidence_id": "e0"}]
    with pytest.raises(NliUnavailableError):
        asyncio.run(annotate_nli_entailment(pairs))


def test_budget_error_propagates_not_swallowed(monkeypatch):
    # A BudgetExceededError from the judge must PROPAGATE (the annotator has no catch) so the run aborts.
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _patch_judge(monkeypatch, _FakeJudge([], raise_exc=BudgetExceededError("cap")))
    pairs = [{"sentence": "x", "span": "y", "section": "A", "evidence_id": "e0"}]
    with pytest.raises(BudgetExceededError):
        asyncio.run(annotate_nli_entailment(pairs))


def test_judge_error_not_counted_as_entailed(monkeypatch):
    # I-cap-005 (#1068): the judge FAILS OPEN to ("ENTAILED", "judge_error: ...") on an API/parse error.
    # That MUST NOT be counted as a genuine entailment (silent downgrade — LAW II). It is counted as an
    # error, excluded from entailed_count, and surfaced in judge_error_count / judge_errors.
    class _ErrJudge:
        _model = "google/gemma-4-31b-it"

        def judge(self, sentence, span):
            if sentence == "ok":
                return "ENTAILED", "reason-text"          # genuine entailment
            return "ENTAILED", "judge_error: TimeoutError"  # fail-open error

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _patch_judge(monkeypatch, _ErrJudge())
    pairs = [
        {"sentence": "ok", "span": "s", "section": "A", "evidence_id": "e0"},
        {"sentence": "boom", "span": "s", "section": "B", "evidence_id": "e1"},
    ]
    out = asyncio.run(annotate_nli_entailment(pairs))
    assert out["nli_status"] == "ok"                  # one real verdict came back -> still ok
    assert out["entailed_count"] == 1                 # the error is NOT an entailment
    assert out["judge_error_count"] == 1
    assert out["sentences_scored"] == 1               # 2 checked, 1 errored
    assert out["judge_errors"][0]["sentence"] == "boom"
    assert out["judge_errors"][0]["reason"].startswith("judge_error:")


def test_all_judge_errors_maps_to_status_error(monkeypatch):
    # I-cap-005 (#1068): if EVERY call errors, nothing was actually entailment-checked -> nli_status MUST
    # be "error" (surfaced loudly), never "ok" with a misleading zero-dispute count.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    class _AllErr:
        _model = "google/gemma-4-31b-it"

        def judge(self, sentence, span):
            return "ENTAILED", "judge_error: ConnectionError"

    _patch_judge(monkeypatch, _AllErr())
    pairs = [{"sentence": "x", "span": "y", "section": "A", "evidence_id": "e0"}]
    out = asyncio.run(annotate_nli_entailment(pairs))
    assert out["nli_status"] == "error"
    assert out["entailed_count"] == 0
    assert out["judge_error_count"] == 1
    assert out["sentences_scored"] == 0


def test_empty_pairs_is_ok_zero(monkeypatch):
    # No pairs -> clean ok with zero checked WITHOUT needing OPENROUTER_API_KEY or a judge.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = asyncio.run(annotate_nli_entailment([]))
    assert out["nli_status"] == "ok"
    assert out["sentences_checked"] == 0
    assert out["judge"] == "llm_entailment"


# --------------------------------------------------------------------------- #
# I-wire-012 (#1326): bounded-parallel scoring — completes within the wall, coverage + budget intact
# --------------------------------------------------------------------------- #

def test_parallel_scoring_is_concurrent_and_order_preserving(monkeypatch):
    """The N per-pair judge calls run CONCURRENTLY (proving the wall-overrun fix) AND every pair is still
    scored with its OWN verdict mapped to its OWN sentence regardless of completion order (no sampling,
    no scrambling). Concurrency is proven by a max-in-flight counter (no wall-clock flake)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_NLI_JUDGE_CONCURRENCY", "8")

    in_flight = {"now": 0, "max": 0}
    lock = threading.Lock()

    class _SlowJudge:
        _model = "google/gemma-4-31b-it"

        def judge(self, sentence, span):
            with lock:
                in_flight["now"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["now"])
            try:
                time.sleep(0.05)  # real blocking work so the pool actually overlaps calls
                # verdict keyed on sentence content -> deterministic per-pair mapping under any interleave
                return ("CONTRADICTED" if sentence == "s3" else "ENTAILED"), f"r:{sentence}"
            finally:
                with lock:
                    in_flight["now"] -= 1

    _patch_judge(monkeypatch, _SlowJudge())
    pairs = [
        {"sentence": f"s{i}", "span": "x", "section": "S", "evidence_id": f"e{i}"}
        for i in range(16)
    ]
    out = asyncio.run(annotate_nli_entailment(pairs))
    assert out["nli_status"] == "ok"
    assert out["sentences_checked"] == 16          # ALL pairs scored — no sampling (§-1.1)
    assert out["entailed_count"] == 15
    assert out["contradicted_count"] == 1
    assert {d["sentence"] for d in out["disputed"]} == {"s3"}  # the one CONTRADICTED, correctly mapped
    assert in_flight["max"] >= 2                    # genuinely concurrent (>1 judge call in flight at once)


def test_parallel_sequential_fast_path_when_concurrency_one(monkeypatch):
    """PG_NLI_JUDGE_CONCURRENCY=1 forces the byte-identical sequential in-context path (off-mode/tests)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_NLI_JUDGE_CONCURRENCY", "1")
    _patch_judge(monkeypatch, _FakeJudge(by_sentence={"a": "ENTAILED", "b": "NEUTRAL"}))
    pairs = [
        {"sentence": "a", "span": "s", "section": "A", "evidence_id": "e0"},
        {"sentence": "b", "span": "s", "section": "B", "evidence_id": "e1"},
    ]
    out = asyncio.run(annotate_nli_entailment(pairs))
    assert out["sentences_checked"] == 2
    assert (out["entailed_count"], out["neutral_count"]) == (1, 1)


def test_parallel_budget_error_propagates(monkeypatch):
    """A BudgetExceededError raised inside a worker on the PARALLEL path (n>1) must PROPAGATE through
    future.result() so the run aborts (Core Invariant §9.1.6 — fail-closed, never a silent drop)."""
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_NLI_JUDGE_CONCURRENCY", "4")

    class _BudgetJudge:
        _model = "google/gemma-4-31b-it"

        def judge(self, sentence, span):
            if sentence == "boom":
                raise BudgetExceededError("cap breached")
            return "ENTAILED", "ok"

    _patch_judge(monkeypatch, _BudgetJudge())
    pairs = [
        {"sentence": s, "span": "x", "section": "S", "evidence_id": "e"}
        for s in ("a", "b", "boom", "d", "e")
    ]
    with pytest.raises(BudgetExceededError):
        asyncio.run(annotate_nli_entailment(pairs))
