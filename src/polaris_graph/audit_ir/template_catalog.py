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

    Attributes:
        template_id: Stable identifier matching a registered JobRunner
                     (e.g. "v30_clinical"). Job enqueue validates against
                     `list_runners()` so an entry here without a runner
                     is detected on enqueue.
        display_name: Human-readable name shown on the scope page.
        description: One- to two-sentence description of what this
                     template does.
        scope_summary: Longer scope description for the scope page.
                       Should be honest about boundaries (what's IN scope,
                       what's NOT in scope).
        scope_keywords: Tuple of tokens / token-bigrams that indicate
                        the query is plausibly in scope. Multi-word
                        entries are matched as token sets (every word
                        must appear in the query). Used by the
                        classifier as a coarse domain signal.
        scope_examples: Positive query exemplars that the classifier
                        compares against via Jaccard token similarity.
                        These should be concrete, real-shape questions
                        — not abstract slogans.
    """

    template_id: str
    display_name: str
    description: str
    scope_summary: str
    scope_keywords: tuple[str, ...]
    scope_examples: tuple[str, ...]


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
        "IN SCOPE: questions about a specific drug or drug class for a "
        "specific clinical condition where regulatory filings, randomized "
        "trial data, and meta-analyses exist. Examples: efficacy of "
        "tirzepatide for type 2 diabetes; safety profile of semaglutide; "
        "FDA approval pathway for a new monoclonal antibody.\n\n"
        "OUT OF SCOPE: clinical practice guideline questions; patient-"
        "specific advice; non-clinical wellness; veterinary; off-label "
        "speculation without published evidence; comparative-effectiveness "
        "between drug classes when both classes lack head-to-head trials. "
        "Submit those queries only after the operator confirms scope."
    ),
    # Domain + clinical-specific signals. Multi-word entries match as
    # token sets (every word must appear in the query).
    scope_keywords=(
        # Clinical-trial framing
        "efficacy", "safety", "randomized", "placebo", "double-blind",
        "trial", "clinical", "phase 1", "phase 2", "phase 3",
        "primary endpoint", "secondary endpoint", "meta-analysis",
        # Regulatory framing
        "fda", "ema", "regulatory", "approval", "indication",
        "label", "post-marketing",
        # Outcomes
        "mortality", "morbidity", "adverse", "tolerability",
        "hba1c", "ldl", "blood pressure",
        # Common drug families / drugs
        "glp-1", "tirzepatide", "semaglutide", "liraglutide",
        "metformin", "monoclonal", "biologic",
        # Common conditions / domains
        "diabetes", "obesity", "hypertension", "cardiovascular",
        "oncology", "cancer", "depression", "stroke",
        # Medical domain (broader — flags for operator review when
        # alone, prevents over-triage as unsupported)
        "drug", "treatment", "therapy", "medication", "patient",
        "disease", "syndrome", "condition", "study", "studies",
    ),
    scope_examples=(
        "What is the efficacy of tirzepatide for type 2 diabetes?",
        "Safety profile of semaglutide for obesity",
        "Studies on metformin for diabetes",
        "Clinical trial outcomes for monoclonal antibodies in hypertension",
        "FDA approval pathway for new diabetes drugs",
        "Cardiovascular safety of GLP-1 receptor agonists",
        "Adverse event rates of liraglutide in obesity trials",
        "Meta-analysis of biologic therapy in oncology",
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
