# Codex round 1 — M-INT-0b v1 (commit 9878def)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_m_int_0b_pin_capture_integration.py`
- DO NOT run rg/find — read directly:
  - `scripts/run_honest_sweep_r3.py` lines 52-66 (imports), ~420-475
    (`_capture_run_pin` helper), ~2025-2055 (main_async replay
    plumbing), ~2135-2175 (sweep loop with replay context)
  - `tests/polaris_graph/test_m_int_0b_pin_capture_integration.py`
- DO NOT run Python verification scripts that print Unicode

## Scope
Second integration milestone of `docs/full_online_plan_FINAL.md`.
Wires `model_pin.capture_pin(...)` + `pin_replay`
substrate into the sweep entry point.

## Acceptance bar

Per FINAL_PLAN.md §G, Codex MUST grep-verify all 4:

1. **Imported.** `capture_pin`, `pin_from_json`, `pin_to_json`,
   `build_replay_plan`, `apply_replay_plan`,
   `DEFAULT_REPLAY_ENV_VARS` are imported by
   `scripts/run_honest_sweep_r3.py`.
2. **Invoked.** `_capture_run_pin()` is called inside the
   sweep's `main_async` loop after each `run_one_query`.
   `apply_replay_plan(...)` is entered/exited around the
   sweep loop when `--replay-from-pin` is set.
3. **Run-log evidence.** Test runs verify `model_pin.json` is
   written to run_dir; valid ModelPin round-trips through
   pin_from_json; env_snapshot contains
   `DEFAULT_REPLAY_ENV_VARS` keys.
4. **Rollback flag works.** `PG_CAPTURE_PIN=0` actually
   disables; default=1 captures.

All 4 pinned by 10/10 passing tests.

## Public API change

New CLI flag added to `scripts/run_honest_sweep_r3.py`:
`--replay-from-pin <path>`. Loads a captured pin, builds
replay plan, enters apply_replay_plan context manager around
the sweep loop. The env-snapshot mutation is scoped + reversible.

Backward-compat: existing CLI flags (`--only`, `--out-root`)
unchanged. Sweep behavior with no flags is unchanged except
that each completed run now writes `<run_dir>/model_pin.json`
(behind PG_CAPTURE_PIN flag).

## Diff-against-baseline

OLD: sweep ran queries in a for-loop, wrote sweep_summary.json
+ sweep_summary.md. No pin.

NEW (additive only):
- 6 new imports from model_pin + pin_replay
- `_capture_run_pin(run_id, run_dir, *, notes)` helper added
  before `run_one_query`
- main_async loop:
  - replay context entered before sweep loop
    (nullcontext when no replay)
  - after each `run_one_query`, call `_capture_run_pin`
  - context exited in finally
- main_async CLI: new `--replay-from-pin` arg with bad-path /
  malformed-pin error paths returning exit code 2

Sweep behavior preserved when:
- PG_CAPTURE_PIN=0 (no pin written, no behavior change)
- --replay-from-pin not set (sweep runs as before, with capture)

## What might Codex probe

- pin_replay.apply_replay_plan(plan) signature: it's a
  context manager. We call .__enter__() / .__exit__() manually
  rather than `with` because we don't want to re-indent the
  existing sweep loop body. Verify that's safe.
- Test fixture isolates env via monkeypatch — sufficient for
  CI; production code respects os.environ live values.
- Failure path: capture_pin can raise (e.g. malformed
  llm_models). v1 catches broad Exception and prints to stdout;
  Codex may suggest using logging instead, but stdout is
  consistent with the rest of the sweep's progress prints.
- Default OPENROUTER_DEFAULT_MODEL value when env is unset:
  v1 uses the literal string "unknown". Could be empty
  string if env is set to ""; pin captures that distinction
  via env_snapshot.
- Whether DEFAULT_REPLAY_ENV_VARS is the right capture set
  vs DEFAULT_ROUTING_ENV_VARS (M-D11 phase 1 has both;
  v1 uses the replay set per its name).

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Acceptance bar
- [x/ ] Imported (6 names from model_pin + pin_replay)
- [x/ ] Invoked (_capture_run_pin in main_async loop;
  apply_replay_plan around sweep on --replay-from-pin)
- [x/ ] Run-log evidence (model_pin.json written; pin
  round-trips; env_snapshot has DEFAULT_REPLAY_ENV_VARS keys)
- [x/ ] PG_CAPTURE_PIN=0 actually disables

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```

Tool hints repeated:
- `python -m pytest -q tests\polaris_graph\test_m_int_0b_pin_capture_integration.py`
- 10/10 tests should pass
