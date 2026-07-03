"""I-deepfix-001 P1_chrome_gate (#1344) — the SEVEN box1 render-seam chrome CLASSES.

RED→GREEN behavioral proof for the P1_chrome_gate fix. Three nets share the ONE render predicate
``weighted_enrichment._contains_forensic_chrome`` (via ``is_render_chrome_or_unrenderable``): the
render-seam sanitize pass, the chrome canary, and the verified-compose K-span junk screen. Before
this fix all EIGHT shipped box1 chrome strings returned False from that predicate, so all three nets
failed together; the INDEPENDENT clean-room detector
(``scripts/iwire013_sec11_forensic_audit.chrome_flags``) was blind to the same classes; and an
all-chrome basket dropped to the insufficient-evidence disclosure SILENTLY.

This suite is fail-loud and proves the complete fix, faithfulness-NEUTRAL (page furniture is not a
corroborating source — suppressing it STRENGTHENS faithfulness and touches no strict_verify / NLI /
4-role / provenance verdict):

  (1) PRODUCTION PREDICATE — ``is_render_chrome_or_unrenderable`` is True for all 8 box1 chrome
      strings (one per class, class 3 in both its stats-table and surname-superscript forms) AND
      False for 5 real box1-family findings (the over-strip guard);
  (2) DEFAULT-ON KILL-SWITCH — with ``PG_RENDER_CHROME_SCREEN=0`` the 8 new-class strings revert to
      False (byte-identical to the legacy base screen), proving the new rules are the only thing
      that flags them;
  (3) DETECTOR MIRROR — the clean-room detector ``chrome_flags`` is non-empty for all 8 and empty
      for the 5 findings, by its OWN independent regexes (the module imports zero production
      predicates — shared code would be a shared blind spot);
  (4) PRECISION GUARDS — the risky surname-digit (rule 3b) and short-nav (rule 7) rules do NOT fire
      on real prose that superficially resembles them (a "Group1 versus Group2" clinical clause; a
      short sentence that carries a finite verb);
  (5) LOUD ALL-CHROME-BASKET CANARY — ``build_verified_span_draft`` returns None AND logs a WARNING
      when a basket's only verified span is all-chrome, and returns a real span with NO warning on a
      clean finding basket.

Pure offline unit test; no network, no model spend.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.weighted_enrichment import (
    is_render_chrome_or_unrenderable,
    sanitize_rendered_report,
)
from src.polaris_graph.generator.verified_compose import build_verified_span_draft

# The clean-room detector lives under scripts/ — import it the way the other CLI-script tests do.
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import iwire013_sec11_forensic_audit as detector  # noqa: E402


# The EIGHT shipped box1 chrome strings — one per class, class 3 in both its forms.
BOX1_CHROME = {
    "1_paywall_cta": (
        "Purchase this article to get instant access to the full text. Add to cart $42.00. "
        "Subscribe for unlimited access to the journal."
    ),
    "2_repo_license": (
        "Standard-Nutzungsbedingungen: Die Dokumente auf EconStor duerfen zu eigenen "
        "wissenschaftlichen Zwecken heruntergeladen werden."
    ),
    "3a_stats_table": (
        "Table 3 Variable Obs Mean Std. Dev. Min Max Employment 1879 0.42 0.11 0.01 0.98."
    ),
    "3b_surname_digit": (
        "Dennis Kanbach1 Louisa Heiduk2 Sascha Kraus3 Patrick Bican4 Alexander Brem5"
    ),
    "4_affiliation_address": (
        "*Corresponding author: Department of Economics, 50 Memorial Drive, Cambridge, MA 02142, "
        "United States."
    ),
    "5_exec_promo_bio": (
        "Jane Smith is the Chief Executive Officer and a visionary thought leader driving digital "
        "transformation across the enterprise."
    ),
    "6_metadata_recital": (
        "Smith, J. 2024. Automation and Work. Journal of Labor Economics, journal article, "
        "volume 42, article 7, authored by Jane Smith and John Doe."
    ),
    "7_short_nav_item": "Labor Market Trends 3.2",
}

# FIVE real box1-family findings — MUST survive (never flagged; the over-strip guard).
BOX1_FINDINGS = {
    "acemoglu_framework": (
        "Acemoglu and Restrepo's task-based framework shows automation displaces labor while "
        "reinstatement effects create new tasks."
    ),
    "autor_polarization": (
        "Autor documents employment polarization, with growth concentrated in high-wage and "
        "low-wage occupations."
    ),
    "robots_0_2pp": (
        "Each additional robot per thousand workers reduces the employment-to-population ratio by "
        "0.2 percentage points and wages by 0.42%."
    ),
    "frey_osborne_gaussian": (
        "Frey and Osborne apply a Gaussian process classifier to estimate that 47% of US jobs are "
        "at high risk of computerisation."
    ),
    "exposure_46pct": (
        "Around 46% of jobs face high exposure to generative AI, with over half their tasks "
        "affected in a complementary-software scenario."
    ),
}


# The Codex iter-1 OVER-STRIP adversarial set (rules 3b / 4 / 7). Each is a REAL terse finding that
# the iter-1 rules wrongly flagged as chrome; the iter-2 tightening (byline-pair structure for 3b,
# an affiliation co-signal for 4, a Title-Case-heading shape for 7) MUST keep every one of them.
BOX1_OVERSTRIP_ADVERSARIAL = {
    "3b_type2_terse": "Type2 diabetes exceeds Type1 diabetes",
    "3b_group1_terse": "Group1 mortality exceeded Group2",
    "3b_gpt_terse": "GPT4 outperforms GPT3",
    # Codex P1 iter-2: two-word entity-label findings ("Given Label<digit>" pairs) that the
    # byline-pair count wrongly read as an author list. The digit is welded to a finding LABEL
    # (Group / Stage), not an author surname — these MUST survive.
    "3b_treatment_group": "Treatment Group1 mortality exceeded Control Group2",
    "3b_stage_tumor": "Advanced Stage3 tumors exceeded Early Stage2 tumors",
    # Codex BLOCKER (rule 3b, open-ended label allowlist): REAL labor / economic TWO-CATEGORY findings
    # whose category labels (School / College / Collar) are NOT authorable in any finite allowlist — a
    # bare 2-pair count with NO author/affiliation co-signal must NEVER be read as a byline.
    "3b_labor_school_college": "High School1 Low College2 earnings differed",
    "3b_blue_white_collar": "Blue Collar1 White Collar2 wages diverged",
    # Codex iter-1 BLOCKER (rule 3b asterisk co-signal): the SAME real two-category / table findings
    # carrying a statistical / footnote SIGNIFICANCE STAR on ONE category label. A single '*' on a
    # category label is a footnote marker, NOT an author byline, so 2 pairs + 1 starred label must
    # NOT be read as an author list.
    "3b_starred_school_college": "High School1* Low College2 earnings differed",
    "3b_starred_blue_white_collar": "Blue Collar1* White Collar2 wages diverged",
    "3b_starred_group": "Group1* Group2 mortality differed",
    # Codex iter-2 BLOCKER (rule 3b two-starred category): BOTH category labels carry a significance /
    # footnote star. Two starred labels ("High School1* Low College2*") are BYTE-IDENTICAL to a starred
    # two-author byline, so the iter-1 ">=2 starred pairs" heuristic over-stripped these real findings.
    # The asterisk is no longer an author co-signal at all — the exactly-2-pair upgrade now needs an
    # INDEPENDENT author signal (affiliation keyword / "et al." / email). These MUST survive.
    "3b_two_starred_school_college": "High School1* Low College2* earnings differed",
    "3b_two_starred_blue_white_collar": "Blue Collar1* White Collar2* wages diverged",
    "3b_two_starred_group": "Group1* Group2* mortality differed",
    # A real finding that NAMES an institution and two numbered groups: 2 pairs + a "University"
    # co-signal, but its stopword density is above the floor, so it is a real clause, not a byline.
    "3b_institution_two_groups": "Researchers at Stanford University found Group1 and Group2 differed",
    "4_bare_city_zip": "Cambridge, MA 02142 saw unemployment rise last year",
    "4_zip_policy": "A housing policy targeting Palo Alto, CA 94301 cut vacancy sharply",
    "7_short_doubled": "Manufacturing exports doubled 2",
    "7_short_differed": "Robot adoption differed 3",
    "7_short_worsened": "Youth joblessness worsened 4",
}


# ---------------------------------------------------------------------------
# (1) PRODUCTION PREDICATE
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", list(BOX1_CHROME))
def test_production_predicate_flags_all_box1_chrome(key):
    text = BOX1_CHROME[key]
    assert is_render_chrome_or_unrenderable(text) is True, (
        f"P1_chrome_gate RED: production predicate blind to box1 chrome class {key!r}: {text!r}"
    )


@pytest.mark.parametrize("key", list(BOX1_FINDINGS))
def test_production_predicate_keeps_real_findings(key):
    text = BOX1_FINDINGS[key]
    assert is_render_chrome_or_unrenderable(text) is False, (
        f"P1_chrome_gate OVER-STRIP: production predicate wrongly flagged real finding {key!r}: {text!r}"
    )


# ---------------------------------------------------------------------------
# (2) DEFAULT-ON KILL-SWITCH (byte-identical revert)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("key", list(BOX1_CHROME))
def test_kill_switch_reverts_new_rules(key, monkeypatch):
    """With the render-chrome screen OFF the box1 classes revert to False — the new rules are the
    ONLY thing that flags them, and OFF is byte-identical to the legacy base screen."""
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", "0")
    assert is_render_chrome_or_unrenderable(BOX1_CHROME[key]) is False


# ---------------------------------------------------------------------------
# (3) DETECTOR MIRROR (clean-room, independent path)
# ---------------------------------------------------------------------------
def test_detector_imports_no_production_predicate():
    """The clean-room contract: the detector must NOT import the production chrome predicate — a
    shared import would re-introduce the shared blind spot the yardstick exists to catch. (The
    module DOCSTRING may name the predicates it refuses to import; only actual import / call
    statements are forbidden.)"""
    src = (_SCRIPTS_DIR / "iwire013_sec11_forensic_audit.py").read_text(encoding="utf-8")
    import_lines = [
        ln for ln in src.splitlines()
        if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
    ]
    for ln in import_lines:
        assert "weighted_enrichment" not in ln, f"detector must not import production code: {ln!r}"
        assert "key_findings" not in ln, f"detector must not import production code: {ln!r}"
    # no shared production chrome helper pulled in, and the production predicate is never CALLED
    assert "from src.polaris_graph.generator.weighted_enrichment import" not in src
    assert "_contains_p1_box1_chrome(" not in src  # not called from the detector
    assert "is_render_chrome_or_unrenderable(" not in src  # never invoked


@pytest.mark.parametrize("key", list(BOX1_CHROME))
def test_detector_flags_all_box1_chrome(key):
    flags = detector.chrome_flags(BOX1_CHROME[key])
    assert flags, (
        f"P1_chrome_gate RED: clean-room detector blind to box1 chrome class {key!r}: "
        f"{BOX1_CHROME[key]!r}"
    )


@pytest.mark.parametrize("key", list(BOX1_FINDINGS))
def test_detector_keeps_real_findings(key):
    flags = detector.chrome_flags(BOX1_FINDINGS[key])
    assert not flags, (
        f"P1_chrome_gate OVER-STRIP: clean-room detector wrongly flagged real finding {key!r}: "
        f"{flags}"
    )


# ---------------------------------------------------------------------------
# (4) PRECISION GUARDS for the two risky rules
# ---------------------------------------------------------------------------
def test_surname_digit_guard_keeps_clinical_group_prose():
    """Rule 3b (surname<digit>) must NOT fire on a real clinical clause that glues a digit to a
    group label but carries stopwords ('In Group1 versus Group2, patients improved')."""
    real = "In Group1 versus Group2, patients showed a marked improvement over the study period."
    assert is_render_chrome_or_unrenderable(real) is False
    assert not detector.chrome_flags(real)


def test_short_nav_guard_keeps_short_real_sentence():
    """Rule 7 (short nav stub) must NOT fire on a short sentence that carries a finite verb even
    when it ends in a number."""
    real = "Unemployment rose to 5"
    assert is_render_chrome_or_unrenderable(real) is False
    assert not detector.chrome_flags(real)


@pytest.mark.parametrize("key", list(BOX1_OVERSTRIP_ADVERSARIAL))
def test_iter2_overstrip_findings_survive_production(key):
    """Codex iter-1 OVER-STRIP (rules 3b/4/7): the tightened production predicate must KEEP each real
    terse finding (a byline-pair-less digit-glued clause; a bare City,ST ZIP with no affiliation
    co-signal; a short claim whose verb is outside any lexicon)."""
    text = BOX1_OVERSTRIP_ADVERSARIAL[key]
    assert is_render_chrome_or_unrenderable(text) is False, (
        f"P1_chrome_gate iter-2 OVER-STRIP: production predicate wrongly flagged real finding "
        f"{key!r}: {text!r}"
    )


@pytest.mark.parametrize("key", list(BOX1_OVERSTRIP_ADVERSARIAL))
def test_iter2_overstrip_findings_survive_detector(key):
    """The clean-room detector's tightened rules 3b/4/7 must ALSO keep each iter-1 over-strip
    finding — the independent yardstick tracks the same precision fix."""
    text = BOX1_OVERSTRIP_ADVERSARIAL[key]
    assert not detector.chrome_flags(text), (
        f"P1_chrome_gate iter-2 OVER-STRIP: clean-room detector wrongly flagged real finding "
        f"{key!r}: {detector.chrome_flags(text)}"
    )


# Codex BLOCKER (rule 3b): the tightened author-LIST structure must STILL fire on a genuine glued
# author byline — >=3 surname-digit pairs (incl. an OCR-mangled "Surname 2, Surname 1, First Last 2"
# spaced list), OR exactly 2 pairs PLUS an INDEPENDENT author/affiliation co-signal (affiliation
# keyword / "et al." / email) in the same low-stopword unit. NOTE: the superscript asterisk is no
# longer a co-signal (Codex iter-2 P1: it over-stripped two-starred category findings), so a bare-
# stars-only two-author byline is now an ACCEPTED LEAK — see ``BOX1_ACCEPTED_ASTERISK_LEAK`` below.
BOX1_GENUINE_AUTHOR_LIST = {
    "ocr_spaced_byline": "bALACHANDER 2, K valant 1, Jeremy Archbold 2",
    "two_author_etal": "Kanbach1 Heiduk2 et al.",
    "two_author_email": "Jane Smith1 John Doe2 jsmith@acme.edu",
    "two_author_affiliation": "Jane Smith1 John Doe2 Acme University",
    # A 3-name starred byline still fires via the >=3-pair path (asterisks irrelevant).
    "three_author_starred": "Jane Smith1* John Doe2* Amy Roe3*",
}

# Codex iter-2 ACCEPTED P2 LEAK: a bare two-author byline that carries ONLY corresponding-author
# asterisks and NO affiliation / email / "et al." is byte-identical to a two-starred category finding
# ("High School1* Low College2*"). Because over-stripping a real finding is the higher harm (§-1.3
# precision-first), the exactly-2-pair asterisk case now falls to KEEP: this leaked byline is not
# flagged. Codex classified this recall loss as P2, not a blocker. Pinned so the trade-off is explicit.
BOX1_ACCEPTED_ASTERISK_LEAK = {
    "two_author_asterisk_only": "Jane Smith1* John Doe2*",
}


@pytest.mark.parametrize("key", list(BOX1_GENUINE_AUTHOR_LIST))
def test_genuine_author_list_still_fires_production(key):
    """A genuine glued author byline (>=3 names, or 2 names + a co-signal) MUST still be flagged by
    the tightened production rule 3b — dropping the label allowlist must not blind it to real bylines."""
    text = BOX1_GENUINE_AUTHOR_LIST[key]
    assert is_render_chrome_or_unrenderable(text) is True, (
        f"P1_chrome_gate RED: tightened rule 3b blind to a genuine author byline {key!r}: {text!r}"
    )


@pytest.mark.parametrize("key", list(BOX1_GENUINE_AUTHOR_LIST))
def test_genuine_author_list_still_fires_detector(key):
    """The clean-room detector's tightened rule 3b must ALSO still fire on a genuine author byline —
    the independent yardstick tracks the same structure anchor."""
    text = BOX1_GENUINE_AUTHOR_LIST[key]
    assert detector.chrome_flags(text), (
        f"P1_chrome_gate RED: clean-room detector blind to a genuine author byline {key!r}: {text!r}"
    )


@pytest.mark.parametrize("key", list(BOX1_ACCEPTED_ASTERISK_LEAK))
def test_bare_asterisk_byline_is_accepted_leak_production(key):
    """Codex iter-2 P2: a bare-stars-only two-author byline (no affiliation/email/et-al) is now KEPT,
    NOT flagged — precision-first (§-1.3) treats a leaked byline as far lower harm than deleting a real
    two-starred category finding. Pinned so the accepted trade-off cannot silently regress."""
    text = BOX1_ACCEPTED_ASTERISK_LEAK[key]
    assert is_render_chrome_or_unrenderable(text) is False, (
        f"P1_chrome_gate iter-2: bare-stars byline {key!r} must be an accepted KEEP, not flagged: {text!r}"
    )
    assert not detector.chrome_flags(text), (
        f"P1_chrome_gate iter-2: clean-room detector must also KEEP the bare-stars byline {key!r}: {text!r}"
    )


# ---------------------------------------------------------------------------
# (6) HEADER-PATH KILL-SWITCH (Codex iter-1 P1 #1 + P2 test-gap)
# ---------------------------------------------------------------------------
# ``sanitize_rendered_report`` screens a non-scaffolding HEADER line by calling
# ``_contains_forensic_chrome(title)`` directly, bypassing ``is_render_chrome_or_unrenderable``.
# The iter-2 fix routes that call through ``render_chrome_screen_enabled()`` so ``PG_RENDER_CHROME_
# SCREEN=0`` reverts the header path too. The chrome header below is a glued author byline (box1
# rule 3b); the body is a real finding that must always survive.
_CHROME_HEADER_REPORT = (
    "## Dennis Kanbach1 Louisa Heiduk2 Sascha Kraus3 Patrick Bican4 Alexander Brem5\n"
    "\n"
    "Automation displaces routine labor while reinstatement effects create new tasks. [1]\n"
)


def test_header_path_drops_chrome_header_when_on():
    """DEFAULT-ON: a glued-author-byline HEADER is dropped and its real body is preserved."""
    out, removed = sanitize_rendered_report(_CHROME_HEADER_REPORT)
    assert removed >= 1
    assert "Kanbach1" not in out, "the glued-author-byline chrome header must be dropped when ON"
    assert "reinstatement effects create new tasks" in out, "the real body must always survive"


def test_header_path_kill_switch_off_preserves_header(monkeypatch):
    """Codex iter-1 P1 #1: with ``PG_RENDER_CHROME_SCREEN=0`` the header path reverts (byte-
    identical), so the box1 rules no longer drop the header — the kill-switch is now complete."""
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", "0")
    out, removed = sanitize_rendered_report(_CHROME_HEADER_REPORT)
    assert removed == 0, "the header path must honour PG_RENDER_CHROME_SCREEN=0 (kill-switch)"
    assert "Kanbach1" in out, "OFF must preserve the header (byte-identical to the legacy base screen)"


# ---------------------------------------------------------------------------
# (5) LOUD ALL-CHROME-BASKET CANARY (verified_compose.build_verified_span_draft)
# ---------------------------------------------------------------------------
def _member(evidence_id: str, direct_quote: str):
    return SimpleNamespace(
        evidence_id=evidence_id,
        direct_quote=direct_quote,
        span_verdict="SUPPORTS",
        credibility_weight=1.0,
    )


def _basket(members, subject="AI and labor market outcomes"):
    return SimpleNamespace(supporting_members=members, subject=subject, claim_text=subject)


def test_all_chrome_basket_drop_is_loud(caplog):
    """A basket whose only verified span is page-furniture chrome falls through to None — and now
    emits a LOUD warning canary so the drop is visible, not silent."""
    chrome_quote = (
        "Standard-Nutzungsbedingungen: Die Dokumente auf EconStor duerfen heruntergeladen werden."
    )
    eid = "ev_chrome_1"
    pool = {eid: {"direct_quote": chrome_quote}}
    basket = _basket([_member(eid, chrome_quote)])

    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.generator.verified_compose"):
        result = build_verified_span_draft(basket, pool)

    assert result is None, "an all-chrome basket must not compose a verified span"
    canary = [r for r in caplog.records if "P1_chrome_gate canary" in r.getMessage()]
    assert canary, "P1_chrome_gate RED: all-chrome-basket drop was SILENT (no canary warning)"
    assert "all-chrome-basket drop" in canary[0].getMessage()


def test_clean_finding_basket_composes_and_is_quiet(caplog):
    """A basket with a real verified finding span composes a real [#ev:] span AND logs no
    all-chrome canary — the fix does not fire on clean content."""
    finding_quote = (
        "Each additional robot per thousand workers reduces the employment-to-population ratio by "
        "0.2 percentage points."
    )
    eid = "ev_real_1"
    pool = {eid: {"direct_quote": finding_quote}}
    basket = _basket([_member(eid, finding_quote)])

    with caplog.at_level(logging.WARNING, logger="src.polaris_graph.generator.verified_compose"):
        result = build_verified_span_draft(basket, pool)

    assert result is not None and f"[#ev:{eid}:" in result
    canary = [r for r in caplog.records if "P1_chrome_gate canary" in r.getMessage()]
    assert not canary, "the canary must stay quiet on a clean finding basket"
