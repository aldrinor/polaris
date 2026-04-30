"""M-LIVE-2: extract competitor (ChatGPT DR / Gemini DR) prose
into the manifest shape that `beat_both_scoring.score_run()`
expects.

The risk Codex flagged in FINAL_PLAN M-LIVE-2: extraction
normalization can invalidate the verdict. To mitigate:
  - extraction rules are explicit, deterministic, regex-based
  - per-dimension extraction is independent (one bad extractor
    doesn't poison other dimensions)
  - extracted manifests round-trip through the same `score_run`
    that scores POLARIS — no separate scoring path

Public API:
    extract_competitor_manifest(text: str, source: str) -> dict

Output dict shape (compatible with beat_both_scoring._get):
    {
        "citations": [{"url": str}, ...],
        "claims": [{"n": int|None, "baseline": float|None,
                    "endpoint": float|None, "ci": str|None,
                    "raw": str}, ...],
        "sections": [{"title": str}, ...],
        "tables": [],     # competitor docs rarely emit tables
        "report": {
            "narrative_word_count": int,
            "source": str,
        },
        "extraction_metadata": {
            "extractor_version": "v1",
            "source": str,
            "char_count": int,
            "word_count": int,
        },
    }
"""

from __future__ import annotations

import re
from typing import Any

_EXTRACTOR_VERSION = "v1"


_URL_RE = re.compile(
    r"https?://[a-zA-Z0-9._\-/?=&%#~+:;,!$'()\[\]*]+",
    re.IGNORECASE,
)


_DOI_RE = re.compile(
    r"\b(?:doi:?\s*)?(10\.\d{4,9}/[\-._;()/:A-Z0-9]+)\b",
    re.IGNORECASE,
)


_PMID_RE = re.compile(
    r"\bpmid:?\s*(\d{6,9})\b",
    re.IGNORECASE,
)


# v2 R1 P1 #1 fix: v1 regex matched ANY short uppercase line,
# inflating section_count to 145 for ChatGPT (page-break residue
# fragments like "Trial", "Design and", "Sou" classified as
# sections). v2 requires Markdown-style heading prefix `#{1,4}`
# explicitly — far fewer false positives.
_SECTION_HEADER_RE = re.compile(
    r"^#{1,4}\s+(.+?)\s*$",
    re.MULTILINE,
)


_TABLE_RE = re.compile(
    r"^\|.+\|\s*$",
    re.MULTILINE,
)


_NUMERIC_CLAIM_RE = re.compile(
    r"(?P<measure>HbA1c|weight|body weight|BMI|systolic|diastolic|"
    r"LDL|HDL|cardiovascular|MACE)"
    r"[^.]{0,200}?"
    r"(?P<delta>[\-−]?\s*\d+\.?\d*\s*(?:%|kg|mg|mmol|mmHg))",
    re.IGNORECASE,
)


_CI_RE = re.compile(
    r"(?:95%?\s*CI|confidence interval)[:,\s]*"
    r"(?P<ci>[\[\(]?\s*[\-−]?\d+\.?\d*\s*(?:[,\-–to]+|to)\s*"
    r"[\-−]?\d+\.?\d*\s*[\]\)]?)",
    re.IGNORECASE,
)


_N_RE = re.compile(
    r"\b(?:n\s*=\s*|sample size of |included )"
    r"(?P<n>\d{2,6})\b",
    re.IGNORECASE,
)


_REGULATORY_HOSTS = {
    "fda.gov", "www.fda.gov", "accessdata.fda.gov",
    "ema.europa.eu", "www.ema.europa.eu",
    "health-products.canada.ca", "www.canada.ca",
    "nice.org.uk", "www.nice.org.uk",
    "clinicaltrials.gov", "www.clinicaltrials.gov",
    "pmda.go.jp", "www.pmda.go.jp",
    "tga.gov.au", "www.tga.gov.au",
    "mhra.gov.uk", "www.gov.uk",
}


_REGULATORY_TEXT_HINTS = (
    "FDA", "EMA", "Health Canada", "NICE", "PMDA", "TGA", "MHRA",
)


def _extract_citations(text: str) -> list[dict[str, Any]]:
    """Extract URLs, DOIs, and PMIDs as citation objects."""
    cites: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            cites.append({"url": url, "kind": "url"})

    for m in _DOI_RE.finditer(text):
        doi = m.group(1).rstrip(".,;)")
        url = f"https://doi.org/{doi}"
        if url not in seen:
            seen.add(url)
            cites.append({"url": url, "kind": "doi"})

    for m in _PMID_RE.finditer(text):
        pmid = m.group(1)
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        if url not in seen:
            seen.add(url)
            cites.append({"url": url, "kind": "pmid"})

    # v2 R1 P1 #4 fix: v1 injected synthetic regulatory proxy URLs
    # from plain-text mentions ("FDA", "EMA", etc.) into the same
    # citations bag that feeds unique_citations + regulatory_coverage
    # + jurisdictional_precision. One extractor error cross-poisoned
    # 3 verdicts. v2 drops the proxy injection: competitors that
    # don't cite regulatory URLs explicitly will (correctly) score
    # lower on regulatory_coverage. POLARIS's pipeline DOES cite
    # regulatory URLs explicitly, which is the right
    # comparative signal.

    return cites


def _extract_sections(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    for m in _SECTION_HEADER_RE.finditer(text):
        title = (m.group(1) or m.group(2) or "").strip()
        if not title or len(title) > 80:
            continue
        if title.isdigit():
            continue
        sections.append({"title": title})
    return sections


def _extract_tables(text: str) -> list[dict[str, Any]]:
    rows = _TABLE_RE.findall(text)
    if not rows:
        return []
    return [{"row_count": len(rows)}]


def _extract_claims(text: str) -> list[dict[str, Any]]:
    """Extract numeric claims with optional N + CI annotations."""
    claims: list[dict[str, Any]] = []
    for m in _NUMERIC_CLAIM_RE.finditer(text):
        start = max(0, m.start() - 50)
        end = min(len(text), m.end() + 200)
        window = text[start:end]
        n_m = _N_RE.search(window)
        ci_m = _CI_RE.search(window)
        delta_str = m.group("delta").replace("−", "-").strip()
        delta_str = re.sub(r"\s+", "", delta_str)
        try:
            num_match = re.match(
                r"^([\-]?\d+\.?\d*)", delta_str,
            )
            value = float(num_match.group(1)) if num_match else None
        except (ValueError, AttributeError):
            value = None
        claims.append({
            "raw": m.group(0),
            "measure": m.group("measure"),
            "endpoint": value,
            "n": int(n_m.group("n")) if n_m else None,
            "ci": ci_m.group("ci").strip() if ci_m else None,
            "baseline": None,
        })
    return claims


def extract_competitor_manifest(
    text: str,
    *,
    source: str,
) -> dict[str, Any]:
    """Extract a competitor DR document into manifest dict shape.

    Args:
        text: full prose text of the competitor DR
        source: human-readable label, e.g. "chatgpt_dr",
                "gemini_dr", "claude_dr"

    Returns:
        dict compatible with `beat_both_scoring.score_run()`
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("source must be non-empty str")

    citations = _extract_citations(text)
    sections = _extract_sections(text)
    tables = _extract_tables(text)
    claims = _extract_claims(text)

    word_count = len(re.findall(r"\b\w+\b", text))

    # v2 R1 P1 #2 fix: M-D9 narrative_length / contradiction
    # scorers read `report.body`. v1 only set `narrative_word_count`,
    # forcing both scorers to 0. v2 also populates `report.body`
    # with the full prose so scorers compute meaningful values.
    return {
        "citations": citations,
        "claims": claims,
        "sections": sections,
        "tables": tables,
        "report": {
            "body": text,
            "narrative_word_count": word_count,
            "source": source,
        },
        "extraction_metadata": {
            "extractor_version": _EXTRACTOR_VERSION,
            "source": source,
            "char_count": len(text),
            "word_count": word_count,
            "citation_count": len(citations),
            "claim_count": len(claims),
            "section_count": len(sections),
            "table_count": len(tables),
        },
    }
