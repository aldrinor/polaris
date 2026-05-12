HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-hygiene-001 — POLARIS root + .codex/ surgical cleanup plan (PLAN REVIEW, not diff)

GH#432. Branch `bot/I-hygiene-001-root-folder-cleanup`. This is iter 1 of plan review. Diff review (separate brief) comes after plan APPROVE.

## User directive (verbatim)

> "OK, pls update the issue list on Github, and help me to have a surgical clean up on the POLARIS folder and file and file name, make sure all file name follow the standard requirement in CLAUDE.md, pls archive all old, confusing, temp, wrong, obselete, test, files and folders inside POLARIS root folder, and I don't expect you fuck my C root folder up. After you complete this job, you must let Codex to review and approve your deliverable. I don't want overkill. I don't want missing. Afterwards, you need to update all necessary doc in github and local, readme, directory, log, handover, task list, todo list, plan, etc"

## Scope

- **In scope:** `C:/POLARIS/` root directory entries + `.codex/` root entries.
- **OUT OF SCOPE (do not touch):** `C:/` above POLARIS (user explicit); `polaris-controls/` (admin-only sister repo with signed-commits-required); `src/`, `tests/`, `scripts/`, `web/`, `docs/`, `config/`, `helm/` contents (production code); existing `archive/` content.

## Approach

- **NO DELETES.** Every flagged entry is moved (git mv where tracked, OS mv where untracked) into `archive/2026-05-11-root-hygiene/<sub>/`. Reversible.
- Inventory built mechanically (`scripts/inventory_root_hygiene.py` + `scripts/inventory_codex_hygiene.py`). Saved at `state/polaris_restart/i_hygiene_001_inventory.md` + `..._codex_inventory.md`.
- **CLAUDE.md §4.1 snake_case enforcement:** the violators at root (e.g. `POLARIS.tmppytest`, `POLARIStmp_pytest_m_int_3_reviewbasetemp`) are flagged ARCHIVE candidates — both are pytest temp dirs anyway, so archive-not-rename satisfies the rule. No active tracked file at root violates snake_case.

## Categorization

### Root directory (181 entries enumerated 2026-05-11)

**KEEP (35) — essential project structure, must remain at root:**

Hidden:
- `.claude/`, `.codex/`, `.dockerignore`, `.env`, `.env.example`, `.git/`, `.github/`, `.gitignore`, `.legacy/`, `.private/`

Files:
- `CLAUDE.md`, `Dockerfile`, `README.md`, `architecture.md`, `ground_rules.md`, `docker-compose.yml`, `pytest.ini`, `requirements.txt`, `requirements-orchestrator.txt`, `requirements-v6.txt`

Dirs:
- `archive/`, `config/`, `data/`, `docs/`, `helm/`, `logs/`, `memory/`, `models/`, `outputs/`, `polaris-controls/`, `scripts/`, `src/`, `state/`, `tests/`, `web/`

**ARCHIVE (146) — move to `archive/2026-05-11-root-hygiene/`:**

Categories (by pattern):
- `.codex_tmp*`, `.codex-tmp`, `.codex_pytest_tmp`, `.codex_review_workforce` (7 dirs) — historical Codex review temp dirs
- `.coverage` (file) — coverage report, rebuildable
- `.pytest-cache*`, `.pytest_cache*`, `.pytest_scope_gate_tmp*`, `.pytest_tmp*` (6 dirs) — pytest caches, rebuildable
- `.ruff_cache` (dir) — ruff cache, rebuildable
- `.tmp*` (9 dirs) — pytest temp dirs
- `POLARIS.tmppytest`, `POLARIStmp_pytest_m_int_3_reviewbasetemp` (2 dirs) — CLAUDE.md §4.1 violators (dot/no-separator), pytest temps
- `__pycache__/` (root dir) — Python bytecode
- `codex_cache_*`, `codex_review_tmp_*`, `codex_tmp_*` (~60 dirs) — historical Codex review temp dirs (M-INT-5..11 era, I-bug-101/107 era)
- `dashboard_probe_*` (5 dirs) — UI probe scratch
- `m10v*`, `m8_*`, `m9_*`, `m_int_*_manual_*`, `m_live_*` (~10 dirs) — manual test scratch
- `manual_pytest_*`, `manual_review_scratch_*`, `manual_tmp_*` (~5 dirs) — manual scratch
- `md3_*` (3 dirs) — M-D3 manual test scratch
- `py_pytest_*`, `pytest-cache-files-*`, `pytest_basetemp_*`, `pytest_run_*` (~8 dirs) — pytest run dirs
- `python_mode_700_probe/` (1 dir) — probe
- `tmp*` (15+ dirs) — assorted temp dirs (mkdtemp() output)

**INSPECT (0) — none at root level; categorization complete.**

### `.codex/` directory (403 entries enumerated 2026-05-11)

**KEEP (171) — current issue-driven dirs + canonical protocol docs:**

Protocol docs:
- `AUDIT_CYCLE_PROTOCOL.md`, `REVIEW_BRIEF_FORMAT.md`, `REVIEW_BRIEF_FORMAT_v2.md`, `LOOP_PROTOCOL.md`, `codex_red_team_checklist.md`, `config.toml`

Current issue-driven dirs:
- All `I-*` dirs (I-anti-*, I-audit-*, I-bakeoff-*, I-beat-*, I-bench-*, I-bug-079..111, I-cj-*, I-decompose-*, I-doc-*, I-ecg-*, I-eval-*, I-f2..f9-*, I-f15-*, I-gen-*, I-hygiene-001, I-tests-*, I-tpl-*) — these are the issue-driven workflow substrate.
- `GH400`, `GH405` — GH-numbered issue dirs.

**ARCHIVE (48) — clearly-historical at `.codex/` root:**

- `m_int_*_review_output.md` (~20 files) — M-INT-3..11 review outputs (all closed milestones)
- `m26_*_brief.md` (5 files) — M-26 threat model round briefs
- `md1_*_brief.md`, `md2_*_brief.md` (4 files) — M-D1/M-D2 harness/LLM round briefs
- `g2_*_brief.md`, `g2_*_verdict_iter_1.txt` (2 files) — G2 acknowledgement review (closed)
- `cleanup_pr_1_dryrun_*` (8 files) — historical cleanup PR-1 dryrun rounds (closed)
- `audit_v32_baseline/`, `faithfulness_gap/` (2 dirs) — pre-issue-driven

**INSPECT (184) — Codex must adjudicate; my proposed categorization below:**

Files I propose ARCHIVE:
- `REVIEW_BRIEF.md` — Codex code-review brief from honest-rebuild era (pre-issue-driven). Reason: the canonical review brief template is `REVIEW_BRIEF_FORMAT.md`; this one is historical.
- `ROUND_N_BRIEF_TEMPLATE.md` — historical template.
- `autoloop_v2_protocol_review_brief.md` — superseded by issue-driven workflow.
- `carney_delivery_plan_FINAL_review_brief.md` — historical plan review (Carney plan v5.3 era, superseded by v6.2).
- `loop_state.json` — historical autoloop state (`status: terminated_ready`, round 5 of 12 from old M-era loop).
- `m28_*..m63_*` code audit briefs and pass2..pass6 variants (~60 files) — Phase B/C/D milestones M-28 to M-63 are all completed and locked.
- `md3_verdict_brief.md`, `md5_v3_verdict_brief.md`, `md5_verdict_brief.md` — M-D3/M-D5 verdicts (locked).
- `phase_c_plan.md`, `phase_d_milestones_review_brief.md`, `phase_d_milestones_round2..3_brief.md` — historical phase plans (Phase C/D locked).
- `plan_amendment_skip_road_b_reset_verdict_iter_1.txt` — historical plan amendment verdict.
- `pr_b*`, `pr_d*`, `pr_e*`, `pr_b2_*` review briefs + iter verdicts (~20 files) — PR-B/D/E/B2 all merged & closed.
- `shippable_plan_*.md` (3 files) — historical shippable plan reviews.
- `test_failure_triage_*` (3 files) — historical triage briefs.
- `triage_executed_*` (2 files) — historical.
- `v17_*..v30_*` plan + audit briefs (~30 files) — version-era pre-issue-driven, all superseded.
- `walkthrough_2026_05_04.md`, `walkthrough_screenshots_2026_05_04*/` (4 dirs) — historical walkthrough captures.

Dirs I propose ARCHIVE:
- `continuous/` — commit-hash-prefixed audit notes from M-era (`07d6c30_2c5b_inspector_error_a11y.md` etc); historical commit-by-commit audits.
- `deep_dive_round_1..7_*/` (7 dirs) — historical deep-dive rounds from honest-rebuild era.
- `next_issue_pick`, `next_issue_pick_2`, `next_issue_pick_3`, `next_pick_post_cj` — historical issue-picker outputs.
- `round_2`, `round_3`, `round_4`, `round_5` — historical review rounds (likely from autoloop V2 era).
- `runs/` — empty dir.
- `slices/slice_001..005` — historical slice plans (slice-001..005 all completed; archive/ already has slice plans).
- `strategic_review_high_quality/` — historical.
- `task_briefs/` (1 file: `v6_phase_0_1_substrate_round_3_review_brief.md`) — Phase 0.1 substrate review (locked).

## Execution plan (post APPROVE)

1. Create archive dir: `archive/2026-05-11-root-hygiene/{root,codex_historical}/`
2. For each ARCHIVE entry at root: `mv "C:/POLARIS/<name>" "C:/POLARIS/archive/2026-05-11-root-hygiene/root/<name>"`.
3. For each ARCHIVE entry in `.codex/`: `mv ".codex/<name>" "archive/2026-05-11-root-hygiene/codex_historical/<name>"`.
4. Update `.gitignore` to keep these patterns ignored going forward (some are already ignored via `__pycache__`, `.pytest_cache/`, `.ruff_cache/`, etc — verify and add the missing ones like `tmp*/`, `codex_tmp_*/`, `manual_*/`, `dashboard_probe_*/`, `pytest-cache-files-*/`, `pytest_run_*/`, `py_pytest_*/`, `pytest_basetemp_*/`).
5. Update `docs/file_directory.md`, `README.md` §"Repository Layout", `logs/session_log.md`, `state/polaris_restart/issue_breakdown.md`, `state/restart_instructions.md`, `state/handover.md` if exists.
6. Codex diff review (separate brief).
7. User merges.

## Volume estimate

- Root: 146 entries → moved
- .codex/: 48 ARCHIVE-confirmed + ~150 ARCHIVE-from-INSPECT (pending your verdict) → moved
- Total disk space freed at root: tens of MB (pytest temp dirs are small)
- Reversible: every entry is in `archive/2026-05-11-root-hygiene/`. Can git restore or filesystem-restore.

## Questions for Codex

1. **Approve the KEEP list at root** — are 35 entries correct? Anything missed? Anything wrongly KEPT?
2. **Approve the ARCHIVE list at root** — are 146 entries all safe to archive? Any one of them load-bearing?
3. **Approve the .codex/ KEEP list** — 171 current issue-driven dirs + 6 protocol docs. Correct?
4. **Approve the .codex/ ARCHIVE list (48 confirmed + my proposed INSPECT→ARCHIVE)** — anything that should stay at .codex/ root? Specifically: should `loop_state.json` stay (active runtime state) or archive (terminated)? Should `continuous/` stay (active continuous-audit substrate per `outputs/audits/continuous/` exemption in .gitignore line 47) or archive?
5. **.gitignore additions** — what patterns should I add to prevent re-accumulation?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
keep_corrections: [...]  # entries Claude listed KEEP that should be ARCHIVE
archive_corrections: [...]  # entries Claude listed ARCHIVE that should be KEEP
inspect_adjudication: [...]  # for each INSPECT, your verdict
gitignore_additions: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
