"""Compare two EvidenceContract bundles side-by-side."""

from __future__ import annotations

from dataclasses import dataclass

from polaris_v6.schemas.evidence_contract import EvidenceContract


@dataclass
class ReportComparison:
    left_run_id: str
    right_run_id: str
    same_template: bool
    same_question: bool
    shared_evidence_ids: list[str]
    only_left_evidence_ids: list[str]
    only_right_evidence_ids: list[str]
    shared_evidence_pct: float  # |shared| / |left ∪ right|
    frame_coverage_overlap: list[str]  # frame_ids present in both
    only_left_frames: list[str]
    only_right_frames: list[str]
    left_contradictions: int
    right_contradictions: int
    pipeline_status_match: bool
    family_segregation_both_pass: bool


def compare_reports(left: EvidenceContract, right: EvidenceContract) -> ReportComparison:
    if left.run_id == right.run_id:
        raise ValueError("compare_reports requires two distinct runs")

    left_ev = {s.evidence_id for s in left.evidence_pool}
    right_ev = {s.evidence_id for s in right.evidence_pool}
    shared = sorted(left_ev & right_ev)
    union = left_ev | right_ev
    shared_pct = len(shared) / len(union) if union else 0.0

    left_frames = {f.frame_id for f in left.frame_coverage}
    right_frames = {f.frame_id for f in right.frame_coverage}
    frame_overlap = sorted(left_frames & right_frames)

    return ReportComparison(
        left_run_id=left.run_id,
        right_run_id=right.run_id,
        same_template=left.template == right.template,
        same_question=left.question.strip() == right.question.strip(),
        shared_evidence_ids=shared,
        only_left_evidence_ids=sorted(left_ev - right_ev),
        only_right_evidence_ids=sorted(right_ev - left_ev),
        shared_evidence_pct=shared_pct,
        frame_coverage_overlap=frame_overlap,
        only_left_frames=sorted(left_frames - right_frames),
        only_right_frames=sorted(right_frames - left_frames),
        left_contradictions=len(left.contradictions),
        right_contradictions=len(right.contradictions),
        pipeline_status_match=left.pipeline_status == right.pipeline_status,
        family_segregation_both_pass=(
            left.family_segregation_passed and right.family_segregation_passed
        ),
    )
