"""Unit tests for the closed ARCHETYPE registry + pure report-shape helpers (GENERALIZED Fix 4).

OFFLINE, pure — no network, no LLM, no frozen-file touch. Covers:
  * resolve_archetype synonym resolution (longest match), default fallback, opaque-kind preservation;
  * build_framing_md byte-identity for the review default + empty-title (memo) behavior;
  * order_report_blocks permutation invariant (count-invariant, KF-position by archetype);
  * contract_requires_section carve-out for methods-in-body.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.polaris_graph.generator.report_skeleton import (  # noqa: E402
    ARCHETYPES,
    DEFAULT_ARCHETYPE,
    build_framing_md,
    contract_requires_section,
    order_report_blocks,
    resolve_archetype,
)


@dataclass
class _Term:
    dimension: str
    value: Any


@dataclass
class _Sec:
    section_id: str = ""
    title: Any = None


@dataclass
class _Contract:
    deliverable: list = field(default_factory=list)
    sections: list = field(default_factory=list)


def _blocks():
    return dict(
        key_findings_md="## Key Findings\n\nKF\n",
        sections_concat="### Theme\n\nSEC\n",
        depth_layer_md="## Analytical synthesis\n\nDEP\n",
        methods_md="## Methods\n\nMET\n",
        biblio_section_md="## Bibliography\n\nBIB\n",
        cwf_disclosed_md="## CWF\n\nCWF\n",
        drop_disclosure_md="## Drop\n\nDROP\n",
    )


# --- resolve_archetype -----------------------------------------------------

def test_resolve_default_when_no_contract():
    a, assumed, opaque = resolve_archetype(None)
    assert a.key == DEFAULT_ARCHETYPE and assumed and opaque == ""


def test_resolve_named_kind_maps_to_archetype():
    c = _Contract(deliverable=[_Term("deliverable.kind", "decision memo")])
    a, assumed, opaque = resolve_archetype(c)
    assert a.key == "memo" and not assumed and opaque == ""


def test_resolve_longest_synonym_wins():
    # "systematic review" (longer) must beat "review" (substring)
    c = _Contract(deliverable=[_Term("deliverable.kind", "Systematic Review")])
    a, _assumed, _opaque = resolve_archetype(c)
    assert a.key == "systematic_review"


def test_resolve_unmapped_kind_is_opaque_and_falls_back():
    c = _Contract(deliverable=[_Term("deliverable.kind", "interpretive dance")])
    a, assumed, opaque = resolve_archetype(c)
    assert a.key == DEFAULT_ARCHETYPE and assumed and opaque == "interpretive dance"


def test_resolve_ignores_non_kind_terms():
    c = _Contract(deliverable=[_Term("deliverable.format", "table")])
    a, assumed, _opaque = resolve_archetype(c)
    assert a.key == DEFAULT_ARCHETYPE and assumed


# --- build_framing_md ------------------------------------------------------

def test_framing_review_has_heading_and_is_claim_free():
    fm = build_framing_md("the impact of AI on labor", ARCHETYPES["review"])
    assert "## Introduction and Scope" in fm
    assert "[" not in fm and "]" not in fm and "**" not in fm


def test_framing_empty_for_memo_and_empty_objective():
    assert build_framing_md("q", ARCHETYPES["memo"]) == ""
    assert build_framing_md("", ARCHETYPES["review"]) == ""
    assert build_framing_md("   ", ARCHETYPES["review"]) == ""


# --- order_report_blocks ---------------------------------------------------

def test_review_order_and_permutation_invariant():
    b = _blocks()
    body, mach = order_report_blocks(ARCHETYPES["review"], **b, methods_is_machinery=True)
    assert body.index("### Theme") < body.index("## Key Findings")
    assert body.index("## Key Findings") < body.index("## Bibliography")
    assert "## Methods" in mach and "## Methods" not in body
    combined = body + mach
    for blk in b.values():
        assert combined.count(blk) == 1


def test_memo_leads_with_key_findings():
    b = _blocks()
    body, _mach = order_report_blocks(ARCHETYPES["memo"], **b)
    assert body.index("## Key Findings") < body.index("### Theme")


def test_methods_in_body_when_required():
    b = _blocks()
    body, mach = order_report_blocks(ARCHETYPES["review"], **b, methods_is_machinery=False)
    assert "## Methods" in body and "## Methods" not in mach
    assert (body + mach).count(b["methods_md"]) == 1


# --- contract_requires_section --------------------------------------------

def test_requires_section_matches_title_value():
    c = _Contract(sections=[_Sec(section_id="s1", title=_Term("deliverable.section", "Methods"))])
    assert contract_requires_section(c, "methods")
    assert not contract_requires_section(c, "results")


def test_requires_section_none_contract():
    assert not contract_requires_section(None, "methods")
    assert not contract_requires_section(_Contract(), "methods")
