# Codex diff review — I-ready-005 (#1076) per-feature firing telemetry — ITER 5 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What #1076 ships

Per-feature *firing* telemetry for the benchmark-forced features (STORM query-expansion + agentic
search). The operator's no-silent-downgrade directive requires PROVING each forced-ON feature
actually fired, not merely that its flag was set. `make_feature_telemetry(...)` builds a
`{feature, enabled, fired, status, ...}` dict; `_attach_tool_utilization` (the single hook before
EVERY `manifest.json` write) stamps the per-feature telemetry from a ContextVar onto every manifest
(success AND abort/budget/error). `feature_firing_warning(...)` emits the no-silent-degrade warning
when a feature was forced ON but did NOT fire.

## iter-4 verdict was REQUEST_CHANGES (0 P0, 2 P1). Both addressed:

**P1-1** — the iter-3 fix had split `run_one_query` into a thin wrapper +
`_run_one_query_impl` (body), to get a guaranteed ContextVar clear via the wrapper's `finally`.
That broke ~20 source-introspection contract gates across 12 test files that inspect
`run_one_query` via `inspect.getsource(sweep.run_one_query)` or AST `name == "run_one_query"`.

Fix (your iter-4 FIRST-listed option): **reverted the wrapper — the orchestrator body is
`run_one_query` again** (zero edits to any introspection gate). The guaranteed single ContextVar
clear is now a `finally` on the **existing outer orchestration try** (the try whose excepts write
`error_unexpected` / `abort_budget_exceeded`).

Structural proof the `finally` is correct and complete (verified against the source):
- All 8 early abort-returns (scope / no_sources / corpus×2 / no_verified / abort_verifier_degraded
  / 2× cancel) return from INSIDE that try.
- The SUCCESS manifest is written INSIDE that try (before the excepts).
- The budget/error excepts write their manifests first; the `finally` runs after.
- The post-try teardown (ledger copy + terminal event + `return summary`) writes NO manifest.
- ⇒ the `finally` runs after the last manifest write on EVERY exit, never strips telemetry off a
  manifest, and no stale "feature fired" entry can leak into a later `_attach_tool_utilization`
  call sharing the async context.

**P1-2** — byte-identical OFF was broken (ContextVar set unconditionally). Fix: the publish is now
gated — `if _storm_enabled or _agentic_enabled:` — and is the FIRST statement inside the outer try.
Both features OFF ⇒ the ContextVar is never set ⇒ `_attach_tool_utilization` adds no feature keys ⇒
manifest byte-identical to the pre-#1076 OFF path. The `finally` still runs `set(None)` (no-op when
already None).

My new test was rewritten from a wrapper monkeypatch to an AST-structural check that locates the
outer error try (its segment contains `error_unexpected` + `BudgetExceededError`) and asserts its
`finally` clears `_FEATURE_TELEMETRY_CTX`.

## Evidence (offline, this host)
- `test_feature_firing_telemetry_iready005.py` — 8/8 pass.
- The ~20 introspection gates (the P1-1 victims) — 100/100 pass (test_b2, test_m201/202/203/205/206,
  test_scope_gate, test_research_planner_phase1, test_four_role_budget_cap).
- run_one_query monkeypatch consumers — 73 pass (gate-b CLI/seam, benchmark-stack-activation,
  quantified-telemetry, cancellation, runs-db-integration, graph_v4). The only 2 failures are
  `test_actors_upload_error_path` raising `OSError: Unable to run gpg` (gpg binary absent on this
  Windows host; environmental, unrelated to this diff).
- Diff: 243 insertions, 2 files, under the 200-LOC *change* cap (net source change in
  run_honest_sweep_r3.py is small; the bulk is the new test file).

## DO NOT re-flag these — 6 PRE-EXISTING red gates, NOT this diff's regressions

The full suite shows 6 red `test_manifest_contract` / `test_b3` gates. I classified each against the
merge-base (`8fac4dbd`) and #1074-tip (`27701048`, the commit BEFORE any #1076 work) with AST probes.
ALL 6 were already red before #1076; this diff does not touch them:

- `test_manifest_contract_exception_writes_error_manifest` — red at base. `next(first Try)` returns
  the early `except Exception: pass` synthesis-reset try, not the outer error try.
- `test_manifest_contract_abort_statuses_are_authoritative` — red at base (`cancelled`,
  `abort_quota_exceeded`); the file-wide `"status":"x"` regex catches non-manifest dicts.
- `test_manifest_contract_unified_taxonomy_defined` — red at #1074-tip; `abort_verifier_degraded`
  added to `UNIFIED_STATUS_VALUES` by #1071 but not to the test's `expected` set.
- `test_manifest_contract_all_manifest_writes_have_status` — red at #1074-tip; the NLI manifest
  re-write window (#1071) lacks a nearby `"status"` literal.
- `test_b3_orchestrator_uses_extracted_helpers` / `test_b3_manifest_records_zero_verified` — red at
  #1074-tip; `PG_GENERATOR_MODEL` now appears before `if not verified_sections:`.

These are tracked as a separate URGENT issue (stale source-introspection gates that broke as
`run_one_query` grew; earlier scoped-test iters missed them) and will be repaired before the
I-ready stack merges. Please confine your verdict to THIS diff (the telemetry + the finally clear).

## Review scope
Diff: `.codex/I-ready-005/codex_diff.patch` (cumulative #1076: `27701048..HEAD`).
Focus: (1) does the `finally` on the outer try truly clear on every exit incl. the direct
abort-returns and propagating exceptions? (2) is byte-identical OFF actually preserved by the
gated publish? (3) is the firing telemetry honest (fired reflects real firing, not flag state)?

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
