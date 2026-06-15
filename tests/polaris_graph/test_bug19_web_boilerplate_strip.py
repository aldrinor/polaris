"""BUG-19 (GH #1262) unit tests: allowlist-only web-boilerplate hygiene.

Proves the two reusable INPUT-HYGIENE helpers added to
``src/tools/access_bypass.py``:

  • ``strip_web_boilerplate(text)`` removes ONLY confirmed crawl-chrome
    marker lines ("URL Source:", "Markdown Content:", "Title:" headers,
    "Split View", "Cite Cite", "Views", "Download full text from
    publisher", "References listed on IDEAS", cookie-consent banners) and
    leaves real prose — including legitimate multilingual content —
    byte-for-byte untouched.

  • ``is_boilerplate_or_nonassertional(sentence)`` flags pure metadata /
    nav chrome / bare DOI / table-number rows / error-page stubs (the
    literal NTSB "Page not found" / "404 Not Found" body that previously
    self-entailed through the faithfulness gate) and returns False for any
    real assertional sentence.

REGRESSION (the old bug): a pure error page trivially entails itself, so a
literal "Page not found" 404 body was extracted as a finding and judged
ENTAILED by the gate. The helper flags it BEFORE finding extraction so it
never reaches the gate. These are pure unit tests — no network, no
backends. The helpers are INPUT hygiene only; the strict_verify / NLI /
4-role / span-grounding gates are untouched (faithfulness is not relaxed).
"""

from __future__ import annotations

import pytest

from src.tools.access_bypass import (
    is_boilerplate_or_nonassertional,
    strip_web_boilerplate,
)


# ---------------------------------------------------------------------------
# strip_web_boilerplate: removes ONLY allowlisted crawl-chrome lines
# ---------------------------------------------------------------------------


def test_strip_removes_url_source_and_markdown_content_headers() -> None:
    raw = (
        "URL Source: https://example.org/article\n"
        "Markdown Content:\n"
        "Title: Real Article Title\n"
        "Mortality fell to 12.4% in the treatment arm.\n"
    )
    cleaned = strip_web_boilerplate(raw)
    assert "URL Source:" not in cleaned
    assert "Markdown Content:" not in cleaned
    assert "Title:" not in cleaned
    # The real prose sentence survives byte-for-byte.
    assert "Mortality fell to 12.4% in the treatment arm." in cleaned


def test_strip_removes_ideas_repec_and_cookie_chrome() -> None:
    raw = (
        "Split View\n"
        "Cite Cite\n"
        "Views\n"
        "Download full text from publisher\n"
        "References listed on IDEAS\n"
        "This website uses cookies to improve your experience.\n"
        "Accept Cookies\n"
        "The intervention reduced relapse by 30%.\n"
    )
    cleaned = strip_web_boilerplate(raw)
    for marker in (
        "Split View",
        "Cite Cite",
        "Download full text from publisher",
        "References listed on IDEAS",
        "uses cookies",
        "Accept Cookies",
    ):
        assert marker not in cleaned, f"chrome not stripped: {marker!r}"
    assert "The intervention reduced relapse by 30%." in cleaned


def test_strip_is_byte_safe_for_real_prose() -> None:
    """A whole document of real sentences must come back identical (modulo
    surrounding whitespace) — no marker word matched mid-sentence."""
    prose = (
        "The title of the study was registered before enrollment.\n"
        "Source data were available on request.\n"
        "Cookies were administered as a placebo control in the trial.\n"
    )
    cleaned = strip_web_boilerplate(prose)
    # 'title', 'source', 'cookies' appear mid-sentence — must NOT be stripped
    # because the patterns are whole-line anchored.
    assert cleaned == prose.strip()


def test_strip_preserves_multilingual_content() -> None:
    raw = (
        "URL Source: https://example.fr/a\n"
        "La mortalité a chuté de 12,4 % dans le groupe traité.\n"
        "死亡率は治療群で12.4%低下した。\n"
    )
    cleaned = strip_web_boilerplate(raw)
    assert "URL Source:" not in cleaned
    assert "La mortalité a chuté de 12,4 % dans le groupe traité." in cleaned
    assert "死亡率は治療群で12.4%低下した。" in cleaned


def test_strip_handles_empty_and_none_like() -> None:
    assert strip_web_boilerplate("") == ""
    assert strip_web_boilerplate("   ") == ""


# ---------------------------------------------------------------------------
# is_boilerplate_or_nonassertional: flags chrome / error pages / metadata
# ---------------------------------------------------------------------------


def test_flags_error_page_404_stub() -> None:
    """REGRESSION: the literal NTSB-style error body that previously
    self-entailed through the faithfulness gate is now flagged."""
    assert is_boilerplate_or_nonassertional("Page not found") is True
    assert is_boilerplate_or_nonassertional("404 Not Found") is True
    assert is_boilerplate_or_nonassertional("Error 404") is True
    assert is_boilerplate_or_nonassertional("403 Forbidden") is True
    assert is_boilerplate_or_nonassertional("Access Denied") is True


def test_flags_crawl_marker_lines() -> None:
    assert is_boilerplate_or_nonassertional("URL Source: https://x.org") is True
    assert is_boilerplate_or_nonassertional("Markdown Content:") is True
    assert is_boilerplate_or_nonassertional("Split View") is True
    assert is_boilerplate_or_nonassertional("Cite Cite") is True
    assert is_boilerplate_or_nonassertional("Views") is True
    assert (
        is_boilerplate_or_nonassertional("Download full text from publisher")
        is True
    )
    assert (
        is_boilerplate_or_nonassertional("References listed on IDEAS") is True
    )


def test_flags_bare_doi_row() -> None:
    assert is_boilerplate_or_nonassertional("10.1056/NEJMoa2034577") is True
    assert is_boilerplate_or_nonassertional("doi:10.1001/jama.2020.1585") is True


def test_flags_pure_table_number_row() -> None:
    assert is_boilerplate_or_nonassertional("12.4 95% 1.2-3.4") is True
    assert is_boilerplate_or_nonassertional("Table 3 0.78 (0.61-0.99)") is True


def test_flags_empty_or_blank() -> None:
    assert is_boilerplate_or_nonassertional("") is True
    assert is_boilerplate_or_nonassertional("   ") is True


# ---------------------------------------------------------------------------
# is_boilerplate_or_nonassertional: real sentences are NEVER flagged
# (faithfulness — no real claim may be dropped as "boilerplate")
# ---------------------------------------------------------------------------


def test_real_sentence_is_not_flagged() -> None:
    sentence = "Mortality fell to 12.4% in the treatment arm (p < 0.001)."
    assert is_boilerplate_or_nonassertional(sentence) is False


def test_real_sentence_containing_not_found_is_not_flagged() -> None:
    """A real clause that merely contains the substring 'not found' must NOT
    be flagged — the error-page check requires the token to DOMINATE a short
    unit, not merely appear in prose."""
    sentence = "The gene variant was not found in the control cohort of 412 patients."
    assert is_boilerplate_or_nonassertional(sentence) is False


def test_real_numeric_sentence_with_words_is_not_flagged() -> None:
    sentence = "The hazard ratio was 0.78 (95% CI 0.61-0.99) favoring treatment."
    assert is_boilerplate_or_nonassertional(sentence) is False


def test_real_multilingual_sentence_is_not_flagged() -> None:
    assert (
        is_boilerplate_or_nonassertional(
            "La mortalité a chuté de 12,4 % dans le groupe traité."
        )
        is False
    )
    assert (
        is_boilerplate_or_nonassertional("死亡率は治療群で12.4%低下した。") is False
    )


def test_long_article_quoting_not_found_is_not_flagged() -> None:
    """A long body that quotes 'not found' deep in prose stays a finding —
    the error-page check is length-gated."""
    long_body = (
        "In the systematic review the authors reported that no eligible "
        "randomized trials were found for the pediatric subgroup, and the "
        "404 records screened did not include the target population; the "
        "phrase page not found appeared in two retracted preprints. " * 4
    )
    assert len(long_body) > 400
    assert is_boilerplate_or_nonassertional(long_body) is False


def test_error_unit_max_chars_is_env_overridable(monkeypatch) -> None:
    """LAW VI: the error-page short-body window is env-driven, not magic."""
    short_error = "Page not found"
    assert is_boilerplate_or_nonassertional(short_error) is True
    # Shrink the window below the stub length: the stub is now treated as a
    # potential real unit (not length-eligible for the error check). It is
    # still NOT flagged by the other branches, proving the knob is live.
    monkeypatch.setenv("PG_BOILERPLATE_ERROR_UNIT_MAX_CHARS", "5")
    assert is_boilerplate_or_nonassertional(short_error) is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
