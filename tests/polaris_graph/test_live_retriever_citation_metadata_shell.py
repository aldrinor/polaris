"""FIX 2 (I-deepfix-001 composition-collapse plan, GH #1344): the extraction
"citation-metadata shell" predicate ``_is_citation_metadata_shell``.

A 200-OK fetch whose visible body is a citation-EXPORT widget (Frey-Osborne
ora.ox.ac.uk "[BibTeX][EndNote]"), site/episode NAVIGATION (youreverydayai), or
a bare title followed by a raw "@article{...}" BibTeX entry (a Semantic-Scholar
record stub) carries NO article prose. It was captured VERBATIM as the grounding
span, starving otherwise-clean baskets. ``classify_block_page`` and
``_is_landing_or_abstract_page`` are both blind to this class.

RED-then-GREEN: on the pre-fix branch the symbol ``_is_citation_metadata_shell``
does not exist, so this module fails at import (collection error = RED). After
the fix it imports and every assertion below passes (GREEN).

The predicate must:
  * flag the 3 real shells True,
  * flag a real full-text labor-econ article that quotes a BibTeX block in its
    references False (protected by the short-body gate — a real article is well
    over ``PG_LANDING_PAGE_MAX_CHARS``),
  * only DOWN-WEIGHT (never a hard drop) — the master flag is default-OFF so the
    OFF path is byte-identical.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.live_retriever import (
    _citation_shell_refetch_enabled,
    _is_citation_metadata_shell,
)

# ── The 3 REAL shells (must flag True) ────────────────────────────────────────

# 1. Frey-Osborne "The Future of Employment" record on ora.ox.ac.uk — the visible
#    body is a citation-export widget, not the article.
_FREY_OSBORNE_BIBTEX_SHELL = (
    "The Future of Employment: How Susceptible Are Jobs to Computerisation?\n"
    "Carl Benedikt Frey, Michael A. Osborne\n"
    "Cite this record\n"
    "[BibTeX] [EndNote] [RIS] [DataCite]\n"
    "Export citation\n"
)

# 2. youreverydayai podcast page — the visible body is site/episode navigation.
_YOUREVERYDAYAI_EPISODE_NAV_SHELL = (
    "Everyday AI Podcast — An AI Podcast\n"
    "Episode Categories: AI News, Prompt Engineering, Careers\n"
    "Related Episodes: How to use ChatGPT at work, Prompt tips\n"
    "Join the discussion in our free daily newsletter\n"
    "Subscribe · Share · Download\n"
)

# 3. Semantic-Scholar record stub — a bare title followed by a raw BibTeX entry.
_SEMANTICSCHOLAR_TITLE_BIBTEX_SHELL = (
    "Generative AI and the Future of Work\n"
    "@article{smith2024genai,\n"
    "  title={Generative AI and the Future of Work},\n"
    "  author={Smith, Jane and Doe, John},\n"
    "  journal={Journal of Labor Economics},\n"
    "  year={2024}\n"
    "}\n"
)

_REAL_SHELLS = {
    "frey_osborne_bibtex": _FREY_OSBORNE_BIBTEX_SHELL,
    "youreverydayai_episode_nav": _YOUREVERYDAYAI_EPISODE_NAV_SHELL,
    "semanticscholar_title_bibtex": _SEMANTICSCHOLAR_TITLE_BIBTEX_SHELL,
}


# ── The FALSE-positive guard: a real full-text article citing BibTeX ───────────
# A genuine labor-economics article whose References section quotes a BibTeX
# block. The body is well over PG_LANDING_PAGE_MAX_CHARS (3000), so the
# short-body gate keeps it OFF the shell path — its real prose must ground claims.
_REAL_FULLTEXT_ARTICLE_CITING_BIBTEX = (
    "Automation and the Future of the Labor Market\n\n"
    + (
        "We estimate the exposure of occupations to recent advances in machine "
        "learning using a task-based framework. Across 702 occupations we find "
        "that roughly 47 percent of total US employment is in a high-risk "
        "category, meaning associated jobs are potentially automatable over an "
        "unspecified number of years, perhaps a decade or two. Wages and "
        "educational attainment exhibit a strong negative relationship with an "
        "occupation's probability of computerisation. "
    ) * 12
    + "\n\nReferences\n"
    + "Frey, C. B., & Osborne, M. A. (2017). The future of employment.\n"
    + "@article{frey2017future, title={The future of employment}, "
    + "author={Frey, Carl and Osborne, Michael}, year={2017}}\n"
)


@pytest.mark.parametrize("name,body", list(_REAL_SHELLS.items()))
def test_real_shells_flag_true(name, body):
    """Each of the 3 real citation-metadata shells is detected."""
    assert _is_citation_metadata_shell(body) is True, name


def test_full_text_article_citing_bibtex_flags_false():
    """A real full-text article that merely quotes BibTeX in its references is
    NEVER flagged — the short-body gate protects it (body > 3000 chars)."""
    assert len(_REAL_FULLTEXT_ARTICLE_CITING_BIBTEX) > 3000
    assert _is_citation_metadata_shell(_REAL_FULLTEXT_ARTICLE_CITING_BIBTEX) is False


def test_long_body_with_head_marker_flags_false():
    """The short-body gate is the PRIMARY guard: a > 3000-char body is not a
    shell even when a [BibTeX] marker sits in the head window. This is the exact
    protection for a full-text article whose export widget renders inline."""
    para = (
        "We estimate the exposure of occupations to machine learning using a "
        "task-based framework. Across 702 occupations we find roughly 47 percent "
        "of US employment is in a high-risk category. "
    )
    long_body = "[BibTeX] export available. " + para * 18
    assert len(long_body) > 3000
    assert _is_citation_metadata_shell(long_body) is False


def test_short_body_without_marker_flags_false():
    """A short body carrying no export/nav/BibTeX marker is not a shell."""
    prose = "Tirzepatide reduced HbA1c by 2.1 percent versus placebo in SURPASS-2."
    assert _is_citation_metadata_shell(prose) is False


def test_empty_body_flags_false():
    assert _is_citation_metadata_shell("") is False
    assert _is_citation_metadata_shell("   \n  ") is False


def test_head_window_gate(monkeypatch):
    """A marker buried PAST the head window is not scanned (mirrors the landing
    predicate's head-only scan). With a tiny head window the leading-prose shell
    body no longer trips."""
    body = ("x" * 40) + " [BibTeX] "  # marker sits after char 40
    monkeypatch.setenv("PG_CITATION_SHELL_HEAD_CHARS", "10")
    assert _is_citation_metadata_shell(body) is False
    monkeypatch.delenv("PG_CITATION_SHELL_HEAD_CHARS", raising=False)
    assert _is_citation_metadata_shell(body) is True


def test_short_body_gate_env_tunable(monkeypatch):
    """Lowering PG_LANDING_PAGE_MAX_CHARS below the shell length turns the flag
    OFF — confirms the gate reuses that knob at CALL time (LAW VI)."""
    shell = _FREY_OSBORNE_BIBTEX_SHELL
    assert _is_citation_metadata_shell(shell) is True
    monkeypatch.setenv("PG_LANDING_PAGE_MAX_CHARS", "10")
    assert _is_citation_metadata_shell(shell) is False


def test_master_flag_default_off(monkeypatch):
    """PG_CITATION_SHELL_REFETCH unset => the caller never acts on the signal
    (OFF path byte-identical)."""
    monkeypatch.delenv("PG_CITATION_SHELL_REFETCH", raising=False)
    assert _citation_shell_refetch_enabled() is False


@pytest.mark.parametrize("raw", ["1", "true", "on", "yes", "TRUE", "On"])
def test_master_flag_truthy_values_on(monkeypatch, raw):
    monkeypatch.setenv("PG_CITATION_SHELL_REFETCH", raw)
    assert _citation_shell_refetch_enabled() is True


@pytest.mark.parametrize("raw", ["0", "false", "off", "no", "", "garbage"])
def test_master_flag_falsey_values_off(monkeypatch, raw):
    monkeypatch.setenv("PG_CITATION_SHELL_REFETCH", raw)
    assert _citation_shell_refetch_enabled() is False
