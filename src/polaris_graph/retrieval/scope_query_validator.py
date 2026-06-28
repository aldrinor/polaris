"""
Scope-protocol query validator — HONEST-REBUILD Phase 2e.

Validates that amplified search queries stay within the pre-registered
protocol's research scope. Drops queries that have drifted off-topic
before they waste retrieval budget.

WHY THIS EXISTS (PG_LB_SA_02_CONTENT_AUDIT Section E-04):
The pre-rebuild pipeline amplified a single research question into
10-25 search variants using an LLM. Some variants drifted:
  original: "efficacy of semaglutide for weight loss"
  amplified: "Japan national health insurance elderly care coverage"

These drifted queries pulled in the junk that Phase 2d's post-fetch
off-topic filter then had to remove. Dropping drift at amplification
time is cheaper than fetching and discarding.

DESIGN:
- No new LLM call. Uses token overlap with protocol.research_question +
  PICO fields (intervention / population / outcome) as the anchor.
- Drops any amplified query whose similarity with the anchor is below
  PG_AMPLIFIER_SCOPE_FLOOR (default 0.08, the containment-scale floor — see
  I-retr-001 #1340).
- ALWAYS keeps the verbatim research_question and direct PICO-term
  queries ("{intervention} {population}") as a safety net.
- Logs drops so the user can see which amplifier variants were killed.

SIMILARITY MEASURE (default `containment` per I-retr-001 #1340; was `jaccard`
per BB-001 #1171):
- PG_SCOPE_SIM_MEASURE selects the measure: `containment` (DEFAULT) or `jaccard`.
  Symmetric Jaccard (|q∩a|/|q∪a|) punishes a SHORT on-topic query against a large
  anchor bag (tiny intersection over a huge union) — the #1 retrieval-breadth
  chokepoint (kept=2 of 35 on drb_72, anchor_tokens=136). Containment / overlap-
  coefficient (|q∩a|/min(|q|,|a|)) normalises by the smaller set so a short on-topic
  query clears while genuine drift still fails. The GATE is KEPT either way (genuine
  off-anchor drift still drops); only the measure changes. `jaccard` stays selectable
  for back-compat. Default flipped to `containment` so EVERY run path is correct, not
  only the Gate-B slate (which already set containment explicitly).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("polaris_graph.scope_query_validator")


# Very small English stopword set — we care about domain terms, so
# we strip only the grammatical connective tissue.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "in", "is", "it", "its", "of", "on", "or", "that",
    "the", "this", "to", "was", "were", "will", "with", "what", "which",
    "how", "why", "when", "where", "who", "whom", "whose", "i", "you",
    "we", "they", "can", "could", "should", "would", "may", "might",
    "do", "does", "did", "done", "being", "been", "about", "into",
    "than", "then", "so", "also", "more", "most", "some", "any", "all",
    "not", "no", "only", "very", "just", "other",
})

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")


def _tokenize(text: str) -> set[str]:
    """Lowercased tokens minus stopwords, minus short tokens."""
    if not text:
        return set()
    tokens = {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 2
    }
    return tokens - _STOPWORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard (symmetric) similarity |a∩b| / |a∪b|. Empty a or b -> 0.0."""
    if not a or not b:
        return 0.0
    union = a | b
    inter = a & b
    return len(inter) / len(union) if union else 0.0


def _containment(a: set[str], b: set[str]) -> float:
    """Containment / overlap-coefficient similarity |a∩b| / min(|a|, |b|).

    BB-001 (I-beatboth-fix-000 #1171): the symmetric Jaccard punishes a SHORT
    on-topic query against a LARGE anchor bag — a 4-6-token query has a tiny
    intersection over a huge union, so its sim sits far below the floor and the
    query is dropped before it ever issues a search (the #1 retrieval-breadth
    chokepoint: 40->5 kept on drb_72). Containment normalises by the SMALLER set,
    so a short query whose tokens are all in the anchor scores ~1.0 while a query
    that drifts off-anchor still scores low — it KEEPS the gate (reranks against
    intent) rather than removing it. Empty a or b -> 0.0; never raises.
    """
    if not a or not b:
        return 0.0
    inter = a & b
    smaller = min(len(a), len(b))
    return len(inter) / smaller if smaller else 0.0


_SIM_MEASURES = {"jaccard": _jaccard, "containment": _containment}

# I-retr-001 (#1340): the DEFAULT measure is `containment` (overlap-coefficient
# |q∩a| / min(|q|,|a|)) with floor 0.08. Under SYMMETRIC jaccard a short on-topic
# query against a long research-question anchor (drb_72: anchor_tokens=136) caps at
# ~8/136 ≈ 0.06 and was wrongly dropped (kept=2 of 35) — the §-1.3 filter-strangles-
# breadth defect. Containment normalises by the SMALLER set, so a short on-topic query
# scores ~1.0 while genuine off-anchor drift still scores low and is still dropped: the
# de-drift GATE is KEPT, only the measure is corrected. `jaccard` remains selectable via
# PG_SCOPE_SIM_MEASURE for back-compat. Faithfulness-NEUTRAL — this is a pre-fetch
# query/scope gate; it touches no strict_verify / NLI / 4-role / span faithfulness gate.
# (Supersedes BB-001 #1171, whose `jaccard`-default "byte-identical OFF" choice was the
# source of the breadth collapse on every run path that does not apply the Gate-B slate.)
_DEFAULT_SIM_MEASURE = "containment"
_DEFAULT_SCOPE_FLOOR = 0.08


def _select_sim_measure():
    """Return the (name, fn) for the configured similarity measure.

    Reads ``PG_SCOPE_SIM_MEASURE`` (default ``containment`` per I-retr-001 #1340).
    An unrecognised value FAILS LOUD (LAW II) — a typo'd measure must not
    silently fall back to a different gate behaviour on a paid benchmark run.
    """
    raw = os.getenv("PG_SCOPE_SIM_MEASURE", _DEFAULT_SIM_MEASURE).strip().lower()
    if raw not in _SIM_MEASURES:
        raise ValueError(
            f"PG_SCOPE_SIM_MEASURE={raw!r} is not a recognised similarity measure "
            f"(expected one of {sorted(_SIM_MEASURES)})."
        )
    return raw, _SIM_MEASURES[raw]


@dataclass
class ValidationResult:
    """Return value of validate_amplified_queries()."""

    kept: list[str]
    dropped: list[tuple[str, float, str]]  # (query, similarity, reason)
    anchor_tokens_used: list[str]


def _build_anchor_tokens(protocol: dict[str, Any]) -> set[str]:
    """Merge research_question + anchor tokens into one anchor set.

    Accepts either a ProtocolDocument dict (from scope_gate) or any dict with
    similar fields. Missing fields are skipped gracefully.

    Clinical PICO fields (population / intervention / comparator / outcome) are
    string-valued and tokenized as before — OFF byte-identical.

    I-meta-005 Phase 1 (#985, brief §2.4): ADDITIVELY also merge the field-
    agnostic `ResearchFrame` anchor fields (entities / relations / metrics /
    comparators / constraints) when present, so planner sub-queries derived
    from a non-clinical frame validate against the frame's OWN tokens. These
    fields may be list-valued (from `ResearchFrame.to_anchor_protocol`); each
    element is tokenized. A clinical PICO protocol carries none of them, so
    this extension does not change PICO behavior.
    """
    bag: set[str] = set()
    # Legacy clinical PICO anchors (string-valued). Unchanged.
    for field in (
        "research_question", "population", "intervention",
        "comparator", "outcome",
    ):
        val = protocol.get(field) or ""
        bag |= _tokenize(str(val))
    # I-meta-005 Phase 1: field-agnostic frame anchors (list-valued). Skipped
    # gracefully when absent (clinical PICO protocols), so OFF is unchanged.
    for field in (
        "entities", "relations", "metrics", "comparators", "constraints",
    ):
        val = protocol.get(field)
        if isinstance(val, (list, tuple, set)):
            for item in val:
                bag |= _tokenize(str(item))
        elif val:
            bag |= _tokenize(str(val))
    return bag


def validate_amplified_queries(
    amplified: list[str],
    protocol: dict[str, Any],
    *,
    floor: Optional[float] = None,
    always_keep_anchor: bool = True,
) -> ValidationResult:
    """Drop amplified queries that drift off the scope protocol.

    Args:
        amplified: Raw output from query amplifier — plain string queries.
        protocol: Dict form of protocol.json, OR any dict with the
            fields research_question / intervention / population / outcome.
        floor: Minimum scope similarity (query-tokens-vs-anchor-tokens) to
            keep a query. Default: PG_AMPLIFIER_SCOPE_FLOOR env var,
            fallback 0.08 (the containment-scale floor; see I-retr-001 #1340).
        always_keep_anchor: When True, the verbatim research_question is
            always kept even if its own similarity is below floor (which
            can happen for very short questions). Default True.

    Returns:
        ValidationResult with `kept` (queries that passed), `dropped`
        (tuples with reason), and `anchor_tokens_used` for debugging.
    """
    if floor is None:
        floor = float(os.getenv("PG_AMPLIFIER_SCOPE_FLOOR", str(_DEFAULT_SCOPE_FLOOR)))

    # I-retr-001 (#1340): default `containment` (overlap-coefficient) so a short
    # on-topic query clears the floor against a long anchor. The de-drift gate is
    # KEPT either way (off-anchor queries still fail) — only the MEASURE changes.
    sim_name, sim_fn = _select_sim_measure()

    anchor_tokens = _build_anchor_tokens(protocol)
    anchor_tokens_sorted = sorted(anchor_tokens)

    research_question = (protocol.get("research_question") or "").strip()

    kept: list[str] = []
    dropped: list[tuple[str, float, str]] = []
    seen: set[str] = set()

    # Dedupe while preserving order
    unique_amplified: list[str] = []
    for q in amplified:
        norm = (q or "").strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            unique_amplified.append(q.strip())

    for q in unique_amplified:
        q_tokens = _tokenize(q)
        if not q_tokens:
            dropped.append((q, 0.0, "empty_after_tokenization"))
            continue
        sim = sim_fn(q_tokens, anchor_tokens)
        if sim >= floor:
            kept.append(q)
        else:
            # I-retr-001 (#1340): the drop reason carries the active measure name
            # (default now `containment`) for debuggability; bare `jaccard` keeps the
            # legacy suffix-less form for back-compat with the explicit-jaccard path.
            _reason = f"below_scope_floor_{floor:.2f}"
            if sim_name != "jaccard":
                _reason = f"{_reason}_{sim_name}"
            dropped.append((q, sim, _reason))

    # Safety net: always keep the verbatim research_question, even if
    # its own similarity was below floor (happens for very short PICO
    # questions like "Semaglutide efficacy?").
    if always_keep_anchor and research_question:
        if research_question not in kept:
            kept.insert(0, research_question)

    logger.info(
        "[scope_validator] measure=%s floor=%.2f kept=%d dropped=%d (anchor_tokens=%d)",
        sim_name, floor, len(kept), len(dropped), len(anchor_tokens),
    )
    if dropped:
        sample = dropped[:3]
        for q, sim, reason in sample:
            logger.debug(
                "[scope_validator] DROP q=%r sim=%.3f reason=%s",
                q[:80], sim, reason,
            )

    return ValidationResult(
        kept=kept,
        dropped=dropped,
        anchor_tokens_used=anchor_tokens_sorted,
    )
