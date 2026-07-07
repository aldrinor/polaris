"""FIX (I-deepfix-001, GH #1344, drb_72 live-run forensic): the PURE content-shell
predicate ``_is_content_shell``.

DISTINCT from ``_is_citation_metadata_shell`` (which catches BibTeX/EndNote EXPORT
widgets + episode-nav stubs — a citation-metadata class). This catches a 200-OK
fetch whose WHOLE extracted body is boilerplate with ZERO citable article prose:

  * an ACM download-WAIT interstitial ("Export Citations ... No abstract
    available. Download PDFs. Please wait while we prepare your download..."), or
  * a Georgia State site-NAV menu ("[Alumni] [Faculty & Staff] javascript:void(0)").

A smart composer CANNOT extract a signal from a page with no signal, so the
source silently occupies a corpus slot and delivers zero citable content = a
COVERAGE loss. ``classify_block_page``, ``_is_landing_or_abstract_page`` AND
``_is_citation_metadata_shell`` are all blind to this class.

RED-then-GREEN: on the pre-fix branch the symbols ``_is_content_shell`` and
``_content_shell_refetch_enabled`` do not exist, so this module fails at import
(collection error = RED). After the fix it imports and every assertion below
passes (GREEN).

The predicate must:
  * flag the ACM download-wait body + the ACM no-abstract/download co-occurrence
    body + the GSU nav-menu body True,
  * flag a real full-text labor-market article (3000+ chars) False, protected by
    the short-body gate,
  * flag a real short article carrying a couple of nav links but genuine prose
    False, protected by the prose-sentence guard,
  * only DOWN-WEIGHT (never a hard drop); the master flag ``PG_CONTENT_SHELL_REFETCH``
    is default-OFF so the OFF path is byte-identical (predicate never acted on).

Import is NARROW (only the two pure predicate symbols) so the module loads
offline without pulling model / network dependencies — mirrors the sibling
``test_live_retriever_citation_metadata_shell``.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.live_retriever import (
    _content_shell_refetch_enabled,
    _is_content_shell,
)

# ── The REAL content shells (must flag True) ──────────────────────────────────

# 1. ACM download-preparation interstitial — the visible body is a "please wait"
#    download page carrying no article text. Trips sub-signal 1 (the exact
#    'please wait while we prepare your download' phrase).
_ACM_DOWNLOAD_WAIT_SHELL = (
    "Export Citations\n"
    "No abstract available.\n"
    "Download PDFs\n"
    "Please wait while we prepare your download...\n"
)

# 2. ACM no-abstract + download page WITHOUT the 'please wait' phrase — trips
#    sub-signal 1 via the co-occurrence of 'download pdfs' AND 'no abstract
#    available' in the head window.
_ACM_NO_ABSTRACT_DOWNLOAD_SHELL = (
    "Export Citations\n"
    "No abstract available.\n"
    "Download PDFs.\n"
    "Get Access. Sign in to your account.\n"
)

# 3. Georgia State site-NAV menu — the visible body is a nav-link menu with a
#    javascript:void(0) anchor and no article prose. Trips sub-signal 2.
_GSU_NAV_MENU_SHELL = (
    "[Alumni] [Faculty & Staff] [Current Students] [Prospective Students]\n"
    "[Give] [Apply] [Visit]\n"
    "javascript:void(0)\n"
    "Home About Academics Admissions\n"
    "Search this site\n"
)

_REAL_CONTENT_SHELLS = {
    "acm_download_wait": _ACM_DOWNLOAD_WAIT_SHELL,
    "acm_no_abstract_download": _ACM_NO_ABSTRACT_DOWNLOAD_SHELL,
    "gsu_nav_menu": _GSU_NAV_MENU_SHELL,
}


# ── FALSE-positive guards ─────────────────────────────────────────────────────

# A genuine 3000+ char labor-economics article. It merely mentions "download"
# and carries a top-of-page breadcrumb, but is real full text. The short-body
# gate keeps it OFF the shell path — its real prose must ground claims.
_REAL_FULLTEXT_LABOR_ARTICLE = (
    "[Home] [Research] Automation and the Future of the Labor Market\n\n"
    + (
        "We estimate the exposure of occupations to recent advances in machine "
        "learning using a task-based framework. Across 702 occupations we find "
        "that roughly 47 percent of total US employment is in a high-risk "
        "category, meaning associated jobs are potentially automatable over an "
        "unspecified number of years, perhaps a decade or two. Wages and "
        "educational attainment exhibit a strong negative relationship with an "
        "occupation's probability of computerisation. Readers may download the "
        "full dataset from the supplementary appendix. "
    ) * 14
)

# A real SHORT article (< 3000 chars) that carries a small breadcrumb nav plus
# genuine prose sentences. The prose-sentence guard keeps it OFF the nav path
# even though it has a couple of bracketed links.
_REAL_SHORT_ARTICLE_WITH_NAV = (
    "[Home] [Articles]\n"
    "The labor-market study found that 47 percent of examined occupations face "
    "substantial automation risk over the next two decades. Wages correlate "
    "negatively with the estimated probability of computerisation across the "
    "702 occupations analysed in the national sample. The authors caution that "
    "the timeline for adoption remains highly uncertain.\n"
)


@pytest.mark.parametrize("name,body", list(_REAL_CONTENT_SHELLS.items()))
def test_real_content_shells_flag_true(name, body):
    """Each real download-wait / nav-menu content shell is detected."""
    assert _is_content_shell(body) is True, name


def test_fulltext_labor_article_flags_false():
    """A real 3000+ char full-text article that mentions 'download' and carries a
    breadcrumb is NEVER flagged — the short-body gate protects it."""
    assert len(_REAL_FULLTEXT_LABOR_ARTICLE) > 3000
    assert _is_content_shell(_REAL_FULLTEXT_LABOR_ARTICLE) is False


def test_short_article_with_nav_flags_false():
    """A real SHORT article carrying a couple of nav links but genuine prose is
    NOT flagged — the prose-sentence guard is the high-precision protection."""
    assert len(_REAL_SHORT_ARTICLE_WITH_NAV) < 3000
    assert _is_content_shell(_REAL_SHORT_ARTICLE_WITH_NAV) is False


def test_short_body_without_markers_flags_false():
    """A short prose body with no download/nav markers is not a content shell."""
    prose = "Tirzepatide reduced HbA1c by 2.1 percent versus placebo in SURPASS-2."
    assert _is_content_shell(prose) is False


def test_empty_body_flags_false():
    assert _is_content_shell("") is False
    assert _is_content_shell("   \n  ") is False


def test_long_body_with_download_marker_flags_false():
    """The short-body gate is the PRIMARY guard: a > 3000-char body carrying the
    'please wait' phrase in its head is NOT a shell (a real article whose page
    footer renders a download widget)."""
    para = (
        "We estimate the exposure of occupations to machine learning using a "
        "task-based framework. Across 702 occupations we find roughly 47 percent "
        "of US employment is in a high-risk category. "
    )
    long_body = "Please wait while we prepare your download... " + para * 18
    assert len(long_body) > 3000
    assert _is_content_shell(long_body) is False


def test_short_body_gate_env_tunable(monkeypatch):
    """Lowering PG_LANDING_PAGE_MAX_CHARS below the shell length turns the flag
    OFF — confirms the gate reuses that knob at CALL time (LAW VI)."""
    shell = _ACM_DOWNLOAD_WAIT_SHELL
    assert _is_content_shell(shell) is True
    monkeypatch.setenv("PG_LANDING_PAGE_MAX_CHARS", "10")
    assert _is_content_shell(shell) is False


def test_head_window_gate(monkeypatch):
    """A download marker buried PAST the head window is not scanned (mirrors the
    landing/citation predicates' head-only scan)."""
    body = ("x" * 60) + " please wait while we prepare your download "
    monkeypatch.setenv("PG_CONTENT_SHELL_HEAD_CHARS", "10")
    assert _is_content_shell(body) is False
    monkeypatch.delenv("PG_CONTENT_SHELL_HEAD_CHARS", raising=False)
    assert _is_content_shell(body) is True


def test_nav_link_min_env_tunable(monkeypatch):
    """Raising PG_NAV_SHELL_MIN_LINKS above the shell's link count turns the nav
    sub-signal OFF — confirms the threshold is read at CALL time (LAW VI)."""
    shell = _GSU_NAV_MENU_SHELL
    assert _is_content_shell(shell) is True
    monkeypatch.setenv("PG_NAV_SHELL_MIN_LINKS", "999")
    assert _is_content_shell(shell) is False


def test_master_flag_default_off(monkeypatch):
    """PG_CONTENT_SHELL_REFETCH unset => the caller never acts on the signal
    (OFF path byte-identical)."""
    monkeypatch.delenv("PG_CONTENT_SHELL_REFETCH", raising=False)
    assert _content_shell_refetch_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "on", "yes", "TRUE", "On"])
def test_master_flag_truthy_values_on(monkeypatch, raw):
    monkeypatch.setenv("PG_CONTENT_SHELL_REFETCH", raw)
    assert _content_shell_refetch_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "off", "no", "", "garbage"])
def test_master_flag_falsey_values_off(monkeypatch, raw):
    monkeypatch.setenv("PG_CONTENT_SHELL_REFETCH", raw)
    assert _content_shell_refetch_enabled() is False
