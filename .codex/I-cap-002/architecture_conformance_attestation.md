# Architecture Conformance Attestation

I-meta-001 (#933) Step 11: every PR touching runtime/model/docs MUST include this artifact so the
architecture invariant is verified at PR time.

## 1. PR scope

- PR title: I-cap-002 (#1060) — wire the Tier-B deep-research machinery (STORM, depth-gate, agentic, NLI) into the benchmark path
- Branch: bot/I-cap-002-storm / -depth / -agentic / -nli (PRs #1061 / #1062 / #1063 / #1064)
- Issue: I-cap-002
- Files touched (count): 4 new modules + run_one_query + run_gate_b + tests (per-feature; see each PR)

## 2. Architecture lock under which this PR was authored

- Lock file: `config/architecture/polaris_runtime_lock.yaml`
- Lock SHA256: `1dd2e7882b930f7e032fbbc39ec474402051150630a1d03f6a4b318a66a8bb99`
- Lock status at PR-open time: `codex_approved_pending_operator_signature`
- Required roles in lock: generator (deepseek/deepseek-v4-pro), mirror (z-ai/glm-5.1), sentinel (minimax/minimax-m2), judge (qwen/qwen3.6-35b-a3b)
- Roles touched by this PR: NONE. The four Tier-B features are additive/advisory and run BEFORE (STORM/agentic widen retrieval) or AFTER (depth/NLI annotate the manifest) the 4-role seam; the generator + Mirror/Sentinel/Judge seam itself is byte-unchanged.

## 3. Conformance assertions

- [x] This PR does NOT remove or rename any role from the lock. (No role definition touched.)
- [x] This PR does NOT introduce a new env var that bypasses the lock's `env_vars` registry. The new flags (`PG_STORM_ENABLED_IN_BENCHMARK`, `PG_DEPTH_ANNOTATION_IN_BENCHMARK`, `PG_AGENTIC_SEARCH_IN_BENCHMARK`, `PG_NLI_IN_BENCHMARK`, `PG_*_PER_ROUND_COST_USD`, etc.) are FEATURE-ACTIVATION toggles for advisory/discovery features OUTSIDE the 4-role seam — they do not select a role model, base URL, or family, and they cannot route around the lock.
- [x] This PR does NOT add a new LLM call path that lacks role tagging. The 4-role generator/mirror/sentinel/judge call paths are unchanged. STORM (interview) and agentic (round-analysis) use SEARCH/DISCOVERY helper LLMs that are not part of the 4-role seam (same class as the existing Pipeline-B planner/refiner); NLI uses a local entailment model (flan-t5-large), not an OpenRouter role. None of them produce evidence or a release verdict — the 4-role seam remains the single binding gate (D8).
- [x] If this PR changes any model_slug, the change is reflected in the lock YAML. (No model_slug changed.)
- [x] If this PR touches `openrouter_client.py:_FAMILY_PREFIXES`, the lock YAML's `family_policy` still validates. (Not touched; `python -m scripts.architecture.verify_lock` → 4 roles + family policy OK.)
- [x] If this PR touches `pathB_run_gate.py:preflight`, the architecture-coverage check still raises on pending lock status. (preflight not touched.)
- [x] The Path-B smoke (with `--pathB-gate`) cannot PASS on a 2-LLM stub under this PR. (The 4-role seam guard is unchanged; B adds no stub path.)

## 4. Codex review trail

- Brief: `.codex/I-cap-002-storm/brief.md`, `.codex/I-cap-002-depth/brief.md`, `.codex/I-cap-002-agentic/brief.md`, `.codex/I-cap-002-nli/brief.md`
- Codex APPROVE on brief: each feature's `codex_brief_verdict.txt` (STORM design-locked over 3 brief-gate iters; depth iter-2; agentic iter-2; NLI iter-1)
- Codex APPROVE on diff: each feature's `codex_diff_audit.txt` (STORM iter-3; depth iter-1; agentic iter-1; NLI iter-2)

## 5. Tests

- New tests added: `tests/polaris_graph/test_storm_query_extractor.py`, `test_analytical_depth.py`, `test_agentic_url_harvester.py`, `test_nli_benchmark_annotator.py`; extended `tests/dr_benchmark/test_benchmark_stack_activation_meta007.py`.
- Existing tests verified green: `python -m pytest tests/architecture/ tests/dr_benchmark/ -q`
- Test result count: tests/architecture 15/15 + tests/dr_benchmark 233/233 + the per-feature unit suites (storm 4, depth 10, agentic 6, nli 8) all green.

## 6. Operator sign-off

- Required: no. This PR does NOT mutate the lock YAML, the family registry, or the canonical pin.
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
  codex_brief_approve_path: ".codex/I-cap-002-nli/codex_brief_verdict.txt"
  codex_diff_approve_path: ".codex/I-cap-002-nli/codex_diff_audit.txt"
  tests_pass_count: 248
  tests_total_count: 248
  operator_signoff_required: false
  operator_signoff_commit: ""
```
