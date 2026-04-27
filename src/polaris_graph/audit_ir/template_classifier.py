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
    """One template-and-score pair surfaced to the UI.

    Codex M-10 review fix: surfaces drug_hits and medical_hits
    separately so the operator-review UI can show "matched 2 medical
    keywords but no specific drug; confirm scope" rather than a
    single opaque keyword count. `keyword_hits` retained as the union
    for backwards compat with v1 consumers.
    """

    template_id: str
    score: float
    keyword_hits: tuple[str, ...] = field(default_factory=tuple)
    drug_hits: tuple[str, ...] = field(default_factory=tuple)
    medical_hits: tuple[str, ...] = field(default_factory=tuple)
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

# Codex M-10 review fix: normalize Unicode hyphens (non-breaking
# hyphen U+2011, en-dash U+2013, em-dash U+2014, minus sign U+2212,
# figure dash U+2012) to ASCII so copy-pasted text like "GLP‑1"
# tokenizes the same way as "GLP-1". Done at normalize-time, not
# inside the regex, so the regex stays simple/auditable.
_HYPHEN_TRANSLATE = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-",
    "–": "-", "—": "-", "―": "-",
    "−": "-",
})

# Codex M-10 review fix: stopword/scaffold suppression. Without this,
# a query that mimics an exemplar's question scaffold ("What is the
# efficacy of X for Y?") gets a high Jaccard from {what, is, the,
# of, for} alone, which let off-scope queries like "What is the
# efficacy of turmeric for arthritis?" auto-route. The suppression
# is small and conservative — it only removes question scaffold and
# core English function words, never medical content.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the",
    "and", "or", "but",
    "of", "in", "on", "at", "to", "for", "from", "with", "by",
    "is", "are", "was", "were", "be", "been", "being",
    "what", "which", "who", "whom", "why", "how", "when", "where",
    "do", "does", "did", "has", "have", "had",
    "this", "that", "these", "those",
    "as", "if", "than", "then", "so", "such",
    "i", "you", "we", "they", "he", "she", "it",
    "my", "your", "our", "their", "his", "her", "its",
    "new", "any", "some", "all", "both", "each", "every",
})


def _tokenize_raw(text: str) -> frozenset[str]:
    """Lowercased, hyphen-preserving word/digit tokens.

    Hyphens within tokens are kept (so "glp-1" stays one token).
    1-char non-digit tokens are dropped to suppress noise.
    Unicode hyphen variants are normalized to ASCII first.
    """
    if not text:
        return frozenset()
    normalized = text.translate(_HYPHEN_TRANSLATE).lower()
    raw = _TOKEN_RE.findall(normalized)
    return frozenset(t for t in raw if len(t) > 1 or t.isdigit())


def _filter_stopwords(tokens: frozenset[str]) -> frozenset[str]:
    """Drop scaffold words so they cannot inflate Jaccard similarity."""
    return frozenset(t for t in tokens if t not in _STOPWORDS)


def _keyword_hits(qtokens: frozenset[str], keywords: tuple[str, ...]) -> tuple[str, ...]:
    """Return the keywords that are subsets of the query tokens.

    Operates on raw (un-stopword-filtered) query tokens because
    keywords like "in" never occur — keywords are content words.
    A multi-word keyword like "phase 3" matches only if both tokens
    are present in the query.
    """
    hits: list[str] = []
    for kw in keywords:
        kw_toks = _tokenize_raw(kw)
        if kw_toks and kw_toks.issubset(qtokens):
            hits.append(kw)
    return tuple(hits)


def _max_example_jaccard(
    qtokens_filtered: frozenset[str], examples: tuple[str, ...]
) -> float:
    """Highest Jaccard similarity between the query and any exemplar.

    Both sides are stopword-filtered (Codex M-10 fix). Without the
    filter, a query+exemplar that share `{what, is, the, of, for}`
    gets a misleading 0.5+ baseline from scaffold alone.
    """
    best = 0.0
    if not qtokens_filtered:
        return 0.0
    for ex in examples:
        ex_toks = _filter_stopwords(_tokenize_raw(ex))
        if not ex_toks:
            continue
        inter = qtokens_filtered & ex_toks
        union = qtokens_filtered | ex_toks
        if not union:
            continue
        j = len(inter) / len(union)
        if j > best:
            best = j
    return best


def _score_template(
    qtokens_raw: frozenset[str], tmpl: CuratedTemplate
) -> tuple[float, tuple[str, ...], tuple[str, ...], float]:
    """Codex M-10 review fix: discrete-tier score using two-class
    keyword signals.

    Returns (score in [0, 1], drug_hits, medical_hits, example_jaccard).

    The ROUTED gate (tier A) requires BOTH:
      (1) at least one drug_keyword hit (a specific regulated drug
          or drug class is named in the query), AND
      (2) example_jaccard ≥ 0.30 on stopword-filtered tokens (the
          query semantically matches a known exemplar shape, not
          just the question scaffold).

    Without (1), the verdict can rise no higher than OPERATOR_REVIEW
    regardless of exemplar similarity. This is the Risk #13
    guardrail — the false-positive direction (auto-routing
    off-scope queries about supplements / non-drugs / generic
    medical topics) is the dominant failure mode in Phase B with
    one production template, so the route gate is deliberately
    drug-anchored.
    """
    drug_hits = _keyword_hits(qtokens_raw, tmpl.drug_keywords)
    medical_hits = _keyword_hits(qtokens_raw, tmpl.medical_keywords)
    qtokens_filtered = _filter_stopwords(qtokens_raw)
    ex_jac = _max_example_jaccard(qtokens_filtered, tmpl.scope_examples)

    n_drug = len(drug_hits)
    n_medical = len(medical_hits)

    # Tier A — ROUTED: drug-anchored AND semantically aligned with
    # an exemplar shape. Score blends jaccard so very-strong matches
    # land near 1.0 and weak-but-passing matches sit just above
    # floor_high.
    if n_drug >= 1 and ex_jac >= 0.30:
        score = 0.55 + 0.45 * ex_jac
        return min(score, 1.0), drug_hits, medical_hits, ex_jac

    # Tier B — OPERATOR_REVIEW: drug named but the query shape is
    # off-pattern (e.g. "tirzepatide weather forecast"). Operator
    # decides if the query can be reframed.
    if n_drug >= 1:
        # Score sits in the review band; jaccard contributes a small
        # nudge so a borderline exemplar match isn't lost in logs.
        return 0.40 + 0.10 * ex_jac, drug_hits, medical_hits, ex_jac

    # Tier C — OPERATOR_REVIEW: no drug named, but multiple medical
    # signals + decent jaccard. Could be a question that needs a
    # drug specified by the operator (e.g. "What is the efficacy of
    # this new GLP-1 agonist?" with the drug name elided).
    if n_medical >= 3 and ex_jac >= 0.20:
        return 0.40, drug_hits, medical_hits, ex_jac

    # Tier D — OPERATOR_REVIEW (low): some medical signal but no
    # drug and weak shape match.
    if n_medical >= 2:
        return 0.35, drug_hits, medical_hits, ex_jac
    if n_medical >= 1:
        return 0.30, drug_hits, medical_hits, ex_jac

    # Tier E — UNSUPPORTED: weak lexical overlap but no medical
    # framing at all.
    if ex_jac >= 0.20:
        return 0.20, drug_hits, medical_hits, ex_jac

    return 0.0, drug_hits, medical_hits, ex_jac


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

    qtokens_raw = _tokenize_raw(question)
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
        score, drug_hits, medical_hits, ex_jac = _score_template(qtokens_raw, tmpl)
        scored.append(
            RoutingCandidate(
                template_id=tmpl.template_id,
                score=score,
                keyword_hits=drug_hits + medical_hits,
                drug_hits=drug_hits,
                medical_hits=medical_hits,
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
                f"drug hits: {len(top.drug_hits)}, medical hits: "
                f"{len(top.medical_hits)}, example Jaccard: "
                f"{top.example_jaccard:.2f})."
            ),
        )

    if top.score >= config.floor_review:
        # Codex M-10 review fix: rationale calls out which gate the
        # query failed so the operator-review UI can show "no
        # specific drug named — confirm or supply one" vs "drug named
        # but query shape is off".
        if not top.drug_hits:
            why = (
                "no specific regulated drug or drug class named — "
                "v30_clinical requires one for routed audits"
            )
        else:
            why = (
                "drug named but query shape did not match a known "
                "exemplar; operator should reframe or confirm scope"
            )
        return RoutingResult(
            verdict=RoutingVerdict.OPERATOR_REVIEW,
            template_id=top.template_id,
            confidence=top.score,
            candidates=candidates,
            rationale=(
                f"Query partially matches '{top.template_id}' "
                f"(score {top.score:.2f} in "
                f"[{config.floor_review:.2f}, {config.floor_high:.2f})): "
                f"{why}. Operator must confirm scope before audit launches."
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
