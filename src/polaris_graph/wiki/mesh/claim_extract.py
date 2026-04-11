"""
Mesh claim extraction — L2 write path.

Takes a source_page row + its body text, calls the LLM to extract
atomic facts, filters garbage, computes body-relative char spans,
assigns tiers, and inserts the result as `claims` rows via MeshStore.

Design (per advisor CP-A):

  - REUSE the production schemas (`AtomicFact`, `SourceAnalysis`,
    `SourceAnalysisBatch`) from `src.polaris_graph.schemas`. Those have
    40+ runs of Qwen field-name normalization baked into their
    `@model_validator(mode="before")` methods — rewriting them would
    introduce silent parsing bugs.

  - REUSE the `ANALYSIS_SYSTEM` prompt from
    `src.polaris_graph.agents.analyzer`. Duplicating it creates drift
    between copies and breaks one while fixing the other.

  - SPLIT into two layers for testability:
      `_parse_batch_to_claims(parsed, source_body, ...) -> list[dict]`
          Pure function. No I/O. Takes a SourceAnalysisBatch, returns
          a list of claim dicts ready for `store.insert_claim()`.
      `extract_claims_from_source(client, store, ...) -> list[str]`
          Orchestrator. Reads body from disk, calls LLM, parses,
          inserts, returns claim IDs.
    The parser covers 80% of the test surface without any LLM mocking.

  - char_start / char_end are relative to the source BODY (the text
    after ingest.py's markdown header). Downstream drill-down code
    must read the body via `ingest.read_source_text`, not raw file
    reads. See the comment in `ingest.py` near `_HEADER_TERMINATOR`.

  - Unverifiable quotes are NOT dropped — they get a sentinel span
    `char_start=0, char_end=1` and a BRONZE tier. Dropping claims
    because the LLM paraphrased slightly would replicate the
    "NLI too strict for niche domains" failure mode from memory.

  - Tier assignment: 3 signals for v1.
      GOLD   = relevance >= 0.7 AND source_quality >= 0.6 AND verified
      SILVER = relevance >= 0.4 (if verified) OR relevance >= 0.5 (unverified)
      BRONZE = everything else
    The full 5-signal production tier logic is deferred to Unit 4
    where edge discovery provides corroboration-count inputs.

  - has_numeric detection runs against direct_quote — a cheap regex
    catching CIs, p-values, effect sizes, sample sizes, percentages.

  - Filters ported from analyzer.py::_analyze_batch:
      - statement shorter than 10 chars → skip
      - quote with fewer than PG_MIN_QUOTE_WORDS words → skip
      - URL fragment in quote → skip
      - cookie / consent boilerplate in quote → skip

  - NOT ported (production-pipeline specific):
      - fetch_method propagation
      - citation_count propagation
      - STORM perspective_source tagging
      - source_content_store writes
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Protocol

import numpy as np

from src.polaris_graph.agents.analyzer import ANALYSIS_SYSTEM
from src.polaris_graph.schemas import SourceAnalysisBatch

from .ingest import read_source_text
from .store import EMBEDDING_DIM, MeshStore, MeshStoreError

logger = logging.getLogger(__name__)


# ───── constants (mirroring analyzer.py) ─────

PG_MIN_QUOTE_WORDS = int(os.getenv("PG_MIN_QUOTE_WORDS", "15"))
PG_MIN_STATEMENT_LEN = int(os.getenv("PG_MIN_STATEMENT_LEN", "10"))
PG_CONTENT_PER_SOURCE = int(os.getenv("PG_CONTENT_PER_SOURCE", "25000"))
PG_EXTRACTION_MAX_TOKENS = int(os.getenv("PG_EXTRACTION_MAX_TOKENS", "16384"))
PG_EXTRACTION_TIMEOUT = int(os.getenv("PG_EXTRACTION_TIMEOUT", "180"))

# Sentinel char span for claims whose direct_quote could not be located
# in the source body. Store's CHECK constraint requires char_end > char_start,
# so (0, 1) is the minimum legal span.
UNVERIFIED_CHAR_START = 0
UNVERIFIED_CHAR_END = 1

# Regex patterns for the URL / cookie / nav filters ported from
# analyzer.py::_analyze_batch (lines 2063-2075).
_URL_MARKERS = ("http://", "https://", ".com/", ".gov/", ".org/", ".edu/", "www.")
_COOKIE_MARKERS = (
    "cookie", "advertising", "track the user", "consent", "privacy policy",
)

# has_numeric detector: 95% CI, p-values, sample sizes, effect sizes,
# percentages with decimals, confidence interval ranges.
_NUMERIC_PATTERN = re.compile(
    r"(?:95\s*%\s*CI|p\s*[<>=]\s*0?\.\d|n\s*=\s*\d|±\s*\d|"
    r"\d+\.\d+\s*%|(?:OR|HR|RR|SMD|WMD|MD)\s*[:=]\s*[-\d])",
    re.IGNORECASE,
)


# ───── client protocol (for typing, not enforcement) ─────

class _LLMClient(Protocol):
    """Minimal protocol — matches `OpenRouterClient.generate_structured`.

    Tests inject a mock that implements just this method; production code
    passes the real `OpenRouterClient` instance.
    """

    async def generate_structured(
        self,
        *,
        prompt: str,
        schema: Any,
        system: str,
        max_tokens: int,
        timeout: int,
        reasoning_enabled: bool,
    ) -> Any: ...  # returns a SourceAnalysisBatch


# ───── extraction result dataclass ─────

class ExtractionResult:
    """Bundle returned from extract_claims_from_source.

    Attributes:
        inserted_claim_ids: list of claim IDs written to the store
        skipped: counts per reason (for observability)
        total_facts_seen: how many atomic_facts the LLM returned
    """
    __slots__ = ("inserted_claim_ids", "skipped", "total_facts_seen")

    def __init__(self) -> None:
        self.inserted_claim_ids: list[str] = []
        self.skipped: dict[str, int] = {
            "short_statement": 0,
            "short_quote": 0,
            "url_fragment": 0,
            "cookie_text": 0,
        }
        self.total_facts_seen: int = 0

    def as_dict(self) -> dict:
        return {
            "inserted_count": len(self.inserted_claim_ids),
            "inserted_claim_ids": list(self.inserted_claim_ids),
            "skipped": dict(self.skipped),
            "total_facts_seen": self.total_facts_seen,
        }


# ───── pure parser (no I/O, no store, no LLM) ─────

def _parse_batch_to_claims(
    *,
    parsed: SourceAnalysisBatch,
    source_body: str,
    source_url: str,
) -> tuple[list[dict], ExtractionResult]:
    """
    Transform a SourceAnalysisBatch into a list of claim dicts ready for
    `store.insert_claim()`.

    Pure function: no file I/O, no LLM calls, no database writes. This
    is 80% of the test surface — exercise it directly with mocked
    `SourceAnalysisBatch` inputs, no client mocking needed.

    Returns:
        (claim_dicts, result)
        - claim_dicts: list of kwargs-style dicts, each directly passable
          to `store.insert_claim(**claim_dict)`
        - result: ExtractionResult with skip counts and total_facts_seen

    The caller is responsible for matching the right SourceAnalysis to
    the right source_page (this function operates on a single source at
    a time — pass the parsed batch but only the analyses matching
    `source_url` are consumed).
    """
    result = ExtractionResult()
    claim_dicts: list[dict] = []

    matching_analyses = [
        a for a in parsed.analyses if a.source_url == source_url
    ]
    if not matching_analyses:
        logger.warning(
            "_parse_batch_to_claims: no analyses matched source_url=%s "
            "(found %d analyses for other URLs)",
            source_url[:80], len(parsed.analyses),
        )
        return claim_dicts, result

    # Lowercase the source body ONCE for all quote lookups
    body_lower = source_body.lower()

    for analysis in matching_analyses:
        source_quality = float(analysis.source_quality or 0.0)

        for fact in analysis.atomic_facts:
            result.total_facts_seen += 1

            # ── Filter 1: statement too short ──
            statement = (fact.statement or "").strip()
            if len(statement) < PG_MIN_STATEMENT_LEN:
                result.skipped["short_statement"] += 1
                continue

            # ── Filter 2: quote too short ──
            quote = (fact.direct_quote or "").strip()
            if len(quote.split()) < PG_MIN_QUOTE_WORDS:
                result.skipped["short_quote"] += 1
                continue

            # ── Filter 3: URL fragment ──
            quote_lower = quote.lower()
            if any(m in quote_lower for m in _URL_MARKERS):
                result.skipped["url_fragment"] += 1
                continue

            # ── Filter 4: cookie / consent boilerplate ──
            if any(m in quote_lower for m in _COOKIE_MARKERS):
                result.skipped["cookie_text"] += 1
                continue

            # ── Char-span lookup against the BODY (not the LLM input) ──
            char_start, char_end, verified = _locate_quote(quote, body_lower, source_body)

            # ── has_numeric detection ──
            has_numeric = bool(_NUMERIC_PATTERN.search(quote))

            # ── Tier assignment (3 signals for v1) ──
            relevance = _clamp01(fact.relevance_score)
            tier = _assign_tier(
                relevance=relevance,
                source_quality=source_quality,
                verified=verified,
            )

            claim_dicts.append({
                "statement": statement,
                "direct_quote": quote[:500],  # mirror analyzer's cap
                "char_start": char_start,
                "char_end": char_end,
                "tier": tier,
                "relevance_score": relevance,
                "has_numeric": has_numeric,
            })

    return claim_dicts, result


# ───── orchestrator (I/O + LLM) ─────

async def extract_claims_from_source(
    *,
    client: _LLMClient,
    store: MeshStore,
    workspace_id: str,
    source_page_id: str,
    query: str,
) -> ExtractionResult:
    """
    Full L2 write path for a single source_page.

    Reads the source body from disk, calls the LLM with the production
    ANALYSIS_SYSTEM prompt, parses the response, and inserts the result
    as claim rows via `store.insert_claim`. The whole insert phase runs
    inside a single transaction so a partial parser failure rolls back
    cleanly and does not double-count the workspace claim counter.

    Returns an ExtractionResult with the inserted claim IDs and skip
    counts.
    """
    src = store.get_source(source_page_id)
    if src is None:
        raise MeshStoreError(f"Source not found: {source_page_id}")
    if src["workspace_id"] != workspace_id:
        raise MeshStoreError(
            f"Source {source_page_id} belongs to workspace "
            f"{src['workspace_id']}, not {workspace_id}"
        )

    # Resolve the on-disk path and read the body (header-stripped)
    md_path = store.workspace_dir / src["filepath"]
    source_body = read_source_text(md_path)
    if not source_body.strip():
        raise MeshStoreError(
            f"Source body is empty for {source_page_id} at {md_path}"
        )

    # Cap the content sent to the LLM (matches analyzer.py behavior)
    llm_content = source_body[:PG_CONTENT_PER_SOURCE]
    source_url = src.get("url") or f"mesh://{source_page_id}"
    source_title = src.get("title") or ""
    source_type = src.get("kind") or "web"

    prompt = (
        f"Research question: {query}\n\n"
        f"Analyze the following source and extract the TOP 8-15 MOST "
        f"relevant atomic facts. Focus on the most specific, unique, "
        f"and directly relevant numbers, dates, measurements, claims, "
        f"findings, regulations, and standards. Quality over quantity.\n\n"
        f"Source URL: {source_url}\n"
        f"Source title: {source_title}\n"
        f"Source type: {source_type}\n"
        f"Content:\n{llm_content}\n"
        f"---"
    )

    parsed = await client.generate_structured(
        prompt=prompt,
        schema=SourceAnalysisBatch,
        system=ANALYSIS_SYSTEM,
        max_tokens=PG_EXTRACTION_MAX_TOKENS,
        timeout=PG_EXTRACTION_TIMEOUT,
        reasoning_enabled=False,
    )

    # Parse (pure function — no I/O)
    claim_dicts, result = _parse_batch_to_claims(
        parsed=parsed,
        source_body=source_body,
        source_url=source_url,
    )

    # Embed every surviving claim statement BEFORE opening the transaction.
    # Embedding is slow (GPU/CPU inference) and we don't want to hold a
    # DB write lock while it runs. The embed call is idempotent and
    # stateless — if the transaction later fails, we throw the vectors
    # away without corruption. Atomicity is preserved because the vector
    # insert inside `store.insert_claim` (via `_insert_vector`) is in
    # the same transaction as the row insert.
    embeddings: list[np.ndarray] = []
    if claim_dicts:
        try:
            from src.utils.embedding_service import embed_texts
        except ImportError as exc:
            raise MeshStoreError(
                "src.utils.embedding_service is required for claim extraction "
                f"({exc}). Install dependencies or run tests with a mock."
            ) from exc
        raw_vecs = embed_texts([c["statement"] for c in claim_dicts])
        for vec in raw_vecs:
            arr = np.asarray(vec, dtype=np.float32)
            if arr.shape != (EMBEDDING_DIM,):
                raise MeshStoreError(
                    f"Embedding service returned shape {arr.shape}, "
                    f"expected ({EMBEDDING_DIM},). Model change detected — "
                    f"update schema.VECTOR_DDL and EMBEDDING_DIM to match."
                )
            embeddings.append(arr)

    # Insert everything atomically — claims + their vectors in one tx
    with store.transaction():
        for claim_kwargs, emb in zip(claim_dicts, embeddings):
            clm_id = store.insert_claim(
                workspace_id=workspace_id,
                source_page_id=source_page_id,
                embedding=emb,
                **claim_kwargs,
            )
            result.inserted_claim_ids.append(clm_id)

    logger.info(
        "extract_claims_from_source %s: %d inserted, %d total seen, skipped=%s",
        source_page_id, len(result.inserted_claim_ids),
        result.total_facts_seen, result.skipped,
    )
    return result


# ───── helpers ─────

def _clamp01(v: float | None) -> float:
    if v is None:
        return 0.1
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.1
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _locate_quote(
    quote: str,
    body_lower: str,
    body: str,
) -> tuple[int, int, bool]:
    """
    Find `quote` in `body_lower` (the lowercased body). Returns
    (char_start, char_end, verified). If not found, returns the
    sentinel (UNVERIFIED_CHAR_START, UNVERIFIED_CHAR_END, False).

    We search with the first 50 chars of the quote (matching the
    production heuristic in analyzer.py:2126) to tolerate minor
    trailing drift (punctuation, whitespace, LLM paraphrase).
    """
    quote_lower = quote.lower().strip()
    if not quote_lower or not body_lower:
        return UNVERIFIED_CHAR_START, UNVERIFIED_CHAR_END, False

    # Try the first 50-char prefix first (tolerates trailing paraphrase)
    prefix = quote_lower[:50]
    start = body_lower.find(prefix)
    if start < 0:
        return UNVERIFIED_CHAR_START, UNVERIFIED_CHAR_END, False

    # Try to locate the full quote starting from this position
    full_pos = body_lower.find(quote_lower, start)
    if full_pos >= 0:
        end = full_pos + len(quote_lower)
    else:
        end = start + len(prefix)

    # Sanity check: both within body bounds
    if start >= len(body) or end > len(body) or end <= start:
        return UNVERIFIED_CHAR_START, UNVERIFIED_CHAR_END, False

    return start, end, True


def _assign_tier(
    *,
    relevance: float,
    source_quality: float,
    verified: bool,
) -> str:
    """
    v1 tier assignment using three signals available at extraction time.

    The production pipeline uses a 5-signal scheme (FIX-048-K2)
    including corroboration count and citation_count — those require
    edge discovery (Unit 4) and are deferred. For v1, the following
    rule is enough to get GOLD/SILVER/BRONZE roughly right for the
    lethal retrieval algorithm to work on:

        GOLD   = relevance >= 0.7 AND source_quality >= 0.6 AND verified
        SILVER = (relevance >= 0.4 AND verified) OR (relevance >= 0.5)
        BRONZE = everything else

    Unverifiable but highly relevant claims still get SILVER — we
    don't want to bury a 0.9-relevance claim as BRONZE just because
    the LLM paraphrased the quote slightly and the body-search missed.
    """
    if verified and relevance >= 0.7 and source_quality >= 0.6:
        return "GOLD"
    if (verified and relevance >= 0.4) or relevance >= 0.5:
        return "SILVER"
    return "BRONZE"
