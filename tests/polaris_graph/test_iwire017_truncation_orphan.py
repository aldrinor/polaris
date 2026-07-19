"""I-wire-017 (#1339) — behavioral self-tests for the 4 withhold-only render-seam / composer fixes.

All assertions run THE PRODUCTION predicates against the REAL drb_72 corpus
(``tests/fixtures/drb72/evidence_pool.json``); ``known_words`` is built via the production
``build_corpus_vocabulary_from_evidence``. No live calls; every helper is pure and withhold-only — the
faithfulness engine (strict_verify / NLI / 4-role / provenance / span) is untouched.

FIX A  — the truncation leg flags a LOWERCASE single-letter mid-word cut ("At t.[2]",
         "restricted to s.[89]") even though the bare letter is itself a known corpus token, while
         keeping legitimate single-CAPITAL label findings ("vitamin C [5]", "hepatitis B [8]",
         "grade B [12]") — the §-1.1-lethal precision cases.
FIX B  — ``_sanitize_report_line`` drops the orphaned continuation markers ([7][5]) left behind when
         the prose segment they continue is dropped as chrome; a marker run after a KEPT segment stays.
FIX C1 — ``sanitize_rendered_report`` drops a non-scaffolding ###-or-deeper section whose body
         collapsed to bare-citations-only, while preserving a scaffolding ### header.
FIX R1 — ``_compose_boilerplate_screen`` (the K-span PRODUCER path) now flags a truncated span it previously
         passed, once known_words + require_sentence_form are threaded in.
"""
from __future__ import annotations

import json
import pathlib

from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator import weighted_enrichment as we
from src.polaris_graph.generator import verified_compose as vc

_FIXTURE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "drb72" / "evidence_pool.json"
)


def _evidence_pool() -> list:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _known_words() -> "set[str]":
    return we.build_corpus_vocabulary_from_evidence(_evidence_pool())


# ── FIX A: single-letter truncation recall + capital-label precision ─────────
def test_fix_a_lowercase_single_letter_cut_is_flagged():
    """A LOWERCASE single-letter END boundary token before a [N] marker is a span cut — even though
    the bare letter is itself a known corpus token (the early-out that hid this is now bypassed)."""
    kw = _known_words()
    # Sanity: the bare letters ARE in the corpus, which is exactly what hid the cut pre-fix.
    assert "s" in kw and "t" in kw
    for line in ("the scope was restricted to s.[89]", "At t.[2]"):
        assert kf.is_truncated_fragment(
            line, kw, ends_before_marker=True, starts_after_marker=True
        ), f"FIX A recall: {line!r} should be flagged as a truncation cut"


def test_fix_a_capital_letter_labels_are_kept():
    """§-1.1-LETHAL precision: legitimate single-CAPITAL-letter label findings MUST be kept — the
    boundary token is uppercase, so the lowercase-gated single-letter cut never fires on them."""
    kw = _known_words()
    for line in ("vitamin C [5]", "hepatitis B [8]", "grade B [12]"):
        assert not kf.is_truncated_fragment(
            line, kw, ends_before_marker=True, starts_after_marker=True
        ), f"FIX A precision: {line!r} is a real capital-label finding and MUST be kept"


def test_fix_a_one_letter_english_words_are_kept():
    """The {"a","i"} keep-list still survives the new lowercase-single-letter cut branch."""
    kw = _known_words()
    for line in ("type 2 diabetes affects glucose a.[3]", "the model i.[7]"):
        assert not kf.is_truncated_fragment(
            line, kw, ends_before_marker=True, starts_after_marker=True
        ), f"FIX A precision: {line!r} ends in a legit one-letter word and MUST be kept"


def test_fix_a_fires_through_the_render_predicate():
    """The same recall fires through the SHIPPED render-seam predicate (known_words supplied)."""
    kw = _known_words()
    assert we.is_render_chrome_or_unrenderable("the scope was restricted to s", known_words=kw)
    assert we.is_render_chrome_or_unrenderable("At t", known_words=kw)


# ── FIX B: orphaned continuation markers dropped with their dropped claim ─────
def test_fix_b_orphaned_continuation_markers_dropped():
    """When a chrome prose segment is dropped, its trailing continuation markers ([7][5] after the
    dropped [6]) are dropped too — not left orphaned."""
    line = "Accept all cookies[6][7][5]"
    assert we.is_render_chrome_or_unrenderable("Accept all cookies")  # precondition: prose is chrome
    clean, dropped = we._sanitize_report_line(line, None)
    assert "[6]" not in clean and "[7]" not in clean and "[5]" not in clean
    assert clean.strip() == ""
    assert dropped == 3


def test_fix_b_markers_after_kept_prose_survive():
    """A marker-only run after a KEPT prose segment stays (it belongs to that kept claim)."""
    line = "Glucagon-like peptide-1 reduces appetite[6][7][5]"
    assert not we.is_render_chrome_or_unrenderable("Glucagon-like peptide-1 reduces appetite")
    clean, dropped = we._sanitize_report_line(line, None)
    assert "[6]" in clean and "[7]" in clean and "[5]" in clean
    assert dropped == 0


# ── FIX C1: empty content section dropped, scaffolding section kept ───────────
def test_fix_c1_empty_content_section_dropped_scaffolding_kept():
    report = (
        "# Research Report: test\n"
        "\n"
        "## Findings\n"
        "\n"
        "### Comparative Assessment\n"
        "\n"
        "Accept all cookies[6][7][5]\n"
        "\n"
        "### Real Section\n"
        "\n"
        "Glucagon-like peptide-1 reduces appetite[3].\n"
        "\n"
        "## Bibliography\n"
        "\n"
        "### Cookie Policy reference list\n"
        "[1] https://doi.org/10.1000/x\n"
    )
    clean, removed = we.sanitize_rendered_report(report, None)
    # The content-empty ### section header is gone.
    assert "Comparative Assessment" not in clean
    # A real ### section with claim prose survives.
    assert "### Real Section" in clean
    assert "Glucagon-like peptide-1 reduces appetite" in clean
    # A scaffolding ### header (under Bibliography) is NEVER dropped, even though its body has no
    # claim-bearing prose (it is a reference list).
    assert "Cookie Policy reference list" in clean
    assert "## Bibliography" in clean
    assert removed > 0


def test_fix_c1_top_level_headers_never_dropped():
    """A top-level (##) section with no claim prose is left for the operator — only ###-or-deeper
    content sections are dropped when emptied."""
    report = "# Research Report: t\n\n## Lonely Top Header\n\n[6][7]\n"
    clean, _removed = we.sanitize_rendered_report(report, None)
    assert "Lonely Top Header" in clean


# ── FIX R1: K-span producer now screens truncation it previously passed ──────
def test_fix_r1_kspan_screen_flags_previously_passed_truncation():
    """The K-span ``_compose_boilerplate_screen`` passed a mid-word-cut span before (no known_words / no
    require_sentence_form); with FIX R1's threaded args it now flags it."""
    kw = vc._known_words_for_compose(_evidence_pool())
    assert kw  # the producer builds a real allowlist from the pool
    frag = "developed by researchers and deployed in produc"  # 'produc' -> 'production' (cut)
    assert vc._compose_boilerplate_screen(frag) is False  # OLD inert behaviour (no args)
    assert vc._compose_boilerplate_screen(frag, kw, require_sentence_form=True) is True  # NEW: flagged


def test_fix_r1_real_whole_sentence_is_kept():
    """A real lifted source sentence is NOT screened out by the newly-active legs (precision)."""
    kw = vc._known_words_for_compose(_evidence_pool())
    real = (
        "Artificial intelligence systems can automate routine cognitive tasks "
        "across many industries."
    )
    assert vc._compose_boilerplate_screen(real, kw, require_sentence_form=True) is False
