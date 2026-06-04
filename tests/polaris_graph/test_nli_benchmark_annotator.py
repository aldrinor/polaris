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

class _FakeMiniCheck:
    """Mimics the MiniCheck .score(docs, claims) -> (labels, probs, chunks, chunk_probs) API."""
    def __init__(self, probs):
        self._probs = probs

    def score(self, docs, claims):
        return [1] * len(claims), list(self._probs), None, None


class _FakeFaithLens:
    """Mimics the FaithLens .infer(docs, claims) -> [ {prediction, explanation} ] API."""
    def __init__(self, preds):
        self._preds = preds

    def infer(self, docs, claims):
        return [{"prediction": p, "explanation": "x"} for p in self._preds]


def _patch_loader(monkeypatch, scorer):
    # The annotator does `from ...nli_verifier import PG_NLI_MODEL, load_nli_model` INSIDE the async
    # function, so patching the module attributes before the call binds the fakes at call time —
    # importing nli_verifier here does NOT pull torch (load_nli_model imports it lazily).
    async def _fake_load():
        return scorer
    import src.polaris_graph.agents.nli_verifier as nli_verifier
    monkeypatch.setattr(nli_verifier, "load_nli_model", _fake_load)
    monkeypatch.setattr(nli_verifier, "PG_NLI_MODEL", "flan-t5-large", raising=False)


def test_ok_path_flags_low_prob_as_disputed(monkeypatch):
    _patch_loader(monkeypatch, _FakeMiniCheck(probs=[0.95, 0.10]))
    pairs = [
        {"sentence": "grounded claim", "span": "support", "section": "A", "evidence_id": "ev_000"},
        {"sentence": "hallucinated claim", "span": "unrelated", "section": "B", "evidence_id": "ev_001"},
    ]
    out = asyncio.run(annotate_nli_entailment(pairs, threshold=0.25))
    assert out["nli_status"] == "ok"
    assert out["sentences_checked"] == 2
    assert out["disputed_count"] == 1                       # only the 0.10 sentence
    assert out["disputed"][0]["sentence"] == "hallucinated claim"
    assert out["min_prob"] == 0.10
    assert out["advisory"] is True


def test_faithlens_infer_api_is_supported(monkeypatch):
    _patch_loader(monkeypatch, _FakeFaithLens(preds=[1, 0]))
    pairs = [
        {"sentence": "entailed", "span": "s", "section": "A", "evidence_id": "e0"},
        {"sentence": "not entailed", "span": "s", "section": "B", "evidence_id": "e1"},
    ]
    out = asyncio.run(annotate_nli_entailment(pairs, threshold=0.25))
    assert out["nli_status"] == "ok"
    assert out["disputed_count"] == 1                       # pred 0 -> prob 0.0 < 0.25


def test_unavailable_model_raises_not_silent(monkeypatch):
    _patch_loader(monkeypatch, None)                        # load_nli_model returns None
    pairs = [{"sentence": "x", "span": "y", "section": "A", "evidence_id": "e0"}]
    with pytest.raises(NliUnavailableError):
        asyncio.run(annotate_nli_entailment(pairs, threshold=0.25))


def test_empty_pairs_is_ok_zero(monkeypatch):
    # No pairs -> a clean ok with zero checked (does not even load the model).
    out = asyncio.run(annotate_nli_entailment([], threshold=0.25))
    assert out["nli_status"] == "ok"
    assert out["sentences_checked"] == 0
