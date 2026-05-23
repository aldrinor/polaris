"""I-bug-775 (#815) — PMC BioC full-text fetch invariants.

Per Codex decision A+B+D: the PMC BioC API gives structured OA full text where
HTML/PDF scraping stubs (JACC PMC10715890 → 54-char stub → 62k-char BioC). The
SAFETY-CRITICAL guard (Codex): never accept abstract-only / references-only /
error text as full text (no laundering — a stub can't support a clinical claim).
These assert the deterministic core (_extract_pmcid + _parse_bioc_fulltext).
"""

from __future__ import annotations

import json

from src.tools.access_bypass import (
    AccessBypass,
    _parse_bioc_fulltext,
    _PMC_BIOC_MIN_FULLTEXT_CHARS,
)


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
