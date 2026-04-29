"""M-D11 phase 2 v2 (Phase D): Pin trend analysis.

Phase 2 v1 (`pin_replay.py`, commit 1afd82e) shipped pin
replay execution — apply a single pin's captured runtime
configuration and verify reproduction.

Phase 2 v2 layers **trend analysis** on top of a chronological
sequence of pins: detect drift in model assignments, prompt
versions, validation set hashes, env snapshots, and other
schema dimensions. Pure derivation — given a sequence of
`ModelPin` records, return a `PinTrendReport`. No I/O, no
side effects.

## Why this milestone matters

A single pin records one run's configuration. The replay
substrate (v1) verifies that pin reproduces the run.
Operationally, what matters is *whether the configuration
is stable across runs* — if the generator model is changing
weekly, the BEAT-BOTH dimension scores from M-D9 phase 2 are
not comparable across runs because the generator itself is
moving.

Trend analysis surfaces:
- **Model drift**: a `llm_models` role flipping model_id
  more often than expected
- **Prompt drift**: `prompt_version_hashes` changing without
  a corresponding model bump
- **Validation drift**: `validation_set_hash` flipping (means
  M-D1 precision benchmark inputs changed)
- **Env drift**: high-churn env vars in `env_snapshot`
- **Schema drift**: `pin_schema_version` progression

## What v2 v1 ships

  - `PinDriftEvent` dataclass — one observed transition
  - `DimensionTrendStat` dataclass — per-dimension stats
  - `PinTrendVerdict` enum — STABLE | DRIFTING | UNSTABLE
  - `PinTrendReport` dataclass — full report
  - `analyze_pin_trends(pins, *, stability_thresholds)` — pure
    derivation function

## Substrate boundary

Pure stdlib + `model_pin.ModelPin`. No LLM clients, no
HTTP, no DB, no file I/O. Every public function is
deterministic given the same input sequence.

## What v2 v1 does NOT do

  - No live trend monitoring (running this on every pin
    capture). That's caller orchestration.
  - No tolerance auto-calibration against historical drift
    rates. Defaults are conservative.
  - No alerting / notification glue. The verdict is a
    report; emitting alerts on `UNSTABLE` is V19+ live-audit
    territory.
  - No pin filtering / selection (e.g. "only inductor-related
    drift"). Caller filters the input sequence.

See `docs/md11_phase2_v2_threat_model.md` for boundaries.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from src.polaris_graph.audit_ir.model_pin import ModelPin


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PinTrendError(ValueError):
    """Raised on contract violations — empty pin sequence,
    out-of-order pins, malformed inputs."""


# ---------------------------------------------------------------------------
# Verdict enum + dataclasses
# ---------------------------------------------------------------------------


class PinTrendVerdict(str, Enum):
    """Trend report verdict.

    STABLE: every dimension's stability_score >= the stable
       threshold (default 0.95). Configuration is reproducibly
       consistent across the window.
    DRIFTING: at least one dimension is between the unstable
       and stable thresholds. Operator should review whether
       the drift is intentional (e.g. a model upgrade rollout)
       or accidental (e.g. an env var unintentionally varying
       between worker hosts).
    UNSTABLE: at least one dimension's stability_score is
       below the unstable threshold (default 0.5). Strong
       signal that BEAT-BOTH dimension scoring across this
       window is comparing apples to oranges.
    """

    STABLE = "stable"
    DRIFTING = "drifting"
    UNSTABLE = "unstable"


@dataclass(frozen=True)
class PinDriftEvent:
    """One observed transition between two consecutive pins
    on one dimension.

    `pin_index` is the position of the *later* pin in the
    input sequence (the pin where the change first appears).
    `before` and `after` are the dimension values; either may
    be None when a key was absent in one of the pins or when
    the dimension's value is itself nullable (e.g. an
    env_snapshot var that was unset in pin N and set in
    pin N+1).
    """

    pin_index: int
    captured_at: float
    dimension: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class DimensionTrendStat:
    """Per-dimension stability statistics over the window.

    `change_count` is the number of transitions where the
    dimension value differed from the previous pin.
    `total_transitions` is `len(pins) - 1` for a non-empty
    window. `stability_score` is `1.0 - (change_count /
    total_transitions)` — 1.0 for no changes, 0.0 for changes
    on every transition.
    """

    dimension: str
    change_count: int
    total_transitions: int
    stability_score: float


@dataclass(frozen=True)
class PinTrendReport:
    """Trend analysis output.

    `pin_count` is the number of pins analyzed.
    `window_start` / `window_end` are the captured_at of the
    first / last pin (UNIX epoch float; same convention as
    `ModelPin.captured_at`).
    `drift_events` is the full chronological list of
    transitions observed (one per change per dimension).
    `dimension_stats` aggregates per-dimension statistics.
    `verdict` is the rolled-up trend judgment.
    """

    pin_count: int
    window_start: float
    window_end: float
    drift_events: tuple[PinDriftEvent, ...] = field(default_factory=tuple)
    dimension_stats: tuple[DimensionTrendStat, ...] = field(default_factory=tuple)
    verdict: PinTrendVerdict = PinTrendVerdict.STABLE


# ---------------------------------------------------------------------------
# Stability thresholds (env-overridable per LAW VI)
# ---------------------------------------------------------------------------


DEFAULT_STABLE_THRESHOLD = 0.95
DEFAULT_UNSTABLE_THRESHOLD = 0.5


def _read_stable_threshold_from_env() -> float:
    raw = os.environ.get("PG_PIN_TREND_STABLE_THRESHOLD")
    return _coerce_threshold(raw, DEFAULT_STABLE_THRESHOLD)


def _read_unstable_threshold_from_env() -> float:
    raw = os.environ.get("PG_PIN_TREND_UNSTABLE_THRESHOLD")
    return _coerce_threshold(raw, DEFAULT_UNSTABLE_THRESHOLD)


def _coerce_threshold(raw: str | None, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Dimension extraction
# ---------------------------------------------------------------------------


# Top-level scalar dimensions on ModelPin. Dict-valued fields
# (llm_models, env_snapshot, etc.) get expanded per-key below.
_SCALAR_DIMENSIONS: tuple[str, ...] = (
    "pin_schema_version",
    "inductor_type",
    "inductor_version_hash",
    "validation_set_hash",
)

# Dict-valued fields get one dimension per observed key,
# joined with a dot: e.g. "llm_models.generator".
_DICT_DIMENSIONS: tuple[str, ...] = (
    "llm_models",
    "llm_providers",
    "prompt_version_hashes",
    "retrieval_source_versions",
    "env_snapshot",
)


def _extract_dimensions(pin: ModelPin) -> dict[str, str | None]:
    """Flatten a ModelPin into a dict of dimension -> value.

    Scalar dimensions surface as their attribute name. Dict
    dimensions surface one entry per key. Keys absent from a
    given pin map to None — which is distinguished from a key
    explicitly set to None (e.g. env_snapshot var that was
    unset at capture time).

    The caller's transition logic treats both as "no value",
    so the distinction does not affect change-counting; it
    matters only for surfacing in PinDriftEvent.before/after.
    """
    flat: dict[str, str | None] = {}
    for attr in _SCALAR_DIMENSIONS:
        flat[attr] = getattr(pin, attr, None)
    for attr in _DICT_DIMENSIONS:
        d = getattr(pin, attr, None) or {}
        for key, value in d.items():
            flat[f"{attr}.{key}"] = value
    return flat


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_pin_trends(
    pins: Sequence[ModelPin],
    *,
    stable_threshold: float | None = None,
    unstable_threshold: float | None = None,
) -> PinTrendReport:
    """Compute a `PinTrendReport` over a chronological pin
    sequence.

    Pins must be ordered by `captured_at` ascending. Out-of-
    order input raises `PinTrendError` rather than silently
    sorting — silent sorting would mask operator-side bugs in
    the pin store query.

    `stable_threshold` and `unstable_threshold` default to env
    overrides (`PG_PIN_TREND_STABLE_THRESHOLD`,
    `PG_PIN_TREND_UNSTABLE_THRESHOLD`) per LAW VI, falling
    back to 0.95 and 0.5 respectively. Thresholds are clamped
    to [0.0, 1.0].
    """
    if not isinstance(pins, Sequence) or isinstance(pins, (str, bytes)):
        raise PinTrendError(
            f"pins must be a sequence of ModelPin, got {type(pins).__name__}"
        )
    n = len(pins)
    if n == 0:
        raise PinTrendError("pins sequence is empty; need at least one pin")

    # Validate types + chronological order.
    last_ts: float | None = None
    for i, pin in enumerate(pins):
        if not isinstance(pin, ModelPin):
            raise PinTrendError(
                f"pins[{i}] is not a ModelPin (got {type(pin).__name__})"
            )
        if last_ts is not None and pin.captured_at < last_ts:
            raise PinTrendError(
                f"pins[{i}].captured_at ({pin.captured_at}) is earlier "
                f"than pins[{i-1}].captured_at ({last_ts}); "
                "pins must be chronologically ordered"
            )
        last_ts = pin.captured_at

    # Codex round-1 MEDIUM fix (v2): explicit kwargs are clamped
    # to [0.0, 1.0] the same way env overrides are. v1 only
    # clamped env values; explicit kwargs went unclamped and
    # raised on out-of-range values, contradicting the docstring
    # contract.
    if stable_threshold is None:
        stable_t = _read_stable_threshold_from_env()
    else:
        stable_t = max(0.0, min(1.0, stable_threshold))
    if unstable_threshold is None:
        unstable_t = _read_unstable_threshold_from_env()
    else:
        unstable_t = max(0.0, min(1.0, unstable_threshold))
    if not (unstable_t <= stable_t):
        raise PinTrendError(
            f"thresholds must satisfy unstable ({unstable_t}) <= "
            f"stable ({stable_t}) after clamping to [0.0, 1.0]"
        )

    window_start = pins[0].captured_at
    window_end = pins[-1].captured_at

    # Single-pin window: no transitions, trivially stable.
    if n == 1:
        return PinTrendReport(
            pin_count=1,
            window_start=window_start,
            window_end=window_end,
            drift_events=(),
            dimension_stats=(),
            verdict=PinTrendVerdict.STABLE,
        )

    total_transitions = n - 1

    # Walk pin pairs, collect drift events per dimension.
    # Codex round-1 MEDIUM fix (v2): iterate dimensions in
    # SORTED order so drift_events tuple is deterministic
    # across processes. v1 iterated `seen_dims` (a set), which
    # has hash-seed-dependent order — same input could yield
    # different drift_events tuples, violating the pure-
    # derivation contract.
    drift_events: list[PinDriftEvent] = []
    change_counts: dict[str, int] = {}
    seen_dims: set[str] = set()

    prev_flat = _extract_dimensions(pins[0])
    seen_dims.update(prev_flat.keys())
    for i in range(1, n):
        cur_flat = _extract_dimensions(pins[i])
        seen_dims.update(cur_flat.keys())
        # Sorted iteration: drift events for one transition
        # appear in dimension-name lexicographic order. Across
        # transitions, pin_index orders the events
        # chronologically (preserved).
        for dim in sorted(seen_dims):
            before = prev_flat.get(dim)
            after = cur_flat.get(dim)
            if before != after:
                drift_events.append(
                    PinDriftEvent(
                        pin_index=i,
                        captured_at=pins[i].captured_at,
                        dimension=dim,
                        before=before,
                        after=after,
                    )
                )
                change_counts[dim] = change_counts.get(dim, 0) + 1
        prev_flat = cur_flat

    # Build per-dimension stats. A dimension never seen has 0
    # changes; a dimension seen once has 0 changes too.
    stats: list[DimensionTrendStat] = []
    for dim in sorted(seen_dims):
        changes = change_counts.get(dim, 0)
        stability = 1.0 - (changes / total_transitions)
        stats.append(
            DimensionTrendStat(
                dimension=dim,
                change_count=changes,
                total_transitions=total_transitions,
                stability_score=stability,
            )
        )

    # Verdict: worst-dimension wins.
    verdict = PinTrendVerdict.STABLE
    for stat in stats:
        if stat.stability_score < unstable_t:
            verdict = PinTrendVerdict.UNSTABLE
            break
        if stat.stability_score < stable_t:
            verdict = PinTrendVerdict.DRIFTING
            # Don't break — a later dim might be UNSTABLE.

    return PinTrendReport(
        pin_count=n,
        window_start=window_start,
        window_end=window_end,
        drift_events=tuple(drift_events),
        dimension_stats=tuple(stats),
        verdict=verdict,
    )


def report_to_exit_code(report: PinTrendReport) -> int:
    """Map verdict to CI exit code.

    UNSTABLE → 1 (block CI / merge)
    STABLE | DRIFTING → 0 (proceed; DRIFTING surfaces to operator
                           for review but does not block)
    """
    return 1 if report.verdict == PinTrendVerdict.UNSTABLE else 0
