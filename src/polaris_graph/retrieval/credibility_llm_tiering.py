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
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait as futures_wait
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

# Per-source LLM-tiering outcome states, surfaced as REAL runtime counts by the
# post-execution canary in ``classify_sources_llm_tiering`` (never a config echo).
# SUCCESS = GLM returned a valid tier; FALLBACK = llm_tier_one returned None
# (judge_error / malformed / retracted) so the deterministic rules-floor was kept;
# ERROR = an unexpected exception escaped llm_tier_one (contracted not to raise).
_TIER_STATUS_SUCCESS = "success"
_TIER_STATUS_FALLBACK = "fallback"
_TIER_STATUS_ERROR = "error"

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


def _tier_llm_batch_wall_seconds() -> float:
    """I-deepfix-001 W07 (#1344): a TOTAL wall (seconds) for the whole LLM-tiering batch.
    `classify_sources_llm_tiering` is per-CALL bounded, but `pool.map` BLOCKS until ALL N
    futures finish; on a mirror blank-200/trickle storm each source can burn up to its
    per-call budget x retries, so the batch wall = ceil(N/workers)*per-call. Because
    `run_live_retrieval` runs on the event-loop thread, the run-level wall cannot preempt
    this post-loop W5 batch. When the deadline passes we STOP waiting and keep the
    deterministic rules-FLOOR tier for every un-returned source (no drop, §-1.3). `<= 0`
    disables the wall. Default 600s (generous)."""
    raw = os.getenv("PG_TIER_LLM_BATCH_WALL_SECONDS", "600").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 600.0
    import math as _math
    if not _math.isfinite(value) or value <= 0:
        return 0.0
    return value


def _tier_llm_degrade_after() -> int:
    """I-deepfix-001 W07 (#1344): a consecutive-fallback circuit-breaker count. Once this
    many tiering calls in a row fall back (blank/trickle storm), short-circuit the REMAINING
    sources straight to the rules-floor instead of paying the per-call budget on each. `<= 0`
    disables the breaker. Default 8."""
    raw = os.getenv("PG_TIER_LLM_DEGRADE_AFTER", "8").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 8
    return value


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
    deadline_monotonic: "float | None" = None,
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

    def _one(idx: int) -> tuple[int, ClassificationResult | None, str]:
        # llm_tier_one is contracted NOT to raise (it captures judge_error / timeout
        # internally and degrades to None). The defensive guard counts any truly
        # unexpected escape as ERROR so the canary never silently swallows it.
        try:
            res = llm_tier_one(signals_list[idx], caller)
        except Exception as exc:  # noqa: BLE001 — fail-honest: degrade to rules-floor
            logger.warning(
                "[credibility_llm_tiering] unexpected error tiering idx=%d — "
                "falling back to rules-floor: %s",
                idx, exc,
            )
            return idx, None, _TIER_STATUS_ERROR
        status = _TIER_STATUS_SUCCESS if res is not None else _TIER_STATUS_FALLBACK
        return idx, res, status

    llm_by_idx: dict[int, ClassificationResult | None] = {}
    llm_success = 0
    fallback_count = 0
    error_count = 0
    # I-deepfix-001 W07 (#1344): bound the whole batch by a TOTAL deadline + a
    # consecutive-fallback circuit-breaker. The TIGHTER (earlier) of the threaded
    # `deadline_monotonic` (the caller's retrieval wall) and the env fallback wins.
    _batch_wall = _tier_llm_batch_wall_seconds()
    _eff_deadline = deadline_monotonic
    if _batch_wall > 0:
        _wall_instant = time.monotonic() + _batch_wall
        _eff_deadline = (
            _wall_instant if _eff_deadline is None else min(_eff_deadline, _wall_instant)
        )
    _degrade_after = _tier_llm_degrade_after()
    _consecutive_fallbacks = 0
    _short_circuited = 0
    _wall_unreturned = 0
    # I-deepfix-001 W07 (#1344): manage the pool MANUALLY (NOT `with`) so the
    # non-blocking shutdown below cannot be defeated by `with`'s __exit__ shutdown(wait=True),
    # which would BLOCK until a wedged worker finishes — making the batch wall cosmetic.
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        future_to_idx = {pool.submit(_one, i): i for i in range(n)}
        pending = set(future_to_idx)
        _stop = False
        while pending and not _stop:
            _remaining = (
                None if _eff_deadline is None
                else max(0.0, _eff_deadline - time.monotonic())
            )
            if _remaining is not None and _remaining <= 0:
                break
            done, pending = futures_wait(
                pending, timeout=_remaining, return_when=FIRST_COMPLETED,
            )
            if not done:
                break  # the wall elapsed mid-flight
            for fut in done:
                idx, res, status = fut.result()
                llm_by_idx[idx] = res
                if status == _TIER_STATUS_SUCCESS:
                    llm_success += 1
                    _consecutive_fallbacks = 0
                elif status == _TIER_STATUS_ERROR:
                    error_count += 1
                    _consecutive_fallbacks += 1
                else:
                    fallback_count += 1
                    _consecutive_fallbacks += 1
                # Circuit-breaker: once consecutive fallbacks exceed the threshold, stop
                # waiting on the rest and let them fall through to the rules-floor.
                if _degrade_after > 0 and _consecutive_fallbacks >= _degrade_after:
                    _stop = True
                    break
        # Any future not yet collected (wall hit OR circuit-breaker tripped) keeps the
        # deterministic rules-floor (no drop, §-1.3). Do NOT block on the still-running
        # futures — they finish in their threads but we stop waiting on them.
        if pending:
            for fut in list(pending):
                if fut.done():
                    try:
                        idx, res, status = fut.result()
                        llm_by_idx[idx] = res
                        if status == _TIER_STATUS_SUCCESS:
                            llm_success += 1
                        elif status == _TIER_STATUS_ERROR:
                            error_count += 1
                        else:
                            fallback_count += 1
                        continue
                    except Exception:  # noqa: BLE001 — a late failure falls to the floor
                        pass
                if _stop:
                    _short_circuited += 1
                else:
                    _wall_unreturned += 1
        if _short_circuited or _wall_unreturned:
            logger.warning(
                "[credibility_llm_tiering] W07: batch bounded — %d short-circuited "
                "(>=%d consecutive fallbacks), %d un-returned at wall; ALL kept at the "
                "deterministic rules-floor (no drop, §-1.3).",
                _short_circuited, _degrade_after, _wall_unreturned,
            )
    finally:
        # NON-BLOCKING teardown: a wedged tiering worker must not delay the return (the
        # un-returned source already keeps its rules-floor). The orphaned thread exits on
        # its own per-call timeout.
        pool.shutdown(wait=False, cancel_futures=True)

    # Gather-then-sort: walk indices in order, prefer the LLM tier, fall back to floor.
    out: list[ClassificationResult] = []
    for idx in range(n):
        llm_res = llm_by_idx.get(idx)
        out.append(llm_res if llm_res is not None else floor_results[idx])

    # POST-execution canary — REAL runtime counts, fired only after the fan-out ran.
    # If GLM tiered nothing (llm_success == 0) the batch is DEGRADED to the rules-floor;
    # never claim "tiered via GLM" when every source fell back (the prior false-positive).
    attempted = n
    if llm_success == 0:
        logger.info(
            "[credibility_llm_tiering] DEGRADED (rules-floor only): attempted=%d "
            "llm_success=0 fallback=%d error=%d — GLM tiering did NOT fire",
            attempted, fallback_count, error_count,
        )
    else:
        logger.info(
            "[credibility_llm_tiering] tiered via GLM: attempted=%d llm_success=%d "
            "fallback=%d error=%d",
            attempted, llm_success, fallback_count, error_count,
        )
    return out


def classify_source_tier_llm(signals: ClassificationSignals) -> ClassificationResult:
    """Single-source ON-path entry called by ``classify_source_tier`` when the flag is
    ON. Escalates to the LLM, falling back to the rules-floor on any error. The
    bounded-parallel batch path (``classify_sources_llm_tiering``) is the preferred
    high-throughput entry; this keeps the single-source dispatcher contract intact."""
    floor = _classify_source_tier_rules(signals)
    llm_res = llm_tier_one(signals, _default_caller())
    return llm_res if llm_res is not None else floor
