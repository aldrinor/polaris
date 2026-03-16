"""
Citation Registry - Late-Binding Citation Resolution

Tracks [CITE:xyz] tokens from P7 and maps them to source metadata.
Enables citation resolution at rendering time for Phase 11.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real metadata lookup from VWM
- Actual URL/author/date extraction
- Live citation validation

Usage:
    from src.utils.citation_registry import CitationRegistry

    registry = CitationRegistry(vector_id="S1V1_...")
    registry.load_from_vwm()

    # Resolve citation
    citation = registry.resolve("chunk_00123")
    # Returns: {"url": "...", "author": "...", "date": "...", "title": "..."}

    # Bind citations in text
    bound_text = registry.bind_citations(text_with_cite_markers)
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_config, OUTPUTS_DIR
from src.memory.chroma_client import get_chroma_manager

# SOTA: CrossRef API for deterministic citation resolution
try:
    from src.utils.crossref_resolver import (
        CrossRefResolver,
        resolve_doi_sync,
        extract_doi_from_url,
    )
    CROSSREF_AVAILABLE = True
except ImportError:
    CROSSREF_AVAILABLE = False
    resolve_doi_sync = None
    extract_doi_from_url = None


# ============================================================================
# FIX-183A: Citation Token Normalization (pre-extraction cleanup)
# ============================================================================

def normalize_cite_tokens(text: str) -> str:
    """Normalize malformed [CITE:xxx] tokens BEFORE extraction.

    Handles:
    1. Double brackets: [[CITE:xxx]] -> [CITE:xxx]
    2. Nested quotes: [CITE:["ev_001"]] -> [CITE:ev_001]
    3. Whitespace: [CITE: ev_001 ] -> [CITE:ev_001]
    4. Comma-separated: [CITE:ev_001, ev_002] -> [CITE:ev_001][CITE:ev_002]

    All transformations are idempotent.
    """
    if not text:
        return text

    # Step 1: Fix double/nested brackets
    text = re.sub(r'\[\[CITE:', '[CITE:', text)
    # Handle [CITE:["ev_001"]] -> [CITE:ev_001]
    # First strip inner ["..."] notation inside CITE tokens
    def _fix_nested(m):
        inner = m.group(1)
        # Strip ["..."] wrapping
        inner = re.sub(r'^\["?|"?\]$', '', inner.strip())
        # Strip remaining quotes
        inner = inner.strip('"\'')
        return f'[CITE:{inner}]'
    text = re.sub(r'\[CITE:(\[.+?\])\]\]?', _fix_nested, text)
    # Handle remaining double-close: [CITE:xxx]]
    text = re.sub(r'(\[CITE:[^\]]+)\]\]', r'\1]', text)

    # Step 2: Strip whitespace inside tokens
    def _strip_ws(m):
        return f'[CITE:{m.group(1).strip()}]'
    text = re.sub(r'\[CITE:(\s+[^\]]+)\]', _strip_ws, text)
    text = re.sub(r'\[CITE:([^\]]+\s+)\]', _strip_ws, text)

    # Step 3: Split comma-separated IDs
    def _split_multi(m):
        raw = m.group(1)
        if ',' not in raw:
            return m.group(0)
        parts = [p.strip() for p in raw.split(',') if p.strip()]
        return ''.join(f'[CITE:{p}]' for p in parts)
    text = re.sub(r'\[CITE:([^\]]+)\]', _split_multi, text)

    return text


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class CitationSource:
    """Represents a single citation source."""
    chunk_id: str
    url: str = ""
    title: str = ""
    author: str = ""
    publication_date: str = ""
    source_type: str = "web"  # web, pdf, academic
    snippet: str = ""
    verification_status: str = "unverified"  # unverified, verified, invalid
    # SOTA: CrossRef metadata fields
    doi: str = ""
    journal: str = ""
    cited_by_count: int = 0
    crossref_resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "url": self.url,
            "title": self.title,
            "author": self.author,
            "publication_date": self.publication_date,
            "source_type": self.source_type,
            "snippet": self.snippet,
            "verification_status": self.verification_status,
            "doi": self.doi,
            "journal": self.journal,
            "cited_by_count": self.cited_by_count,
            "crossref_resolved": self.crossref_resolved,
        }

    def enrich_from_crossref(self) -> bool:
        """
        SOTA: Enrich citation metadata from CrossRef API.

        Attempts to resolve DOI and fill in missing metadata.

        Returns:
            True if successfully enriched, False otherwise
        """
        if not CROSSREF_AVAILABLE:
            return False

        # Try to extract DOI from URL if not set
        if not self.doi and self.url:
            extracted_doi = extract_doi_from_url(self.url)
            if extracted_doi:
                self.doi = extracted_doi

        # If we have a DOI, try to resolve via CrossRef
        if self.doi:
            try:
                citation = resolve_doi_sync(self.doi)
                if citation:
                    # Update fields with CrossRef data (don't overwrite existing)
                    if not self.title or self.title == "Untitled":
                        self.title = citation.title
                    if not self.author or self.author == "Unknown":
                        self.author = ", ".join(citation.authors[:3])
                        if len(citation.authors) > 3:
                            self.author += " et al."
                    if not self.publication_date and citation.year:
                        self.publication_date = str(citation.year)
                    if citation.journal:
                        self.journal = citation.journal
                    self.cited_by_count = citation.cited_by_count
                    self.source_type = "academic"
                    self.crossref_resolved = True
                    return True
            except Exception as e:
                logger.warning(f"CrossRef resolution failed for {self.doi}: {e}")

        return False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CitationSource":
        return cls(
            chunk_id=data.get("chunk_id", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            author=data.get("author", ""),
            publication_date=data.get("publication_date", ""),
            source_type=data.get("source_type", "web"),
            snippet=data.get("snippet", ""),
            verification_status=data.get("verification_status", "unverified"),
            # SOTA: CrossRef fields
            doi=data.get("doi", ""),
            journal=data.get("journal", ""),
            cited_by_count=data.get("cited_by_count", 0),
            crossref_resolved=data.get("crossref_resolved", False),
        )


@dataclass
class BlockedCitation:
    """Represents a blocked citation with reason."""
    chunk_id: str
    reason: str
    blocked_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "reason": self.reason,
            "blocked_at": self.blocked_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlockedCitation":
        return cls(
            chunk_id=data.get("chunk_id", ""),
            reason=data.get("reason", ""),
            blocked_at=data.get("blocked_at", ""),
        )


@dataclass
class CitationRegistry:
    """
    Registry for managing citations in research output.

    Tracks [CITE:chunk_id] markers and maps them to source metadata.
    Supports blocking citations that fail NLI verification (architecture.md 6.2).
    """
    vector_id: str
    sources: Dict[str, CitationSource] = field(default_factory=dict)
    citation_order: List[str] = field(default_factory=list)
    _verified_ids: Set[str] = field(default_factory=set)
    _blocked_citations: Dict[str, BlockedCitation] = field(default_factory=dict)

    def load_from_vwm(self) -> int:
        """
        Load citation metadata from VWM (ChromaDB).

        Returns:
            Number of sources loaded
        """
        try:
            chroma = get_chroma_manager()
            chroma.initialize_client()
            collection_name = f"vwm_{self.vector_id}"

            try:
                collection = chroma._client.get_collection(name=collection_name)
            except Exception as e:
                # LOW-111: Use logger instead of print
                logger.warning(f"Could not get VWM collection: {e}")
                return 0

            # Get all chunks in the collection
            results = collection.get(
                include=["documents", "metadatas"]
            )

            if not results or not results.get("ids"):
                return 0

            loaded = 0
            for i, chunk_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results.get("metadatas") else {}
                document = results["documents"][i] if results.get("documents") else ""

                source = CitationSource(
                    chunk_id=chunk_id,
                    url=metadata.get("source_url", metadata.get("url", "")),
                    title=metadata.get("title", ""),
                    author=metadata.get("author", ""),
                    publication_date=metadata.get("publication_date", metadata.get("date", "")),
                    source_type=metadata.get("source_type", "web"),
                    snippet=document[:300] if document else "",
                    verification_status="unverified",
                )

                self.sources[chunk_id] = source
                loaded += 1

            return loaded

        except Exception as e:
            # LOW-112: Use logger instead of print
            logger.warning(f"Failed to load from VWM: {e}")
            return 0

    def load_verified_ids(self, verified_ids: List[str]) -> None:
        """
        Mark specific chunk IDs as verified (from P6 NLI verification).

        Args:
            verified_ids: List of verified chunk IDs from P6
        """
        self._verified_ids = set(verified_ids)

        # Update verification status
        for chunk_id in verified_ids:
            if chunk_id in self.sources:
                self.sources[chunk_id].verification_status = "verified"

    def load_from_p6_output(self, vector_id: str) -> int:
        """
        Load verified IDs from P6 output file.

        Args:
            vector_id: Vector ID

        Returns:
            Number of verified IDs loaded
        """
        p6_dir = OUTPUTS_DIR / "P6"
        p6_files = list(p6_dir.glob(f"{vector_id}__P6__*.json"))

        if not p6_files:
            return 0

        try:
            with open(sorted(p6_files)[-1], 'r', encoding='utf-8') as f:
                p6_data = json.load(f)

            verified_ids = p6_data.get("verified_ids", [])
            self.load_verified_ids(verified_ids)
            return len(verified_ids)

        except Exception as e:
            # LOW-113: Use logger instead of print
            logger.warning(f"Failed to load P6 output: {e}")
            return 0

    # =========================================================================
    # CITATION BLOCKING (architecture.md Section 6.2)
    # =========================================================================

    def mark_blocked(self, evidence_id: str, reason: str) -> None:
        """
        Block a citation from appearing in final output.

        Per architecture.md Section 6.2, citations that fail NLI verification
        or have other issues should be blocked from the final report.

        Args:
            evidence_id: The chunk/evidence ID to block
            reason: Reason for blocking (e.g., "NLI contradiction detected")
        """
        blocked = BlockedCitation(
            chunk_id=evidence_id,
            reason=reason,
            blocked_at=datetime.now().isoformat(),
        )
        self._blocked_citations[evidence_id] = blocked

        # Update source verification status if exists
        if evidence_id in self.sources:
            self.sources[evidence_id].verification_status = "blocked"

    def is_blocked(self, evidence_id: str) -> bool:
        """
        Check if a citation is blocked.

        Args:
            evidence_id: The chunk/evidence ID to check

        Returns:
            True if blocked, False otherwise
        """
        return evidence_id in self._blocked_citations

    # =========================================================================
    # SOTA: CITATION VERIFICATION (Compare claim to source)
    # =========================================================================

    def verify_citation(
        self,
        chunk_id: str,
        claim_text: str,
        min_similarity: float = 0.70,
    ) -> Tuple[bool, float]:
        """
        SOTA: Verify that a citation actually supports the claim it's attached to.

        Computes semantic similarity between claim text and source chunk text.
        This prevents hallucinated or misattributed citations.

        Args:
            chunk_id: The chunk ID being cited
            claim_text: The sentence/claim using this citation
            min_similarity: Minimum similarity score required (default 0.70)

        Returns:
            Tuple of (is_verified, similarity_score)
        """
        if chunk_id not in self.sources:
            logger.debug(f"verify_citation: chunk_id {chunk_id} not in sources ({len(self.sources)} total)")
            return False, 0.0

        source = self.sources[chunk_id]
        source_text = source.snippet

        if not source_text:
            logger.debug(f"verify_citation: source {chunk_id} has no snippet text")
            return False, 0.0

        if not claim_text:
            logger.debug(f"verify_citation: no claim_text provided for {chunk_id}")
            return False, 0.0

        # Compute similarity using keyword overlap (fast heuristic)
        similarity = self._compute_similarity(claim_text, source_text)

        # Update verification status
        if similarity >= min_similarity:
            source.verification_status = "verified"
            self._verified_ids.add(chunk_id)
            return True, similarity
        else:
            source.verification_status = "low_similarity"
            return False, similarity

    def _compute_similarity(self, text_a: str, text_b: str) -> float:
        """
        Compute semantic similarity between two texts.

        Uses weighted keyword overlap with IDF-like weighting for
        content words vs common words.

        Args:
            text_a: First text
            text_b: Second text

        Returns:
            Similarity score between 0 and 1
        """
        # Stopwords for English
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
            'these', 'those', 'it', 'its', 'they', 'their', 'them', 'we', 'our',
            'you', 'your', 'he', 'she', 'his', 'her', 'which', 'who', 'whom',
            'what', 'where', 'when', 'how', 'why', 'all', 'each', 'every',
            'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not',
            'only', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now',
        }

        # Extract content words (3+ chars, not stopwords)
        def extract_words(text):
            words = re.findall(r'\b[a-z]{3,}\b', text.lower())
            return [w for w in words if w not in stopwords]

        words_a = set(extract_words(text_a))
        words_b = set(extract_words(text_b))

        if not words_a or not words_b:
            return 0.0

        # Jaccard similarity
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)

        jaccard = intersection / union if union > 0 else 0.0

        # Boost for domain-specific terms
        domain_terms = {
            'water', 'filter', 'filtration', 'contamination', 'pathogen',
            'bacteria', 'virus', 'drinking', 'quality', 'treatment', 'health',
            'disease', 'outbreak', 'source', 'well', 'groundwater', 'surface',
        }

        domain_a = words_a & domain_terms
        domain_b = words_b & domain_terms
        domain_overlap = len(domain_a & domain_b) / max(1, len(domain_a | domain_b))

        # Weighted combination
        similarity = 0.7 * jaccard + 0.3 * domain_overlap

        return round(min(1.0, similarity * 1.5), 4)  # Scale up slightly

    def verify_all_citations_in_text(
        self,
        text: str,
        min_similarity: float = 0.70,
    ) -> Dict[str, Tuple[bool, float]]:
        """
        SOTA: Verify all citations in a text against their sources.

        Extracts claim sentences around each citation and verifies them.

        Args:
            text: Text containing [N] citation markers
            min_similarity: Minimum similarity threshold

        Returns:
            Dict mapping chunk_id -> (is_verified, similarity_score)
        """
        results = {}

        # Find all citation markers and their surrounding context
        # Pattern: text [N] more text
        citation_pattern = r'([^.!?]*\[(\d+)\][^.!?]*[.!?]?)'

        for match in re.finditer(citation_pattern, text):
            claim_text = match.group(1).strip()
            citation_num = int(match.group(2))

            # Map citation number to chunk_id
            if citation_num <= len(self.citation_order):
                chunk_id = self.citation_order[citation_num - 1]
                is_verified, score = self.verify_citation(
                    chunk_id, claim_text, min_similarity
                )
                results[chunk_id] = (is_verified, score)

        return results

    def get_blocked_citations(self) -> List[Dict[str, Any]]:
        """
        Get all blocked citations with their reasons.

        Returns:
            List of blocked citation dictionaries
        """
        return [bc.to_dict() for bc in self._blocked_citations.values()]

    def get_blocked_count(self) -> int:
        """Get count of blocked citations."""
        return len(self._blocked_citations)

    def unblock(self, evidence_id: str) -> bool:
        """
        Unblock a previously blocked citation.

        Args:
            evidence_id: The chunk/evidence ID to unblock

        Returns:
            True if unblocked, False if wasn't blocked
        """
        if evidence_id in self._blocked_citations:
            del self._blocked_citations[evidence_id]
            if evidence_id in self.sources:
                self.sources[evidence_id].verification_status = "unverified"
            return True
        return False

    def load_blocked_from_p7_5(self, vector_id: str) -> int:
        """
        Load blocked citations from P7.5 claim verification output.

        Args:
            vector_id: Vector ID

        Returns:
            Number of blocked citations loaded
        """
        p7_5_dir = OUTPUTS_DIR / "P7_5"
        p7_5_files = list(p7_5_dir.glob(f"{vector_id}__P7_5__*.json"))

        if not p7_5_files:
            return 0

        try:
            with open(sorted(p7_5_files)[-1], 'r', encoding='utf-8') as f:
                p7_5_data = json.load(f)

            blocked_citations = p7_5_data.get("blocked_citations", [])
            for chunk_id in blocked_citations:
                self.mark_blocked(chunk_id, "Failed NLI verification in P7.5")

            return len(blocked_citations)

        except Exception as e:
            # LOW-114: Use logger instead of print
            logger.warning(f"Failed to load P7.5 output: {e}")
            return 0

    # =========================================================================
    # RESOLUTION AND REGISTRATION
    # =========================================================================

    def resolve(self, chunk_id: str) -> Optional[CitationSource]:
        """
        Resolve a chunk ID to its citation source.

        Args:
            chunk_id: The chunk ID to resolve

        Returns:
            CitationSource if found, None otherwise
        """
        return self.sources.get(chunk_id)

    def register_citation(self, chunk_id: str) -> int:
        """
        Register a citation and return its citation number.

        Citations are numbered in order of first appearance.

        Args:
            chunk_id: The chunk ID being cited

        Returns:
            Citation number (1-indexed)
        """
        if chunk_id not in self.citation_order:
            self.citation_order.append(chunk_id)

        return self.citation_order.index(chunk_id) + 1

    def get_citation_number(self, chunk_id: str) -> Optional[int]:
        """
        Get the citation number for a chunk ID.

        Args:
            chunk_id: The chunk ID

        Returns:
            Citation number (1-indexed) or None if not registered
        """
        if chunk_id in self.citation_order:
            return self.citation_order.index(chunk_id) + 1
        return None

    # =========================================================================
    # ISSUE B FIX: URL DEDUPLICATION
    # =========================================================================

    def get_url_to_canonical_chunk(self) -> Dict[str, str]:
        """
        Build a mapping from URL to canonical chunk_id.

        When multiple chunks have the same URL, the first registered one
        becomes the canonical citation for that URL.

        Returns:
            Dict mapping URL -> canonical chunk_id
        """
        url_to_chunk: Dict[str, str] = {}

        for chunk_id in self.citation_order:
            source = self.resolve(chunk_id)
            if source and source.url:
                url = source.url.rstrip("/").lower()  # Normalize URL
                if url not in url_to_chunk:
                    url_to_chunk[url] = chunk_id

        return url_to_chunk

    def get_deduped_bibliography(self) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Get bibliography deduplicated by URL.

        ISSUE B FIX: Same URL should only appear once in bibliography.
        Returns a mapping from chunk_id to canonical citation number.

        Returns:
            Tuple of (bibliography_entries, chunk_to_canonical_number)
        """
        url_to_canonical = self.get_url_to_canonical_chunk()

        # Build deduped bibliography
        bibliography = []
        canonical_chunks = set(url_to_canonical.values())

        # Mapping from any chunk_id to its canonical citation number
        chunk_to_number: Dict[str, int] = {}

        # Track chunks without URLs separately
        chunks_without_url = []

        citation_num = 1
        for chunk_id in self.citation_order:
            source = self.resolve(chunk_id)

            # Check if this chunk has a URL
            if source and source.url:
                if chunk_id in canonical_chunks:
                    entry = {
                        "number": citation_num,
                        "chunk_id": chunk_id,
                        "url": source.url,
                        "title": source.title or "Untitled",
                        "author": source.author or "Unknown",
                        "publication_date": source.publication_date or "",
                        "source_type": source.source_type or "web",
                        "verified": chunk_id in self._verified_ids,
                    }
                    bibliography.append(entry)
                    chunk_to_number[chunk_id] = citation_num
                    citation_num += 1
            else:
                # Chunk has no URL - track for separate numbering
                if chunk_id not in chunks_without_url:
                    chunks_without_url.append(chunk_id)

        # Map non-canonical chunks with URLs to their canonical number
        for url, canonical_chunk in url_to_canonical.items():
            canonical_num = chunk_to_number.get(canonical_chunk)
            if canonical_num:
                for chunk_id in self.citation_order:
                    source = self.resolve(chunk_id)
                    if source and source.url:
                        chunk_url = source.url.rstrip("/").lower()
                        if chunk_url == url and chunk_id not in chunk_to_number:
                            chunk_to_number[chunk_id] = canonical_num

        # Add chunks without URLs (each gets own number since no dedup possible)
        # FIX: Validate chunk_id format before adding - reject malformed IDs
        for chunk_id in chunks_without_url:
            if chunk_id not in chunk_to_number:
                # FIX-183F: Create degraded entry for malformed chunk IDs instead of skipping
                is_malformed = False
                if "," in chunk_id or "CITE:" in chunk_id or " " in chunk_id:
                    logger.warning(f"[FIX-183F] Malformed chunk_id, creating degraded entry: {chunk_id}")
                    is_malformed = True
                elif not chunk_id.startswith("chunk_") and not chunk_id.isalnum():
                    logger.warning(f"[FIX-183F] Invalid chunk_id format, creating degraded entry: {chunk_id}")
                    is_malformed = True
                if is_malformed:
                    entry = {
                        "number": citation_num,
                        "chunk_id": chunk_id,
                        "url": "",
                        "title": "[Reference unavailable]",
                        "malformed": True,
                    }
                    bibliography.append(entry)
                    chunk_to_number[chunk_id] = citation_num
                    citation_num += 1
                    continue

                source = self.resolve(chunk_id)
                # Generate meaningful title if source has none
                title = source.title if source and source.title else ""
                if not title or title.lower() in ["untitled", "unknown", ""]:
                    title = f"Source document {chunk_id[-5:]}"

                entry = {
                    "number": citation_num,
                    "chunk_id": chunk_id,
                    "url": "",
                    "title": title,
                    "author": source.author if source and source.author else "Unknown",
                    "publication_date": source.publication_date if source else "",
                    "source_type": source.source_type if source else "web",
                    "verified": chunk_id in self._verified_ids,
                }
                bibliography.append(entry)
                chunk_to_number[chunk_id] = citation_num
                citation_num += 1

        return bibliography, chunk_to_number

    def extract_citations(self, text: str) -> List[str]:
        """
        Extract all [CITE:chunk_id] markers from text.

        Args:
            text: Text containing citation markers

        Returns:
            List of chunk IDs found (in order of appearance)
        """
        pattern = r'\[CITE:([^\]]+)\]'
        matches = re.findall(pattern, text)
        return matches

    def bind_citations(
        self,
        text: str,
        format_style: str = "numbered",
        include_snippet: bool = False
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Replace [CITE:chunk_id] markers with formatted citations.

        Args:
            text: Text with [CITE:chunk_id] markers
            format_style: "numbered" ([1], [2]), "footnote" (superscript), "inline" (Author, Year)
            include_snippet: Whether to include snippet in bibliography

        Returns:
            Tuple of (bound_text, bibliography_entries)
        """
        # Extract all citations first to establish numbering
        chunk_ids = self.extract_citations(text)

        # Register all citations
        for chunk_id in chunk_ids:
            self.register_citation(chunk_id)

        # Replace markers based on format style
        def replace_marker(match):
            chunk_id = match.group(1)
            num = self.get_citation_number(chunk_id)
            source = self.resolve(chunk_id)

            if format_style == "numbered":
                return f"[{num}]"
            elif format_style == "footnote":
                return f"<sup>{num}</sup>"
            elif format_style == "inline":
                if source and source.author:
                    year = source.publication_date[:4] if source.publication_date else "n.d."
                    return f"({source.author}, {year})"
                return f"[{num}]"
            else:
                return f"[{num}]"

        pattern = r'\[CITE:([^\]]+)\]'
        bound_text = re.sub(pattern, replace_marker, text)

        # Build bibliography
        bibliography = []
        for chunk_id in self.citation_order:
            source = self.resolve(chunk_id)
            entry = {
                "number": self.get_citation_number(chunk_id),
                "chunk_id": chunk_id,
                "url": source.url if source else "",
                "title": source.title if source else "",
                "author": source.author if source else "",
                "publication_date": source.publication_date if source else "",
                "source_type": source.source_type if source else "web",
                "verified": chunk_id in self._verified_ids,
            }

            if include_snippet and source:
                entry["snippet"] = source.snippet

            bibliography.append(entry)

        return bound_text, bibliography

    def get_bibliography(self, format_style: str = "numbered") -> List[Dict[str, Any]]:
        """
        Get the full bibliography.

        Args:
            format_style: Citation format style

        Returns:
            List of bibliography entries
        """
        bibliography = []
        for i, chunk_id in enumerate(self.citation_order, 1):
            source = self.resolve(chunk_id)
            entry = {
                "number": i,
                "chunk_id": chunk_id,
                "url": source.url if source else "",
                "title": source.title if source else "",
                "author": source.author if source else "",
                "publication_date": source.publication_date if source else "",
                "verified": chunk_id in self._verified_ids,
            }
            bibliography.append(entry)

        return bibliography

    def validate_citations(self, text: str) -> Dict[str, Any]:
        """
        Validate all citations in text against the registry.

        Args:
            text: Text with [CITE:chunk_id] markers

        Returns:
            Validation report
        """
        chunk_ids = self.extract_citations(text)

        valid = []
        invalid = []
        verified = []
        unverified = []

        for chunk_id in set(chunk_ids):
            source = self.resolve(chunk_id)
            if source:
                valid.append(chunk_id)
                if chunk_id in self._verified_ids:
                    verified.append(chunk_id)
                else:
                    unverified.append(chunk_id)
            else:
                invalid.append(chunk_id)

        return {
            "total_citations": len(chunk_ids),
            "unique_citations": len(set(chunk_ids)),
            "valid_count": len(valid),
            "invalid_count": len(invalid),
            "verified_count": len(verified),
            "unverified_count": len(unverified),
            "valid_ids": valid,
            "invalid_ids": invalid,
            "verified_ids": verified,
            "unverified_ids": unverified,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_sources": len(self.sources),
            "citations_registered": len(self.citation_order),
            "verified_count": len(self._verified_ids),
            "blocked_count": len(self._blocked_citations),
            "source_types": self._count_source_types(),
        }

    def _count_source_types(self) -> Dict[str, int]:
        """Count sources by type."""
        counts = {}
        for source in self.sources.values():
            counts[source.source_type] = counts.get(source.source_type, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        """Serialize registry to dict."""
        return {
            "vector_id": self.vector_id,
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "citation_order": self.citation_order,
            "verified_ids": list(self._verified_ids),
            "blocked_citations": {k: v.to_dict() for k, v in self._blocked_citations.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CitationRegistry":
        """Deserialize registry from dict."""
        registry = cls(vector_id=data.get("vector_id", ""))
        registry.sources = {
            k: CitationSource.from_dict(v)
            for k, v in data.get("sources", {}).items()
        }
        registry.citation_order = data.get("citation_order", [])
        registry._verified_ids = set(data.get("verified_ids", []))
        registry._blocked_citations = {
            k: BlockedCitation.from_dict(v)
            for k, v in data.get("blocked_citations", {}).items()
        }
        return registry

    def enrich_from_crossref(self, max_citations: int = 50) -> int:
        """
        SOTA: Enrich citations with metadata from CrossRef API.

        Attempts to resolve DOIs and fill in missing metadata for
        all citations that have DOIs (or DOIs can be extracted from URLs).

        Args:
            max_citations: Maximum number of citations to enrich (for rate limiting)

        Returns:
            Number of citations successfully enriched
        """
        if not CROSSREF_AVAILABLE:
            logger.warning("CrossRef resolver not available")
            return 0

        enriched_count = 0
        processed = 0

        for chunk_id, source in self.sources.items():
            if processed >= max_citations:
                break

            # Skip if already enriched
            if source.crossref_resolved:
                continue

            # Try to extract DOI from URL if not set
            if not source.doi and source.url:
                extracted = extract_doi_from_url(source.url)
                if extracted:
                    source.doi = extracted

            # Skip if no DOI
            if not source.doi:
                continue

            processed += 1

            # Try to enrich via CrossRef
            if source.enrich_from_crossref():
                enriched_count += 1
                logger.debug(f"Enriched {chunk_id} via CrossRef: {source.title[:50]}...")

        if enriched_count > 0:
            logger.info(f"CrossRef enriched {enriched_count}/{processed} citations")

        return enriched_count

    def save(self, output_path: Path) -> None:
        """Save registry to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, input_path: Path) -> "CitationRegistry":
        """Load registry from JSON file."""
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_citation_registry(
    vector_id: str,
    load_vwm: bool = True,
    load_verified: bool = True
) -> CitationRegistry:
    """
    Factory function to create and initialize a CitationRegistry.

    Args:
        vector_id: Vector ID for the research
        load_vwm: Whether to load sources from VWM
        load_verified: Whether to load verified IDs from P6

    Returns:
        Initialized CitationRegistry
    """
    registry = CitationRegistry(vector_id=vector_id)

    if load_vwm:
        count = registry.load_from_vwm()
        print(f"  Loaded {count} sources from VWM")

    if load_verified:
        count = registry.load_from_p6_output(vector_id)
        print(f"  Loaded {count} verified IDs from P6")

    return registry


# ============================================================================
# SELF-TEST
# ============================================================================

def self_test():
    """Run self-tests for CitationRegistry."""
    print("\nRunning CitationRegistry self-tests...")

    # Test 1: Basic registry creation
    registry = CitationRegistry(vector_id="TEST_VECTOR")
    assert registry.vector_id == "TEST_VECTOR"
    assert len(registry.sources) == 0
    print("  [PASS] Registry creation")

    # Test 2: Add sources manually
    source1 = CitationSource(
        chunk_id="chunk_001",
        url="https://example.com/article1",
        title="Test Article 1",
        author="John Doe",
        publication_date="2024-01-15",
        source_type="web",
    )
    source2 = CitationSource(
        chunk_id="chunk_002",
        url="https://example.com/article2",
        title="Test Article 2",
        author="Jane Smith",
        publication_date="2024-02-20",
        source_type="academic",
    )

    registry.sources["chunk_001"] = source1
    registry.sources["chunk_002"] = source2

    assert len(registry.sources) == 2
    print("  [PASS] Adding sources")

    # Test 3: Resolve citation
    resolved = registry.resolve("chunk_001")
    assert resolved is not None
    assert resolved.title == "Test Article 1"
    assert registry.resolve("nonexistent") is None
    print("  [PASS] Citation resolution")

    # Test 4: Register citations and get numbers
    num1 = registry.register_citation("chunk_001")
    num2 = registry.register_citation("chunk_002")
    num3 = registry.register_citation("chunk_001")  # Same as first

    assert num1 == 1
    assert num2 == 2
    assert num3 == 1  # Same citation should return same number
    print("  [PASS] Citation numbering")

    # Test 5: Extract citations from text
    text = "This is a claim [CITE:chunk_001] and another [CITE:chunk_002] and again [CITE:chunk_001]."
    extracted = registry.extract_citations(text)
    assert extracted == ["chunk_001", "chunk_002", "chunk_001"]
    print("  [PASS] Citation extraction")

    # Test 6: Bind citations
    registry2 = CitationRegistry(vector_id="TEST2")
    registry2.sources["chunk_001"] = source1
    registry2.sources["chunk_002"] = source2

    bound_text, bibliography = registry2.bind_citations(text, format_style="numbered")
    assert "[1]" in bound_text
    assert "[2]" in bound_text
    assert "CITE:" not in bound_text
    assert len(bibliography) == 2
    print("  [PASS] Citation binding")

    # Test 7: Load verified IDs
    registry2.load_verified_ids(["chunk_001"])
    assert "chunk_001" in registry2._verified_ids
    assert registry2.sources["chunk_001"].verification_status == "verified"
    print("  [PASS] Verified IDs loading")

    # Test 8: Validate citations
    validation = registry2.validate_citations(text)
    assert validation["valid_count"] == 2
    assert validation["invalid_count"] == 0
    assert validation["verified_count"] == 1
    print("  [PASS] Citation validation")

    # Test 9: Serialization
    data = registry2.to_dict()
    loaded = CitationRegistry.from_dict(data)
    assert loaded.vector_id == registry2.vector_id
    assert len(loaded.sources) == len(registry2.sources)
    print("  [PASS] Serialization/deserialization")

    # Test 10: Get bibliography
    bib = registry2.get_bibliography()
    assert len(bib) == 2
    assert bib[0]["number"] == 1
    assert bib[0]["verified"] == True
    print("  [PASS] Bibliography generation")

    print("\nAll CitationRegistry self-tests PASSED!")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Citation Registry")
    parser.add_argument("--vector-id", required=False, help="Vector ID")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        registry = create_citation_registry(args.vector_id)
        print(f"\nRegistry stats: {registry.get_stats()}")
    else:
        print("Usage: python citation_registry.py --vector-id <ID> or --self-test")
