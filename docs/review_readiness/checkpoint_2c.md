# Phase 2C checkpoint — generation checkpoint (pre-check data only, flag-gated)

Branch: `chore/review-readiness-phase2c`  ·  Base: `gate-inversion`  ·  Worktree: `/home/polaris/wt/phase2c`

## What was wired

Pipeline A (`src/polaris_graph/honest_pipeline.py`) is a synchronous, non-LangGraph
orchestrator, so the LangGraph `AsyncSqliteSaver` in `checkpoint_manager` cannot be
reused there. Phase 2C adds a minimal, self-contained generation checkpoint to that
pipeline that persists **only pre-check data** — the draft/outline plus the retrieved
`evidence_pool` — so an interrupted run can resume without re-generating, while the
faithfulness verdict is always recomputed on resume.

Three helpers were added near the top of the module:

- `_pg2c_checkpoint_enabled()` — returns `True` only when `PG_CHECKPOINT_ENABLED == '1'`.
- `_pg2c_checkpoint_path(run_id)` — `PG_CHECKPOINT_DIR/pg2c_precheck_{run_id}.json`.
- `_pg2c_save_precheck(run_id, draft_text, evidence_pool)` — writes exactly
  `{run_id, draft_text, evidence_pool}` as JSON. Best-effort: any failure is logged
  and swallowed so checkpointing can never break generation.
- `_pg2c_load_precheck(run_id)` — returns `{run_id, draft_text, evidence_pool}` or
  `None`; never a verdict.

Two flag-gated call sites in `run_honest_pipeline`:

- **Reload** (line 303): at the top of the run, right after `run_dir` is created and
  before the Phase 2b scope gate. When the flag is on and a checkpoint exists, only
  `draft_text` is restored (`draft_text = _pg2c_reloaded.get("draft_text", draft_text)`).
- **Save** (line 451): immediately before `strict = strict_verify(...)` (line 453),
  right after `evidence_pool = {ev["evidence_id"]: ev for ev in evidence}` is built —
  so the write happens **before** any verdict is computed.

Pipeline B (`graph.py`) was already fully wired via the native LangGraph saver
(`get_checkpointer` at 1428, compile-time checkpointer at 1501–1502) and was left
untouched.

## Flag-off byte-identical proof (oracle SHA)

Default `PG_CHECKPOINT_ENABLED = '0'` (`config_defaults.py:97`) — unchanged. With the
flag off, `_pg2c_checkpoint_enabled()` returns `False` and neither call site executes,
so the generation path is byte-identical to today.

Oracle replay (validate GATE 1, critical):

- `flag_off_oracle_sha = 9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98`
  (short `9c0a3d43`) — matches the recorded golden **exactly**.
- Reproduced with `PG_CHECKPOINT_ENABLED` **unset** and explicitly **=0** — identical
  SHA both ways.
- Acceptance replay: `replay artifact BYTE-IDENTICAL to recorded golden` +
  `ACCEPTANCE PASSED: all run controls valid` (exit 0).

## Pre-check-data-only guarantee

`_pg2c_save_precheck` serializes exactly `{run_id, draft_text, evidence_pool}` and runs
**before** `strict_verify`, so the faithfulness / `strict_verify` verdict physically
cannot be persisted. The new roundtrip test (`tests/test_checkpoint_roundtrip.py`)
asserts the absence of every verdict-shaped key (`faithfulness`, `strict_verify`,
`verdict`, `kept_sentences`, …) both structurally (exact key set) and as raw-byte
substrings of the serialized artifact.

## Reload re-verifies design

`_pg2c_load_precheck` restores **only** `draft_text`; the stored `evidence_pool` is
never reinstated. Execution falls through to the Phase 4 step where
`strict_verify(draft_text, evidence_pool, ...)` runs **from scratch** on the reloaded
draft (line 453) — the verdict is recomputed, never read from disk. A poisoned or
partial checkpoint cannot corrupt the verdict:

- Malformed JSON, a missing `draft_text` key, and load errors all fall back to the
  supplied `draft_text` (a required kwarg, so the `.get()` default is always valid).
- Save errors are swallowed and never skip verification.
- A hostile draft swapped on disk must still pass a fresh `strict_verify` and renders
  only from `strict.kept_sentences` — there is no verdict bypass.

## Validation (all gates green, HEAD c5448ec)

| Gate | Result |
|------|--------|
| 1 — flag-off byte-identical | PASS (oracle SHA `9c0a3d43…db98`, flag unset and =0) |
| 2 — collection unchanged | PASS (16738 collected, 11 errors — baseline match) |
| 3 — config characterization | PASS (`test_config_registry` + `test_settings_models` = 9 passed) |
| 4 — flag-on roundtrip (new test) | PASS 4/4 (`tests/test_checkpoint_roundtrip.py`, hermetic) |

Validate flags: `flag_off_byte_identical=true`, `collection_ok=true`,
`roundtrip_test_passes=true`, `no_verdict_persisted=true`.

## Codex verdict

**CHECKPOINT-SAFE** (CODEX / GPT-5.6, medium effort, exit 0). Evidence independently
re-verified against HEAD `c5448ec` before gating:

- Q1 Flag-off byte-identical: YES (both call sites guarded; default `'0'` unchanged;
  SHA reproduced flag-off).
- Q2 Pre-check data only: YES (save writes `{run_id, draft_text, evidence_pool}` before
  `strict_verify`; verdict cannot be persisted).
- Q3 Reload re-verifies from scratch: YES (only `draft_text` restored; one fresh
  `strict_verify` invocation confirmed by sentinel test).
- Q4 Poisoned/partial checkpoint cannot corrupt faithfulness: confirmed (all failure
  modes fall back and re-verify; no verdict bypass).
- Non-blocking robustness note: `_pg2c_load_precheck` does not type-validate
  `draft_text`/`run_id` — an availability/robustness concern only, not a verdict-bypass
  path. Does not block.
