"""M-D2 stub: keyword + ontology-match inductor.

Per the Phase D plan (`docs/phase_d_milestones.md` M-D2): rule-based
inductor FIRST, LLM-augmented inductor SECOND. This module ships
the rule-based stub.

The stub treats induction as a routing-and-lookup problem: given a
query, identify which curated `curator_contract_slug` (if any) best
matches via keyword profile match. If a single slug clearly wins,
return its curator contract as the "induced" contract.

## Scoring (Codex round-1 review fix)

For each profile we distinguish:
  - **anchor_keywords**: high-precision identifiers (drug brand
    names, named programs, named statutes). At least one anchor
    must match for an accept.
  - **support_keywords**: broader contextual terms (condition,
    domain words). Useful as supporting signal but never sufficient
    alone.

Match uses **word-boundary regex** (`\\b...\\b`) so "drug price"
does NOT match inside "drug pricing", and "diabetes" does NOT match
inside any token containing it as a substring. This closes the
substring double-counting bug Codex round 1 caught.

Score = anchor_hits + support_hits (counted distinct keywords).

Decision:
  - require anchor_hits >= 1 (high-precision anchor required)
  - require total >= accept_count_floor (default 2)
  - require margin >= margin_count_floor (default 1) over runner-up
  - if any disqualifier present, score = 0 for that slug

This closes the "type 2 diabetes" / "PBM rebate in employer plans"
class of false accepts that Codex round 1 found.

## Limitations (still applicable in round 2)

- Doesn't construct contracts; just routes to curator-reviewed
  ones. M-D2 LLM-augmented version is the real inductor.
- Hand-curated keyword profiles. Won't catch novel paraphrase
  (e.g. "maximum fair price" without "Medicare/IRA/CMS").
- Anchor list is closed; new branded drugs / new statutes need
  manual profile updates.
"""

from __future__ import annotations

import re
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
    """Keyword profile for one curator-reviewed contract slug.

    Codex round-1 review fix: split keywords into anchor (high-
    precision identifiers, must have at least one) and support
    (contextual / supportive). Previously a single flat list let
    a single broad keyword match yield false accepts.
    """

    slug: str
    anchor_keywords: tuple[str, ...]
    support_keywords: tuple[str, ...] = field(default_factory=tuple)
    disqualify_keywords: tuple[str, ...] = field(default_factory=tuple)


# Hand-curated profiles. After Codex round-1 stress-test, anchor
# words are restricted to drug brand names + program names (high
# precision); broader words moved to support.
_DEFAULT_PROFILES: tuple[_SlugProfile, ...] = (
    _SlugProfile(
        slug="clinical_tirzepatide_t2dm",
        anchor_keywords=(
            # Brand + INN names — high precision for the contract.
            "tirzepatide",
            "mounjaro",
            "zepbound",
            # Named SURPASS / SURMOUNT trial programs.
            "surpass",
            "surmount",
        ),
        support_keywords=(
            # Comparators (presence is supportive, not anchoring).
            "ozempic",
            "wegovy",
            "semaglutide",
            # Condition / metric words — supportive only.
            "type 2 diabetes",
            "t2dm",
            "hba1c",
            "glycemic",
            "diabetes",
        ),
        disqualify_keywords=(),
    ),
    _SlugProfile(
        slug="policy_medicare_drug_price",
        anchor_keywords=(
            # Anchored phrases that ONLY make sense in the Medicare
            # drug-price context. Multiple gerund / noun variants
            # of "drug price negotiation" — Codex round-1 found
            # gerund-form "drug pricing negotiation" was missed.
            "medicare drug price",
            "medicare drug pricing",
            "drug price negotiation",
            "drug pricing negotiation",
            "inflation reduction act",
            "ira drug price",
            "ira drug pricing",
            "maximum fair price",
            "negotiated drug price",
            "negotiated price",
            "drug pricing rule",
            "drug-pricing rule",
        ),
        support_keywords=(
            # Broader policy vocabulary that's supportive but not
            # specific (CMS does many things; PBM exists in
            # commercial too; medicare alone covers many areas).
            "medicare",
            "part d",
            "cms",
            "pbm",
            "rebate",
            "formulary",
            "drug price",
            "drug pricing",
            "negotiation",
            "ira",
        ),
        disqualify_keywords=(
            # Codex round-1: "How do PBM rebates affect
            # employer-sponsored insurance premiums?" wrongly
            # accepted. The Medicare drug-price contract doesn't
            # cover commercial / employer-plan PBM mechanics.
            "employer-sponsored",
            "employer sponsored",
            "commercial insurance",
            "commercial plan",
            # CMS does many non-drug things (DME reimbursement,
            # hospital payment, MA plan rules). Disqualify when
            # the topic is clearly not drug pricing.
            "insulin pump",
            "durable medical equipment",
            "hospital reimbursement",
        ),
    ),
)


def _word_pattern(keyword: str) -> re.Pattern[str]:
    """Build a word-boundary regex for `keyword` (already lowered).

    Word-boundary matching means "diabetes" does NOT match inside
    "type 2 diabetes" (already a separate keyword) AND does not
    match inside any token containing it. Multi-word keywords
    are matched as adjacency with whitespace tolerated.
    """
    # Escape any regex metachars in the keyword, then surround
    # with `\b` word boundaries.
    return re.compile(r"\b" + re.escape(keyword) + r"\b")


# Cache compiled patterns per profile to avoid recompiling on every
# induce() call.
_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _kw_in_query(query_lower: str, keyword: str) -> bool:
    """Word-boundary substring match (Codex round-1 fix)."""
    pattern = _PATTERN_CACHE.get(keyword)
    if pattern is None:
        pattern = _word_pattern(keyword)
        _PATTERN_CACHE[keyword] = pattern
    return bool(pattern.search(query_lower))


@dataclass(frozen=True)
class KeywordInductorConfig:
    """Tunable parameters for the keyword inductor.

    Defaults (Codex round-1 review hardening):
      - require_anchor=True: at least one anchor keyword must
        match for an accept. Closes the "type 2 diabetes" class
        of false accepts where only support keywords matched.
      - accept_count_floor=2: total (anchor+support) must be >=2.
      - margin_count_floor=1: winning slug strictly beats runner-up.
    """

    require_anchor: bool = True
    accept_count_floor: int = 2
    margin_count_floor: int = 1
    profiles: tuple[_SlugProfile, ...] = _DEFAULT_PROFILES


class KeywordInductor:
    """M-D2 stub: rule-based keyword+ontology inductor.

    Implements `InductorProtocol` (induce(query) -> InductorVerdict).
    """

    def __init__(self, config: KeywordInductorConfig | None = None) -> None:
        self._config = config or KeywordInductorConfig()

    def _score_slug(
        self, query_lower: str, profile: _SlugProfile,
    ) -> tuple[int, int]:
        """Return (anchor_hits, support_hits) for the slug.

        Returns (0, 0) if any disqualifier keyword matches.
        """
        if any(
            _kw_in_query(query_lower, dk)
            for dk in profile.disqualify_keywords
        ):
            return (0, 0)
        anchor_hits = sum(
            1 for kw in profile.anchor_keywords
            if _kw_in_query(query_lower, kw)
        )
        support_hits = sum(
            1 for kw in profile.support_keywords
            if _kw_in_query(query_lower, kw)
        )
        return (anchor_hits, support_hits)

    def _confidence_from_score(
        self, count: int, total: int,
    ) -> float:
        if total <= 0:
            return 0.0
        return min(1.0, count / total)

    def induce(self, query: str) -> InductorVerdict:
        ql = query.lower()
        scored: list[tuple[_SlugProfile, int, int]] = []
        for p in self._config.profiles:
            anchor, support = self._score_slug(ql, p)
            scored.append((p, anchor, support))
        # Sort by total descending.
        scored.sort(key=lambda x: x[1] + x[2], reverse=True)
        if not scored:
            return InductorVerdict(
                decision="abstain",
                abstain_reason="no slug profiles configured",
            )

        best_profile, best_anchor, best_support = scored[0]
        best_total = best_anchor + best_support
        if len(scored) > 1:
            second_total = scored[1][1] + scored[1][2]
            second_slug = scored[1][0].slug
        else:
            second_total = 0
            second_slug = "none"
        margin = best_total - second_total
        total_kw = (
            len(best_profile.anchor_keywords)
            + len(best_profile.support_keywords)
        )
        confidence = self._confidence_from_score(best_total, total_kw)

        if self._config.require_anchor and best_anchor < 1:
            return InductorVerdict(
                decision="abstain",
                abstain_reason=(
                    f"no anchor keyword matched for {best_profile.slug} "
                    f"(support hits: {best_support}; anchor required "
                    f"per config)"
                ),
                confidence=confidence,
            )
        if best_total < self._config.accept_count_floor:
            return InductorVerdict(
                decision="abstain",
                abstain_reason=(
                    f"max keyword count {best_total} below floor "
                    f"{self._config.accept_count_floor} "
                    f"(anchor={best_anchor}, support={best_support})"
                ),
                confidence=confidence,
            )
        if margin < self._config.margin_count_floor:
            return InductorVerdict(
                decision="abstain",
                abstain_reason=(
                    f"top-2 margin {margin} below floor "
                    f"{self._config.margin_count_floor} (top: "
                    f"{best_profile.slug}, second: {second_slug})"
                ),
                confidence=confidence,
            )

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
