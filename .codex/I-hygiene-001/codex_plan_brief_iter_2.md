HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-hygiene-001 — POLARIS root + .codex/ surgical cleanup plan (iter 2)

## Diff from iter 1

### P1 addressed (continuing P0/P1 must be empty)

- **`.codex/slices/` reclassified KEEP.** Verified via `grep -rn "codex/slices"` against `src/`, `tests/`, `scripts/`: 9 production files reference it (`tests/polaris_graph/golden/test_slice_002_goldens.py` + `test_slice_003_goldens.py` fall back to `.codex/slices/slice_{002,003}/golden_drafts/`; `scripts/run_benchmark.py` cites `.codex/slices/slice_005/architecture_proposal.md`; `src/polaris_graph/{api/benchmark_route.py, api/retrieval_route.py, audit_bundle/bundle_builder.py, audit_bundle/bundle_schema.py, audit_bundle/gpg_signer.py, audit_bundle/manifest_builder.py}` cite `.codex/slices/slice_{002,004,005}/architecture_proposal.md`). Out-of-scope to migrate; staying KEEP.

### P2 addressed

- **P2-1 (stale refs beyond README/file_directory):** plan now updates `docs/pipeline_audit_context/04_sample_run_artifacts.md`, `docs/pipeline_audit_context/06_recent_commits.md`, `docs/task_acceptance_matrix.yaml`, and script comments. Will grep for archived-paths after move and patch references.
- **P2-2 (inventory staleness):** plan now regenerates inventory IMMEDIATELY before execution (after Codex APPROVE of plan, before any `mv`). Both `scripts/inventory_root_hygiene.py` and `scripts/inventory_codex_hygiene.py` are idempotent re-runnable. Final manifest committed.
- **P2-3 (tracked manifest):** plan now produces `state/polaris_restart/i_hygiene_001_cleanup_manifest.md` — tracked file with one row per move: source path, destination path, tracked/untracked status, mtime, size. Codex diff-review reads this.
- **P2-4 (anchored .gitignore patterns):** all new patterns use leading `/` (anchored to repo root), no broad unanchored `tmp*/`. Final list pasted below.
- **P2-5 (permission-denied handling):** execution uses `git mv` for tracked entries, Python `shutil.move` with explicit try/except for untracked. On PermissionError → log to `state/polaris_restart/i_hygiene_001_move_failures.txt`, fail loud, exit non-zero. No silent continue.

### P3 addressed (cosmetic)

- snake_case clause clarified: standard exceptions are `CLAUDE.md`, `README.md`, `Dockerfile`, `.env*`, `.gitignore`, `.dockerignore`, `pytest.ini`, `requirements*.txt`, `docker-compose.yml`, `architecture.md`, `ground_rules.md` (all conventional/required casing per their tooling). No active tracked entry at root violates snake_case-or-conventional-exception.

## Final categorization (post iter-1 corrections)

### Root: 35 KEEP + 146 ARCHIVE (unchanged from iter 1)

### `.codex/`: 172 KEEP + 47 ARCHIVE-confirmed + 184 INSPECT (with Codex's adjudication applied)

**KEEP additions per iter-1:**
- `.codex/config.toml` (active codex config)
- **`.codex/slices/`** (load-bearing per P1 above) ★ NEW

**ARCHIVE additions per iter-1 (your inspect_adjudication block ran):**
- `REVIEW_BRIEF.md`, `ROUND_N_BRIEF_TEMPLATE.md`, `autoloop_v2_protocol_review_brief.md`, `carney_delivery_plan_FINAL_review_brief.md`, `loop_state.json`
- `continuous/`, `deep_dive_round_1..7_*/`, `round_2..round_5/`, `runs/`, `strategic_review_high_quality/`
- `next_issue_pick`, `next_issue_pick_2`, `next_issue_pick_3`, `next_pick_post_cj`, `task_briefs/`
- `m28_*..m63_*` audit briefs + pass variants
- `md3_verdict_brief.md`, `md5_*_verdict_brief.md`
- `phase_c_plan.md`, `phase_d_milestones_*`
- `pr_b*`, `pr_b2_*`, `pr_d*`, `pr_e*` review briefs + iter verdicts
- `shippable_plan_*`, `test_failure_triage_*`, `triage_executed_*`
- `v17_*..v30_*` plan + audit briefs
- `walkthrough_2026_05_04.md`, `walkthrough_screenshots_2026_05_04*/`, `walkthrough_screenshots_latest/`
- `plan_amendment_skip_road_b_reset_verdict_iter_1.txt`

## Execution flow (now-explicit)

1. **Verify clean working tree on `bot/I-hygiene-001-root-folder-cleanup`.** Any untracked deliverable from prior branches (BEAT-BOTH `.codex/I-eval-{005..008}/` etc) is preserved as untracked — not touched by the cleanup.
2. **Re-run inventory:** `python scripts/inventory_root_hygiene.py && python scripts/inventory_codex_hygiene.py` → freshest state under `state/polaris_restart/i_hygiene_001_*_inventory.md`.
3. **Create destination:** `mkdir -p archive/2026-05-11-root-hygiene/{root,codex_historical}`.
4. **Manifest header:** create `state/polaris_restart/i_hygiene_001_cleanup_manifest.md` with table columns: `src_path | dest_path | tracked_status | mtime | size_bytes | move_method`.
5. **Move root ARCHIVE entries:** for each of 146, `git ls-files --error-unmatch "<name>"` to test tracked vs untracked; tracked → `git mv`; untracked → `shutil.move`. Append manifest row. On PermissionError → log + halt.
6. **Move .codex/ ARCHIVE entries:** same protocol.
7. **Reference patching:** `grep -rl "<archived-path>" docs/ scripts/ src/ tests/` → patch each hit to point at new location OR add a deprecation note. Per Codex's P2-1 list: specifically `docs/pipeline_audit_context/04_sample_run_artifacts.md`, `docs/pipeline_audit_context/06_recent_commits.md`, `docs/task_acceptance_matrix.yaml`.
8. **.gitignore additions:** anchored patterns appended to `.gitignore` (see Final .gitignore additions below).
9. **Sanity test:** `python -c "import polaris_graph"` + targeted pytest collection (no run) to confirm no import-time breakage from the moves.
10. **Codex diff review** (separate brief, this is plan review only).

## Final .gitignore additions (anchored)

```
# --- I-hygiene-001 root-clutter prevention (2026-05-11) ---
# Pytest temp dirs (mkdtemp output + manual scratch)
/tmp*/
/.tmp*/
/POLARIS.tmppytest/
/POLARIStmp_pytest*/
/pytest-cache-files-*/
/pytest_basetemp*/
/pytest_run_*/
/py_pytest_*/
/.pytest-cache*/
/.pytest_cache*/
/.pytest_scope_gate_tmp*/
/.pytest_tmp*/
/manual_pytest_*/
/manual_review_scratch*/
/manual_tmp_*/
/md3_pytest*/
/md3_round*_tmp/
# Codex review temp dirs
/.codex-tmp/
/.codex_tmp*/
/.codex_pytest_tmp/
/.codex_review_workforce/
/codex_cache_*/
/codex_review_tmp_*/
/codex_tmp_*/
# Manual milestone scratch
/m8_*/
/m9_*/
/m9v*/
/m10v*/
/m_int_*_manual_*/
/m_live_*/
# UI probes
/dashboard_probe_*/
/python_mode_*_probe/
# .codex/ historical walkthrough screenshots (regenerated by scripts)
/.codex/walkthrough_screenshots*/
```

Note: anchored `/` prefix is important — without it, `tmp*/` would match `src/foo/tmp_local/` too, which is over-broad per your P2-4.

## Questions for Codex (iter 2)

1. Confirm KEEP list now correct (35 root + 172 .codex/) — anything still misclassified?
2. Confirm ARCHIVE list (146 root + ~230 .codex/ after applying your inspect_adjudication) — anything load-bearing I missed?
3. Confirm anchored .gitignore additions match your P2-4 — under-broad? over-broad?
4. Confirm the cleanup-manifest schema (src/dest/tracked/mtime/size/method) — anything else needed for auditability?
5. Approve the execution flow (idempotent re-inventory, git mv for tracked, halt-on-permission-error)?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
final_keep_corrections: [...]
final_archive_corrections: [...]
gitignore_pattern_review: [...]
manifest_schema_review: [...]
execution_flow_review: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
