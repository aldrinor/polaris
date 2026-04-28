"""M-D2 stub: keyword + ontology-match inductor.

Per the Phase D plan (`docs/phase_d_milestones.md` M-D2): rule-based
inductor FIRST, LLM-augmented inductor SECOND. This module ships
the rule-based stub.

The stub treats induction as a routing-and-lookup problem: given a
query, identify which curated `curator_contract_slug` (if any) best
matches via keyword overlap with a slug-specific keyword profile.
If a single slug clearly wins, return its curator contract as the
"induced" contract — this is the trivial baseline.

When no slug wins clearly (low max-score, or two slugs tied), the
inductor abstains. This is the right behavior on ambiguous /
out-of-scope queries.

A real inductor (M-D2 LLM-augmented) would actually CONSTRUCT a
new ReportContract from the query rather than looking up a curator
contract. That work depends on a working M-D1 harness with
benchmark metrics — which now exists (commit 4687a15). The stub
unblocks pipeline integration.

## Confidence calculation

For each curated slug, the keyword profile is a set of strings.
The query's `score(slug)` is the COUNT of distinct keywords from
the profile that appear in the (lower-cased) query.

  best_score = max(score(slug) for slug in profiles)
  margin    = best_score - second_best_score

  - If best_score >= 1 AND margin >= 1 → accept best slug.
    (At least one matched keyword + the winning slug has strictly
    more matches than the runner-up.)
  - Otherwise → abstain.

Count-based scoring rather than ratio-based was a deliberate
choice in M-D2 round-1: with 10-keyword profiles, a query naming
just one keyword (e.g. "tirzepatide" alone) gets ratio=0.1 which
no reasonable accept-floor catches. Counting matches and
requiring a clear winner (margin ≥ 1) keeps precision high
without over-narrowing coverage.

The `confidence` field on the verdict carries best_score + margin
so calling code can apply its own threshold via the harness's
confidence_threshold parameter.

## Limitations

- Doesn't construct contracts; just routes to curator-reviewed ones.
  An induced contract that disagrees with the curator on entity ids
  cannot be measured against itself — score is always 1.0 when
  routing to the right slug.
- Hand-curated keyword profiles. M-D2 LLM version replaces this
  with embedding similarity + LLM template-affinity score.
- Keyword overlap is brittle to paraphrase. The "Mounjaro" /
  "Ozempic" / "T2DM" surface synonyms are explicitly listed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.polaris_graph.auto_induction.precision_metrics import (
    InductorVerdict,
    _load_curator_contract,
)


@dataclass(frozen=True)
class _SlugProfile:
    """Keyword profile for one curator-reviewed contract slug."""

    slug: str
    keywords: tuple[str, ...]
    # Optional: queries containing any of `disqualify_keywords` are
    # explicitly NOT routed to this slug, even if the keyword score
    # would suggest it. Used to mark cross-domain ambiguity (e.g.
    # "weight loss" alone shouldn't route to clinical_tirzepatide_t2dm
    # because it crosses to policy on insurance coverage).
    disqualify_keywords: tuple[str, ...] = field(default_factory=tuple)


# Hand-curated profiles for the curator contracts that exist in
# config/scope_templates/. Adding a new curator template means
# adding a profile here AND making sure the keyword set is
# disjoint from existing profiles to avoid spurious matches.
_DEFAULT_PROFILES: tuple[_SlugProfile, ...] = (
    _SlugProfile(
        slug="clinical_tirzepatide_t2dm",
        keywords=(
            "tirzepatide",
            "mounjaro",
            "ozempic",
            "semaglutide",
            "type 2 diabetes",
            "t2dm",
            "hba1c",
            "glycemic",
            "surpass",
            "diabetes",
        ),
        disqualify_keywords=(
            # Pure weight-loss without diabetes context tilts to
            # ambiguous (could be policy / coverage).
            # Note: "weight loss" alone NOT a disqualifier here
            # because diabetes drugs are studied for weight too.
        ),
    ),
    _SlugProfile(
        slug="policy_medicare_drug_price",
        keywords=(
            "medicare",
            "drug price",
            "drug pricing",
            "negotiation",
            "ira",
            "inflation reduction act",
            "pbm",
            "formulary",
            "rebate",
            "part d",
            "cms",
        ),
        disqualify_keywords=(),
    ),
)


@dataclass(frozen=True)
class KeywordInductorConfig:
    """Tunable parameters for the keyword inductor.

    Defaults use count-based scoring:
      - accept_count_floor=2: require at least 2 matched keywords.
        Calibrated against the M-D1.5 expanded validation set:
        single-keyword queries like "Tell me about diabetes
        treatments" or "drug prices" are intentionally too weak
        to accept — they belong in the operator-review queue.
      - margin_count_floor=1: winner must have strictly more
        matches than the runner-up. Cross-domain ambiguous
        queries naturally hit margin=0 and abstain.
    """

    accept_count_floor: int = 2
    margin_count_floor: int = 1
    profiles: tuple[_SlugProfile, ...] = _DEFAULT_PROFILES


class KeywordInductor:
    """M-D2 stub: rule-based keyword+ontology inductor.

    Implements `InductorProtocol` (induce(query) -> InductorVerdict).
    """

    def __init__(self, config: KeywordInductorConfig | None = None) -> None:
        self._config = config or KeywordInductorConfig()

    def _score_slug(self, query_lower: str, profile: _SlugProfile) -> int:
        """Count of distinct profile keywords appearing in the query.

        Returns 0 if any disqualifier keyword is present.
        """
        if any(dk in query_lower for dk in profile.disqualify_keywords):
            return 0
        if not profile.keywords:
            return 0
        return sum(1 for kw in profile.keywords if kw in query_lower)

    def _confidence_from_score(self, count: int, total: int) -> float:
        """Convert match count to confidence in [0, 1] for the
        verdict's confidence field. confidence = matches / total
        (the ratio is fine here as a soft signal even though the
        accept decision uses count + margin)."""
        if total <= 0:
            return 0.0
        return min(1.0, count / total)

    def induce(self, query: str) -> InductorVerdict:
        ql = query.lower()
        scores = [
            (p, self._score_slug(ql, p))
            for p in self._config.profiles
        ]
        scores.sort(key=lambda x: x[1], reverse=True)
        if not scores:
            return InductorVerdict(
                decision="abstain",
                abstain_reason="no slug profiles configured",
            )

        best_profile, best_score = scores[0]
        second_score = scores[1][1] if len(scores) > 1 else 0
        margin = best_score - second_score
        confidence = self._confidence_from_score(
            best_score, len(best_profile.keywords),
        )

        if best_score < self._config.accept_count_floor:
            return InductorVerdict(
                decision="abstain",
                abstain_reason=(
                    f"max keyword count {best_score} below floor "
                    f"{self._config.accept_count_floor}"
                ),
                confidence=confidence,
            )
        if margin < self._config.margin_count_floor:
            second_slug = (
                scores[1][0].slug if len(scores) > 1 else "none"
            )
            return InductorVerdict(
                decision="abstain",
                abstain_reason=(
                    f"top-2 margin {margin} below floor "
                    f"{self._config.margin_count_floor} (top: "
                    f"{best_profile.slug}, second: {second_slug})"
                ),
                confidence=confidence,
            )

        # Look up the curator contract for the winning slug.
        try:
            contract = _load_curator_contract(best_profile.slug)
        except ValueError as exc:
            return InductorVerdict(
                decision="abstain",
                abstain_reason=f"slug load failed: {exc}",
                confidence=confidence,
            )
        return InductorVerdict(
            decision="accept",
            induced_contract=contract,
            confidence=confidence,
        )
