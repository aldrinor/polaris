# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

## How to use

Copy this template to `.codex/<issue_id>/architecture_conformance_attestation.md`,
fill in every section, and commit it alongside the brief + diff. CI gate
`architecture-conformance-required` parses the YAML block at the bottom and FAILS
the PR if any required field is missing or any required check is false.

---

## 1. PR scope

- PR title:
- Branch:
- Issue: I-...
- Files touched (count):

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256 (compute: `sha256sum config/architecture/polaris_runtime_lock.yaml`):
- Lock status at PR-open time:
- Required roles in lock:
- Roles touched by this PR:

## 3. Conformance assertions

- [ ] This PR does NOT remove or rename any role from the lock.
- [ ] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry.
- [ ] This PR does NOT add a new LLM call path that lacks role tagging (per `_PATHB_ROLE` ContextVar).
- [ ] If this PR changes any model_slug, the change is reflected in the lock YAML.
- [ ] If this PR touches `src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates (run `python -m scripts.architecture.verify_lock`).
- [ ] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check at preflight still raises when lock status is `codex_approved_pending_operator_signature`.
- [ ] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR.

## 4. Codex review trail

- Brief: `.codex/<issue_id>/brief.md`
- Codex APPROVE on brief: `.codex/<issue_id>/codex_brief_verdict.txt`
- Codex APPROVE on diff: `.codex/<issue_id>/codex_diff_audit.txt`

## 5. Tests

- New tests added: (path/file/test_name)
- Existing tests verified green: `python -m pytest tests/architecture/ tests/dr_benchmark/ -q`
- Test result count:

## 6. Operator sign-off

- Required: yes/no (yes if PR mutates the lock YAML, family registry, or canonical pin)
- Operator commit reference (if required):

---

## Machine-parseable footer (CI parses this)

```yaml
schema_version: 1
pr_attestation:
  lock_sha256: ""
  lock_status_at_pr: ""
  roles_unchanged: false
  envvars_unchanged: false
  role_tagging_preserved: false
  model_slugs_lock_synced: false
  family_registry_validates: false
  preflight_freeze_intact: false
  smoke_cannot_pass_stub: false
  codex_brief_approve_path: ""
  codex_diff_approve_path: ""
  tests_pass_count: 0
  tests_total_count: 0
  operator_signoff_required: false
  operator_signoff_commit: ""
```
