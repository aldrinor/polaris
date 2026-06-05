# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

---

## 1. PR scope

- PR title: I-ready-010 (#1073): wire uploaded-document grounding into the Gate-B benchmark path
- Branch: bot/I-ready-010-doc-upload-wiring (off bot/I-ready-013-analyst-synthesis-verified)
- Issue: I-ready-010 (#1073)
- Files touched (count): 2 runtime/test (`scripts/dr_benchmark/run_gate_b.py`, `tests/dr_benchmark/test_benchmark_upload_wiring_iready010.py`) + 6 artifacts under `.codex/I-ready-010/` and `outputs/audits/I-ready-010/`.

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256 (compute: `sha256sum config/architecture/polaris_runtime_lock.yaml`): `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator, mirror, sentinel, judge (4-role)
- Roles touched by this PR: NONE. This PR is a benchmark-CLI producer-side change only (`run_gate_b.py` `main` adds `--upload-file`/`--upload-classification` + a resolver that populates `q["uploaded_documents"]`). It does not touch any role, transport, family registry, model slug, or LLM call path.

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock.
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. (Two CLI flags added — `--upload-file`, `--upload-classification` — no new env var.)
- [x] This PR does NOT add a new LLM call path that lacks role tagging (per `_PATHB_ROLE` ContextVar). (No LLM call added; uploaded rows flow through the existing `build_upload_evidence_rows` → strict_verify → 4-role path.)
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed — vacuously satisfied.)
- [x] If this PR touches `src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `verify_lock --consistency` = OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check at preflight still raises when lock status is `codex_approved_pending_operator_signature`. (Not touched.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (Unaffected — no change to the 4-role seam or preflight.)

## 4. Codex review trail

- Brief: `.codex/I-ready-010/brief.md`
- Codex APPROVE on brief: `.codex/I-ready-010/codex_brief_verdict.txt` (iter-1, `scope_decision=part1_only_correct`)
- Codex APPROVE on diff: `.codex/I-ready-010/codex_diff_audit.txt` (iter-2, 0 P0/P1/P2, accept_remaining)

## 5. Tests

- New tests added: `tests/dr_benchmark/test_benchmark_upload_wiring_iready010.py` (14 tests: resolver→ev_upload_* row; sovereignty block; empty/missing/unsupported fail-loud; CLI copy + registry isolation; flag-OFF byte-identical; lazy-import pin).
- Existing tests verified green: `python -m pytest tests/architecture/ tests/dr_benchmark/ -q`
- Test result count: 301 passed (architecture + dr_benchmark suites); `verify_lock --consistency` = OK (exit 0).

## 6. Operator sign-off

- Required: no (this PR does NOT mutate the lock YAML, family registry, or canonical pin).
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
  codex_brief_approve_path: ".codex/I-ready-010/codex_brief_verdict.txt"
  codex_diff_approve_path: ".codex/I-ready-010/codex_diff_audit.txt"
  tests_pass_count: 301
  tests_total_count: 301
  operator_signoff_required: false
  operator_signoff_commit: ""
```
