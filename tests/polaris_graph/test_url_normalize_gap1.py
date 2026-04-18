"""
Regression tests for Gap-1 URL normalization (2026-04-18 apples-to-apples run).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.run_honest_on_prerebuild_corpus import _normalize_url


def test_gap1_trailing_slash_stripped() -> None:
    assert _normalize_url("https://example.com/path/") == "https://example.com/path"
    assert _normalize_url("https://example.com/") == "https://example.com"


def test_gap1_www_prefix_stripped() -> None:
    assert _normalize_url("https://www.example.com/x") == "https://example.com/x"
    assert _normalize_url("https://WWW.Example.com/x") == "https://example.com/x"


def test_gap1_fragment_dropped() -> None:
    assert _normalize_url("https://example.com/x#section-1") == "https://example.com/x"


def test_gap1_query_preserved() -> None:
    # jomes.org / DOI gateway URLs carry real info in ?doi=... — keep it.
    url = "https://www.jomes.org/journal/download_pdf.php?doi=10.7570%2Fjomes22012"
    normalized = _normalize_url(url)
    assert "doi=10.7570%2Fjomes22012" in normalized


def test_gap1_case_insensitive_netloc() -> None:
    a = _normalize_url("https://PMC.ncbi.nlm.nih.gov/articles/PMC9758543")
    b = _normalize_url("https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543")
    assert a == b


def test_gap1_variants_collide() -> None:
    """All four variants of the same URL must produce the same key."""
    urls = [
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543/",
        "https://www.pmc.ncbi.nlm.nih.gov/articles/PMC9758543",
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543#abstract",
    ]
    normalized = {_normalize_url(u) for u in urls}
    assert len(normalized) == 1, f"Variants didn't collide: {normalized}"


def test_gap1_empty_url_safe() -> None:
    assert _normalize_url("") == ""
    assert _normalize_url(None) == ""  # type: ignore[arg-type]
