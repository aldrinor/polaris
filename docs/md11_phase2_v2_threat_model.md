# M-D11 phase 2 v2 — pin trend analysis boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/pin_trends.py`
**Tests:** `tests/polaris_graph/test_md11_phase2_v2_pin_trends.py` (34 passing)
**Pairs with:** M-D11 phase 1 (`model_pin.py`, commit 6c2f17f),
M-D11 phase 2 v1 (`pin_replay.py`, commit 1afd82e).
**Substrate:** stdlib + `model_pin.ModelPin` only — no
LLM clients, no live HTTP, no DB, no file I/O.

---

## Scope

Phase 2 v1 (pin replay) verifies a single pin reproduces a
single run. v2 adds the **trend analysis** layer: given a
chronological sequence of pins, surface per-dimension
configuration drift across the window.

Why this milestone matters: a single pin record is necessary
but not sufficient for replay-grade audit. If the generator
model changes weekly, BEAT-BOTH dimension scores from M-D9
phase 2 across that window are not directly comparable —
the underlying generator is moving. v2 detects that drift
explicitly, surfaces it as a verdict, and enables CI-time
gating on configuration stability.

The 3 verdict tiers:
- **STABLE**: every dimension's stability score ≥ 0.95.
  All BEAT-BOTH cross-window comparisons are defensible.
- **DRIFTING**: ≥ 1 dimension is between 0.5 and 0.95.
  Operator-review prompt — drift may be intentional (e.g.
  staged model rollout) or accidental (e.g. env var
  inconsistency between worker hosts).
- **UNSTABLE**: ≥ 1 dimension < 0.5. Hard signal — block
  cross-window comparisons until investigated.

---

## v1 boundaries

### 1. Pure derivation — no I/O

`pin_trends.py` imports only stdlib + `model_pin.ModelPin`.
No file reads, no DB queries, no HTTP, no LLM clients.
`analyze_pin_trends(pins)` is deterministic given the same
input sequence.

The "M-D11 phase 2 v2 = pure derivation" boundary mirrors
M-D9 phase 2 (BEAT-BOTH scoring) and M-D7 phase 1 (cache
substrate) — substrate primitives never touch runtime
services. Caller code (a future trend-monitoring orchestrator
or CI-gate hook) wires up pin-store reads and verdict-to-
alert glue.

### 2. Out-of-order pins fail loudly, not silently sorted

If `pins[i].captured_at < pins[i-1].captured_at`,
`analyze_pin_trends` raises `PinTrendError` rather than
sorting. Silent sorting would mask operator-side bugs in the
pin store query (e.g. forgot ORDER BY captured_at ASC,
joined two windows, etc.). Per LAW II — fail loudly.

Equal timestamps are allowed: concurrent workers writing a
batch can produce pins with identical `captured_at`.

### 3. Dimension expansion — closed scalars + open dicts

Scalar dimensions (`pin_schema_version`, `inductor_type`,
`inductor_version_hash`, `validation_set_hash`) surface as
their attribute name.

Dict dimensions (`llm_models`, `llm_providers`,
`prompt_version_hashes`, `retrieval_source_versions`,
`env_snapshot`) surface one entry per *observed* key,
joined with a dot: `llm_models.generator`,
`env_snapshot.PG_NLI_ENABLED`, etc.

A key appearing in pin[i] but absent in pin[i-1] is a
transition from None → value (and vice versa). This is
explicit in the `PinDriftEvent` (`before=None`,
`after="value"`).

### 4. None vs "" distinction preserved (env_snapshot)

`ModelPin.env_snapshot` uses `None` to mean "var was unset
at capture time" and `""` to mean "var was set to empty
string". Trend analysis preserves this distinction — going
from `None` → `""` IS a transition, captured as
`before=None, after=""`. Same convention as
`pins_equivalent_for_replay` in `model_pin.py`.

**Mitigation**: the test suite pins this behavior
(`test_env_var_unset_vs_empty_string_are_distinct`) so
future maintenance doesn't accidentally collapse the two.

### 5. Verdict thresholds env-overridable + clamped

Defaults: `stable_threshold=0.95`,
`unstable_threshold=0.5`. Env overrides:
`PG_PIN_TREND_STABLE_THRESHOLD`,
`PG_PIN_TREND_UNSTABLE_THRESHOLD` (per LAW VI).

Both clamped to [0.0, 1.0]. Invalid env strings fall back
to defaults (no exception — keeps autoloop runs from
crashing on a typo). Explicit kwargs override env values.

The relationship `0.0 ≤ unstable_threshold ≤ stable_threshold ≤ 1.0`
is REQUIRED — violating it raises `PinTrendError` at
analyze time. Otherwise verdict semantics break (a
"stable" tier below an "unstable" tier is incoherent).

### 6. Worst-dimension-wins verdict

The report verdict is the worst per-dimension verdict in
the window. One UNSTABLE dimension makes the whole report
UNSTABLE even if 99 others are STABLE. This is the
conservative choice — a single weekly generator-flip is
already enough to invalidate cross-window BEAT-BOTH
comparisons; surfacing the rest of the dimensions as
"stable" hides the actual problem.

**Mitigation**: callers wanting per-dimension granularity
can iterate `report.dimension_stats` directly. The verdict
is for the CI-gate use case where a single bool decision is
needed.

### 7. Single-pin window is trivially stable

`analyze_pin_trends([pin])` returns a STABLE report with
empty `drift_events` and `dimension_stats`. There are no
transitions to analyze. This is intentional: callers
shouldn't have to special-case "I only have one pin" — the
substrate handles it.

Empty pin sequences raise `PinTrendError` rather than
returning a vacuous report — an empty input is a caller
bug, not a "trivially stable" outcome.

---

## v2 v1 NON-goals (defer to v2 v2 / v3)

  - **No live monitoring**: running `analyze_pin_trends`
    every time a pin is captured. That's caller orchestration.
  - **No tolerance auto-calibration**: the 0.95/0.5
    thresholds are educated guesses from the M-D11 phase 1
    asymptote-stop boundary (5+ rounds suggested >5%
    transitional churn is "real" drift). Auto-calibration
    against historical drift rates is v2 v3 territory.
  - **No alert/notification glue**: verdict is a report,
    emitting alerts on UNSTABLE is V19+ live-audit territory.
  - **No pin filtering**: callers wanting "only inductor
    drift" or "only generator drift" filter the input
    sequence themselves. The substrate doesn't ship a
    selector API — that would be premature abstraction.
  - **No drift-velocity metrics** (changes per unit time):
    `stability_score` is per-transition, not time-weighted.
    A pin every 10 minutes vs a pin every week with the
    same transition count gets the same score. v2 v3 may
    add time-weighted variants if operationally needed.

---

## Codex review trail

Round-1 brief incoming. Tool hints (per M-D5 / M-D3 /
M-D9 phase 2 lessons):
- Use `python -m pytest -q tests\polaris_graph\test_md11_phase2_v2_pin_trends.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode
  — Windows sandbox uses cp1252 (this has cut off 4+ Codex
  reviews in the M-D9 phase 2 v5/v6/v7 cycle)
- 34 tests pin all 7 boundaries above

Targeted at 1-2 round convergence per the M-D7/M-D11 phase 2
v1 pattern (substrate work with v1-shipped threat-model
docs and pure-derivation boundaries converges fast).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (live
monitoring, auto-calibration, alert glue) tracked
separately under M-D11 phase 2 v2 v2.
