# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

---

## 1. PR scope

- PR title: I-ready-015 (#1084): table-cell faithfulness gate (+ dead-SVG hygiene)
- Branch: bot/I-ready-015-table-cell-verify (off bot/I-ready-013-analyst-synthesis-verified)
- Issue: I-ready-015 (#1084)
- Files touched (count): 2 runtime (`src/polaris_graph/generator/multi_section_generator.py`, `src/tools/visual_generator.py` docstring-only) + 1 test + `.codex`/`outputs` artifacts.

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256: `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator, mirror, sentinel, judge (4-role)
- Roles touched by this PR: NONE. This is a deterministic table-cell numeric gate in the report assembler + a docstring-only note on a dead SVG module. No role/transport/family/model/LLM-call change.

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock.
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. (New flag `PG_SWEEP_TABLE_CELL_VERIFY` is a deterministic report-assembly toggle, not role/model routing.)
- [x] This PR does NOT add a new LLM call path that lacks role tagging. (No LLM call added — the gate is a pure-Python `_decimals` subset check on already-generated table text.)
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed.)
- [x] If this PR touches `src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `verify_lock --consistency` = OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check still raises when lock status is `codex_approved_pending_operator_signature`. (Not touched.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (Unaffected.)

## 4. Codex review trail

- Brief: `.codex/I-ready-015/brief.md`
- Codex APPROVE on brief: `.codex/I-ready-015/codex_brief_verdict.txt` (reference_source=option_b_verified_prose, flag_default_off_correct=yes)
- Codex APPROVE on diff: `.codex/I-ready-015/codex_diff_audit.txt`

## 5. Tests

- New tests added: `tests/polaris_graph/test_table_cell_verify_iready015.py` (7 tests: flag-OFF byte-identical, 2-arg caller inert, flag-ON drops fabricated number, keeps all-in-prose, no-decimal row unaffected, citation-marker stripped, strict_verify._decimals source-pin).
- Existing tests verified green: `python -m pytest tests/polaris_graph/test_m36_trial_summary_table.py tests/polaris_graph/test_m41_v24_regression_fixes.py -q` (59) + `verify_lock --consistency` = OK.
- Test result count: 7 (feature) + 59 (regression) = 67 passed.

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
  codex_brief_approve_path: ".codex/I-ready-015/codex_brief_verdict.txt"
  codex_diff_approve_path: ".codex/I-ready-015/codex_diff_audit.txt"
  tests_pass_count: 67
  tests_total_count: 67
  operator_signoff_required: false
  operator_signoff_commit: ""
```
