# Codex DIFF gate — I-arch-004 A2 (#1248): section timeout + token-budget sizing

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## ITER-1 RESOLUTION (your 1 P1 fixed — please verify)
Your iter-1 P1 was correct: `preflight_import_time_constants()` (which held the generator-timeout floor) is NOT called on the real Gate-B path, so a stale low `PG_GENERATOR_LLM_TIMEOUT_SECONDS` froze `openrouter_client.GENERATOR_TIMEOUT_SECONDS` while the slate raised only `os.environ` and `preflight_full_capability()` passed on the env. Fixed by mirroring the existing `set_max_cost_per_run` pattern:
- Added `set_generator_timeout_seconds()` + `get_generator_timeout_seconds()` to `openrouter_client.py` (sync the live module global the generator actually reads).
- `apply_full_capability_benchmark_slate()` now calls `set_generator_timeout_seconds(int(os.environ["PG_GENERATOR_LLM_TIMEOUT_SECONDS"]))` right after `set_max_cost_per_run()`.
- `preflight_full_capability()` now validates the LIVE constant via `get_generator_timeout_seconds()` against the `_BENCHMARK_EXTRA_ENV_FLOORS` floor (6500), not just env.
- New tests: `test_slate_syncs_live_generator_timeout_constant` (set live constant=600 + env=600 → after slate live constant ≥6500) and `test_preflight_catches_stale_live_generator_timeout` (env=6500 but live constant forced to 600 → preflight RAISES). 8 A2 tests + 7 regression pass. (`preflight_import_time_constants` import-const floor retained as defense-in-depth.)
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Your job
VERIFY this diff (evidence pack below — do not hunt). It is the timeout/token-sizing half of the drb_72 fix (A1 = crash isolation is a separate gated diff). Red-team per `.codex/codex_red_team_checklist.md`. Diff: `.codex/I-arch-004/A2_timeout_token_sizing/codex_diff.patch`. Files: `scripts/dr_benchmark/run_gate_b.py`, `scripts/run_honest_sweep_r3.py`, `src/polaris_graph/llm/openrouter_client.py`, `tests/dr_benchmark/test_section_timeout_token_sizing_iarch004.py`.

## The bug
The drb_72 run died composing the V30 section: the SMOKE wall-clock (`PG_SECTION_WALLCLOCK_SECONDS=600`) killed the DeepSeek `generate()` mid-stream x2. Three sizing defects let that happen and would recur on a real Gate-B run:
1. The Gate-B slate (`_FULL_CAPABILITY_BENCHMARK_SLATE`) did NOT set `PG_SECTION_WALLCLOCK_SECONDS` / `PG_GENERATOR_LLM_TIMEOUT_SECONDS` / `PG_SECTION_MAX_TOKENS` at all → a real run got module defaults: wall-clock OFF (the original #1248 hang-forever), generator timeout 1800s (sized for the old 16384 ceiling), section budget 16384.
2. `run_honest_sweep_r3.py:6132` defaulted `PG_SECTION_MAX_TOKENS` to a STALE **16384**, shadowing the module's intended 64000 (confirmed by Codex sessions g2/g5/h1).
3. `openrouter_client.py:801` `GENERATOR_TIMEOUT_SECONDS` default 1800s.

## The data-grounded sizing (from the drb_72 cost_ledger.jsonl, 1631 calls)
- Observed generation throughput (output+reasoning tok/s): median **55**, p10 **35**, slow band for BIG reasoning-first sections ~**12–15**.
- Section budget **64000** tokens (≈4× the largest section observed in the run, ~16000 total) = generous "never truncate" headroom.
- `PG_GENERATOR_LLM_TIMEOUT_SECONDS = 6500` = 1.5 × (64000 / 15 tok/s) ≈ 6400 → 6500s inner LLM timeout.
- `PG_SECTION_WALLCLOCK_SECONDS = 9000` = outer per-attempt section backstop (LLM 6500 + verify/rewrite headroom). With A1, a wall-clock fire degrades to a gap-stub, not a crash.

## Live provider-cap check (per §9.1.8 "read the API, don't guess", 2026-06-14)
`GET /api/v1/models/deepseek/deepseek-v4-pro/endpoints`: the I-arch-003 generator chain `[wandb, siliconflow, baidu, novita, streamlake, gmicloud, deepseek]` all serve `max_completion_tokens >= 384000` (wandb/parasail 1048576; siliconflow/baidu/novita 393216; streamlake/deepseek 384000). **DeepInfra (16384) is EXCLUDED** from the chain. So 64000 is safe on every pinned provider — the stale 16384 comment at `run_honest_sweep_r3.py:6123-6131` predates that exclusion.

## What the diff does
1. **Slate (`run_gate_b.py`):** adds the 3 keys as FLOORS (max(existing, slate)) so a smoke value (600) is RAISED to 9000, and an operator may raise but not lower.
2. **Fail-loud preflight:** adds the 3 to `_BENCHMARK_EXTRA_ENV_FLOORS` → `preflight_full_capability()` raises RuntimeError if any resolves below the floor (so a smoke `PG_SECTION_WALLCLOCK_SECONDS=600` can NEVER reach a paid run).
3. **Import-time floor:** adds `("...openrouter_client", "GENERATOR_TIMEOUT_SECONDS", 6500)` to `_BENCHMARK_IMPORT_TIME_CONSTANT_FLOORS` — because that constant is read at import (before the slate runs), a stale `.env` value can't be fixed by the slate env; preflight fails loud on it. Module default is now 6500, so an UNSET `.env` passes.
4. **Runner default:** `run_honest_sweep_r3.py:6132` `16384 → 64000` (+ corrected stale comment).
5. **Module default:** `openrouter_client.py:801` `1800 → 6500` (+ corrected stale comment).

## Faithfulness / safety
- These are TIMEOUT + max_tokens CAPS only — no faithfulness gate is touched. max_tokens is billed by actual usage, so a generous cap is free.
- FLOOR semantics = no silent downgrade (operator no-downgrade directive); a HIGHER operator value is kept.

## Adjacent-file scan (checked and clean)
- `PG_SECTION_WALLCLOCK_SECONDS` read at CALL time (`multi_section_generator.py:_section_wallclock_seconds`), `PG_SECTION_MAX_TOKENS` read at CALL time (`run_honest_sweep_r3.py:6132`) → slate env applies. `GENERATOR_TIMEOUT_SECONDS` read at IMPORT → handled via the import-const floor + safe module default.
- `PG_LLM_TIMEOUT_SECONDS=180` in the slate is the GENERIC (non-generator) timeout — left as-is (the reason()/generate_structured generic-timeout shadow is a separate B-tier finding, not A2).
- No existing test asserts the old 1800 default (meta008 references the symbol, not the literal); `test_generator_writer_timeout_meta008.py` 3/3 pass.

## Tests (offline, passing)
`tests/dr_benchmark/test_section_timeout_token_sizing_iarch004.py` — 6 tests: slate floors all three; the SMOKE 600 is raised to ≥9000; a HIGHER operator value (20000) is kept; preflight FAILS CLOSED on `PG_SECTION_WALLCLOCK_SECONDS=600` AND on `PG_SECTION_MAX_TOKENS=16384`; the generator-timeout import-const floor is wired. Regression: existing slate tests (evidence-cap, readiness-flags) 14/14 + meta008 3/3 pass.

## Output — required schema (last `verdict:` line is CI-parsed)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
Red-team specifically: (a) is the 64000 budget genuinely safe on EVERY provider in the live generator chain (any None/low cap I missed)? (b) does the FLOOR semantics ever wrongly KEEP a too-low value (e.g. a non-numeric env)? (c) is 9000s wall-clock actually ≥ a realistic worst-case section (64000 tok + strict_verify + rewrite + 1 regen)? (d) any OTHER call site that reads these three knobs and would now behave differently?
