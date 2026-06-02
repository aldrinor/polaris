"""Diff-gate P1-C regression — raw ld+json survives _strip_html to the classifier.

Codex MEASURED the production-wiring bug: `live_retriever._fetch_content` set
`ClassificationSignals.structured_jsonld = content`, but `content` is already
`_strip_html()` output and `_strip_html` deletes every `<script>...</script>`
block. The structural junk classifier (Signal C, news_article class) keys on
`"@type":"NewsArticle"` markers that live ONLY inside `<script type=
"application/ld+json">` blocks — so the demotion never fired on the live ON
path. With fixture JSON-LD the smoke S2 read 38/40 = 0.95, but production-like
cleaned content (JSON-LD destroyed) dropped to 37/40 = 0.925.

The fix captures the raw ld+json BEFORE `_strip_html` and routes it to
`structured_jsonld` separately from the stripped `fetched_body`. These tests
prove, end-to-end and offline:

  1. `_extract_jsonld_blocks` recovers the `@type` marker from raw HTML, and
     `_strip_html` independently destroys it from the body (the two diverge).
  2. With the wired JSON-LD, the ON-path classifier demotes a NewsArticle page
     to T6 (news) — REMOVING the dangerous false-T1 primary; with the JSON-LD
     stripped (the old bug) the SAME page lands T1.
  3. The structured_jsonld field is INERT when OFF — the OFF tier is identical
     whether the JSON-LD is present or absent (kill-switch guarantee).

Offline; no network. Pure regex extraction + the deterministic classifier.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.authority import AuthoritySignals
from src.polaris_graph.retrieval.live_retriever import (
    _extract_jsonld_blocks,
    _strip_html,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)

# A realistic lay-news page: NewsArticle JSON-LD in a <script> block + a body
# long enough to clear the stub-content threshold so the news signal — not a
# thin-content rule — drives the tier.
_NEWS_BODY = (
    "A new study reported that once-weekly tirzepatide significantly improved "
    "glycemic control and weight loss in patients with type 2 diabetes. "
) * 12
_NEWS_RAW_HTML = (
    "<html><head>"
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@type":"NewsArticle",'
    '"headline":"Tirzepatide Shows Significant Improvements"}'
    "</script>"
    "</head><body><p>" + _NEWS_BODY + "</p></body></html>"
)


def _classify(url: str, body: str, jsonld: str):
    sig = ClassificationSignals(
        url=url,
        title="Tirzepatide Shows Significant Improvements",
        fetched_content_length=len(body),
        # OpenAlex matched the underlying paper → would otherwise read as T1.
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
        fetched_body=body,
        structured_jsonld=jsonld,
        claim_vendor_token="",
    )
    sig.authority = AuthoritySignals()
    return classify_source_tier(sig).tier.value


def test_jsonld_extracted_and_strip_html_destroys_it():
    """The extractor recovers the @type marker; _strip_html destroys it."""
    jsonld = _extract_jsonld_blocks(_NEWS_RAW_HTML)
    body = _strip_html(_NEWS_RAW_HTML)

    assert '"@type":"NewsArticle"' in jsonld, (
        "extractor must recover the NewsArticle @type marker from raw HTML"
    )
    assert "NewsArticle" not in body, (
        "_strip_html must destroy the <script> JSON-LD from the body — this is "
        "exactly why the marker has to be captured separately BEFORE stripping"
    )
    # Long body cleared the stub threshold (the news signal, not thin-content,
    # must drive the tier in the demotion test below).
    assert len(body) >= 1000


def test_extractor_empty_on_cleaned_text_no_fabrication():
    """No <script> blocks (Jina markdown / Crawl4AI cleaned text) → honestly
    empty, never fabricated."""
    assert _extract_jsonld_blocks("Title: X\n\nClean markdown body text.") == ""
    assert _extract_jsonld_blocks("<html><body>plain article</body></html>") == ""
    assert _extract_jsonld_blocks("") == ""


def test_on_path_demotes_newsarticle_when_jsonld_wired(monkeypatch):
    """ON + wired JSON-LD demotes the NewsArticle page off the false-T1 primary.

    The lethal failure the fix prevents: a lay-news re-report whose OpenAlex
    match would read T1 (authoritative primary) unless the structural news
    signal demotes it. With the JSON-LD STRIPPED (the production bug Codex
    measured) the same page lands T1.
    """
    monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    url = "https://newsmedia.example/view/tirzepatide-news"

    jsonld = _extract_jsonld_blocks(_NEWS_RAW_HTML)
    body = _strip_html(_NEWS_RAW_HTML)

    tier_wired = _classify(url, body, jsonld)
    tier_stripped = _classify(url, body, "")  # the old bug: JSON-LD gone

    assert tier_wired == "T6", (
        f"wired JSON-LD must demote NewsArticle to T6 (news); got {tier_wired}"
    )
    assert tier_stripped == "T1", (
        "with JSON-LD stripped the SAME page reads T1 — the false-primary the "
        f"P1-C fix removes; got {tier_stripped}"
    )
    assert tier_wired != tier_stripped, "the wiring must change the ON-path tier"


def test_structured_jsonld_inert_when_off(monkeypatch):
    """OFF tier is identical with or without the JSON-LD (kill-switch guarantee).

    Uses a host NOT in any legacy news allowlist so the OFF result is driven by
    the non-junk legacy rules only — proving the structured_jsonld field never
    reaches the OFF path.
    """
    monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    url = "https://neutral-host.example/article/tirzepatide"

    jsonld = _extract_jsonld_blocks(_NEWS_RAW_HTML)
    body = _strip_html(_NEWS_RAW_HTML)

    off_with = _classify(url, body, jsonld)
    off_without = _classify(url, body, "")
    assert off_with == off_without, (
        "OFF tier must be byte-identical whether or not structured_jsonld is "
        f"populated; got {off_with} vs {off_without}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
