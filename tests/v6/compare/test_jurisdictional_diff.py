"""I-f12-004 — jurisdictional diff tests."""

from __future__ import annotations

import pytest

from polaris_v6.compare.jurisdictional_diff import compute_jurisdictional_diff
from polaris_v6.schemas.evidence_contract import EvidenceContract, VerifiedSentence


def _vs(sid: str, text: str, eids: list[str]) -> VerifiedSentence:
    return VerifiedSentence(
        section_id=sid, sentence_text=text,
        provenance_tokens=[f"[#ev:{e}:0-10]" for e in eids],
        verifier_local_pass=True, verifier_global_pass=True, drop_reason=None,
    )


def _c(rid: str, q: str, sents: list[VerifiedSentence]) -> EvidenceContract:
    return EvidenceContract(
        run_id=rid, template="t", question=q,
        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
        pipeline_status="success", evidence_pool=[],
        verified_sentences=sents, frame_coverage=[], contradictions=[],
        cost_usd=0.0, generator_model="g", verifier_model="v",
        family_segregation_passed=True,
    )


def test_two_jurisdictions_one_pair() -> None:
    q = "Drug X efficacy?"
    rep = compute_jurisdictional_diff(
        {"canada": _c("c", q, [_vs("S1", "shared", ["a"])]),
         "us": _c("u", q, [_vs("S1", "shared", ["a"])])},
    )
    assert len(rep.pairs) == 1
    assert rep.pairs[0].left_jurisdiction == "canada"
    assert rep.pairs[0].right_jurisdiction == "us"
    # claim_diff actually computed (not stub)
    assert rep.pairs[0].claim_diff.counts_by_verdict["agreement"] == 1


def test_three_jurisdictions_three_pairs() -> None:
    q = "Drug X?"
    rep = compute_jurisdictional_diff({
        j: _c(j, q, [_vs("S1", "shared text", ["a"])]) for j in ("canada", "us", "eu")
    })
    assert len(rep.pairs) == 3


def test_pairs_sorted_alphabetically_by_jurisdiction() -> None:
    q = "Q?"
    rep = compute_jurisdictional_diff({
        j: _c(j, q, [_vs("S1", "x", ["a"])]) for j in ("us", "canada", "eu")
    })
    assert rep.jurisdictions == ["canada", "eu", "us"]
    assert rep.pairs[0].left_jurisdiction == "canada"
    assert rep.pairs[0].right_jurisdiction == "eu"


def test_question_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="identical question"):
        compute_jurisdictional_diff({
            "canada": _c("c", "Q1?", []),
            "us": _c("u", "Q2?", []),
        })


def test_single_jurisdiction_rejected() -> None:
    with pytest.raises(ValueError, match=">= 2"):
        compute_jurisdictional_diff({"canada": _c("c", "Q?", [])})
