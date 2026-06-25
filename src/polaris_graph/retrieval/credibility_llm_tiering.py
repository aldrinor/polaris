"""I-wire-001 W5 — credibility LLM-tiering winner (PG_CREDIBILITY_LLM_TIERING).

The bake-off winner (`scripts/dr_benchmark/upstream_bakeoff/credibility_winner.json`):
an LLM (GLM-5.2 via OpenRouter) classifies a source DIRECTLY into the POLARIS T1-T7
tier scheme from the observable authority payload, beating the deterministic 22-rule
floor by +0.353 macro-F1 on the 27-row GATE-0-validated real clinical tier gold. The
headline repair is the rule-floor's two EXPOSED-weak tiers:
  * T7 social / predatory-OA / abstract-stub: 0.000 -> 1.000 (there is no social->T7
    rule; the floor classifies social platforms T6 via RP1_social_platform_early).
  * T2 evidence-synthesis / guideline under-recall: 0.400 -> 0.889.
No tier regresses.

ARCHITECTURE (mirrors `authority/credibility_judge_caller.py`):
  * The LLM call is DEPENDENCY-INJECTED (`call_llm(prompt) -> text`) so the prompt
    build + JSON parse are pure and offline-testable; the production caller binds
    GLM-5.2 + family-segregation + provider-pin + budget via the existing
    `make_openrouter_credibility_caller` factory.
  * Tiering is a per-citation WEIGHT, NEVER a drop (CLAUDE.md §-1.3). On ANY judge
    error / timeout / malformed output, the per-source result falls back to the
    deterministic rules-floor — instant, no source is ever dropped.
  * The faithfulness engine (strict_verify / NLI / 4-role / provenance) is FROZEN and
    untouched. This module only changes the per-source tier WEIGHT.

BOUNDED PARALLELISM (operator mandate, §8 of the wiring plan): per-SOURCE LLM tiering
runs bounded-parallel via a `ThreadPoolExecutor(max_workers=PG_TIER_LLM_WORKERS)`,
order-independent (gather-then-sort by source index). The rules-floor is computed for
every source first (the instant deterministic fallback) so a slow/failed LLM call never
blocks or drops a source.

Default-OFF: `classify_source_tier` only routes here when PG_CREDIBILITY_LLM_TIERING is
set to a truthy value; otherwise the legacy rule body runs byte-identical.
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationResult,
    ClassificationSignals,
    TierLevel,
    _classify_source_tier_rules,
)

logger = logging.getLogger(__name__)

# Bounded-parallel cap for the per-source LLM tiering fan-out (LAW VI). Default 10
# mirrors the wiring plan §8.2 (`PG_TIER_LLM_WORKERS=10`). Clamped >=1 so a misconfig
# can never produce a zero/negative worker count.
_ENV_TIER_LLM_WORKERS = "PG_TIER_LLM_WORKERS"
_DEFAULT_TIER_LLM_WORKERS = 10

# Valid tier labels the LLM may return (UNKNOWN excluded — the LLM must commit to a
# tier; an unparseable / out-of-scheme answer falls back to the rules-floor).
_VALID_TIER_LABELS = {"T1", "T2", "T3", "T4", "T5", "T6", "T7"}

# The POLARIS T1-T7 scheme, transcribed VERBATIM from the rules-floor's own documented
# scheme (tier_classifier.py class docstring + domain frozensets), per the winning
# scorecard's `rubric` field. NO answer-row leakage — this is the floor's own scheme.
_TIER_SCHEME = (
    "T1 = peer-reviewed primary study (RCT, prospective cohort, case-control, "
    "cross-sectional, lab/mechanistic study in a peer-reviewed journal).\n"
    "T2 = peer-reviewed evidence synthesis or clinical guideline (systematic review, "
    "meta-analysis, Cochrane review, NICE/ADA/specialty-society guideline).\n"
    "T3 = government / regulatory body (FDA, EMA, NICE-as-regulator, WHO, CDC, "
    "Health Canada, national regulator).\n"
    "T4 = peer-reviewed narrative review, commentary, editorial, perspective, preprint, "
    "or repository deposit (not peer-reviewed primary research).\n"
    "T5 = industry-funded report (pharmaceutical-company HCP portal, manufacturer drug "
    "monograph, sponsored brand site, paid market-research / consulting collateral).\n"
    "T6 = mainstream news, blog, or non-peer-reviewed consumer-health web content.\n"
    "T7 = social-media / user-generated content (YouTube, Reddit, Facebook, X, "
    "Instagram, forums), predatory open-access, or abstract-only / conference-abstract / "
    "stub with no full article."
)

_PROMPT = (
    "You are a source-credibility TIER classifier for ONE retrieved source. Assign the "
    "single best-fitting POLARIS tier (T1..T7) from the observable signals below. Judge "
    "the SOURCE TYPE / venue authority, not the topic.\n\n"
    "TIER SCHEME:\n{scheme}\n\n"
    "SOURCE:\n"
    "  url: {url}\n"
    "  title: {title}\n"
    "  publication_type: {pub_type}\n"
    "  source_type: {source_type}\n"
    "  venue: {venue}\n"
    "  is_retracted: {is_retracted}\n"
    "  fetched_content_length: {content_length}\n\n"
    "Return STRICT JSON only, no prose, no code fence:\n"
    '{{"tier": "<one of T1,T2,T3,T4,T5,T6,T7>", '
    '"rationale": "<one short sentence citing the signal you relied on>"}}'
)


def build_tier_prompt(signals: ClassificationSignals) -> str:
    """Pure: render the per-source LLM tiering prompt from observable signals only.

    Carries ONLY observable fields (url/title/pub_type/source_type/venue/is_retracted/
    content_length) — never any gold tier or rule verdict (LAW II, no answer leakage).
    """
    return _PROMPT.format(
        scheme=_TIER_SCHEME,
        url=signals.url or "",
        title=signals.title or "",
        pub_type=signals.openalex_publication_type or "",
        source_type=signals.openalex_source_type or "",
        venue=signals.openalex_venue or "",
        is_retracted=bool(signals.openalex_is_retracted),
        content_length=signals.fetched_content_length or 0,
    )


def parse_tier_response(text: str) -> tuple[TierLevel | None, str]:
    """Pure: parse the LLM JSON response into a TierLevel + rationale.

    Returns ``(None, "")`` on ANY malformed / out-of-scheme output (the caller then
    falls back to the rules-floor — fail-honest, never fabricate a tier). Tolerates a
    stray code fence by extracting the first JSON object.
    """
    if not text or not text.strip():
        return None, ""
    raw = text.strip()
    # Extract the first {...} object so a stray code fence / preamble cannot break parse.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None, ""
    try:
        obj = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None, ""
    if not isinstance(obj, dict):
        return None, ""
    tier_str = str(obj.get("tier", "")).strip().upper()
    if tier_str not in _VALID_TIER_LABELS:
        return None, ""
    rationale = str(obj.get("rationale", "")).strip()
    return TierLevel(tier_str), rationale


def llm_tier_one(
    signals: ClassificationSignals,
    call_llm: Callable[[str], str],
) -> ClassificationResult | None:
    """Single-source LLM tiering escalation. Returns a ClassificationResult carrying the
    LLM tier as a WEIGHT, or ``None`` on judge_error / timeout / malformed output so the
    caller keeps the deterministic rules-floor result for that source.

    NEVER raises into the caller (LAW II fail-honest): any exception from the injected
    ``call_llm`` is captured and degrades to ``None`` (rules-floor fallback).
    """
    # Rule 0 parity: a retracted source is never positively tiered by the LLM either;
    # let the deterministic floor handle the exclusion semantics.
    if signals.openalex_is_retracted:
        return None
    prompt = build_tier_prompt(signals)
    try:
        text = call_llm(prompt)
    except Exception as exc:  # noqa: BLE001 — fail-honest: degrade to rules-floor
        logger.warning(
            "[credibility_llm_tiering] judge_error for %s — falling back to rules-floor: %s",
            (signals.url or "")[:80], exc,
        )
        return None
    tier, rationale = parse_tier_response(text)
    if tier is None:
        logger.warning(
            "[credibility_llm_tiering] malformed/out-of-scheme LLM tier for %s — "
            "falling back to rules-floor",
            (signals.url or "")[:80],
        )
        return None
    return ClassificationResult(
        tier=tier,
        confidence=0.9,  # LLM-tiering VIEW confidence; not a deterministic 1.0
        reasons=[
            f"LLM-tiering (PG_CREDIBILITY_LLM_TIERING): assigned {tier.value} — "
            f"{rationale or 'no rationale returned'}"
        ],
        matched_rules=["llm_tiering"],
        signals_used={
            "url": signals.url,
            "title": signals.title,
            "publication_type": signals.openalex_publication_type,
            "source_type": signals.openalex_source_type,
            "venue": signals.openalex_venue,
            "content_length": signals.fetched_content_length,
        },
    )


def _tier_llm_workers() -> int:
    """Bounded-parallel worker count from PG_TIER_LLM_WORKERS (LAW VI). Clamped >=1."""
    try:
        n = int(os.environ.get(_ENV_TIER_LLM_WORKERS, str(_DEFAULT_TIER_LLM_WORKERS)))
    except (TypeError, ValueError):
        n = _DEFAULT_TIER_LLM_WORKERS
    return max(1, n)


def _default_caller() -> Callable[[str], str]:
    """Bind the production GLM-5.2 credibility caller (lazy — keeps the OFF path free of
    httpx + the authority package). Reuses the SAME control surface as the entailment /
    credibility judge: family-segregation, provider-pin, budget + wall-deadline."""
    from src.polaris_graph.authority.credibility_judge_caller import (
        make_openrouter_credibility_caller,
    )

    return make_openrouter_credibility_caller()


def classify_sources_llm_tiering(
    signals_list: list[ClassificationSignals],
    *,
    call_llm: Callable[[str], str] | None = None,
    max_workers: int | None = None,
) -> list[ClassificationResult]:
    """Bounded-parallel per-SOURCE LLM tiering over a batch of sources.

    For EVERY source the deterministic rules-floor is computed first (the instant,
    no-network fallback). The LLM escalation then runs bounded-parallel; a source keeps
    its rules-floor result on any judge_error / timeout / malformed output. The result
    list is order-PRESERVING (gather-then-sort by index) so concurrency never changes
    the per-source outcome (§8 determinism invariant). No source is ever dropped
    (§-1.3 weight-not-filter).

    Returns a list aligned 1:1 with ``signals_list``.
    """
    n = len(signals_list)
    if n == 0:
        return []
    # Deterministic floor for every source first — the instant fallback (no network).
    floor_results: list[ClassificationResult] = [
        _classify_source_tier_rules(s) for s in signals_list
    ]
    caller = call_llm if call_llm is not None else _default_caller()
    workers = max_workers if max_workers is not None else _tier_llm_workers()

    def _one(idx: int) -> tuple[int, ClassificationResult | None]:
        return idx, llm_tier_one(signals_list[idx], caller)

    llm_by_idx: dict[int, ClassificationResult | None] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for idx, res in pool.map(_one, range(n)):
            llm_by_idx[idx] = res

    # Gather-then-sort: walk indices in order, prefer the LLM tier, fall back to floor.
    out: list[ClassificationResult] = []
    for idx in range(n):
        llm_res = llm_by_idx.get(idx)
        out.append(llm_res if llm_res is not None else floor_results[idx])
    return out


def classify_source_tier_llm(signals: ClassificationSignals) -> ClassificationResult:
    """Single-source ON-path entry called by ``classify_source_tier`` when the flag is
    ON. Escalates to the LLM, falling back to the rules-floor on any error. The
    bounded-parallel batch path (``classify_sources_llm_tiering``) is the preferred
    high-throughput entry; this keeps the single-source dispatcher contract intact."""
    floor = _classify_source_tier_rules(signals)
    llm_res = llm_tier_one(signals, _default_caller())
    return llm_res if llm_res is not None else floor
