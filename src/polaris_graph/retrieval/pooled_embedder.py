"""Pooled Embedding (Fix R4-#1 — Embedding Context Truncation).

all-MiniLM-L6-v2 has a hard max_seq_length of 256 tokens. Our CRAG chunks
are 1024 tokens + 150-token L6 context header = 1174 tokens. The sentence-
transformers library SILENTLY truncates past the limit:

    - The embedding model reads: Title, Abstract, first ~100 tokens of chunk
    - It NEVER sees the remaining ~900 tokens of empirical data
    - All chunks from the same document share the same prefix
    - Result: near-identical embeddings (0.87 cosine) for completely
      different content from the same paper

Empirically verified on 2026-03-16:
    - Prefix (91 tokens) occupies 36% of the 256-token window
    - 408/664 tokens truncated from enriched chunks
    - Same-doc different-content similarity: 0.87 (should be <0.5)
    - Blueprint routing was completely blind to chunk-level differences

Fix: Mean Pooling Sub-chunking.
    1. Split long text into max_seq_tokens-sized blocks
    2. Embed each block individually (single batch call for efficiency)
    3. Mean-pool the sub-chunk vectors into one per-text vector
    4. Re-normalize the averaged vector (unit sphere for cosine sim)

This is model-agnostic — works with any embedding model regardless of
its context window. If/when we upgrade to a long-context model (e.g.,
nomic-embed-text-v1.5 at 8192 tokens), the sub-chunking will simply
pass texts through unchanged (no performance penalty).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import numpy as np

logger = logging.getLogger("polaris_graph")

# Model's max sequence length in tokens — verified for all-MiniLM-L6-v2
# Override via env var if using a different model
MAX_SEQ_TOKENS = int(os.getenv("PG_EMBED_MAX_SEQ_TOKENS", "256"))

# Conservative chars-per-token ratio (English prose ≈ 4 chars/token)
# We use 3.5 to be safe — better to sub-chunk unnecessarily than to truncate
_CHARS_PER_TOKEN = 3.5


def embed_with_pooling(
    texts: list[str],
    embed_fn: Callable[[list[str]], list[list[float]]],
    max_seq_tokens: int = MAX_SEQ_TOKENS,
) -> list[list[float]]:
    """Embed texts with mean pooling for texts exceeding model's max_seq_length.

    Fix R4-#1 (Embedding Context Truncation): Prevents silent truncation
    by splitting long texts into sub-chunks, embedding them individually
    in a single batch call, and mean-pooling back to one vector per text.

    Args:
        texts: List of texts to embed (can be any length).
        embed_fn: The embedding function (e.g., embed_texts from embedding_service).
                  Must accept list[str] and return list[list[float]].
        max_seq_tokens: Model's maximum sequence length in tokens.

    Returns:
        List of embeddings (one per input text), same order as input.
        Vectors are L2-normalized for cosine similarity.
    """
    if not texts:
        return []

    max_chars = int(max_seq_tokens * _CHARS_PER_TOKEN)

    # Phase 1: Build flat list of sub-chunks with group tracking
    sub_chunks: list[str] = []
    group_boundaries: list[tuple[int, int]] = []  # (start_idx, count) per text

    for text in texts:
        start = len(sub_chunks)
        text_stripped = (text or "").strip()

        if not text_stripped:
            # Empty text — pass through (embedding service handles this)
            sub_chunks.append("")
        elif len(text_stripped) <= max_chars:
            # Short enough — no sub-chunking needed
            sub_chunks.append(text_stripped)
        else:
            # Split into sub-chunks at word boundaries
            _split_into_subchunks(text_stripped, max_chars, sub_chunks)

        count = len(sub_chunks) - start
        if count == 0:
            # Safety: ensure at least one sub-chunk per text
            sub_chunks.append(text_stripped[:max_chars] if text_stripped else "")
            count = 1
        group_boundaries.append((start, count))

    # Phase 2: Single batch embedding call (efficient — one GPU pass)
    all_embeddings = embed_fn(sub_chunks)

    # Phase 3: Mean pool back to per-text embeddings
    result: list[list[float]] = []
    for start, count in group_boundaries:
        if count == 1:
            result.append(all_embeddings[start])
        else:
            vecs = np.array(
                all_embeddings[start:start + count], dtype=np.float32
            )
            mean_vec = np.mean(vecs, axis=0)
            # Re-normalize after averaging (embeddings must be unit vectors
            # for cosine similarity to equal dot product)
            norm = np.linalg.norm(mean_vec)
            if norm > 1e-8:
                mean_vec = mean_vec / norm
            result.append(mean_vec.tolist())

    return result


def _split_into_subchunks(
    text: str,
    max_chars: int,
    out: list[str],
) -> None:
    """Split text into sub-chunks at word boundaries.

    Appends sub-chunks to `out` in-place for efficiency.
    Minimum sub-chunk size: 50 chars (skip tiny remainders).
    """
    pos = 0
    text_len = len(text)

    while pos < text_len:
        end = min(pos + max_chars, text_len)

        # If not at the end, try to break at a word boundary
        if end < text_len:
            # Look back for the last space within the window
            space_pos = text.rfind(" ", pos, end)
            if space_pos > pos + max_chars // 2:
                # Found a space in the second half — break there
                end = space_pos

        sub = text[pos:end].strip()
        if len(sub) >= 50:
            out.append(sub)

        pos = end
        # Skip whitespace at boundary
        while pos < text_len and text[pos] == " ":
            pos += 1
