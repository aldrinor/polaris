# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

---

## 1. PR scope

- PR title: I-ready-018 (#1100 keystone): generate_structured 404 on reasoning-first deepseek
- Branch: bot/I-ready-018-structured-404 (base bot/I-ready-consolidated)
- Issue: I-ready-018 (#1100)
- Files touched: 1 runtime (`src/polaris_graph/llm/openrouter_client.py`, one-line gate + comment) + 1 new test + 1 smoke script.

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256: `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator, mirror, sentinel, judge (4-role)
- Roles touched by this PR: NONE. This changes the `generate_structured` skip-response_format gate from `_ALWAYS_REASON_MODELS` (GLM-only) to `_REASONING_FIRST_MODELS` (adds the reasoning-first deepseek default). It adds no role, transport, family, model, or LLM call; it only stops attaching a strict json_schema `response_format` for reasoning-first models (which 404'd).

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock.
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. (No new env var.)
- [x] This PR does NOT add a new LLM call path that lacks role tagging. (No new call path; same `generate_structured`, only the response_format attachment changes.)
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed — `_REASONING_FIRST_MODELS` already contained deepseek-v4-pro/-flash; this PR only references that existing set from the gate.)
- [x] If this PR touches `openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `verify_lock --consistency` = OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check still raises when lock status is `codex_approved_pending_operator_signature`. (Not touched.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (Unaffected.)

## 4. Codex review trail

- Diagnosis posted: #1100 comment (forensic root cause, re-verified against source).
- Codex APPROVE on diff: `.codex/I-ready-018/codex_diff_audit.txt` (evidence-based review — diagnosis correctness + narrowness/regression + recovery soundness + faithfulness).
- Diff artifact: `.codex/I-ready-018/codex_diff.patch`.

## 5. Tests

- New: `tests/polaris_graph/test_generate_structured_reasoning_first_404_iready018.py` (4 passed) — reasoning-first skips strict schema; non-reasoning-first still gets it (narrow); reasoning_enabled=True skips for any model.
- Live smoke: `.codex/I-ready-018/live_smoke.py` → KEYSTONE_SMOKE_OK (Part A reproduces the 404 on the old body with the generator's exact provider pin; Part B parses the real AgenticRoundAnalysis + StormPersonaBatch on deepseek-v4-pro).
- Regression: `test_reasoning_first_normalize.py` + `test_deepseek_v4_pricing.py` + the new test = 13 passed. `verify_lock --consistency` = OK.

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
  codex_brief_approve_path: ".codex/I-ready-018/codex_diff_audit.txt"
  codex_diff_approve_path: ".codex/I-ready-018/codex_diff_audit.txt"
  tests_pass_count: 13
  tests_total_count: 13
  operator_signoff_required: false
  operator_signoff_commit: ""
```
