"""Curated template catalog (M-10 — Phase B foundation).

Per FINAL_PLAN.md, the curated template router is the Phase B
mitigation for Risk #13 (query-to-template misrouting / unsupported-
query overclaim). Phase B ships with a SINGLE working template
(v30_clinical) plus the routing infrastructure; new templates are
added to this catalog as data, no router-code change required.

The catalog also doubles as the data source for the "supported scope"
page (FINAL_PLAN scope-page reinforcement mitigation): UI surfaces
each entry's display_name, description, and scope_summary so users
understand the bounds before submitting a query.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CuratedTemplate:
    """A supported audit template with metadata for routing + scope display.

    Codex M-10 review fix: signals are split into TWO classes to close
    the false-positive bypass identified in v1:

      drug_keywords   → STRONG signals (specific drug names + drug
                        classes). Required for the ROUTED verdict —
                        no drug-keyword hit means the verdict cannot
                        rise above OPERATOR_REVIEW regardless of
                        exemplar similarity. This is the Risk #13
                        guardrail: a query about supplements,
                        psychotherapy, or non-pharmaceutical
                        interventions cannot accidentally route to
                        v30_clinical just because it shares the
                        question scaffold of an exemplar.

      medical_keywords → BROAD signals (regulatory bodies, trial
                        methodology terms, conditions, generic
                        outcomes, broad medical-domain words).
                        Indicates the query is plausibly medical
                        and merits OPERATOR_REVIEW, but never alone
                        sufficient for ROUTED.

    `scope_keywords` is a property returning the union — kept for
    backwards compat with code that just wants the full bag.

    Attributes:
        template_id: Stable identifier matching a registered JobRunner.
        display_name: Human-readable name shown on the scope page.
        description: One- to two-sentence description.
        scope_summary: Longer scope description; documents IN-scope
                       AND OUT-of-scope per FINAL_PLAN scope-page
                       reinforcement mitigation.
        drug_keywords: Tuple of specific drugs / drug classes. Multi-
                       word entries match as token sets.
        medical_keywords: Tuple of broad medical/clinical-trial/
                          regulatory/condition terms.
        scope_examples: Concrete real-shape positive query exemplars.
    """

    template_id: str
    display_name: str
    description: str
    scope_summary: str
    drug_keywords: tuple[str, ...]
    medical_keywords: tuple[str, ...]
    scope_examples: tuple[str, ...]

    @property
    def scope_keywords(self) -> tuple[str, ...]:
        """Backward-compat: union of drug + medical keywords."""
        return tuple(self.drug_keywords) + tuple(self.medical_keywords)


# ---------------------------------------------------------------------------
# Phase B initial catalog
# ---------------------------------------------------------------------------

_V30_CLINICAL = CuratedTemplate(
    template_id="v30_clinical",
    display_name="Clinical drug audit",
    description=(
        "Audits a drug-condition pair for efficacy, safety, regulatory "
        "status, and contradictions across published evidence."
    ),
    scope_summary=(
        "IN SCOPE: questions about a specific regulated drug (by name "
        "or by drug class) for a specific clinical condition where "
        "regulatory filings, randomized trial data, and meta-analyses "
        "exist. Examples: efficacy of tirzepatide for type 2 diabetes; "
        "safety profile of semaglutide; cardiovascular outcomes of "
        "GLP-1 receptor agonists.\n\n"
        "OUT OF SCOPE: questions about supplements, vitamins, "
        "homeopathy, or other non-regulated interventions; "
        "psychotherapy or other non-pharmaceutical treatments; "
        "clinical practice guideline questions; patient-specific advice; "
        "non-clinical wellness; veterinary; off-label speculation "
        "without published evidence; comparative-effectiveness between "
        "drug classes when both lack head-to-head trials. The router "
        "will surface medical-but-non-drug queries to operator review; "
        "v30_clinical is not the right template for them."
    ),
    # Codex M-10 review fix: drug_keywords are the STRONG gate. Only
    # specific regulated drugs and drug classes qualify. Generic
    # words like "drug" / "medication" / "therapy" are NOT here —
    # they belong in medical_keywords (review-only).
    drug_keywords=(
        # Specific drug names (small Phase B set; expanded as the
        # template library grows in Phase C).
        "tirzepatide", "semaglutide", "liraglutide", "dulaglutide",
        "metformin", "empagliflozin", "dapagliflozin", "sitagliptin",
        "atorvastatin", "rosuvastatin",
        # Drug classes (multi-word entries match as token sets).
        "glp-1", "sglt2", "dpp-4",
        "monoclonal antibody", "monoclonal antibodies",
        "receptor agonist",
        # Regulated biologic / antibody umbrella terms — these only
        # matter as drug-keywords when paired with a real exemplar
        # match, so they are conservative.
        "biologic", "biosimilar",
    ),
    # Codex M-10 review fix: medical_keywords cover the broad medical
    # domain — clinical-trial terminology, regulatory framing,
    # conditions, and generic outcomes. A medical_keyword hit is
    # NEVER sufficient on its own for ROUTED; it can only push the
    # verdict up to OPERATOR_REVIEW (the operator decides whether
    # v30_clinical is the right template).
    medical_keywords=(
        # Trial methodology
        "randomized", "double-blind", "placebo", "placebo-controlled",
        "phase 1", "phase 2", "phase 3", "phase 4",
        "primary endpoint", "secondary endpoint",
        "meta-analysis", "systematic review",
        # Regulatory framing
        "fda", "ema", "mhra", "regulatory", "approval", "indication",
        "label", "post-marketing", "clinical trial", "trial",
        # Outcomes / safety
        "efficacy", "safety", "adverse", "adverse event", "tolerability",
        "mortality", "morbidity",
        "hba1c", "ldl", "blood pressure", "weight loss",
        # Conditions
        "diabetes", "type 2 diabetes", "obesity", "hypertension",
        "cardiovascular", "oncology", "cancer", "depression", "stroke",
        "atherosclerosis",
        # Broader medical-domain words
        "drug", "drugs", "treatment", "therapy", "medication",
        "patient", "patients",
        "disease", "syndrome", "condition", "study", "studies",
        "clinical", "pharmacology", "pharmacokinetic",
    ),
    scope_examples=(
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
        "Cardiovascular safety of GLP-1 receptor agonists",
        "Adverse event rates of liraglutide in obesity trials",
        "Empagliflozin cardiovascular outcomes meta-analysis in heart failure",
        "Atorvastatin efficacy for hypercholesterolemia in adults",
        "Phase 3 trial of monoclonal antibody for hypertension",
    ),
)

TEMPLATE_CATALOG: tuple[CuratedTemplate, ...] = (
    _V30_CLINICAL,
)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def list_catalog() -> tuple[CuratedTemplate, ...]:
    """Return the full curated catalog.

    The order of entries is meaningful: classifier picks the
    highest-scoring template, ties broken by catalog order.
    """
    return TEMPLATE_CATALOG


def get_template(template_id: str) -> CuratedTemplate | None:
    """Lookup a template by id. Returns None if not in the catalog."""
    for tmpl in TEMPLATE_CATALOG:
        if tmpl.template_id == template_id:
            return tmpl
    return None
