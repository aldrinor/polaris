"""I-wire-013 (#1327): tests for the INDEPENDENT §-1.1 forensic render-audit.

Proves the clean-room detector FLAGS crafted chrome + truncation units and does NOT flag a clean,
grounded finding — i.e. it has the recall the blind production predicate lacks AND the precision a
naive "unknown word -> cut" rule lacks. Fully offline; no production predicate is imported by the
detector under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.iwire013_sec11_forensic_audit import (
    build_known_words,
    chrome_flags,
    contradiction_noise,
    enumerate_units,
    main,
    run_audit,
    truncation_flag,
    _Unit,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "iwire013_forensic"
_REPORT = _FIXTURE / "dirty_report.md"

# A compact known-word basis for the function-level truncation tests (mirrors what
# build_known_words derives from evidence_pool.json — the completions of the crafted cuts).
_KNOWN = {
    "research", "local", "methodology", "labor", "demand", "occupations", "productivity",
    "share", "automation", "disadvantaged",
}


# ---------------------------------------------------------------------------
# chrome — containment rules FLAG furniture, leave a clean finding alone
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text, expected_category", [
    ("Jane Kanbach1,2 · Louisa Heiduk1 · John Doe3 ORCID 0000-0002-1825-0097.", "author_meta"),
    ("Received: 31 May 2023 / Accepted: 1 June 2023 / Published online: 5 June 2023.", "author_meta"),
    ("This is an open access article distributed under the Creative Commons Attribution License.", "license"),
    ("1 Introduction 1.1 Research background to the study 1.2 Research methods", "glued_header_toc"),
    ("# A Fourth Industrial Revolution ## Dennis Zami Atibuni Abstract This article", "glued_header_toc"),
    ("please refresh the page or clear your browser cache and try again", "browser_ui"),
    ("DOI:10.5772/18850 ISSN 1234-5678 Crossref reports the following articles citing this article", "biblio_junk"),
    ("ما هو تأثير الذكاء الاصطناعي على سوق العمل", "nonlatin_scrape"),
])
def test_chrome_flags_fire_on_furniture(text, expected_category):
    flags = chrome_flags(text)
    assert expected_category in flags, f"{expected_category!r} not in {flags!r} for {text!r}"


def test_chrome_does_not_flag_clean_grounded_finding():
    clean = (
        "Automation complements labor and raises productivity in many occupations, "
        "shifting the task content of production toward higher-value work."
    )
    assert chrome_flags(clean) == []


# ---------------------------------------------------------------------------
# truncation — span cut at the [N] boundary; clean word does NOT flag
# ---------------------------------------------------------------------------
def test_truncation_flags_end_cut():
    u = _Unit("section", "A novel methodology to estimate the probability within loc",
              ends_before_marker=True)
    assert truncation_flag(u, _KNOWN) == "end-cut:'loc'"


def test_truncation_flags_short_end_cut():
    u = _Unit("key_finding", "Overall the scope was restricted to s", ends_before_marker=True)
    assert truncation_flag(u, _KNOWN) == "end-cut:'s'"


def test_truncation_flags_start_cut():
    u = _Unit("section", "hodology to estimate the probability of computerisation",
              starts_after_marker=True)
    assert truncation_flag(u, _KNOWN) == "start-cut:'hodology'"


def test_truncation_does_not_flag_clean_finding():
    # "...labor demand." (advisor canary): a complete sentence ending in a known word.
    u = _Unit("key_finding", "Automation raises the labor share and labor demand",
              ends_before_marker=True, starts_after_marker=False)
    assert truncation_flag(u, _KNOWN) is None


def test_truncation_inflection_guard_keeps_real_base_word():
    # "disadvantage" is a real base word whose only longer completion is the inflection
    # "disadvantaged" -> must NOT be flagged as a cut (the precision guard).
    u = _Unit("section", "this places second-language speakers at a significant disadvantage",
              ends_before_marker=True)
    assert truncation_flag(u, _KNOWN) is None


def test_truncation_uppercase_start_is_not_a_cut():
    # An uppercase leading token after a citation is a legitimate new sentence, not a cut.
    u = _Unit("section", "Population: US labor markets across many occupations",
              starts_after_marker=True)
    assert truncation_flag(u, _KNOWN) is None


# ---------------------------------------------------------------------------
# contradiction-noise — possible_metric_mismatch rows counted + classified
# ---------------------------------------------------------------------------
def test_contradiction_noise_counts_pmm_row():
    report_text = _REPORT.read_text(encoding="utf-8")
    res = contradiction_noise(_FIXTURE / "contradictions.json", report_text)
    assert res["validated"] is True
    assert res["count"] >= 1
    assert res["pmm_rows"] == 1
    assert any("year-as-metric" in ex for ex in res["examples"])


def test_contradiction_noise_absent_input_is_not_validated():
    res = contradiction_noise(None, "no contradictions section here")
    assert res["validated"] is False


# ---------------------------------------------------------------------------
# end-to-end on the fixture: dirty report FAILS all three; absent input FAILS for coverage
# ---------------------------------------------------------------------------
def test_known_words_built_from_fixture_evidence_pool():
    known, chars = build_known_words(_FIXTURE, floor=5)
    assert chars > 0
    for w in ("research", "local", "methodology", "labor", "demand", "occupations"):
        assert w in known


def test_run_audit_on_dirty_fixture_detects_all_three():
    report_text = _REPORT.read_text(encoding="utf-8")
    known, chars = build_known_words(_FIXTURE, floor=5)
    audit = run_audit(report_text, _FIXTURE, known, chars, _FIXTURE / "contradictions.json")
    assert audit["chrome"]["count"] >= 4          # author, license, glued-ToC, browser, foreign
    assert audit["truncation"]["count"] >= 3      # Resea, s, loc, hodology
    assert audit["truncation"]["validated"] is True
    assert audit["contradiction"]["count"] >= 1
    # the clean grounded section unit is NOT among the flagged units
    flagged = {u.text for u in audit["chrome"]["units"]} | {u.text for u in audit["truncation"]["units"]}
    assert not any("complements labor and raises productivity" in t for t in flagged)


def test_main_returns_fail_on_dirty_fixture(capsys):
    rc = main(["--report", str(_REPORT)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "OVERALL: FAIL" in out


def test_main_absent_report_fails_for_coverage(tmp_path, capsys):
    rc = main(["--report", str(tmp_path / "does_not_exist.md")])
    assert rc == 2  # absent input -> non-zero exit (SKIPPED == FAIL-for-coverage)
    out = capsys.readouterr().out
    assert "SKIPPED" in out


def test_enumerate_units_audits_glued_chrome_header_as_a_unit():
    # A glued-chrome header line must be audited as its own unit, not swallowed as a section title.
    report = "### A Fourth Industrial Revolution ## Dennis Zami Atibuni Abstract This article\n\nbody.[1]\n"
    units = enumerate_units(report)
    header_units = [u for u in units if u.category == "header"]
    assert any(chrome_flags(u.text) for u in header_units)
