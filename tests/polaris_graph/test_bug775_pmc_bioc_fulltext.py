"""I-bug-775 (#815) — PMC BioC full-text fetch invariants.

Per Codex decision A+B+D: the PMC BioC API gives structured OA full text where
HTML/PDF scraping stubs (JACC PMC10715890 → 54-char stub → 62k-char BioC). The
SAFETY-CRITICAL guard (Codex): never accept abstract-only / references-only /
error text as full text (no laundering — a stub can't support a clinical claim).
These assert the deterministic core (_extract_pmcid + _parse_bioc_fulltext).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest

from src.tools.access_bypass import (
    AccessBypass,
    _parse_bioc_fulltext,
    _PMC_BIOC_MIN_FULLTEXT_CHARS,
)


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status = 200

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """Minimal aiohttp.ClientSession stand-in returning a canned Unpaywall payload."""
    def __init__(self, payload: dict):
        self._payload = payload

    def get(self, *a, **k):
        return _FakeResp(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _bioc(passages: list[tuple[str, str]]) -> str:
    """Build a BioC_json string from (section_type, text) passages."""
    return json.dumps([
        {"documents": [{"passages": [
            {"infons": {"section_type": st}, "text": txt} for st, txt in passages
        ]}]}
    ])


# ── _extract_pmcid ──

def test_extract_pmcid_from_pmc_urls() -> None:
    ab = AccessBypass()
    assert ab._extract_pmcid("https://pmc.ncbi.nlm.nih.gov/articles/PMC6490750/") == "PMC6490750"
    assert ab._extract_pmcid("https://pmc.ncbi.nlm.nih.gov/articles/PMC10715890/pdf/main.pdf") == "PMC10715890"
    # lowercase normalizes
    assert ab._extract_pmcid("https://example.org/pmc12345/") == "PMC12345"


def test_extract_pmcid_none_for_non_pmc() -> None:
    ab = AccessBypass()
    assert ab._extract_pmcid("https://www.jacc.org/doi/10.1016/j.jacc.2017.03.541") is None
    assert ab._extract_pmcid("https://doi.org/10.1161/CIR.0000000000001193") is None
    assert ab._extract_pmcid("") is None
    assert ab._extract_pmcid(None) is None  # type: ignore[arg-type]


# ── _parse_bioc_fulltext: the no-laundering guard ──

def test_parse_rejects_abstract_only() -> None:
    """Abstract-only (no body section) must be rejected (returns '')."""
    raw = _bioc([("TITLE", "A Title"), ("ABSTRACT", "An abstract sentence.")])
    assert _parse_bioc_fulltext(raw) == ""


def test_parse_rejects_references_only() -> None:
    raw = _bioc([("TITLE", "T"), ("REF", "Smith et al. 2020."), ("REF", "Jones 2019.")])
    assert _parse_bioc_fulltext(raw) == ""


def test_parse_rejects_garbage_and_error() -> None:
    assert _parse_bioc_fulltext("not json at all") == ""
    assert _parse_bioc_fulltext("[]") == ""
    assert _parse_bioc_fulltext('{"error": "PMCID not in OA subset"}') == ""


def test_parse_accepts_body_sections() -> None:
    """A doc with an explicit body section (INTRO/METHODS/...) is full text."""
    raw = _bioc([
        ("TITLE", "T"),
        ("ABSTRACT", "abstract"),
        ("INTRO", "introduction " * 50),
        ("METHODS", "methods " * 50),
        ("RESULTS", "results " * 50),
    ])
    out = _parse_bioc_fulltext(raw)
    assert len(out) > _PMC_BIOC_MIN_FULLTEXT_CHARS
    assert "introduction" in out and "methods" in out


def test_parse_accepts_large_unsectioned_article() -> None:
    """OA docs whose passages lack section_type infons but are clearly an
    article (>=5 passages, >=3000 chars) are accepted; tiny ones are not."""
    big = json.dumps([{"documents": [{"passages": [
        {"infons": {}, "text": "paragraph of body text " * 40} for _ in range(6)
    ]}]}])
    assert len(_parse_bioc_fulltext(big)) >= 3000
    # 2 short unsectioned passages → not an article → rejected
    small = json.dumps([{"documents": [{"passages": [
        {"infons": {}, "text": "short"}, {"infons": {}, "text": "also short"}
    ]}]}])
    assert _parse_bioc_fulltext(small) == ""


# ── _try_unpaywall (B): never swap to a publisher/doi.org landing (iter-1 P2) ──

def _patch_unpaywall(monkeypatch, payload: dict) -> None:
    import aiohttp
    monkeypatch.setenv("UNPAYWALL_EMAIL", "test@example.org")
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeSession(payload))


@pytest.mark.asyncio
async def test_unpaywall_rejects_publisher_landing(monkeypatch) -> None:
    """Mode-1 fix: a publisher/doi.org OA landing (no PDF, not PMC) → None
    (do not swap; keep the original URL for the cascade)."""
    _patch_unpaywall(monkeypatch, {
        "is_oa": True,
        "oa_locations": [{"url": "https://doi.org/10.1111/eci.13803", "host_type": "publisher"}],
        "best_oa_location": {"url": "https://doi.org/10.1111/eci.13803", "host_type": "publisher"},
    })
    result = await AccessBypass()._try_unpaywall("10.1111/eci.13803")
    assert result is None, f"publisher landing must NOT be swapped, got {result!r}"


@pytest.mark.asyncio
async def test_unpaywall_returns_direct_pdf(monkeypatch) -> None:
    _patch_unpaywall(monkeypatch, {
        "is_oa": True,
        "oa_locations": [{
            "url_for_pdf": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10715890/pdf/main.pdf",
            "host_type": "repository",
        }],
    })
    result = await AccessBypass()._try_unpaywall("10.1016/j.jacasi.2023.08.007")
    assert result and "PMC10715890" in result


@pytest.mark.asyncio
async def test_unpaywall_returns_pmc_url_when_no_pdf(monkeypatch) -> None:
    """A PMCID-bearing PMC URL (no PDF) IS allowed — the caller's BioC path
    resolves it to full text."""
    _patch_unpaywall(monkeypatch, {
        "is_oa": True,
        "oa_locations": [{"url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12240022/", "host_type": "repository"}],
        "best_oa_location": {"url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC12240022/", "host_type": "repository"},
    })
    result = await AccessBypass()._try_unpaywall("10.0000/x")
    assert result and "PMC12240022" in result
