# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

---

## 1. PR scope

- PR title: I-ready-016b (#1097): activate the 3 readiness faithfulness flags in the Gate-B slate (force-on) + fail-closed preflight
- Branch: bot/I-ready-consolidated (the consolidated run branch: CORE base + the 7 INDEP readiness fixes + this activation)
- Issue: I-ready-016b (#1097)
- Files touched (count): 1 runtime (`scripts/dr_benchmark/run_gate_b.py`) + 5 tests.

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256: `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator, mirror, sentinel, judge (4-role)
- Roles touched by this PR: NONE. This activates three env feature-flags in the benchmark slate + extends the fail-closed preflight; it adds no role, transport, family, model, or LLM call.

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock.
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. (It force-ONs three EXISTING feature flags — `PG_USE_SAFETY_REFUSAL`, `PG_SWEEP_NLI_CONFLICT`, `PG_SWEEP_TABLE_CELL_VERIFY` — that shipped with their consuming code in #1072/#1079/#1084; not role/model routing.)
- [x] This PR does NOT add a new LLM call path that lacks role tagging. (The activated layers are an input classifier, an evaluator-family NLI judge already family-segregated, and a pure-Python table-cell numeric check.)
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed.)
- [x] If this PR touches `src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `verify_lock --consistency` = OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check still raises when lock status is `codex_approved_pending_operator_signature`. (Not touched — this is the Gate-B `preflight_full_capability`, a different, additive fail-closed guard that only STRENGTHENS the no-silent-downgrade contract.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (Unaffected.)

## 4. Codex review trail

- Brief: `.codex/I-ready-016b/brief.md`
- Codex APPROVE on brief: `.codex/I-ready-016b/codex_brief_verdict.txt` (iter-2 APPROVE; iter-1 caught the `float('local')` crash → PG_DOC_INGEST_BACKEND left out of the slate)
- Codex APPROVE on diff: `.codex/I-ready-016b/codex_diff_audit.txt` (APPROVE, 0 P0/P1; the one P2 — preflight test fixtures — folded in)

## 5. Tests

- New test added: `tests/dr_benchmark/test_slate_readiness_flags_iready016b.py` (force-on overrides preset-0 via fake-transport env-capture; preflight bites when a flag is forced off).
- Diff-gate P2 fix: 4 existing preflight test fixtures updated to set the 3 newly-required flags (`test_evidence_to_generation_cap`, `test_capped_finding_dedup`, `test_verified_only_surface`, `test_benchmark_stack_activation`) — caught by running the FULL dr_benchmark suite, not just the changed file.
- Existing tests verified green: `python -m pytest tests/dr_benchmark/ -q` → 290 passed; `verify_lock --consistency` = OK.
- Test result count: 290 passed (full dr_benchmark suite, incl. the new + the 4 fixed fixtures).

## 6. Operator sign-off

- Required: no (does NOT mutate the lock YAML, family registry, or canonical pin).
- Operator commit reference (if required): N/A

---

## Machine-parseable footer (CI parses this)

```yaml
schema_version: 1
pr_attestation:
  lock_sha256: "1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99"
  lock_status_at_pr: "codex_approved_pending_operator_signature"
  roles_unchanged: true
  envvars_unchanged: true
  role_tagging_preserved: true
  model_slugs_lock_synced: true
  family_registry_validates: true
  preflight_freeze_intact: true
  smoke_cannot_pass_stub: true
  codex_brief_approve_path: ".codex/I-ready-016b/codex_brief_verdict.txt"
  codex_diff_approve_path: ".codex/I-ready-016b/codex_diff_audit.txt"
  tests_pass_count: 290
  tests_total_count: 290
  operator_signoff_required: false
  operator_signoff_commit: ""
```
