# I-hygiene-001 reference sweep

Scanned 1236 text files. Total hit count: 58.
For each archive candidate, scan across .github/, docs/, scripts/, src/, tests/ for references. Hits below need post-move patching.

## `.coverage` — 9 hit(s)
- `scripts/benchmark_proof_package.py`
- `scripts/inventory_root_hygiene.py`
- `scripts/static/inspector/inspector.js`
- `src/orchestration/iteration_manager.py`
- `src/orchestration/stopping_mechanism.py`
- `src/polaris_v6/charts/from_bundle.py`
- `tests/polaris_graph/test_inspector_browser.py`
- `tests/v6/benchmark/test_coverage_scorer.py`
- `tests/polaris_graph/benchmark/test_external_loader.py`

## `.pytest-cache` — 1 hit(s)
- `scripts/inventory_root_hygiene.py`

## `.pytest_cache` — 3 hit(s)
- `docs/file_directory.md`
- `scripts/full_cycle.py`
- `scripts/inventory_root_hygiene.py`

## `.pytest_tmp` — 2 hit(s)
- `scripts/inventory_root_hygiene.py`
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `.ruff_cache` — 1 hit(s)
- `scripts/inventory_root_hygiene.py`

## `.tmp` — 16 hit(s)
- `scripts/inventory_root_hygiene.py`
- `scripts/loopback_auto_analyze.py`
- `scripts/loopback_auto_grade.py`
- `scripts/loopback_auto_pagesummary.py`
- `scripts/loopback_auto_storm.py`
- `scripts/loopback_auto_universal.py`
- `scripts/loopback_auto_verify.py`
- `scripts/loopback_dispatcher.py`
- `scripts/pg_faithfulness_validation.py`
- `scripts/pg_preflight.py`
- `scripts/cleanup/delete_pytest_tmpdirs.sh`
- `src/polaris_graph/graph_v4.py`
- `src/polaris_graph/nodes/corpus_approval_gate.py`
- `src/polaris_graph/nodes/scope_gate.py`
- `src/polaris_graph/wiki/mesh/ingest.py`
- `tests/polaris_graph/test_b102_graph_v4.py`

## `.tmp-pytest` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `.tmp_pytest` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `.tmp_pytest_base` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `POLARIS.tmppytest` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `POLARIStmp_pytest_m_int_3_reviewbasetemp` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `__pycache__` — 5 hit(s)
- `.github/workflows/legacy_protection.yml`
- `scripts/audit_live_code.py`
- `scripts/full_cycle.py`
- `scripts/inventory_root_hygiene.py`
- `scripts/produce_env_var_inventory.py`

## `codex_tmp_pytest` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `tmp_pytest_m_int_3` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `tmp_pytest_m_int_3_review` — 1 hit(s)
- `scripts/cleanup/delete_pytest_tmpdirs.sh`

## `.codex/REVIEW_BRIEF.md` — 1 hit(s)
- `docs/file_directory.md`

## `.codex/ROUND_N_BRIEF_TEMPLATE.md` — 1 hit(s)
- `docs/file_directory.md`

## `.codex/continuous` — 3 hit(s)
- `.github/workflows/web_ci.yml`
- `scripts/cleanup/count_hits.sh`
- `scripts/cleanup/zero_hit_gate.sh`

## `.codex/loop_state.json` — 2 hit(s)
- `docs/file_directory.md`
- `docs/pipeline_audit_context/04_sample_run_artifacts.md`

## `.codex/pr_d_mechanical_gates_review_brief.md` — 1 hit(s)
- `.github/workflows/codex-required.yml`

## `.codex/round_3` — 1 hit(s)
- `scripts/codex_loop_parse.py`

## `.codex/task_briefs` — 1 hit(s)
- `docs/task_acceptance_matrix.yaml`

## `.codex/v28_deep_content_audit_brief.md` — 1 hit(s)
- `scripts/v28_post_manifest_pipeline.sh`

## `.codex/walkthrough_screenshots_latest` — 2 hit(s)
- `scripts/screenshot_benchmark.js`
- `scripts/screenshot_walkthrough.js`
