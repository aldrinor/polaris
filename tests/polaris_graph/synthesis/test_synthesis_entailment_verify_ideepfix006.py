"""I-deepfix-006-compose C1 — offline behavioral tests for the ADDITIVE entailment verify path.

Proves the four faithfulness contracts of ``synthesis_entailment_verify`` with a DETERMINISTIC injected
``entails_fn`` (no GPU / network):

1. an ENTAILED paraphrase whose numbers match the cited span is KEPT (even with <2 verbatim overlap);
2. a paraphrase with a MISMATCHED number is DROPPED (the frozen numeric leg, reused unchanged);
3. a NON-entailed paraphrase is DROPPED (the entailment judge returns False);
4. the UNION wrapper keeps every ``strict_verify`` pass AND adds the entailed paraphrase (ADDITIVE).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import strict_verify
from src.polaris_graph.synthesis.synthesis_entailment_verify import (
    SYNTH_ENTAILMENT_SOFT_WARNING,
    entailment_grounds_sentence,
    entailment_verify,
    make_entailment_union_verify_fn,
)

# One cited span carrying the finding "mortality fell 25%".
_SPAN = "Mortality fell by 25% across the pooled multinational cohorts."
_POOL = {"ev_a": {"source_url": "https://nejm.org/a", "tier": "T1", "direct_quote": _SPAN}}
_TOK = f"[#ev:ev_a:0-{len(_SPAN)}]"

# A PARAPHRASE that shares < 2 verbatim content words with the span (deaths/dropped/combined/groups vs
# mortality/fell/pooled/cohorts) — the frozen >=2-content-word leg would DROP it — but is a faithful,
# number-matched restatement an entailment judge accepts.
_PARAPHRASE_OK = f"Deaths dropped 25% in the combined groups {_TOK}."
# The SAME paraphrase but with a number the span never states -> the frozen numeric leg must DROP it.
_PARAPHRASE_BAD_NUM = f"Deaths dropped 30% in the combined groups {_TOK}."


def _entails_true(_premise: str, _hypothesis: str):
    return True


def _entails_false(_premise: str, _hypothesis: str):
    return False


def _entails_none(_premise: str, _hypothesis: str):
    return None


def test_entailed_paraphrase_matching_numbers_is_kept():
    report = entailment_verify(_PARAPHRASE_OK, _POOL, entails_fn=_entails_true)
    assert len(report.kept_sentences) == 1, report.kept_sentences
    kept = report.kept_sentences[0]
    assert "25%" in kept.sentence
    assert [t.evidence_id for t in kept.tokens] == ["ev_a"]
    assert SYNTH_ENTAILMENT_SOFT_WARNING in kept.soft_warnings


def test_paraphrase_with_mismatched_number_is_dropped():
    # Even though the judge would ENTAIL it, the frozen numeric leg (30% not in span) DROPS it.
    report = entailment_verify(_PARAPHRASE_BAD_NUM, _POOL, entails_fn=_entails_true)
    assert report.kept_sentences == []


def test_non_entailed_paraphrase_is_dropped():
    report = entailment_verify(_PARAPHRASE_OK, _POOL, entails_fn=_entails_false)
    assert report.kept_sentences == []


def test_degrade_none_falls_back_to_verbatim_overlap():
    # Judge unavailable (None): the < 2-verbatim-overlap paraphrase must NOT be kept (degrade is
    # conservative — it falls back to the SAME >=2 content-word overlap the frozen engine uses).
    report = entailment_verify(_PARAPHRASE_OK, _POOL, entails_fn=_entails_none)
    assert report.kept_sentences == []


def test_cross_basket_citation_fails_closed():
    # A token whose evidence_id is absent from the (basket-scoped) pool resolves no span -> dropped.
    other_pool = {"ev_z": {"direct_quote": _SPAN}}
    report = entailment_verify(_PARAPHRASE_OK, other_pool, entails_fn=_entails_true)
    assert report.kept_sentences == []


def test_union_wrapper_is_additive_over_strict_verify(monkeypatch):
    # Disable strict_verify's own entailment LLM leg so the base engine is deterministic/offline.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    # A draft with TWO sentences: (1) a VERBATIM sentence strict_verify keeps on its own, and (2) the
    # entailed paraphrase strict_verify DROPS (< 2 verbatim overlap) but the entailment leg RESCUES.
    verbatim = f"Mortality fell by 25% across the pooled multinational cohorts {_TOK}."
    draft = f"{verbatim} {_PARAPHRASE_OK}"

    # Baseline: strict_verify alone keeps ONLY the verbatim sentence.
    base = strict_verify(draft, _POOL)
    base_texts = {sv.sentence for sv in base.kept_sentences}
    assert any("pooled multinational cohorts" in t for t in base_texts)
    assert not any("combined groups" in t for t in base_texts)

    # Union: keeps the verbatim sentence AND adds the entailed paraphrase (marked entailment-rescued).
    union_fn = make_entailment_union_verify_fn(strict_verify, entails_fn=_entails_true)
    union = union_fn(draft, _POOL)
    union_texts = {sv.sentence for sv in union.kept_sentences}
    assert any("pooled multinational cohorts" in t for t in union_texts)
    assert any("combined groups" in t for t in union_texts)
    # every strict_verify pass survives the union (ADDITIVE — never removes a frozen-engine pass)
    assert base_texts.issubset(union_texts)
    rescued = [sv for sv in union.kept_sentences if "combined groups" in sv.sentence]
    assert rescued and SYNTH_ENTAILMENT_SOFT_WARNING in rescued[0].soft_warnings


def test_entailment_grounds_sentence_promote_hook():
    # C3 promote hook (reused D3 pattern): entailed + number-matched -> True; non-entailed / bad-number -> False.
    rows = [{"direct_quote": _SPAN}]
    assert entailment_grounds_sentence(_PARAPHRASE_OK, rows, entails_fn=_entails_true) is True
    assert entailment_grounds_sentence(_PARAPHRASE_OK, rows, entails_fn=_entails_false) is False
    assert entailment_grounds_sentence(_PARAPHRASE_BAD_NUM, rows, entails_fn=_entails_true) is False
