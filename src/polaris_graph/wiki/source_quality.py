"""
Wiki Source Quality — enhanced scoring with study design, retraction check,
content completeness, and author authority signals.

Wraps the existing src/utils/source_quality.py scorer and adds signals
from S2 publicationTypes, OpenAlex is_retracted/2yr_mean_citedness, and
content analysis.

All new signals come from APIs already called — just need additional fields
requested in the API queries.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

# ── Study Design Hierarchy ──────────────────────────────────────────

STUDY_DESIGN_SCORES: dict[str, float] = {
    "MetaAnalysis": 1.00,
    "SystematicReview": 0.95,
    "meta-analysis": 1.00,
    "systematic review": 0.95,
    "Review": 0.75,
    "ClinicalTrial": 0.85,
    "randomized controlled trial": 0.85,
    "rct": 0.85,
    "CaseReport": 0.40,
    "Editorial": 0.20,
    "LettersAndComments": 0.15,
    "Study": 0.60,
    "JournalArticle": 0.65,
    "Conference": 0.55,
    "Dataset": 0.30,
    "Book": 0.50,
    "BookSection": 0.45,
}

# Keywords for inferring study design from title/abstract
DESIGN_KEYWORDS: dict[str, float] = {
    "meta-analysis": 1.00,
    "systematic review": 0.95,
    "randomized controlled trial": 0.85,
    "randomised controlled trial": 0.85,
    "double-blind": 0.85,
    "placebo-controlled": 0.85,
    "cohort study": 0.70,
    "prospective cohort": 0.75,
    "retrospective": 0.60,
    "cross-sectional": 0.55,
    "case-control": 0.60,
    "case report": 0.40,
    "case series": 0.45,
    "narrative review": 0.50,
    "scoping review": 0.60,
    "umbrella review": 0.95,
    "editorial": 0.20,
    "commentary": 0.25,
    "letter to the editor": 0.15,
    "opinion": 0.20,
    "pilot study": 0.55,
    "observational": 0.55,
    "n-of-1": 0.35,
}


@dataclass
class SourceQualityScore:
    """Full source quality score with all signals."""

    # Core signals (from existing source_quality.py)
    base_quality_score: float = 0.0

    # New signals
    study_design: str = "Unknown"
    study_design_score: float = 0.5
    author_max_hindex: int = 0
    author_authority_score: float = 0.0
    is_retracted: bool = False
    content_completeness: str = "unknown"  # full, abstract_only, paywall_shell, stub
    content_completeness_score: float = 0.5

    # Metadata
    publication_types: list[str] = field(default_factory=list)
    source_url: str = ""
    doi: str = ""

    # Final composite
    composite_score: float = 0.0

    def compute_composite(self) -> float:
        """Compute weighted composite score from all signals."""
        if self.is_retracted:
            self.composite_score = 0.0
            return 0.0

        # Weights match the plan
        score = (
            self.base_quality_score * 0.35       # Existing scorer (citations, venue, recency, domain)
            + self.study_design_score * 0.20     # Study design hierarchy
            + self.author_authority_score * 0.10  # Author h-index
            + self.content_completeness_score * 0.10  # Full vs abstract vs stub
            + 0.25 * self.base_quality_score     # Double-weight base for stability
        )
        self.composite_score = min(1.0, max(0.0, score))
        return self.composite_score


def score_study_design(
    publication_types: list[str] | None = None,
    title: str = "",
    abstract: str = "",
) -> tuple[str, float]:
    """
    Score study design from S2 publicationTypes + keyword detection.

    Returns (design_name, score).
    """
    best_design = "Unknown"
    best_score = 0.5

    # First: check S2 publicationTypes
    if publication_types:
        for ptype in publication_types:
            if ptype in STUDY_DESIGN_SCORES:
                s = STUDY_DESIGN_SCORES[ptype]
                if s > best_score:
                    best_score = s
                    best_design = ptype

    # Second: keyword detection in title + abstract
    text = f"{title} {abstract}".lower()
    for keyword, score in DESIGN_KEYWORDS.items():
        if keyword in text and score > best_score:
            best_score = score
            best_design = keyword.title()

    return best_design, best_score


def score_author_authority(authors: list[dict] | None = None) -> tuple[int, float]:
    """
    Score author authority from max h-index across authors.

    S2 returns authors with hIndex field when requested.
    OpenAlex returns authors with summary_stats.h_index.

    Returns (max_hindex, normalized_score).
    """
    if not authors:
        return 0, 0.0

    max_h = 0
    for author in authors:
        # S2 format
        h = author.get("hIndex", 0) or 0
        # OpenAlex format
        if not h:
            stats = author.get("summary_stats", {})
            h = stats.get("h_index", 0) or 0
        if isinstance(h, (int, float)) and h > max_h:
            max_h = int(h)

    # Normalize: h-index of 40+ is world-class
    score = min(1.0, max_h / 40) if max_h > 0 else 0.0
    return max_h, score


def classify_content_completeness(
    content: str,
    word_count: int | None = None,
) -> tuple[str, float]:
    """
    Classify fetched content as full, abstract_only, paywall_shell, or stub.

    Returns (classification, score).
    """
    if not content:
        return "stub", 0.1

    if word_count is None:
        word_count = len(content.split())

    text_lower = content.lower()

    # Check for paywall indicators
    paywall_phrases = [
        "subscribe to access", "sign in to view", "purchase this article",
        "institutional access", "get full text", "buy this article",
        "rent this article", "log in to access", "access through your institution",
    ]
    has_paywall = any(phrase in text_lower for phrase in paywall_phrases)

    # Check for section headers (indicates full article)
    section_headers = ["introduction", "methods", "results", "discussion",
                       "conclusion", "abstract", "background", "materials and methods"]
    header_count = sum(1 for h in section_headers if h in text_lower)

    # Check for reference list
    has_references = bool(re.search(
        r"(?:references|bibliography|works cited)\s*\n",
        text_lower,
    ))

    if word_count < 50:
        return "stub", 0.1
    elif has_paywall and word_count < 500:
        return "paywall_shell", 0.2
    elif word_count < 300 and header_count < 2:
        return "abstract_only", 0.4
    elif word_count >= 2000 and header_count >= 3:
        return "full", 1.0
    elif word_count >= 1000 and (header_count >= 2 or has_references):
        return "full", 0.9
    elif word_count >= 500:
        return "abstract_only", 0.5
    else:
        return "abstract_only", 0.4


def check_retraction(
    doi: str = "",
    openalex_data: dict | None = None,
) -> bool:
    """
    Check if a paper has been retracted.

    Sources (in priority order):
    1. OpenAlex is_retracted field (free, already in API response)
    2. Retraction Watch CSV (if loaded)
    """
    # OpenAlex check
    if openalex_data:
        if openalex_data.get("is_retracted", False):
            logger.warning("[source-quality] RETRACTED paper detected via OpenAlex: %s", doi)
            return True

    # Retraction Watch CSV check
    rw_db = _get_retraction_watch_db()
    if rw_db and doi:
        normalized_doi = doi.lower().strip()
        if normalized_doi in rw_db:
            logger.warning("[source-quality] RETRACTED paper detected via Retraction Watch: %s", doi)
            return True

    return False


# ── Retraction Watch Database ────────────────────────────────────────

_RETRACTION_WATCH_DB: set[str] | None = None
_RETRACTION_WATCH_PATH = Path(os.getenv(
    "PG_RETRACTION_WATCH_PATH",
    "data/retraction_watch_dois.txt",
))


def _get_retraction_watch_db() -> set[str] | None:
    """Load Retraction Watch DOI database (lazy, one-time)."""
    global _RETRACTION_WATCH_DB

    if _RETRACTION_WATCH_DB is not None:
        return _RETRACTION_WATCH_DB

    if _RETRACTION_WATCH_PATH.exists():
        try:
            dois = set()
            with open(_RETRACTION_WATCH_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith("#"):
                        dois.add(line)
            _RETRACTION_WATCH_DB = dois
            logger.info("[source-quality] Loaded Retraction Watch DB: %d DOIs", len(dois))
            return dois
        except Exception as exc:
            logger.warning("[source-quality] Failed to load Retraction Watch DB: %s", exc)

    _RETRACTION_WATCH_DB = set()
    return _RETRACTION_WATCH_DB


# ── Source Quality Gate ──────────────────────────────────────────────

QUALITY_GATE_THRESHOLD = float(resolve("PG_SOURCE_QUALITY_GATE"))


def source_quality_gate(score: SourceQualityScore) -> bool:
    """
    Determine if a source passes the quality gate.

    Gate: composite >= threshold AND not retracted AND not stub.
    """
    if score.is_retracted:
        return False
    if score.content_completeness == "stub":
        return False
    return score.composite_score >= QUALITY_GATE_THRESHOLD


# ── Batch Enrichment ─────────────────────────────────────────────────


def enrich_evidence_with_quality(
    evidence: list[dict],
    fetched_content: list[dict] | None = None,
) -> list[dict]:
    """
    Enrich evidence pieces with source quality scores.

    Adds 'source_quality_score' and 'study_design' fields to each evidence piece.
    Uses metadata already present on the evidence (from S2/OpenAlex API responses).
    """
    # Build content lookup for completeness check
    content_by_url: dict[str, str] = {}
    if fetched_content:
        for fc in fetched_content:
            url = fc.get("url", "")
            content = fc.get("content", "")
            if url and content:
                content_by_url[url] = content

    enriched_count = 0
    retracted_count = 0

    for ev in evidence:
        url = ev.get("source_url", "")
        doi = ev.get("doi", "")

        # Study design
        pub_types = ev.get("publication_types", [])
        title = ev.get("source_title", "")
        statement = ev.get("statement", "")
        design_name, design_score = score_study_design(pub_types, title, statement)

        # Author authority
        authors = ev.get("authors_detail", ev.get("authors", []))
        # authors might be list of strings, not dicts
        if authors and isinstance(authors[0], str):
            max_h, auth_score = 0, 0.0
        else:
            max_h, auth_score = score_author_authority(authors)

        # Content completeness
        content = content_by_url.get(url, "")
        completeness, comp_score = classify_content_completeness(content)

        # Retraction check
        retracted = check_retraction(doi)
        if retracted:
            retracted_count += 1

        # Build enhanced score
        base_score = ev.get("source_confidence", ev.get("relevance_score", 0.5))
        enhanced = SourceQualityScore(
            base_quality_score=base_score,
            study_design=design_name,
            study_design_score=design_score,
            author_max_hindex=max_h,
            author_authority_score=auth_score,
            is_retracted=retracted,
            content_completeness=completeness,
            content_completeness_score=comp_score,
            publication_types=pub_types,
            source_url=url,
            doi=doi,
        )
        enhanced.compute_composite()

        # Attach to evidence
        ev["source_quality_enhanced"] = enhanced.composite_score
        ev["study_design"] = design_name
        ev["study_design_score"] = design_score
        ev["content_completeness"] = completeness
        ev["is_retracted"] = retracted
        ev["author_max_hindex"] = max_h

        enriched_count += 1

    logger.info(
        "[source-quality] Enriched %d evidence pieces (%d retracted)",
        enriched_count, retracted_count,
    )

    return evidence
