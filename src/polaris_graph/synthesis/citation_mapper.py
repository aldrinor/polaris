"""
Citation mapper for polaris graph.

Verifies every [CITE:id] in the report is grounded in actual evidence.
Strips ungrounded citations. Builds bibliography.
No hallucinated references. No empty citations.
"""

import datetime
import hashlib
import logging
import os
import re
from typing import Optional

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.schemas import CitationAudit, SectionDraft
from src.polaris_graph.state import BibliographyEntry, EvidencePiece
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

# NRC-4: Patterns that indicate placeholder/invalid bibliography entries
_INVALID_TITLE_PATTERNS = re.compile(
    r"(?:not specified|untitled|unavailable|unknown title|n/a|none)",
    re.IGNORECASE,
)

# NRC-6: Blog/commercial source type indicators
_BLOG_SOURCE_TYPES = frozenset([
    "blog", "commercial", "marketing", "news_blog", "opinion",
    "affiliate", "sponsored",
])

CITE_PATTERN = re.compile(r"\[CITE:([a-zA-Z0-9_]+)\]")

# Multi-citation: [CITE:id1; CITE:id2] or [CITE:id1; CITE:id2; CITE:id3]
MULTI_CITE_PATTERN = re.compile(
    r"\[CITE:[a-zA-Z0-9_]+(?:\s*;\s*CITE:[a-zA-Z0-9_]+)+\]"
)


def _normalize_citations(text: str) -> str:
    """Split multi-citations and fix malformed citations before resolution.

    [CITE:id1; CITE:id2] → [CITE:id1][CITE:id2]
    [CITE:ev_abc123def (truncated, no ]) → [CITE:ev_abc123def]
    CITE:ev_abc123def (bare, no [ bracket) → [CITE:ev_abc123def]
    , CITE:ev_abc123def] (comma-separated) → [CITE:ev_abc123def]
    """
    # Split multi-citations into individual markers
    def _split(match: re.Match) -> str:
        ids = re.findall(r"CITE:([a-zA-Z0-9_]+)", match.group(0))
        return "".join(f"[CITE:{eid}]" for eid in ids)

    text = MULTI_CITE_PATTERN.sub(_split, text)

    # Fix bare CITE: markers (no [ bracket): "CITE:ev_xxx" → "[CITE:ev_xxx]"
    # Matches CITE: NOT preceded by [ (negative lookbehind)
    # Also consumes optional trailing ] to avoid double brackets
    text = re.sub(
        r"(?<!\[)CITE:([a-zA-Z0-9_]+)\]?",
        r"[CITE:\1]",
        text,
    )

    # Fix bare evidence IDs without CITE: prefix: "ev_abc123" → "[CITE:ev_abc123]"
    # Matches ev_ followed by hex chars, NOT already inside [CITE:...]
    # Consumes optional trailing ] to avoid double brackets
    text = re.sub(
        r"(?<!\[CITE:)(ev_[a-f0-9]{8,})\]?",
        r"[CITE:\1]",
        text,
    )

    # Fix truncated citations: [CITE:id not followed by ]
    # Matches [CITE: + id chars NOT followed by more id chars or ]
    text = re.sub(
        r"\[CITE:([a-zA-Z0-9_]+)(?=[^a-zA-Z0-9_\]])",
        r"[CITE:\1]",
        text,
    )
    # Also fix truncation at end of string
    text = re.sub(r"\[CITE:([a-zA-Z0-9_]+)$", r"[CITE:\1]", text)

    # Clean up comma/space artifacts around citation markers
    # "], [CITE:" or "], CITE:" → "][CITE:"
    text = re.sub(r"\],?\s*\[CITE:", "][CITE:", text)

    return text


def _validate_bibliography_urls(bibliography: list[str]) -> list[str]:
    """Validate and deduplicate bibliography entries by URL.

    Phase 1C quality improvement: removes bibliography entries with invalid
    URLs and deduplicates entries that resolve to the same URL.

    Rules applied:
    - Remove entries where the URL is empty, None, or "N/A"
    - Remove entries where the URL does not start with http:// or https://
    - Deduplicate by URL (keep first occurrence)
    - Log count of removed entries

    Args:
        bibliography: List of formatted bibliography entry strings.

    Returns:
        Cleaned list of bibliography entries with invalid URLs removed
        and duplicates eliminated.
    """
    if not bibliography:
        return bibliography

    # Extract URL from formatted entry string: "Available at: <url>" or "DOI: ..."
    _url_pattern = re.compile(r"Available at:\s*(https?://\S+)")
    _doi_pattern = re.compile(r"DOI:\s*(\S+)")

    cleaned: list[str] = []
    seen_urls: set[str] = set()
    removed_empty = 0
    removed_invalid_scheme = 0
    removed_duplicate = 0

    for entry in bibliography:
        # Extract URL from the formatted entry
        url_match = _url_pattern.search(entry)
        doi_match = _doi_pattern.search(entry)

        url = ""
        if url_match:
            url = url_match.group(1).rstrip(".")
        elif doi_match:
            # DOI entries are always valid (no URL scheme check needed)
            cleaned.append(entry)
            continue

        # Check for empty/placeholder URLs
        if not url or url.lower() in ("n/a", "none", ""):
            # Entry has no URL and no DOI — check if it's a metadata-only entry
            # like "[1] (Source metadata unavailable)" which we still keep
            if "Source metadata unavailable" in entry:
                cleaned.append(entry)
                continue
            # If no URL was found but entry exists, it might have inline URL
            # Only remove if we can confirm URL is explicitly bad
            if "Available at:" in entry:
                removed_empty += 1
                continue
            # No URL reference at all — keep entry (may be DOI-only or venue-only)
            cleaned.append(entry)
            continue

        # Check URL scheme
        if not url.startswith("http://") and not url.startswith("https://"):
            removed_invalid_scheme += 1
            continue

        # Deduplicate by URL
        url_normalized = url.lower().rstrip("/")
        if url_normalized in seen_urls:
            removed_duplicate += 1
            continue
        seen_urls.add(url_normalized)

        cleaned.append(entry)

    total_removed = removed_empty + removed_invalid_scheme + removed_duplicate
    if total_removed > 0:
        logger.info(
            "[polaris graph] Bibliography URL validation: removed %d entries "
            "(%d empty URL, %d invalid scheme, %d duplicate URL) from %d total",
            total_removed,
            removed_empty,
            removed_invalid_scheme,
            removed_duplicate,
            len(bibliography),
        )

        # OBS: Trace bibliography validation
        tracer = get_tracer()
        if tracer:
            tracer.evidence(
                "synthesize", "bibliography_url_validation",
                total_removed,
                removed_empty=removed_empty,
                removed_invalid_scheme=removed_invalid_scheme,
                removed_duplicate=removed_duplicate,
                original_count=len(bibliography),
                cleaned_count=len(cleaned),
            )

    return cleaned


async def audit_citations(
    client: OpenRouterClient,
    sections: list[SectionDraft],
    evidence: list[EvidencePiece],
) -> CitationAudit:
    """
    Audit all citations in the report sections.

    Uses reason() mode to verify each citation is properly grounded.
    Identifies ungrounded claims for removal or hedging.
    """
    # Build evidence lookup
    evidence_map = {
        e.get("evidence_id", ""): e for e in evidence
    }

    # Extract all citations from sections
    all_citations: list[dict] = []
    ungrounded_claims: list[str] = []

    # FIX-B1: Semantic relevance check — detect citation hallucination.
    # When LLM attaches [CITE:ev_xxx] to wrong claim (e.g., "ADF vs TRE LDL"
    # citing a mouse lifespan study), keyword overlap between the surrounding
    # sentence and the evidence statement is ~0. Strip these misattributions.
    # FIX-B1: Embedding similarity for citation-claim matching.
    # Domain-agnostic — no hardcoded stopwords. Works for any topic.
    _cite_sim_threshold = float(resolve("PG_CITE_SIMILARITY_THRESHOLD"))
    _misattributed_count = 0

    for section in sections:
        # Normalize multi-citations and truncated citations first
        normalized = _normalize_citations(section.content)
        matches = CITE_PATTERN.findall(normalized)
        for evidence_id in matches:
            if evidence_id in evidence_map:
                # FIX-B1: Check semantic relevance of citation to context
                _is_relevant = True
                if _cite_sim_threshold > 0:
                    ev = evidence_map[evidence_id]
                    ev_text = (
                        ev.get("statement", "") + " "
                        + ev.get("source_title", "")
                    ).strip()
                    # Extract ~200 chars around the citation
                    _cite_literal = f"[CITE:{evidence_id}]"
                    _cite_pos = normalized.find(_cite_literal)
                    if _cite_pos >= 0 and ev_text:
                        _ctx_start = max(0, _cite_pos - 100)
                        _ctx_end = min(len(normalized), _cite_pos + len(_cite_literal) + 100)
                        _ctx_text = normalized[_ctx_start:_ctx_end]
                        try:
                            from src.utils.embedding_service import embed_texts
                            import numpy as np
                            vecs = np.array(embed_texts([_ctx_text, ev_text]))
                            sim = float(vecs[0] @ vecs[1])
                            if sim < _cite_sim_threshold:
                                _is_relevant = False
                                _misattributed_count += 1
                                ungrounded_claims.append(
                                    f"Section '{section.title}': [CITE:{evidence_id}] "
                                    f"misattributed (sim={sim:.2f} < {_cite_sim_threshold})"
                                )
                        except Exception as _embed_exc:
                            logger.debug(
                                "[polaris graph] FIX-B1: Embedding check skipped "
                                "for %s: %s", evidence_id, str(_embed_exc)[:100],
                            )

                all_citations.append({
                    "evidence_id": evidence_id,
                    "section_id": section.section_id,
                    "grounded": _is_relevant,
                })
            else:
                ungrounded_claims.append(
                    f"Section '{section.title}': [CITE:{evidence_id}] "
                    f"references non-existent evidence"
                )
                all_citations.append({
                    "evidence_id": evidence_id,
                    "section_id": section.section_id,
                    "grounded": False,
                })

    if _misattributed_count > 0:
        logger.warning(
            "[polaris graph] FIX-B1: Detected %d misattributed citations "
            "(claim-evidence keyword overlap < %d)",
            _misattributed_count, _cite_sim_threshold,
        )

    # FIX-QG1: Deduplicate by DOI first, then by URL — prevents same paper
    # from appearing twice under different URLs (PG_TEST_023: [1]=[2], [4]=[5]).
    seen_keys: dict[str, str] = {}  # dedup_key → first evidence_id
    ordered_citations: list[str] = []  # one representative evidence_id per source
    eid_to_representative: dict[str, str] = {}  # any eid → representative eid

    for c in all_citations:
        eid = c["evidence_id"]
        if not c["grounded"]:
            continue
        ev = evidence_map.get(eid, {})
        doi = (ev.get("doi") or "").strip().lower()
        url = ev.get("source_url", eid)
        # Use DOI as primary dedup key if available, fall back to URL
        dedup_key = doi if doi else url
        if dedup_key not in seen_keys:
            seen_keys[dedup_key] = eid
            ordered_citations.append(eid)
        eid_to_representative[eid] = seen_keys[dedup_key]

    # Build bibliography (one entry per unique source)
    bibliography_entries = []
    for i, eid in enumerate(ordered_citations, 1):
        ev = evidence_map.get(eid, {})
        formatted = _format_bibliography_entry(ev, i)
        bibliography_entries.append(formatted)

    # Phase 1C: Validate bibliography URLs — remove empty, invalid, duplicate
    bibliography_entries = _validate_bibliography_urls(bibliography_entries)

    grounded_count = sum(1 for c in all_citations if c["grounded"])
    total_count = len(all_citations)
    stripped_count = total_count - grounded_count
    logger.info(
        "[polaris graph] Citation audit: %d/%d grounded, %d ungrounded claims, "
        "%d unique sources",
        grounded_count,
        total_count,
        len(ungrounded_claims),
        len(ordered_citations),
    )

    # OBS-6: Trace citation audit
    tracer = get_tracer()
    if tracer:
        tracer.evidence(
            "synthesize", "citation_audit", total_count,
            grounded=grounded_count,
            stripped=stripped_count,
            unique_sources=len(ordered_citations),
            mapping=[{
                "num": i + 1,
                "url": evidence_map.get(eid, {}).get("source_url", "")[:150],
                "title": evidence_map.get(eid, {}).get("source_title", "")[:100],
            } for i, eid in enumerate(ordered_citations[:30])],
        )

        # WAVE-4.3: Full citation mapping (ALL citations, no cap)
        tracer.evidence(
            "synthesize", "citation_mapping_full", len(ordered_citations),
            full_mapping=[{
                "evidence_id": eid,
                "citation_number": i + 1,
                "source_url": evidence_map.get(eid, {}).get("source_url", ""),
                "source_title": evidence_map.get(eid, {}).get("source_title", ""),
            } for i, eid in enumerate(ordered_citations)],
            merge_pairs=[{
                "original_eid": eid,
                "representative_eid": rep,
            } for eid, rep in eid_to_representative.items() if eid != rep],
            ungrounded=[{
                "evidence_id": c["evidence_id"],
                "section_id": c.get("section_id", ""),
            } for c in all_citations if not c["grounded"]],
        )

    from src.polaris_graph.schemas import CitationMapping

    # Build citation number map: representative eid → number
    rep_to_number: dict[str, int] = {}
    for i, eid in enumerate(ordered_citations, 1):
        rep_to_number[eid] = i

    # Create mappings for ALL grounded evidence IDs (each maps to its
    # source's citation number via the representative)
    mappings = []
    seen_mapping_ids: set[str] = set()
    for c in all_citations:
        eid = c["evidence_id"]
        if not c["grounded"] or eid in seen_mapping_ids:
            continue
        seen_mapping_ids.add(eid)
        rep = eid_to_representative.get(eid, eid)
        number = rep_to_number.get(rep, 0)
        if number > 0:
            mappings.append(
                CitationMapping(
                    evidence_id=eid,
                    citation_number=number,
                    is_grounded=True,
                )
            )

    # FIX-R7: Log perspective diversity warning
    if mappings:
        _persp_counts: dict[str, int] = {}
        for _mc in all_citations:
            if not _mc.get("grounded"):
                continue
            _eid = _mc["evidence_id"]
            _ev = evidence_map.get(_eid, {})
            _p = _ev.get("perspective", "Unknown")
            _persp_counts[_p] = _persp_counts.get(_p, 0) + 1
        _total_mapped = sum(_persp_counts.values())
        for _p, _c in _persp_counts.items():
            if _total_mapped > 0 and (_c / _total_mapped) < 0.05:
                logger.warning(
                    "[polaris graph] FIX-R7: Perspective '%s' under-represented "
                    "in citations: %d/%d (%.1f%%)",
                    _p, _c, _total_mapped, (_c / _total_mapped) * 100,
                )

    return CitationAudit(
        mappings=mappings,
        ungrounded_claims=ungrounded_claims,
        bibliography_entries=bibliography_entries,
    )


def resolve_citations(
    content: str,
    citation_map: dict[str, int],
    max_frequency: int = 0,
    global_citation_counts: Optional[dict[int, int]] = None,
) -> str:
    """
    Replace [CITE:evidence_id] with [N] numbered references.

    Handles multi-citations [CITE:id1; CITE:id2] and truncated markers.
    Strips citations that aren't in the map (ungrounded).

    FIX-QG1: If max_frequency > 0, caps each source at max_frequency
    citations per section to prevent over-citation concentration.

    NRC-2: If global_citation_counts is provided, also enforces a global
    cross-section cap via PG_MAX_GLOBAL_CITATION_FREQ. The dict is
    mutated in place to track counts across calls.
    """

    if max_frequency <= 0:
        max_frequency = int(os.getenv("PG_MAX_CITATION_FREQUENCY", "5"))
    max_global_freq = int(resolve("PG_MAX_GLOBAL_CITATION_FREQ"))

    # Normalize multi-citations and truncated citations first
    normalized = _normalize_citations(content)

    # FIX-QG1: Track citation frequency per source number for capping
    citation_counts: dict[int, int] = {}
    # FIX-H12: Track ungrounded citation removals for logging
    _ungrounded_removals: list[str] = []

    def _replace(match: re.Match) -> str:
        evidence_id = match.group(1)
        number = citation_map.get(evidence_id)
        if number is not None:
            citation_counts[number] = citation_counts.get(number, 0) + 1
            if max_frequency > 0 and citation_counts[number] > max_frequency:
                return ""  # Drop excess citations beyond per-section cap
            # NRC-2: Check global cross-section citation cap
            if global_citation_counts is not None:
                global_citation_counts[number] = global_citation_counts.get(number, 0) + 1
                if global_citation_counts[number] > max_global_freq:
                    return "[*]"  # Phantom: citation existed but was capped
            return f"[{number}]"
        # FIX-H12: Log ungrounded citation removal (was silent)
        _ungrounded_removals.append(evidence_id)
        return ""
    resolved = CITE_PATTERN.sub(_replace, normalized)

    # FIX-H12: Log removed ungrounded citations
    if _ungrounded_removals:
        logger.info(
            "[polaris graph] FIX-H12: Removed %d unmapped citations during "
            "resolution (evidence IDs not in citation map)",
            len(_ungrounded_removals),
        )

    # Log over-cited sources
    over_cited = {k: v for k, v in citation_counts.items() if v > max_frequency}
    if over_cited:
        logger.info(
            "[polaris graph] FIX-QG1: Citation frequency cap applied: %s "
            "(max=%d per source)",
            {f"[{k}]": v for k, v in over_cited.items()},
            max_frequency,
        )

    # Deduplicate adjacent identical citation numbers: [1][1] → [1]
    resolved = re.sub(r"(\[\d+\])(?:\1)+", r"\1", resolved)

    # Clean up empty citation artifacts (double spaces, trailing spaces before periods)
    resolved = re.sub(r"  +", " ", resolved)
    # FIX-047A: Clean space-period artifacts from citation removal
    resolved = re.sub(r'\s+([.,;:!?])', r'\1', resolved)

    return resolved


def strip_ungrounded_citations(
    sections: list[SectionDraft],
    evidence_ids: set[str],
) -> list[SectionDraft]:
    """
    Remove [CITE:id] markers that reference non-existent evidence.

    Returns new section drafts with clean citations only.
    """
    cleaned = []
    total_stripped = 0

    for section in sections:
        def _clean(match: re.Match) -> str:
            nonlocal total_stripped
            eid = match.group(1)
            if eid in evidence_ids:
                return match.group(0)
            total_stripped += 1
            return ""

        # Normalize multi/truncated citations before stripping
        normalized = _normalize_citations(section.content)
        clean_content = CITE_PATTERN.sub(_clean, normalized)
        cleaned.append(
            SectionDraft(
                section_id=section.section_id,
                title=section.title,
                content=clean_content,
                claims_made=section.claims_made,
                evidence_ids=section.evidence_ids,  # FIX-039: Preserve
            )
        )

    if total_stripped > 0:
        logger.warning(
            "[polaris graph] Stripped %d ungrounded citations from %d sections",
            total_stripped,
            len(sections),
        )
        # OBS-6: Trace ungrounded citation stripping
        tracer = get_tracer()
        if tracer:
            tracer.evidence(
                "synthesize", "citations_stripped",
                total_stripped,
                sections_affected=len(sections),
            )

    return cleaned


_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_reader", "utm_viz_id", "utm_brand",
    "ref", "ref_src", "ref_url", "referrer", "referral",
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_eid", "mc_cid",
    "source", "campaign", "medium", "email_source",
    "_ga", "_gl", "__hsfp", "__hssc", "__hstc", "hsCtaTracking",
    "igshid", "trackingId", "tracking_id", "spm", "sessionid",
})


def _canonicalize_url(url: str) -> str:
    """W3.9: Normalize URL for bibliography dedup.

    Why: different evidence pieces reference the same page with trivial
    variations (http/https, trailing slash, www, uppercase host, marketing
    tracking params). Without canonicalization, dedup misses these pairs
    and the bibliography contains sim=1.0 duplicates.

    Critical: preserve identifier query params like SSRN's ?abstract_id=,
    PubMed's ?term=, DOI resolvers, Google Scholar, etc. Only strip known
    tracking params so different papers on query-driven sites stay distinct.
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url.strip())
        scheme = "https" if parts.scheme in ("http", "https") else (parts.scheme or "https")
        netloc = parts.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parts.path.rstrip("/") or "/"
        # Preserve identifier params; drop only known marketing/tracking params.
        if parts.query:
            kept = [
                (k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=True)
                if k.lower() not in _TRACKING_PARAMS
            ]
            kept.sort()  # Order-insensitive dedup.
            query = urlencode(kept, doseq=True)
        else:
            query = ""
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        return url.strip().lower()


def build_bibliography(
    evidence: list[EvidencePiece],
    used_ids: list[str],
) -> list[BibliographyEntry]:
    """Build ordered bibliography from used evidence IDs.

    Deduplicates by canonicalized source URL so the same source appears
    only once, even if multiple evidence pieces cite it with minor URL
    variations (http/https, www prefix, trailing slash, query params).

    NRC-4: Validates entries and rejects placeholders.
    NRC-6: Marks blog/commercial sources as non-peer-reviewed.
    W3.9: Canonical-URL dedup replaces raw-URL dedup.
    """
    evidence_map = {e.get("evidence_id", ""): e for e in evidence}
    entries: list[BibliographyEntry] = []
    seen_urls: dict[str, int] = {}  # canonical_url → entry index
    invalid_count = 0
    blog_count = 0

    for eid in used_ids:
        ev = evidence_map.get(eid, {})
        url = ev.get("source_url", eid)
        canonical = _canonicalize_url(url) or url

        if canonical in seen_urls:
            # Add this evidence_id to the existing entry
            idx = seen_urls[canonical]
            entries[idx]["evidence_ids"].append(eid)
            continue

        number = len(entries) + 1
        citation_key = f"[{number}]"
        seen_urls[canonical] = len(entries)

        # NRC-4: Validate before formatting
        is_valid, reason = _validate_bibliography_entry(ev)
        if not is_valid:
            invalid_count += 1

        # NRC-6: Track blog sources
        source_type = ev.get("source_type", "unknown")
        if source_type in _BLOG_SOURCE_TYPES:
            blog_count += 1

        # FIX-FORMAT-2: Extract title for separate field (audit D6 scoring)
        _bib_title = ev.get("source_title", "")
        if not _bib_title or len(_bib_title.strip()) < 3:
            _bib_title = _recover_title(ev)

        entries.append(
            BibliographyEntry(
                citation_key=citation_key,
                formatted=_format_bibliography_entry(ev, number),
                citation_number=number,  # FIX-B6
                url=url,
                title=_bib_title,
                source_type=source_type,
                evidence_ids=[eid],
            )
        )

    if invalid_count > 0:
        logger.warning(
            "[polaris graph] NRC-4: %d/%d bibliography entries had invalid metadata "
            "(placeholder titles, future dates, or missing fields)",
            invalid_count,
            len(entries),
        )

    if blog_count > 0:
        logger.info(
            "[polaris graph] NRC-6: %d/%d bibliography entries marked as non-peer-reviewed",
            blog_count,
            len(entries),
        )

    return entries


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _validate_bibliography_entry(evidence: dict) -> tuple[bool, str]:
    """NRC-4: Validate a bibliography entry for completeness and accuracy.

    Checks for placeholder titles, future-dated years, and missing metadata.
    Returns (is_valid, reason) tuple.
    """
    title = evidence.get("source_title", "")
    year = evidence.get("year", 0)
    authors = evidence.get("authors", [])
    venue = evidence.get("venue", "")
    url = evidence.get("source_url", "")

    # Check for placeholder/invalid titles
    if not title or _INVALID_TITLE_PATTERNS.search(title):
        return False, f"placeholder_title: '{title[:50]}'"

    # Check for future-dated years (suspicious)
    current_year = datetime.datetime.now().year
    if year and year > current_year:
        return False, f"future_dated: year={year}"

    # Check for completely empty metadata (no author, no venue, no year)
    if not authors and not venue and not year:
        if not url:
            return False, "no_metadata: empty author+venue+year+url"

    # Check venue for placeholder patterns
    if venue and _INVALID_TITLE_PATTERNS.search(venue):
        return False, f"placeholder_venue: '{venue[:50]}'"

    return True, "valid"


def _extract_author_from_metadata(evidence: dict) -> str:
    """FIX-047G: Extract author from evidence metadata when authors list is empty.

    Tries multiple strategies:
    1. 'author' field (string) from Exa/Jina metadata
    2. Domain-based organization name extraction from URL
    3. Returns empty string if no author can be determined
    """
    # Strategy 1: Check 'author' string field (Exa, Jina, Firecrawl metadata)
    author_str = evidence.get("author", "")
    if author_str and isinstance(author_str, str) and len(author_str) > 2:
        # Skip placeholder values
        if author_str.lower() not in ("unknown", "n/a", "none", "anonymous"):
            return author_str

    # Strategy 2: Extract organization from URL domain
    url = evidence.get("source_url", "")
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. and common TLDs
            domain = domain.replace("www.", "")

            # Known authoritative domain mappings
            domain_authors = {
                "epa.gov": "U.S. Environmental Protection Agency",
                "who.int": "World Health Organization",
                "cdc.gov": "U.S. Centers for Disease Control and Prevention",
                "nih.gov": "National Institutes of Health",
                "nature.com": "Nature Publishing Group",
                "sciencedirect.com": "Elsevier",
                "springer.com": "Springer",
                "wiley.com": "Wiley",
                "ieee.org": "IEEE",
                "arxiv.org": "arXiv",
                "ncbi.nlm.nih.gov": "National Center for Biotechnology Information",
                "usgs.gov": "U.S. Geological Survey",
                "worldbank.org": "World Bank",
                "un.org": "United Nations",
                "europa.eu": "European Union",
            }

            for known_domain, author_name in domain_authors.items():
                if known_domain in domain:
                    return author_name

            # Extract organization from domain (e.g., "example.org" -> "Example")
            parts = domain.split(".")
            if len(parts) >= 2:
                org_name = parts[-2]  # e.g., "example" from "example.org"
                if len(org_name) > 3 and org_name not in ("www", "com", "org", "net", "gov", "edu"):
                    return org_name.capitalize()
        except Exception as url_err:
            logger.debug("Author extraction from URL failed: %s", url_err)

    return ""


def _recover_title(evidence: dict) -> str:
    """D6 fix: Recover title from evidence metadata when source_title is empty.

    Tries multiple strategies before falling back to empty string:
    1. evidence_summary field (analyzer generates this)
    2. statement field (first evidence statement from this source)
    3. URL path extraction (readable slug from URL)
    """
    # Strategy 1: evidence_summary
    summary = evidence.get("evidence_summary", "")
    if summary and len(summary) > 10 and not _INVALID_TITLE_PATTERNS.search(summary):
        return summary[:200]

    # Strategy 2: first statement (truncated)
    statement = evidence.get("statement", "")
    if statement and len(statement) > 15:
        # Take first sentence, cap at 150 chars
        first_sent = statement.split(".")[0].strip()
        if len(first_sent) > 15:
            return first_sent[:150]

    # Strategy 3: URL path extraction
    url = evidence.get("source_url", "")
    if url:
        from urllib.parse import urlparse, unquote
        path = urlparse(url).path
        # Extract the last meaningful path segment
        segments = [s for s in path.split("/") if s and len(s) > 3]
        if segments:
            slug = unquote(segments[-1])
            # Convert hyphens/underscores to spaces, title-case
            readable = slug.replace("-", " ").replace("_", " ").strip()
            if len(readable) > 10 and not readable.isdigit():
                return readable.title()[:150]

    return ""


def _format_bibliography_entry(evidence: dict, number: int) -> str:
    """Format a single bibliography entry in academic style.

    NRC-4: Validates entry before formatting. Invalid entries get URL-only
    footnote format instead of fake bibliography entries.
    NRC-6: Blog/commercial sources get "(non-peer-reviewed)" suffix.
    FIX-047G: Extracts author from metadata/URL when authors list is empty.
    D6 fix: Recovers title from metadata before falling back to URL-only.
    """
    # D6 fix: Try to recover empty titles before validation
    title = evidence.get("source_title", "")
    if not title or len(title.strip()) < 3:
        recovered = _recover_title(evidence)
        if recovered:
            evidence["source_title"] = recovered
            logger.debug(
                "[polaris graph] D6-fix: Recovered title for [%d]: '%s'",
                number, recovered[:60],
            )

    is_valid, reason = _validate_bibliography_entry(evidence)

    authors = evidence.get("authors", [])
    title = evidence.get("source_title", "Untitled")
    url = evidence.get("source_url", "")
    year = evidence.get("year", 0)
    venue = evidence.get("venue", "")
    doi = evidence.get("doi", "")
    source_type = evidence.get("source_type", "unknown")

    # NRC-4: For invalid entries, format as URL-only footnote
    if not is_valid:
        logger.warning(
            "[polaris graph] NRC-4: Bibliography entry [%d] invalid (%s), "
            "using URL-only format",
            number,
            reason,
        )
        if url:
            return f"[{number}] Available at: {url}"
        return f"[{number}] (Source metadata unavailable)"

    # NRC-4: Clamp future-dated years
    current_year = datetime.datetime.now().year
    if year and year > current_year:
        year = 0  # Will show as (n.d.)

    author_str = ""
    if authors:
        if len(authors) <= 3:
            author_str = ", ".join(authors)
        else:
            author_str = f"{authors[0]} et al."
    else:
        # FIX-047G: Try to extract author from metadata/URL
        author_str = _extract_author_from_metadata(evidence)

    year_str = f"({year})" if year else "(n.d.)"

    parts = [f"[{number}]"]
    if author_str:
        parts.append(f"{author_str} {year_str}.")
    else:
        parts.append(year_str + ".")

    parts.append(f'"{title}."')

    if venue:
        parts.append(f"*{venue}*.")

    if doi:
        parts.append(f"DOI: {doi}.")
    elif url:
        parts.append(f"Available at: {url}")

    # NRC-6: Mark non-peer-reviewed sources
    if source_type in _BLOG_SOURCE_TYPES:
        parts.append("(non-peer-reviewed)")

    return " ".join(parts)
