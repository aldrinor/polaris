"""I-deepfix-001 wave-2 4IR (#1344): Cookiebot / Usercentrics consent-manager
chrome strip — focused negative-control + byte-identity coverage.

The regex + the ``strip_web_boilerplate`` / ``clean_fetch_body`` wiring shipped in
6c4135fb; this module adds the missing tests the diff-gate flagged:

  * POSITIVE controls — each confirmed CMP chrome LINE is stripped when the flag is
    ON (input hygiene: removes junk, so a provenance head-quote starts at real prose).
  * NEGATIVE controls — a real sentence that merely CONTAINS or STARTS WITH a category
    word ("Marketing" / "Statistics" / "Necessary Preferences Statistics Marketing")
    survives BYTE-FOR-BYTE (the §-1.3 no-real-claim-dropped invariant).
  * ``PG_FETCH_COOKIE_CHROME_STRIP=0`` byte-identity — the flag OFF is byte-identical
    to the pre-fix behaviour for ``strip_web_boilerplate`` AND for ``_fetch_content``.

All OFFLINE (no network / no GPU). Faithfulness engine (strict_verify / NLI / 4-role /
span-grounding) is untouched — this is whole-line, multi-token-anchored INPUT hygiene.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.tools.access_bypass import clean_fetch_body, strip_web_boilerplate

_FLAG = "PG_FETCH_COOKIE_CHROME_STRIP"

# One CMP chrome line per taxonomy entry (each is a WHOLE line in a fetched body).
_CHROME_LINES = [
    "Consent Selection",
    "Necessary Preferences Statistics Marketing",  # ordered 4-category tab strip
    "Statistics Marketing",                         # ordered >=2-subset
    "Show details",
    "Show/Hide details",
    "Powered by Cookiebot by Usercentrics",
    "Powered by Cookiebot",
    "Cookiebot by Usercentrics",
    "About cookies",
    "Allow all Deny Customize",                     # button trio (>=2 buttons)
    "Allow selection Deny",
]

# Real prose that CONTAINS / STARTS WITH a category or button word but is a genuine
# assertional sentence — must survive the cookie strip byte-for-byte.
_REAL_PROSE_LINES = [
    "Marketing strategies drove the 2024 revenue increase across all regions.",
    "The Statistics module reported a p-value of 0.03 for the primary endpoint.",
    "Necessary safety precautions were followed throughout the clinical trial.",
    "We disabled Necessary Preferences Statistics Marketing tracking on page load.",
    "Deny the null hypothesis only when the confidence interval excludes unity.",
    "Preferences for once-weekly dosing were reported by most enrolled patients.",
    "Marketing",           # a bare single-token line (lookahead requires >=2 tokens)
    "Statistics",
]


# ── 1. POSITIVE controls: each CMP chrome line is stripped when ON ─────────────
@pytest.mark.parametrize("chrome", _CHROME_LINES)
def test_cookie_chrome_line_stripped_when_on(monkeypatch, chrome):
    monkeypatch.delenv(_FLAG, raising=False)  # default ON
    prose_head = "Tirzepatide reduced HbA1c by 2.1 percent in the phase 3 trial."
    prose_tail = "Mortality did not differ between the treatment and control arms."
    body = f"{prose_head}\n{chrome}\n{prose_tail}"

    out = strip_web_boilerplate(body)

    assert chrome not in out, f"CMP chrome line was not stripped ON: {chrome!r}"
    # The real prose on either side is retained (never dropped).
    assert prose_head in out
    assert prose_tail in out


def test_cookie_chrome_block_stripped_head_is_real_prose(monkeypatch):
    """A whole CMP banner block ahead of the article body is removed ON, so the
    body now STARTS with real prose (the provenance head-quote is clean)."""
    monkeypatch.delenv(_FLAG, raising=False)
    body = (
        "Consent Selection\n"
        "Necessary Preferences Statistics Marketing\n"
        "Show details\n"
        "Allow all Deny Customize\n"
        "Powered by Cookiebot by Usercentrics\n"
        "About cookies\n"
        "Tirzepatide reduced HbA1c by 2.1 percent in the phase 3 randomized trial."
    )
    out = strip_web_boilerplate(body)
    assert out.startswith("Tirzepatide reduced HbA1c")
    for chrome in (
        "Consent Selection", "Show details", "Allow all Deny Customize",
        "Powered by Cookiebot", "About cookies",
    ):
        assert chrome not in out


# ── 2. NEGATIVE controls: real prose survives BYTE-FOR-BYTE ────────────────────
@pytest.mark.parametrize("prose", _REAL_PROSE_LINES)
def test_real_prose_survives_cookie_strip_byte_for_byte(monkeypatch, prose):
    """The cookie regex must change NOTHING for a real sentence: ON output ==
    OFF output (isolates the cookie strip from the rest of strip_web_boilerplate)."""
    monkeypatch.setenv(_FLAG, "0")
    off = strip_web_boilerplate(prose)
    monkeypatch.setenv(_FLAG, "1")
    on = strip_web_boilerplate(prose)
    assert on == off, f"cookie strip altered real prose: {prose!r}"
    # And the sentence text itself is fully preserved.
    assert prose.strip() in on


# ── 3. PG_FETCH_COOKIE_CHROME_STRIP=0 byte-identity for strip_web_boilerplate ──
def test_flag_off_keeps_cookie_chrome(monkeypatch):
    """OFF ("0") is byte-identical to the pre-fix behaviour: the cookie regex is NOT
    applied, so a CMP chrome line SURVIVES (present in the OFF output)."""
    body = (
        "Real intro sentence about the trial outcome.\n"
        "Consent Selection\n"
        "Necessary Preferences Statistics Marketing\n"
        "Real closing sentence about mortality."
    )
    monkeypatch.setenv(_FLAG, "0")
    off = strip_web_boilerplate(body)
    assert "Consent Selection" in off
    assert "Necessary Preferences Statistics Marketing" in off

    monkeypatch.setenv(_FLAG, "1")
    on = strip_web_boilerplate(body)
    assert "Consent Selection" not in on
    assert "Necessary Preferences Statistics Marketing" not in on
    assert on != off


# ── 4. clean_fetch_body: cookie strip is gated; preamble strip is not ──────────
def test_clean_fetch_body_strips_cookie_chrome_when_on(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    body = (
        "Consent Selection\n"
        "Powered by Cookiebot by Usercentrics\n"
        "Semaglutide lowered cardiovascular events in the outcomes trial."
    )
    cleaned = clean_fetch_body(body).cleaned_text
    assert "Consent Selection" not in cleaned
    assert "Powered by Cookiebot" not in cleaned
    assert "Semaglutide lowered cardiovascular events" in cleaned


def test_clean_fetch_body_off_keeps_cookie_but_still_drops_preamble(monkeypatch):
    """OFF gates ONLY the cookie regex — the Jina 'Markdown Content:' preamble drop is
    independent, so it still fires (the flag's OFF path is scoped to the cookie strip)."""
    monkeypatch.setenv(_FLAG, "0")
    body = (
        "Title: Junk Title\n"
        "URL Source: https://x.example/y\n"
        "Markdown Content: Consent Selection\n"
        "Semaglutide lowered cardiovascular events in the outcomes trial."
    )
    cleaned = clean_fetch_body(body).cleaned_text
    # Preamble up to+including 'Markdown Content:' is dropped regardless of the flag.
    assert "Title: Junk Title" not in cleaned
    assert "URL Source" not in cleaned
    # But the cookie chrome after it SURVIVES because the cookie flag is OFF.
    assert "Consent Selection" in cleaned
    assert "Semaglutide lowered cardiovascular events" in cleaned


# ── 5. _fetch_content wiring: OFF byte-identical; ON applies clean_fetch_body ──
@dataclass
class _FakeAccessResult:
    success: bool = True
    content: str = ""
    access_method: str = "crawl4ai"
    metadata: dict | None = None


def _make_fake_bypass(raw: str):
    class _FakeBypass:
        async def fetch_with_bypass(self, url, prefer_legal=True):
            return _FakeAccessResult(content=raw)

    return _FakeBypass


_RAW_WITH_PREAMBLE = (
    "Title: Junk Title\n"
    "URL Source: https://x.example/y\n"
    "Markdown Content: Tirzepatide reduced HbA1c by 2.1 percent in the phase 3 "
    "randomized controlled trial across enrolled adults with type 2 diabetes over "
    "the full study period, a clinically meaningful and statistically robust result."
)


def test_fetch_content_flag_off_byte_identical_to_strip_html(monkeypatch):
    """OFF: _fetch_content returns exactly _strip_html(raw)[:max_chars] (byte-identical
    to the pre-fix behaviour — clean_fetch_body is never applied)."""
    from src.polaris_graph.retrieval import live_retriever
    import src.tools.access_bypass as ab

    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
    monkeypatch.setenv(_FLAG, "0")
    monkeypatch.setattr(ab, "AccessBypass", _make_fake_bypass(_RAW_WITH_PREAMBLE))

    max_chars = 5000
    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://example.com/paper", max_chars=max_chars,
    )
    expected_off = live_retriever._strip_html(_RAW_WITH_PREAMBLE)[:max_chars]
    assert ok is True
    assert content == expected_off
    # The preamble is retained on the OFF path (proof clean_fetch_body did NOT run).
    assert "Markdown Content" in content


def test_fetch_content_flag_on_applies_clean_fetch_body(monkeypatch):
    """ON (default): _fetch_content returns clean_fetch_body(_strip_html(raw)).cleaned_text
    [:max_chars] — the chrome/preamble head is removed so the body starts at real prose."""
    from src.polaris_graph.retrieval import live_retriever
    import src.tools.access_bypass as ab

    monkeypatch.setenv("PG_DISABLE_ACCESS_BYPASS", "0")
    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
    monkeypatch.delenv(_FLAG, raising=False)  # default ON
    monkeypatch.setattr(ab, "AccessBypass", _make_fake_bypass(_RAW_WITH_PREAMBLE))

    max_chars = 5000
    stripped = live_retriever._strip_html(_RAW_WITH_PREAMBLE)
    expected_on = clean_fetch_body(stripped).cleaned_text[:max_chars]
    expected_off = stripped[:max_chars]
    # Fixture sanity: clean_fetch_body must actually change the strip output, else the
    # ON/OFF difference below would be vacuous (fail loud rather than pass silently).
    assert expected_on != expected_off

    content, ok, _title, _body, _jsonld = live_retriever._fetch_content(
        "https://example.com/paper", max_chars=max_chars,
    )
    assert ok is True
    assert content == expected_on
    # The provenance head-quote now starts at real prose (chrome/preamble head gone).
    assert "Markdown Content" not in content
    assert content.startswith("Tirzepatide reduced HbA1c")
