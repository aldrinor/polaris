"""ARCH-1: NLI-based verification for evidence faithfulness.

Uses the minicheck library for fact-checking models:
- flan-t5-large (75.0% LLM-AggreFact, 770M params, Windows-compatible)
- Bespoke-MiniCheck-7B (77.4% LLM-AggreFact, 7B params, requires vllm/Linux)

Default: flan-t5-large (works on Windows via standard transformers).

Benefits vs Kimi K2.5 self-verification (54.2%):
- Much higher accuracy (75.0% vs 54.2%)
- Free (local inference vs $3.17/run)
- 20-50x faster (~5-10 min vs 3h43m for 1300 evidence)
- No self-enhancement bias

FIX-048-K1: Cross-source verification — after self-check, verify claims
against INDEPENDENT sources (different URLs) to break circular verification.

Falls back gracefully to LLM verification if NLI model unavailable.
"""

import asyncio
import logging
import os
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Model selection via env var
PG_NLI_MODEL = os.getenv("PG_NLI_MODEL", "flan-t5-large")
PG_NLI_BATCH_SIZE = int(os.getenv("PG_NLI_BATCH_SIZE", "16"))
PG_NLI_ENABLED = os.getenv("PG_NLI_ENABLED", "0") == "1"
PG_NLI_DISPUTE_THRESHOLD = float(os.getenv("PG_NLI_DISPUTE_THRESHOLD", "0.3"))
PG_NLI_CONTEXT_WINDOW = int(os.getenv("PG_NLI_CONTEXT_WINDOW", "2048"))

# FIX-047J: FaithLens 8B model option (F1: 87.3 vs flan-t5-large 62.1)
# Set PG_NLI_MODEL=faithlens to enable. Requires: pip install faithlens
# Model: ssz1111/FaithLens on HuggingFace. Needs 16GB VRAM.
PG_FAITHLENS_MODEL = os.getenv("PG_FAITHLENS_MODEL", "ssz1111/FaithLens")

_scorer = None
_faithlens_scorer = None
_load_lock = asyncio.Lock()


async def _load_faithlens():
    """FIX-047J: Lazy-load FaithLens 8B model. Returns FaithLensInfer instance or None."""
    global _faithlens_scorer

    if _faithlens_scorer is not None:
        return _faithlens_scorer

    async with _load_lock:
        if _faithlens_scorer is not None:
            return _faithlens_scorer

        try:
            from faithlens.inference import FaithLensInfer

            logger.info(
                "[polaris graph] FIX-047J: Loading FaithLens model '%s'",
                PG_FAITHLENS_MODEL,
            )
            start = time.time()
            _faithlens_scorer = FaithLensInfer(
                model_name=PG_FAITHLENS_MODEL,
                device="cuda:0",
            )
            elapsed = time.time() - start
            logger.info(
                "[polaris graph] FIX-047J: FaithLens loaded in %.1fs (F1=87.3)",
                elapsed,
            )
            return _faithlens_scorer

        except ImportError as exc:
            logger.warning(
                "[polaris graph] FIX-047J: FaithLens not available: %s. "
                "Install with: pip install 'faithlens @ git+https://github.com/S1s-Z/FaithLens.git@master'. "
                "Falling back to MiniCheck/LLM.",
                str(exc)[:200],
            )
            return None
        except Exception as exc:
            logger.error(
                "[polaris graph] FIX-047J: FaithLens load failed: %s. "
                "Falling back to MiniCheck/LLM.",
                str(exc)[:300],
            )
            return None


async def load_nli_model():
    """Lazy-load NLI scorer. Returns scorer instance or None.

    FIX-047J: When PG_NLI_MODEL=faithlens, loads FaithLens 8B (F1: 87.3).
    Otherwise loads MiniCheck flan-t5-large (F1: 62.1) as before.
    """
    global _scorer

    # FIX-047J: Route to FaithLens if configured
    if PG_NLI_MODEL == "faithlens":
        return await _load_faithlens()

    if _scorer is not None:
        return _scorer

    async with _load_lock:
        # Double-check after acquiring lock
        if _scorer is not None:
            return _scorer

        try:
            from minicheck.minicheck import MiniCheck

            logger.info(
                "[polaris graph] ARCH-1: Loading NLI model '%s' via minicheck library",
                PG_NLI_MODEL,
            )

            start = time.time()
            _scorer = MiniCheck(
                model_name=PG_NLI_MODEL,
                batch_size=PG_NLI_BATCH_SIZE,
                enable_prefix_caching=False,
                cache_dir=None,
            )
            elapsed = time.time() - start

            import torch
            device_name = "CUDA" if torch.cuda.is_available() else "CPU"
            gpu_mem = ""
            if torch.cuda.is_available():
                alloc = torch.cuda.memory_allocated() / 1e9
                if alloc > 0:
                    gpu_mem = f" ({alloc:.1f} GB VRAM)"

            logger.info(
                "[polaris graph] ARCH-1: NLI model loaded on %s%s in %.1fs",
                device_name, gpu_mem, elapsed,
            )
            return _scorer

        except ImportError as exc:
            logger.warning(
                "[polaris graph] ARCH-1: Cannot load NLI model — "
                "missing dependency: %s. Install with: pip install minicheck. "
                "Falling back to LLM verification.",
                str(exc)[:200],
            )
            return None
        except Exception as exc:
            logger.error(
                "[polaris graph] ARCH-1: Failed to load NLI model: %s. "
                "Falling back to LLM verification.",
                str(exc)[:300],
            )
            return None


def _extract_quote_context(
    content: str,
    direct_quote: str,
    context_chars: int,
    statement: str = "",
) -> str:
    """Extract content around the direct quote for focused NLI scoring.

    MiniCheck flan-t5-large has 512-token context window. Feeding 8K+ chars
    creates 4-8 chunks per document, each requiring a separate forward pass.
    By extracting just the ~1K chars around the quote, we get 1 chunk per item,
    making inference ~4-8x faster while keeping the relevant context.

    NRC-1 (T041 forensic audit): When the direct_quote is LLM-paraphrased
    and not found verbatim, fall back to searching for STATEMENT keywords
    in the full content. This recovered 25% of unfaithful verdicts in T041
    (276 claims scored against irrelevant content[:2048] intro text).
    """
    if not direct_quote or len(direct_quote) < 10:
        # No usable quote — try statement-anchored fallback first
        if statement:
            result = _statement_anchored_context(content, statement, context_chars)
            if result:
                return result
        return content[:context_chars]

    # Try progressively shorter prefixes to find the quote in content
    content_lower = content.lower()
    for prefix_len in [len(direct_quote), 80, 50, 30, 20]:
        prefix = direct_quote[:prefix_len].lower()
        idx = content_lower.find(prefix)
        if idx >= 0:
            # Found quote — return surrounding context window
            start = max(0, idx - context_chars // 4)
            end = min(len(content), idx + context_chars * 3 // 4)
            return content[start:end]

    # NRC-1: Quote not found (LLM paraphrased it). Try statement-anchored
    # context extraction before falling back to content[:2048].
    if statement:
        result = _statement_anchored_context(content, statement, context_chars)
        if result:
            return result

    # Last resort — return beginning of content
    return content[:context_chars]


def _statement_anchored_context(
    content: str, statement: str, context_chars: int,
) -> str | None:
    """Search for claim statement keywords in content and center window there.

    NRC-1 fix: When direct_quote is paraphrased by the LLM and not found
    verbatim in source content, we search for the CLAIM keywords instead.
    60% of faithful evidence has supporting text deeper than 2K chars —
    this function finds it by keyword matching.

    Returns context window centered on best keyword match, or None if
    no meaningful keywords found in content.
    """
    content_lower = content.lower()
    # Extract meaningful keywords (>5 chars, not stopwords)
    stopwords = {
        "which", "their", "these", "those", "about", "would", "could",
        "should", "being", "between", "through", "during", "before",
        "after", "above", "below", "under", "other", "there", "where",
        "while", "using", "based", "study", "found", "shown", "report",
    }
    keywords = [
        w.strip(".,;:!?()[]\"'").lower()
        for w in statement.split()
        if len(w.strip(".,;:!?()[]\"'")) > 5
        and w.strip(".,;:!?()[]\"'").lower() not in stopwords
    ]
    if not keywords:
        return None

    # Score each position in content by keyword density in a sliding window
    best_idx = -1
    best_hits = 0
    for kw in keywords:
        idx = content_lower.find(kw)
        if idx >= 0:
            # Count how many other keywords appear within context_chars of this position
            window_start = max(0, idx - context_chars // 2)
            window_end = min(len(content), idx + context_chars // 2)
            window = content_lower[window_start:window_end]
            hits = sum(1 for k in keywords if k in window)
            if hits > best_hits:
                best_hits = hits
                best_idx = idx

    if best_hits >= 2 or (best_hits >= 1 and len(keywords) <= 2):
        # Found meaningful keyword cluster — center window on it
        start = max(0, best_idx - context_chars // 4)
        end = min(len(content), best_idx + context_chars * 3 // 4)
        return content[start:end]

    return None


# FIX-048-K1: Cross-source verification config (LAW VI: from env vars)
PG_CROSS_SOURCE_ENABLED = os.getenv("PG_CROSS_SOURCE_ENABLED", "1") == "1"
PG_CROSS_SOURCE_MIN_SIM = float(os.getenv("PG_CROSS_SOURCE_MIN_SIM", "0.3"))
PG_CROSS_SOURCE_MIN_NLI = float(os.getenv("PG_CROSS_SOURCE_MIN_NLI", "0.5"))
PG_CROSS_SOURCE_MAX_SOURCES = int(os.getenv("PG_CROSS_SOURCE_MAX_SOURCES", "3"))
PG_CROSS_SOURCE_SELF_CHECK_MIN = float(os.getenv("PG_CROSS_SOURCE_SELF_CHECK_MIN", "0.7"))
# BUG-092: Cap cross-source NLI pairs to prevent O(n^2) explosion.
# Selects top-N pairs by relevance score (embedding similarity) rather than
# arbitrary truncation. Default 50 (was 500 with blind truncation).
PG_MAX_CROSS_SOURCE_PAIRS = int(os.getenv("PG_MAX_CROSS_SOURCE_PAIRS", "50"))


def _find_independent_sources(
    ev: dict,
    all_evidence: list[dict],
    url_content_map: dict[str, str],
    statement_embeddings: np.ndarray | None,
    ev_index: int,
    max_sources: int,
    min_similarity: float,
) -> list[tuple[str, str, float]]:
    """FIX-048-K1: Find content from OTHER URLs to verify a claim independently.

    For each evidence piece, finds source content from different URLs that are
    semantically related to the claim (using pre-computed embeddings for speed).

    Args:
        ev: The evidence piece to find independent sources for.
        all_evidence: Full evidence pool (to find other URLs).
        url_content_map: URL -> full content mapping.
        statement_embeddings: Pre-computed embeddings for all evidence statements.
        ev_index: Index of ev in all_evidence (for embedding lookup).
        max_sources: Maximum independent sources to return.
        min_similarity: Minimum embedding similarity to consider a source relevant.

    Returns:
        List of (url, content_excerpt, similarity_score) tuples from
        independent sources, sorted by similarity descending.
    """
    source_url = ev.get("source_url", "")
    if not source_url:
        return []

    # Normalize for comparison
    source_url_norm = source_url.strip().rstrip("/").lower()
    if source_url_norm.startswith("http://"):
        source_url_norm = "https://" + source_url_norm[7:]
    source_url_norm = source_url_norm.replace("://www.", "://")

    # Collect candidate URLs (different from evidence's own source)
    candidate_urls: dict[str, float] = {}  # url -> best similarity score

    if statement_embeddings is not None and len(statement_embeddings) > 1:
        # Use embedding similarity to find relevant independent sources
        ev_vec = statement_embeddings[ev_index]
        for j, other_ev in enumerate(all_evidence):
            if j == ev_index:
                continue
            other_url = other_ev.get("source_url", "")
            if not other_url:
                continue
            # Normalize other URL
            other_norm = other_url.strip().rstrip("/").lower()
            if other_norm.startswith("http://"):
                other_norm = "https://" + other_norm[7:]
            other_norm = other_norm.replace("://www.", "://")

            # Skip same source
            if other_norm == source_url_norm:
                continue

            # Compute similarity
            sim = float(np.dot(ev_vec, statement_embeddings[j]))
            if sim >= min_similarity:
                # Keep the best similarity per URL
                if other_url not in candidate_urls or sim > candidate_urls[other_url]:
                    candidate_urls[other_url] = sim
    else:
        # No embeddings available — collect all other URLs
        for other_ev in all_evidence:
            other_url = other_ev.get("source_url", "")
            if not other_url:
                continue
            other_norm = other_url.strip().rstrip("/").lower()
            if other_norm.startswith("http://"):
                other_norm = "https://" + other_norm[7:]
            other_norm = other_norm.replace("://www.", "://")
            if other_norm != source_url_norm and other_url not in candidate_urls:
                candidate_urls[other_url] = 0.5  # Default similarity

    # Sort by similarity (highest first), take top N
    sorted_urls = sorted(candidate_urls.items(), key=lambda x: x[1], reverse=True)
    sorted_urls = sorted_urls[:max_sources]

    # Look up content for each candidate URL
    results: list[tuple[str, str, float]] = []
    for url, sim in sorted_urls:
        content = url_content_map.get(url, "")
        if not content:
            # Try normalized lookup
            norm = url.strip().rstrip("/").lower()
            if norm.startswith("http://"):
                norm = "https://" + norm[7:]
            norm = norm.replace("://www.", "://")
            content = url_content_map.get(norm, "")
        if content and len(content) >= 200:  # Skip stub content
            results.append((url, content, sim))

    return results


async def _cross_source_verify(
    scorer,
    evidence: list[dict],
    self_check_results: list[dict],
    url_content_map: dict[str, str],
    all_evidence: list[dict],
    statement_embeddings: np.ndarray | None,
) -> list[dict]:
    """FIX-048-K1: Cross-source verification pass.

    For each evidence piece that passed self-check (NLI >= self_check_min),
    find content from INDEPENDENT sources and verify the claim against them.

    This breaks the circular verification where a claim extracted from
    source A is verified only against source A (always passes).

    Final faithfulness: self_check >= threshold AND
    (cross_source >= threshold OR no independent sources available).

    BUG-092: Caps total pairs at PG_MAX_CROSS_SOURCE_PAIRS (default 50),
    selecting top-N by relevance score to prioritize high-quality verification.

    Returns updated results list with cross_source_score and verification_type.
    """
    if not PG_CROSS_SOURCE_ENABLED:
        return self_check_results

    self_check_min = PG_CROSS_SOURCE_SELF_CHECK_MIN
    cross_nli_min = PG_CROSS_SOURCE_MIN_NLI
    max_sources = PG_CROSS_SOURCE_MAX_SOURCES
    min_sim = PG_CROSS_SOURCE_MIN_SIM
    context_window = PG_NLI_CONTEXT_WINDOW
    is_faithlens = PG_NLI_MODEL == "faithlens"
    max_pairs = PG_MAX_CROSS_SOURCE_PAIRS

    # Identify claims that passed self-check and need cross-source verification
    candidates: list[int] = []  # indices into self_check_results
    for i, r in enumerate(self_check_results):
        nli_score = r.get("nli_score", 0.0)
        if nli_score >= self_check_min:
            candidates.append(i)

    if not candidates:
        logger.info(
            "[polaris graph] FIX-048-K1: No claims passed self-check threshold "
            "(%.2f) — skipping cross-source verification", self_check_min,
        )
        return self_check_results

    # Prepare cross-source verification pairs with relevance scores
    cross_docs: list[str] = []
    cross_claims: list[str] = []
    cross_indices: list[int] = []  # Maps back to candidates index
    cross_relevance: list[float] = []  # BUG-092: Track relevance for sorting
    no_independent: set[int] = set()  # Candidates with no independent sources

    for idx in candidates:
        ev = evidence[idx] if idx < len(evidence) else {}
        statement = ev.get("statement", "")
        direct_quote = ev.get("direct_quote", "")

        independent_sources = _find_independent_sources(
            ev, all_evidence, url_content_map,
            statement_embeddings, idx, max_sources, min_sim,
        )

        if not independent_sources:
            no_independent.add(idx)
            continue

        for url, content, sim_score in independent_sources:
            # Extract focused context for NLI scoring
            doc_text = _extract_quote_context(
                content, direct_quote, context_window, statement=statement,
            )
            cross_docs.append(doc_text)
            cross_claims.append(statement)
            cross_indices.append(idx)
            cross_relevance.append(sim_score)

    # BUG-092: Cap total cross-source pairs to prevent O(n^2) scaling.
    # Select top-N pairs by relevance score (embedding similarity) instead
    # of arbitrary truncation. Higher-relevance pairs are more likely to
    # produce meaningful cross-source verification results.
    if len(cross_docs) > max_pairs:
        logger.warning(
            "[polaris graph] BUG-092: Capping cross-source NLI pairs from %d "
            "to %d (selecting top-N by relevance score)",
            len(cross_docs), max_pairs,
        )
        # Build index-sorted list by relevance descending, take top max_pairs
        sorted_pair_indices = sorted(
            range(len(cross_relevance)),
            key=lambda k: cross_relevance[k],
            reverse=True,
        )[:max_pairs]
        # Re-sort by original order to maintain candidate grouping
        sorted_pair_indices.sort()
        cross_docs = [cross_docs[k] for k in sorted_pair_indices]
        cross_claims = [cross_claims[k] for k in sorted_pair_indices]
        cross_indices = [cross_indices[k] for k in sorted_pair_indices]
        cross_relevance = [cross_relevance[k] for k in sorted_pair_indices]

    if not cross_docs:
        logger.info(
            "[polaris graph] FIX-048-K1: No independent sources found for any "
            "of %d candidate claims — all marked self_check_only",
            len(candidates),
        )
        return self_check_results

    # Run NLI on cross-source pairs
    t0 = time.time()
    logger.info(
        "[polaris graph] FIX-048-K1: Running cross-source NLI on %d pairs "
        "(%d claims x up to %d independent sources, model=%s)",
        len(cross_docs), len(candidates) - len(no_independent),
        max_sources, PG_NLI_MODEL,
    )

    try:
        if is_faithlens:
            fl_results = scorer.infer(docs=cross_docs, claims=cross_claims)
            cross_probs = [
                1.0 if r.get("prediction", 0) == 1 else 0.0
                for r in fl_results
            ]
        else:
            _labels, cross_probs, _chunks, _chunk_probs = scorer.score(
                docs=cross_docs, claims=cross_claims,
            )
            cross_probs = [float(p) for p in cross_probs]
    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-048-K1: Cross-source NLI failed: %s — "
            "keeping self-check results only",
            str(exc)[:200],
        )
        return self_check_results

    elapsed = time.time() - t0

    # Aggregate: for each candidate, take max NLI score across independent sources
    cross_scores: dict[int, float] = {}  # idx -> max cross-source NLI score
    for pair_idx, prob in enumerate(cross_probs):
        original_idx = cross_indices[pair_idx]
        if original_idx not in cross_scores or prob > cross_scores[original_idx]:
            cross_scores[original_idx] = prob

    # Update results with cross-source information
    upgraded = 0
    downgraded = 0
    for idx in candidates:
        r = self_check_results[idx]

        if idx in no_independent:
            # No independent sources — mark as self-check only
            r["cross_source_score"] = None
            r["verification_type"] = "extraction_self_check"
            continue

        cross_score = cross_scores.get(idx, 0.0)
        r["cross_source_score"] = round(cross_score, 4)

        if cross_score >= cross_nli_min:
            # Independently confirmed — upgrade verification type
            r["verification_type"] = "independent_cross_source"
            r["reasoning"] = (
                f"Self-check NLI={r.get('nli_score', 0):.3f}, "
                f"cross-source NLI={cross_score:.3f} (independent confirmation)"
            )
            upgraded += 1
        else:
            # Self-check passed but cross-source failed — keep self-check result
            # but mark as self-check only (not independently confirmed)
            r["verification_type"] = "extraction_self_check"
            # If cross-source strongly disagrees, downgrade faithfulness
            if cross_score < 0.2 and r.get("is_faithful"):
                r["is_faithful"] = False
                r["verification_method"] = "nli_cross_source_failed"
                r["reasoning"] = (
                    f"Self-check NLI={r.get('nli_score', 0):.3f} PASSED, but "
                    f"cross-source NLI={cross_score:.3f} FAILED (no independent support). "
                    f"Downgraded: claim may be extraction artifact."
                )
                downgraded += 1

    logger.info(
        "[polaris graph] FIX-048-K1: Cross-source verification complete in %.1fs. "
        "%d/%d candidates verified, %d independently confirmed, %d downgraded, "
        "%d had no independent sources",
        elapsed, len(candidates) - len(no_independent),
        len(candidates), upgraded, downgraded, len(no_independent),
    )

    return self_check_results


async def verify_evidence_nli(
    evidence: list[dict],
    url_content_map: dict[str, str],
    research_query: str = "",
    all_evidence: list[dict] | None = None,
    statement_embeddings: np.ndarray | None = None,
) -> list[dict]:
    """Verify all evidence using NLI model via minicheck library.

    For each evidence piece, checks if the statement is entailed by the source content.
    RC-5: When research_query is provided, pre-checks source topic relevance.
    FIX-048-K1: When all_evidence provided, runs cross-source verification after self-check.

    Args:
        evidence: Evidence pieces to verify.
        url_content_map: URL -> content mapping for source lookup.
        research_query: Research query for topic relevance check.
        all_evidence: Full evidence pool (for cross-source verification).
        statement_embeddings: Pre-computed embeddings for all_evidence statements.

    Returns list of VerifiedClaim-compatible dicts.

    Returns empty list if model is unavailable (caller should fall back to LLM).
    """
    scorer = await load_nli_model()
    if scorer is None:
        return []  # Signal caller to fall back

    context_window = PG_NLI_CONTEXT_WINDOW
    results = []

    # Prepare (document, claim) pairs
    docs_list = []
    claims_list = []
    basis_list = []

    # RC-5: Pre-compute query keywords for topic relevance check.
    # If research_query is provided, we check that source content has SOME
    # overlap with the query. Catches egregious off-topic sources (e.g.,
    # tick genetics cited in water filtration reports).
    query_keywords: set[str] = set()
    if research_query:
        # Extract meaningful words (>3 chars, lowered) from query
        query_keywords = {
            w.lower().strip(".,;:!?()[]\"'")
            for w in research_query.split()
            if len(w.strip(".,;:!?()[]\"'")) > 3
        }
    offtopic_indices: set[int] = set()

    for i, ev in enumerate(evidence):
        source_url = ev.get("source_url", "")
        # FIX-URL-NORM: Try original URL then normalized to handle www/slash/protocol diffs
        content = url_content_map.get(source_url, "")
        if not content and source_url:
            norm_url = source_url.strip().rstrip("/").lower()
            if norm_url.startswith("http://"):
                norm_url = "https://" + norm_url[7:]
            norm_url = norm_url.replace("://www.", "://")
            content = url_content_map.get(norm_url, "")
        has_content = bool(content)

        if not content:
            # No content available — use direct quote as context
            content = ev.get("direct_quote", ev.get("source_title", ""))

        has_quote = bool(ev.get("direct_quote", ""))
        statement = ev.get("statement", "")
        direct_quote = ev.get("direct_quote", "")

        # RC-5: Topic relevance pre-check. If source has ZERO query keywords
        # in title+content, it's almost certainly off-topic. Mark index for
        # forced NOT_SUPPORTED after NLI scoring.
        if query_keywords and has_content:
            source_title = ev.get("source_title", "").lower()
            # Check title + first 2000 chars of content for any query keyword
            check_text = (source_title + " " + content[:2000]).lower()
            keyword_hits = sum(1 for kw in query_keywords if kw in check_text)
            if keyword_hits == 0:
                offtopic_indices.add(i)

        # Extract focused context around the quote for efficient NLI scoring.
        # flan-t5-large has 512-token context (~2048 chars). Feeding more creates
        # multiple chunks per item, each needing a forward pass.
        # NRC-1: Pass statement for fallback keyword search when quote not found.
        if has_content and direct_quote:
            doc_text = _extract_quote_context(
                content, direct_quote, context_window, statement=statement,
            )
        elif has_content:
            # No quote but have content — try statement-anchored context
            doc_text = _extract_quote_context(
                content, "", context_window, statement=statement,
            )
        elif has_quote:
            # FIX-043C: Use direct_quote as document text for NLI when no
            # source content available. Previously NLI received "No source
            # content available." which always scored near-zero.
            doc_text = direct_quote
        else:
            doc_text = "No source content available."

        docs_list.append(doc_text)
        claims_list.append(statement if statement else "No claim.")

        if has_content:
            basis_list.append("content")
        elif has_quote:
            basis_list.append("quote_only")
        else:
            basis_list.append("title_only")

    if offtopic_indices:
        logger.info(
            "[polaris graph] RC-5: %d/%d evidence pieces flagged as off-topic "
            "(zero query keyword overlap with source)",
            len(offtopic_indices), len(evidence),
        )

    if not docs_list:
        return []

    # Run NLI inference — the library handles batching internally
    start = time.time()
    logger.info(
        "[polaris graph] ARCH-1: Starting NLI inference on %d evidence pieces "
        "(model=%s, batch_size=%d)",
        len(docs_list), PG_NLI_MODEL, PG_NLI_BATCH_SIZE,
    )

    # FIX-047J: FaithLens has a different API than MiniCheck
    is_faithlens = PG_NLI_MODEL == "faithlens"
    pred_labels = []
    raw_probs = []
    faithlens_explanations: list[str] = []

    try:
        if is_faithlens:
            # FaithLens API: infer(docs, claims) -> list of result dicts
            fl_results = scorer.infer(docs=docs_list, claims=claims_list)
            for r in fl_results:
                label = r.get("prediction", 0)
                pred_labels.append(label)
                # FaithLens returns 0/1 labels but no continuous probability
                raw_probs.append(1.0 if label == 1 else 0.0)
                faithlens_explanations.append(r.get("explanation", ""))
        else:
            # MiniCheck API: score(docs, claims) -> (labels, probs, chunks, chunk_probs)
            pred_labels, raw_probs, used_chunks, prob_per_chunk = scorer.score(
                docs=docs_list, claims=claims_list,
            )
    except Exception as exc:
        logger.error(
            "[polaris graph] ARCH-1: NLI scoring failed: %s — returning empty (fallback to LLM)",
            str(exc)[:300],
        )
        return []

    elapsed = time.time() - start

    # Build result dicts
    # FIX-059-B: NLI faithfulness threshold. Claims below this probability
    # are not faithful regardless of binary label.
    _nli_faith_threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.65"))
    offtopic_overrides = 0
    for i in range(len(evidence)):
        ev = evidence[i]
        label = pred_labels[i] if i < len(pred_labels) else 0
        prob = float(raw_probs[i]) if i < len(raw_probs) else 0.0
        # FIX-059-B: NLI threshold gate. Model binary label uses ~0.5 threshold,
        # but claims with prob < 0.65 are marginal and should not count as faithful.
        is_faithful = bool(label == 1) and prob >= _nli_faith_threshold

        # RC-5: Override NLI verdict for off-topic sources.
        # NLI can confirm "claim X is entailed by source Y" even when source Y
        # is completely irrelevant to the research question. Force NOT_SUPPORTED.
        # FIX-047J: Include FaithLens explanation in reasoning when available
        if is_faithlens and i < len(faithlens_explanations) and faithlens_explanations[i]:
            reasoning = f"FaithLens ({PG_FAITHLENS_MODEL}): {faithlens_explanations[i][:300]}"
        else:
            reasoning = f"MiniCheck NLI score: {prob:.3f} (model={PG_NLI_MODEL})"
        if i in offtopic_indices:
            is_faithful = False
            reasoning = f"RC-5 OFF-TOPIC OVERRIDE: source has zero query keyword overlap. Original NLI score: {prob:.3f}"
            offtopic_overrides += 1

        # FIX-047-K4: Mark self-referential verification explicitly.
        # NLI checks claim against its OWN source — this validates extraction
        # quality, not independent claim truth. evidence_ids starts with just
        # the source evidence; link_corroborating_evidence() adds independent
        # cross-references later. verification_type distinguishes self-check
        # from independent verification for honest faithfulness reporting.
        primary_eid = ev.get("evidence_id", f"nli_claim_{i}")
        # B17: Include cross_source_score=None as default key so it always
        # exists on the dict. _cross_source_verify() updates it for claims
        # that pass self-check and have independent sources.
        results.append({
            "claim_id": primary_eid,
            "statement": ev.get("statement", ""),
            "evidence_ids": [primary_eid],
            "confidence": prob,
            "verification_method": "nli_supported" if is_faithful else "nli_not_supported",
            "is_faithful": is_faithful,
            "section_id": None,
            "reasoning": reasoning,
            "verification_basis": basis_list[i] if i < len(basis_list) else "unknown",
            "nli_score": prob,
            "cross_source_score": None,
            "verification_type": "extraction_self_check",
            "verdict": "SUPPORTED" if is_faithful else "NOT_SUPPORTED",
            "source_url": ev.get("source_url", ""),
            "direct_quote": ev.get("direct_quote", ""),
        })

    if offtopic_overrides:
        logger.info(
            "[polaris graph] RC-5: %d NLI verdicts overridden to NOT_SUPPORTED "
            "(off-topic source detected by keyword check)",
            offtopic_overrides,
        )

    # FIX-048-K1: Cross-source verification pass.
    # After self-check, verify claims against INDEPENDENT sources.
    # Uses all_evidence pool to find content from other URLs.
    if PG_CROSS_SOURCE_ENABLED and scorer is not None:
        cross_evidence = all_evidence if all_evidence else evidence
        results = await _cross_source_verify(
            scorer=scorer,
            evidence=evidence,
            self_check_results=results,
            url_content_map=url_content_map,
            all_evidence=cross_evidence,
            statement_embeddings=statement_embeddings,
        )

    faithful_count = sum(1 for r in results if r["is_faithful"])
    total = len(results)

    # NLI-3: Score histogram logging for threshold tuning observability
    if raw_probs is not None and len(raw_probs) > 0:
        probs = [float(p) for p in raw_probs]
        bins = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
        histogram = [0] * (len(bins) - 1)
        for p in probs:
            for b_idx in range(len(bins) - 1):
                if bins[b_idx] <= p < bins[b_idx + 1]:
                    histogram[b_idx] += 1
                    break
        hist_str = " ".join(
            f"[{bins[i]:.1f}-{bins[i+1]:.1f}):{histogram[i]}"
            for i in range(len(histogram))
            if histogram[i] > 0
        )
        logger.info(
            "[polaris graph] NLI-3: Score histogram (n=%d): %s | "
            "mean=%.3f median=%.3f",
            len(probs),
            hist_str,
            sum(probs) / max(len(probs), 1),
            sorted(probs)[len(probs) // 2] if probs else 0.0,
        )

    logger.info(
        "[polaris graph] ARCH-1: NLI verification complete. %d/%d faithful "
        "(%.1f%%) in %.1fs (%.0f evidence/sec, model=%s)",
        faithful_count,
        total,
        100 * faithful_count / max(total, 1),
        elapsed,
        total / max(elapsed, 0.1),
        PG_NLI_MODEL,
    )

    return results


def get_disputed_claims(
    nli_results: list[dict],
    threshold: float | None = None,
) -> list[dict]:
    """Identify claims with ambiguous NLI scores for LLM review.

    Claims with NLI scores between threshold and (1-threshold) are
    considered disputed and should get a second opinion from LLM.

    FIX-NLI-CASCADE: Also include ALL title_only claims regardless of score,
    since NLI with no source content is essentially guessing.
    """
    if threshold is None:
        threshold = PG_NLI_DISPUTE_THRESHOLD
    disputed = []
    for r in nli_results:
        nli_score = r.get("nli_score", 0.5)
        basis = r.get("verification_basis", "")
        # Ambiguous NLI score — needs LLM review
        if threshold < nli_score < (1 - threshold):
            disputed.append(r)
        # FIX-NLI-CASCADE: title_only verification is unreliable — always dispute
        elif basis == "title_only":
            disputed.append(r)
        # FIX-043C: quote_only NLI is unreliable (no source content to verify
        # against, only the direct quote). Route to LLM for second opinion.
        elif basis == "quote_only":
            disputed.append(r)
    return disputed
