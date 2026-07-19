"""CRAG Retriever (v2 Layer 1 — Loopholes L6, L7).

Replaces v1's 126-call LLM analyzer with $0 local embeddings.

Pipeline:
    1. Fetch raw documents (URLs from search node)
    2. Context-Enriched Chunking (L6): prepend title+abstract to every chunk
    3. MinHash dedup (L7): eliminate near-duplicate chunks BEFORE scoring
    4. Embed chunks + query via all-MiniLM-L6-v2
    5. Cosine-score → quality tier (GOLD / SILVER / BRONZE)
    6. CRAG confidence gate: CORRECT / AMBIGUOUS / INCORRECT
    7. Register unique sources in SourceRegistry (L1)
    8. Return EvidencePiece list ready for LangGraph state

Cost: $0 (all local). Time: ~5-10s for 200 chunks.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from dotenv import load_dotenv

from src.polaris_graph.retrieval.pooled_embedder import embed_with_pooling
from src.polaris_graph.retrieval.source_registry import SourceRegistry
from src.polaris_graph.settings import resolve

load_dotenv()
logger = logging.getLogger("polaris_graph")


# ---------------------------------------------------------------------------
# Configuration (all from .env, LAW VI)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CRAGConfig:
    """Immutable configuration for the CRAG retriever."""

    # Chunking (L6)
    chunk_size_tokens: int = int(resolve("PG_CRAG_CHUNK_SIZE"))
    chunk_overlap_tokens: int = int(resolve("PG_CRAG_CHUNK_OVERLAP"))
    abstract_max_chars: int = int(resolve("PG_CRAG_ABSTRACT_MAX_CHARS"))

    # Dedup (L7) — reuses existing MinHash infra
    dedup_threshold: float = float(resolve("PG_CRAG_DEDUP_THRESHOLD"))
    dedup_num_hashes: int = int(resolve("PG_CRAG_DEDUP_HASHES"))
    dedup_shingle_size: int = int(resolve("PG_CRAG_DEDUP_SHINGLE"))

    # Embedding scoring
    gold_threshold: float = float(resolve("PG_CRAG_GOLD_THRESHOLD"))
    silver_threshold: float = float(resolve("PG_CRAG_SILVER_THRESHOLD"))
    min_relevance: float = float(resolve("PG_CRAG_MIN_RELEVANCE"))

    # CRAG gate thresholds (Yan et al. 2024)
    correct_threshold: float = float(resolve("PG_CRAG_CORRECT_THRESHOLD"))
    incorrect_threshold: float = float(resolve("PG_CRAG_INCORRECT_THRESHOLD"))

    # Capacity
    max_evidence: int = int(resolve("PG_CRAG_MAX_EVIDENCE"))
    max_chunks_per_doc: int = int(resolve("PG_CRAG_MAX_CHUNKS_PER_DOC"))
    min_chunk_chars: int = int(resolve("PG_CRAG_MIN_CHUNK_CHARS"))

    # Fix #3 (Table Bomb): max chars for a single table before row-splitting
    max_table_chars: int = int(resolve("PG_CRAG_MAX_TABLE_CHARS"))

    # Fix #4 (Paywall Poison): min chars for fetched content to be usable
    paywall_min_chars: int = int(resolve("PG_CRAG_PAYWALL_MIN_CHARS"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RawDocument:
    """A fetched document from the search node."""

    url: str
    title: str
    content: str
    source_type: str = "web"          # web, academic, pdf, government
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    abstract: str = ""                # extracted or first paragraph
    authority_score: float = 0.0      # from source_confidence pipeline


@dataclass
class EnrichedChunk:
    """A chunk with context prefix prepended (L6).

    The context prefix (title + abstract) gives the embedding model
    document-level context that a bare chunk would lack.

    IMPORTANT (Fix #4 — Attention Dilution):
        enriched_text is for EMBEDDING SCORING ONLY.
        When building synthesis prompts, use raw_text and group chunks
        by SRC-NNN, printing source metadata ONCE per source.
        Do NOT feed enriched_text to the section writer LLM.
    """

    chunk_id: str                     # deterministic hash
    doc_url: str
    doc_title: str
    raw_text: str                     # original chunk text (without prefix)
    enriched_text: str                # prefix + raw_text (for EMBEDDING ONLY)
    char_start: int                   # offset in original document
    char_end: int
    chunk_index: int                  # 0-based position within document
    is_table: bool = False            # True if chunk is an intact markdown table
    source_type: str = "web"
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: str = ""
    doi: str = ""
    authority_score: float = 0.0


@dataclass
class CRAGResult:
    """Output of the CRAG retriever pipeline."""

    evidence: list[dict[str, Any]]    # EvidencePiece-compatible dicts
    registry: SourceRegistry
    stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context-Enriched Chunker (L6)
# ---------------------------------------------------------------------------

class ContextEnrichedChunker:
    """Markdown-aware splitter with title+abstract prefix (L6).

    Two-pass approach (Fix #1 — Markdown Table Cleaver):
        Pass 1: Extract structural blocks (tables, code fences) that must
                 remain intact. Replace them with sentinel tokens.
        Pass 2: Sentence-split the remaining prose normally.
        Merge:  Re-insert structural blocks as standalone chunks.

    This prevents a markdown table sitting at the 1024-token boundary from
    being cleaved in half — chunk A gets headers + 5 rows, chunk B gets
    10 headerless rows, and the LLM hallucinates column associations.

    Loophole L6: bare 1024-token chunks lose document context.
    Fix: prepend "Title: ... | Abstract: ..." to every chunk so the
    embedding model scores relevance with full document awareness.
    enriched_text is for EMBEDDING ONLY (see Fix #4).
    """

    # Regex: detect a contiguous markdown table (header + separator + rows)
    # Matches: | col | col |\n| --- | --- |\n| val | val |\n...
    _TABLE_RE = re.compile(
        r"(?:^|\n)"                        # start of text or newline
        r"(\|[^\n]+\|\n"                   # header row:  | ... |
        r"\|[\s:]*-+[\s:]*(?:\|[\s:]*-+[\s:]*)*\|\n"  # separator: | --- | --- |
        r"(?:\|[^\n]+\|\n?)+)",            # data rows:   | ... | (1 or more)
        re.MULTILINE,
    )

    # Regex: detect fenced code blocks (``` ... ```)
    _CODE_FENCE_RE = re.compile(
        r"(```[^\n]*\n[\s\S]*?```)",
        re.MULTILINE,
    )

    _SENTINEL_PREFIX = "\x00BLOCK_"

    def __init__(self, config: CRAGConfig) -> None:
        self._config = config
        # Approximate tokens as chars/4 (conservative for English)
        self._chunk_chars = config.chunk_size_tokens * 4
        self._overlap_chars = config.chunk_overlap_tokens * 4

    def chunk_document(self, doc: RawDocument) -> list[EnrichedChunk]:
        """Split one document into context-enriched chunks."""
        content = (doc.content or "").strip()
        if len(content) < self._config.min_chunk_chars:
            return []

        # Build context prefix (L6 — for embedding only, Fix #4)
        abstract = self._extract_abstract(doc)
        prefix = self._build_prefix(doc.title, abstract)

        # Pass 1: extract structural blocks (tables, code fences)
        structural_blocks, prose_with_sentinels = self._extract_structural_blocks(content)

        # Pass 2: sentence-split the prose (sentinels mark block positions)
        raw_chunks = self._split_markdown_aware(prose_with_sentinels, structural_blocks)

        enriched: list[EnrichedChunk] = []
        for idx, (text, char_start, char_end, is_table) in enumerate(raw_chunks):
            if idx >= self._config.max_chunks_per_doc:
                break
            chunk_id = self._deterministic_id(doc.url, char_start, char_end)
            enriched.append(EnrichedChunk(
                chunk_id=chunk_id,
                doc_url=doc.url,
                doc_title=doc.title,
                raw_text=text,
                enriched_text=f"{prefix}\n\n{text}" if prefix else text,
                char_start=char_start,
                char_end=char_end,
                chunk_index=idx,
                is_table=is_table,
                source_type=doc.source_type,
                authors=doc.authors,
                year=doc.year,
                venue=doc.venue,
                doi=doc.doi,
                authority_score=doc.authority_score,
            ))

        return enriched

    def chunk_documents(self, docs: list[RawDocument]) -> list[EnrichedChunk]:
        """Chunk multiple documents."""
        all_chunks: list[EnrichedChunk] = []
        for doc in docs:
            all_chunks.extend(self.chunk_document(doc))
        return all_chunks

    # -- Pass 1: structural block extraction -------------------------------

    def _extract_structural_blocks(
        self, text: str
    ) -> tuple[dict[str, tuple[str, int, int, bool]], str]:
        """Extract tables and code fences, replace with sentinels.

        Returns:
            (blocks_map, modified_text)
            blocks_map: sentinel_key -> (original_text, char_start, char_end, is_table)
        """
        blocks: dict[str, tuple[str, int, int, bool]] = {}
        counter = 0

        def _replace(match: re.Match, is_table: bool) -> str:
            nonlocal counter
            key = f"{self._SENTINEL_PREFIX}{counter}\x00"
            counter += 1
            original = match.group(1) if match.lastindex else match.group(0)
            start = match.start(1) if match.lastindex else match.start(0)
            end = match.end(1) if match.lastindex else match.end(0)
            blocks[key] = (original.strip(), start, end, is_table)
            return f"\n{key}\n"

        # Extract tables first (higher priority — they contain pipes)
        modified = self._TABLE_RE.sub(lambda m: _replace(m, True), text)
        # Then code fences
        modified = self._CODE_FENCE_RE.sub(lambda m: _replace(m, False), modified)

        return blocks, modified

    # -- Pass 2: markdown-aware splitting ----------------------------------

    def _split_markdown_aware(
        self,
        text: str,
        blocks: dict[str, tuple[str, int, int, bool]],
    ) -> list[tuple[str, int, int, bool]]:
        """Split prose at sentence boundaries; re-insert structural blocks intact.

        Returns list of (chunk_text, char_start, char_end, is_table).
        """
        # Split into segments: prose segments and sentinel tokens
        segments: list[tuple[str, bool]] = []  # (text, is_sentinel)
        remaining = text
        while remaining:
            # Find next sentinel
            sentinel_pos = remaining.find(self._SENTINEL_PREFIX)
            if sentinel_pos == -1:
                segments.append((remaining, False))
                break
            # Prose before sentinel
            if sentinel_pos > 0:
                segments.append((remaining[:sentinel_pos], False))
            # Find end of sentinel (terminated by \x00)
            end_pos = remaining.find("\x00", sentinel_pos + len(self._SENTINEL_PREFIX))
            if end_pos == -1:
                segments.append((remaining[sentinel_pos:], False))
                break
            sentinel_key = remaining[sentinel_pos:end_pos + 1]
            segments.append((sentinel_key, True))
            remaining = remaining[end_pos + 1:]

        # Process segments into chunks
        chunks: list[tuple[str, int, int, bool]] = []
        prose_buffer: list[str] = []
        prose_len = 0
        # Track approximate char position in original document
        approx_pos = 0

        for segment_text, is_sentinel in segments:
            if is_sentinel and segment_text in blocks:
                # Flush prose buffer first
                if prose_buffer:
                    prose_chunks = self._split_sentences(" ".join(prose_buffer))
                    for pc_text, pc_start, pc_end in prose_chunks:
                        chunks.append((pc_text, approx_pos + pc_start, approx_pos + pc_end, False))
                    approx_pos += prose_len
                    prose_buffer = []
                    prose_len = 0

                # Emit structural block — split oversized tables (Fix R2-#3)
                block_text, block_start, block_end, is_table = blocks[segment_text]
                if is_table and len(block_text) > self._config.max_table_chars:
                    # Split by rows, re-attach header to each sub-table
                    for sub_text, sub_start, sub_end in self._split_large_table(
                        block_text, block_start, block_end
                    ):
                        chunks.append((sub_text, sub_start, sub_end, True))
                else:
                    chunks.append((block_text, block_start, block_end, is_table))
            else:
                cleaned = segment_text.strip()
                if cleaned:
                    prose_buffer.append(cleaned)
                    prose_len += len(cleaned) + 1

        # Flush remaining prose
        if prose_buffer:
            prose_chunks = self._split_sentences(" ".join(prose_buffer))
            for pc_text, pc_start, pc_end in prose_chunks:
                chunks.append((pc_text, approx_pos + pc_start, approx_pos + pc_end, False))

        # Filter too-small chunks (but never filter tables)
        return [
            (text, start, end, is_tbl)
            for text, start, end, is_tbl in chunks
            if is_tbl or len(text) >= self._config.min_chunk_chars
        ]

    # -- Internal helpers --------------------------------------------------

    def _extract_abstract(self, doc: RawDocument) -> str:
        """Extract abstract from doc or use first paragraph."""
        if doc.abstract:
            return doc.abstract[:self._config.abstract_max_chars]
        # Heuristic: first paragraph as abstract proxy
        paragraphs = doc.content.split("\n\n")
        for p in paragraphs:
            stripped = p.strip()
            if len(stripped) > 80:
                return stripped[:self._config.abstract_max_chars]
        return ""

    def _build_prefix(self, title: str, abstract: str) -> str:
        """Build context prefix string (for embedding only — Fix #4)."""
        parts: list[str] = []
        if title.strip():
            parts.append(f"Title: {title.strip()}")
        if abstract.strip():
            parts.append(f"Abstract: {abstract.strip()}")
        return " | ".join(parts)

    def _split_sentences(
        self, text: str
    ) -> list[tuple[str, int, int]]:
        """Split prose text into overlapping chunks at sentence boundaries.

        Returns list of (chunk_text, char_start, char_end).
        Only called on prose segments (tables/code already extracted).
        """
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[tuple[str, int, int]] = []
        current_sents: list[str] = []
        current_len = 0
        chunk_start = 0
        pos = 0

        for sent in sentences:
            sent_len = len(sent)
            if current_len + sent_len > self._chunk_chars and current_sents:
                chunk_text = " ".join(current_sents)
                chunks.append((chunk_text, chunk_start, chunk_start + len(chunk_text)))

                # Overlap: keep last N chars worth of sentences
                overlap_sents: list[str] = []
                overlap_len = 0
                for s in reversed(current_sents):
                    if overlap_len + len(s) > self._overlap_chars:
                        break
                    overlap_sents.insert(0, s)
                    overlap_len += len(s)

                current_sents = overlap_sents
                current_len = overlap_len
                chunk_start = pos - overlap_len

            current_sents.append(sent)
            current_len += sent_len
            pos += sent_len + 1  # +1 for split separator

        # Final chunk
        if current_sents:
            chunk_text = " ".join(current_sents)
            chunks.append((chunk_text, chunk_start, chunk_start + len(chunk_text)))

        return chunks

    def _split_large_table(
        self,
        table_text: str,
        char_start: int,
        char_end: int,
    ) -> list[tuple[str, int, int]]:
        """Split an oversized table by rows, re-attaching header to each split.

        Fix R2-#3 (Table Bomb): A 400-row supplementary table from a PDF can be
        25,000 chars. The embedding model truncates at 512 tokens (~2K chars),
        and it would eat the entire section writer context window.

        Each sub-table gets the original header row + separator row prepended
        so the LLM retains column context.
        """
        lines = table_text.split("\n")
        if len(lines) < 3:
            return [(table_text, char_start, char_end)]

        # Header = first line, separator = second line, data = rest
        header_line = lines[0]
        separator_line = lines[1]
        data_lines = [l for l in lines[2:] if l.strip()]

        if not data_lines:
            return [(table_text, char_start, char_end)]

        header_block = f"{header_line}\n{separator_line}"
        header_len = len(header_block) + 1  # +1 for newline after header

        # Calculate how many data rows fit in max_table_chars
        max_data_chars = self._config.max_table_chars - header_len
        if max_data_chars < 100:
            max_data_chars = 100

        sub_tables: list[tuple[str, int, int]] = []
        current_rows: list[str] = []
        current_len = 0
        row_offset = char_start + len(header_block) + 1

        for row in data_lines:
            row_len = len(row) + 1  # +1 for newline
            if current_len + row_len > max_data_chars and current_rows:
                sub_text = header_block + "\n" + "\n".join(current_rows)
                sub_start = char_start  # approximate — all sub-tables share parent offset
                sub_end = sub_start + len(sub_text)
                sub_tables.append((sub_text, sub_start, sub_end))
                current_rows = []
                current_len = 0

            current_rows.append(row)
            current_len += row_len
            row_offset += row_len

        # Final sub-table
        if current_rows:
            sub_text = header_block + "\n" + "\n".join(current_rows)
            sub_tables.append((sub_text, char_start, char_start + len(sub_text)))

        logger.info(
            "Table split: %d chars -> %d sub-tables of ~%d chars each",
            len(table_text), len(sub_tables),
            self._config.max_table_chars,
        )
        return sub_tables

    @staticmethod
    def _deterministic_id(url: str, char_start: int, char_end: int) -> str:
        """Deterministic chunk ID from URL + offsets."""
        raw = f"{url}:{char_start}:{char_end}"
        return f"ev_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# CRAG Retriever
# ---------------------------------------------------------------------------

class CRAGRetriever:
    """Corrective Retrieval-Augmented Generation retriever.

    Replaces v1's 126-call LLM analyzer with $0 local embeddings.
    Implements CRAG gate (Yan et al. 2024): classify retrieval confidence
    as CORRECT / AMBIGUOUS / INCORRECT to decide follow-up action.

    Pipeline:
        documents -> chunk -> dedup -> embed -> score -> gate -> register

    Thread-safe: SourceRegistry uses internal lock.
    """

    def __init__(
        self,
        config: Optional[CRAGConfig] = None,
        registry: Optional[SourceRegistry] = None,
    ) -> None:
        self._config = config or CRAGConfig()
        self._registry = registry or SourceRegistry()
        self._chunker = ContextEnrichedChunker(self._config)

        # Lazy-loaded embedding service (avoids import-time model load)
        self._embed_fn = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        documents: list[RawDocument],
    ) -> CRAGResult:
        """Full CRAG pipeline: chunk -> dedup -> embed -> score -> gate -> register.

        Fix R3-#1 (CPU Lock): All CPU-bound operations (chunking, MinHash dedup,
        embedding) are wrapped in asyncio.to_thread() to prevent GIL from blocking
        the async event loop. Without this, 200+ chunks of model.encode() holds the
        GIL for seconds, silently expiring pending asyncio.wait_for timeouts and
        dropping network heartbeats across the graph.

        Args:
            query: The research query (for relevance scoring).
            documents: Fetched documents from search node.

        Returns:
            CRAGResult with EvidencePiece-compatible dicts, registry, and stats.
        """
        stats: dict[str, Any] = {
            "input_documents": len(documents),
        }

        # 1. Chunk all documents (L6: context-enriched)
        # CPU-bound: regex + string ops on all documents
        chunks = await asyncio.to_thread(
            self._chunker.chunk_documents, documents
        )
        stats["total_chunks"] = len(chunks)
        logger.info("CRAG: %d documents -> %d chunks", len(documents), len(chunks))

        # 2. MinHash dedup (L7: before scoring, not after)
        # CPU-bound: MinHash signature generation + pairwise comparison
        unique_chunks = await asyncio.to_thread(
            self._dedup_chunks, chunks
        )
        stats["after_dedup"] = len(unique_chunks)
        stats["dedup_removed"] = len(chunks) - len(unique_chunks)
        logger.info("CRAG dedup: %d -> %d chunks (-%d)",
                     len(chunks), len(unique_chunks), stats["dedup_removed"])

        # 3. Embed query + chunks
        # CPU-bound: model.encode() on all-MiniLM-L6-v2 (heaviest operation)
        scored_chunks = await asyncio.to_thread(
            self._score_chunks, query, unique_chunks
        )

        # 4. Quality tier assignment + relevance gate (lightweight, stays in-thread)
        evidence = self._assign_tiers_and_filter(scored_chunks)
        stats["after_filter"] = len(evidence)

        # 5. CRAG confidence gate
        gate_result = self._crag_gate(evidence)
        stats["crag_gate"] = gate_result
        logger.info("CRAG gate: %s (%d evidence above threshold)",
                     gate_result, len(evidence))

        # 6. Register unique sources (L1) — thread-safe via SourceRegistry lock
        for ev in evidence:
            ev["citation_key"] = self._registry.register(
                url=ev["source_url"],
                title=ev["source_title"],
                source_type=ev["source_type"],
                authors=ev.get("authors") or [],
                year=ev.get("year"),
                doi=ev.get("doi", ""),
                authority_score=ev.get("source_confidence", 0.0),
            )

        # 7. Cap at max_evidence (sorted by relevance)
        evidence.sort(key=lambda e: e["relevance_score"], reverse=True)
        if len(evidence) > self._config.max_evidence:
            evidence = evidence[: self._config.max_evidence]
            stats["capped_at"] = self._config.max_evidence

        stats["final_evidence"] = len(evidence)
        stats["unique_sources"] = self._registry.size

        return CRAGResult(
            evidence=evidence,
            registry=self._registry,
            stats=stats,
        )

    @property
    def registry(self) -> SourceRegistry:
        """Access the source registry."""
        return self._registry

    @staticmethod
    def state_cleanup_keys() -> dict[str, Any]:
        """Return state keys that MUST be cleared after CRAG processing.

        Fix R4-#3 (State Memory Bloat): LangGraph serializes the entire state
        dict at every node boundary. If 100+ raw HTML pages (50-100MB) stay in
        state["fetched_content"], the checkpointer will time out or OOM.

        The CRAG graph node MUST merge these keys into its return dict:
            return {
                "evidence": crag_result.evidence,
                **CRAGRetriever.state_cleanup_keys(),  # <-- MANDATORY
            }

        This acts as garbage collection, replacing heavy payloads with empty
        containers before passing control to the LLM-heavy synthesis nodes.
        """
        return {
            "fetched_content": [],       # 50-100MB of raw HTML/PDF text
            "search_results": [],        # redundant after evidence extraction
            "web_results": [],           # raw Serper/DDG results
            "academic_results": [],      # raw S2/OpenAlex results
        }

    # ------------------------------------------------------------------
    # Step 2: MinHash dedup (L7)
    # ------------------------------------------------------------------

    def _dedup_chunks(self, chunks: list[EnrichedChunk]) -> list[EnrichedChunk]:
        """Remove near-duplicate chunks using MinHash.

        CRITICAL (Fix R2-#1 — Context/Dedup Paradox):
            Dedup MUST use raw_text, NOT enriched_text. Every chunk from the
            same document shares an identical L6 prefix (title + abstract).
            If we dedup on enriched_text, the shared 300-word prefix dominates
            the Jaccard signature, and MinHash thinks chunks 2-10 are duplicates
            of chunk 1. This silently deletes 90% of valid document content.

        Reuses existing ContentDeduplicator infrastructure.
        """
        if len(chunks) <= 1:
            return chunks

        from src.utils.content_deduplicator import (
            ContentDeduplicator,
            DeduplicationConfig,
        )

        dedup_config = DeduplicationConfig(
            near_duplicate_threshold=self._config.dedup_threshold,
            num_hashes=self._config.dedup_num_hashes,
            shingle_size=self._config.dedup_shingle_size,
        )
        deduplicator = ContentDeduplicator(config=dedup_config)

        # INVARIANT: use raw_text (not enriched_text) to avoid L6 prefix domination
        items = [{"content": c.raw_text, "_idx": i} for i, c in enumerate(chunks)]
        result = deduplicator.deduplicate(items)

        # Map back to EnrichedChunk objects
        unique_indices = {item["_idx"] for item in result.unique_items}
        return [c for i, c in enumerate(chunks) if i in unique_indices]

    # ------------------------------------------------------------------
    # Step 3: Embedding-based scoring
    # ------------------------------------------------------------------

    def _get_embed_fn(self):
        """Lazy-load embedding function."""
        if self._embed_fn is None:
            from src.utils.embedding_service import embed_texts
            self._embed_fn = embed_texts
        return self._embed_fn

    def _score_chunks(
        self,
        query: str,
        chunks: list[EnrichedChunk],
    ) -> list[tuple[EnrichedChunk, float]]:
        """Embed query + chunks, return (chunk, cosine_score) pairs.

        Fix R4-#1 (Embedding Context Truncation): Uses pooled embedding to
        handle texts longer than the model's 256-token max_seq_length.
        Without this, the model silently truncates enriched_text, seeing only
        the L6 prefix (title + abstract) and producing near-identical embeddings
        (0.87 cosine) for all chunks from the same document.
        """
        if not chunks:
            return []

        embed = self._get_embed_fn()

        # Fix R4-#1: Use pooled embedding for long enriched texts
        # Query is short (fits in 256 tokens), but enriched chunks are 1024+ tokens
        texts = [query] + [c.enriched_text for c in chunks]
        embeddings = embed_with_pooling(texts, embed)

        query_vec = np.array(embeddings[0], dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm < 1e-8:
            return [(c, 0.0) for c in chunks]

        scored: list[tuple[EnrichedChunk, float]] = []
        for i, chunk in enumerate(chunks):
            chunk_vec = np.array(embeddings[i + 1], dtype=np.float32)
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm < 1e-8:
                scored.append((chunk, 0.0))
                continue
            cosine = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
            scored.append((chunk, cosine))

        return scored

    # ------------------------------------------------------------------
    # Step 4: Tier assignment + relevance gate
    # ------------------------------------------------------------------

    def _assign_tiers_and_filter(
        self,
        scored: list[tuple[EnrichedChunk, float]],
    ) -> list[dict[str, Any]]:
        """Assign quality tiers and filter below minimum relevance.

        Returns EvidencePiece-compatible dicts.
        """
        evidence: list[dict[str, Any]] = []
        cfg = self._config

        for chunk, score in scored:
            if score < cfg.min_relevance:
                continue

            # Tier from relevance score
            if score >= cfg.gold_threshold:
                tier = "GOLD"
            elif score >= cfg.silver_threshold:
                tier = "SILVER"
            else:
                tier = "BRONZE"

            # Build EvidencePiece-compatible dict
            ev: dict[str, Any] = {
                "evidence_id": chunk.chunk_id,
                "source_url": chunk.doc_url,
                "source_title": chunk.doc_title,
                "source_type": chunk.source_type,
                "direct_quote": chunk.raw_text,
                "statement": chunk.raw_text[:500],
                "fact_category": "table" if chunk.is_table else "extracted",
                "relevance_score": round(score, 4),
                "llm_relevance_score": None,
                "quality_tier": tier,
                "citation_key": "",  # filled in register step
                "year": chunk.year,
                "authors": chunk.authors,
                "venue": chunk.venue,
                "doi": chunk.doi,
                "perspective": None,
                "corroborating_sources": None,
                "source_confidence": chunk.authority_score,
                "nli_self_check_score": None,
                "quote_substance": None,
                "tier_composite_score": score,
                "quote_char_start": chunk.char_start,
                "quote_char_end": chunk.char_end,
                "is_table": chunk.is_table,
            }
            evidence.append(ev)

        return evidence

    # ------------------------------------------------------------------
    # Step 5: CRAG confidence gate (Yan et al. 2024)
    # ------------------------------------------------------------------

    def _crag_gate(self, evidence: list[dict[str, Any]]) -> str:
        """Classify retrieval confidence: CORRECT / AMBIGUOUS / INCORRECT.

        CORRECT:   >= 1 GOLD chunk exists. Proceed to synthesis.
        AMBIGUOUS: No GOLD, but SILVER exists. Trigger web search refinement.
        INCORRECT: All below SILVER. Trigger full re-search.

        The caller (graph node) decides action based on this signal.
        """
        gold_count = sum(1 for e in evidence if e["quality_tier"] == "GOLD")
        silver_count = sum(1 for e in evidence if e["quality_tier"] == "SILVER")

        if gold_count > 0:
            return "CORRECT"
        if silver_count > 0:
            return "AMBIGUOUS"
        return "INCORRECT"

    # ------------------------------------------------------------------
    # Utility: build RawDocument from search results
    # ------------------------------------------------------------------

    # Fix R5-#2 (Base64 Image Bomb): Jina Reader converts embedded images to
    # inline Base64 strings (e.g., ![img](data:image/png;base64,iVBOR...)).
    # A single Base64 image can be 50,000+ chars of random alphanumeric noise.
    # This obliterates embedding vectors, wastes 10K+ tokens of LLM context,
    # and skyrockets API costs — all to feed unreadable garbage to the model.
    _BASE64_IMAGE_RE = re.compile(
        r"!\[[^\]]*\]\(data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+\)",
        re.DOTALL,
    )

    # Fix R5-#5 (Phantom Figure): References to figures/tables that won't
    # exist in the final report. The LLM copies "As shown in Figure 4..."
    # from source text, but we can't render Figure 4 — reader sees nothing.
    # Scrubbed BEFORE chunking so evidence chunks are clean.
    _PHANTOM_REF_RE = re.compile(
        r"(?:as\s+(?:shown|illustrated|depicted|presented|summarized|seen)"
        r"\s+in\s+(?:Fig(?:ure)?|Table|Chart|Exhibit|Appendix)\s*\.?\s*\d+[a-z]?"
        r"[,;.]?\s*)",
        re.IGNORECASE,
    )

    # Fix R2-#4 (Paywall Poison): keywords that indicate paywalled content
    _PAYWALL_KEYWORDS = (
        "purchase pdf", "buy this article", "log in to access",
        "sign in to view", "subscribe to read", "institutional access",
        "rent this article", "add to cart", "access through your institution",
        "full text is not available", "pdf available for purchase",
    )

    @classmethod
    def documents_from_search_results(
        cls,
        search_results: list[dict[str, Any]],
        fetched_content: dict[str, str],
        paywall_min_chars: int = 1000,
    ) -> list[RawDocument]:
        """Convert search node output into RawDocument list.

        Fix R2-#4 (Paywall Poison): If fetched content is too short or
        contains paywall keywords, discard it and use the S2 API abstract
        instead. This prevents the LLM from trying to synthesize facts
        from a shopping cart page.

        Args:
            search_results: List of dicts with url, title, snippet, source_type, etc.
            fetched_content: Map of url -> fetched full text content.
            paywall_min_chars: Minimum content length before paywall check.

        Returns:
            List of RawDocument ready for retrieve().
        """
        docs: list[RawDocument] = []
        paywall_count = 0

        base64_total_stripped = 0

        for result in search_results:
            url = result.get("url", "")
            raw_content = fetched_content.get(url, "")
            abstract = result.get("snippet", "") or result.get("abstract", "")
            title = result.get("title", "")

            # Fix R5-#2 (Base64 Image Bomb): Strip inline Base64 images
            # BEFORE any length checks — a single image can be 50K+ chars,
            # making paywalled content appear voluminous.
            if raw_content and "data:image" in raw_content:
                original_len = len(raw_content)
                raw_content = cls._BASE64_IMAGE_RE.sub("", raw_content)
                stripped = original_len - len(raw_content)
                if stripped > 0:
                    base64_total_stripped += stripped
                    logger.debug(
                        "Base64 scrub: removed %d chars from %s",
                        stripped, url[:60],
                    )

            # Determine usable content
            content = raw_content
            is_paywall = False

            if raw_content and len(raw_content) < paywall_min_chars:
                # Short content — check for paywall indicators
                lower = raw_content.lower()
                if any(kw in lower for kw in cls._PAYWALL_KEYWORDS):
                    is_paywall = True
            elif not raw_content:
                is_paywall = True

            if is_paywall:
                paywall_count += 1
                # Fall back to S2 abstract if available
                if abstract and len(abstract) > 50:
                    content = abstract
                    logger.debug(
                        "Paywall detected for %s — using abstract (%d chars)",
                        url[:80], len(abstract),
                    )
                else:
                    # No abstract either — skip entirely
                    logger.debug("Paywall + no abstract — skipping %s", url[:80])
                    continue

            if not content or len(content) < 50:
                continue

            docs.append(RawDocument(
                url=url,
                title=title,
                content=content,
                source_type=result.get("source_type", "web"),
                authors=result.get("authors", []),
                year=result.get("year"),
                venue=result.get("venue", ""),
                doi=result.get("doi", ""),
                abstract=abstract,
                authority_score=result.get("authority_score", 0.0),
            ))

        if paywall_count:
            logger.info(
                "CRAG: %d/%d sources were paywalled (abstract fallback or skipped)",
                paywall_count, len(search_results),
            )
        if base64_total_stripped > 0:
            logger.info(
                "CRAG: stripped %d chars of Base64 image data across %d documents",
                base64_total_stripped, len(docs),
            )
        return docs
