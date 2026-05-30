"""Pure, no-network question decomposition for the live retrieval path (I-meta-002-q1d #951 q1d-a).

The 5 golden benchmark questions are 40-70-word multi-clause paragraphs; four ship with NO
hand-authored `amplified` query list, so the whole paragraph was fired as ~one keyword query and
each sub-topic was under-retrieved (the Codex-verified S0 depth gap). This module decomposes the
question into focused sub-queries deterministically — NO network, NO LLM, pure string operations —
which the sweep prepends to the amplified-query list before `run_live_retrieval`.

Splitting is deliberately CONSERVATIVE (Codex brief-gate iter-1): split only on sentence terminators,
semicolons, explicit enumerators, and top-level conjunction/connective boundaries — NEVER on bare
commas. Conjunction / `versus` splits require BOTH sides to carry >= MIN_SPLIT_CONTENT_WORDS content
words, so protected compounds ("safety and efficacy", "type 2 diabetes", "non-small cell lung cancer")
are preserved BY CONSTRUCTION.
"""

from __future__ import annotations

import re

# Content-word tokenization (stopword-filtered, 3+ chars) — mirrors the lexical notion used by the
# fetch-time rerank; pure, no model.
_DECOMP_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "of", "in", "on", "at",
    "to", "for", "with", "by", "from", "as", "that", "this", "these", "those", "it", "its",
    "be", "been", "what", "which", "who", "how", "why", "when", "where", "we", "our", "their",
    "between", "into", "about", "than", "such", "does", "do", "can", "may", "any", "also",
})

# Minimum content words for a sub-query to be KEPT (drop noise fragments).
MIN_FRAGMENT_CONTENT_WORDS = 3
# Minimum content words on EACH side of a conjunction/connective for the split to be allowed
# (protects "safety and efficacy", "type 2 diabetes", etc. — each side has < 4 content words).
MIN_SPLIT_CONTENT_WORDS = 4
# Hard cap on emitted sub-queries (keeps the per-question query fan-out bounded; PR1's total
# fetch_cap + rerank keep the corpus bounded regardless).
DEFAULT_MAX_SUBQUERIES = 6

# Top-level connective boundaries we MAY split on (only when both sides are query-like).
# "vs." is normalized to "vs" up front so it never reaches the terminator regex as a period.
_CONNECTIVES = (" as well as ", " versus ", " vs ", " and ")
# Protected "X and Y" clinical compounds: even when both surrounding fragments carry >=4 content
# words, an `and` flanked by one of these (last-word-of-left, first-word-of-right) pairs is a single
# concept, NOT a clause boundary (Codex diff-gate iter-1 P1). Lowercased word pairs.
_PROTECTED_AND_PAIRS = frozenset({
    ("safety", "efficacy"), ("efficacy", "safety"),
    ("signs", "symptoms"), ("symptoms", "signs"),
    ("risks", "benefits"), ("benefits", "risks"),
    ("morbidity", "mortality"), ("mortality", "morbidity"),
    ("diagnosis", "treatment"), ("incidence", "prevalence"),
    ("sensitivity", "specificity"), ("safety", "tolerability"),
})
# Additive connectives where a protected-compound guard applies ("safety and efficacy"). Comparators
# (" versus ", " vs ") are NOT additive — "safety vs efficacy" is a valid split — so the guard skips them.
_ADDITIVE_CONNECTIVES = (" and ", " as well as ")
# Abbreviations whose internal period(s) must NOT be treated as sentence terminators. "vs." is
# handled separately (normalized to "vs"). Periods here are masked (CASE-INSENSITIVELY, preserving
# the original casing) before the terminator split.
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "et al.", "fig.", "no.", "approx.", "ca.")
_ABBREVIATION_RE = re.compile("|".join(re.escape(a) for a in _ABBREVIATIONS), re.IGNORECASE)
_PERIOD_MASK = "\x00"
# Sentence/clause terminators we always split on. Enumerators like "1.", "2)", "(a)" are handled
# by the terminator + enumerator regex below.
_TERMINATOR_RE = re.compile(r"(?<=[.;?])\s+|\s*\|\s*")
# Strip a leading enumerator marker ("1.", "2)", "(a)", "- ", "• ") from a clause.
_ENUMERATOR_RE = re.compile(r"^\s*(?:\(?[0-9a-zA-Z]\)|[0-9]+[.)]|[-•])\s+")


def _content_tokens(text: str) -> list[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", (text or "").lower())
    return [t for t in toks if t not in _DECOMP_STOPWORDS]


def _normalize(clause: str) -> str:
    clause = _ENUMERATOR_RE.sub("", clause or "")
    return re.sub(r"\s+", " ", clause).strip().strip(",;:")


def _flanking_words(left: str, right: str) -> tuple[str, str]:
    """The last word of `left` and the first word of `right`, lowercased + punctuation-stripped."""
    lw = left.split()[-1].lower().strip(",;:.()") if left.split() else ""
    rw = right.split()[0].lower().strip(",;:.()") if right.split() else ""
    return lw, rw


def _split_on_connectives(clause: str) -> list[str]:
    """Split a clause on the FIRST top-level connective where both sides have
    >= MIN_SPLIT_CONTENT_WORDS content words AND the connective is not flanked by a protected
    clinical compound (Codex diff-gate iter-1 P1); recurse on each side. Otherwise return [clause].
    Bare commas / weak coordinators are never split points."""
    lower = clause.lower()
    for conn in _CONNECTIVES:
        idx = lower.find(conn)
        while idx != -1:
            left = clause[:idx].strip()
            right = clause[idx + len(conn):].strip()
            protected = (
                conn in _ADDITIVE_CONNECTIVES
                and _flanking_words(left, right) in _PROTECTED_AND_PAIRS
            )
            if (len(_content_tokens(left)) >= MIN_SPLIT_CONTENT_WORDS
                    and len(_content_tokens(right)) >= MIN_SPLIT_CONTENT_WORDS
                    and not protected):
                return _split_on_connectives(left) + _split_on_connectives(right)
            idx = lower.find(conn, idx + len(conn))
    return [clause]


def decompose_question(question: str, *, max_subqueries: int = DEFAULT_MAX_SUBQUERIES) -> list[str]:
    """Decompose a multi-clause question into focused sub-query strings. Pure / no-network / no-LLM.

    Returns [] for a short single-clause question (the caller then falls back to today's behavior —
    the full question is always seeded separately by `run_live_retrieval`). Sub-queries are normalized,
    fragment-filtered (>= MIN_FRAGMENT_CONTENT_WORDS content words), de-duplicated case-insensitively,
    and capped at `max_subqueries`, preserving leading-clause-first order.
    """
    if not question or not question.strip():
        return []
    # Stage 0: abbreviation protection (Codex diff-gate iter-1 P1). Normalize "vs." -> "vs" so the
    # >=4-per-side connective guard handles comparators (never the period terminator), and MASK the
    # internal periods of other abbreviations so they are not mistaken for sentence boundaries.
    work = re.sub(r"\bvs\.", "vs", question, flags=re.IGNORECASE)
    # Case-insensitive masking that PRESERVES the matched text's casing (so "E.g."/"Fig."/"No." at a
    # sentence start are protected too — Codex diff-gate iter-2 P1).
    work = _ABBREVIATION_RE.sub(lambda m: m.group(0).replace(".", _PERIOD_MASK), work)
    # Stage 1: split on sentence terminators / enumerators / pipes.
    primary = [c for c in _TERMINATOR_RE.split(work) if c and c.strip()]
    # Stage 2: split each clause on safe top-level connectives.
    clauses: list[str] = []
    for clause in primary:
        clauses.extend(_split_on_connectives(clause))
    # Stage 3: unmask abbreviation periods, normalize, fragment-filter, dedup (case-insensitive), cap.
    out: list[str] = []
    seen: set[str] = set()
    for clause in clauses:
        norm = _normalize(clause.replace(_PERIOD_MASK, "."))
        if len(_content_tokens(norm)) < MIN_FRAGMENT_CONTENT_WORDS:
            continue
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
        if len(out) >= max_subqueries:
            break
    # A single clause out of a single-clause question adds nothing → fall back to [].
    if len(out) <= 1:
        return []
    return out


def build_amplified_query_list(
    *,
    hand_authored: list[str],
    decomposed: list[str],
    regulatory: list[str],
    trial: list[str],
) -> list[str]:
    """Build the effective amplified-query list with a deterministic prepend order
    (hand_authored, decomposed, regulatory, trial) and case-insensitive dedup. Pure — the sweep
    wiring test asserts prepend order / dedup / cap behavior without invoking live retrieval.

    The anchor full question is NEVER added here — `run_live_retrieval` seeds it separately, so the
    decomposed sub-queries augment (not replace) the anchor.
    """
    out: list[str] = []
    seen: set[str] = set()
    for group in (hand_authored, decomposed, regulatory, trial):
        for q in group or []:
            norm = (q or "").strip()
            if not norm:
                continue
            key = norm.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(norm)
    return out
