"""I-arch-004 F08 + F11 (#1249): qualitative present-vs-absent conflicts must gate
PT08, and an uncovered CRITICAL clinical completeness topic must HOLD release.

F08 — BUG: the qualitative (present-vs-absent) conflict records were DETECTED and
written to contradictions.json + rendered in the report, but were NEVER added to the
PT08 evaluator payload (run_external_evaluation received only numeric + semantic
records). So a high present-vs-absent conflict (one source asserts a contraindication,
another denies it) could never block release. FIX: pass the EXACT subset
render_qualitative_disclosure renders inline (hard CONFLICT rows always; REVIEW flags
only when PG_SWEEP_QUAL_REVIEW_INLINE is on) into PT08, so a real undisclosed
qualitative conflict holds release, while a legitimately-collapsed record never
false-fails.

F11 — BUG: the completeness gate was advisory — a clinical report with 0%
contraindication coverage shipped as the success-class ok_incomplete_corpus (GREEN).
FIX: a checklist topic marked `critical: true` (contraindications / boxed warnings)
that is applicable+uncovered on a CLINICAL run yields the non-success
abort_critical_topic_uncovered. Non-clinical runs (no critical-marked checklist) are
byte-identical; kill-switch PG_SWEEP_CRITICAL_COMPLETENESS_HOLD (default ON).

Both fixes STRENGTHEN release gating and never relax strict_verify / NLI / 4-role D8 /
provenance. Offline, no network, no heavy ML.
"""
from __future__ import annotations

from dataclasses import asdict

import pytest

from src.polaris_graph.evaluator.external_evaluator import run_external_evaluation
from src.polaris_graph.nodes.completeness_checker import (
    ChecklistTopic,
    CompletenessReport,
    TopicCoverage,
    check_completeness,
    load_checklist,
)
from src.polaris_graph.retrieval.qualitative_conflict_detector import (
    QualitativeConflictRecord,
)

from scripts.run_honest_sweep_r3 import (
    UNIFIED_STATUS_VALUES,
    _critical_completeness_hold_on,
    qualitative_records_disclosed_for_pt08,
    to_unified_status,
)

_CRITICAL_HOLD_ENV = "PG_SWEEP_CRITICAL_COMPLETENESS_HOLD"
_QUAL_REVIEW_INLINE_ENV = "PG_SWEEP_QUAL_REVIEW_INLINE"


# --------------------------------------------------------------------------- helpers
def _qual_record(*, subject: str, predicate: str, severity: str) -> QualitativeConflictRecord:
    """A present-vs-absent qualitative conflict record (loader-shaped)."""
    return QualitativeConflictRecord(
        predicate=predicate,
        subject=subject,
        severity=severity,
        claims=[
            {"evidence_id": "ev_a", "predicate": predicate, "value": 1.0,
             "assertion_status": "present", "source_tier": "T1"},
            {"evidence_id": "ev_b", "predicate": predicate, "value": 0.0,
             "assertion_status": "absent", "source_tier": "T2"},
        ],
        conflict_reason="present vs absent across sources",
    )


def _clinical_protocol() -> dict:
    return {
        "research_question": "semaglutide contraindications",
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.30, "max_fraction": 0.60},
        ],
    }


_EVIDENCE_POOL = {
    "ev_a": {"direct_quote": "Drug X is contraindicated in pregnancy.", "tier": "T1"},
    "ev_b": {"direct_quote": "Drug X showed no contraindication signal.", "tier": "T2"},
}


def _report_disclosing(subject: str, predicate: str) -> str:
    """A methods-complete report that DISCLOSES the subject + predicate (PT08 passes)."""
    return (
        "## Methods\n"
        "Retrieved 2026-06-14 using protocol.json. "
        "deepseek/deepseek-v3.2-exp generated. qwen/qwen3-8b evaluated. "
        "Included RCTs. Excluded blogs. Tiers T1-T7. Expected actual tier match.\n"
        "## Qualitative safety-conflict disclosures\n"
        f"- [CONFLICT] {subject} / {predicate}: present vs absent.\n"
        "## Results\n"
        "Body.\n"
    )


def _report_omitting() -> str:
    """A methods-complete report that does NOT disclose any qualitative conflict."""
    return (
        "## Methods\n"
        "Retrieved 2026-06-14 using protocol.json. "
        "deepseek/deepseek-v3.2-exp generated. qwen/qwen3-8b evaluated. "
        "Included RCTs. Excluded blogs. Tiers T1-T7. Expected actual tier match.\n"
        "## Results\n"
        "Body with no conflict disclosure.\n"
    )


# ===========================================================================
# F08 — qualitative records reach PT08
# ===========================================================================
class TestF08QualitativePt08Eligibility:
    def test_hard_record_eligible_when_clinical(self, monkeypatch):
        monkeypatch.delenv(_QUAL_REVIEW_INLINE_ENV, raising=False)
        recs = [_qual_record(subject="drug x", predicate="contraindicated", severity="high")]
        eligible = qualitative_records_disclosed_for_pt08(recs, is_clinical=True)
        assert len(eligible) == 1
        assert eligible[0].subject == "drug x"

    def test_medium_record_eligible_when_clinical(self, monkeypatch):
        monkeypatch.delenv(_QUAL_REVIEW_INLINE_ENV, raising=False)
        recs = [_qual_record(subject="drug x", predicate="contraindicated", severity="medium")]
        assert len(qualitative_records_disclosed_for_pt08(recs, is_clinical=True)) == 1

    def test_non_clinical_excludes_everything(self, monkeypatch):
        # Non-clinical runs render nothing (renderer returns "") -> PT08 must not gate.
        monkeypatch.delenv(_QUAL_REVIEW_INLINE_ENV, raising=False)
        recs = [_qual_record(subject="drug x", predicate="contraindicated", severity="high")]
        assert qualitative_records_disclosed_for_pt08(recs, is_clinical=False) == []

    def test_review_excluded_by_default(self, monkeypatch):
        # REVIEW flags collapse to a count by default (not rendered inline) -> not PT08-gated.
        monkeypatch.delenv(_QUAL_REVIEW_INLINE_ENV, raising=False)
        recs = [_qual_record(subject="drug x", predicate="warning", severity="review")]
        assert qualitative_records_disclosed_for_pt08(recs, is_clinical=True) == []

    def test_review_eligible_when_review_inline_on(self, monkeypatch):
        # When PG_SWEEP_QUAL_REVIEW_INLINE is ON the review rows ARE rendered -> PT08-gated.
        monkeypatch.setenv(_QUAL_REVIEW_INLINE_ENV, "1")
        recs = [_qual_record(subject="drug x", predicate="warning", severity="review")]
        assert len(qualitative_records_disclosed_for_pt08(recs, is_clinical=True)) == 1

    def test_empty_input_is_noop(self):
        assert qualitative_records_disclosed_for_pt08([], is_clinical=True) == []

    def test_dedup_collapses_identical_signature(self, monkeypatch):
        monkeypatch.delenv(_QUAL_REVIEW_INLINE_ENV, raising=False)
        recs = [
            _qual_record(subject="drug x", predicate="contraindicated", severity="high"),
            _qual_record(subject="drug x", predicate="contraindicated", severity="high"),
        ]
        # Same (subject, predicate, status-signature) -> collapsed to one; the kept
        # record's subject+predicate still appears in the report so PT08 is satisfied.
        assert len(qualitative_records_disclosed_for_pt08(recs, is_clinical=True)) == 1


class TestF08Pt08GatesUndisclosedQualitative:
    """The bug repro: a high present-vs-absent conflict that the report does NOT
    disclose must now FAIL PT08 (release blocked). Pre-fix, the qualitative record
    never reached PT08, so PT08 always passed regardless."""

    def test_undisclosed_qualitative_conflict_fails_pt08(self):
        rec = _qual_record(subject="drug x", predicate="contraindicated", severity="high")
        eligible = qualitative_records_disclosed_for_pt08([rec], is_clinical=True)
        assert eligible, "fixture must be PT08-eligible"
        result = run_external_evaluation(
            report_text=_report_omitting(),
            protocol=_clinical_protocol(),
            tier_distribution_report={"tier_fractions": {}},
            contradictions=[asdict(qr) for qr in eligible],
            evidence_pool=_EVIDENCE_POOL,
        )
        pt08 = next(r for r in result.rule_checks if r.item_id == "PT08")
        assert pt08.passed is False, "undisclosed qualitative conflict must fail PT08"
        assert any("contraindicated" in m for m in result.contradictions_missing)

    def test_disclosed_qualitative_conflict_passes_pt08(self):
        rec = _qual_record(subject="drug x", predicate="contraindicated", severity="high")
        eligible = qualitative_records_disclosed_for_pt08([rec], is_clinical=True)
        result = run_external_evaluation(
            report_text=_report_disclosing("drug x", "contraindicated"),
            protocol=_clinical_protocol(),
            tier_distribution_report={"tier_fractions": {}},
            contradictions=[asdict(qr) for qr in eligible],
            evidence_pool=_EVIDENCE_POOL,
        )
        pt08 = next(r for r in result.rule_checks if r.item_id == "PT08")
        assert pt08.passed is True, "a disclosed qualitative conflict must pass PT08"

    def test_non_clinical_qualitative_does_not_gate_pt08(self):
        # On a non-clinical run nothing is rendered, so nothing reaches PT08 -> no
        # false abort even with an undisclosed (would-be) conflict present.
        rec = _qual_record(subject="drug x", predicate="contraindicated", severity="high")
        eligible = qualitative_records_disclosed_for_pt08([rec], is_clinical=False)
        result = run_external_evaluation(
            report_text=_report_omitting(),
            protocol=_clinical_protocol(),
            tier_distribution_report={"tier_fractions": {}},
            contradictions=[asdict(qr) for qr in eligible],
            evidence_pool=_EVIDENCE_POOL,
        )
        pt08 = next(r for r in result.rule_checks if r.item_id == "PT08")
        assert pt08.passed is True


# ===========================================================================
# F11 — uncovered critical clinical completeness topic holds release
# ===========================================================================
class TestF11ChecklistCriticalField:
    def test_clinical_checklist_marks_contraindications_critical(self):
        topics = load_checklist("clinical")
        assert topics, "clinical checklist must load"
        contra = next((t for t in topics if t.id == "contraindications"), None)
        assert contra is not None
        assert contra.critical is True

    def test_other_clinical_topics_not_critical_by_default(self):
        topics = load_checklist("clinical")
        efficacy = next((t for t in topics if t.id == "efficacy_primary"), None)
        assert efficacy is not None
        assert efficacy.critical is False

    def test_checklist_topic_critical_defaults_false(self):
        t = ChecklistTopic(id="x", label="X")
        assert t.critical is False


class TestF11UncoveredCriticalTopicIds:
    def _clinical_evidence_without_contraindications(self) -> list[dict]:
        # Efficacy + adverse-event coverage but ZERO contraindication keywords.
        return [
            {"direct_quote": "Mean weight loss was 14.9% at week 68.", "statement": ""},
            {"direct_quote": "Nausea was the most common adverse event.", "statement": ""},
        ]

    def test_uncovered_contraindications_surfaces_critical(self):
        report = check_completeness(
            domain="clinical",
            research_question="semaglutide efficacy and safety",
            evidence_rows=self._clinical_evidence_without_contraindications(),
        )
        assert "contraindications" in report.uncovered_topic_ids()
        assert report.uncovered_critical_topic_ids() == ["contraindications"]

    def test_covered_contraindications_no_critical_gap(self):
        rows = self._clinical_evidence_without_contraindications() + [
            {"direct_quote": "Drug X is contraindicated in patients with MEN 2.",
             "statement": ""},
        ]
        report = check_completeness(
            domain="clinical",
            research_question="semaglutide efficacy and safety",
            evidence_rows=rows,
        )
        assert "contraindications" not in report.uncovered_topic_ids()
        assert report.uncovered_critical_topic_ids() == []

    def test_helper_only_counts_applicable_uncovered_critical(self):
        crit_topic = ChecklistTopic(id="contraindications", label="C", critical=True)
        noncrit = ChecklistTopic(id="efficacy", label="E", critical=False)
        report = CompletenessReport(
            domain="clinical",
            topics=[
                TopicCoverage(topic=crit_topic, applies=True, covered=False, hits=0),
                TopicCoverage(topic=noncrit, applies=True, covered=False, hits=0),
                # A critical topic that does NOT apply must be ignored.
                TopicCoverage(
                    topic=ChecklistTopic(id="other_crit", label="O", critical=True),
                    applies=False, covered=False, hits=0,
                ),
            ],
            total_applicable=2, total_covered=0, total_uncovered=2,
        )
        assert report.uncovered_critical_topic_ids() == ["contraindications"]


class TestF11HoldGatePredicate:
    """The sweep's status branch fires iff
    (clinical) AND (kill-switch ON) AND (uncovered critical topics exist).
    This proves a clinical run with 0% contraindication coverage -> hold, while
    non-clinical / kill-switch-OFF stay advisory."""

    def _uncovered_clinical_report(self) -> CompletenessReport:
        return check_completeness(
            domain="clinical",
            research_question="semaglutide efficacy and safety",
            evidence_rows=[
                {"direct_quote": "Mean weight loss was 14.9%.", "statement": ""},
            ],
        )

    @staticmethod
    def _holds(*, is_clinical: bool, report: CompletenessReport) -> bool:
        # Mirrors the exact predicate in scripts/run_honest_sweep_r3.py status chain.
        return bool(
            is_clinical
            and _critical_completeness_hold_on()
            and report.uncovered_critical_topic_ids()
        )

    def test_clinical_uncovered_critical_holds(self, monkeypatch):
        monkeypatch.delenv(_CRITICAL_HOLD_ENV, raising=False)  # default ON
        report = self._uncovered_clinical_report()
        assert report.uncovered_critical_topic_ids()  # repro: real gap exists
        assert self._holds(is_clinical=True, report=report) is True

    def test_non_clinical_never_holds(self, monkeypatch):
        monkeypatch.delenv(_CRITICAL_HOLD_ENV, raising=False)
        report = self._uncovered_clinical_report()
        assert self._holds(is_clinical=False, report=report) is False

    def test_kill_switch_off_reverts_to_advisory(self, monkeypatch):
        monkeypatch.setenv(_CRITICAL_HOLD_ENV, "0")
        report = self._uncovered_clinical_report()
        assert report.uncovered_critical_topic_ids()
        assert self._holds(is_clinical=True, report=report) is False

    def test_kill_switch_default_is_on(self, monkeypatch):
        monkeypatch.delenv(_CRITICAL_HOLD_ENV, raising=False)
        assert _critical_completeness_hold_on() is True


class TestF11StatusTaxonomy:
    def test_status_in_unified_taxonomy(self):
        assert "abort_critical_topic_uncovered" in UNIFIED_STATUS_VALUES

    def test_status_maps_to_itself(self):
        assert (
            to_unified_status("abort_critical_topic_uncovered")
            == "abort_critical_topic_uncovered"
        )

    def test_status_is_known_to_regression_lab_as_abort_tier(self):
        from src.polaris_graph.audit_ir.regression_lab import (
            KNOWN_STATUS_VALUES,
            _STATUS_TIERS,
        )
        assert "abort_critical_topic_uncovered" in KNOWN_STATUS_VALUES
        assert _STATUS_TIERS["abort_critical_topic_uncovered"] == 2  # abort tier
