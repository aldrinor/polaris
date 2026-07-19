"""Parameterized full-scale launcher — Q6 consolidation of run_full_scale_vNN.

This module is the single source of truth for the run_full_scale_v10..v30
launchers. Each historical vNN launcher differed only by:
  - a VARIANT env-profile dict (capacity knobs + feature flags),
  - a default --out-root,
  - a console log prefix,
  - a launch-banner label.

Every one of those launchers is now a thin call-through shim:

    from run_full_scale import run
    import sys
    run("vNN", sys.argv[1:])

`run(variant, argv)` reproduces the historical behavior BYTE-FOR-BYTE:
  - VARIANT_ENV[variant] equals the original vNN script's env dict exactly.
  - Env precedence is preserved (override=False: never clobber a value the
    user already set in the parent shell / .env).
  - --only and --out-root are injected ONLY when absent.
  - CLI args are forwarded verbatim to scripts.run_honest_sweep_r3.main.

Direct use is possible too:

    python scripts/run_full_scale.py --variant v28 --out-root outputs/x
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# VARIANT_ENV — each entry reproduces the original run_full_scale_vNN.py env
# dict BYTE-FOR-BYTE (verified against the pre-consolidation scripts).
#
# History (knob deltas):
#   v10/v23/v24/v25  base 13-key profile.
#   v26              + PG_M41D_HC_QUOTA=2
#   v27              + PG_SWEEP_MAX_REGULATORY_ANCHORS=12
#   v28/v29          PG_LIVE_MAX_EV_TO_GEN 600->300;
#                    + PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS=15
#   v30_phase2       + PG_V30_ENABLED=1, PG_V30_PHASE2_ENABLED=1
# ---------------------------------------------------------------------------

# The base profile shared verbatim by v10/v23/v24/v25.
_BASE_ENV: dict[str, str] = {
    # Sweep-level retrieval knobs (scripts/run_honest_sweep_r3.py:536-538)
    "PG_SWEEP_MAX_SERPER":    "50",     # amplified queries fanned to Serper
    "PG_SWEEP_MAX_S2":        "50",     # amplified queries to Semantic Scholar
    "PG_SWEEP_FETCH_CAP":     "500",    # max URLs classified + fetched per query

    # Generator evidence pool cap
    # (scripts/run_honest_sweep_r3.py:902 -> max_rows in evidence_selector)
    "PG_LIVE_MAX_EV_TO_GEN":  "600",

    # Budget cap (src/polaris_graph/... PG_MAX_COST_PER_RUN)
    "PG_MAX_COST_PER_RUN":    "10.00",

    # M-23 access-bypass feature flags
    "PG_UNPAYWALL_ENABLED":   "1",      # M-23a Unpaywall step 0 (default on)
    "PG_CRAWL4AI_ENABLED":    "1",      # concurrent Crawl4AI primary backend
    "PG_FIRECRAWL_ENABLED":   "0",      # per user directive: costs money
    "PG_TRAFILATURA_ENABLED": "1",      # concurrent Trafilatura backend

    # Scraper circuit breakers (keep defaults tolerant)
    "PG_CRAWL4AI_TIMEOUT":    "30",
    "PG_CIRCUIT_BREAKER_THRESHOLD": "8",
    "PG_CIRCUIT_BREAKER_COOLDOWN":  "120",

    # Sci-Hub DISABLED by default (legal/provenance, I-faith-002); CORE is the OA full-text source
    "PG_SCIHUB_ENABLED":      "0",
}


VARIANT_ENV: dict[str, dict[str, str]] = {
    "v10": dict(_BASE_ENV),
    "v23": dict(_BASE_ENV),
    "v24": dict(_BASE_ENV),
    "v25": dict(_BASE_ENV),
    # v26 = base + M-42d HC quota knob.
    "v26": {**_BASE_ENV, "PG_M41D_HC_QUOTA": "2"},
    # v27 = v26 + M-43 regulatory anchor cap.
    "v27": {
        **_BASE_ENV,
        "PG_M41D_HC_QUOTA": "2",
        "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
    },
    # v28 = v27 + M-46 EV cap 600->300 + M-35 primary-trial anchor cap.
    "v28": {
        **_BASE_ENV,
        "PG_LIVE_MAX_EV_TO_GEN": "300",
        "PG_M41D_HC_QUOTA": "2",
        "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
        "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
    },
    # v29 = same knobs as v28.
    "v29": {
        **_BASE_ENV,
        "PG_LIVE_MAX_EV_TO_GEN": "300",
        "PG_M41D_HC_QUOTA": "2",
        "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
        "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
    },
    # v30_phase2 = v29 knobs + V30 phase gating.
    "v30_phase2": {
        "PG_V30_ENABLED": "1",
        "PG_V30_PHASE2_ENABLED": "1",
        **_BASE_ENV,
        "PG_LIVE_MAX_EV_TO_GEN": "300",
        "PG_M41D_HC_QUOTA": "2",
        "PG_SWEEP_MAX_REGULATORY_ANCHORS": "12",
        "PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS": "15",
    },
}


# Per-variant console log prefix (reproduces the original [VNN env] tags).
_LOG_PREFIX: dict[str, str] = {
    "v10": "V10 env",
    "v23": "V23 env",
    "v24": "V24 env",
    "v25": "V25 env",
    "v26": "V26 env",
    "v27": "V27 env",
    "v28": "V28 env",
    "v29": "V29 env",
    "v30_phase2": "V30-P2 env",
}

# Per-variant launch-banner label (reproduces the original banner text).
_BANNER_LABEL: dict[str, str] = {
    "v10": "V10 launch",
    "v23": "V23 launch",
    "v24": "V24 launch",
    "v25": "V25 launch",
    "v26": "V26 launch",
    "v27": "V27 launch",
    "v28": "V28 launch",
    "v29": "V29 launch",
    "v30_phase2": "V30 Phase-2 launch",
}

# Per-variant default --out-root (injected only when absent).
_DEFAULT_OUT_ROOT: dict[str, str] = {
    "v10": "outputs/full_scale_v10",
    "v23": "outputs/full_scale_v23",
    "v24": "outputs/full_scale_v24",
    "v25": "outputs/full_scale_v25",
    "v26": "outputs/full_scale_v26",
    "v27": "outputs/full_scale_v27",
    "v28": "outputs/full_scale_v28",
    "v29": "outputs/full_scale_v29",
    "v30_phase2": "outputs/full_scale_v30_phase2",
}

# Default single-query slug for the auto-loop (caller can override).
_DEFAULT_ONLY = "clinical_tirzepatide_t2dm"


def _apply_env(variant: str) -> None:
    """Export the variant's env. Does NOT overwrite values already set by the
    user in the parent shell — so manual overrides remain possible. Does NOT
    overwrite .env-loaded values either; python-dotenv's load_dotenv() inside
    the sweep script uses its default override=False behavior.
    """
    prefix = _LOG_PREFIX[variant]
    for key, val in VARIANT_ENV[variant].items():
        existing = os.environ.get(key)
        if existing is None or existing == "":
            os.environ[key] = val
            print(f"[{prefix}]  {key} = {val}")
        else:
            print(f"[{prefix}]  {key} = {existing}  (already set, not overriding)")


def run(variant: str, argv: list[str]) -> int:
    """Reproduce run_full_scale_<variant>.py behavior for the given argv.

    `argv` is the list of CLI args (i.e. sys.argv[1:]). It is mutated in place
    to inject --only / --out-root defaults only when absent, then forwarded to
    the sweep script verbatim via sys.argv.
    """
    if variant not in VARIANT_ENV:
        raise KeyError(
            f"Unknown variant {variant!r}; known: {sorted(VARIANT_ENV)}"
        )

    _apply_env(variant)

    # Inject defaults only when absent (verbatim to the historical scripts).
    if "--only" not in argv:
        argv.extend(["--only", _DEFAULT_ONLY])
    if "--out-root" not in argv:
        argv.extend(["--out-root", _DEFAULT_OUT_ROOT[variant]])

    # The sweep script reads sys.argv directly; forward verbatim. sys.argv[0]
    # is preserved (the invoking script / shim path) exactly as before.
    sys.argv = [sys.argv[0], *argv]

    print("=" * 72)
    print(f"{_BANNER_LABEL[variant]} with argv: {sys.argv}")
    print("=" * 72)

    # Import AFTER env is set so module-level env.getenv() calls see our values.
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from scripts.run_honest_sweep_r3 import main as sweep_main
    return sweep_main()


def _parse_variant(argv: list[str]) -> tuple[str, list[str]]:
    """Extract --variant VALUE from argv for direct CLI use; returns
    (variant, remaining_argv). Defaults to v30_phase2 if unspecified.
    """
    out: list[str] = []
    variant = "v30_phase2"
    i = 0
    while i < len(argv):
        if argv[i] == "--variant":
            variant = argv[i + 1]
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return variant, out


def main() -> int:
    variant, rest = _parse_variant(sys.argv[1:])
    return run(variant, rest)


if __name__ == "__main__":
    raise SystemExit(main())
