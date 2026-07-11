"""S2/S3 re-pass iter-5 (Fable full-list) — offline unit tests.

Locks the iter-5 fixes that split the two output-confirmed false merges ("the consolidation
ghost is wounded, not dead") and the surrounding hardening. Pure/deterministic (no LLM, no
network): every NLI-dependent path is exercised with an injected deterministic ``entail_fn``.

Covered: P0-1(a) stopword/function-word/verb/adverb subject collapse; P0-1(b) numbers-strict
value gate + telemetry; P0-1(c) sentence-mergeable heading/nav screen; P1-2 cross-host filename
same-work union; P1-5 nav/homepage/catalog chrome detector; P1-6 bibtex/metadata rep screen.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.synthesis import finding_dedup as fd
from src.polaris_graph.retrieval import line_screen as ls


# ─────────────────────────────────────────────────────────────────────────
# P0-1(a) — non-content (stopword / function-word / verb / adverb) subject collapse
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("subject", [
    "their", "reveals", "because", "thus", "significant", "point", "capabilities",
    "mid", "particularly", "significant point", "their level",
])
def test_noncontent_subject_is_collapsed(subject):
    assert fd._subject_is_noncontent(subject) is True


@pytest.mark.parametrize("subject", [
    "unemployment rate", "productivity", "tirzepatide", "GDP", "automation exposure",
    "wages", "large language models", "total factor productivity",
])
def test_content_subject_is_kept(subject):
    assert fd._subject_is_noncontent(subject) is False


class _Claim:
    def __init__(self, subject, value, unit="", predicate="level"):
        self.subject = subject
        self.value = value
        self.unit = unit
        self.predicate = predicate
        self.dose = ""
        self.arm = "treatment"
        self.endpoint_phrase = ""


def test_finding_key_collapses_stopword_subject_to_unknown():
    k = fd._finding_key(_Claim("reveals", 26.08, "percent"), "ev_927", 0,
                        exact_value=True, clinical=False)
    assert k[0] == "__unknown__"


def test_finding_key_keeps_content_subject():
    k = fd._finding_key(_Claim("productivity", 26.08, "percent"), "ev_1", 0,
                        exact_value=True, clinical=False)
    assert k[0] == "productivity"


def test_clinical_row_key_never_folds():
    # A clinical row keeps its verbatim strict subject even if it is a function word.
    k = fd._finding_key(_Claim("their", 4.0), "ev_x", 0, exact_value=True, clinical=True)
    assert k[0] == "their"


# ─────────────────────────────────────────────────────────────────────────
# P0-1(b) — numbers-strict value presence
# ─────────────────────────────────────────────────────────────────────────
def test_value_present_formatting_tolerant():
    assert fd._text_contains_value("the share rises to 5.5 per cent", 5.5) is True
    assert fd._text_contains_value("about 1,000 workers", 1000.0) is True
    assert fd._text_contains_value("just over 46% of jobs", 46.0) is True


def test_value_absent_from_boilerplate():
    assert fd._text_contains_value("Narrative Review reporting checklist standard", 4.0) is False


def test_value_gate_fail_open_on_none():
    assert fd._text_contains_value("any text", None) is True


def test_numeric_confirm_splits_when_value_missing_and_records_telemetry():
    # Two rows collide on a garbage (folded) numeric key but one claim sentence lacks the value.
    rows = [
        {"evidence_id": "a", "direct_quote": "Access to the tool raised output by 14 percent.",
         "source_url": "https://x.org/a", "authority_score": 0.9},
        {"evidence_id": "b", "direct_quote": "Narrative Review reporting checklist boilerplate.",
         "source_url": "https://y.org/b", "authority_score": 0.5},
    ]
    groups = {("thing", "level", 14.0, "percent", "", "", ""): [0, 1]}
    tel: dict = {}
    # Deterministic entail_fn: claim both-ways entail (so only the value gate can split).
    out = fd._confirm_numeric_clusters_via_nli(
        groups, rows, lambda ri: rows[ri]["authority_score"],
        entail_fn=lambda a, b: True, telemetry=tel,
    )
    # b lacked '14' in its claim sentence -> split into its own singleton.
    keys = list(out.keys())
    assert any("__split__" in str(k) for k in keys)
    assert tel.get("members_split_numbers_strict", 0) >= 1


# ─────────────────────────────────────────────────────────────────────────
# P0-1(c) — sentence-mergeable heading / nav screen
# ─────────────────────────────────────────────────────────────────────────
def test_bare_heading_is_not_mergeable():
    assert fd._sentence_mergeable("Main findings from the consultation process") is False


def test_genuine_claim_is_mergeable():
    assert fd._sentence_mergeable(
        "Access to the tool increases productivity by 14 percent among support agents."
    ) is True


def test_nav_dominated_row_has_no_mergeable_claim():
    row = {"direct_quote": "(https://x.org/#main-navigation)(https://x.org/about) Home | About | Login"}
    assert fd._row_has_mergeable_claim(row) is False


# ─────────────────────────────────────────────────────────────────────────
# P1-2 — cross-host filename same-work union
# ─────────────────────────────────────────────────────────────────────────
def test_url_basename_key_discriminative():
    a = {"source_url": "https://www.econstor.eu/bitstream/10419/279352/1/cesifo1_wp10601.pdf"}
    b = {"source_url": "https://www.ifo.de/DocDL/cesifo1_wp10601.pdf"}
    ka, kb = fd._url_basename_key(a), fd._url_basename_key(b)
    assert ka and ka == kb  # same distinctive filename across hosts => same key


@pytest.mark.parametrize("url", [
    "https://site.org/index.html", "https://site.org/download", "https://cbo.gov/publication/61147",
    "https://site.org/en", "https://site.org/",
])
def test_url_basename_key_rejects_generic(url):
    assert fd._url_basename_key({"source_url": url}) == ""


def test_filename_union_merges_cross_host_mirrors():
    os.environ["PG_SWEEP_CREDIBILITY_REDESIGN"] = "1"
    rows = [
        {"evidence_id": "ev_095", "direct_quote": "Employment fell by 2% in exposed occupations.",
         "source_url": "https://www.econstor.eu/bitstream/10419/279352/1/cesifo1_wp10601.pdf",
         "title": "CESifo Working Paper 10601", "authority_score": 0.8},
        {"evidence_id": "ev_110", "direct_quote": "Employment fell by 2% in exposed occupations.",
         "source_url": "https://www.ifo.de/DocDL/cesifo1_wp10601.pdf",
         "title": "cesifo1 wp10601", "authority_score": 0.7},
    ]
    res = fd.consolidate_same_work(rows)
    # Both rows resolve to ONE work id (one canonical), so corroboration cannot count them twice.
    work_ids = {res.work_id_by_index.get(0), res.work_id_by_index.get(1)}
    assert len(work_ids) == 1 and None not in work_ids


# ─────────────────────────────────────────────────────────────────────────
# P1-5 — nav / homepage / catalog chrome detector (S2)
# ─────────────────────────────────────────────────────────────────────────
def test_nav_homepage_fires_on_chrome():
    body = "\n".join([
        "## Header menu",
        "* [About](https://site.org/about)",
        "* [Opportunities](https://site.org/opportunities)",
        "* [Publications](https://site.org/publications)",
        "* [Login](https://site.org/login)",
        "* [Contact](https://site.org/contact)",
        "Sort by | Filter by | Results 1 of 50",
        "* [Rankings](https://site.org/rankings)",
    ])
    row = {"direct_quote": body, "source_url": "https://site.org/"}
    assert ls._row_is_nav_homepage_catalog(row) is True


def test_nav_homepage_fail_open_on_real_prose():
    body = (
        "Generative AI raises worker productivity in professional writing tasks. "
        "In a preregistered experiment, access to an assistive chatbot increased output "
        "by fourteen percent while cutting task time nearly in half across the sample."
    )
    row = {"direct_quote": body, "source_url": "https://journal.org/article"}
    assert ls._row_is_nav_homepage_catalog(row) is False


# ─────────────────────────────────────────────────────────────────────────
# P1-6 — bibtex / metadata representative screen
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Experimental evidence @article{Noy2023ExperimentalEO, title={x}, year={2023}}",
    "Published by Informa UK Limited, trading as Taylor & Francis Group",
    "Cite as: arXiv:2303.10130",
    "Author keywords: generative AI; labor; productivity",
])
def test_metadata_rep_is_boilerplate(text):
    assert fd._is_boilerplate_or_metadata_line(text) is True


def test_genuine_claim_is_not_boilerplate():
    assert fd._is_boilerplate_or_metadata_line(
        "Access to the tool increases productivity by 14 percent."
    ) is False
