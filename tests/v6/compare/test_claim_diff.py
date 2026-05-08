"""I-f12-003 — claim-level diff tests."""

from __future__ import annotations

import pytest

from polaris_v6.compare.claim_diff import compute_claim_diff
from polaris_v6.schemas.evidence_contract import EvidenceContract, VerifiedSentence


def _vs(sid: str, text: str, eids: list[str], drop: str | None = None) -> VerifiedSentence:
    return VerifiedSentence(
        section_id=sid, sentence_text=text,
        provenance_tokens=[f"[#ev:{e}:0-10]" for e in eids],
        verifier_local_pass=drop is None, verifier_global_pass=drop is None,
        drop_reason=drop,
    )

def _c(rid: str, sents: list[VerifiedSentence]) -> EvidenceContract:
    return EvidenceContract(
        run_id=rid, template="t", question="q?",
        queued_at="2026-05-08T00:00:00Z", finished_at="2026-05-08T00:00:30Z",
        pipeline_status="success", evidence_pool=[],
        verified_sentences=sents, frame_coverage=[], contradictions=[],
        cost_usd=0.0, generator_model="g", verifier_model="v",
        family_segregation_passed=True,
    )


def test_agreement_high_overlap_shared_evidence() -> None:
    t = "Drug X reduced HbA1c by 1.5 percent"
    rep = compute_claim_diff(_c("L", [_vs("S1", t, ["a"])]), _c("R", [_vs("S1", t, ["a"])]))
    assert rep.entries[0].verdict == "agreement"


@pytest.mark.parametrize("ev", [["a"], ["b"]])
def test_partial_mid_overlap_either_evidence(ev: list[str]) -> None:
    rep = compute_claim_diff(
        _c("L", [_vs("S1", "Drug X reduced HbA1c 1.5 percent in trial A", ["a"])]),
        _c("R", [_vs("S1", "Drug X improved HbA1c trial A by some amount", ev)]),
    )
    assert rep.entries[0].verdict == "partial"


def test_partial_low_overlap_shared_evidence() -> None:
    rep = compute_claim_diff(
        _c("L", [_vs("S1", "alpha beta gamma", ["a"])]),
        _c("R", [_vs("S1", "completely different words", ["a"])]),
    )
    assert rep.entries[0].verdict == "partial"


def test_disagreement_low_overlap_disjoint_evidence() -> None:
    rep = compute_claim_diff(
        _c("L", [_vs("S1", "alpha beta gamma", ["a"])]),
        _c("R", [_vs("S1", "completely different words", ["b"])]),
    )
    assert rep.entries[0].verdict == "disagreement"


def test_only_left_section_missing_right() -> None:
    rep = compute_claim_diff(
        _c("L", [_vs("S1", "shared", ["a"]), _vs("S2", "left-only", ["x"])]),
        _c("R", [_vs("S1", "shared", ["a"])]),
    )
    s2 = [e for e in rep.entries if e.section_id == "S2"]
    assert len(s2) == 1 and s2[0].verdict == "only_left"


def test_counts_aggregated() -> None:
    same = "Drug X reduced HbA1c by 1.5 percent"
    rep = compute_claim_diff(
        _c("L", [_vs("S1", same, ["a"]), _vs("S2", "alpha beta gamma", ["x"])]),
        _c("R", [_vs("S1", same, ["a"]), _vs("S2", "completely different", ["y"])]),
    )
    assert sum(rep.counts_by_verdict.values()) == len(rep.entries)
    assert rep.counts_by_verdict["agreement"] == 1
    assert rep.counts_by_verdict["disagreement"] == 1


def test_provenance_tokens_in_text_stripped_before_jaccard() -> None:
    rep = compute_claim_diff(
        _c("L", [_vs("S1", "alpha [#ev:a:0-10]", ["a"])]),
        _c("R", [_vs("S1", "omega [#ev:b:0-10]", ["b"])]),
    )
    assert rep.entries[0].verdict == "disagreement"


def test_dropped_sentences_excluded_and_same_run_id_rejected() -> None:
    t = "Drug X reduced HbA1c by 1.5 percent"
    rep = compute_claim_diff(
        _c("L", [_vs("S1", t, ["a"]), _vs("S1", "dropped", ["z"], drop="numeric_mismatch")]),
        _c("R", [_vs("S1", t, ["a"])]),
    )
    assert all("dropped" not in (e.left_sentence or "") for e in rep.entries)
    with pytest.raises(ValueError):
        compute_claim_diff(_c("X", []), _c("X", []))
