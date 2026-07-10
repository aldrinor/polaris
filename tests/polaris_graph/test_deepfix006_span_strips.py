"""I-deepfix-006 A/B/C/D/E (#1376) — span-level junk-strip defense-in-depth in weighted_enrichment.

Every strip is SPAN-LEVEL and SUPPRESS-only: it excises furniture / markup text or withholds a
shell/marketing span from the drafting body, but the SOURCE is never deleted from the evidence pool.
Each fix is gated by a default-ON kill-switch that, when OFF, is byte-identical to the legacy text.

Real-shaped fixtures mirror the drb_72 forensic (gov banner welded to a finding, a "Crossref 0"
citation widget, "5 Minute Read Time" reader furniture, IMF working-paper front-matter, the ev_716
nav/search link-farm shell, and the TRU/AACSB marketing preambles).
"""
import os

import pytest

from src.polaris_graph.generator import weighted_enrichment as we


# ── A/B inline furniture strip (PG_INLINE_FURNITURE_STRIP) ───────────────────

def test_gov_banner_stripped_inline_clause_kept():
    s = "An official website of the United States government The unemployment rate fell 0.4% in 2020."
    out = we.strip_inline_furniture(s)
    assert "official website" not in out
    assert out == "The unemployment rate fell 0.4% in 2020."


def test_crossref_widget_stripped_inline_clause_kept():
    s = "Adoption rose to 12% Crossref 0 across firms."
    out = we.strip_inline_furniture(s)
    assert "Crossref" not in out
    assert "Adoption rose to 12%" in out and "across firms." in out


def test_reading_time_stripped_inline_clause_kept():
    s = "5 Minute Read Time Automation cut costs by 8%."
    out = we.strip_inline_furniture(s)
    assert "Minute Read Time" not in out
    assert out == "Automation cut costs by 8%."


def test_standalone_date_stamp_stripped():
    s = "02-10-2025 Manufacturing output rose by 3%."
    out = we.strip_inline_furniture(s)
    assert "02-10-2025" not in out
    assert "Manufacturing output rose by 3%." in out


def test_imf_front_matter_stripped():
    s = ("© 2025 International Monetary Fund WP/25/123 Prepared by the staff. "
         "Authorized for distribution by the department. Automation reduced hours worked.")
    out = we.strip_inline_furniture(s)
    assert "International Monetary Fund" not in out
    assert "WP/25/123" not in out
    assert "Prepared by" not in out
    assert "Authorized for distribution by" not in out
    assert "Automation reduced hours worked." in out


def test_acknowledgements_stripped_keeps_finding_clause():
    s = "The authors would like to thank the referees for comments. Wages fell 0.42%."
    out = we.strip_inline_furniture(s)
    assert "would like to thank" not in out
    assert out == "Wages fell 0.42%."


def test_prepared_by_with_finding_is_kept_fail_open():
    # "Prepared by" here introduces a REAL attribution carrying a finding — must NOT be stripped.
    s = "Prepared by the OECD, which found unemployment rose 2%."
    assert we.strip_inline_furniture(s) == s


def test_inline_furniture_off_is_byte_identical():
    os.environ["PG_INLINE_FURNITURE_STRIP"] = "0"
    try:
        s = "An official website of the United States government The rate fell."
        assert we.strip_inline_furniture(s) == s
    finally:
        os.environ.pop("PG_INLINE_FURNITURE_STRIP", None)


# ── C inline markup strip (PG_INLINE_MARKUP_STRIP) ───────────────────────────

def test_markdown_link_remnant_stripped():
    s = "Employment grew ](http://example.com/y) sharply."
    out = we.strip_inline_markup(s)
    assert "](http" not in out
    assert "Employment grew" in out and "sharply." in out


def test_bare_url_stripped():
    s = "See https://example.org/report for the figure of 5%."
    out = we.strip_inline_markup(s)
    assert "https://" not in out
    assert "5%" in out


def test_url_path_query_fragment_stripped():
    s = "Data at /search/researchers?institution=41ILO_INST&query=*&page=1 was collected."
    out = we.strip_inline_markup(s)
    assert "institution=" not in out and "?query" not in out
    assert "Data at" in out and "was collected." in out


def test_real_numbered_heading_at_line_start_preserved():
    # A REAL numbered header line must never lose its number.
    assert we.strip_inline_markup("## 2 Results") == "## 2 Results"


def test_welded_orphan_heading_mid_line_stripped():
    s = "Adoption grew. ## 2 firms invested."
    out = we.strip_inline_markup(s)
    assert "## 2" not in out
    assert "Adoption grew." in out and "firms invested." in out


def test_stray_emphasis_marker_stripped():
    s = "Productivity _** rose by 6%."
    out = we.strip_inline_markup(s)
    assert "_**" not in out
    assert "rose by 6%." in out


def test_inline_markup_off_is_byte_identical():
    os.environ["PG_INLINE_MARKUP_STRIP"] = "0"
    try:
        s = "Employment grew ](http://example.com/y) sharply."
        assert we.strip_inline_markup(s) == s
    finally:
        os.environ.pop("PG_INLINE_MARKUP_STRIP", None)


# ── D shell-source input screen (PG_SHELL_SOURCE_INPUT_SCREEN) ────────────────

def test_ev716_shape_shell_source_detected():
    # ev_716: a pure nav/search link-farm — bracketed empty-anchor links + search-query URLs, no finding.
    q = ("[](https://ilo.org/search/researchers?institution=41ILO_INST&query=*&page=1) "
         "[](https://ilo.org/search?q=*&page=2)")
    assert we.is_shell_source_quote(q) is True


def test_shell_narration_detected():
    assert we._is_shell_narration("The span consists of a repository collection link.") is True
    assert we._is_shell_narration("This is the search query for all results.") is True


def test_real_source_is_not_a_shell_fail_open():
    q = "Automation reduced employment by 0.42% across manufacturing firms in 2021."
    assert we.is_shell_source_quote(q) is False


def test_shell_source_held_out_of_substantive_units():
    q = ("[](https://ilo.org/search/researchers?institution=41ILO_INST&query=*&page=1) "
         "[](https://ilo.org/search?q=*&page=2) The span consists of a repository collection link.")
    assert we._substantive_units(q, is_junk=lambda _t: False) == []


def test_shell_screen_off_is_byte_identical():
    os.environ["PG_SHELL_SOURCE_INPUT_SCREEN"] = "0"
    try:
        assert we.is_shell_source_quote("[](x) [](y)") is False
    finally:
        os.environ.pop("PG_SHELL_SOURCE_INPUT_SCREEN", None)


# ── E evidence-base finding-signal preference (PG_EVIDENCE_BASE_FINDING_PREFERENCE) ──
# E is a §-1.3 DEMOTE to the low-relevance ledger (kept at weight), NEVER a drop. It routes an UNJUDGED
# marketing-only preamble (no finding signal) to the ledger; a judged-relevant row always wins first.

def test_marketing_only_preamble_predicate_fires_tru_aacsb():
    assert we._row_is_marketing_only_preamble("Thompson Rivers University's top 10 predictions for 2025") is True
    assert we._row_is_marketing_only_preamble("AACSB is leading the way in business education") is True


def test_finding_signal_span_is_not_marketing_preamble():
    assert we._row_is_marketing_only_preamble("Wages fell 0.42% in the manufacturing sector") is False


def test_unjudged_marketing_row_demoted_to_ledger():
    # Unjudged (no label, no numeric relevance) + on-topic + no finding signal => ledger (demote).
    row = {"direct_quote": "AACSB is leading the way in business education", "url": "https://aacsb.edu"}
    q_terms = we._placement_topic_terms("business education accreditation trends")
    assert we._row_routes_to_ledger(row, q_terms, we._ledger_relevance_floor()) is True


def test_judged_relevant_marketing_row_stays_in_body():
    # A positive judged relevance label ALWAYS wins — never demoted by E (rule 1 first).
    row = {
        "direct_quote": "AACSB is leading the way in business education",
        "content_relevance_label": "relevant",
    }
    q_terms = we._placement_topic_terms("business education accreditation trends")
    assert we._row_routes_to_ledger(row, q_terms, we._ledger_relevance_floor()) is False


def test_unjudged_finding_row_stays_in_body():
    row = {"direct_quote": "Enrollment in business programs rose 12% in 2024", "url": "https://x.edu"}
    q_terms = we._placement_topic_terms("business education accreditation trends")
    assert we._row_routes_to_ledger(row, q_terms, we._ledger_relevance_floor()) is False


def test_finding_preference_off_leg_disabled():
    os.environ["PG_EVIDENCE_BASE_FINDING_PREFERENCE"] = "0"
    try:
        assert we._row_is_marketing_only_preamble("AACSB is leading the way") is False
    finally:
        os.environ.pop("PG_EVIDENCE_BASE_FINDING_PREFERENCE", None)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
