# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact
(or an exemption justification) so the architecture invariant is verified at PR time.

---

## 1. PR scope

- PR title: I-ready-012 (#1079): semantic/NLI cross-document contradiction layer (3rd detector)
- Branch: bot/I-ready-012-semantic-conflict-nli (off bot/I-ready-013-analyst-synthesis-verified)
- Issue: I-ready-012 (#1079)
- Files touched (count): 2 runtime (`src/polaris_graph/retrieval/semantic_conflict_detector.py` NEW, `scripts/run_honest_sweep_r3.py`) + 1 test + 6 `.codex`/`outputs` artifacts.

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256: `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator, mirror, sentinel, judge (4-role)
- Roles touched by this PR: NONE. The new semantic-conflict detector reuses the existing two-family evaluator substrate (`PG_ENTAILMENT_MODEL`, the same model class as the strict_verify entailment judge) via its OWN isolated `_SemanticContradictionJudge`; it does not add, rename, or re-route any of the 4 roles, nor touch the 4-role transport.

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock.
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. (New flags `PG_SWEEP_NLI_CONFLICT` + `PG_SWEEP_NLI_CONFLICT_*` knobs are detector toggles/thresholds, not role/model routing; `PG_ENTAILMENT_MODEL` is the EXISTING evaluator model var, reused unchanged.)
- [x] This PR does NOT add a new LLM call path that lacks role tagging. The semantic judge posts the evaluator-family model and explicitly forces `get_role_provider("evaluator")` provider routing (mirroring `entailment_judge`), and is family-segregation-checked at construction (`check_family_segregation(evaluator_model=...)`).
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed — vacuously satisfied.)
- [x] If this PR touches `src/polaris_graph/llm/openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `verify_lock --consistency` = OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check still raises when lock status is `codex_approved_pending_operator_signature`. (Not touched.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (Unaffected — the 4-role seam/preflight is untouched.)

## 4. Codex review trail

- Brief: `.codex/I-ready-012/brief.md`
- Codex APPROVE on brief: `.codex/I-ready-012/codex_brief_verdict.txt` (iter-2: routing_approach_ok=yes, pairing_approach_ok=yes, generator_hedging_needed=no)
- Codex APPROVE on diff: `.codex/I-ready-012/codex_diff_audit.txt` (iter-2: 0 P0/P1; 2 P2 deferred to #1092; accept_remaining)

## 5. Tests

- New tests added: `tests/polaris_graph/test_semantic_conflict_detector_iready012.py` (16 tests: recall/precision, flag-OFF inertness, per-pair + BudgetExceededError fail-open, finite-confidence guard, pair cap, REAL PT08 gate pass/fail, REAL audit_ir.loader parse).
- Existing tests verified green: `python -m pytest tests/polaris_graph/test_contradiction_detector.py tests/polaris_graph/test_qualitative_conflict_detector.py -q` (39) + `run_honest_sweep_r3` imports cleanly; `verify_lock --consistency` = OK.
- Test result count: 16 (feature) + 39 (regression) = 55 passed.

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
  codex_brief_approve_path: ".codex/I-ready-012/codex_brief_verdict.txt"
  codex_diff_approve_path: ".codex/I-ready-012/codex_diff_audit.txt"
  tests_pass_count: 55
  tests_total_count: 55
  operator_signoff_required: false
  operator_signoff_commit: ""
```
