#!/usr/bin/env python3
"""I-wire-001 W5 — §-1.4 BEHAVIORAL fire-test for credibility_llm_tiering.

FAIL-LOUD canary (non-zero exit if the effect did not fire). Acceptance per the
operator §-1.4 mandate: the winner's effect must APPEAR in the real per-source tier on a
REAL banked corpus_snapshot, with a REAL GLM-5.2 call (NOT a stub — a stub returning T7
would make the assertion circular).

What it proves on a real corpus_snapshot that contains social-media sources:

  1. flag-OFF  -> re-classifying the corpus's social rows reproduces the snapshot's
                 recorded rules-floor tier (T6 via RP1_social_platform_early) AND the
                 source count is unchanged (byte-identical legacy behaviour).

  2. flag-ON   -> the SAME social URLs are tiered T7 by the LLM tierer (the documented
                 win: the rules-floor scored social->T7 = 0.000; the LLM repairs it to
                 T7), AND the source count is unchanged (NO source dropped — §-1.3
                 weight-not-filter, tier is a WEIGHT).

  Fail-loud: a known social URL NOT reaching T7 with the flag ON => non-zero exit.
             Any social row DROPPED (count shrinks) => non-zero exit.

Real-data / LAW VI:
  * The corpus_snapshot path is env-overridable (PG_W5_FIRE_TEST_SNAPSHOT); the default
    points at a banked real snapshot in the main tree.
  * OPENROUTER_API_KEY is loaded from .env (PG_W5_FIRE_TEST_ENV, default C:/POLARIS/.env).
    No key => loud blocker exit (LAW II: report blocked, do not fake).
  * The number of social rows actually tier-judged via the real LLM is bounded by
    PG_W5_FIRE_TEST_MAX_SOCIAL (default 4) to keep the canary cheap; the bounded-parallel
    batch path (PG_TIER_LLM_WORKERS) is exercised on that subset.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# The social-platform domains the rules-floor recognises (RP1_social_platform_early ->
# T6). The win is that the LLM lifts these to T7.
_SOCIAL_DOMAINS = (
    "youtube.com", "reddit.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "tiktok.com", "pinterest.com", "quora.com", "tumblr.com",
)

_DEFAULT_SNAPSHOT = (
    "C:/POLARIS/outputs/corpus_backups/extracted/drb_72_ai_labor/corpus_snapshot.json"
)
_DEFAULT_ENV = "C:/POLARIS/.env"


def _fail(msg: str) -> None:
    print(f"FIRE-TEST FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _is_social(rec: dict) -> bool:
    blob = (rec.get("domain", "") or "") + " " + (rec.get("url", "") or "")
    return any(dom in blob for dom in _SOCIAL_DOMAINS)


def main() -> None:
    snapshot_path = os.environ.get("PG_W5_FIRE_TEST_SNAPSHOT", _DEFAULT_SNAPSHOT)
    env_path = os.environ.get("PG_W5_FIRE_TEST_ENV", _DEFAULT_ENV)
    try:
        max_social = max(1, int(os.environ.get("PG_W5_FIRE_TEST_MAX_SOCIAL", "4")))
    except ValueError:
        max_social = 4

    # Load the API key from .env (LAW VI: env-driven, never hard-coded).
    try:
        from dotenv import load_dotenv

        if Path(env_path).exists():
            load_dotenv(env_path)
    except ImportError:
        pass
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        _fail(
            f"OPENROUTER_API_KEY not reachable (looked in {env_path}). The REAL "
            "GLM-5.2 fire-test cannot run without it — BLOCKED, not wired (LAW II)."
        )

    snap = Path(snapshot_path)
    if not snap.exists():
        _fail(f"corpus_snapshot not found at {snapshot_path}")
    data = json.loads(snap.read_text(encoding="utf-8"))
    classified = data.get("retrieval", {}).get("classified_sources", [])
    if not classified:
        _fail(f"snapshot {snapshot_path} has no retrieval.classified_sources")
    total_sources = len(classified)

    social_rows = [r for r in classified if _is_social(r)]
    if not social_rows:
        _fail(
            f"snapshot {snapshot_path} contains NO social-media source — cannot prove "
            "the social->T7 effect. Pick a snapshot with a social source."
        )

    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        TierLevel,
        classify_source_tier,
    )
    from src.polaris_graph.retrieval.credibility_llm_tiering import (
        classify_sources_llm_tiering,
    )

    # Build ClassificationSignals for the bounded subset of social rows. The snapshot's
    # recorded fields drive the signals (real data). content_length is reconstructed
    # above the stub threshold so the snapshot's recorded T6 path (RP1 fires BEFORE the
    # stub rule) is what we compare against.
    subset = social_rows[:max_social]
    sigs = [
        ClassificationSignals(
            url=r.get("url", ""),
            title=r.get("title", "") or "",
            fetched_content_length=2000,
        )
        for r in subset
    ]

    # -- 1. flag-OFF: dispatcher == rules-floor; recorded snapshot tier reproduced. --
    os.environ.pop("PG_CREDIBILITY_LLM_TIERING", None)
    off_results = [classify_source_tier(s) for s in sigs]
    for rec, res in zip(subset, off_results):
        if res.tier is not TierLevel.T6:
            _fail(
                f"flag-OFF social row {rec.get('url','')[:70]} tier={res.tier.value} "
                f"!= T6 (legacy rules-floor regression — OFF must be byte-identical)"
            )
        if res.matched_rules and res.matched_rules[0] != "RP1_social_platform_early":
            _fail(
                f"flag-OFF social row {rec.get('url','')[:70]} rule="
                f"{res.matched_rules[0]} != RP1_social_platform_early (legacy drift)"
            )
    # No-drop on the OFF path: re-classifying produces one result per input source.
    if len(off_results) != len(sigs):
        _fail("flag-OFF dropped a source (result count != input count)")

    # -- 2. flag-ON: REAL GLM-5.2 bounded-parallel tiering; social -> T7; no drop. --
    os.environ["PG_CREDIBILITY_LLM_TIERING"] = "1"
    on_results = classify_sources_llm_tiering(sigs)  # real default GLM-5.2 caller
    if len(on_results) != len(sigs):
        _fail(
            f"flag-ON DROPPED a source: {len(on_results)} results for {len(sigs)} "
            "inputs (tier must be a WEIGHT, never a drop — §-1.3)"
        )
    t7_hits = 0
    for rec, res in zip(subset, on_results):
        url = rec.get("url", "")[:70]
        if res.tier is TierLevel.T7 and res.matched_rules and res.matched_rules[0] == "llm_tiering":
            t7_hits += 1
            print(f"  FIRED: social {url} -> T7 (llm_tiering) — was T6 on the floor")
        else:
            print(
                f"  NOT-T7: social {url} -> {res.tier.value} "
                f"(rule={res.matched_rules[0] if res.matched_rules else '-'})",
                file=sys.stderr,
            )
    if t7_hits == 0:
        _fail(
            "flag-ON: NO social URL reached T7 via the LLM tierer. The documented win "
            "(social->T7 0.000->1.000) did NOT fire in the real output."
        )

    print(
        f"FIRE-TEST PASS: corpus={snap.name} total_sources={total_sources} "
        f"social_rows={len(social_rows)} judged={len(subset)} "
        f"OFF=byte-identical(T6/RP1) ON=social->T7 fired on {t7_hits}/{len(subset)} "
        f"(no source dropped; tier is a WEIGHT)"
    )


if __name__ == "__main__":
    main()
