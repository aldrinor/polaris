# I-ready-005 (#1076) — Codex iter-4 REQUEST_CHANGES resolution (→ iter-5 candidate)

Date: 2026-06-05. Author: Claude. Gate: diff review (last before the §8.3.1 5-iter force-approve).

## Codex iter-4 verdict (2 P1, 0 P0)

- **P1-1** — the iter-3 `run_one_query` → `_run_one_query_impl` wrapper split broke the
  source-introspection contract gates: ~20 sites across 12 test files inspect
  `run_one_query` via `inspect.getsource(sweep.run_one_query)` or AST `name == "run_one_query"`.
  With the body moved to `_run_one_query_impl`, they saw the thin wrapper and failed.
- **P1-2** — byte-identical OFF was broken: the ContextVar was set unconditionally at the top of
  the body, so `_attach_tool_utilization` stamped `storm_query_expansion` / `agentic_search` keys
  onto manifests even when both features were OFF.

## Fix (Codex iter-4's FIRST-listed option: keep the body in `run_one_query`)

Reverted the wrapper. The orchestrator body is `run_one_query` again (zero edits to the ~20
introspection gates). Guaranteed single ContextVar clear is now a `finally` on the **existing
outer orchestration try** (the one whose excepts write `error_unexpected` /
`abort_budget_exceeded`).

Why a `finally` on that try is correct and complete (verified against the source structure):
- Every early abort-return (`scope` / `no_sources` / `corpus`×2 / `no_verified` /
  `abort_verifier_degraded` / 2× cancel) returns from **inside** that try.
- The **success** manifest is written **inside** that try (before the excepts).
- The budget/error excepts write their manifests, then the `finally` runs.
- The post-try teardown (ledger copy + terminal event + `return summary`) writes **no** manifest,
  so clearing in the `finally` can never strip telemetry off a manifest.
- Net: the `finally` runs after the last manifest write on **every** exit, and a stale "feature
  fired" entry can never leak into a later `_attach_tool_utilization` call in the same async
  context.

P1-2: the ContextVar publish is now gated — `if _storm_enabled or _agentic_enabled:` — and placed
as the **first statement inside the outer try**. Both OFF ⇒ never set ⇒ `_attach` adds no keys ⇒
byte-identical OFF. The `finally` still runs `set(None)` (a no-op when already None).

My new test was rewritten from the wrapper-based monkeypatch to an AST-structural check that
locates the outer orchestration try (the one whose segment contains `error_unexpected` +
`BudgetExceededError`) and asserts its `finally` clears `_FEATURE_TELEMETRY_CTX` — mirroring how
`test_manifest_contract` / `test_four_role_budget_cap` verify `run_one_query`'s try structure.

## Evidence

- `test_feature_firing_telemetry_iready005.py` — **8/8 pass**.
- The ~20 introspection gates (the P1-1 victims) — **100/100 pass**:
  test_b2, test_m201/m202/m203/m205/m206, test_scope_gate, test_research_planner_phase1,
  test_four_role_budget_cap.
- run_one_query monkeypatch consumers — **73 pass** (gate-b CLI/seam, benchmark-stack-activation,
  quantified-telemetry, cancellation, runs-db-integration, graph_v4). The only 2 failures in that
  sweep are `test_actors_upload_error_path` failing on `OSError: Unable to run gpg` — the gpg
  binary is absent on this Windows host; environmental, unrelated to this diff (green in CI/Linux).
- Diff size ~122 LOC (under the 200-LOC cap).

## IMPORTANT — 6 PRE-EXISTING red contract gates are NOT this diff's regressions

While verifying, the full suite surfaced 6 red `test_manifest_contract` / `test_b3` gates. I
classified each against the merge-base (`8fac4dbd`) and the #1074-tip (`27701048`, the commit
**before** any #1076 work) via AST probes:

| Test | Red at base / #1074-tip? | Root cause | Owner |
|---|---|---|---|
| `test_manifest_contract_exception_writes_error_manifest` | **red at base** | `next(first Try)` returns the early `except Exception: pass` synthesis-reset try, not the outer error try | pre-existing |
| `test_manifest_contract_abort_statuses_are_authoritative` | **red at base** (`cancelled`, `abort_quota_exceeded`) | file-wide `"status":"x"` regex catches non-manifest dicts | pre-existing (+#1076 adds telemetry `fired`/`not_enabled`) |
| `test_manifest_contract_unified_taxonomy_defined` | **red at #1074-tip** | `abort_verifier_degraded` added to `UNIFIED_STATUS_VALUES` (#1071) but not to the test's `expected` set | #1071 |
| `test_manifest_contract_all_manifest_writes_have_status` | **red at #1074-tip** | NLI manifest re-write window (#1071) lacks a nearby `"status"` literal | #1071 |
| `test_b3_orchestrator_uses_extracted_helpers` | **red at #1074-tip** | `PG_GENERATOR_MODEL` now appears before `if not verified_sections:` | pre-#1076 |
| `test_b3_manifest_records_zero_verified` | **red at #1074-tip** | same anchor (`PG_GENERATOR_MODEL`) ordering | pre-#1076 |

None of these were introduced by #1076. They are stale source-introspection contract gates that
broke as `run_one_query` grew across the I-ready stack and were missed because earlier Codex iters
ran scoped (touched-area) tests, not the full suite (the exact failure mode
`feedback_run_full_test_suite_not_just_new_file` warns about). They are tracked as a separate
URGENT issue and must be repaired before the I-ready stack merges. This diff does not touch them.
