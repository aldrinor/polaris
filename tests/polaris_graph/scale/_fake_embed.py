"""Deterministic offline embedder for the SCALE tests ($0, no GPU, no network).

Feature-hashing bag-of-words: every token is hashed into a fixed-width vector,
counts are summed, then L2-normalised. Cosine similarity therefore reflects
token overlap and is STABLE across separate calls (ingest vs query) with no
shared vocabulary state. This is a test-only fixture embedder — it lives under
tests/ per LAW VI/§9.4 and is never used in production.
"""

from __future__ import annotations

import hashlib
import math
import re

_DIM = 256
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tok_index(token: str) -> int:
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") % _DIM


def fake_embed(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for text in texts:
        vec = [0.0] * _DIM
        for tok in _TOKEN_RE.findall((text or "").lower()):
            vec[_tok_index(tok)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [v / norm for v in vec]
        out.append(vec)
    return out
