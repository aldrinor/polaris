"""Curated-template scope-guardrail classifier (M-10 — Phase B).

NOT a multi-template intent classifier. With one production template
(v30_clinical) the routing problem in Phase B is "is this query in
scope for v30_clinical: yes/maybe/no" — the FINAL_PLAN Risk #13
mitigation. Misframing matters: an over-eager classifier silently
routes off-scope queries to v30_clinical and the user gets a
polished-but-misframed audit. The defaults bias toward
`unsupported_scope` when uncertain.

Verdicts:
  routed                    → high-confidence in scope; UI can offer to
                              auto-enqueue. Score >= floor_high.
  operator_review_required  → medium-confidence; UI surfaces the
                              candidate template to a human for
                              confirmation before enqueue. Score in
                              [floor_review, floor_high).
  unsupported_scope         → low-confidence; UI tells the user the
                              question isn't yet supported and points
                              them at the scope page. Score <
                              floor_review.

The classifier is **advisory only**. The /api/inspector/jobs enqueue
endpoint still requires an explicit template_id. UI flow: call
/route → surface verdict → user confirms → call /jobs.

Scoring (deliberately simple for Phase B):
  - Tokenize the query (lowercase, ascii-ish word/digit tokens).
  - For each catalog template:
      keyword_match: count of scope_keywords whose token-set is a
                     subset of the query tokens (multi-word entries
                     match as token sets).
      example_jaccard: max Jaccard similarity (intersection / union)
                       between query tokens and any scope_example's
                       tokens.
      score: discrete cascade — high keyword-AND-example overlap
             → routed; some-but-not-strong → operator_review;
             nothing → unsupported.

Determinism: same query produces the same verdict on every call.
No randomness, no model state, no external calls.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum

from src.polaris_graph.audit_ir.template_catalog import (
    CuratedTemplate,
    list_catalog,
)


# ---------------------------------------------------------------------------
# Threshold defaults (env-overridable, per LAW VI)
# ---------------------------------------------------------------------------

DEFAULT_FLOOR_HIGH = 0.55
DEFAULT_FLOOR_REVIEW = 0.30


class RoutingVerdict(str, Enum):
    """Three-tier routing outcome — see module docstring."""

    ROUTED = "routed"
    OPERATOR_REVIEW = "operator_review_required"
    UNSUPPORTED = "unsupported_scope"


@dataclass(frozen=True)
class RoutingCandidate:
    """One template-and-score pair surfaced to the UI."""

    template_id: str
    score: float
    keyword_hits: tuple[str, ...] = field(default_factory=tuple)
    example_jaccard: float = 0.0


@dataclass(frozen=True)
class RoutingResult:
    """Output of `classify_query`. See module docstring for verdict semantics."""

    verdict: RoutingVerdict
    template_id: str | None
    confidence: float
    candidates: tuple[RoutingCandidate, ...]
    rationale: str


@dataclass(frozen=True)
class RouterConfig:
    """Tunable thresholds for the classifier.

    Defaults are conservative-high in the false-positive direction
    (it is better to surface a supported question as
    operator_review_required than to silently route an off-scope
    question to v30_clinical and produce a misframed audit).

    Override via env:
      PG_TEMPLATE_ROUTER_FLOOR_HIGH    (default 0.55)
      PG_TEMPLATE_ROUTER_FLOOR_REVIEW  (default 0.30)
    """

    floor_high: float = DEFAULT_FLOOR_HIGH
    floor_review: float = DEFAULT_FLOOR_REVIEW

    @classmethod
    def from_env(cls) -> "RouterConfig":
        try:
            high = float(os.environ.get("PG_TEMPLATE_ROUTER_FLOOR_HIGH", DEFAULT_FLOOR_HIGH))
        except ValueError:
            high = DEFAULT_FLOOR_HIGH
        try:
            review = float(os.environ.get("PG_TEMPLATE_ROUTER_FLOOR_REVIEW", DEFAULT_FLOOR_REVIEW))
        except ValueError:
            review = DEFAULT_FLOOR_REVIEW
        # Guardrails: review_floor must be < high_floor; both must be in [0, 1].
        high = max(0.0, min(1.0, high))
        review = max(0.0, min(high, review))
        return cls(floor_high=high, floor_review=review)


# ---------------------------------------------------------------------------
# Tokenization + matching primitives
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def _tokenize(text: str) -> frozenset[str]:
    """Return lowercased word/digit tokens. Hyphens preserved (so
    'glp-1' stays one token). Drops 1-char tokens that aren't digits
    to suppress noise.
    """
    if not text:
        return frozenset()
    raw = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in raw if len(t) > 1 or t.isdigit())


def _keyword_hits(qtokens: frozenset[str], keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return the keywords that are subsets of the query tokens.

    A multi-word keyword like "phase 3" matches only if both tokens
    are present in the query. This prevents accidental partial hits.
    """
    hits: list[str] = []
    for kw in keywords:
        kw_toks = _tokenize(kw)
        if kw_toks and kw_toks.issubset(qtokens):
            hits.append(kw)
    return tuple(hits)


def _max_example_jaccard(qtokens: frozenset[str], examples: tuple[str, ...]) -> float:
    """Highest Jaccard similarity between the query and any exemplar."""
    best = 0.0
    for ex in examples:
        ex_toks = _tokenize(ex)
        if not ex_toks or not qtokens:
            continue
        inter = qtokens & ex_toks
        union = qtokens | ex_toks
        if not union:
            continue
        j = len(inter) / len(union)
        if j > best:
            best = j
    return best


def _score_template(
    qtokens: frozenset[str], tmpl: CuratedTemplate
) -> tuple[float, tuple[str, ...], float]:
    """Discrete-tier score for one template against the query tokens.

    Returns (score in [0, 1], keyword_hits, example_jaccard).

    Tiers (higher tiers fire first):
      tier A — example_jaccard >= 0.4 AND >=2 keyword hits
               → routed; score blends jaccard.
      tier B — example_jaccard >= 0.3 alone
               → routed-or-review depending on threshold.
      tier C — >=3 keyword hits (medical+clinical framing) but no
               strong example overlap
               → operator_review (just below floor_high).
      tier D — 1-2 keyword hits OR weak example overlap
               → operator_review (above floor_review).
      tier E — nothing
               → unsupported.
    """
    kw_matches = _keyword_hits(qtokens, tmpl.scope_keywords)
    ex_jac = _max_example_jaccard(qtokens, tmpl.scope_examples)
    n_kw = len(kw_matches)

    if ex_jac >= 0.4 and n_kw >= 2:
        # Strong example match + at least two keyword hits.
        return min(0.6 + 0.4 * ex_jac, 1.0), kw_matches, ex_jac
    if ex_jac >= 0.3:
        # Strong example match alone — route, but lower confidence.
        return min(0.5 + 0.5 * ex_jac, 0.85), kw_matches, ex_jac
    if n_kw >= 3:
        # Multiple keyword hits without exemplar match — keyword-only
        # query (e.g. "FDA drug trial") is likely in domain but
        # ambiguous; surface for operator review.
        return min(0.40 + 0.05 * (n_kw - 3), 0.54), kw_matches, ex_jac
    if n_kw == 2:
        return 0.35, kw_matches, ex_jac
    if n_kw == 1:
        return 0.30, kw_matches, ex_jac
    if ex_jac >= 0.10:
        # Weak lexical overlap with examples but no keyword hits.
        # Borderline; route to operator review.
        return 0.20, kw_matches, ex_jac
    return 0.0, kw_matches, ex_jac


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_query(
    question: str, config: RouterConfig | None = None
) -> RoutingResult:
    """Map a user query to a routing verdict.

    Empty / whitespace-only queries return UNSUPPORTED with a
    helpful rationale (rather than 400-ing) so the UI can surface
    the same scope-page CTA in every off-scope branch.
    """
    if config is None:
        config = RouterConfig.from_env()

    if not question or not question.strip():
        return RoutingResult(
            verdict=RoutingVerdict.UNSUPPORTED,
            template_id=None,
            confidence=0.0,
            candidates=(),
            rationale=(
                "Empty query. Provide a clinical drug-condition question; "
                "see the scope page for examples of supported queries."
            ),
        )

    qtokens = _tokenize(question)
    catalog = list_catalog()
    if not catalog:
        return RoutingResult(
            verdict=RoutingVerdict.UNSUPPORTED,
            template_id=None,
            confidence=0.0,
            candidates=(),
            rationale="No curated templates registered.",
        )

    scored: list[RoutingCandidate] = []
    for tmpl in catalog:
        score, kw_hits, ex_jac = _score_template(qtokens, tmpl)
        scored.append(
            RoutingCandidate(
                template_id=tmpl.template_id,
                score=score,
                keyword_hits=kw_hits,
                example_jaccard=ex_jac,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    candidates = tuple(scored)
    top = candidates[0]

    if top.score >= config.floor_high:
        return RoutingResult(
            verdict=RoutingVerdict.ROUTED,
            template_id=top.template_id,
            confidence=top.score,
            candidates=candidates,
            rationale=(
                f"Query matches '{top.template_id}' with high confidence "
                f"(score {top.score:.2f} ≥ floor_high {config.floor_high:.2f}; "
                f"keyword hits: {len(top.keyword_hits)}, example "
                f"Jaccard: {top.example_jaccard:.2f})."
            ),
        )

    if top.score >= config.floor_review:
        return RoutingResult(
            verdict=RoutingVerdict.OPERATOR_REVIEW,
            template_id=top.template_id,
            confidence=top.score,
            candidates=candidates,
            rationale=(
                f"Query partially matches '{top.template_id}' "
                f"(score {top.score:.2f} in "
                f"[{config.floor_review:.2f}, {config.floor_high:.2f})). "
                f"Operator must confirm scope before audit launches."
            ),
        )

    return RoutingResult(
        verdict=RoutingVerdict.UNSUPPORTED,
        template_id=None,
        confidence=top.score,
        candidates=candidates,
        rationale=(
            f"Query does not match any supported audit template "
            f"(top candidate '{top.template_id}' scored {top.score:.2f}, "
            f"below floor_review {config.floor_review:.2f}). "
            f"See the scope page for supported question shapes."
        ),
    )
