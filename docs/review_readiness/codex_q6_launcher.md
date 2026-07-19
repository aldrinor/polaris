# Q6 launcher consolidation — codex review record

**Phase 2 (per codex):** consolidate `run_full_scale_v10..v30_phase2` into one
parameterized launcher plus behavior-preserving call-through shims.

Branch: `chore/review-readiness-launcher` · PR base: `gate-inversion`.

## What changed
- **New single source of truth:** `scripts/run_full_scale.py`. It holds
  `VARIANT_ENV` (one dict per variant), per-variant `_DEFAULT_OUT_ROOT`,
  `_LOG_PREFIX`, `_BANNER_LABEL`, and the shared `_DEFAULT_ONLY` slug, plus
  `run(variant, argv)` / `main()`.
- **Nine shims** (`run_full_scale_v10/23/24/25/26/27/28/29/30_phase2.py`) are now
  thin call-throughs: `from run_full_scale import run; run("<variant>", sys.argv[1:])`.
  Filenames are preserved so path-based references keep resolving.

## Behavior-preservation contract
`run(variant, argv)` reproduces the pre-consolidation script byte-for-byte:
- `VARIANT_ENV[variant]` equals the original `_VNN_ENV` dict exactly (keys + values).
- Env precedence preserved: a value already set in the parent shell / `.env`
  is never clobbered (the historical `override=False` semantics).
- `--only` and `--out-root` are injected **only when absent**; caller-supplied
  args are forwarded verbatim.
- `sys.argv[0]` (the invoking shim path) is preserved.

### Variant knob history (as encoded in `VARIANT_ENV`)
- `v10/v23/v24/v25` — the shared 13-key base profile.
- `v26` — base + `PG_M41D_HC_QUOTA=2`.
- `v27` — v26 + `PG_SWEEP_MAX_REGULATORY_ANCHORS=12`.
- `v28/v29` — `PG_LIVE_MAX_EV_TO_GEN` 600→300 + `PG_SWEEP_MAX_PRIMARY_TRIAL_ANCHORS=15`.
- `v30_phase2` — v29 knobs + `PG_V30_ENABLED=1`, `PG_V30_PHASE2_ENABLED=1`.

## Known dynamic reference (must not break)
`src/polaris_graph/audit_ir/honest_sweep_job_runner.py` launches
`scripts/run_full_scale_v30_phase2.py` **by path** as a subprocess, and
`tests/polaris_graph/test_honest_sweep_job_runner.py` asserts the sweep script's
filename is exactly `run_full_scale_v30_phase2.py`. The v30_phase2 shim keeps the
filename and stays byte-runnable / path-loadable.

## Verification (all green)
1. **collection_ok** — the consolidated module and all nine shims import cleanly
   and each exposes `main()`; `py_compile` passes on all ten files.
2. **oracle_matches** — an AST-level oracle parses each original committed
   `_VNN_ENV` dict from `HEAD` and compares it to `VARIANT_ENV[variant]`, plus the
   `--out-root` and `--only` defaults. All nine variants match exactly:
   `env=True out_root=True only=True` for every variant.
3. **dynamic_refs_intact** — `test_make_default_honest_sweep_job_runner_resolves_canonical_paths`
   passes (filename assertion + job-runner path resolution). Env-precedence
   (`override=False`) and argv-injection (defaults only when absent) behave as the
   historical scripts did.

## Codex verdict
LAUNCHER-SAFE — consolidation is behavior-preserving; the nine shims reproduce
each historical launcher byte-for-byte, the v30_phase2 dynamic reference is
intact, and the oracle confirms env/out-root/only parity across all variants.
