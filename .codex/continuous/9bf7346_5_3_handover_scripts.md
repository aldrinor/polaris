# Per-commit Codex brief — `9bf7346`

**Commit:** `9bf7346 PL: v6.2 handover scripts — cost_summary + replay_pin + run_pin_replay (9/9 tests)`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (4):**
- `scripts/v6/cost_summary.py` (new, ~95 lines)
- `scripts/v6/replay_pin.py` (new, ~70 lines)
- `scripts/v6/run_pin_replay.py` (new, ~80 lines)
- `tests/v6/test_scripts_v6_handover.py` (new, 9 tests)

## What this commit does

Closes 3 open promises from `docs/carney_handover/runbook.md`. The runbook §3, §5, §6 reference 3 scripts that previously didn't exist on disk:

1. **`cost_summary.py`** — runbook §5: `python scripts/v6/cost_summary.py --since 2026-10-01`
   - Walks every `.json` under `--bundles-dir` (default `outputs/runs/`).
   - Validates each as `EvidenceContract`, sums `cost_usd`.
   - With `--since YYYY-MM-DD`: filters by `finished_at`.
   - Reports `sum/avg/min/max/p50/p95`. Exits 1 if no bundles match.

2. **`replay_pin.py`** — runbook §6: `python scripts/v6/replay_pin.py --pin-id <pin_id>`
   - Loads two `RunPin` JSON files (original + replay).
   - Calls existing `compute_pin_diff()` from `polaris_v6.replay.differ`.
   - Prints human-readable summary (or `--json` for machine consumption).
   - Exits 1 if `is_regression=True`, 0 otherwise.

3. **`run_pin_replay.py`** — runbook §3: `python scripts/v6/run_pin_replay.py --against=goldens`
   - Loads pin sets from `--baseline-dir` + `--candidate-dir`.
   - Pairs by `run_id` via existing `run_regression_lab()`.
   - Prints summary + per-regression detail.
   - Exit codes: 0 PASS, 1 FAIL (any regression), 2 missing dir.

All 3 are pure CLI shells — they reuse existing substrate from `polaris_v6.schemas.evidence_contract`, `polaris_v6.replay.{differ,schema}`, `polaris_v6.regression_lab.runner`. **No new business logic**, just argparse + JSON I/O + invocation.

## Test coverage

`tests/v6/test_scripts_v6_handover.py` runs each script via `subprocess.run` with the parent env preserved (so pip-installed pydantic resolves), `PYTHONPATH=src` for `polaris_v6.*`, against tmp dirs + the existing golden EvidenceContract fixtures. Asserts both stdout content AND exit codes:

- 3 cost_summary tests (real bundles + reports / empty dir / since filter)
- 3 replay_pin tests (no-change PASS / pipeline-status regression / --json)
- 3 run_pin_replay tests (clean PASS / regression FAIL / missing dir)

Total **9/9 PASS** in 11.16s.

## Acceptance criteria

1. **Subprocess env inheritance.** The `_run` helper uses `os.environ.copy()` then overlays `PYTHONPATH` so pip packages stay discoverable. Earlier sparse-env attempt failed with `ModuleNotFoundError: pydantic` until fixed.
2. **ASCII-only stdout.** Output uses `->` not `→` because Win32 default `charmap` codec rejects U+2192. Necessary for both the local Windows dev env AND CI runners that may not set PYTHONIOENCODING.
3. **No new logic.** Each script is a thin CLI on existing substrate. Codex must verify no validation logic, no schema reshaping, no model-rotation policy hidden inside the scripts.
4. **Exit codes are meaningful.** 0=PASS, 1=substantive failure (no bundles, regression, etc.), 2=usage error (missing dir). Tests assert each.
5. **Real fixtures, not mocks.** Tests use the existing 6 EvidenceContract goldens. cost_summary's "no bundles since 2030" test relies on real `finished_at: 2026-05-01` strings, not stubs.

## Codex focus

- **P0:** Does the runbook §3 actually invoke `--against=goldens` (single arg) but my `run_pin_replay.py` requires `--baseline-dir` + `--candidate-dir`? The runbook signature is conflicting. Either (a) update runbook to match script, (b) add a thin `--against goldens` shorthand. I'd lean (a) for honesty.
- **P0:** `cost_summary.py` uses `datetime.fromisoformat(contract.finished_at.rstrip("Z"))` — Python 3.11+ accepts Z natively; the strip is a defensive belt-and-suspenders. Verify it doesn't double-strip a real `+00:00` suffix that legitimate bundles might use.
- **P1:** `compute_pin_diff()` raises `ValueError` if both pin_ids match (test fixture safety). My replay_pin.py doesn't catch + reword that — script crashes with traceback. Should we wrap in a friendly error message?
- **P2:** No way to filter cost_summary by template — useful for "what's our clinical-template cost vs housing?" Future enhancement.

## Cross-review

Lands at `outputs/audits/continuous/9bf7346/cross_review.md`. Counter now **2/5** (new batch since 4fe03f7 audit subagent fired).
