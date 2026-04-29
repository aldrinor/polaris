# Codex round 1 — M-D11 phase 2 v2 v1 (commit d276fa5)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md11_phase2_v2_pin_trends.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode —
  Windows sandbox uses cp1252 (cut off 4+ Codex reviews on
  M-D9 phase 2 v5/v6/v7 reviews this session)

## Scope
M-D11 phase 2 v1 (commit 1afd82e) shipped pin replay
execution. This v2 layers **trend analysis** on top: given a
chronological sequence of `ModelPin` records, return a
`PinTrendReport` with per-dimension drift events + stability
scores + STABLE/DRIFTING/UNSTABLE verdict.

## What v2 v1 ships

  - `analyze_pin_trends(pins, *, stable_threshold,
    unstable_threshold)` — pure derivation
  - `PinTrendVerdict` enum (3 tiers)
  - `PinDriftEvent` + `DimensionTrendStat` + `PinTrendReport`
  - `report_to_exit_code` (UNSTABLE → 1, others → 0)

## Key boundaries

1. Pure derivation — no I/O, no LLM, no HTTP, no DB.
2. Out-of-order pins fail loudly (no silent sort).
3. Dimension expansion: closed scalars + open dicts joined
   with `.` (e.g. `llm_models.generator`,
   `env_snapshot.PG_NLI_ENABLED`).
4. None vs "" distinction preserved in env_snapshot.
5. Verdict thresholds env-overridable + clamped + relationship
   validated.
6. Worst-dimension-wins verdict.
7. Single-pin window trivially stable; empty raises.

## Test coverage (34/34)

- Empty / single-pin edge cases
- Out-of-order chronology (strict)
- Equal timestamps allowed
- All-stable window
- Drift events per dimension class (model, prompt, validation,
  env appearing/disappearing/None-vs-empty, inductor,
  schema_version)
- Stability score arithmetic (1/3, 2/3, 0.0)
- Verdict thresholds + env overrides + invalid env strings +
  invalid threshold relationship
- Drift events chronologically ordered

## What might Codex probe

- Threshold edge cases (=== boundary at 0.5 / 0.95)
- Float precision in stability_score
- Dimension explosion (huge env_snapshot creates many keys)
- Pin schema additions in future model_pin.py versions —
  does v2 v1 silently miss new dict-fields?
- `os.environ` mutation safety in test fixtures (monkeypatch
  scope)

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure derivation (no I/O)
- [x/ ] Out-of-order fails loudly
- [x/ ] None vs "" preserved
- [x/ ] Verdict thresholds correct

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
