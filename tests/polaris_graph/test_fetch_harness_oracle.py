"""Offline unit tests for the fetch cited-content harness oracle
(I-deepfix-004 / Fable design 2026-07-09).

These are the ONLY offline part of the harness (the live network IS the rest of
the test). They exercise the HARNESS-OWNED oracle — squash / contains / the
INDEPENDENT front_matter_structural detector / the cross-work collision +
distinct-group screens / the per-class verdict — against the REAL banked span
heads named in the design doc. No network, no mocks, no production predicate.

The harness is loaded by file path (scripts/ is not a package); its heavy seam
and flag imports are lazy, so importing it here stays offline and cheap.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_HARNESS_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_cited_content_harness.py"
_spec = importlib.util.spec_from_file_location("fetch_cited_content_harness", _HARNESS_PATH)
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


# ── squash: survives PDF hyphen-breaks, diacritics, case, whitespace ────────
def test_squash_survives_pdf_hyphen_break():
    # A PDF line-wrap hyphenates "generative" and inserts a newline; squash must
    # reunite it so the fingerprint still matches the unbroken title form.
    assert h.squash("Gener-\native AI at Work") == "generativeaiatwork"
    assert h.squash("Generative AI at Work") == "generativeaiatwork"
    assert h.squash("gener-  ative  ai  at  work") == "generativeaiatwork"


def test_squash_strips_diacritics():
    # Czech + Icelandic diacritics fold to ASCII; the real Auspicia masthead and
    # the NBER author name must squash to their fingerprint stems.
    assert h.squash("Kováčová") == "kovacova"
    assert h.squash("Recenzovaný vědecký časopis") == "recenzovanyvedeckycasopis"
    assert h.squash("Brynjólfsson") == "brynjolfsson"


def test_squash_is_idempotent():
    for token in ("ailiteracy", "редакционнаяколлегия", "employmentoutlook2023"):
        assert h.squash(token) == token


def test_squash_preserves_cyrillic_letters_and_digits():
    assert h.squash("СОДЕРЖАНИЕ") == "содержание"
    assert h.squash("ISSN 2658-5286") == "issn26585286"
    assert h.squash("") == ""
    assert h.squash(None) == ""


# ── front_matter_structural: fires on real front matter, not on article prose ──
def test_front_matter_fires_on_editorial_board_masthead():
    # Real dgpu-class Russian journal masthead head.
    body = "РЕДАКЦИОННАЯ КОЛЛЕГИЯ\nГлавный редактор ... Заместитель главного редактора ..."
    assert h.front_matter_structural(body) is True


def test_front_matter_fires_on_dot_leader_toc():
    toc = (
        "Introduction ........... 5\n"
        "Methods ................. 12\n"
        "Results ................. 20\n"
        "Discussion .............. 28\n"
    )
    assert h.front_matter_structural(toc) is True


def test_front_matter_fires_on_table_of_contents_and_issn_masthead():
    assert h.front_matter_structural("Table of Contents\n1. First article ...") is True
    assert h.front_matter_structural("Editorial Board\nISSN 2658-5286\nEditor-in-Chief") is True


def test_front_matter_does_not_fire_on_lone_soderzhanie():
    # A lone "СОДЕРЖАНИЕ" (contents) heading must NOT trip the oracle — it is a
    # co-signal, not a standalone one (the production is_issue_front_matter needs
    # ISSN + vocab; the independent oracle drops содержание entirely).
    assert h.front_matter_structural("СОДЕРЖАНИЕ") is False
    assert h.front_matter_structural("Содержание") is False


def test_front_matter_does_not_fire_on_poultry_protein_prose():
    # Real poultry-article prose: "содержание белка" == "protein content". This is
    # the exact false-positive the design forbids.
    prose = (
        "Содержание белка в мясе птицепродуктов составляет важный показатель "
        "качества. Птицеводство обеспечивает высокое содержание белка."
    )
    assert h.front_matter_structural(prose) is False


def test_front_matter_does_not_fire_on_good_article_head():
    head = (
        "This paper studies AI literacy among workers and job posting behavior. "
        "We find generative AI at work shifts task composition substantially."
    )
    assert h.front_matter_structural(head) is False


def test_front_matter_editorial_board_needs_issn_cosignal():
    # "editorial board" alone (no ISSN) must not fire; two dot-leaders (< 3) must not fire.
    assert h.front_matter_structural("Editorial Board of the Society") is False
    assert h.front_matter_structural("A ...... 5\nB ...... 9") is False


# ── contains_any / contains_none semantics ──────────────────────────────────
def test_contains_any_and_none_semantics():
    sq = h.squash("Generative AI at Work by Erik Brynjolfsson")
    assert h.contains_any(sq, ["generativeaiatwork", "nomatch"]) is True
    assert h.contains_any(sq, ["nomatch"]) is False
    assert h.contains_any(sq, []) is True            # vacuous where no list
    assert h.contains_none(sq, ["reveliolabs"]) is True
    assert h.contains_none(sq, ["brynjolfsson"]) is False
    assert h.contains_none(sq, []) is True


# ── The 4 good-control fingerprints match their real source-form heads ──────
@pytest.mark.parametrize("name, natural_head, fingerprints", [
    ("good_arxiv_html",
     "This work measures AI literacy across the workforce.",
     ["ailiteracy"]),
    ("good_feds_note",
     "AI Adoption and Firms' Job Posting Behavior, FEDS Notes.",
     ["jobposting"]),
    ("good_oa_pdf_nber",
     "Generative AI at Work. Erik Brynjolfsson, Danielle Li, Lindsey Raymond.",
     ["generativeaiatwork", "brynjolfsson"]),
    ("good_oecd_fullreport",
     "Artificial intelligence and the labour market, by Stijn Broecke, "
     "OECD Employment Outlook 2023.",
     ["broecke", "employmentoutlook2023"]),
])
def test_good_control_fingerprints_match_source_form(name, natural_head, fingerprints):
    sq = h.squash(natural_head)
    assert h.contains_any(sq, fingerprints) is True, name
    # A good-control article head is NEVER front matter.
    assert h.front_matter_structural(natural_head) is False, name


def test_good_control_fingerprints_present_in_yaml():
    cases = {c["name"]: c for c in h.load_cases()}
    for name in h.GOOD_CONTROLS:
        assert name in cases, name
        assert cases[name]["expect"] == "article"
        assert cases[name]["contains_squashed"], name


# ── collision: 2 different DOIs sharing one squashed span => FAIL both ───────
def test_identical_span_collision_flags_two_dois_same_blob():
    # ev_664 & ev_700 today share the identical first-article head "физическое
    # развитие …" under TWO different DOIs (2 articles, 1 blob) — the 31x-dgpu
    # false-corroboration signature.
    shared = h.squash("Физическое развитие и физическая подготовленность студентов вузов")
    entries = [
        {"name": "dgpu_sport_managers", "work_id": "doi:a", "squashed_quote": shared, "eligible": True},
        {"name": "dgpu_poultry", "work_id": "doi:b", "squashed_quote": shared, "eligible": True},
    ]
    assert h.identical_span_collision(entries) == {"dgpu_sport_managers", "dgpu_poultry"}


def test_identical_span_collision_ignores_same_work_duplicate():
    shared = h.squash("Same article body cited twice under one DOI")
    entries = [
        {"name": "a", "work_id": "doi:same", "squashed_quote": shared, "eligible": True},
        {"name": "b", "work_id": "doi:same", "squashed_quote": shared, "eligible": True},
    ]
    assert h.identical_span_collision(entries) == set()


def test_identical_span_collision_ignores_unique_and_ineligible():
    entries = [
        {"name": "a", "work_id": "doi:a", "squashed_quote": "uniquea", "eligible": True},
        {"name": "b", "work_id": "doi:b", "squashed_quote": "uniqueb", "eligible": True},
        {"name": "c", "work_id": "doi:c", "squashed_quote": "shared", "eligible": False},
        {"name": "d", "work_id": "doi:d", "squashed_quote": "shared", "eligible": False},
    ]
    assert h.identical_span_collision(entries) == set()


def test_group_distinctness_violation_within_group():
    shared = h.squash("committee list marchenko dmytro editorial")
    entries = [
        {"name": "isg_2026", "group": "isg", "squashed_quote": shared, "eligible": True},
        {"name": "isg_2025", "group": "isg", "squashed_quote": shared, "eligible": True},
        {"name": "other", "group": "auspicia", "squashed_quote": "distinct", "eligible": True},
    ]
    assert h.group_distinctness_violations(entries) == {"isg_2026", "isg_2025"}


# ── per-class verdict ───────────────────────────────────────────────────────
def _case(expect, contains=None, not_contains=None, doi="", group=""):
    return {
        "name": "t", "url": "u", "expect": expect, "doi": doi, "group": group,
        "contains_squashed": [h.squash(x) for x in (contains or [])],
        "not_contains_squashed": [h.squash(x) for x in (not_contains or [])],
    }


def test_verdict_article_pass_and_fail():
    good = "AI literacy shapes how workers adopt generative tools. " * 6
    v, _ = h.verdict_for("article", good, {"failure_mode": ""}, _case("article", ["ailiteracy"]))
    assert v == h.PASS
    # Wrong span (fingerprint absent) but eligible => FAIL.
    wrong = "An unrelated body of text about weather patterns and rainfall. " * 6
    v2, _ = h.verdict_for("article", wrong, {"failure_mode": ""}, _case("article", ["ailiteracy"]))
    assert v2 == h.FAIL


def test_verdict_article_unreachable_on_fetch_failure():
    v, _ = h.verdict_for("article", "", {"failure_mode": "fetch_failed"}, _case("article", ["x"]))
    assert v == h.UNREACHABLE


def test_verdict_no_front_matter_pass_on_production_screen():
    v, _ = h.verdict_for(
        "no_front_matter_span", "",
        {"failure_mode": "wrong_content_front_matter"},
        _case("no_front_matter_span", not_contains=["редакционнаяколлегия"]),
    )
    assert v == h.PASS


def test_verdict_no_front_matter_fail_when_masthead_span_adopted():
    masthead = "РЕДАКЦИОННАЯ КОЛЛЕГИЯ главный редактор заместитель редакции журнала. " * 4
    v, checks = h.verdict_for(
        "no_front_matter_span", masthead, {"failure_mode": ""},
        _case("no_front_matter_span", not_contains=["редакционнаяколлегия"]),
    )
    assert v == h.FAIL
    assert checks["front_matter_structural"] is True
    assert checks["contains_none"] is False


def test_verdict_refused_pass_when_not_eligible():
    v, _ = h.verdict_for("refused", "short hub blurb", {"failure_mode": "fetch_shell"},
                         _case("refused"))
    assert v == h.PASS
    # A hub that leaked a full eligible body is a FAIL.
    big = "x" * 300
    v2, _ = h.verdict_for("refused", big, {"failure_mode": ""}, _case("refused"))
    assert v2 == h.FAIL


def test_verdict_recover_or_disclose_degrades_honestly():
    v, _ = h.verdict_for("recover_or_disclose", "", {"failure_mode": "paywall_shell"},
                         _case("recover_or_disclose", ["hartley"], ["suggestedcitation"]))
    assert v == h.DEGRADED_OK


# ── case set loads, is complete, and is well-formed ─────────────────────────
def test_case_set_loads_all_22_expected_classes():
    cases = h.load_cases()
    assert len(cases) == 22
    valid_classes = {
        "article", "article_or_degrade", "recover_or_disclose",
        "no_front_matter_span", "refused",
    }
    names = set()
    for c in cases:
        assert c["url"].startswith("http"), c["name"]
        assert c["expect"] in valid_classes, c["name"]
        assert c["name"] not in names, "duplicate case name"
        names.add(c["name"])
    # Class tallies per the design (A4 + B3 + C7 + D5 + E2 + F1).
    tally: dict[str, int] = {}
    for c in cases:
        tally[c["expect"]] = tally.get(c["expect"], 0) + 1
    assert tally["article"] == 7            # 4 good controls + 3 combined-PDF
    assert tally["no_front_matter_span"] == 7
    assert tally["refused"] == 5
    assert tally["recover_or_disclose"] == 2
    assert tally["article_or_degrade"] == 1
