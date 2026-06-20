"""BUG-20 (I-arch-011) — adequacy false-pass + wrong-domain completeness checklist.

TWO behavioral defects, both fixed in this lane:

1. ADEQUACY FALSE-PASS ON CONTENT-LESS STUBS.
   ``assess_corpus_adequacy`` counted EVERY retrieved row toward the grounded
   ``evidence_rows`` threshold, including rows the fetch/tier layer flagged as
   content-less stubs (``fetch_degraded`` / ``content_starved`` / ``fetch_failed``
   / ``landing_page``). A corpus padded with stubs (the real run had 91) read as
   adequate (decision=proceed) even though it had almost no grounded content.
   FIX: when the real ``evidence_rows`` are supplied, the grounded count EXCLUDES
   content-less stubs, so a stub-padded corpus can no longer false-PASS. This is a
   faithfulness improvement — it STOPS a false PASS and adds no cap/floor (a merely
   down-weighted but GROUNDED row is still counted, per the WEIGHT-AND-CONSOLIDATE
   DNA §-1.3).

2. WRONG-DOMAIN COMPLETENESS CHECKLIST.
   A Parkinson's / deep-brain-stimulation (DBS) question routes ``domain="clinical"``
   and was scored against the GLP-1 / drug-efficacy clinical checklist. Post-BUG-7,
   6 of its 7 topics are ``requires_drug_intervention`` and become non-applicable,
   leaving a single applicable topic that incidentally matches -> "100% covered".
   The topics a reviewer of a DBS question expects (device efficacy / UPDRS-III,
   patient selection, hardware complications, stimulation adverse effects, warning
   signs) were never measured.
   FIX: ``check_completeness`` routes a Parkinson's/DBS question to a question-matched
   sub-domain checklist (clinical_neuro_device) via config-driven ``routing_terms``,
   so the applicable topics match what is being asked.

These tests assert the BEHAVIOR (the decision flip + the routed topic ids), fail on
the pre-fix code, and pass after the fix.
"""
from __future__ import annotations

from src.polaris_graph.nodes.completeness_checker import check_completeness
from src.polaris_graph.nodes.corpus_adequacy_gate import (
    assess_corpus_adequacy,
    count_grounded_rows,
)

_DBS_QUESTION = (
    "What are the clinical outcomes and risks of subthalamic nucleus deep brain "
    "stimulation (DBS) for advanced Parkinson's disease?"
)

# A clinical tier mix that satisfies every NON-evidence-row threshold (T1/T2/T3
# counts, fractions), so the adequacy decision hinges ONLY on the grounded
# evidence-row count. clinical thresholds: min_evidence_rows=6, min_total=10,
# min_t1=3, min_t1_plus_t2=5, min_t1_plus_t2_plus_t3=6.
_CLINICAL_TIER_COUNTS = {"T1": 4, "T2": 3, "T3": 2, "T4": 1}


def _grounded_row() -> dict:
    return {
        "direct_quote": "STN-DBS reduced UPDRS-III by 44% at five years.",
        "statement": "Deep brain stimulation efficacy outcome.",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12439180/",
    }


def _stub_row(flag: str) -> dict:
    # A content-less stub flagged by the fetch/tier layer. Empty grounding span.
    return {
        "direct_quote": "",
        "statement": "",
        "source_url": "https://example.org/landing",
        flag: True,
    }


# ── Part (a): adequacy must not count content-less stubs as grounded ──────────

def test_content_less_stubs_excluded_from_grounded_count() -> None:
    rows = [_grounded_row() for _ in range(2)]
    rows += [_stub_row("content_starved") for _ in range(4)]
    rows += [_stub_row("fetch_failed") for _ in range(3)]
    rows += [_stub_row("landing_page") for _ in range(2)]
    rows += [_stub_row("fetch_degraded") for _ in range(2)]
    # 2 grounded, 11 stubs => grounded count must be 2, not 13.
    assert count_grounded_rows(rows) == 2


def test_stub_padded_corpus_does_not_false_pass_adequacy() -> None:
    """The real defect: 2 grounded rows + 11 stubs flips proceed -> abort."""
    rows = [_grounded_row() for _ in range(2)]
    # Pad with content-less stubs across the real fetch-layer flags.
    rows += [_stub_row("content_starved") for _ in range(5)]
    rows += [_stub_row("landing_page") for _ in range(4)]
    rows += [_stub_row("fetch_failed") for _ in range(2)]

    # Without the rows (legacy count-only path), the inflated count = 13 PASSES.
    legacy = assess_corpus_adequacy(
        tier_counts=_CLINICAL_TIER_COUNTS,
        evidence_row_count=len(rows),
        domain="clinical",
    )
    assert legacy.decision == "proceed", (
        "precondition: the stub-inflated count clears every threshold, so the "
        "legacy count-only path passes — that is the false PASS this lane fixes"
    )

    # With the real rows, the grounded count = 2 (< min_evidence_rows=6) so the
    # gate FAILS the evidence_rows threshold and refuses to proceed.
    fixed = assess_corpus_adequacy(
        tier_counts=_CLINICAL_TIER_COUNTS,
        evidence_row_count=len(rows),
        domain="clinical",
        evidence_rows=rows,
    )
    assert fixed.decision != "proceed", (
        "BUG-20: a corpus of 2 grounded rows + 11 content-less stubs must NOT "
        f"false-PASS adequacy; got decision={fixed.decision!r}"
    )
    assert fixed.evidence_rows == 2
    ev_finding = next(f for f in fixed.findings if f.name == "evidence_rows")
    assert ev_finding.ok is False
    assert ev_finding.observed == 2


def test_down_weighted_grounded_row_still_counts() -> None:
    """§-1.3: a down-weighted but GROUNDED row is a real source — never excluded."""
    row = _grounded_row()
    row["down_weighted"] = True
    row["retrieval_weight"] = 0.05
    assert count_grounded_rows([row]) == 1


# ── Part (b): a Parkinson's/DBS question routes to the neuro-device checklist ──

def test_dbs_question_routes_to_neuro_device_checklist() -> None:
    report = check_completeness(
        domain="clinical",
        research_question=_DBS_QUESTION,
        evidence_rows=[],
    )
    # The routed checklist supplies DBS-specific topic ids that DO NOT exist in the
    # GLP-1 clinical checklist.
    topic_ids = {tc.topic.id for tc in report.topics}
    assert report.domain == "clinical_neuro_device"
    assert "hardware_complications" in topic_ids
    assert "device_efficacy" in topic_ids
    assert "patient_selection" in topic_ids
    assert "warning_signs" in topic_ids
    # The GLP-1-CLASS pharmacology topic must NOT leak in (wrong drug class for a
    # device question). The drug-gated `contraindications`/`drug_interactions`
    # backstop topics ARE present by design (dormant unless a drug is detected),
    # so they are deliberately not excluded here.
    assert "class_specific_risks_glp1" not in topic_ids
    assert "efficacy_primary" not in topic_ids  # GLP-1 drug-endpoint topic


def test_dbs_question_does_not_get_glp1_template() -> None:
    """Pre-fix, a DBS question got the clinical (GLP-1) checklist whose applicable
    topics collapsed to a near-vacuous 1-of-1; post-fix it gets the neuro-device
    checklist whose DBS topics are uncovered against empty evidence (honest gaps).
    """
    report = check_completeness(
        domain="clinical",
        research_question=_DBS_QUESTION,
        evidence_rows=[],
    )
    # Empty evidence -> the routed DBS topics are applicable + uncovered (real gaps
    # surfaced), NOT a vacuous "fully covered".
    assert report.total_applicable >= 4
    assert report.total_uncovered == report.total_applicable
    assert report.covered_fraction == 0.0


def test_non_dbs_clinical_question_keeps_default_clinical_checklist() -> None:
    """No-match routing is byte-identical: a drug question stays on clinical.yaml."""
    report = check_completeness(
        domain="clinical",
        research_question=(
            "What is the efficacy and safety of semaglutide for weight loss?"
        ),
        evidence_rows=[],
    )
    assert report.domain == "clinical"
    topic_ids = {tc.topic.id for tc in report.topics}
    # The drug checklist's topics are present; the neuro-device ones are not.
    assert "class_specific_risks_glp1" in topic_ids
    assert "hardware_complications" not in topic_ids


def test_drug_bearing_parkinsons_question_keeps_contraindications_check() -> None:
    """SAFETY (BUG-7 #1262 must NOT regress): a question that mentions Parkinson's
    but is actually about a DRUG must NEVER lose the critical `contraindications`
    topic gating abort_critical_topic_uncovered.

    Two protections combine: (a) routing keys on DEVICE terms only, so a bare
    disease-name drug question stays on the drug clinical checklist; (b) even when
    a question DOES route to the neuro-device checklist, the drug-gated critical
    `contraindications` topic lives there too as a backstop. Either way the
    critical check is present whenever a drug is detected.
    """
    # (a) Drug question that only names the disease -> stays on clinical.yaml.
    drug_q = (
        "What are the contraindications and drug interactions of "
        "levodopa-carbidopa in Parkinson's disease?"
    )
    report = check_completeness(
        domain="clinical", research_question=drug_q, evidence_rows=[],
    )
    # Pin the routing decision: a disease-name-only drug question must NOT route to
    # the device checklist (guards against re-adding bare "parkinson" routing terms).
    assert report.domain == "clinical"
    ids = {tc.topic.id for tc in report.topics}
    assert "contraindications" in ids, (
        "a levodopa drug question must keep the CRITICAL contraindications topic; "
        f"got domain={report.domain!r} ids={sorted(ids)}"
    )
    contra = next(tc for tc in report.topics if tc.topic.id == "contraindications")
    assert contra.topic.critical is True
    assert contra.applies is True  # levodopa is a recognized drug -> applicable

    # (b) A DEVICE question that also names a drug routes to neuro-device but the
    # critical contraindications backstop is still present + applicable.
    device_drug_q = (
        "How does subthalamic nucleus deep brain stimulation compare with "
        "levodopa drug therapy for advanced Parkinson's disease?"
    )
    report2 = check_completeness(
        domain="clinical", research_question=device_drug_q, evidence_rows=[],
    )
    assert report2.domain == "clinical_neuro_device"
    ids2 = {tc.topic.id for tc in report2.topics}
    assert "contraindications" in ids2
    contra2 = next(
        tc for tc in report2.topics if tc.topic.id == "contraindications"
    )
    assert contra2.topic.critical is True
    assert contra2.applies is True  # levodopa present -> critical topic active


def test_pure_device_question_recognizes_device_intervention() -> None:
    """FIX-P0-B (I-arch-011 #1271): a pure DEVICE question (deep brain stimulation,
    no drug) is now DELIBERATELY recognized by the device/procedure recognizer, so
    the critical ``contraindications`` topic — gated on a recognized intervention —
    is APPLICABLE for the device run.

    This UPDATES the prior behavior (pre-device-recognizer: ``applies is False``):
    before the recognizer was taught device/procedure stems, a deep-brain-stimulation
    question had NO recognized intervention, so the drug-gated critical topic stayed
    dormant. Now the device IS recognized as an intervention, so device-safety
    completeness (contraindications) correctly applies. The resulting
    ``abort_critical_topic_uncovered`` hazard on an uncovered corpus is mitigated by
    the always-release conversion to ``released_with_disclosed_gaps`` (verified body
    ships, gap LABELED) — see
    ``tests/.../test_critical_topic_uncovered_always_release_iarch011.py``.
    """
    report = check_completeness(
        domain="clinical", research_question=_DBS_QUESTION, evidence_rows=[],
    )
    assert report.domain == "clinical_neuro_device"
    contra = next(
        (tc for tc in report.topics if tc.topic.id == "contraindications"), None
    )
    assert contra is not None
    assert contra.topic.critical is True
    # The device recognizer now recognizes the DBS device as an intervention, so the
    # critical device-safety topic is APPLICABLE (not dormant). An uncovered corpus
    # therefore SURFACES the gap (-> the always-release disclosed-gaps path), instead
    # of the topic silently vanishing.
    assert contra.applies is True
    assert "contraindications" in report.uncovered_critical_topic_ids()
