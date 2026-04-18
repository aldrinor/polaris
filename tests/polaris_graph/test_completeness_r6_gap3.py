"""
R-6 Gap-3 regression tests: completeness checklist checker.
"""
from __future__ import annotations

from src.polaris_graph.nodes.completeness_checker import (
    check_completeness,
    load_checklist,
)


def test_gap3_checklist_loads_for_clinical() -> None:
    topics = load_checklist("clinical")
    assert len(topics) >= 5
    ids = {t.id for t in topics}
    assert "efficacy_primary" in ids
    assert "safety_adverse_events" in ids
    assert "class_specific_risks_glp1" in ids


def test_gap3_checklist_loads_for_policy() -> None:
    topics = load_checklist("policy")
    assert len(topics) >= 4
    ids = {t.id for t in topics}
    assert "regulatory_framework" in ids
    assert "enforcement" in ids


def test_gap3_unknown_domain_returns_empty() -> None:
    topics = load_checklist("nonexistent_domain")
    assert topics == []


def test_gap3_covered_corpus_returns_full_coverage() -> None:
    """A corpus with evidence on all topics should cover fully."""
    evidence = [
        {"direct_quote": (
            "In adults with obesity, semaglutide produced a mean weight loss "
            "of 14.9% at week 68, a statistically significant reduction."
        ), "statement": "STEP 1 efficacy"},
        {"direct_quote": (
            "Nausea, vomiting, and diarrhea were the most common adverse "
            "events in the semaglutide arm."
        ), "statement": "STEP 1 safety"},
        {"direct_quote": (
            "Semaglutide is contraindicated in patients with a personal "
            "or family history of medullary thyroid carcinoma or MEN 2 "
            "syndrome. A boxed warning is included."
        ), "statement": "FDA label warnings"},
        {"direct_quote": (
            "Pancreatitis was reported in 0.3% of semaglutide recipients. "
            "Gallbladder events were also noted. The thyroid C-cell signal "
            "from rodent studies prompts the boxed warning."
        ), "statement": "Class-specific GLP-1 risks"},
        {"direct_quote": (
            "Wegovy is FDA approved for chronic weight management in adults "
            "with obesity; EMA granted a similar indication in 2022."
        ), "statement": "Regulatory status"},
        {"direct_quote": (
            "Dose adjustment may be required in patients with renal "
            "impairment; use in pregnancy is not recommended."
        ), "statement": "Population subgroups"},
        {"direct_quote": (
            "Drug interactions with insulin secretagogues may require dose "
            "reduction of concomitant medications to avoid hypoglycemia."
        ), "statement": "Interactions"},
    ]
    report = check_completeness(
        domain="clinical",
        research_question=(
            "What is the efficacy and safety of semaglutide for weight loss?"
        ),
        evidence_rows=evidence,
    )
    assert report.total_applicable >= 5
    # All GLP-1 class topics should apply because "semaglutide" is in evidence
    ids_applicable = {
        t.topic.id for t in report.topics if t.applies
    }
    assert "class_specific_risks_glp1" in ids_applicable
    # And should be covered
    glp1_coverage = next(
        t for t in report.topics
        if t.topic.id == "class_specific_risks_glp1"
    )
    assert glp1_coverage.covered is True
    # Overall
    assert report.total_uncovered == 0


def test_gap3_missing_pancreatitis_flagged() -> None:
    """The live-run PG_LB_SA_02-like gap: semaglutide corpus without
    pancreatitis/gallbladder mention must flag the class-specific-risks
    topic as uncovered."""
    evidence = [
        {"direct_quote": "Mean weight loss was 14.9% at week 68 with semaglutide 2.4 mg.",
         "statement": "Efficacy"},
        {"direct_quote": "Nausea was the most common adverse event reported.",
         "statement": "Safety"},
        {"direct_quote": "Wegovy is FDA approved for chronic weight management.",
         "statement": "Regulatory"},
    ]
    report = check_completeness(
        domain="clinical",
        research_question="Semaglutide weight loss in adults with obesity",
        evidence_rows=evidence,
    )
    uncovered = report.uncovered_topic_ids()
    assert "class_specific_risks_glp1" in uncovered
    # Expand queries should include pancreatitis / gallbladder / thyroid probes
    all_queries = " ".join(report.expand_queries).lower()
    assert "pancreatitis" in all_queries
    assert "thyroid" in all_queries


def test_gap3_applies_if_filters_topic() -> None:
    """class_specific_risks_glp1 should NOT apply for a non-GLP-1 query."""
    evidence = [
        {"direct_quote": "Metformin 500 mg twice daily reduced HbA1c by 1.2 percentage points.",
         "statement": "Metformin result"},
    ]
    report = check_completeness(
        domain="clinical",
        research_question="What is the efficacy of metformin for type 2 diabetes?",
        evidence_rows=evidence,
    )
    glp1_topic = next(
        t for t in report.topics
        if t.topic.id == "class_specific_risks_glp1"
    )
    assert glp1_topic.applies is False


def test_gap3_expand_queries_substitute_drug_token() -> None:
    evidence = [
        {"direct_quote": "semaglutide weight loss 14.9%",
         "statement": "Efficacy only"},
    ]
    report = check_completeness(
        domain="clinical",
        research_question="Semaglutide safety profile",
        evidence_rows=evidence,
    )
    # Expand queries should carry "semaglutide" in place of {drug}
    combined = " ".join(report.expand_queries).lower()
    assert "semaglutide" in combined
    # And should NOT leave unsubstituted {drug} placeholder
    assert "{drug}" not in combined


def test_gap3_covered_fraction_computed() -> None:
    evidence = [
        {"direct_quote": "semaglutide weight loss 14.9%", "statement": ""},
    ]
    report = check_completeness(
        domain="clinical",
        research_question="Semaglutide safety",
        evidence_rows=evidence,
    )
    # Most topics uncovered → low fraction
    assert report.covered_fraction < 0.5


def test_gap3_empty_evidence_uncovered_everywhere() -> None:
    report = check_completeness(
        domain="clinical",
        research_question="Semaglutide weight loss",
        evidence_rows=[],
    )
    # Nothing covered
    assert report.total_covered == 0
    assert report.total_uncovered >= 1


def test_gap3_policy_checklist_works() -> None:
    evidence = [
        {"direct_quote": (
            "The FDA's final guidance on PCCPs for AI-enabled device "
            "software functions was issued December 2024. Effective "
            "immediately, manufacturers may submit a Predetermined "
            "Change Control Plan. Industry stakeholders, patient "
            "advocacy groups, and manufacturers commented during the "
            "public comment period."
        ), "statement": "FDA PCCP guidance summary"},
    ]
    report = check_completeness(
        domain="policy",
        research_question="FDA regulation of AI-enabled medical devices under PCCP",
        evidence_rows=evidence,
    )
    covered_ids = {
        t.topic.id for t in report.topics
        if t.applies and t.covered
    }
    assert "regulatory_framework" in covered_ids
    assert "stakeholder_impact" in covered_ids
    assert "implementation_timeline" in covered_ids


def test_gap3_notes_describe_uncovered() -> None:
    report = check_completeness(
        domain="clinical",
        research_question="semaglutide weight loss",
        evidence_rows=[
            {"direct_quote": "semaglutide achieved 14.9% weight loss.",
             "statement": "Efficacy only"},
        ],
    )
    assert len(report.notes) >= 1
    assert "uncovered" in report.notes[0].lower()
