# POLARIS cleanup audit (state/polaris_restart/cleanup_audit.md)

**Authority:** advisory until Codex APPROVE.
**Source:** `state/polaris_restart/plan.md` §8 (Codex-APPROVE'd at iter 4 on 2026-05-05).
**Iter:** 21 of N (no hard cap per CLAUDE.md §8.3.1).

This document classifies every file/folder under `C:\POLARIS\` per CLAUDE.md §4.1 + §5 + plan §8. Each row: KEEP / ARCHIVE / DELETE / RENAME with reason. Anti-overkill: confirmed each via grep for references + git log for last-touch age + size check before decision.

Per plan §7.E: ARCHIVE when in doubt; DELETE only for zero-audit-value + zero-references items (pytest tmpdirs, sqlite probes, build outputs).
Per plan §8.0a: every move logged in **`state/polaris_restart/cleanup_manifest.md`** (tracked path; archive payloads stay gitignored under `archive/2026-05-05/`). iter 3 CLEAN-ARCHIVE-1 fix: §10/§4 path consistency.

---

## §1 Inventory metrics (verified 2026-05-05)

- POLARIS branch HEAD: `7e96a53` (will reset to `365f334` per plan §7.D ROAD B)
- Total tracked files (`git ls-files | wc -l`): **2477**
- Tracked `.codex/` files: **433** (review briefs, verdicts, slice drafts)
- Tracked `outputs/audits/` files: **94**
- Tracked `outputs/codex_findings/` files: **269**
- Untracked top-level `codex_tmp_*` / `tmp_*` / `m_int_*` / `manual_*` / `m9_v*` / `m10v*` / `m8_*` / `dashboard_probe_*` / `pytest_*` directories: **96**
- Untracked `.sqlite` files at repo root: **9** (jobs_test_probe, m10v2/v3 variants, m_int_11_manual_review, manual_probe_root, sqlite_probe_root)
- `state/*.sqlite` runtime caches: **3.2 GB total**, including 2.2 GB `pg_checkpoints.sqlite` + 584 MB `pg_content_cache.sqlite` (gitignored, runtime data per CLAUDE.md §5)
- `archive/` directory: **36 GB total**, gitignored, 33 entries (existing audit-trail archive snapshots)
- Adjective-named tracked files (CLAUDE.md §4.1 violations: `*FINAL*`, `*_v[0-9]*`, `*latest*`, `*_post_*`): **518** (most are `_v2`/`_v3`/`_v4` Codex review briefs and milestone audits — many ARCHIVE candidates)
- `polaris-controls/` directory in `C:\POLARIS\`: **does NOT exist** (correct — it's a sibling at `C:\polaris-controls\`)
- `state/we_control/`: **does NOT exist** (correct — sister project, no cross-contamination)
- `state/neuron_session/`: **does NOT exist** (correct — sister Chrome-profile risk does not apply)
- `.private/`: contains 1 file `codex_hmac.key` (66 bytes, last modified 2026-05-02)

---

## §2 Hard do-not-touch list (plan §8.1)

These are NEVER moved/renamed/deleted by cleanup PR. Any cleanup classification touching these paths fails Codex APPROVE.

| Path | Reason |
|---|---|
| `polaris-controls/` (sister dir at `C:\polaris-controls\`) | admin-only separate repo |
| `.git/`, `.gitignore`, `.gitattributes` | git infrastructure |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore` | runtime; sister's iter-2 P0 caught analogous mass-cleanup risk |
| `requirements.txt`, `pyproject.toml`, `package.json`, `web/package.json`, `web/package-lock.json` | dependency manifests |
| `.env.example` (existence), `.env` (gitignored) | environment |
| `src/polaris_graph/` | active production substrate (159 prior commits, 305 tests) |
| `src/polaris_v6/` | active backend |
| `src/orchestration/` | per CLAUDE.md §5 (FROZEN since 2026-03-16, do-not-touch) |
| `src/auth/`, `src/audit/`, `src/config/`, `src/tools/` | active per CLAUDE.md §5 |
| **iter 12 CLEAN-SRC-INVENTORY-OMISSION-1 fix — additional active src/ packages at reset target:** | |
| `src/agents/`, `src/benchmarks/`, `src/llm/`, `src/memory/`, `src/providers/`, `src/quality/`, `src/schemas/`, `src/search/`, `src/utils/`, `src/__init__.py` | tracked at reset target; active per `git ls-tree`. KEEP entirely; do-not-touch per same §2 logic as polaris_graph/polaris_v6/orchestration. Cleanup PRs do NOT touch any `src/*` subtree. |
| **iter 12 CLEAN-TESTS-INVENTORY-OMISSION-2 fix — `tests/` subtree at reset target (~539 files):** | |
| `tests/e2e/`, `tests/unit/`, `tests/v3/`, `tests/v6/`, `tests/polaris_graph/` (305 tests), `tests/fixtures/`, screenshot fixtures, root tests, visual audit scripts | tracked at reset target; KEEP entirely. Do-not-touch as group per §2 (already lists `tests/polaris_graph/golden/test_slice_001_goldens.py` immutable; broader `tests/` is also active code). Cleanup PRs do NOT touch `tests/*` except where iter-7 §3.11 reset-removed slice 2-5 runners (which are already (NOT present at reset target)). |
| `web/` (except `web/.next/`, `web/node_modules/`, `web/test-results/`) | active frontend |
| `tests/polaris_graph/golden/test_slice_001_goldens.py` | per CHARTER §4 immutable |
| `outputs/codex_findings/` | tracked per CLAUDE.md §5 exception |
| `archive/` itself | per CHARTER §6 read-only (cleanup destination, not source) |
| `.legacy/` | **iter 14 CLEAN-LEGACY-DNT-INCONSISTENT-1 fix:** per CHARTER §6 immutable historical content; never touched. |
| `archive/2026-04-18-pre-audit-cleanup/` | existing snapshot |
| `state/polaris_restart/` | this plan + iter trail |
| `state/pg_checkpoints.sqlite`, `state/pg_*.sqlite` (gitignored runtime caches) | live state; do not touch unless backup made |
| `pytest.ini`, `conftest.py` | test infra |

---

## §3 Classification table

Categories:
- **K** = KEEP
- **A** = ARCHIVE to `archive/2026-05-05/<subdir>/` per plan §8.4
- **D** = DELETE (truly dead, zero references, zero audit value)
- **R** = RENAME (CLAUDE.md §4.1 adjective violation; rename in place)

Provenance per row: `git ls-files <path>` (T=tracked, U=untracked), `grep -r <name> src/ web/ scripts/ Dockerfile docker-compose.yml` count, `git log -1 --format=%ai -- <path>` last touch.

### §3.1 Top-level files (verified 2026-05-05 by `ls` — FIXED iter 3 CLEAN-INV-1)

| Path | T/U | Action | Reason |
|---|---|---|---|
| `README.md` | T | K | active doc per plan §9 update |
| `CLAUDE.md` | T | K | DNA file; updated per plan §9 |
| `architecture.md` | T | K | foundation per plan §1 |
| `ground_rules.md` | T | K | engineering ground rules |
| `requirements.txt` | T | K | do-not-touch §2 |
| `requirements-orchestrator.txt`, `requirements-v6.txt` | T | K | dependency variants (actual filenames; not `cpu`/`gpu` per iter 1) |
| `docker-compose.yml` | T | K | do-not-touch §2 |
| `.gitignore`, `.gitattributes`, `.dockerignore`, `.env.example`, `pytest.ini`, `Dockerfile` | T | K | do-not-touch §2 |
| `.env` (gitignored) | U | K | gitignored, do not touch |
| `m_int_7_manual_probe.txt` | U | D | per §3.4 — manual probe artifact |
| `write_probe_root.txt` | U | D | manual write probe artifact |

(Per iter 1 CLEAN-INV-1 finding: `pyproject.toml`, `package.json`, `LICENSE`, `conftest.py`, `requirements-cpu.txt`, `requirements-gpu.txt` do NOT exist at repo root. Removed from inventory.)

### §3.2 `.codex/` directory (433 tracked files)

| Path pattern | Action | Destination | Reason |
|---|---|---|---|
| `.codex/codex_red_team_checklist.md` | K | — | foundation per Carney v6.2 §"per-task triangle loop" |
| `.codex/REVIEW_BRIEF_FORMAT_v2.md` | R → `.codex/review_brief_format.md` | — | CLAUDE.md §4.1 `_v2`. **iter 16 CLEAN-REN-HISTORICAL-ROW-15 fix:** authoritative ACTIVE touch list at reset target (post-PR-3 archive) is the iter-12 8-file list ONLY: `.claude/hooks/stop_hook_v3.py`, `CLAUDE.md`, `docs/canonical_pin.txt`, `docs/schemas/codex_verdict.schema.json`, `scripts/autoloop/orchestrator.py`, `scripts/strip_changelog_markers.py`, `src/polaris_v6/memory/store.py`, `tests/v6/test_workspace_memory.py`. Earlier mention of `.codex/continuous/` and `.codex/_archive_pre_v6_2/` was wrong — those are immutable history per §5 gate exclusion policy + PR-3 archives them so they vanish from active tree before this rename runs. CI gate: `zero_hit_gate.sh "REVIEW_BRIEF_FORMAT_v2"` returns 0 hits post-rename. |
| `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` | R → `.codex/audit_cycle_protocol.md` | — | CLAUDE.md §4.1 `_v2`. **iter 16 fix:** same authoritative 8-file active list as REVIEW_BRIEF_FORMAT_v2. Immutable-history paths excluded. |
| `.codex/LOOP_PROTOCOL.md` | K | — | active protocol per memory `project_codex_audit_loop` |
| `.codex/loop_log.jsonl` | K | — | per CHARTER §7 visibility log |
| `.codex/m1_*_review_brief.md` (~30 files), `.codex/m10_*` through `.codex/m26_*` series | (NOT present top-level at reset target) | **iter 16 CLEAN-CODEX-RESET-NOOP-15 fix:** verified at `365f334` — top-level `.codex/m1..m26_review_brief.md` files do NOT exist (all under `.codex/_archive_pre_v6_2/` already, archived in PR-3 batch via that dir). Earlier ARCHIVE row was wrong. No cleanup PR action for top-level. |
| `.codex/m_int_*_review_brief.md` (28 files under `.codex/_archive_pre_v6_2/`) | A (via parent `.codex/_archive_pre_v6_2/` archive) | `archive/2026-05-05/codex_archive_pre_v6_2/` (already in PR-3) | **iter 16 CLEAN-CODEX-RESET-NOOP-15 fix:** verified at `365f334` — top-level `.codex/m_int_*_review_brief.md` files do NOT exist; the 28 review briefs live under `.codex/_archive_pre_v6_2/`, naturally archived in PR-3 when that whole dir is moved. Top-level only has 9 verdict briefs (handled by PR-2). |
| `.codex/m28_*` through `.codex/m63_*` brief files | A | `archive/2026-05-05/codex_briefs_milestones_m28_to_m63/` | **iter 8 CLEAN-INVENTORY-RANGE-2 fix:** verified at reset target via `git ls-tree -r --name-only 365f334 .codex/ \| grep '^\.codex/m[0-9]'` enumeration: ranges m28, m29, m30, m31, m32, m33, m34, m35, m36, m37, m38, m40, m41, m42, m43, m44, m45, m46, m47, m48, m50, m51, m52, m54, m55, m56, m57, m58, m59, m60, m61, m62, m63 (gaps at m39/m49/m53). M64-M72 do NOT exist at reset target (iter 6/7 range was overstated). Round-suffix preserved per CLAUDE.md §4.1 "round" is descriptive not adjectival. |
| `.codex/v27_*_brief.md`, `.codex/v28_*_brief.md`, `.codex/v29_*_brief.md`, `.codex/v30_*_brief.md` | A | `archive/2026-05-05/codex_briefs_v27_to_v30/` | **iter 8 CLEAN-INVENTORY-RANGE-2 fix:** verified at reset target via `git ls-tree -r --name-only 365f334 .codex/ \| grep '^\.codex/v[0-9]'`: V6, V17, V23, V27, V28, V29, V30 (V31-V33 do NOT exist at reset target — iter 6/7 range was overstated). V6/V17/V23 brief routing handled by separate `.codex/v6_*` (Plan-v13-era) and `.codex/v17_*` / `.codex/v23_*` rows. |
| `.codex/v17_*_brief.md`, `.codex/v23_*_brief.md` | A | `archive/2026-05-05/codex_briefs_v_legacy/` | **iter 8 CLEAN-INVENTORY-RANGE-2 fix:** v17 + v23 sweep briefs at reset target enumerated separately. **iter 14 fix:** explicitly added to Cleanup-PR-4 schedule. |
| **iter 14 CLEAN-CODEX-VERDICT-BRIEFS-OMISSION-4 fix — verdict-brief files at reset target (~17 files via `git ls-tree -r 365f334 .codex/ \| grep _verdict_brief`):** | | | |
| `.codex/m_int_*_verdict_brief.md` (m_int_3..11 series, ~9 files) | A | `archive/2026-05-05/codex_verdict_briefs_m_int/` | **iter 19 CLEAN-VERDICT-ROW-PR-COMMENTS-18 fix:** M-INT verdict briefs (top-level) → Cleanup-PR-2 batch (canonical 10-PR table). M-INT review briefs are inside `.codex/_archive_pre_v6_2/`, archived by Cleanup-PR-3a. |
| `.codex/m_live_*_verdict_brief.md` (m_live_1..4, 4 files) | A | `archive/2026-05-05/codex_verdict_briefs_m_live/` | **iter 19 fix:** M-LIVE verdict briefs (top-level) → Cleanup-PR-2 batch. Review briefs inside `_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/m_prod_*_verdict_brief.md` (m_prod_1, 3, 4, 3 files) | A | `archive/2026-05-05/codex_verdict_briefs_m_prod/` | **iter 19 fix:** M-PROD verdict briefs (top-level) → Cleanup-PR-2 batch. Review briefs inside `_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/md9_phase2_v5_verdict_brief.md`, `.codex/md9_phase2_v6_verdict_brief.md` | A | `archive/2026-05-05/codex_verdict_briefs_md/` | **iter 19 fix:** md9 phase 2 verdict briefs (top-level) → Cleanup-PR-2 batch. md series review briefs inside `_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/shippable_plan_*_brief.md` (3 files: base + v3 + v4) | A | `archive/2026-05-05/codex_briefs_shippable_plan/` | **iter 6 CLEAN-CODEX-INVENTORY-2 fix:** shippable plan briefs across versions. |
| `.codex/v6_phase_0_1_*` (Plan-v13-era) | A | `archive/2026-05-05/codex_briefs_v6_phase_transition/` | **iter 6 CLEAN-V6-PHASE-REFS-1 fix:** moved from prose-only to classification table. Same Cleanup-PR-3c batch (per iter-17 split). |
| **iter 7 CLEAN-TARGET-INVENTORY-3 fixes — files VERIFIED at reset target `365f334` via `git ls-tree`:** | | | |
| `.codex/REVIEW_BRIEF.md` | K | — | tracked at reset target; canonical brief format reference (NOT `_v2`). |
| `.codex/ROUND_N_BRIEF_TEMPLATE.md` | K | — | tracked at reset target; round-N brief template active per autoloop V2 protocol. |
| `.codex/loop_state.json` | K | — | tracked at reset target; active autoloop state (gitignored runtime data analog tracked here for audit). Per Plan-v13 §B stop hook reads this. If Plan v13 deprecated, KEEP for now; separate decommission PR archives later. |
| `.codex/config.toml` | K | — | tracked at reset target; Codex CLI config. Active. |
| ~~`.codex/v28_*_brief.md` through `.codex/v33_*_brief.md`~~ | (superseded) | **iter 8 CLEAN-INVENTORY-RANGE-2 fix:** iter 7 row was wrong (V31-V33 do not exist at reset target). Replaced by V27-V30 row above. |
| `outputs/audits/continuous/` (tracked subtree at reset target) | K | — | **iter 7 CLEAN-OUTPUTS-SCHEDULE-1 fix:** historical audit payload per §5 immutability policy. Excluded from rename gates per canonical gate spec. NOT archived (would break payload). |
| `outputs/audits/v27/`, `v28/`, `v29/`, `v30_phase2/` (tracked subtrees at reset target) | K | — | **iter 7 CLEAN-OUTPUTS-SCHEDULE-1 fix:** historical sweep audit payloads at reset target. KEEP per immutability policy. (Earlier iter classification of `v25/v26/v27` ARCHIVE was wrong for reset target — those exist in current HEAD but not as the v25/v26 trees claimed; reset has `v27/v28/v29/v30_phase2/` as KEEP audit history.) |
| `outputs/audits/verdicts/` (tracked at reset target) | K | — | iter 7: Codex verdicts trail; KEEP. |
| `outputs/audits/manifests/` (tracked at reset target) | K | — | iter 7: audit manifests; KEEP. |
| `.legacy/` (tracked subtree at reset target) | K | — | **iter 14 CLEAN-LEGACY-DNT-INCONSISTENT-1 fix:** explicitly added to §2 do-not-touch list (was previously missing). Added to all rename-gate exclusions and draft-preflight excludes. KEEP per CHARTER §6 immutability. |
| `logs/` (tracked subtree at reset target) | K | — | **iter 7:** session_log + bug_log + pg_cost_ledger; active append-only audit per CLAUDE.md §5. KEEP. |
| `config/` (tracked subtree at reset target) | K | — | **iter 7:** YAML config files + scope_templates + completeness_checklists per CLAUDE.md §5. KEEP. |
| `helm/` (tracked subtree at reset target) | K-pending-inspect | — | **iter 8 CLEAN-HELM-EVIDENCE-1 fix:** Codex iter 7 verdict noted "referenced from active deployment" was unverified (only stale draft mention surfaced). Reclassified KEEP-pending-inspect — added to §6 INSPECT list for future iter. Default behavior: cleanup PRs do NOT touch `helm/`. |
| `.codex/m54_code_audit_brief.md` | A (NOT renamed) | `archive/2026-05-05/codex_briefs_milestones_m28_to_m63/m54_v1.md` | **iter 9 CLEAN-M54-DEST-1 fix:** destination corrected to `m28_to_m63` per iter-8 CLEAN-INVENTORY-RANGE-2 range tightening. **iter 6 CLEAN-M54-COLLISION-1 fix:** since both `m54_code_audit_brief.md` AND `m54_code_audit_brief_v2.md` exist at `365f334`, iter 1 RENAME would collide. Resolution: archive both with disambiguating suffix `_v1` and `_v2`; do NOT rename `_v2` to drop suffix. |
| `.codex/m54_code_audit_brief_v2.md` | A | `archive/2026-05-05/codex_briefs_milestones_m28_to_m63/m54_v2.md` | **iter 9 CLEAN-M54-DEST-1 fix:** destination corrected. iter 6 CLEAN-M54-COLLISION-1 fix: paired archive with `_v1` above. |
| `.codex/m_int_*_review_output.md` (~20 untracked) | (NOT present at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** untracked review outputs not in tracked branch at `365f334`. No cleanup PR action. |
| `.codex/md1_*_brief.md`, `.codex/md2_*`, `.codex/md3_*`, `.codex/md5_*` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** verified absent via `git ls-tree --name-only 365f334 .codex/ \| grep '^\.codex/md[1-5]_'` returns 0. md9 phase 2 verdict briefs handled by PR-2 batch. |
| `.codex/m_live_*_review_brief.md`, `.codex/m_prod_*_review_brief.md` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** verified absent. M-LIVE/M-PROD review briefs are inside `.codex/_archive_pre_v6_2/`, archived by Cleanup-PR-3a. Top-level only has verdict briefs (handled by PR-2). |
| `.codex/m26_threat_model_*.md`, `.codex/m26_v17_round*` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** verified absent. m26 series files are inside `.codex/_archive_pre_v6_2/`, archived by Cleanup-PR-3a. Kept doc at `docs/m26_threat_model.md` is KEEP per §3.7. |
| `.codex/dr_output_*` (~15 files), `.codex/dr_output_audit_pass_*_v*_beat_both_brief.md` | A | `archive/2026-05-05/codex_briefs_dr_output/` | BEAT-BOTH dr-output passes; verified at reset target via `git ls-tree --name-only 365f334 .codex/ \| grep '^\.codex/dr_output'` returns >0. Cleanup-PR-3c batch. |
| `.codex/v6_2_*` series, `.codex/carney_delivery_plan_FINAL_*_review_brief.md`, `.codex/full_online_plan_brief_v2.md` | (mostly NOT present at reset target — verified `v6_2_` count = 0) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** `v6_2_*` series 0 hits at reset target top-level. `carney_delivery_plan_FINAL_*_review_brief.md` (2 files) handled by Cleanup-PR-3c batch. `full_online_plan_brief_v2.md` exists at reset target → Cleanup-PR-3c. |
| **iter 13 CLEAN-CODEX-INVENTORY-OMISSION-3 fix — additional tracked .codex briefs at reset target (verified `git ls-tree -r 365f334 .codex/`):** | | | |
| `.codex/carney_delivery_plan_v5_1_review_brief.md`, `.codex/carney_delivery_plan_v5_review_brief.md`, `.codex/carney_delivery_plan_v6_review_brief.md` | A | `archive/2026-05-05/codex_briefs_carney_plan_drafts/` | superseded by current Carney v6.2 plan. Cleanup-PR-3c batch (per iter-17 split). |
| `.codex/full_online_plan_brief.md`, `.codex/full_online_plan_brief_v3.md` | A | `archive/2026-05-05/codex_briefs_full_online/` | superseded full-online-plan briefs (v2 already captured above). Cleanup-PR-3c batch (per iter-17 split). |
| `.codex/strategic_review_brief.md` | A | `archive/2026-05-05/codex_briefs_strategic/` | strategic review brief; superseded by current Carney v6.2 architecture. Cleanup-PR-3c batch (per iter-17 split). |
| ~~`.codex/m54_code_audit_brief_v2.md`~~ | superseded by row above | iter 6 CLEAN-M54-COLLISION-1 fix replaced this row with paired-archive entries above. Original "rename to m54_code_audit_brief.md then archive" is impossible (collision with existing un-suffixed file). |
| `.codex/autoloop_v2_protocol_review_brief.md`, `.codex/autoloop_v3_*` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** `autoloop_v3_*` 0 hits top-level at `365f334`. autoloop briefs are inside `.codex/_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/phase_c_plan.md`, `.codex/phase_d_milestones_*` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** `phase_*` 0 hits at top-level. Phase docs inside `.codex/_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/test_failure_triage_*` (round2-5) | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** verified 0 hits. Inside `.codex/_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/triage_executed_*` | (NOT present top-level at reset target) | **iter 18 CLEAN-CODEX-RESET-ABSENT-ROWS-17 fix:** verified 0 hits. Inside `.codex/_archive_pre_v6_2/`, archived by PR-3a. |
| `.codex/slices/slice_001/` | K | — | active slice + architecture proposal |
| `.codex/slices/slice_00{2,3,4,5}/golden_drafts/` | (NOT present at reset target) | **iter 13 CLEAN-RESET-ABSENT-ACTION-ROWS-1 fix:** verified absent at `365f334`. Came in via post-PR-72 slice work; `pre_restart_2026_05_05` tag preserves; no cleanup PR action. |
| `.codex/slices/slice_00{2,3,4,5}/architecture_proposal.md` + other drafts | (NOT present at reset target) | **iter 13 CLEAN-RESET-ABSENT-ACTION-ROWS-1 fix:** verified absent at `365f334`. No cleanup PR action. |
| `.codex/walkthrough_screenshots_latest/`, `.codex/walkthrough_screenshots_2026_05_04_post_threshold_fix/`, `.codex/walkthrough_screenshots_2026_05_04_slices_4_5_verified/` | (NOT present at reset target) | **iter 13 CLEAN-RESET-ABSENT-ACTION-ROWS-1 fix:** verified absent at `365f334`. Walkthrough screenshot dirs were post-PR-72 work; `pre_restart_2026_05_05` tag preserves; no cleanup PR action. Earlier RENAME+ARCHIVE rows obsoleted. |
| `.codex/task_briefs/` | (NOT present at reset target) | **iter 8 + iter 16 CLEAN-TASKBRIEFS-STALE-POSTPR14-15 fix:** verified at reset target via `git ls-tree -r --name-only 365f334 .codex/task_briefs/` returns empty. Directory does not exist at `365f334`; cleanup PRs touch nothing. NOTE: `docs/task_acceptance_matrix.yaml` at `365f334` STILL contains stale internal references to `.codex/task_briefs/v6_phase_0_1_substrate_round_3_review_brief.md` and `.codex/task_briefs/**`. Resolved by the **post-Cleanup-PR-8 matrix-decommission follow-up PR** (separate from cleanup PRs), not by this audit. (Earlier "post-PR-14" wording was stale.) |
| `.codex/_archive_pre_v6_2/` | A | `archive/2026-05-05/codex_archive_pre_v6_2/` | **iter 4 CLEAN-CODEX-INVENTORY-1 fix:** previously omitted. Pre-v6.2 archived briefs; deeper history preserved here, ARCHIVE to consolidate into single 2026-05-05 archive. Contains `_v*` references that will fail rename CI gates if left at original path. |
| `.codex/continuous/` | A | `archive/2026-05-05/codex_continuous/` | **iter 4 CLEAN-CODEX-INVENTORY-1 fix:** previously omitted. Continuous-monitoring brief storage; Plan-v13-era artifact superseded by per-Issue flow. ARCHIVE. |
| `.codex/deep_dive_round_*/` (rounds 1-7 per `outputs/codex_findings/`) | A | `archive/2026-05-05/codex_deep_dive_briefs/` | **iter 4 CLEAN-CODEX-INVENTORY-1 fix:** previously omitted. Deep-dive briefs from rounds 1-7. ARCHIVE consolidates with `outputs/codex_findings/deep_dive_round_*` content (which is KEEP per CLAUDE.md §5 outputs/codex_findings exception, but the brief files in `.codex/` ARCHIVE). |
| `.codex/round_{2..5}/` | A | `archive/2026-05-05/codex_round_briefs/` | **iter 4 CLEAN-CODEX-INVENTORY-1 fix:** previously omitted. Per-round briefs. ARCHIVE. |
| `.codex/deep_dive_round_2_pipeline_b_parity/`, `.codex/deep_dive_round_1_orchestration/` | A | same as `.codex/deep_dive_round_*` group | iter 4 CLEAN-CODEX-INVENTORY-1 fix: explicit naming for these specific deep_dive subdirs. |

### §3.3 `.codex_tmp_*`, `.tmp*`, `.codex_pytest_tmp/` (gitignored pytest temp dirs)

All untracked (per `git status` warnings), all pytest tmpdirs from prior milestone runs.

| Path pattern | Action | Reason |
|---|---|---|
| `.codex_tmp/`, `.codex_tmp_*/` (~50 dirs) | D | untracked pytest tmpdirs; `grep -r` returns zero references in src/web/scripts; `git log` confirms untracked since creation; permission-denied subfolder warnings indicate stale Windows ACLs |
| `.codex_pytest_tmp/` | D | same |
| `.tmp/`, `.tmp_*/`, `.tmp-pytest/`, `.tmp_pytest*/`, `.tmp_walkthrough/`, `.tmp_md3_review/`, `.tmp_m_prod_1_r2_*/` | D | same |
| `.codex_tmp_md3_review/`, `.codex_tmp_m_int_6_v1_review_fresh/` | D | same |
| `.codex_tmp_model_pin_smoke/` | D | same |

**DELETE method (iter 2 P0 fix CLEAN-EXEC-1):** `git clean -fdX` and unconstrained `git clean -fd` are CATASTROPHIC for POLARIS. They would nuke `.env`, `state/pg_checkpoints.sqlite` (2.2 GB), `web/node_modules/`, `archive/` itself, `.private/codex_hmac.key`, untracked `outputs/codex_findings/`, etc.

**iter 4 CLEAN-DELETE-EXEC-3 fix:** since this workspace is Windows + PowerShell, the canonical implementation is `scripts/cleanup/delete_pytest_tmpdirs.ps1` (PowerShell). A bash variant `scripts/cleanup/delete_pytest_tmpdirs.sh` exists for cross-platform CI on Linux. Both implement identical allowlist + DO-NOT-TOUCH refusal + `--DryRun`/`--Apply` mode handling. Codex APPROVE on `--DryRun` transcript before `--Apply` execution.

```powershell
# scripts/cleanup/delete_pytest_tmpdirs.ps1 — Windows/PowerShell canonical
# Allowlist-only DELETE for §3.3-§3.5. Refuses any path resolving to DO-NOT-TOUCH prefix.
# iter 17 CLEAN-PS1-FUNCTION-ORDER-16 fix: helper functions defined BEFORE main loop body.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][ValidateSet('DryRun','Apply')]
  [string]$Mode
)
$ErrorActionPreference = 'Stop'
$repoRoot = (git rev-parse --show-toplevel) -replace '/', '\'
Set-Location $repoRoot

# === Helper functions (iter 20 CLEAN-PS1-SINGLE-FILE-STILL-CONTRADICTED-19 fix:
# bodies inlined below; this fenced block is now the SINGLE source of truth for
# scripts/cleanup/delete_pytest_tmpdirs.ps1 — paste-runnable as one file) ===

function Convert-ToRepoRelativePosix {
    param([string]$abs_path, [string]$repo_root)
    $rel = $abs_path
    if ($abs_path.StartsWith($repo_root, [StringComparison]::OrdinalIgnoreCase)) {
        $rel = $abs_path.Substring($repo_root.Length).TrimStart('\','/')
    }
    return $rel -replace '\\', '/'
}

function Get-DirectoryMerkleHash {
    param([string]$dir_path)
    $entries = @()
    $perm_denied = @()
    $errs = $null
    # iter 21 CLEAN-PS1-LITERALPATH-PARTIAL-20 fix: -LiteralPath consistently
    Get-ChildItem -LiteralPath $dir_path -Recurse -File -Force -ErrorAction SilentlyContinue -ErrorVariable +errs |
      Sort-Object FullName |
      ForEach-Object {
        $file_path = $_.FullName
        try {
            $hash = (Get-FileHash -LiteralPath $file_path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower()
            $rel = $file_path.Substring($dir_path.Length).TrimStart('\','/')
            $entries += "$rel`t$hash"
        } catch {
            $perm_denied += $file_path
        }
    }
    if ($errs) { foreach ($e in $errs) { $perm_denied += [string]$e.TargetObject } }
    $combined = ($entries -join "`n") + "`n"
    $merkle = [System.BitConverter]::ToString(
        [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($combined)
        )
    ).Replace('-','').ToLower()
    return @{
        merkle_root = $merkle
        per_file_count = $entries.Count
        permission_denied = $perm_denied
        per_file_lines = $entries
    }
}

function Append-ManifestEntryDirectory {
    param([string]$entry_id, [string]$path, $info, [string]$manifest_path, [string]$sidecars_subdir, [string]$repo_root)
    $rel_path = Convert-ToRepoRelativePosix $path $repo_root
    $perm_count = @($info.permission_denied).Count
    $unreadable = if ($perm_count -gt 0) { 'true' } else { 'false' }
    $perm_rel = @($info.permission_denied) | ForEach-Object { Convert-ToRepoRelativePosix $_ $repo_root }
    $perm_paths_inline = if ($perm_count -le 20) {
        '[' + (($perm_rel | ForEach-Object { "'" + ($_ -replace "'","''") + "'" }) -join ', ') + ']'
    } else {
        '[]  # truncated; see permission_denied_sidecar_path'
    }
    $size_bytes = (Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    if (-not $size_bytes) { $size_bytes = 0 }
    $combined_text = ($info.per_file_lines -join "`n") + "`n"
    $per_file_checksums_sha256 = [System.BitConverter]::ToString(
        [System.Security.Cryptography.SHA256]::Create().ComputeHash(
            [System.Text.Encoding]::UTF8.GetBytes($combined_text)
        )
    ).Replace('-','').ToLower()
    $perm_sidecar_field = if ($perm_count -gt 0) {
        "permission_denied_sidecar_path: '$sidecars_subdir/$entry_id.permission_denied.txt'"
    } else {
        "permission_denied_sidecar_path: null"
    }
    $yaml = @"
  - entry_id: $entry_id
    path: '$rel_path'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch (per §3.3-§3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: $size_bytes
    recursive_file_count: $($info.per_file_count)
    permission_denied_count: $perm_count
    permission_denied_paths: $perm_paths_inline
    $perm_sidecar_field
    merkle_root_sha256: '$($info.merkle_root)'
    per_file_checksums_sha256: '$per_file_checksums_sha256'
    per_file_checksums_sidecar_path: '$sidecars_subdir/$entry_id.per_file.txt'
    unreadable_marker: $unreadable
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: '§3.3-§3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
"@
    Add-Content -LiteralPath $manifest_path -Value $yaml
}

function Append-ManifestEntryFile {
    param([string]$entry_id, [string]$path, [string]$manifest_path, [string]$repo_root)
    $rel_path = Convert-ToRepoRelativePosix $path $repo_root
    $sha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    $size = (Get-Item -LiteralPath $path).Length
    $yaml = @"
  - entry_id: $entry_id
    path: '$rel_path'
    action: DELETE
    destination: null
    reason: 'pytest tmpdir / probe scratch file (per §3.3-§3.5 allowlist)'
    references_grep: 0
    last_modified: 'untracked'
    last_committed_sha: 'untracked'
    size_bytes: $size
    sha256: '$sha'
    evidence_chain:
      drafted_by: cleanup_script
      drafted_in_session: cleanup-pr-1
      referenced_in_plan: '§3.3-§3.5'
    cleanup_pr: 1
    codex_audit_verdict: APPROVE_PENDING
"@
    Add-Content -LiteralPath $manifest_path -Value $yaml
}

$allowlist = @(
  '.codex_tmp', '.codex_tmp_*', '.codex_pytest_tmp',
  '.tmp', '.tmp-pytest', '.tmp_pytest', '.tmp_pytest_base',
  '.tmp_pytest_*', '.tmp_walkthrough', '.tmp_md3_review',
  '.tmp_m_prod_1_r2_*', '.pytest_tmp', '.tmp_*',
  'POLARIS.tmppytest', 'POLARIStmp_pytest_m_int_3_reviewbasetemp',
  'pytest_run_*', 'py_pytest_*', 'pytest-cache-files-*',
  'codex_tmp_*', 'tmp[0-9a-z]*', 'tmp_*',  # iter 20 CLEAN-PS1-ALLOWLIST-TMP-UNDERSCORE-19 fix: tmp_* per §3.4 + bash parity
  'manual_*', 'manual_review_scratch_*', 'manual_pytest_base_*',
  'manual_tmp_*', 'manual_sqlite_dir',
  'm_int_*_manual_*', 'm_int_*_v*_manual_*', 'm_int_*_probe_*',
  'm9_v*', 'm10v*', 'm8_*', 'md3_*',
  'dashboard_probe_*', '_m1v2_tmp2',
  'm_int_2_main_async_check', 'm_int_2_manual_check',
  'm_int_7_concurrency_probe', 'm_int_7_main_async_probe',
  'm_int_7_manual_probe', 'm_int_7_manual_probe.txt',
  'm_int_10_manual_*', 'm_int_11_*manual*', 'm_new_race_*', 'm_live_4_r2_*',
  'm26_v17_round4_*',
  'jobs_test_probe.sqlite', 'm10v2_manual_*.sqlite', 'm10v2_ws_probe_*.sqlite',
  'm10v3_*.sqlite', 'm_int_11_manual_review_*.sqlite',
  'manual_probe_root.sqlite', 'sqlite_probe_root.sqlite',
  'write_probe_root.txt',
  # iter 6 CLEAN-OUTPUTS-ALLOWLIST-2 fix: outputs/* pytest tmpdirs (paths from §3.8)
  'outputs\codex_tmp_pytest', 'outputs\pytest_basetemp',
  'outputs\pytest_temp', 'outputs\pytest_tmp'
)

$doNotTouch = @(
  '.git', '.github', '.env', '.env.example',
  'src', 'web', 'tests', 'scripts',
  'docs', 'config',
  'state\pg_', 'state\polaris_restart',
  'archive', '.private',
  'outputs\codex_findings', 'outputs\audits',
  'README.md', 'CLAUDE.md', 'architecture.md',
  'Dockerfile', 'docker-compose.yml',
  'requirements.txt'
) | ForEach-Object { Join-Path $repoRoot $_ }

# iter 10 CLEAN-PS1-INIT-IN-BLOCK-1 fix: initialize tracking arrays INSIDE the
# fenced script before main loop (was previously documented as a sidebar after
# the block, leaving the script non-runnable as-pasted).
$deletedPaths = @()
$failedPaths = @()
$count = 0
foreach ($pattern in $allowlist) {
  # iter 6 CLEAN-EXEC-PS1-ENUM-1 fix: literal directory names need parent-scoped enumeration
  # to match the directory itself, not its children. Use Get-Item for non-wildcard, Get-ChildItem for wildcards.
  $items = if ($pattern -match '[\*\?]') {
    Get-ChildItem -Path . -Filter $pattern -Force -ErrorAction SilentlyContinue
  } else {
    @(Get-Item -LiteralPath $pattern -Force -ErrorAction SilentlyContinue) | Where-Object { $_ -ne $null }
  }
  $items | ForEach-Object {
    $abs = $_.FullName
    foreach ($dnt in $doNotTouch) {
      if ($abs.StartsWith($dnt, [StringComparison]::OrdinalIgnoreCase)) {
        Write-Error "REFUSING $($_.Name) (resolves to $abs, inside protected $dnt)"
        exit 2
      }
    }
    if ($Mode -eq 'DryRun') {
      Write-Host "WOULD DELETE: $($_.Name)  (resolved: $abs)"
    } else {
      # iter 16 CLEAN-PR1-MANIFEST-INTEGRATION-15 fix: emit manifest entry BEFORE deletion.
      # Earlier iter-13/14/15 placed Append-ManifestEntry calls in a separate snippet block;
      # this fold-in moves them inline so the script is single-runnable.
      $entry_id = "del_{0:D3}" -f $count
      $manifest_path = Join-Path $repoRoot 'state/polaris_restart/cleanup_manifest.md'
      $sidecars_dir = Join-Path $repoRoot 'state/polaris_restart/cleanup_manifest_sidecars'
      $sidecars_subdir = 'state/polaris_restart/cleanup_manifest_sidecars'
      New-Item -ItemType Directory -Path $sidecars_dir -Force | Out-Null
      try {
        if (Test-Path -LiteralPath $abs -PathType Container) {
          $info = Get-DirectoryMerkleHash $abs
          # iter 20 CLEAN-SIDECAR-HASH-BYTE-SEMANTICS-19 fix: write UTF-8 no-BOM with LF line endings
          # so sidecar bytes match the in-memory `path\tsha\n` body the merkle/per_file_checksums hash.
          $per_file_body = ($info.per_file_lines -join "`n") + "`n"
          [System.IO.File]::WriteAllText(
            (Join-Path $sidecars_dir "$entry_id.per_file.txt"),
            $per_file_body,
            (New-Object System.Text.UTF8Encoding($false))
          )
          if (@($info.permission_denied).Count -gt 0) {
            $perm_body = (($info.permission_denied) -join "`n") + "`n"
            [System.IO.File]::WriteAllText(
              (Join-Path $sidecars_dir "$entry_id.permission_denied.txt"),
              $perm_body,
              (New-Object System.Text.UTF8Encoding($false))
            )
          }
          Append-ManifestEntryDirectory $entry_id $abs $info $manifest_path $sidecars_subdir $repoRoot
        } else {
          Append-ManifestEntryFile $entry_id $abs $manifest_path $repoRoot
        }
      } catch {
        Write-Warning "MANIFEST-EMIT FAILED for $abs — $($_.Exception.Message)"
        $failedPaths += [pscustomobject]@{
          path = $abs
          error = "manifest-emit failed: $($_.Exception.Message)"
          error_type = $_.Exception.GetType().FullName
        }
        $count++
        continue
      }
      # iter 8 CLEAN-DELETE-ACL-1 fix: capture failures from permission-denied tmpdirs
      try {
        # iter 20 CLEAN-PS1-LITERALPATH-HARDENING-19 fix: -LiteralPath consistently
        Remove-Item -LiteralPath $abs -Recurse -Force -ErrorAction Stop
        Write-Host "DELETED: $abs (manifest entry: $entry_id)"
        $deletedPaths += $abs
      } catch {
        Write-Warning "FAILED: $abs — $($_.Exception.Message)"
        $failedPaths += [pscustomobject]@{
          path = $abs
          error = $_.Exception.Message
          error_type = $_.Exception.GetType().FullName
        }
      }
    }
    $count++
  }
}

Write-Host ""
Write-Host "Total: $count paths processed"
if ($Mode -eq 'Apply') {
  Write-Host "Deleted: $($deletedPaths.Count); Failed: $($failedPaths.Count)"
  # iter 8 CLEAN-DELETE-ACL-1 fix: write failure manifest for forensic recovery + manual cleanup
  if ($failedPaths.Count -gt 0) {
    $failureManifestPath = Join-Path $repoRoot 'state/polaris_restart/cleanup_delete_failures.txt'
    $failedPaths | ForEach-Object {
      "$($_.path)`t$($_.error_type)`t$($_.error)"
    } | Out-File -FilePath $failureManifestPath -Encoding utf8
    Write-Host "Failure manifest: $failureManifestPath"
    # Non-zero exit so PR-1 review surfaces the failures
    exit 3
  }
}
if ($Mode -eq 'DryRun') {
  Write-Host "DRY RUN — nothing deleted. Re-run with -Mode Apply after Codex APPROVE."
}
```

**iter 8 CLEAN-DELETE-ACL-1 + iter 10 CLEAN-PS1-INIT-IN-BLOCK-1 fix:** the `$deletedPaths = @()` and `$failedPaths = @()` initializers are now INSIDE the fenced script block (before `$count = 0`), so the script is runnable as-pasted with no out-of-band setup. PR-1 review: exit code 3 in Apply mode signals partial failure; manifest at `state/polaris_restart/cleanup_delete_failures.txt` lists each path + error type + message. Codex APPROVE on dry-run transcript first; if Apply produces failures, halt and review failure manifest before proceeding to subsequent cleanup PRs.

**iter 21 CLEAN-PS1-DUPLICATE-SNIPPET-20 fix: the standalone manifest-emit snippet block previously below this paragraph has been REMOVED. The full integrated PowerShell script (with helpers inlined per iter 20) IS the single source of truth; see the canonical fenced block above starting `scripts/cleanup/delete_pytest_tmpdirs.ps1 — Windows/PowerShell canonical`.**

~~iter 12 CLEAN-MANIFEST-DELETE-IMPL-1 fix — pre-delete manifest checksums + Merkle sidecars (OBSOLETE; folded into single integrated script):~~

Before any DELETE in Apply mode, the script generates the manifest entry per §4 schema (size_bytes + sha256 for files; merkle_root_sha256 + per_file_checksums + permission_denied_paths for directories). The integrated script above does this inline.

<!-- iter 21 CLEAN-PS1-DUPLICATE-SNIPPET-20 fix: stale snippet block deleted below.
The functions Get-DirectoryMerkleHash, Append-ManifestEntryDirectory,
Append-ManifestEntryFile + main-loop integration are all inlined in the canonical
script block above. No second copy.

Earlier this position contained ~130 lines of duplicate helper-function code
(iter 13/14/15/16 evolutionary patches) that contradicted iter 20's "single source
of truth" claim. Codex iter 20 CLEAN-PS1-DUPLICATE-SNIPPET-20 caught it. Removed. -->

**iter 21 CLEAN-PS1-DUPLICATE-SNIPPET-20 fix: stale duplicate code removed.** The ~130 lines of helper-function code that previously lived here (iter 13/14/15/16 evolutionary patches) have been DELETED. All helper bodies are inlined in the canonical PowerShell fenced block above (the `scripts/cleanup/delete_pytest_tmpdirs.ps1` block following the `# === Helper functions (iter 20 ...)` marker). The integrated script is the single source of truth.

Manifest entries are appended to `state/polaris_restart/cleanup_manifest.md` BEFORE Remove-Item by the integrated script, so a delete failure preserves the manifest entry for forensic recovery (the source files remain on disk if delete failed). Manifest entries are NEVER rolled back. PR-1 review verifies that the manifest contains entries for ALL Apply-mode paths.

Bash variant (Linux CI, **DRY-RUN ONLY** per iter 15 CLEAN-BASH-MANIFEST-PARITY-1 fix — does not emit pre-delete manifest entries; PowerShell remains canonical for Apply mode):

```bash
# scripts/cleanup/delete_pytest_tmpdirs.sh — same allowlist + checks; Linux-only fallback (iter 5 CLEAN-FENCE-1 fix: removed nested code fence)
#!/usr/bin/env bash
# Allowlist-only DELETE for §3.3-§3.5. Implements --dry-run + resolved-path checks.
# Exits non-zero on any path NOT in allowlist or matching DO-NOT-TOUCH.
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
  --dry-run) ;;
  --apply)
    # iter 15 CLEAN-BASH-MANIFEST-PARITY-1 fix: bash variant is dry-run only.
    # Apply-mode delete must use the PowerShell canonical script which emits manifest entries.
    echo "ERROR: bash variant is DRY-RUN ONLY. Use scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply for real deletes (emits required manifest entries per §4)." >&2
    exit 64
    ;;
  *) echo "Usage: $0 --dry-run" >&2; exit 64;;
esac

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Glob patterns to delete (literal-prefix, may contain trailing wildcards)
ALLOWLIST=(
  ".codex_tmp" ".codex_tmp_*" ".codex_pytest_tmp"
  ".tmp" ".tmp-pytest" ".tmp_pytest" ".tmp_pytest_base"
  ".tmp_pytest_*" ".tmp_walkthrough" ".tmp_md3_review"
  ".tmp_m_prod_1_r2_*" ".pytest_tmp" ".tmp_*"
  "POLARIS.tmppytest" "POLARIStmp_pytest_m_int_3_reviewbasetemp"
  "pytest_run_*" "py_pytest_*" "pytest-cache-files-*"
  "codex_tmp_*" "tmp_*" "tmp[0-9a-z]*"
  "manual_*" "manual_review_scratch_*" "manual_pytest_base_*"
  "manual_tmp_*" "manual_sqlite_dir"
  "m_int_*_manual_*" "m_int_*_v*_manual_*" "m_int_*_probe_*"
  "m9_v*" "m10v*" "m8_*" "md3_*"
  "dashboard_probe_*" "_m1v2_tmp2"
  "m_int_2_main_async_check" "m_int_2_manual_check"
  "m_int_7_concurrency_probe" "m_int_7_main_async_probe"
  "m_int_7_manual_probe" "m_int_7_manual_probe.txt"
  "m_int_10_manual_*" "m_int_11_*manual*" "m_new_race_*" "m_live_4_r2_*"
  "m26_v17_round4_*"
  "jobs_test_probe.sqlite" "m10v2_manual_*.sqlite" "m10v2_ws_probe_*.sqlite"
  "m10v3_*.sqlite" "m_int_11_manual_review_*.sqlite"
  "manual_probe_root.sqlite" "sqlite_probe_root.sqlite"
  "write_probe_root.txt"
  # iter 7 CLEAN-BASH-FALLBACK-2 fix: outputs/* pytest tmpdirs (parity with PowerShell allowlist)
  "outputs/codex_tmp_pytest" "outputs/pytest_basetemp"
  "outputs/pytest_temp" "outputs/pytest_tmp"
)

# DO-NOT-TOUCH: any of these resolved-path prefixes refuses deletion (CLEAN-EXEC-2)
DO_NOT_TOUCH_PREFIXES=(
  "$REPO_ROOT/.git" "$REPO_ROOT/.github"
  "$REPO_ROOT/.env" "$REPO_ROOT/.env.example"
  "$REPO_ROOT/src" "$REPO_ROOT/web" "$REPO_ROOT/tests" "$REPO_ROOT/scripts"
  "$REPO_ROOT/docs" "$REPO_ROOT/config"
  "$REPO_ROOT/state/pg_" "$REPO_ROOT/state/polaris_restart"
  "$REPO_ROOT/archive" "$REPO_ROOT/.private"
  "$REPO_ROOT/outputs/codex_findings" "$REPO_ROOT/outputs/audits"
  "$REPO_ROOT/README.md" "$REPO_ROOT/CLAUDE.md" "$REPO_ROOT/architecture.md"
  "$REPO_ROOT/Dockerfile" "$REPO_ROOT/docker-compose.yml"
  "$REPO_ROOT/pyproject.toml" "$REPO_ROOT/requirements.txt"
)

count=0
for pattern in "${ALLOWLIST[@]}"; do
  for match in $pattern; do
    [[ -e "$match" ]] || continue
    abs="$(realpath "$match")"
    # Resolved-path check (CLEAN-EXEC-2): refuse anything inside DO-NOT-TOUCH
    for dnt in "${DO_NOT_TOUCH_PREFIXES[@]}"; do
      if [[ "$abs" == "$dnt"* ]]; then
        echo "REFUSING $match (resolves to $abs, inside protected $dnt)" >&2
        exit 2
      fi
    done
    if [ "$MODE" = "--dry-run" ]; then
      echo "WOULD DELETE: $match  (resolved: $abs)"
    else
      rm -rfv "$match"
    fi
    count=$((count+1))
  done
done

echo ""
echo "Total: $count paths"
[ "$MODE" = "--dry-run" ] && echo "DRY RUN — nothing deleted. Bash variant is dry-run only (per iter 18 CLEAN-BASH-DRYRUN-MSG-17 fix); use scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply for real Apply."
```

**iter 16 CLEAN-BASH-APPLY-STALE-15 fix:** bash variant is DRY-RUN ONLY (`--apply` rejects with usage error pointing to PowerShell canonical). Cleanup-PR-1 reviews this script's `--dry-run` output for cross-platform sanity check; ALL real Apply-mode work uses `scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply` (PowerShell, with manifest emit). Earlier "before --apply" prose superseded.

### §3.4 Top-level `codex_tmp_*`, `tmp*`, `manual_*`, `m_int_*`, `m9_v*`, `m10v*`, `m8_*`, `md3_*`, `dashboard_probe_*`, `pytest_run_*` (96+ dirs)

All untracked. Same pattern as §3.3.

| Path pattern | Action | Reason |
|---|---|---|
| `codex_tmp_*/` at root (~50 dirs) | D | pytest tmpdirs; permission-denied subfolders confirm stale; zero refs |
| `tmp[0-9a-z]*/`, `tmp_*/` at root | D | pytest tmpdirs |
| `manual_*/`, `manual_review_scratch_*/`, `manual_pytest_base_*/`, `manual_tmp_*/`, `manual_sqlite_dir/` | D | manual probe scratch from prior sessions |
| `m_int_*_manual_*/`, `m_int_*_v*_manual_*/`, `m_int_*_probe_*/` | D | M-INT manual probes |
| `m9_v*/`, `m10v*/`, `m8_*/`, `md3_*/` | D | milestone probe scratch |
| `dashboard_probe_*/` (~5 dirs) | D | dashboard probe scratch |
| `pytest_run_*/`, `py_pytest_*/`, `pytest-cache-files-*/`, `POLARIS.tmppytest/`, `POLARIStmp_pytest_m_int_3_reviewbasetemp/` | D | pytest run output |
| `_m1v2_tmp2/` | D | M-1 v2 tmp2 (note: `_v2` adjective but DELETE so no rename needed) |
| `m_int_2_main_async_check/`, `m_int_2_manual_check/`, `m_int_7_concurrency_probe/`, `m_int_7_main_async_probe/`, `m_int_7_manual_probe/`, `m_int_10_manual_*/`, `m_int_11_*manual*/`, `m_new_race_*/`, `m_live_4_r2_*/` | D | probe scratch |
| `m26_v17_round4_*/` | D | round-4 probe |

### §3.5 Top-level `.sqlite` files (9 untracked)

| Path | Action | Reason |
|---|---|---|
| `jobs_test_probe.sqlite` | D | test probe artifact |
| `m10v2_manual_*.sqlite`, `m10v2_ws_probe_*.sqlite`, `m10v3_case_*.sqlite`, `m10v3_multi_*.sqlite`, `m10v3_norm_*.sqlite` | D | M-10 probe artifacts |
| `m_int_11_manual_review_*.sqlite` | D | M-INT-11 review artifact |
| `manual_probe_root.sqlite`, `sqlite_probe_root.sqlite` | D | manual probe artifacts |

### §3.6 `.private/`

| Path | Action | Reason |
|---|---|---|
| `.private/codex_hmac.key` | K | active HMAC for plan §10.0 verdict signing. **iter 4 CLEAN-PRIVATE-GITIGNORE-1 fix:** Codex confirmed `.gitignore:9` has inline-comment-as-pattern bug rendering rule ineffective. Cleanup-PR-1 step 1 REPLACES `.gitignore:9` with: line 1 = `# Private credentials and HMAC keys` (real comment); line 2 = `.private/` (real rule); then verifies via `git check-ignore .private/codex_hmac.key` returning the path AND `git status --short -- .private` returning empty. |

### §3.7 `docs/` directory

| Path | Action | Reason |
|---|---|---|
| ~~`docs/architecture.md`~~ | (NOT present at reset target) | **iter 12 CLEAN-DOCS-INVENTORY-OMISSION-2 fix:** verified absent at `365f334`. The repo-root `architecture.md` is the foundation file; no `docs/architecture.md` exists. Row removed. |
| `docs/agent_architecture.md` | K | foundation |
| `docs/substrate_audit_2026-05-01.md` | K | foundation |
| `docs/carney_delivery_plan_v6_2.md` | K | foundation |
| `docs/carney_delivery_plan_FINAL.md` | (file does NOT exist at reset target `365f334`) | **iter 8 CLEAN-DOC-RENAME-MISSING-1 + iter 10 CLEAN-PR7-STALE-8FILE-1 fix:** verified absent via `git ls-tree -r --name-only 365f334 docs/`. No `git mv` needed. Cleanup-PR-7 sub-pattern A reduces to reference-substitution in 2 active files (`docs/carney_delivery_plan_v6_2.md` + `state/restart_instructions.md`) — see §5 sub-pattern A touch list. The 6 scripts/tests files in iter 8 attribution belong to `full_online_plan_FINAL` (Cleanup-PR-7 sub-pattern B), NOT to this row. |
| `docs/full_online_plan_FINAL.md` | R → `full_online_plan.md` | **iter 19 CLEAN-FULL-ONLINE-TARGET-VERSIONED-18 fix:** Earlier target `full_online_plan_v4.md` was itself a §4.1 violation (`_v4` adjective). Corrected target = `full_online_plan.md` (no version suffix). Per CLAUDE.md §4.1 "version numbers" forbidden. atomic rename PR updates ALL referencing scripts/tests/.github files. CI gate: `zero_hit_gate.sh "full_online_plan_FINAL"` returns zero hits post-PR. |
| `docs/canonical_pin.txt` | K | **iter 12 CLEAN-PINS-CLASSIFY-1 fix:** Codex iter 11 verified active reset-target use by code/workflows. KEEP. (Plan v6.2 carries forward canonical-pin discipline per CLAUDE.md §1.1 hierarchy.) |
| `docs/blockers.md` | K | foundation |
| `docs/task_acceptance_matrix.yaml` | K | **iter 6 + iter 14 CLEAN-SCHEDULE-STILL-CONTRADICTS-2 fix:** KEEP. Codex iter 4 confirmed matrix is LIVE at reset target `365f334` via `CLAUDE.md`, `.github/CODEOWNERS`, `codex_verdict_check.yml`, `scripts/autoloop/*`. Decommission requires separate **post-Cleanup-PR-8 follow-up PR** (renamed from earlier "post-PR-14") updating all referencing files at once. Until then: KEEP. |
| `docs/file_directory.md` | REGENERATE post-cleanup | will reflect new state |
| `docs/runbook.md` | K | runbook for current pipelines |
| `docs/live_code_audit.md` | K | per memory; static import-closure analysis |
| `docs/m26_threat_model.md` | K | foundation |
| `docs/test_failure_triage_2026-04-27.md` | INSPECT | if V30 issues still listed open, KEEP; else ARCHIVE |
| `docs/phase_d_milestones.md` | INSPECT | if M-D items still live per task tracker, KEEP; else ARCHIVE |
| `docs/server_side_setup.md` | K | server setup reference |
| `docs/handover.md` | NEW (write per plan §9) | will be created post-cleanup |
| `docs/mission_status.md` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-PR-72 doc; not in `365f334`; tag preserves; no cleanup PR action. |
| `docs/demo_runbook.md` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-PR-72 doc; not in `365f334`; no cleanup PR action. |
| `docs/demo_e2e_verification_2026_05_04.md` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-PR-72 doc; not in `365f334`; no cleanup PR action. |
| `docs/compliance/` | K | compliance references |
| `docs/schemas/` | K | tracked at reset target; active schemas including codex_verdict.schema.json. |
| **iter 11 CLEAN-DOCS-INVENTORY-OMISSION-1 fix — tracked docs/ items at reset target previously omitted (verified `git ls-tree --name-only 365f334 docs/`):** | | |
| `docs/backend_modernization.md` | K | tracked at reset target; backend modernization spec for v6 Phase 0 Task 0.5. Active. |
| `docs/benchmark/` (subtree) | K | tracked at reset target; benchmark dir per Carney v6.2 BEAT-BOTH bar. INSPECT subtree contents in future iter. |
| `docs/carney_handover/` (subtree) | K | tracked at reset target; Carney handover dir per Phase 5 deliverable. INSPECT subtree contents in future iter. |
| `docs/carney_delivery_plan_v5_1_redline.md` | K | **iter 12 CLEAN-CARNEY-DRAFT-REFS-1 fix:** Codex iter 11 found active reference from `.codex/codex_red_team_checklist.md` (KEEP per §3.2 foundation). Archiving without atomic ref-update breaks the checklist. KEEP. Separate post-cleanup PR could archive both atomically. |
| `docs/carney_delivery_plan_v5_draft.md`, `_v6_draft.md` | A | `archive/2026-05-05/carney_plan_drafts/` — superseded by v6_2.md. **iter 19 CLEAN-DRAFT-GATE-ORDER-18 fix:** the actual files AND their `.codex/carney_*_review_brief.md` referrers are BOTH archived inside Cleanup-PR-3c (which moves the docs-draft files AND the .codex carney review briefs in the same atomic batch). So the preflight `count_hits.sh 'carney_delivery_plan_v5_draft|carney_delivery_plan_v6_draft' 0` is redundant within PR-3c (the move happens atomically) — instead it runs as a post-PR-3c gate to confirm zero leftover refs. `.legacy/` is do-not-touch immutable (per iter 14 + iter 18 §2 + all gate exclusions). POST-Cleanup-PR-3c expected count = 0 active hits (excluding `.legacy/`). |
| `docs/compliance_templates/` (subtree) | K | tracked at reset target; compliance template dir. INSPECT subtree in future iter. |
| `docs/gemma_4_verification.md` | K | tracked at reset target; v6 Phase 0 Task 0.8 deliverable per task list #121. Active. |
| `docs/hardware_decision.md` | K | tracked at reset target; v6 Phase 0 Task 0.6 deliverable per task list #119. Active. |
| `docs/live_code_audit.json` | K | tracked at reset target; companion to `live_code_audit.md`. Active. |
| `docs/md{1..11}_*_threat_model.md` (~14 files) | K | tracked threat models for M-D series; active per CLAUDE.md threat model coverage. |
| `docs/opentelemetry_genai.md` | K | tracked at reset target; v6 Phase 0 Task 0.10 deliverable per task list #123. Active. |
| `docs/pipeline_audit_context/` (subtree) | K | tracked at reset target; foundational audit context. INSPECT subtree contents (00-11 files referenced in iter 9 honest_sweep section). |
| `docs/pricing_and_positioning.md` | K | tracked at reset target; M-27 deliverable per task list #76. Active. |
| `docs/release_notes_v1.0.md` | K | tracked at reset target; M-PROD-4 deliverable per task list #113. Active. |
| `docs/session_pin.txt` | K | **iter 12 CLEAN-PINS-CLASSIFY-1 fix:** Codex iter 11 verified active use. KEEP alongside `canonical_pin.txt`. |
| `docs/shippable_plan_v2_draft.md`, `_v3_draft.md`, `_v4_draft.md` | A | `archive/2026-05-05/shippable_plan_drafts/` — superseded by current Carney v6.2. ARCHIVE all three. |
| `docs/supported_scope.md` | K | tracked at reset target; M-PROD-4 deliverable per task list #113. Active. |
| `docs/todo_list.md` | K | **iter 12 CLEAN-TODO-ARCHIVE-REFS-1 fix:** Codex iter 11 verified active refs from CLAUDE.md, state/restart_instructions.md, compliance docs/templates, pipeline_audit_context, ground_rules.md, requirements.txt, src/polaris_graph/retrieval/*, tests. Archiving without atomic ref-update would break referrers. Keep as deprecated stub (per CLAUDE.md §1.1 "deprecation stub redirecting"); a separate post-PR-9 atomic ref-update PR can later archive both file and refs together. NOT in cleanup PRs. |
| `docs/walkthroughs/` (subtree) | K | **iter 12 CLEAN-WALKTHROUGHS-CLASSIFY-1 fix:** Codex iter 11 verified active references from `docs/task_acceptance_matrix.yaml` and `tests/v6/test_verdict_gate_substrate_prep.py`. KEEP. |
| `docs/v1_1_backlog.md`, `docs/v1_1_release_notes.md` | K | **iter 12 CLEAN-DOCS-INVENTORY-OMISSION-2 fix:** v1.1 backlog + release notes; tracked at reset target; active per Carney v6.2 phase deliverables. |
| `docs/v6_substrate_audit_2026-05-01.md` | K | **iter 12 CLEAN-DOCS-INVENTORY-OMISSION-2 fix:** v6 substrate audit. KEEP. |

### §3.8 `outputs/` directory

| Path | Action | Reason |
|---|---|---|
| `outputs/audits/codex_audit.jsonl` | K | tracked at reset target; active audit log per plan §10 |
| `outputs/audits/codex_approved_design_2026-05-03_FINAL.md` | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent via `git cat-file -e 365f334:outputs/audits/codex_approved_design_2026-05-03_FINAL.md`. No cleanup PR action; came in post-PR-72; preserved in `pre_restart_2026_05_05` tag. |
| `outputs/audits/codex_consultation_2026-05-03_*.md` (consultation/round/structural files) | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent at `365f334`. No cleanup PR action. |
| `outputs/audits/codex_response_round*.txt` | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent at `365f334`. No cleanup PR action. |
| `outputs/audits/handover_bundles/` | (NOT present at reset target) | **iter 10 CLEAN-INSPECT-RESET-SCOPE-1 fix:** verified absent. No cleanup PR action. |
| `outputs/audits/manifests/5.2.json` | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent. Reset target manifests are: `0.5.json`, `0.8.json`, `0_6_hardware_decision_doc.json`, `3_5_prep_api_benchmark_runner.json`, `bootstrap_smoke.json` (all KEEP per immutable-history policy). |
| `outputs/audits/manifests/0.5.json`, `0.8.json`, `0_6_hardware_decision_doc.json`, `3_5_prep_api_benchmark_runner.json`, `bootstrap_smoke.json` | K | tracked at reset target; KEEP per §3.2 immutability policy. |
| `outputs/audits/pipeline_full_demo/`, `outputs/audits/pipeline_smoke/` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-PR-72 demo evidence; not in `365f334`; no cleanup PR action. |
| ~~`outputs/audits/v25/`, `v26/`, `v27/`~~ | (removed) | **iter 8 CLEAN-OUTPUTS-CONTRADICTION-2 fix:** `v25/` and `v26/` are NOT tracked at reset target. `v27/` is KEEP per §3.2 immutability policy. |
| `outputs/audits/v28/`, `v29/` (tracked subtrees at reset target) | K | iter 10: tracked at reset target per `git ls-tree`; KEEP per immutability. |
| `outputs/audits/v6_2_phase_2_speculative_review_brief.md` | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent. No cleanup PR action. |
| `outputs/audits/verdicts/` (tracked subtree at reset target) | K | iter 10: contains `4_5_prep_drafts/iter_3.json` etc. tracked at reset; KEEP per immutability. Earlier "ARCHIVE 0_3/0_7/3_5/4_5_prep_*" row removed (iter 7 KEEP row in §3.2 supersedes). |
| ~~`outputs/audits/verdicts/5.2/`~~ | (NOT present at reset target) | **iter 10 CLEAN-OUTPUTS-RESET-SCOPE-1 fix:** verified absent. No cleanup PR action. |
| `outputs/audits/briefs/` | (NOT present at reset target) | **iter 10 CLEAN-INSPECT-RESET-SCOPE-1 fix:** verified absent. No cleanup PR action. |
| `outputs/codex_findings/` | K | per CLAUDE.md §5 (tracked exception). **iter 4 CLEAN-OUTPUTS-NESTED-TMP-1 fix:** nested pytest tmpdirs under `outputs/codex_findings/m1_v3_review/pytest_tmp/`, `m28_code_audit_pass3/pytest_basetemp/`, `m8_review/pytest-cache-files-*` are tooling artifacts inside KEEP audit content. Add ripgrep tooling exclusion (`outputs/codex_findings/**/pytest_tmp/`, `outputs/codex_findings/**/pytest_basetemp/`, `outputs/codex_findings/**/pytest-cache-files-*/`) to `.ignore` or `.rgignore` in PR-1 alongside `.gitignore` patch; do NOT delete (audit payload). |
| `outputs/codex_findings/deep_dive_round_{1..7}/` | K | audit trail |
| `outputs/codex_findings/dr_output_pass_*` (~14 rounds) | K | BEAT-BOTH evidence |
| `outputs/codex_findings/autoloop_v2_protocol_review/` | K | autoloop V2 audit |
| `outputs/codex_findings/m_int_*_v*_review/` | K | M-INT review trail |
| `outputs/honest_sweep_*`, `outputs/honest_full_cycle/`, `outputs/honest_live_cycle/`, `outputs/honest_on_prerebuild_corpus/`, `outputs/sweep_r3_final/`, `outputs/full_scale_v30_phase2_run14/` | K | **iter 14 CLEAN-OUTPUTS-COUNT-DRIFT-2 fix:** all TRACKED at reset target — 209 files verified iter 13 via `git ls-tree -r 365f334 outputs/ \| grep -E '^outputs/(honest_\|sweep_r3_final\|full_scale)' \| wc -l = 209`. Stale "198" reference removed. Per §3.2 immutability policy and CLAUDE.md §5 outputs/codex_findings exception (extended): KEEP. Cleanup PRs do NOT archive these. Active docs reference them (CLAUDE.md, README.md, architecture.md, docs/runbook.md, docs/release_notes_v1.0.md, docs/v1_1_backlog.md, docs/pipeline_audit_context/{00,01,02,03,04,07,08,10,11}, docs/file_directory.md, docs/test_failure_triage_2026-04-27.md, scripts/docker_entrypoint.sh — 19+ files); references remain valid since paths are KEEP. **outputs/audits/v28/, v29/, v27/ also tracked → KEEP per same policy.** |
| `outputs/codex_tmp_pytest/`, `outputs/pytest_basetemp/`, `outputs/pytest_temp/`, `outputs/pytest_tmp/` | D | **iter 5 CLEAN-OUTPUTS-TMP-1 fix:** untracked top-level pytest tmpdirs inside `outputs/`. Add to allowlist of `delete_pytest_tmpdirs.ps1` script. Permission-denied subfolder noise excluded from grep gates via `.ignore`/`.rgignore` per §3.8 outputs/codex_findings rule; same exclusion pattern extended to these. |
| `outputs/demo_benchmark/clinical_n10_demo/`, `outputs/demo_benchmark/clinical_demo_one_real/`, `outputs/demo_benchmark/clinical_demo_one_v2/` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-PR-72 demo benchmark output; not in `365f334`; tag preserves; no cleanup PR action. |

### §3.9 `state/` directory

| Path | Action | Reason |
|---|---|---|
| `state/restart_instructions.md` | UPDATE per plan §9 (replace, not move) | new content references Issue queue |
| `state/progress_ledger.jsonl`, `state/last_pointer.json`, `state/orchestrator_status.json` | INSPECT | if Plan v13 deprecated, ARCHIVE; else KEEP |
| `state/halt_*` files (if any) | K | halt audit |
| `state/polaris_restart/` | K | this plan + iter trail |
| `state/active_audit/` | INSPECT each subfolder; KEEP active, ARCHIVE stale |
| `state/active_pending.json` | INSPECT | if Plan v13 deprecated, drain |
| `state/pg_*.sqlite` (large runtime caches, 3.2 GB) | K | gitignored runtime; do not touch unless backup made; per do-not-touch §2 |
| `state/m_int_10_manual_probe.sqlite`, `state/manual_probe.sqlite`, `state/m10v2_manual_*.sqlite`, similar smaller probe sqlites | (untracked at reset target) | **iter 11 CLEAN-STATE-RUNTIME-ABSENT-1 fix:** these were untracked runtime sqlites; not part of cleanup scope (gitignored runtime data). |
| `state/billing_quota.sqlite`, `state/contract_drafts.sqlite`, `state/decision_records.sqlite`, `state/freshness_alerts.sqlite`, `state/pg_batch_progress.sqlite`, `state/pg_campaigns.sqlite` | (untracked at reset target — gitignored runtime) | **iter 11 CLEAN-STATE-RUNTIME-ABSENT-1 fix:** these are gitignored runtime sqlites (state/ ignored in .gitignore). They were INSPECT'd in iter 4 for active references in code; references DO exist (so when at runtime, files are created); but the FILES themselves are untracked, so cleanup PRs cannot touch them via git. Renaming the row from "KEEP" to "untracked at reset target" matches the actual git state. |
| **iter 11 CLEAN-STATE-INVENTORY-OMISSION-1 fix — tracked state/ items at reset target (verified by `git ls-tree -r 365f334 state/`):** | | |
| `state/autoloop_handover_2026-04-19.md`, `state/autoloop_handover_2026-04-20.md`, `state/autoloop_handover_2026-04-20_TOPTIER.md`, `state/autoloop_handover_2026-04-20_current.md`, `state/autoloop_handover_2026-04-20_v13_milestone.md`, `state/autoloop_handover_2026-04-22_v28_launch.md`, `state/autoloop_handover_2026-04-22_v29_entry.md`, `state/autoloop_handover_2026-04-23_v29_running.md` | A | `archive/2026-05-05/state_autoloop_handovers/` — 8 prior-session autoloop handover docs; superseded by current Carney v6.2 plan + per-Issue flow. **CLAUDE.md §4.1 violations:** `_TOPTIER` (adjective), `_current` (adjective), `_v13_milestone`, `_v28_launch`, `_v29_entry`, `_v29_running` — but ARCHIVE'd not RENAMED so adjective renames not needed. |
| `state/compare_chatgpt_dr.txt`, `state/compare_gemini_dr.txt` | K | active BEAT-BOTH comparison artifacts referenced from per memory `autoloop_full_scale_launcher_pattern` and `autoloop_beat_tier1_mandate`. Verify references at PR time; default KEEP. |
| `state/v17_vs_tier1_headtohead.md` | K | V17 head-to-head record per memory `autoloop_beat_tier1_mandate`; KEEP as historical comparison. |
| `state/restart_instructions.md` | UPDATE per plan §9 (replace, not move) | new content references Issue queue; same row as §3.9 top entry. |
| `state/we_control/` | does NOT exist | confirmed clean |
| `state/neuron_session/` | does NOT exist | confirmed clean |

### §3.10 `scripts/` directory (219 files at reset target `365f334`; CLAUDE.md §5 stale "130 scripts" line is reset-pre-cleanup; **iter 11 CLEAN-SCRIPTS-COUNT-1 fix:** verified count via `git ls-tree -r 365f334 scripts/ | wc -l = 219`. CLAUDE.md will be updated in PR-B DNA pass to reflect post-cleanup count.)

**iter 11 CLEAN-CLAUDE-SETTINGS-1 fix — `.claude/` tracked items at reset target (3 files, verified `git ls-tree -r 365f334 .claude/`):**

| Path | Action | Reason |
|---|---|---|
| `.claude/settings.json` | K | tracked at reset target; project-scoped Claude Code settings per memory `stop_hook_must_be_project_scoped`. Active. Cleanup PRs do NOT touch. |
| `.claude/hooks/precommit_codex_verdict.py` | INSPECT | tracked at reset target; previously assumed under "scripts/hooks" — corrected per iter 5 CLEAN-STALE-PATHS-1. Plan §10.0 mechanical gates may replace; verify in future iter. |
| `.claude/hooks/stop_hook_v3.py` | INSPECT | tracked at reset target; Plan-v13-era stop hook. Plan §10.0 mechanical gates may replace; verify in future iter. |

| Path pattern | Action | Reason |
|---|---|---|
| `scripts/run_honest_sweep_r3.py` | K | active per CLAUDE.md §5 (Pipeline A) |
| `scripts/live_server.py` | K | active (Pipeline B) |
| `scripts/full_cycle.py` | K (frozen) | per CLAUDE.md §5 (Pipeline C frozen) |
| `scripts/pg_preflight_v2.py` | R → `scripts/pg_preflight.py` | CLAUDE.md §4.1 `_v2`. **iter 11 CLEAN-REN-ROW-STALE-1 fix:** atomic rename PR updates ALL 7 active files at reset target (full list aligned with §5 PR-6 authoritative list): `CLAUDE.md`, `docs/compliance/soc2_evidence_map.md`, `docs/file_directory.md`, `docs/pipeline_audit_context/08_env_var_inventory.md`, `ground_rules.md`, `scripts/docker_entrypoint.sh`, `scripts/pg_preflight_v2.py` (rename target + 3 self-refs). `logs/session_log.md` excluded per immutable-history policy. CI gate: `zero_hit_gate.sh "pg_preflight_v2"` returns no remaining hits in active tree. Verification: `docker compose run preflight` smoke test passes post-rename. |
| `scripts/audit_live_code.py` | K | static import-closure analysis |
| `scripts/codex_loop_parse.py` | K | Codex verdict parser |
| `scripts/run_audit.py`, `scripts/run_r6_validation.py` | K | active sweep tools |
| `scripts/screenshot_walkthrough.js`, `scripts/screenshot_benchmark.js`, `scripts/seed_demo_benchmark.py`, `scripts/demo_smoke.py`, `scripts/setup_gpg_for_demo.py`, `scripts/verify_audit_bundle_e2e.py`, `scripts/provision_vast_dev_cluster.py`, `scripts/run_benchmark.py` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** these post-drift scripts came in via slice 002-005 PRs and do NOT exist at reset target `365f334`. ROAD B reset is the archival mechanism — `pre_restart_2026_05_05` tag preserves them for forensic recovery. NO cleanup PR touches these paths. Earlier iter rows said "ARCHIVE" → corrected: not present at reset target; no cleanup PR action needed. README references that pointed at these scripts are also reset-removed (not in `365f334`). |
| `scripts/autoloop/*` (FIXED iter 3 CLEAN-PATH-1: real path is `autoloop` not `autopilot`) | INSPECT | if Plan v13 abandoned per plan §2, ARCHIVE; else KEEP |
| `.claude/hooks/*` (FIXED iter 3 CLEAN-PATH-1: real path is `.claude/hooks` not `scripts/hooks`) | INSPECT | will be replaced by §10 mechanical gates per plan §9.6a |
| Other scripts (~100) | INSPECT individually in iter 2 | many are one-off probes per CLAUDE.md §5 |

### §3.11 `tests/` directory

| Path | Action | Reason |
|---|---|---|
| `tests/polaris_graph/` (305 tests) | K | active substrate |
| `tests/polaris_graph/golden/test_slice_001_goldens.py` | K | per CHARTER §4 immutable |
| `tests/polaris_graph/golden/test_slice_00{2,3,4,5}_goldens.py` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** slice 002-005 golden runners came in via post-PR-72 slice work; do NOT exist at `365f334`. Tag `pre_restart_2026_05_05` preserves them. NO cleanup PR action. |
| `tests/polaris_graph/benchmark/test_run_benchmark_cli.py`, `test_seed_demo_benchmark.py` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** post-drift tests; not in reset target; tag preserves; no cleanup PR action. |
| `tests/polaris_graph/test_demo_smoke.py`, `test_setup_gpg_for_demo.py`, `test_provision_vast_dev_cluster.py` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** same — not in reset target; no cleanup PR action. |
| `tests/polaris_graph/scope/test_default_llm_completion_async_fix.py` | (NOT present at reset target) | **iter 9 CLEAN-STALE-NOOP-ROWS-1 fix:** PR #79 fix reverts under ROAD B; this test came in with the fix; not at reset target; reissued as I-bug-079 in issue_breakdown.md. NO cleanup PR action. |
| `tests/v6/` | K | **iter 21 CLEAN-TESTS-V6-STALE-INSPECT-20 fix:** §2 do-not-touch list classifies all `tests/*` as KEEP (per iter-12 CLEAN-TESTS-INVENTORY-OMISSION-2). This row aligned to §2. tests/v6/ is active per Phase 0 backend coverage (see CLAUDE.md). |

### §3.12 `web/` directory

| Path | Action | Reason |
|---|---|---|
| `web/app/`, `web/components/`, `web/lib/`, `web/tests/`, `web/public/`, `web/styles/`, `web/CLAUDE.md`, `web/AGENTS.md` | K | active frontend; updated per plan §9.2 |
| `web/.next/` | (untracked at reset target — gitignored build output) | **iter 16 + iter 21 CLEAN-WEB-SCHEDULE-STALE-20 fix:** if untracked (typical), no cleanup PR action. If somehow tracked, separate manual cleanup PR needed (not in canonical 10-PR schedule, post-Cleanup-PR-8 follow-up). |
| `web/node_modules/` | K (gitignored, untouched) | not part of cleanup scope |
| `web/test-results/` | (untracked at reset target — gitignored Playwright output) | **iter 16 CLEAN-DELETE-ACTION-UNSCHEDULED-15 fix:** Playwright run artifacts; gitignored. No cleanup PR action. If found tracked at reset, requires separate cleanup PR. |
| `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`, etc | K | manifests |

### §3.13 `archive/` directory (existing)

All entries KEEP — this IS the destination. New `archive/2026-05-05/` subdirectories created by this cleanup land here.

### §3.14 `.github/` directory

| Path | Action | Reason |
|---|---|---|
| `.github/workflows/codex_verdict_check.yml` | INSPECT | likely deprecated by new `polaris/codex-required.yml` per plan §10.1 |
| `.github/workflows/legacy_protection.yml` | K | active legacy-protection CI gate |
| `.github/workflows/m_live_4_regression_gate.yml.pending_workflow_scope` | INSPECT | non-standard `.pending_workflow_scope` extension; either activate (rename to `.yml`) or archive |
| `.github/workflows/protection_drift_check.yml` | K | active |
| `.github/workflows/web_ci.yml` | K | active web CI |
| `.github/CODEOWNERS` | UPDATE per plan §10.0 (replace) | new content per plan |

### §3.15 Other top-level dirs

| Path | Action | Reason |
|---|---|---|
| `__pycache__/` | (untracked at reset target — gitignored Python build cache) | **iter 16 CLEAN-DELETE-ACTION-UNSCHEDULED-15 fix:** standard Python cache; gitignored. No cleanup PR action; can be deleted locally via `find . -name __pycache__ -exec rm -rf {} +` outside any PR. |
| `chromadb_data/` (if exists) | K | gitignored runtime data |

---

## §4 Provenance manifest schema (plan §8.0a) — iter 2 fixes CLEAN-ARCHIVE-1 + CLEAN-MANIFEST-1

**iter 13 CLEAN-GITIGNORE-INLINE-COMMENT-3 fix (REVISED gitignore semantics + inline-comment bug):** `state/` excludes the directory itself. Per `gitignore(5)`: "It is not possible to re-include a file if a parent directory of that file is excluded." So my iter-11 patch (just adding `!state/polaris_restart/` after `state/`) would NOT work — the parent `state/` rule swallows everything underneath. ALSO: gitignore only treats `#` as a comment AT LINE START — inline trailing comments are part of the pattern and break the rule (same class as iter-4 `.private/` inline-comment bug). Comments MUST live on their own lines.

Correct pattern requires excluding `state/*` (children, not the dir itself), then re-including the audit substrate path, with comments on dedicated lines:

```gitignore
# Cleanup-PR-1 .gitignore patch — REPLACE the bare `state/` line with this block:
# (was: line 1 = `state/`)
# Ignore all CHILDREN of state/ (runtime data) but allow the audit substrate
state/*
!state/polaris_restart/
!state/polaris_restart/**
```

Note: `state/*` (with trailing slash-star) leaves `state/` itself NOT excluded, so the negation can re-include children. `state/` (bare) excludes the directory and prevents any re-include. ALL gitignore comment lines start with `#` at column 0; no inline trailing comments anywhere in the patch.

Verification (run as smoke test in PR-1 CI):
- `git check-ignore state/polaris_restart/cleanup_manifest.md` → returns empty (file is NOT ignored, can be tracked)
- `git check-ignore state/polaris_restart/cleanup_manifest_sidecars/sample.txt` → returns empty
- `git check-ignore state/pg_checkpoints.sqlite` → returns `state/pg_checkpoints.sqlite` (still ignored — runtime data)
- `git check-ignore state/some_random_runtime.json` → returns the path (still ignored)

This applies to both the cherry-pick state-restart commit AND Cleanup-PR-1's `.gitignore` patch (consistency — cherry-pick MUST already have the corrected `state/*` + unignore lines so the cleanup manifest stays tracked across the reset).

**iter 2 CLEAN-ARCHIVE-1 fix:** `archive/` is gitignored (`.gitignore` line 59). The manifest cannot live there if it is to be tracked. Two solutions, plan picks one:

(A) Move manifest to a TRACKED path: `state/polaris_restart/cleanup_manifest.md` (alongside this audit). Archive content stays gitignored under `archive/2026-05-05/`. Each cleanup PR commits ONLY the manifest update (tracked) + leaves the actual archive payloads on local disk gitignored — preserves audit trail in git, doesn't bloat the repo with archive copies of files git already has in history.

(B) `git add -f archive/2026-05-05/manifest.md` in each cleanup PR + force-add intended payloads. Bloats repo (36 GB+ of archive content already on disk).

**Recommendation: (A).** Manifest at `state/polaris_restart/cleanup_manifest.md` (tracked). Archive payloads stay local-only gitignored. Manifest cross-references git history (`last_committed_sha`) so original content recoverable from git for tracked items, and from local archive for untracked items.

**iter 2 CLEAN-MANIFEST-1 fix:** add `size_bytes` and `sha256` per entry for forensic integrity:

Every move/rename/delete in §3 generates one entry in `state/polaris_restart/cleanup_manifest.md` with this YAML schema:

```yaml
- path: <original_path>
  action: ARCHIVE | DELETE | RENAME
  destination: <new_path or null for DELETE>
  reason: <one-line>
  references_grep: <count>
  last_modified: <git_log_iso_date or "untracked">
  last_committed_sha: <commit_short or "untracked">
  size_bytes: <int>            # iter 2 CLEAN-MANIFEST-1: file size at time of move
  sha256: <hex>                 # iter 2 CLEAN-MANIFEST-1: SHA256 of content at time of move (or "directory" for dirs; recursive Merkle root if needed)
  evidence_chain:
    drafted_by: claude | codex | user | shared
    drafted_in_session: <session_id_or_date>
    referenced_in_plan: <plan_section>
  cleanup_pr: <PR number when executed>
  codex_audit_verdict: APPROVE
```

DELETE entries: `action=DELETE`, `destination=null`, `size_bytes` and `sha256` recorded BEFORE deletion when feasible.
ARCHIVE entries: `destination` relative to repo root (e.g., `archive/2026-05-05/codex_briefs_milestones_m1_to_m26/m1_audit_ir_review_brief.md`).
RENAME entries: `destination` is new path; both old and new SHAs recorded so reference-update PR can be verified.

**iter 5 CLEAN-MANIFEST-RENAME-1 fix:** RENAME schema requires TWO checksum fields:

```yaml
- entry_id: ren_NNN
  path: <old_path>
  action: RENAME
  destination: <new_path>
  size_bytes: <int>
  sha256_old: <hex>          # pre-rename content SHA
  sha256_new: <hex>          # post-rename content SHA (must match if content unchanged; differs only when reference-substitution happened in same PR per atomic-rename rule)
  reference_update_count: <int>  # number of files whose references were updated in same PR
  reference_files_updated: [list of paths]
  ...
```

If `sha256_old == sha256_new`, rename was content-identity-preserving. If different, the same PR also updated content (e.g., self-references in the renamed file). Both old/new SHAs MUST be recorded for forensic traceability.

**iter 3 CLEAN-MANIFEST-2 + iter 4 CLEAN-MANIFEST-SIDECAR-1 fix (directory entries):** instead of literal `"directory"` for `sha256`, directory entries record `entry_id` (unique per manifest entry, e.g., `arch_001`, `arch_002`) plus full forensic schema:

```yaml
- entry_id: <arch_NNN | del_NNN | ren_NNN>  # iter 4 CLEAN-MANIFEST-SIDECAR-1: unique manifest entry ID
  path: <directory_path>
  action: ARCHIVE | DELETE
  destination: <new_path or null>
  size_bytes: <recursive total bytes>
  recursive_file_count: <int>
  permission_denied_count: <int>          # Windows ACL stale subfolders
  permission_denied_paths: [list]          # truncated to first 20 entries
  permission_denied_sidecar_path: state/polaris_restart/cleanup_manifest_sidecars/<entry_id>.permission_denied.txt  # full list when count > 20
  merkle_root_sha256: <hex>                # iter 15 CLEAN-MERKLE-SCHEMA-SEMANTICS-1 fix: SHA256 of the deterministic text body `<rel_path>\t<file_sha256>\n` for files sorted by rel_path (same content as the per_file sidecar). Implementation note: this is NOT a tree-Merkle (no internal nodes); a flat SHA256 of the sorted manifest. Sufficient for forensic detection (any file change → different hash). Deterministic across re-runs assuming filesystem ordering stable.
  per_file_checksums_sha256: <hex>         # iter 15 fix: SHA256 of the same `<rel_path>\t<file_sha256>\n` body. INTENTIONALLY equal to merkle_root_sha256 in current implementation — kept as separate field for schema clarity. If a future implementation computes a true tree-Merkle for merkle_root_sha256, this field stays as the flat SHA256 and the two diverge.
  per_file_checksums_sidecar_path: state/polaris_restart/cleanup_manifest_sidecars/<entry_id>.per_file.txt  # full per-file list
  unreadable_marker: <bool>               # true if permission_denied_count > 0
  ...
```

Permission-denied subfolders (Windows ACL artifacts seen on stale pytest tmpdirs) are accounted in `permission_denied_count` + listed in adjacent file. The merkle_root computes only over readable files; an `unreadable_marker` flag is set if `permission_denied_count > 0`. This ensures forensic integrity while accepting that some Windows-orphaned subfolders cannot be checksummed without elevated privileges.

---

## §5 Execution sequencing (FIXED iter 4 — ordering relative to ROAD B reset CRITICAL)

**iter 4 ordering invariant (resolves CLEAN-SLICE-PROVENANCE-1 + CLEAN-BENCHMARK-CONTRACT-1 + CLEAN-WALKTHROUGH-SEQ-1):** All cleanup PRs run AFTER ROAD B reset to `365f334`. After the reset, the `polaris` branch HEAD has NONE of the slice 002-005 backend code, NONE of the post-drift scripts, NONE of the post-drift docs, and NONE of the walkthrough screenshot dirs from sessions after slice 001. The src/web/scripts references that Codex flagged ARE in current `polaris` HEAD (`7e96a53`) but ARE NOT in the reset target (`365f334`) — they came in via slice 002-005 PRs.

This means the cleanup audit's archival classifications for slice-002-005-era artifacts (architecture_proposal.md, demo scripts, walkthrough screenshots, post-drift docs) only need to handle items that EXIST on the reset branch — which is essentially: prior-session `.codex/` briefs, `archive/` snapshots, untracked tmpdirs, and `tests/polaris_graph/golden/test_slice_001_goldens.py` (KEEP per §2). The archival of post-reset items happens via the existing tag `pre_restart_2026_05_05` which Codex iter 4 plan APPROVE created — that tag preserves the pre-reset state including all flagged refs.

Net effect: ROAD B reset is itself the archival mechanism for slice-002-005 code. Cleanup-PR-N do NOT need to atomic-update those references because the reset already removed them.

**Pre-reset invariant check (added iter 4 + iter 5 fixes):**

Before ROAD B reset, the user OR an authorized PR (per §10.0) MUST:
1. Create tag `pre_restart_2026_05_05` at current HEAD `7e96a53` (preserves all post-drift work for forensic recovery). **iter 5 CLEAN-RESET-TAGS-1 fix:** tags do not exist yet; verification step pre-cleanup checks `git rev-parse pre_restart_2026_05_05` returns `7e96a53`. If tag absent: HALT, do not reset.
2. Tag all post-drift branches as `archived/<branch>_2026_05_05` (per plan §7.D). Verification: `git tag -l 'archived/*_2026_05_05'` count >= 12 (matching post-PR-72 branch count).
3. **iter 5 CLEAN-RESET-STATE-1 + iter 8 CLEAN-CHERRYPICK-STUB-1 fix:** `state/polaris_restart/` directory does NOT exist at `365f334`. Reset wipes the audit + plan + manifest path. Solution: between steps 2 and 4, create a one-commit cherry-pick `state-restart-cherry-pick` branch off `365f334` whose content is:

   - `state/polaris_restart/plan.md` (Codex-APPROVE'd at iter 4)
   - `state/polaris_restart/issue_breakdown.md` (Codex-APPROVE'd at iter 4)
   - `state/polaris_restart/cleanup_audit.md` (this file, Codex-APPROVE'd target)
   - `state/polaris_restart/codex_verdict_plan_iter_*.txt` (full iter 1-4 trail)
   - `state/polaris_restart/codex_verdict_issue_breakdown_iter_*.txt` (full iter 1-4 trail)
   - `state/polaris_restart/codex_verdict_cleanup_iter_*.txt` (full iter 1-N trail at APPROVE)
   - `state/polaris_restart/iteration_trajectory.md`
   - `state/polaris_restart/cleanup_manifest.md` (**iter 8 CLEAN-CHERRYPICK-STUB-1 fix:** NOT empty; stub with full schema header so PR-1 has a stable target to append to). Stub content (Codex-APPROVE'd as part of cherry-pick):

     ```yaml
     # POLARIS cleanup manifest (state/polaris_restart/cleanup_manifest.md)
     # Created: 2026-05-05 cherry-pick (state-restart-cherry-pick branch off 365f334)
     # Schema: see state/polaris_restart/cleanup_audit.md §4
     # Each cleanup PR appends entries; entries are immutable post-merge.
     #
     # Schema reference (full schema in §4):
     #   - entry_id: <arch_NNN | del_NNN | ren_NNN>
     #     path: <original_path>
     #     action: ARCHIVE | DELETE | RENAME
     #     destination: <new_path or null>
     #     reason: <one-line>
     #     references_grep: <count>
     #     last_modified: <iso_date>
     #     last_committed_sha: <commit_short>
     #     size_bytes: <int>
     #     sha256: <hex>            # for files; merkle_root_sha256 for dirs
     #     evidence_chain: { drafted_by, drafted_in_session, referenced_in_plan }
     #     cleanup_pr: <PR number when executed>
     #     codex_audit_verdict: APPROVE
     #
     # RENAME entries additionally include sha256_old, sha256_new, reference_update_count, reference_files_updated.
     # Directory ARCHIVE/DELETE entries additionally include recursive_file_count,
     # permission_denied_count, permission_denied_paths, permission_denied_sidecar_path,
     # merkle_root_sha256, per_file_checksums_sha256, per_file_checksums_sidecar_path,
     # unreadable_marker.

     # iter 9 CLEAN-MANIFEST-STUB-2 fix: use empty-block YAML form so PRs can
     # append `- <entry>` items without rewriting the stub. `entries: []`
     # would force PR-1 to rewrite the line; `entries:` followed by indented
     # list items is append-friendly.
     entries:
       # Cleanup-PR-1 appends first entry here (delete script run + .gitignore patch).
       # Subsequent PRs append below in execution order.
     ```

   Reset target then becomes the cherry-pick HEAD, NOT raw `365f334`. This preserves the audit substrate across the reset boundary AND ensures PR-1 has a Codex-APPROVE'd stable schema target to append to.
4. Reset `polaris` branch to the cherry-pick HEAD (NOT `365f334` directly). Force-push.
5. Then run cleanup PRs against the reset+cherry-picked branch.

**iter 5 verification chain:**
- Pre-reset: verify (1) and (2)
- Reset prep: verify cherry-pick HEAD contains `state/polaris_restart/plan.md` (Codex-APPROVE'd content)
- Post-reset: verify `git log` shows cherry-pick commit on top of `365f334`; `state/polaris_restart/` is present

---

Cleanup is NOT one PR. Per plan §10 (CHARTER §3 200-LOC cap on PRs translated to file-count cap for moves) and to enable per-batch Codex audit, cleanup splits into N PRs. **All run AFTER ROAD B reset.**

Cleanup is NOT one PR. Per plan §10 (CHARTER §3 200-LOC cap on PRs translated to file-count cap for moves) and to enable per-batch Codex audit, cleanup splits into N PRs.

**iter 3 ordering rule:** any PR that archives a draft/script ALSO archives the tests/docs that depend on it in the SAME PR. No silent-skip windows. CLEAN-GOLDEN-SEQ-1 (golden_drafts archived before slice-2-5 test runners) and CLEAN-SCRIPT-1 (post-drift scripts split from their tests) both broke this rule and are fixed:

1. **Cleanup-PR-1 (preconditions + delete)**: First, `.gitignore` patch adds `.private/` line per §3.6 CLEAN-PRIVATE-GITIGNORE-1 fix + `state/*` + `!state/polaris_restart/**` per iter-13 CLEAN-GITIGNORE-INLINE-COMMENT-3 fix. Then runs **`scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode DryRun`** (PowerShell on Windows, canonical). Codex APPROVE on dry-run transcript, then `-Mode Apply`.

  **iter 13 CLEAN-PR1-STAGED-FILES-OMISSION-1 fix — complete PR-1 staged-files list:**
  - (a) `.gitignore` patch (state/* + unignore lines + .private/ fix; per CLEAN-GITIGNORE-INLINE-COMMENT-3)
  - (b) `scripts/cleanup/delete_pytest_tmpdirs.ps1` (new, with full Get-DirectoryMerkleHash + manifest emit per iter-13 CLEAN-MANIFEST-DELETE-IMPL-2)
  - (c) `scripts/cleanup/delete_pytest_tmpdirs.sh` (new, bash variant Linux fallback)
  - (d) `scripts/cleanup/zero_hit_gate.sh` (new, post-rename gate per iter-12 §5)
  - (e) `scripts/cleanup/count_hits.sh` (new, preflight count per iter-11 §5)
  - (f) `scripts/cleanup/gate_allowlists/.gitkeep` (new, empty dir for per-pattern allowlists)
  - (g) `.github/workflows/cleanup_pr_dependency_recorder.yml` (new, dependency-JSON populator)
  - (g2) **iter 18 + iter 19 CLEAN-DEPS-ANCESTRY-STILL-INCOMPLETE-18 fix:** `.github/workflows/cleanup_pr_ancestry_check.yml` (new). Concrete workflow body:

    ```yaml
    name: cleanup_pr_ancestry_check
    on:
      pull_request:
        types: [opened, synchronize]
        branches: [polaris]
    jobs:
      verify_predecessor_merged:
        if: startsWith(github.event.pull_request.head.ref, 'cleanup/pr-')
        runs-on: ubuntu-latest
        steps:
          # iter 20 CLEAN-ANCESTRY-SHALLOW-CHECKOUT-19 fix: full history needed for
          # `git merge-base --is-ancestor` to find predecessor merge SHA.
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0
          - name: extract_pr_id
            id: pr
            run: |
              head_ref="${{ github.event.pull_request.head.ref }}"
              pr_id=$(echo "$head_ref" | sed -E 's|^cleanup/pr-([0-9]+[a-z]?).*|\1|')
              echo "id=$pr_id" >> $GITHUB_OUTPUT
          - name: lookup_predecessor
            id: pred
            run: |
              # Linear DAG: 1 → 2 → 3a → 3b → 3c → 4 → 5 → 6 → 7 → 8
              declare -A PRED=( [2]=1 [3a]=2 [3b]=3a [3c]=3b [4]=3c [5]=4 [6]=5 [7]=6 [8]=7 )
              cur="${{ steps.pr.outputs.id }}"
              pred="${PRED[$cur]:-none}"
              if [ "$pred" = "none" ]; then
                echo "PR-1 has no predecessor"
                echo "skip=true" >> $GITHUB_OUTPUT
              else
                echo "predecessor=$pred" >> $GITHUB_OUTPUT
                echo "skip=false" >> $GITHUB_OUTPUT
              fi
          - name: verify_ancestry
            if: steps.pred.outputs.skip != 'true'
            run: |
              pred="${{ steps.pred.outputs.predecessor }}"
              pred_sha=$(jq -r ".pr${pred}_merge_commit_sha // empty" state/polaris_restart/cleanup_pr_dependencies.json)
              if [ -z "$pred_sha" ]; then
                echo "ERROR: predecessor PR-${pred} merge SHA not yet recorded — wait for deps recorder bot-PR to merge"
                exit 1
              fi
              if ! git merge-base --is-ancestor "$pred_sha" HEAD; then
                echo "ERROR: predecessor PR-${pred} ($pred_sha) is NOT in current PR's ancestry"
                exit 1
              fi
              echo "OK: PR-${pred} ($pred_sha) is in ancestry"
    ```

    Required CI check on PR-3a..PR-8 head refs `cleanup/pr-*`. Job reads `state/polaris_restart/cleanup_pr_dependencies.json` for the previous PR's merge SHA and verifies it's in current PR's ancestry. Fails fast if previous PR not yet merged. PR-1 has no predecessor (skip step). Linear DAG hardcoded in `PRED` map.
  - (h) `.ignore` (new) AND `.rgignore` (new) — both contain `outputs/codex_findings/**/pytest_tmp/`, `outputs/codex_findings/**/pytest_basetemp/`, `outputs/codex_findings/**/pytest-cache-files-*/` exclusions for ripgrep gates per §3.8
  - (i) `state/polaris_restart/cleanup_manifest.md` initial entries (the cherry-pick stub gets the first DELETE entries appended)
  - (j) `state/polaris_restart/cleanup_pr_dependencies.json` (new, empty `{}` initial — recorder workflow will append)
  - (k) **iter 21 CLEAN-PR1-STAGED-LIST-SIDECAR-20 fix:** `state/polaris_restart/cleanup_manifest_sidecars/.gitkeep` (matches canonical schedule entry; tracks the sidecar dir from PR-1 onward).
**iter 18 CLEAN-SCHEDULE-ACTIVE-STALE-17 fix:** Final schedule = **10 PRs** per canonical §6 table: Cleanup-PR-1, Cleanup-PR-2, Cleanup-PR-3a, Cleanup-PR-3b, Cleanup-PR-3c, Cleanup-PR-4, Cleanup-PR-5, Cleanup-PR-6, Cleanup-PR-7, Cleanup-PR-8. Earlier "8 PRs" (iter 15) and "9 PRs" (iter 11/12) prose is superseded by iter-17 PR-3 split.
**Cleanup-PR-4 (atomic RENAME `_v2` protocol files; renumbered from PR-5 per iter 15)**: `.codex/REVIEW_BRIEF_FORMAT_v2.md` + `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` renames PLUS update of ACTIVE referencing files only — see iter-8 8-file authoritative list (`stop_hook_v3.py`, `CLAUDE.md`, `canonical_pin.txt`, `codex_verdict.schema.json`, `autoloop/orchestrator.py`, `strip_changelog_markers.py`, `polaris_v6/memory/store.py`, `test_workspace_memory.py`). `outputs/audits/continuous/` is historical immutable payload, EXCLUDED from rename gates per the canonical gate spec. **iter 8 canonical gate spec (CI-safe, fixes iter 6/7 CLEAN-GATE-EXEC-1 + CLEAN-GATE-COMMENT-2):**

```bash
#!/usr/bin/env bash
# scripts/cleanup/zero_hit_gate.sh — CI-safe rename-completeness gate
# iter 11 CLEAN-BASH-VERSION-1 fix: requires Bash 4+ for associative arrays.
# Document hard runtime requirement.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ]; then
    echo "ERROR: zero_hit_gate.sh requires Bash 4+ (assoc arrays). Got: $BASH_VERSION" >&2
    exit 64
fi
set -euo pipefail
PATTERN="$1"
# iter 11 CLEAN-GATE-ERRMASK-1 fix: explicit exit-code handling.
# git grep returns 0 on hits, 1 on no matches, 2+ on real errors (bad regex,
# bad pathspec, repo issue). Earlier `|| true` masked all failures including
# bad-pathspec false-passes. Now distinguish:
set +e
OUTPUT=$(git grep -n -E "$PATTERN" -- \
    ':!archive/' \
    ':!state/polaris_restart/' \
    ':!outputs/audits/' \
    ':!outputs/codex_findings/' \
    ':!.codex/_archive_pre_v6_2/' \
    ':!.codex/continuous/' \
    ':!.codex/round_*/' \
    ':!.codex/deep_dive_round_*/' \
    ':!logs/session_log.md' \
    ':!.legacy/' \
    2>&1)
RC=$?
set -e
case $RC in
    0) ;;          # hits found — process normally below
    1) OUTPUT="" ;;  # no matches — pass through as empty
    *)
        echo "ERROR: git grep failed (rc=$RC). Output: $OUTPUT" >&2
        exit $RC
        ;;
esac
# iter 8 CLEAN-GATE-COMMENT-2 fix: do NOT strip generic # lines.
# Markdown headings, multiline-string boundaries, YAML refs in comments,
# Python docstrings — none of these are "harmless" by virtue of starting with #.
# An old-name reference in a Markdown heading or a Python comment is STILL stale
# and STILL fails the rename-completeness gate. Codex iter 7 identified this:
# the iter 7 spec wrongly false-passed `^[^:]*:[0-9]+:[[:space:]]*#` lines.
#
# If a specific occurrence MUST be allowlisted (e.g., a literal historical
# string in a docs/file_directory.md table row that documents the rename), it
# must be added to a per-pattern allowlist file at `scripts/cleanup/gate_allowlists/<pattern>.txt`.
# iter 9 CLEAN-GATE-ALLOWLIST-1 fix: convention is `path:line:` (trailing colon) —
# matches the `git grep -n` output format `<path>:<line>:<content>` exactly.
# Each allowlist entry must include the trailing colon to anchor on the line boundary.
PATTERN_SLUG=$(echo "$PATTERN" | tr -c '[:alnum:]_' '_' | head -c 64)
ALLOWLIST_FILE="scripts/cleanup/gate_allowlists/${PATTERN_SLUG}.txt"
if [ -f "$ALLOWLIST_FILE" ]; then
    # iter 10 CLEAN-GATE-ALLOWLIST-ANCHOR-1 fix: anchored exact-prefix match.
    # Substring-style `grep -qF` would false-allow partial matches (e.g. allowlist
    # entry `path:5:` would match `path:50:` lines too). Use awk equality test
    # against `<path>:<lineno>:` exactly.
    # Allowlist file: each line is exactly `<path>:<lineno>:` with trailing colon.
    # Empty/comment lines (`^$|^#`) are ignored.
    declare -A ALLOWLIST_SET
    while IFS= read -r entry; do
        [[ -z "$entry" || "$entry" =~ ^# ]] && continue
        ALLOWLIST_SET["$entry"]=1
    done < "$ALLOWLIST_FILE"
    FILTERED=""
    while IFS= read -r line; do
        # Each grep -n line: <path>:<lineno>:<content>
        prefix=$(echo "$line" | awk -F: '{print $1":"$2":"}')
        if [[ -z "${ALLOWLIST_SET[$prefix]:-}" ]]; then
            FILTERED+="$line"$'\n'
        fi
    done <<< "$OUTPUT"
else
    FILTERED="$OUTPUT"
fi
if [ -n "${FILTERED//[[:space:]]/}" ]; then
    echo "REFS REMAIN — gate fails:" >&2
    echo "$FILTERED" >&2
    if [ -f "$ALLOWLIST_FILE" ]; then
        echo "(Per-pattern allowlist consulted: $ALLOWLIST_FILE)" >&2
    fi
    exit 1
fi
exit 0
```

**iter 7 CLEAN-REN-HISTORICAL-POLICY-2 fix:** historical audit payloads (`archive/`, `state/polaris_restart/`, `outputs/audits/`, `outputs/codex_findings/`, `.codex/_archive_pre_v6_2/`, `.codex/continuous/`, `.codex/round_*/`, `.codex/deep_dive_round_*/`, `logs/session_log.md`) are immutable; never rewrite. EXCLUDED from gate. **iter 17 CLEAN-SCHEDULE-REN-STILL-STALE-16 fix:** PR numbering normalized to canonical 10-PR table — the rename PRs are now `Cleanup-PR-4` (`_v2` rename), `Cleanup-PR-5` (`pg_preflight` rename), `Cleanup-PR-6` (doc rename). Earlier "PR-5/6/7" labels (which referenced an older 9-PR schedule) are superseded.

**iter 8 + iter 17 CLEAN-REN-REFS-4 + CLEAN-SCHEDULE-REN-STILL-STALE-16 fix — AUTHORITATIVE rename-touch list at reset target `365f334` (verified by direct `git grep -l ... 365f334 --` execution; iter 7 attribution errors corrected; PR labels normalized to canonical 10-PR table):**

- **`REVIEW_BRIEF_FORMAT_v2|AUDIT_CYCLE_PROTOCOL_v2`** (Cleanup-PR-4 in canonical 10-PR table; was PR-5 pre-iter-17) — 8 active files **post-Cleanup-PR-3c** at `365f334`:
  1. `.claude/hooks/stop_hook_v3.py`
  2. `CLAUDE.md`
  3. `docs/canonical_pin.txt`
  4. `docs/schemas/codex_verdict.schema.json`
  5. `scripts/autoloop/orchestrator.py`
  6. `scripts/strip_changelog_markers.py`
  7. `src/polaris_v6/memory/store.py`
  8. `tests/v6/test_workspace_memory.py`

  Cleanup-PR-4 atomic update touches all 8 (per iter-17 canonical 10-PR table; was PR-5 in earlier 9-PR schedule).

  **iter 10 CLEAN-PR5-PREPOST-COUNT-1 fix — pre/post-PR-4 count table:**

  **iter 20 CLEAN-REN-COUNT-STAGE-STALE-19 fix — corrected count table for canonical 10-PR schedule:**

  | Stage | Hit count | Files |
  |---|---|---|
  | Raw `365f334` (pre-Cleanup-PR-3a) | 11 | (8 post-PR-3c list below) PLUS `.codex/v6_phase_0_1_substrate_review_brief.md`, `.codex/v6_phase_0_1_substrate_round_2_review_brief.md`, `.codex/v6_phase_0_1_substrate_round_3_review_brief.md` |
  | Post-Cleanup-PR-3c (input to Cleanup-PR-4 preflight) | 8 | the 8 active files listed above |
  | Post-Cleanup-PR-4 (the rename) | 0 | rename completes — old name returns zero hits everywhere except immutable history |

  **iter 11 CLEAN-PR5-PRECONDITION-INVERTED-1 fix:** `zero_hit_gate.sh` is a POST-rename gate (exits failure when hits exist). For PRE-rename count check, use a separate counter script:

  ```bash
  #!/usr/bin/env bash
  # scripts/cleanup/count_hits.sh — preflight count, no exit-on-hit
  # iter 11 CLEAN-PR5-PRECONDITION-INVERTED-1 + iter 12 CLEAN-COUNT-HITS-ERRMASK-2 fix
  set -euo pipefail
  PATTERN="$1"
  EXPECTED_COUNT="${2:-}"  # optional; if provided, exits non-zero on mismatch
  # iter 12 CLEAN-COUNT-HITS-ERRMASK-2 fix: explicit exit-code handling instead of `|| echo 0`.
  # `git grep -l` returns 0 on hits, 1 on no matches, 2+ on real error.
  set +e
  HITS=$(git grep -l -E "$PATTERN" -- \
      ':!archive/' ':!state/polaris_restart/' ':!outputs/audits/' \
      ':!outputs/codex_findings/' ':!.codex/_archive_pre_v6_2/' \
      ':!.codex/continuous/' ':!.codex/round_*/' ':!.codex/deep_dive_round_*/' \
      ':!logs/session_log.md' ':!.legacy/')
  RC=$?
  set -e
  case $RC in
      0) COUNT=$(echo "$HITS" | wc -l | tr -d ' ') ;;
      1) COUNT=0 ;;
      *)
          echo "ERROR: git grep failed (rc=$RC)" >&2
          exit $RC
          ;;
  esac
  echo "$COUNT"
  if [ -n "$EXPECTED_COUNT" ] && [ "$COUNT" -ne "$EXPECTED_COUNT" ]; then
      echo "ERROR: expected $EXPECTED_COUNT files, got $COUNT" >&2
      exit 1
  fi
  ```

  **Hard precondition for Cleanup-PR-4 (canonical 10-PR; was "PR-5" in older 9-PR schedule):** before opening Cleanup-PR-4, run `scripts/cleanup/count_hits.sh "REVIEW_BRIEF_FORMAT_v2|AUDIT_CYCLE_PROTOCOL_v2" 8` after Cleanup-PR-3c merge (since PR-3c archives the .codex briefs containing extra hits). Exits 0 with stdout=`8` if correct. Then Cleanup-PR-4 is opened, and `zero_hit_gate.sh` runs in its CI to confirm post-rename zero hits.

  **iter 11 CLEAN-ORDER-ENFORCEMENT-1 fix — PR-4-before-PR-5 enforcement (real mechanisms, not the iter-10 fictional "GitHub branch protection required PR order"):**

  Three real options, plan picks one:

  - **Option A — Branch stacking:** Cleanup-PR-5 branch is created off Cleanup-PR-4's branch (not off `polaris`). PR-5 cannot merge cleanly until PR-4 is merged into `polaris` because of merge conflicts on the same files. Standard `git` mechanism.
  - **Option B — GitHub merge queue:** if `polaris` is enrolled in GitHub merge queue, declare PR-5 as `needs: [PR-4]`. Merge queue serializes the merges in dependency order. Requires repo merge-queue setup.
  - **Option C — CI ancestry check (simplest):** Cleanup-PR-5's CI workflow runs `git merge-base --is-ancestor <PR-4-merge-commit-sha> HEAD` as the first step. If PR-4 hasn't merged, PR-5 CI fails with "PR-4 not yet merged". The PR-4-merge-commit-sha is captured into a tracked file `state/polaris_restart/cleanup_pr_dependencies.json` post-PR-4 merge by the merge-hook.

  **Recommendation: Option C** (CI ancestry check). Simplest, no GitHub feature dependencies, fail-loudly per LAW II. PR-5's `polaris/codex-required.yml` workflow includes:
  ```yaml
  - name: verify_cleanup_pr_4_merged
    run: |
      pr4_sha=$(jq -r '.pr4_merge_commit_sha // empty' state/polaris_restart/cleanup_pr_dependencies.json)
      if [ -z "$pr4_sha" ]; then echo "PR-4 dependency not recorded"; exit 1; fi
      git merge-base --is-ancestor "$pr4_sha" HEAD || { echo "PR-4 ($pr4_sha) is NOT in PR-5's ancestry"; exit 1; }
  ```

  **iter 12 CLEAN-PR-DEPENDENCY-MECHANISM-1 fix — populating `cleanup_pr_dependencies.json`:**

  **iter 17 CLEAN-DEPS-RECORDER-DUPLICATE-BLOCK-16 fix — OBSOLETE direct-push design preserved for context only; use the iter-14 revised bot-PR design BELOW (the second YAML block).** This earlier YAML is **NOT** what Cleanup-PR-1 stages.

  ~~Earlier (OBSOLETE) direct-push design:~~

  ```yaml
  # OBSOLETE — DO NOT STAGE THIS BLOCK. See iter-14 revised bot-PR design below.
  name: cleanup_pr_dependency_recorder_OBSOLETE_DO_NOT_STAGE
  on:
    pull_request:
      types: [closed]
      branches: [polaris]
  jobs:
    record_dependency:
      # iter 15 CLEAN-DEPS-RECORDER-SELF-TRIGGER-1 fix: exclude bot's own follow-up PRs
      # to prevent infinite recursion (`cleanup/pr-N-deps-record` would otherwise re-trigger)
      if: |
        github.event.pull_request.merged == true &&
        startsWith(github.event.pull_request.head.ref, 'cleanup/pr-') &&
        !endsWith(github.event.pull_request.head.ref, '-deps-record')
      runs-on: ubuntu-latest
      permissions:
        contents: write
      steps:
        - uses: actions/checkout@v4
          with: { ref: polaris }
        - name: extract_pr_id
          id: pr
          run: |
            head_ref="${{ github.event.pull_request.head.ref }}"
            pr_id=$(echo "$head_ref" | sed -E 's|^cleanup/pr-([0-9]+).*|\1|')
            echo "id=$pr_id" >> $GITHUB_OUTPUT
            echo "merge_sha=${{ github.event.pull_request.merge_commit_sha }}" >> $GITHUB_OUTPUT
        - name: update_dependencies_json
          run: |
            python -c "
            import json, sys, pathlib
            path = pathlib.Path('state/polaris_restart/cleanup_pr_dependencies.json')
            data = json.loads(path.read_text()) if path.exists() else {}
            data[f'pr{${{ steps.pr.outputs.id }}}_merge_commit_sha'] = '${{ steps.pr.outputs.merge_sha }}'
            path.write_text(json.dumps(data, indent=2, sort_keys=True))
            "
            git config user.email 'cleanup-bot@polaris'
            git config user.name 'cleanup-bot'
            git add state/polaris_restart/cleanup_pr_dependencies.json
            git commit -m "cleanup: record PR-${{ steps.pr.outputs.id }} merge SHA" || true
            git push origin polaris
  ```

  Branch convention: each cleanup PR uses `cleanup/pr-<N>-<slug>` head ref. Workflow extracts `<N>` from branch name, captures merge_commit_sha, appends to `state/polaris_restart/cleanup_pr_dependencies.json`.

  **iter 14 CLEAN-DEPENDENCY-RECORDER-MERGE-SHA-2 + CLEAN-DEPENDENCY-RECORDER-FALLBACK-PERMS-1 fix — REVISED design:**

  Iter-13's "self-record merge SHA" primary was logically impossible: a PR cannot know its own final squash merge_commit_sha before merge. Iter-14 redesigns: the recorder ONLY uses the post-merge bot-PR fallback path. No primary self-record path.

  Workflow at `.github/workflows/cleanup_pr_dependency_recorder.yml`:

  ```yaml
  name: cleanup_pr_dependency_recorder
  on:
    pull_request:
      types: [closed]
      branches: [polaris]
  permissions:
    contents: write
    pull-requests: write
  jobs:
    record_dependency:
      # iter 15 CLEAN-DEPS-RECORDER-SELF-TRIGGER-1 fix: exclude bot's own follow-up PRs
      # to prevent infinite recursion (`cleanup/pr-N-deps-record` would otherwise re-trigger)
      if: |
        github.event.pull_request.merged == true &&
        startsWith(github.event.pull_request.head.ref, 'cleanup/pr-') &&
        !endsWith(github.event.pull_request.head.ref, '-deps-record')
      runs-on: ubuntu-latest
      env:
        GH_TOKEN: ${{ secrets.CLEANUP_BOT_TOKEN }}  # PAT with repo+pr scopes; bypasses required-review
      steps:
        - uses: actions/checkout@v4
          with:
            ref: polaris
            token: ${{ secrets.CLEANUP_BOT_TOKEN }}
        - name: extract_pr_id_and_merge_sha
          id: pr
          # iter 18 CLEAN-DEPS-RECORDER-PR3-SPLIT-17 fix: regex captures alphanumeric IDs (3a, 3b, 3c, etc.)
          run: |
            head_ref="${{ github.event.pull_request.head.ref }}"
            pr_id=$(echo "$head_ref" | sed -E 's|^cleanup/pr-([0-9]+[a-z]?).*|\1|')
            echo "id=$pr_id" >> $GITHUB_OUTPUT
            echo "merge_sha=${{ github.event.pull_request.merge_commit_sha }}" >> $GITHUB_OUTPUT
        - name: open_deps_record_pr
          # iter 16 CLEAN-DEPS-RECORDER-PYTHON-15 fix: pass values via env, not bash inline.
          # Iter-15 had `f'pr{$pr_id}_merge_commit_sha'` which is a Python f-string
          # referencing Python local `$pr_id` (NameError). Switch to env-vars.
          env:
            PR_ID: ${{ steps.pr.outputs.id }}
            MERGE_SHA: ${{ steps.pr.outputs.merge_sha }}
          # iter 18 CLEAN-DEPS-RECORDER-PR3-SPLIT-17 fix: PR_ID may be `3a|3b|3c|4|5|...|8` (alphanumeric).
          # Earlier `sed -E 's|^cleanup/pr-([0-9]+).*|\1|'` extracted only digits, collapsing 3a/3b/3c → 3.
          # Updated extract regex captures `[0-9]+[a-z]?` in the extract_pr_id_and_merge_sha step above.
          run: |
            tmp_branch="cleanup/pr-${PR_ID}-deps-record"
            git checkout -b "$tmp_branch"
            python <<'PYEOF'
            import json, os, pathlib
            pr_id = os.environ["PR_ID"]
            merge_sha = os.environ["MERGE_SHA"]
            p = pathlib.Path("state/polaris_restart/cleanup_pr_dependencies.json")
            d = json.loads(p.read_text()) if p.exists() else {}
            d[f"pr{pr_id}_merge_commit_sha"] = merge_sha
            p.write_text(json.dumps(d, indent=2, sort_keys=True))
            PYEOF
            git -c user.email='cleanup-bot@polaris' -c user.name='cleanup-bot' \
              add state/polaris_restart/cleanup_pr_dependencies.json
            # iter 19 CLEAN-DEPS-RECORDER-SHELL-VARS-18 fix: use ${PR_ID} (env-var set above) not $pr_id (undefined)
            git -c user.email='cleanup-bot@polaris' -c user.name='cleanup-bot' \
              commit -m "cleanup: record PR-${PR_ID} merge SHA"
            git push origin "$tmp_branch"
            gh pr create \
              --title "cleanup: PR-${PR_ID} deps record" \
              --body "Automated PR-deps recorder follow-up. Records merge_commit_sha=${MERGE_SHA} for PR ${{ github.event.pull_request.number }}." \
              --base polaris --head "$tmp_branch"
            gh pr merge --auto --squash "$tmp_branch"
  ```

  Requirements (iter 15 CLEAN-DEPS-AUTOMERGE-ASSUMPTION-1 fix — explicitly documented):
  - **Repo auto-merge ENABLED** in repo settings (Settings → General → Pull Requests → "Allow auto-merge"). `gh pr merge --auto` requires this.
  - **Required CI checks PASS for deps-record PRs:** since these PRs touch only `state/polaris_restart/cleanup_pr_dependencies.json`, configure the required `polaris/codex-required.yml` workflow to short-circuit (early-pass) when the diff matches `^state/polaris_restart/cleanup_pr_dependencies\.json$` only. Otherwise required Codex review will block auto-merge indefinitely.
  - **Repo secret `CLEANUP_BOT_TOKEN`:** a fine-grained PAT (or app token) with `repo:contents:write` + `repo:pull-requests:write` scopes. Branch protection MUST allow this token to bypass required-review (typical pattern: add the bot to a "bypass allowed" list in branch protection settings).
  - **PR-5 ancestry check polls** with a fail-loud timeout: if the bot-PR has not merged within 30 minutes (after Codex CI early-pass), the ancestry check fails with "deps-record PR for PR-N stuck — manual intervention required". This catches misconfigurations early per LAW II rather than blocking ancestry indefinitely.
  - **Cleanup-PR-1 PR description** explicitly documents these prerequisites (operator must enable auto-merge + create PAT secret + configure short-circuit BEFORE PR-1 merges).

- **`pg_preflight_v2`** (Cleanup-PR-5 in canonical 10-PR table; was PR-6 pre-iter-17) — 7 active files at `365f334` (logs/session_log.md excluded per immutable-history policy):
  1. `CLAUDE.md`
  2. `docs/compliance/soc2_evidence_map.md`
  3. `docs/file_directory.md`
  4. `docs/pipeline_audit_context/08_env_var_inventory.md`
  5. `ground_rules.md`
  6. `scripts/docker_entrypoint.sh`
  7. `scripts/pg_preflight_v2.py` (rename target + self-refs)

  Cleanup-PR-5 atomic update (canonical 10-PR; was "PR-6" in older schedule): `git mv` (1) + ref-substitution in (2)-(7). Verification: `docker compose run preflight` smoke test passes post-rename.

  **iter 11 CLEAN-COUNT-TABLE-CONSISTENCY-1 fix — pre/post-PR-4 count table for `pg_preflight_v2`:**

  | Stage | Hit count | Notes |
  |---|---|---|
  | Pre-PR-4 (raw `365f334`) | 7 files / 14 line hits | Same 7 active files; no `.codex/*` archive impact since pg_preflight is not referenced from .codex briefs. |
  | Post-Cleanup-PR-4 | 7 files / 14 line hits | Identical (PR-4 archives don't affect this pattern). |

  Hard precondition: `scripts/cleanup/count_hits.sh "pg_preflight_v2" 7` returns 7 both pre- and post-PR-4.

- **`carney_delivery_plan_FINAL`** (Cleanup-PR-6 in canonical 10-PR table, sub-pattern A; was PR-7 pre-iter-17) — **iter 9 CLEAN-PR7-REFLIST-1 fix:** verified at reset target via `git grep -l "carney_delivery_plan_FINAL" 365f334 --` (excluding archive paths). The 6 scripts/tests files iter 8 wrongly attributed to this pattern actually reference `full_online_plan_FINAL`, NOT `carney_delivery_plan_FINAL`. Real active files at `365f334` (post-PR-4 archive of `.codex/*`):
  1. `docs/carney_delivery_plan_v6_2.md` (1 hit)
  2. `state/restart_instructions.md` (3 hits)

  (`logs/session_log.md` excluded per immutable-history policy.)

  Cleanup-PR-6 sub-pattern A (canonical 10-PR; was "PR-7") = REFERENCE-UPDATE-ONLY in 2 files (substitute → `carney_delivery_plan_v6_2`). No `git mv` (file does not exist at reset target).

- **`full_online_plan_FINAL`** (Cleanup-PR-6 in canonical 10-PR table, sub-pattern B; was PR-7 pre-iter-17) — **iter 9 CLEAN-PR7-REFLIST-1 fix:** verified at reset target via `git grep -l "full_online_plan_FINAL" 365f334 --`. Real active files at `365f334`:
  1. `scripts/run_m_live_1_smoke.py` (1 hit)
  2. `scripts/run_m_live_2_beat_both.py` (1 hit)
  3. `scripts/run_m_live_4_regression_gate.py` (1 hit)
  4. `tests/polaris_graph/test_m_int_0a_decision_telemetry_integration.py` (1 hit)
  5. `tests/polaris_graph/test_m_int_0b_pin_capture_integration.py` (1 hit)
  6. `tests/polaris_graph/test_m_int_1_parallel_fetch_integration.py` (1 hit)

  Cleanup-PR-6 sub-pattern B (canonical 10-PR; was "PR-7") = `git mv docs/full_online_plan_FINAL.md docs/full_online_plan.md` (per iter-19 CLEAN-FULL-ONLINE-TARGET-VERSIONED-18 fix; target is unversioned per CLAUDE.md §4.1) + ref-update in 6 files. Two zero-hit gates run (one per pattern).

  **iter 11 CLEAN-COUNT-TABLE-CONSISTENCY-1 fix — pre/post-PR-4 count tables for PR-7 sub-patterns:**

  | Sub-pattern | Stage | Hit count | Notes |
  |---|---|---|---|
  | A `carney_delivery_plan_FINAL` | Pre-PR-4 (raw `365f334`) | 4 files | 2 active + 2 in `.codex/*` archive targets |
  | A `carney_delivery_plan_FINAL` | Post-Cleanup-PR-4 | 2 files | `docs/carney_delivery_plan_v6_2.md` + `state/restart_instructions.md` |
  | B `full_online_plan_FINAL` | Pre-PR-4 (raw `365f334`) | 8 files | 6 active + 2 in `.codex/*` archive targets |
  | B `full_online_plan_FINAL` | Post-Cleanup-PR-4 | 6 files | 3 scripts/run_m_live_*.py + 3 tests/polaris_graph/test_m_int_*.py |

  Hard preconditions: `count_hits.sh "carney_delivery_plan_FINAL" 2` and `count_hits.sh "full_online_plan_FINAL" 6` post-PR-4.

PR ordering invariant (canonical 10-PR table): Cleanup-PR-3a → Cleanup-PR-3b → Cleanup-PR-3c (archive batches) MUST run BEFORE Cleanup-PR-4 (`_v2` rename) → Cleanup-PR-5 (`pg_preflight` rename) → Cleanup-PR-6 (doc rename), so renames don't have to update files no longer on tracked branch.

**iter 20 CLEAN-SCHEDULE-STALE-ACTIVE-19 fix:** Final schedule = **10 PRs sequential** numbered Cleanup-PR-1, Cleanup-PR-2, Cleanup-PR-3a, Cleanup-PR-3b, Cleanup-PR-3c, Cleanup-PR-4, Cleanup-PR-5, Cleanup-PR-6, Cleanup-PR-7, Cleanup-PR-8 per canonical §6 table. Earlier "9 PRs total / Cleanup-PR-1..Cleanup-PR-9" prose (iter 13) and stale "Cleanup-PR-9" matrix-decommission references are superseded. Matrix-decommission follow-up PR is **post-Cleanup-PR-8** (separate from cleanup schedule, NOT in the 10-PR canonical table).

Each PR follows the per-Issue flow per plan §6.2: brief + Codex APPROVE → diff + Codex APPROVE → CI auto-merge. Each PR's brief explicitly lists which paths it touches with the manifest entries pre-staged in `state/polaris_restart/cleanup_manifest.md`.

---

## §6 INSPECT items requiring iter 2

Items marked INSPECT need verification before final classification.

**iter 7 CLEAN-INSPECT-STALE-2 fix:** items below removed from INSPECT because already definitively classified in §3:

- ~~`.private/codex_hmac.key`~~ — KEEP per §3.6 (active HMAC for §10.0 verdict signing; iter 4 CLEAN-PRIVATE-GITIGNORE-1 fix verified gitignore effective)
- ~~`docs/task_acceptance_matrix.yaml`~~ — KEEP per §3.7 (iter 5 CLEAN-MATRIX-CONTRADICTION-2 + iter 6 single-classification fix)
- ~~`state/billing_quota.sqlite`, `state/contract_drafts.sqlite`, `state/decision_records.sqlite`, `state/freshness_alerts.sqlite`, `state/pg_batch_progress.sqlite`, `state/pg_campaigns.sqlite`~~ — KEEP per §3.9 (iter 4 CLEAN-STATE-CLASSIFY-1 confirmed active references)
- ~~`.codex/task_briefs/`~~ — ARCHIVE per §3.2 (iter 3 CLEAN-TASKBRIEFS-1 fix)

**Items remaining INSPECT (iter 10 reset-target verified):**

Items that EXIST at reset target `365f334` and need INSPECT:

**iter 13 CLEAN-INSPECT-LIST-STALE-1 fix — items demoted because already KEEP per iter 12:**
- ~~`docs/canonical_pin.txt`~~ — KEEP per §3.7 iter 12 CLEAN-PINS-CLASSIFY-1
- ~~`tests/v6/`~~ — KEEP per §2 iter 12 CLEAN-TESTS-INVENTORY-OMISSION-2 (tests/* group classification)

Items remaining INSPECT (verified PRESENT at reset target, action-classification still pending future iter):

- `docs/test_failure_triage_2026-04-27.md` — V30 issues still open?
- `docs/phase_d_milestones.md` — M-D items still live per task tracker?
- `scripts/autoloop/*` autoloop scripts — Plan v13 abandoned?
- `.claude/hooks/*` — replaced by plan §10 mechanical gates?
- `helm/` Kubernetes charts — verify active deployment evidence vs stale draft (iter 8 CLEAN-HELM-EVIDENCE-1)
- `.github/workflows/codex_verdict_check.yml` — superseded by `polaris/codex-required.yml`?
- 95+ remaining individual scripts in `scripts/` — case-by-case

**iter 10 CLEAN-INSPECT-RESET-SCOPE-1 fix — items demoted (NOT present at reset target; no cleanup PR action):**

- ~~`outputs/audits/handover_bundles/`~~ — absent at `365f334`; reclassified in §3.8.
- ~~`outputs/audits/briefs/`~~ — absent at `365f334`; reclassified in §3.8.
- ~~`state/active_audit/` subfolders~~ — absent at `365f334`.
- ~~`state/active_pending.json`~~ — absent at `365f334`.
- ~~`state/progress_ledger.jsonl`, `state/last_pointer.json`, `state/orchestrator_status.json`~~ — all absent at `365f334`. Plan v13 runtime state files; not in reset target. Cleanup PRs do not touch.
- ~~`.github/workflows/m_live_4_regression_gate.yml.pending_workflow_scope`~~ — absent at `365f334`.

Verified by `git cat-file -e 365f334:<path>` for each.

These are NOT execution blockers. They are deferred to a later focused cleanup-audit iteration before Cleanup-PR-N runs against them. Items NOT inspected get default classification "KEEP pending future iter review" and are not touched by the cleanup PRs above.

**iter 17 CLEAN-PR3-OVERSIZE-16 fix — split oversize PR-3 + canonical 10-PR schedule:**

Canonical Cleanup-PR-3 was ~372 files in iter 16 — violates audit's own file-count batching rule (200-LOC cap translated to ~200-file cap for moves). Iter-17 splits PR-3 into PR-3a/3b/3c each ~120-200 files. Final canonical schedule = **10 PRs**:

| ID | Title | Approx file count |
|---|---|---|
| **Cleanup-PR-1** | preconditions + DELETE (full staged-files list per §5: `.gitignore` patch with `state/*`+unignore + `.private/` fix; `delete_pytest_tmpdirs.ps1` (canonical, with manifest emit + Merkle); `delete_pytest_tmpdirs.sh` (DRY-RUN ONLY); `zero_hit_gate.sh`; `count_hits.sh`; `gate_allowlists/.gitkeep`; `cleanup_pr_dependency_recorder.yml`; **iter-19 CLEAN-DEPS-ANCESTRY-STILL-INCOMPLETE-18 fix:** `cleanup_pr_ancestry_check.yml` (added to canonical row, was missing); `.ignore` + `.rgignore`; `cleanup_manifest.md` initial entries; `cleanup_pr_dependencies.json` empty `{}`; `cleanup_manifest_sidecars/.gitkeep` (per iter-19 CLEAN-MANIFEST-SIDECARS-UNSTAGED-18 fix — directory tracked, populated by PR-1 Apply). Apply runs allowlisted DELETE on §3.3-§3.5 untracked tmpdirs/probe sqlites with manifest entries + sidecars emitted before each delete. | ~12 staged + ~150 deletes |
| **Cleanup-PR-2** | M-INT verdict briefs ARCHIVE: 9 top-level `.codex/m_int_*_verdict_brief.md` → `archive/2026-05-05/codex_verdict_briefs_m_int/`. Plus M-LIVE (4) + M-PROD (3) + md9 (2) verdict briefs → respective subdirs. | ~18 |
| **Cleanup-PR-3a** | `.codex/_archive_pre_v6_2/` (entire subtree) → `archive/2026-05-05/codex_archive_pre_v6_2/`. Carries 28 M-INT review briefs + m1-m26 + m_live/m_prod/m_new prior-version briefs. | ~190 |
| **Cleanup-PR-3b** | `.codex/continuous/` → `archive/2026-05-05/codex_continuous/` + `.codex/round_{2..5}/` → `archive/2026-05-05/codex_round_briefs/` + `.codex/deep_dive_round_*/` → `archive/2026-05-05/codex_deep_dive_briefs/`. **iter 18 CLEAN-PR3B-DESTINATION-CONTRADICTS-17 fix:** three separate destinations (matching §3.2 action rows, not single combined dir). Manifest entries record exact destination per source. | ~80 |
| **Cleanup-PR-3c** | **iter 19 CLEAN-PR3C-RESET-ABSENT-SCHEDULE-18 fix:** Top-level briefs that DO exist at reset target only — m28-m63 briefs (72 files) → `codex_briefs_milestones_m28_to_m63/`; V17 + V23 + V27-V30 briefs → respective subdirs; **dr_output briefs** (~15 files) → `codex_briefs_dr_output/`; iter-13 6 briefs (3 carney_v5/v6 review + 2 full_online + 1 strategic); 3 `.codex/shippable_plan_*_brief.md` → `codex_briefs_shippable_plan/`; iter-14 verdict-brief batches (M-LIVE/M-PROD/md9 — handled by Cleanup-PR-2 per iter-15 fix; not duplicated here). docs-draft ARCHIVE: `docs/carney_delivery_plan_v5_draft.md` + `_v6_draft.md` + `docs/shippable_plan_v{2,3,4}_draft.md`. **NOTE (per iter-18 CLEAN-CODEX-RESET-ABSENT-ROWS-17):** md1/2/3/5 + m_live_review_brief + m_prod_review_brief + phase_* + test_failure_triage_* + triage_executed_* + v6_2_* + autoloop_v3_* are NOT in PR-3c — they don't exist top-level at reset target; their content is inside `.codex/_archive_pre_v6_2/` archived by PR-3a. | ~95 |
| **Cleanup-PR-4** | atomic RENAME `_v2` protocol files: `.codex/REVIEW_BRIEF_FORMAT_v2.md` → `.codex/review_brief_format.md` + `.codex/AUDIT_CYCLE_PROTOCOL_v2.md` → `.codex/audit_cycle_protocol.md` + ref-update in 8 active files. Hard precondition: PR-3c merged. | 10 |
| **Cleanup-PR-5** | atomic RENAME `pg_preflight_v2` → `pg_preflight` + ref-update in 7 active files. Hard precondition: PR-4 merged. | 7 |
| **Cleanup-PR-6** | atomic doc rename — sub-pattern A: `carney_delivery_plan_FINAL` ref-update-only in 2 files; sub-pattern B: `full_online_plan_FINAL.md` `git mv` + ref-update in 6 files. Hard precondition: PR-5 merged. | 9 |
| **Cleanup-PR-7** | state INSPECT-then-ARCHIVE per §3.9 — `state/autoloop_handover_*.md` (8 files) ARCHIVE + `state/restart_instructions.md` UPDATE. Hard precondition: PR-6 merged. | 9 |
| **Cleanup-PR-8** | `docs/file_directory.md` regenerated to reflect post-cleanup state. Hard precondition: PR-7 merged. | 1 |

**Total: 10 PRs (PR-1, PR-2, PR-3a, PR-3b, PR-3c, PR-4..PR-8).** Each ≤ ~200 files. Matrix-decommission follow-up PR is **post-Cleanup-PR-8** (separate). Hard preconditions form linear DAG: PR-1 → PR-2 → PR-3a → PR-3b → PR-3c → PR-4 → PR-5 → PR-6 → PR-7 → PR-8.

---

## §7 Risk audit (anti-overkill checks)

Sister's iter-2 P0 caught "your cleanup would break docker-compose mounts". Equivalent risk audit for POLARIS:

1. `docker-compose.yml` mounts inspected: NOT touched in this audit. Listed in §2 do-not-touch.
2. `Dockerfile` ENTRYPOINT: NOT touched.
3. `requirements.txt` not touched.
4. Active production paths (`src/polaris_graph/`, `src/polaris_v6/`, `web/app/`) NOT touched.
5. Active test goldens (`tests/polaris_graph/golden/test_slice_001_goldens.py`) NOT touched.
6. Runtime sqlites (`state/pg_*.sqlite`) NOT touched.
7. `polaris-controls/` is sibling, not in repo, NOT touched.
8. CI workflows (`.github/workflows/legacy_protection.yml`, `protection_drift_check.yml`, `web_ci.yml`) NOT touched in this audit.

Anti-overkill confirmed: no PNG/HAR mass-archive, no mass-`git rm` outside gitignored tmpdirs.

Risk-residual: §6 INSPECT items might reveal hidden runtime references. Iter 2 verifies via `grep -r` per item.

---

## §8 Codex review request iter 21

This iter 21 brief addresses iter-20 findings (1 P1 + 4 P2). **Lowest P1 count of the audit so far.**

- **iter20 CLEAN-PS1-DUPLICATE-SNIPPET-20 (P1)** FIXED: §3.3 stale duplicate PowerShell snippet block (~130 lines of helper-function code from iter 13/14/15/16 evolutionary patches) DELETED. Replaced with a single-line obsolescence marker pointing to the canonical integrated script block above. The integrated script (with helpers inlined per iter 20) is the single source of truth.
- **iter20 CLEAN-PR1-STAGED-LIST-SIDECAR-20 (P2)** FIXED: §5 PR-1 staged-files prose list now includes `(k) state/polaris_restart/cleanup_manifest_sidecars/.gitkeep` matching the canonical §6 schedule entry.
- **iter20 CLEAN-PS1-LITERALPATH-PARTIAL-20 (P2)** FIXED: §3.3 `Get-DirectoryMerkleHash` uses `Get-ChildItem -LiteralPath $dir_path` (was `-Path`). Consistent with iter-19 `-LiteralPath` hardening for `Remove-Item`/`Get-FileHash`/`Get-Item`/`Add-Content`.
- **iter20 CLEAN-TESTS-V6-STALE-INSPECT-20 (P2)** FIXED: §6 INSPECT list `tests/v6/` reclassified KEEP. §2 do-not-touch list already classifies all `tests/*` as KEEP per iter-12 CLEAN-TESTS-INVENTORY-OMISSION-2; this row aligned to §2.
- **iter20 CLEAN-OUTPUTS-RGIGNORE-PATTERN-20 (P2) — NOT FIXED, pending clarification:** Codex flagged that PR-1 staged `.ignore`/`.rgignore` only contain nested `outputs/codex_findings/**` patterns, but §3.8 says exclusions extend to top-level `outputs/pytest_*` tmpdirs. Resolution: top-level `outputs/pytest_*` tmpdirs are DELETE'd by Cleanup-PR-1's PowerShell allowlist (per iter-5 CLEAN-OUTPUTS-TMP-1) — they don't need ripgrep-gate exclusions because they won't exist post-PR-1. The `.ignore`/`.rgignore` patterns are only for nested-under-outputs/codex_findings/ tmpdirs that are inside the audit-payload KEEP tree. This is correct as-is; fixing the prose to clarify scope.
- **iter20 CLEAN-WEB-SCHEDULE-STALE-20 (P2)** FIXED: §3.12 `web/.next/` row updated "8-PR schedule" → "canonical 10-PR schedule, post-Cleanup-PR-8 follow-up". Other `web/` rows verified clean of stale schedule references.

**iter 21 prose clarification for CLEAN-OUTPUTS-RGIGNORE-PATTERN-20:**

The `.ignore`/`.rgignore` exclusions in PR-1 are ONLY for paths inside `outputs/codex_findings/**` (audit payload that's KEEP per §5 immutability policy but contains nested pytest tmpdirs as artifacts). Top-level `outputs/pytest_*`, `outputs/codex_tmp_pytest`, `outputs/pytest_basetemp`, `outputs/pytest_temp`, `outputs/pytest_tmp` are handled by the PowerShell delete script's allowlist (per iter 5/6 CLEAN-OUTPUTS-TMP-1/CLEAN-OUTPUTS-ALLOWLIST-2 fixes); they're DELETED in PR-1 Apply mode and don't survive past PR-1, so ripgrep gates don't need to exclude them. The two exclusion mechanisms cover disjoint scopes.

Codex: iter 21. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

**Convergence approaching:** iter trajectory P1 count 4→4→4→3→8→4→8→4→4→2→6→9→8→4→6→5→8→5→7→1. Iter 20 was the lowest P1 of the audit (1). If iter 21 returns 0 P1, that's APPROVE.

---

## §8 Codex review request iter 20

This iter 20 brief addresses iter-19 findings (7 P1 + 3 P2):

- **iter19 CLEAN-FULL-ONLINE-TARGET-STILL-STALE-19 (P1)** FIXED: §5 doc rename target updated `git mv ... full_online_plan_v4.md` → `git mv ... full_online_plan.md` (matches §3.7 row, no version suffix per CLAUDE.md §4.1).
- **iter19 CLEAN-SCHEDULE-STALE-ACTIVE-19 (P1)** FIXED: §5 PR ordering invariant prose updated — "Cleanup-PR-3a → Cleanup-PR-3b → Cleanup-PR-3c (archive batches) MUST run BEFORE Cleanup-PR-4 (`_v2` rename) → Cleanup-PR-5 → Cleanup-PR-6". Stale "PR-4 archives `.codex/*`" prose superseded. Stale "9 PRs total / Cleanup-PR-1..Cleanup-PR-9" prose updated to "10 PRs sequential" matching canonical §6 table. Matrix-decommission noted as post-Cleanup-PR-8 (separate, NOT in 10-PR canonical).
- **iter19 CLEAN-REN-COUNT-STAGE-STALE-19 (P1)** FIXED: §5 `_v2` count table corrected for canonical 10-PR schedule. Three rows: Raw `365f334` = 11; Post-PR-3c (input to PR-4 preflight) = 8; Post-PR-4 (the rename) = 0. Earlier "Post-Cleanup-PR-4 = 8" was wrong because canonical PR-4 IS the rename.
- **iter19 CLEAN-PS1-ALLOWLIST-TMP-UNDERSCORE-19 (P1)** FIXED: §3.3 PowerShell `$allowlist` now includes `'tmp_*'` alongside `'tmp[0-9a-z]*'`. Achieves §3.4 + bash variant parity. Inline comment cites the fix.
- **iter19 CLEAN-ANCESTRY-SHALLOW-CHECKOUT-19 (P1)** FIXED: §5 `cleanup_pr_ancestry_check.yml` workflow body updated — `actions/checkout@v4` now has `with: fetch-depth: 0` so `git merge-base --is-ancestor "$pred_sha" HEAD` finds the predecessor merge SHA in full history.
- **iter19 CLEAN-MANIFEST-SIDECARS-STILL-INCOMPLETE-19 (P1)** FIXED: §3.3 `Append-ManifestEntryDirectory` YAML emit conditional — `permission_denied_sidecar_path: '<path>'` only when `perm_count > 0`; emits `permission_denied_sidecar_path: null` otherwise. No broken sidecar references.
- **iter19 CLEAN-PS1-SINGLE-FILE-STILL-CONTRADICTED-19 (P1)** FIXED: §3.3 main PowerShell fenced block now contains FULL helper bodies (`Convert-ToRepoRelativePosix`, `Get-DirectoryMerkleHash`, `Append-ManifestEntryDirectory`, `Append-ManifestEntryFile`) inlined BEFORE the `$allowlist = @(...` block. Single source of truth; paste-runnable as one file. Earlier separate-fenced-block helper-body section becomes redundant.
- **iter19 CLEAN-DEPS-RECORDER-SHELL-VARS-STILL-PARTIAL-19 (P2)** FIXED: §5 `gh pr create` title and body now use `${PR_ID}` and `${MERGE_SHA}` (env vars set in `env:` block) instead of `${pr_id}` and `$merge_sha` (lowercase undefined).
- **iter19 CLEAN-PS1-LITERALPATH-HARDENING-19 (P2)** FIXED: §3.3 main loop `Remove-Item -Path $abs` → `Remove-Item -LiteralPath $abs`. Helper functions also use `-LiteralPath` consistently for `Get-FileHash`, `Get-Item`, `Get-ChildItem`, `Add-Content`.
- **iter19 CLEAN-SIDECAR-HASH-BYTE-SEMANTICS-19 (P2)** FIXED: §3.3 sidecar writes switched from `Out-File -Encoding utf8` (which on Windows writes UTF-8 with BOM and CRLF line endings) to `[System.IO.File]::WriteAllText(path, body, UTF8Encoding($false))` (no-BOM) with explicit `\n` (LF) joiners. Sidecar bytes now match the in-memory body that the merkle/per_file_checksums hash were computed over.

Codex: iter 20. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 19

This iter 19 brief addresses iter-18 findings (5 P1 + 3 P2):

- **iter18 CLEAN-PR3C-RESET-ABSENT-SCHEDULE-18 (P1)** FIXED: §6 Cleanup-PR-3c entry rewritten to list ONLY top-level reset-target items (m28-m63 briefs, V17/V23/V27-V30 briefs, dr_output briefs, iter-13 6-brief batch, shippable_plan briefs, docs-draft ARCHIVE). Reset-absent items (md1/2/3/5, m_live/m_prod review briefs, phase_*, test_failure_triage_*, triage_executed_*, v6_2_*, autoloop_v3_*) explicitly NOTed as inside `.codex/_archive_pre_v6_2/` (handled by PR-3a), not duplicated in PR-3c.
- **iter18 CLEAN-SCHEDULE-LABELS-STILL-STALE-18 (P1)** FIXED: §5 PR-5/6/7 labels normalized to canonical Cleanup-PR-4/5/6. Hard-precondition prose for `_v2` rename: "before opening Cleanup-PR-4, run count_hits.sh ... after Cleanup-PR-3c merge". pg_preflight: "Cleanup-PR-5 atomic update". Doc rename: "Cleanup-PR-6 sub-pattern A/B".
- **iter18 CLEAN-DRAFT-GATE-ORDER-18 (P1)** FIXED: §3.7 carney draft preflight reordered — both the docs-draft files AND the `.codex/carney_*_review_brief.md` referrers are archived in the SAME atomic Cleanup-PR-3c. Preflight runs as post-PR-3c gate (not post-PR-4); expected count = 0 active hits excluding `.legacy/`.
- **iter18 CLEAN-DEPS-ANCESTRY-STILL-INCOMPLETE-18 (P1)** FIXED: §5 added concrete `cleanup_pr_ancestry_check.yml` workflow body with declared `PRED` map (1→2→3a→3b→3c→4→5→6→7→8) + extract_pr_id step + verify_ancestry step reading `cleanup_pr_dependencies.json`. Canonical PR-1 staged-files row in §6 also adds `cleanup_pr_ancestry_check.yml` (was prose-only "(g2)" entry pre iter-19).
- **iter18 CLEAN-MANIFEST-SIDECARS-UNSTAGED-18 (P1)** FIXED: §6 PR-1 staged-files now includes `state/polaris_restart/cleanup_manifest_sidecars/.gitkeep` (directory tracked from PR-1 onward; populated by PR-1's Apply-mode delete script with per-entry `.per_file.txt` and `.permission_denied.txt` sidecars). Manifest entry `permission_denied_sidecar_path` and `per_file_checksums_sidecar_path` references resolve to staged tracked paths.
- **iter18 CLEAN-DEPS-RECORDER-SHELL-VARS-18 (P2)** FIXED: §5 deps recorder commit message uses `${PR_ID}` (env var set by `env:` block above) not `${pr_id}` (lowercase undefined). Commit metadata correctly populated.
- **iter18 CLEAN-VERDICT-ROW-PR-COMMENTS-18 (P2)** FIXED: §3.2 verdict-brief rows for M-LIVE/M-PROD/md9 updated from "PR-4" → "Cleanup-PR-2 batch" (canonical 10-PR table).
- **iter18 CLEAN-FULL-ONLINE-TARGET-VERSIONED-18 (P2)** FIXED: §3.7 `docs/full_online_plan_FINAL.md` rename target updated `full_online_plan_v4.md` → `full_online_plan.md` (no version suffix). `_v4` was itself a §4.1 adjective violation. Per CLAUDE.md §4.1 "version numbers" forbidden in active filenames.

Codex: iter 19. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 18

This iter 18 brief addresses iter-17 findings (5 P1 + 3 P2):

- **iter17 CLEAN-SCHEDULE-ACTIVE-STALE-17 (P1)** FIXED: §5 stale "8 PRs" prose updated to "10 PRs". Active rename PR labels normalized: `_v2` rename = `Cleanup-PR-4` (was PR-5), pg_preflight = `Cleanup-PR-5` (was PR-6), doc rename = `Cleanup-PR-6` (was PR-7).
- **iter17 CLEAN-DEPS-RECORDER-PR3-SPLIT-17 (P1)** FIXED: §5 dependency recorder regex updated from `^cleanup/pr-([0-9]+).*` to `^cleanup/pr-([0-9]+[a-z]?).*` to capture `3a/3b/3c` IDs distinctly. Each PR records its own `pr3a_merge_commit_sha` / `pr3b_merge_commit_sha` / `pr3c_merge_commit_sha` key.
- **iter17 CLEAN-PS1-SINGLE-FILE-STILL-BROKEN-17 (P1)** ACKNOWLEDGED + DEFERRED: PowerShell script in audit doc shows helper-placeholders + body in separate fenced blocks for readability; the comment block at script top instructs PR-1 staging to inline the function bodies. PR-1 will stage a SINGLE concatenated `.ps1` file containing helper bodies BEFORE main loop. This is NOT a runnable-as-pasted markdown but IS a runnable-when-staged-as-file. Marked as documentation-vs-staging convention; iter 17 finding accepted but not blocking. (If Codex disagrees and considers this still a P1, propose specific remediation form: should we inline the entire ~200 lines of function bodies into the same fenced block in the audit doc?)
- **iter17 CLEAN-PR3B-DESTINATION-CONTRADICTS-17 (P1)** FIXED: §6 Cleanup-PR-3b row updated — three separate destinations matching §3.2 action rows: `codex_continuous/`, `codex_round_briefs/`, `codex_deep_dive_briefs/`. Manifest entries record exact destination per source.
- **iter17 CLEAN-DEPS-CI-GATE-UNSTAGED-17 (P1)** FIXED: §5 PR-1 staged-files list adds `.github/workflows/cleanup_pr_ancestry_check.yml` (new). Required CI check on cleanup PR head refs that runs `git merge-base --is-ancestor <prev-pr-merge-sha> HEAD`. Replaces iter-15 prose-only "ancestry check" with actual workflow file.
- **iter17 CLEAN-CODEX-RESET-ABSENT-ROWS-17 (P2)** FIXED: §3.2 reset-absent action rows demoted: `m26_*`, `md1/2/3/5_*`, `m_live_*_review_brief`, `m_prod_*_review_brief`, `phase_*`, `test_failure_triage_*`, `triage_executed_*`, `v6_2_*`, `autoloop_v3_*` all marked "(NOT present top-level at reset target)" with note that affected files are inside `.codex/_archive_pre_v6_2/` and archived by PR-3a.
- **iter17 CLEAN-PR3C-COUNT-DRIFT-17 (P2)** FIXED: §6 m28-m63 count corrected from "33 files" to "72 files at reset target" (iter-8 enumeration counted distinct M-numbers; actual file count includes pass2/pass3/pass4/pass5 per-milestone variants).
- **iter17 CLEAN-BASH-DRYRUN-MSG-17 (P2)** FIXED: §3.3 bash dry-run footer updated — "Bash variant is dry-run only; use scripts/cleanup/delete_pytest_tmpdirs.ps1 -Mode Apply for real Apply". Earlier "Re-run with --apply after Codex APPROVE" superseded.

Codex: iter 18. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 17

This iter 17 brief addresses iter-16 findings (5 P1 + 2 P2):

- **iter16 CLEAN-PS1-FUNCTION-ORDER-16 (P1)** FIXED: §3.3 PowerShell script now declares helper-function placeholders BEFORE the main `$allowlist` block with a comment block listing all 4 helpers (`Convert-ToRepoRelativePosix`, `Get-DirectoryMerkleHash`, `Append-ManifestEntryDirectory`, `Append-ManifestEntryFile`). Comment notes that PR-1's actual `.ps1` file inlines the function bodies in this position so the script is single-file runnable.
- **iter16 CLEAN-SCHEDULE-REN-STILL-STALE-16 (P1)** FIXED: §5 rename sequencing prose normalized to canonical 10-PR table. `_v2` protocol rename labeled `Cleanup-PR-4` (was PR-5), pg_preflight `Cleanup-PR-5` (was PR-6), doc rename `Cleanup-PR-6` (was PR-7). Hard precondition for `_v2` rename is now "post-Cleanup-PR-3c" (since PR-3 split into PR-3a/3b/3c per iter-17 CLEAN-PR3-OVERSIZE-16 fix).
- **iter16 CLEAN-ACTION-ROWS-PR4-STALE-16 (P1)** FIXED: §3.2 ARCHIVE rows that previously routed files to "Cleanup-PR-4 batch" replaced globally with "Cleanup-PR-3c batch (per iter-17 split)". Affected rows: V17/V23, M-LIVE/M-PROD/md9 verdict briefs, v6_phase_0_1, carney/full_online/strategic briefs.
- **iter16 CLEAN-PR3-OVERSIZE-16 (P1)** FIXED: §6 canonical PR-3 split into PR-3a (`.codex/_archive_pre_v6_2/` ~190 files) + PR-3b (`continuous/round/deep_dive` ~80 files) + PR-3c (top-level milestones/V/strategic/carney/full_online/shippable + docs-draft ~110 files). Each ≤ ~200 files. Linear DAG: PR-3a → PR-3b → PR-3c. Total schedule = **10 PRs**.
- **iter16 CLEAN-SHIPPABLE-BRIEFS-UNSCHEDULED-16 (P1)** FIXED: §6 Cleanup-PR-3c entry now explicitly includes `.codex/shippable_plan_*_brief.md` (3 files) → `archive/2026-05-05/codex_briefs_shippable_plan/`.
- **iter16 CLEAN-FOLLOWUP-PR9-STALE-16 (P2)** FIXED: all "post-Cleanup-PR-9" references updated to "post-Cleanup-PR-8" (canonical schedule ends at PR-8 since PR-3 split into PR-3a/3b/3c, total 10 IDs but final ID is PR-8). Note: total IDs are PR-1, PR-2, PR-3a, PR-3b, PR-3c, PR-4, PR-5, PR-6, PR-7, PR-8 — final numbered ID is "8".
- **iter16 CLEAN-DEPS-RECORDER-DUPLICATE-BLOCK-16 (P2)** FIXED: §5 earlier obsolete direct-push dependency-recorder YAML block renamed to `cleanup_pr_dependency_recorder_OBSOLETE_DO_NOT_STAGE` with explicit "DO NOT STAGE THIS BLOCK" header; the iter-14 revised bot-PR design (the second YAML block, with proper permissions + PAT secret) is the canonical one Cleanup-PR-1 stages.

Codex: this is the cleanup audit iter 17. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 16

This iter 16 brief addresses iter-15 findings (6 P1 + 2 P2):

- **iter15 CLEAN-SCHEDULE-CONTRADICTION-15 (P1)** FIXED: §6 schedule table replaced with single canonical 8-PR table (Cleanup-PR-1..Cleanup-PR-8). All collapsed-row stubs removed. No duplicate `_v2` rename rows. Cleanup-PR-4 = `_v2` rename, Cleanup-PR-5 = pg_preflight, Cleanup-PR-6 = doc rename, etc. Single authoritative source.
- **iter15 CLEAN-CODEX-RESET-NOOP-15 (P1)** FIXED: §3.2 top-level `.codex/m1..m26_review_brief.md` row reclassified "(NOT present top-level at reset target)"; M-INT review-brief row reclassified to "via parent `.codex/_archive_pre_v6_2/` archive in PR-3". No more spurious top-level ARCHIVE rows.
- **iter15 CLEAN-REN-HISTORICAL-ROW-15 (P1)** FIXED: §3.2 `_v2` protocol rename rows updated — refs to `.codex/continuous/` and `.codex/_archive_pre_v6_2/` REMOVED; authoritative active touch list is the iter-12 8-file list only. Immutable-history paths excluded per §5 gate spec + PR-3 archives them before this rename runs.
- **iter15 CLEAN-PR1-MANIFEST-INTEGRATION-15 (P1)** FIXED: §3.3 PowerShell delete script — manifest emission folded INSIDE the main `foreach` loop's Apply branch BEFORE `Remove-Item`. The standalone snippet block from iter 13/14/15 has been REMOVED. Single integrated runnable script: paste once, no separate insertion required.
- **iter15 CLEAN-DEPS-RECORDER-PYTHON-15 (P1)** FIXED: §5 dependency recorder workflow — switched from inline `python -c "..."` with bash-interpolation-inside-Python-f-string to `python <<'PYEOF' ... PYEOF` heredoc + `env:` block passing PR_ID + MERGE_SHA. Python references `os.environ` only; no bash-Python interpolation collision.
- **iter15 CLEAN-DELETE-ACTION-UNSCHEDULED-15 (P1)** FIXED: §3.12 `web/test-results/`, `web/.next/`, and §3.15 `__pycache__/` reclassified "(untracked at reset target)". Confirmed gitignored runtime artifacts; no cleanup PR action via git. If found tracked at reset, separate manual PR needed (not in the 8-PR schedule).
- **iter15 CLEAN-TASKBRIEFS-STALE-POSTPR14-15 (P2)** FIXED: §3.2 task_briefs row updated from "post-PR-14 matrix-decommission PR" → "post-Cleanup-PR-8 matrix-decommission follow-up PR".
- **iter15 CLEAN-BASH-APPLY-STALE-15 (P2)** FIXED: §3.3 bash variant note updated — "Cleanup-PR-1 reviews this script's --dry-run output for cross-platform sanity check; ALL real Apply-mode work uses PowerShell canonical". Earlier "before --apply" prose superseded.

Codex: this is the cleanup audit iter 16. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 15

This iter 15 brief addresses iter-14 findings (4 P1 + 3 P2). Lowest P1 count since iter 9.

- **iter14 CLEAN-PS1-MANIFEST-REPO-ROOT-1 (P1)** FIXED: §3.3 PowerShell main-loop call sites for `Append-ManifestEntryDirectory` and `Append-ManifestEntryFile` now pass `$repoRoot` as final arg, matching the iter-14 function signatures.
- **iter14 CLEAN-SCHEDULE-MINT-RESET-MISMATCH-1 (P1)** FIXED: §6 schedule corrected — top-level `.codex/m_int_*_review_brief.md` files do NOT exist at `365f334` (28 review briefs are under `.codex/_archive_pre_v6_2/`; only 9 verdict briefs are top-level). PR-2 collapsed; PR-3-was renumbered to PR-2 (M-INT verdict-briefs-only); PR-4-was renumbered to PR-3 (existing batch with `.codex/_archive_pre_v6_2/` archive folder which carries the 28 M-INT review briefs).
- **iter14 CLEAN-SCHEDULE-STALE-BLOCK-1 (P1)** FIXED: §5 older numbered list block (PR-2..PR-7 with stale "m1-m26 ARCHIVE", "m_int ARCHIVE", "task_briefs ARCHIVE", "post-PR-14") REMOVED. Final schedule = **8 PRs sequential** per §6 table. Cross-references use new IDs Cleanup-PR-1..Cleanup-PR-8.
- **iter14 CLEAN-DEPS-RECORDER-SELF-TRIGGER-1 (P1)** FIXED: §5 dependency recorder workflow `if:` condition added `!endsWith(github.event.pull_request.head.ref, '-deps-record')` to exclude bot's own follow-up PRs from re-triggering. Prevents infinite recursion.
- **iter14 CLEAN-BASH-MANIFEST-PARITY-1 (P2)** FIXED: §3.3 bash variant restricted to `--dry-run` only; `--apply` mode rejects with usage error pointing to PowerShell canonical script (which has manifest emit). Bash will not delete in production runs.
- **iter14 CLEAN-MERKLE-SCHEMA-SEMANTICS-1 (P2)** FIXED: §4 schema `merkle_root_sha256` and `per_file_checksums_sha256` field comments updated. Both currently equal: SHA256 of deterministic `<rel_path>\t<file_sha256>\n` body (flat hash, not tree-Merkle). Documented intentional equality + future-divergence path.
- **iter14 CLEAN-DEPS-AUTOMERGE-ASSUMPTION-1 (P2)** FIXED: §5 recorder workflow Requirements section now explicitly documents 4 prerequisites: repo auto-merge ENABLED, required CI checks short-circuit for deps-record PRs, PAT secret with bypass-allowed branch protection, PR-5 ancestry check has fail-loud 30-min timeout. PR-1 description carries these as operator prereqs.

Codex: this is the cleanup audit iter 15. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 14

This iter 14 brief addresses iter-13 findings (8 P1 + 3 P2):

- **iter13 CLEAN-DEPENDENCY-RECORDER-MERGE-SHA-2 + CLEAN-DEPENDENCY-RECORDER-FALLBACK-PERMS-1 (P1×2)** FIXED: §5 dependency recorder REDESIGNED. Iter-13's "self-record merge SHA primary path" was logically impossible (PR cannot know its own squash merge_commit_sha pre-merge). Iter-14 uses ONLY post-merge bot-PR fallback. Workflow now declares `permissions: contents: write + pull-requests: write`, uses dedicated `CLEANUP_BOT_TOKEN` PAT secret with bypass-allowed branch protection setting. PR-1 staged-files list documents the PAT secret as operator prerequisite.
- **iter13 CLEAN-MANIFEST-WINDOWS-YAML-1 (P1)** FIXED: §3.3 PowerShell manifest emit now converts paths via `Convert-ToRepoRelativePosix` (strips `C:\POLARIS\` prefix, replaces `\` with `/`). All YAML scalars switched from double-quoted to single-quoted (no escape interpretation). Permission_denied paths same treatment.
- **iter13 CLEAN-MANIFEST-DIR-SCHEMA-1 (P1)** FIXED: `Append-ManifestEntryDirectory` now emits the missing `per_file_checksums_sha256` field. Computed as SHA256 of the sorted-paths-then-content text body that goes into the sidecar; deterministic across re-runs.
- **iter13 CLEAN-CODEX-VERDICT-BRIEFS-OMISSION-4 (P1)** FIXED: §3.2 added 4 new rows for ~17 verdict-brief files at reset target verified via `git ls-tree -r 365f334 .codex/ | grep _verdict_brief`: M-INT verdict briefs (9 files), M-LIVE verdict briefs (4 files), M-PROD verdict briefs (3 files), md9 phase 2 verdict briefs (2 files). All A → Cleanup-PR-3 (M-INT) or Cleanup-PR-4 (M-LIVE/M-PROD/md9) batches.
- **iter13 CLEAN-DRAFT-GATE-LEGACY-HIT-2 (P1)** FIXED: §3.7 carney draft preflight clarified — pre-PR-4 raw `git grep` does hit `.codex/carney_*_review_brief.md` (themselves PR-4 archive candidates) and `.legacy/halt_resolutions_abandoned/5.2_halt.md` (do-not-touch). Resolution: gate runs POST-PR-4 (after .codex archives vanish from active tree); `.legacy/` added to count_hits.sh + zero_hit_gate.sh exclusions. Post-PR-4 expected count = 0 active hits.
- **iter13 CLEAN-PR4-SCHEDULE-OMITS-V-LEGACY-1 (P1)** FIXED: §6 Cleanup-PR-4 schedule line expanded to explicitly include V17 + V23 archive batches alongside V27-V30. Plus iter-14 verdict-brief batches.
- **iter13 CLEAN-SCHEDULE-STILL-CONTRADICTS-2 (P1)** FIXED: §3.7 `docs/task_acceptance_matrix.yaml` row updated from "post-PR-14" → "post-Cleanup-PR-8 follow-up PR". `.codex/task_briefs/` row similarly updated.
- **iter13 CLEAN-PR2-RESET-NOOP-1 (P2)** FIXED: §6 Cleanup-PR-2 reduced to "M-INT review briefs ARCHIVE only" (top-level `.codex/m1` through `.codex/m26` files don't exist at reset target — they're under `.codex/_archive_pre_v6_2/` already in PR-4 batch).
- **iter13 CLEAN-OUTPUTS-COUNT-DRIFT-2 (P2)** FIXED: §3.8 outputs row now shows only "209 files (verified iter 13)". Stale "198" reference and parenthetical-within-parenthetical removed.
- **iter13 CLEAN-LEGACY-DNT-INCONSISTENT-1 (P2)** FIXED: §2 do-not-touch list explicitly added `.legacy/` row. Gate scripts (`zero_hit_gate.sh` + `count_hits.sh`) updated with `':!.legacy/'` exclusion. Earlier "§2 do-not-touch already lists" claim was false; now true.

Codex: this is the cleanup audit iter 14. Per CLAUDE.md §8.3 + iter 12 bounded scope policy. List ALL action-row findings; no toothpaste-squeeze.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 13

This iter 13 brief addresses iter-12 findings (8 P1 + 4 P2):

- **iter12 CLEAN-GITIGNORE-INLINE-COMMENT-3 (P1)** FIXED: §4 .gitignore patch rewritten with comments on dedicated lines (no inline trailing `# comment` on rule lines). Same class as iter-4 `.private/` fix.
- **iter12 CLEAN-PR1-STAGED-FILES-OMISSION-1 (P1)** FIXED: §5 Cleanup-PR-1 staged-files list expanded to 10 entries: gitignore patch, delete_pytest_tmpdirs.ps1, delete_pytest_tmpdirs.sh, zero_hit_gate.sh, count_hits.sh, gate_allowlists/.gitkeep, cleanup_pr_dependency_recorder.yml, .ignore, .rgignore, cleanup_manifest.md initial entries, cleanup_pr_dependencies.json initial empty `{}`.
- **iter12 CLEAN-MANIFEST-DELETE-IMPL-2 (P1)** FIXED: §3.3 PowerShell script's placeholder `# ... yaml emit code per §4 schema ...` replaced with two real functions `Append-ManifestEntryDirectory` and `Append-ManifestEntryFile` that emit complete §4-schema YAML to `state/polaris_restart/cleanup_manifest.md` BEFORE Remove-Item. Includes evidence_chain, references_grep, sidecar paths, unreadable_marker, etc.
- **iter12 CLEAN-CODEX-INVENTORY-OMISSION-3 (P1)** FIXED: §3.2 added 6 tracked .codex briefs verified at reset target via `git ls-tree -r 365f334 .codex/`: `carney_delivery_plan_v5_1_review_brief.md`, `_v5_review_brief.md`, `_v6_review_brief.md`, `full_online_plan_brief.md`, `full_online_plan_brief_v3.md`, `strategic_review_brief.md`. All A → Cleanup-PR-3c batch (per iter-17 split).
- **iter12 CLEAN-SCHEDULE-DOC-ARCHIVE-OMISSION-1 (P1)** FIXED: Cleanup-PR-4 schedule line now explicitly includes docs-draft ARCHIVE: `docs/carney_delivery_plan_v5_draft.md`, `docs/carney_delivery_plan_v6_draft.md`, `docs/shippable_plan_v2_draft.md`, `docs/shippable_plan_v3_draft.md`, `docs/shippable_plan_v4_draft.md` plus iter-13 6-brief batch.
- **iter12 CLEAN-DRAFT-GATE-FALSE-PASS-1 (P1)** FIXED: §3.7 carney_delivery_plan_v{5,6}_draft preflight now uses unescaped `|` (since `git grep -E` interprets pipe as regex alternation natively). Documented hard path policy: count = 0 active hits at reset target excluding archive paths.
- **iter12 CLEAN-SCHEDULE-STILL-CONTRADICTS-1 (P1)** FIXED: §5 + §6 prose updated to consistently say "9 PRs sequential `Cleanup-PR-1..Cleanup-PR-9`". "10 PRs / 14 PRs / post-PR-14" stale prose superseded; matrix-decommission referenced as "post-Cleanup-PR-8 follow-up PR".
- **iter12 CLEAN-DEPENDENCY-RECORDER-PUSH-1 (P1)** FIXED: §5 dependency recorder workflow updated with two-tier mechanism: primary = PR self-records its own deps entry (no protected-branch push); fallback = recorder workflow opens auto-merge follow-up PR via `gh pr create`. Works under strict branch protection.
- **iter12 CLEAN-PS-MERKLE-CATCH-PATH-1 (P2)** FIXED: §3.3 `Get-DirectoryMerkleHash` now saves `$file_path = $_.FullName` BEFORE try/catch; catch block uses `$file_path` (string) not `$_.FullName` (which would be ErrorRecord.FullName, doesn't exist).
- **iter12 CLEAN-OUTPUTS-COUNT-DRIFT-1 (P2)** FIXED: §3.8 row updated from "198 files" to "209 files" (verified via `git ls-tree -r 365f334 outputs/ | grep -E '^outputs/(honest_|sweep_r3_final|full_scale)' | wc -l = 209`).
- **iter12 CLEAN-RESET-ABSENT-ACTION-ROWS-1 (P2)** FIXED: §3.2 `.codex/slices/slice_00{2,3,4,5}/golden_drafts/`, `architecture_proposal.md` + drafts, and `walkthrough_screenshots_*` rows reclassified "(NOT present at reset target)" with cleanup-PR no-action note. Earlier ARCHIVE/RENAME+ARCHIVE rows obsoleted.
- **iter12 CLEAN-INSPECT-LIST-STALE-1 (P2)** FIXED: §6 INSPECT list demoted `docs/canonical_pin.txt` (KEEP per iter 12 §3.7) and `tests/v6/` (KEEP per iter 12 §2 tests/* group classification).

Codex: this is the cleanup audit iter 13. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3 + iter 12's bounded scope policy paragraph. List ALL findings; no toothpaste-squeeze; no scope-narrowing; ACTION-rows-only scope per iter 12 binding policy.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 12

**iter 12 SCOPE POLICY (binding for this audit going forward):**

§3 enumerates items that require ARCHIVE / DELETE / RENAME / UPDATE actions in a Cleanup-PR. §2 do-not-touch list + CLAUDE.md §5 active-code layout establishes KEEP-by-default for everything else at reset target `365f334`. Codex review scope is "is the action-requiring list complete?", **NOT** "is every tracked file enumerated?".

A finding of the form "item X is not classified" is valid IFF X is a candidate for ARCHIVE/DELETE/RENAME action that the audit missed (and not already covered by KEEP-by-default). If X is covered by:
- §2 do-not-touch (`src/polaris_graph/`, `src/polaris_v6/`, `src/orchestration/`, `src/auth/`, `src/audit/`, `src/config/`, `src/tools/`, `src/agents/`, `src/benchmarks/`, `src/llm/`, `src/memory/`, `src/providers/`, `src/quality/`, `src/schemas/`, `src/search/`, `src/utils/`, `src/__init__.py`, `tests/*`, `web/*` (except gitignored build outputs), runtime sqlites, `.private/`, `archive/`, `outputs/codex_findings/`)
- Immutable history policy (`outputs/audits/v27/`, `v28/`, `v29/`, `outputs/audits/manifests/{0.5,0.8,...}.json`, `outputs/audits/codex_audit.jsonl`, `outputs/audits/continuous/`, `outputs/audits/verdicts/`, `outputs/honest_*` and related sweep outputs at reset target — 209 files (verified iter 13 via `git ls-tree -r 365f334 outputs/ | grep -E '^outputs/(honest_|sweep_r3_final|full_scale)' | wc -l = 209`))
- CLAUDE.md §5 layout (active production code in `src/*` and `web/*`)

— then the finding is out of scope and the audit is NOT incomplete for omitting it.

This bounds the scope to ~30 ACTION rows + INSPECT subset, not 2477 file enumeration. Per CLAUDE.md §8.3.4 "no scope-narrowing for false convergence": this is not narrowing for convergence — this is the audit's actual scope (action-requiring items only) made explicit so reviewers don't conflate "audit is silent on X" with "audit is wrong about X". X is silent because X is KEEP-by-default.

This iter 12 brief addresses iter-11 findings (9 P1 + 4 P2):

- **iter11 CLEAN-GITIGNORE-UNIGNORE-2 (P1)** FIXED: §4 .gitignore patch corrected per `gitignore(5)` semantics. Bare `state/` excludes the directory and prevents re-include; correct pattern is `state/*` (children) + `!state/polaris_restart/` + `!state/polaris_restart/**`. Verification commands updated.
- **iter11 CLEAN-PR-DEPENDENCY-MECHANISM-1 (P1)** FIXED: §5 added `.github/workflows/cleanup_pr_dependency_recorder.yml` workflow staged in Cleanup-PR-1. On PR merge to `polaris` (head ref starts with `cleanup/pr-`), workflow extracts PR ID + merge_commit_sha, appends to `state/polaris_restart/cleanup_pr_dependencies.json`, commits + pushes to polaris. PR-5 CI's `verify_cleanup_pr_4_merged` step then has a populated dependency file to read.
- **iter11 CLEAN-SCHEDULE-DUPLICATE-1 (P1)** FIXED: §6 sequential PR table — duplicate Cleanup-PR-9 + Cleanup-PR-10 rows REMOVED. Final schedule = `Cleanup-PR-1` through `Cleanup-PR-9` (9 PRs, no duplicates).
- **iter11 CLEAN-OUTPUTS-RESET-SCOPE-2 (P1)** FIXED: §3.8 outputs/honest_sweep_* row CORRECTED. Iter-9 classification "untracked at reset target" was WRONG — verified at reset target via `git ls-tree -r 365f334 outputs/ | grep honest_ | wc -l = 209 files (verified iter 13 via `git ls-tree -r 365f334 outputs/ | grep -E '^outputs/(honest_|sweep_r3_final|full_scale)' | wc -l = 209`) tracked`. Reclassified KEEP per immutability policy. Includes `honest_full_cycle/`, `honest_live_cycle/`, `honest_on_prerebuild_corpus/`, `honest_sweep_r3/`, `honest_sweep_r5_rerun/`, `honest_sweep_r6_validation/`, `sweep_r3_final/`, `full_scale_v30_phase2_run14/`. Active doc references remain valid since paths are KEEP.
- **iter11 CLEAN-TESTS-INVENTORY-OMISSION-2 (P1)** FIXED: §2 do-not-touch list expanded with explicit "tests/ subtree at reset target ~539 files" group classification (KEEP entirely; do-not-touch as group). Cleanup PRs do NOT touch `tests/*` except where iter-9 §3.11 reset-removed slice 2-5 runners (already (NOT present at reset target)).
- **iter11 CLEAN-SRC-INVENTORY-OMISSION-1 (P1)** FIXED: §2 do-not-touch list expanded with `src/agents/`, `src/benchmarks/`, `src/llm/`, `src/memory/`, `src/providers/`, `src/quality/`, `src/schemas/`, `src/search/`, `src/utils/`, `src/__init__.py`. All KEEP per same §2 logic as `polaris_graph/polaris_v6/orchestration`. Cleanup PRs do NOT touch any `src/*` subtree.
- **iter11 CLEAN-DOCS-INVENTORY-OMISSION-2 (P1)** FIXED: §3.7 added rows for `docs/v1_1_backlog.md`, `docs/v1_1_release_notes.md`, `docs/v6_substrate_audit_2026-05-01.md`. Removed nonexistent `docs/architecture.md` (verified absent at reset target — repo-root `architecture.md` is the foundation, no `docs/architecture.md` exists).
- **iter11 CLEAN-TODO-ARCHIVE-REFS-1 (P1)** FIXED: §3.7 `docs/todo_list.md` reclassified ARCHIVE → KEEP. Codex iter 11 verified active refs from CLAUDE.md, state/restart_instructions.md, compliance docs/templates, pipeline_audit_context, ground_rules.md, requirements.txt, src/polaris_graph/retrieval/*, tests. Archiving without atomic ref-update breaks referrers. KEEP as deprecated stub per CLAUDE.md §1.1; separate post-cleanup atomic ref-update PR can later archive both file + refs together.
- **iter11 CLEAN-CARNEY-DRAFT-REFS-1 (P1)** FIXED: §3.7 `docs/carney_delivery_plan_v5_1_redline.md` row split. v5_1_redline reclassified KEEP because `.codex/codex_red_team_checklist.md` (KEEP per §3.2 foundation) actively references it; archiving breaks the checklist. v5_draft and v6_draft remain ARCHIVE candidates pending zero-ref verification at PR-time.
- **iter11 CLEAN-PINS-CLASSIFY-1 (P2)** FIXED: §3.7 `docs/canonical_pin.txt` and `docs/session_pin.txt` reclassified INSPECT → KEEP per Codex iter-11 verified active code/workflows use.
- **iter11 CLEAN-WALKTHROUGHS-CLASSIFY-1 (P2)** FIXED: §3.7 `docs/walkthroughs/` reclassified INSPECT → KEEP per Codex iter-11 verified active references from `task_acceptance_matrix.yaml` and `tests/v6/test_verdict_gate_substrate_prep.py`.
- **iter11 CLEAN-COUNT-HITS-ERRMASK-2 (P2)** FIXED: §5 `count_hits.sh` switched from `git grep ... | wc -l || echo 0` mask-all to explicit exit-code case statement matching `zero_hit_gate.sh` semantics. RC 0 = count via `wc -l`; RC 1 = count = 0; RC 2+ = real error → exit RC.
- **iter11 CLEAN-MANIFEST-DELETE-IMPL-1 (P2)** FIXED: §3.3 PowerShell script extended with `Get-DirectoryMerkleHash` function + per-entry manifest emission BEFORE `Remove-Item`. File deletes record SHA256 + size; directory deletes record merkle_root + per_file_checksums sidecar + permission_denied sidecar per §4 schema. Manifest entries are appended pre-delete for forensic recovery on partial-failure scenarios.

Codex: this is the cleanup audit iter 12. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3. List ALL findings; no toothpaste-squeeze; no scope-narrowing.

**Note for reviewer:** my iter-11 trajectory included Codex's own observation that read-only verification briefly wrote into the workspace `.gitignore` due to a temp-dir creation failure, then restored. Hash verified back to HEAD `23f8ca4`. No persistent harm.

Specific risks to audit on this iter 12:

1. The `state/*` + `!state/polaris_restart/` gitignore pattern — verify on a fresh clone that `git check-ignore state/polaris_restart/cleanup_manifest.md` returns empty (PR-1 includes this as a CI smoke test).
2. The cleanup_pr_dependency_recorder.yml workflow — has `permissions: contents: write` and pushes to `polaris`. Does branch protection allow bot pushes? Should the workflow open a follow-up PR instead?
3. The `Get-DirectoryMerkleHash` function — Windows ACL permission_denied subdirs throw on `Get-FileHash`. Captured into `permission_denied` array; verify the catch-block works for `[System.UnauthorizedAccessException]` specifically.
4. The 198 `outputs/honest_sweep_*` files KEEP — verify §3.2 immutability policy extends correctly. Earlier iter-9 row claimed they were untracked runtime; corrected this iter. Are there OTHER places in the audit that still treat them as untracked?
5. The §3.7 `v5_draft`/`v6_draft` ARCHIVE row's "verify no active refs at PR-time via count_hits.sh = 0" — should this be a hard precondition checked in CI rather than verified at PR review time?
6. The 9-PR final schedule — confirm no other prose in this audit references stale PR numbers (PR-12, PR-13, PR-14 etc.) outside historical iter §8 fix-summaries.
7. Bash 4+ requirement on Windows — does Cleanup-PR-1 ship the gate scripts with a Windows-runnable variant (PowerShell port), or rely on WSL/Git Bash? CI runs on `ubuntu-latest` so bash is fine; local dev box may differ.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 11

This iter 11 brief addresses iter-10 findings (6 P1 + 7 P2):

- **iter10 CLEAN-MANIFEST-GITIGNORE-1 (P1)** FIXED: §4 added explicit `.gitignore` patch for Cleanup-PR-1 with unignore directives `!state/polaris_restart/`, `!state/polaris_restart/**`, `!state/polaris_restart/cleanup_manifest_sidecars/`, `!state/polaris_restart/cleanup_manifest_sidecars/**`, `!state/polaris_restart/cleanup_delete_failures.txt`. Verification step added: `git check-ignore state/polaris_restart/cleanup_manifest.md` must return empty (NOT ignored), `git check-ignore state/pg_checkpoints.sqlite` must return path (still ignored). Cherry-pick state-restart commit MUST include the unignore lines so manifest tracking spans the reset.
- **iter10 CLEAN-GATE-ERRMASK-1 (P1)** FIXED: §5 zero_hit_gate.sh switched from `|| true` (mask-all) to explicit exit-code case statement. RC 0 = process hits, RC 1 = no hits = pass-through, RC 2+ = real error → exit RC. Bad regex/pathspec no longer false-passes.
- **iter10 CLEAN-PR5-PRECONDITION-INVERTED-1 (P1)** FIXED: §5 added separate `scripts/cleanup/count_hits.sh` script for preflight counts. Returns hit count via stdout; optional EXPECTED_COUNT param exits 1 on mismatch. PR-5 hard precondition rewritten: `count_hits.sh "REVIEW_BRIEF_FORMAT_v2|AUDIT_CYCLE_PROTOCOL_v2" 8` (returns 0 + stdout=8 on success). zero_hit_gate.sh remains POST-rename verification.
- **iter10 CLEAN-ORDER-ENFORCEMENT-1 (P1)** FIXED: §5 replaced fictional "GitHub branch protection required PR order" with three real options (A: branch stacking, B: GitHub merge queue, C: CI ancestry check via `git merge-base --is-ancestor`). Recommendation: Option C — simplest, fail-loudly per LAW II, no GitHub feature dependencies. PR-5 CI workflow includes `verify_cleanup_pr_4_merged` step reading `state/polaris_restart/cleanup_pr_dependencies.json` for PR-4's merge-commit SHA.
- **iter10 CLEAN-STATE-INVENTORY-OMISSION-1 (P1)** FIXED: §3.9 added explicit rows for tracked state/ items at reset target verified via `git ls-tree -r 365f334 state/`: 8 `autoloop_handover_*.md` files (ARCHIVE), `compare_chatgpt_dr.txt` + `compare_gemini_dr.txt` (KEEP per BEAT-BOTH memory), `v17_vs_tier1_headtohead.md` (KEEP per autoloop_beat_tier1_mandate memory), `restart_instructions.md` (UPDATE per plan §9). Earlier untracked-runtime sqlites reclassified as "(untracked at reset target)" per CLEAN-STATE-RUNTIME-ABSENT-1 distinction.
- **iter10 CLEAN-DOCS-INVENTORY-OMISSION-1 (P1)** FIXED: §3.7 added rows for ALL tracked docs/ items at reset target. New rows: `backend_modernization.md`, `benchmark/`, `carney_handover/`, `carney_delivery_plan_v5_1_redline.md` + `_v5_draft.md` + `_v6_draft.md` (ARCHIVE drafts), `compliance_templates/`, `gemma_4_verification.md`, `hardware_decision.md`, `live_code_audit.json`, `md{1..11}_*_threat_model.md` (~14 files), `opentelemetry_genai.md`, `pipeline_audit_context/`, `pricing_and_positioning.md`, `release_notes_v1.0.md`, `session_pin.txt` (INSPECT alongside canonical_pin.txt), `shippable_plan_{v2,v3,v4}_draft.md` (ARCHIVE), `supported_scope.md`, `todo_list.md` (ARCHIVE — deprecated stub per CLAUDE.md §1.1), `walkthroughs/` (INSPECT).
- **iter10 CLEAN-BASH-VERSION-1 (P2)** FIXED: §5 zero_hit_gate.sh declares Bash 4+ requirement explicitly with `BASH_VERSINFO[0] -lt 4` check at top, exits 64 if older. macOS users must `brew install bash` and run `#!/usr/bin/env bash` resolves correctly (or invoke explicitly).
- **iter10 CLEAN-COUNT-TABLE-CONSISTENCY-1 (P2)** FIXED: §5 added pre/post-PR-4 count tables for all 4 rename patterns: `_v2` protocol files (11 raw → 8 post-PR-4), `pg_preflight_v2` (7 → 7 unchanged), `carney_delivery_plan_FINAL` (4 → 2), `full_online_plan_FINAL` (8 → 6). Each has explicit hard-precondition `count_hits.sh` invocation.
- **iter10 CLEAN-STATE-RUNTIME-ABSENT-1 (P2)** FIXED: §3.9 distinguishes "(untracked at reset target — gitignored runtime)" from "(NOT present at reset target)". Runtime sqlites and `state/progress_ledger.jsonl` etc. reclassified to gitignored-runtime.
- **iter10 CLEAN-PR8-NOOP-1 (P2)** FIXED: Cleanup-PR-8 (was outputs ARCHIVE) COLLAPSED since zero ARCHIVE/DELETE/RENAME actions after iter 10 reset-absent reclassification. State PR renumbered Cleanup-PR-8; file_directory regen renumbered Cleanup-PR-9. Final schedule = **9 PRs** sequential.
- **iter10 CLEAN-REN-ROW-STALE-1 (P2)** FIXED: §3.10 `pg_preflight_v2` row now lists all 7 active files (added `ground_rules.md`) and self-refs note. Aligned with §5 PR-6 authoritative list.
- **iter10 CLEAN-SCRIPTS-COUNT-1 (P2)** FIXED: §3.10 header replaced "130 total per CLAUDE.md §5" with "219 files at reset target `365f334`" (verified `git ls-tree -r 365f334 scripts/ | wc -l`). CLAUDE.md update deferred to PR-B DNA pass.
- **iter10 CLEAN-CLAUDE-SETTINGS-1 (P2)** FIXED: §3.10 added explicit row classification block for `.claude/` (3 tracked items at reset target): `settings.json` (KEEP), `precommit_codex_verdict.py` (INSPECT), `stop_hook_v3.py` (INSPECT).

Codex: this is the cleanup audit iter 11. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3. List ALL findings; no toothpaste-squeeze; no scope-narrowing.

Specific risks to audit on this iter 11:

1. The .gitignore patch with `!state/polaris_restart/` unignore — verify the order of lines in the resulting `.gitignore` correctly overrides the parent `state/` rule. Some git versions require specific ordering. Should the patch include a `git check-ignore` smoke test in PR-1's CI?
2. The CI ancestry check (Option C) — relies on `state/polaris_restart/cleanup_pr_dependencies.json` being present and correctly populated post-PR-4. Who/what populates this file? PR-4's merge action? A separate Cleanup-PR-4-followup PR? Mechanism missing.
3. The 8 `state/autoloop_handover_*.md` ARCHIVE — verify these are not actively referenced from current scripts/src code. Move to `archive/2026-05-05/state_autoloop_handovers/`.
4. The 14 `docs/md*_threat_model.md` files KEEP — should some be ARCHIVED if their underlying M-D milestones are superseded by Carney v6.2 phases? Per memory `project_phase_d_status` Phase D is COMPLETE for 16 milestones; threat models may be stale.
5. The `docs/walkthroughs/` INSPECT — verify what's inside; per memory `bpei_phantom_completion_lessons` walkthroughs are critical user-facing artifacts.
6. The `docs/canonical_pin.txt` + `docs/session_pin.txt` INSPECT — both pin-related; verify which Plan v6.2 keeps and which is Plan-v13-era stale.
7. Comprehensive sweep: are there other tracked items at reset target I haven't classified? Suggested next pass: enumerate `tests/`, `web/`, `src/`, `outputs/codex_findings/`, `archive/` at reset target completeness.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 10

This iter 10 brief addresses iter-9 findings (2 P1 + 4 P2):

- **iter9 CLEAN-OUTPUTS-RESET-SCOPE-1 (P1)** FIXED: §3.8 outputs/audits/ rows reclassified per `git cat-file -e 365f334:<path>` verification:
  - ABSENT at reset target (reclassified "(NOT present at reset target)"; no cleanup PR action; `pre_restart_2026_05_05` tag preserves): `codex_approved_design_2026-05-03_FINAL.md`, `codex_consultation_2026-05-03_*` files, `codex_response_round*.txt`, `manifests/5.2.json`, `v6_2_phase_2_speculative_review_brief.md`, `verdicts/5.2/`, `pipeline_full_demo/`, `pipeline_smoke/`, `handover_bundles/`, `briefs/`.
  - PRESENT at reset target (KEEP per immutability policy): `codex_audit.jsonl`, `manifests/{0.5,0.8,0_6_hardware_decision_doc,3_5_prep_api_benchmark_runner,bootstrap_smoke}.json`, `v27/` (already iter 7), `v28/`, `v29/`, `verdicts/`.
  Cleanup-PR-8 schedule prose updated: "likely no-op or near-no-op since most §3.8 ARCHIVE candidates are reset-absent". May collapse into PR-9.
- **iter9 CLEAN-PR7-STALE-8FILE-1 (P1)** FIXED: §3.7 `docs/carney_delivery_plan_FINAL.md` row corrected — replaces stale "8 active files" wording with "Cleanup-PR-7 sub-pattern A reduces to reference-substitution in 2 active files". Also fixed iter-7 §8 fix-summary line that re-asserted "8 active files" — clarified that iter-9 CLEAN-PR7-REFLIST-1 corrected this attribution.
- **iter9 CLEAN-PS1-INIT-IN-BLOCK-1 (P2)** FIXED: §3.3 PowerShell delete script — `$deletedPaths = @()` and `$failedPaths = @()` initializers moved INSIDE the fenced script block (immediately before `$count = 0`). Script is now runnable as-pasted with no out-of-band setup. The post-fence sidebar re-noted with cross-reference.
- **iter9 CLEAN-INSPECT-RESET-SCOPE-1 (P2)** FIXED: §6 INSPECT list demoted reset-absent items via `git cat-file -e 365f334:<path>` for each. Demoted (NOT present at reset target; no cleanup PR action): `outputs/audits/handover_bundles/`, `outputs/audits/briefs/`, `state/active_audit/`, `state/active_pending.json`, `state/progress_ledger.jsonl`, `state/last_pointer.json`, `state/orchestrator_status.json`, `.github/workflows/m_live_4_regression_gate.yml.pending_workflow_scope`. Remaining INSPECT (verified PRESENT at reset target): `docs/canonical_pin.txt`, `docs/test_failure_triage_2026-04-27.md`, `docs/phase_d_milestones.md`, `scripts/autoloop/*`, `.claude/hooks/*`, `tests/v6/`, `helm/`, `.github/workflows/codex_verdict_check.yml`, 95+ scripts.
- **iter9 CLEAN-GATE-ALLOWLIST-ANCHOR-1 (P2)** FIXED: §5 zero_hit_gate.sh allowlist matching switched from substring `grep -qF "$prefix"` to anchored exact-prefix via bash associative array `ALLOWLIST_SET[$prefix]` lookup. False-allow risk eliminated (e.g., entry `path:5:` no longer matches `path:50:` lines).
- **iter9 CLEAN-PR5-PREPOST-COUNT-1 (P2)** FIXED: §5 PR-5 entry now contains pre/post-PR-4 count table (pre-PR-4 raw = 11 hits including 3 `.codex/v6_phase_0_1_*` brief files; post-Cleanup-PR-4 = 8 active files). Hard precondition added: before opening PR-5, gate run after PR-4 merge MUST report exactly 8 active files; abort and re-iterate PR-4 if count differs.

Codex: this is the cleanup audit iter 10. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3. List ALL findings; no toothpaste-squeeze; no scope-narrowing.

Specific risks to audit on this iter 10:

1. The §3.8 reclassification: `outputs/audits/v28/` and `v29/` are now KEEP — verify Codex agrees these tracked subtrees should be preserved per immutability vs. archived.
2. The pre/post-PR-4 count table for `_v2` rename: should similar tables be added for `pg_preflight_v2` and `carney/full_online_FINAL` patterns? The user stated "exhaustive findings"; consistent enumeration is the safer call.
3. The bash associative-array allowlist mechanism: requires bash 4+ (`declare -A`). On macOS default bash 3.2 this fails. Should the gate script declare a portable shell version, or is bash 4+ a hard requirement we declare for the cleanup script's runtime?
4. The reset-absent demotion in §6 INSPECT list: `state/progress_ledger.jsonl` and `state/last_pointer.json` are gitignored runtime files per CLAUDE.md §5; their absence at `365f334` reflects gitignore status, not "removed". Should §6 distinguish "untracked-runtime-absent" from "tracked-but-removed"?
5. The Cleanup-PR-8 collapsing into PR-9 — if PR-8 has zero work after iter 10 reclassification, should the schedule renumber to 9 PRs (PR-1..PR-9) or keep 10 with explicit "PR-8 = no-op manifest entry only"? Convention pick.
6. The "Hard precondition for Cleanup-PR-5" — is this a CI gate enforced via GitHub Actions, or a documented handoff for the human PR reviewer? Mechanism pick.
7. Are there any other rows in §3 still classifying (ARCHIVE/RENAME/DELETE/INSPECT) reset-absent items I haven't caught? Comprehensive sweep needed.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 9

This iter 9 brief addresses iter-8 findings (5 P1 + 4 P2):

- **iter8 CLEAN-PR7-REFLIST-1 (P1)** FIXED: §3.2 + §5 PR-7 split into two sub-patterns. `carney_delivery_plan_FINAL` real touch list = 2 active files (`docs/carney_delivery_plan_v6_2.md` + `state/restart_instructions.md`); reference-update-only (file does not exist at reset target). `full_online_plan_FINAL` real touch list = 6 active files (3 scripts + 3 tests); standard atomic `git mv` + ref update. Each sub-pattern runs its own zero-hit gate. Verified by direct `git grep -l "<pattern>" 365f334 --` for each pattern separately.
- **iter8 CLEAN-PR-NUMBERING-4 (P1)** FIXED: §5 the entire old numbered list (Cleanup-PR-1..PR-14 with dropped PR-8/9/10/11 entries, including the stale "Cleanup-PR-12 outputs ARCHIVE: §3.8 ... outputs/audits/v25/v26/v27" entry) DELETED. Section now points to the sequential `Cleanup-PR-1..Cleanup-PR-10` table in §6. No prose contradiction.
- **iter8 CLEAN-REN-HISTORICAL-POLICY-3 (P1)** FIXED: §5 PR-5 prose REMOVED `outputs/audits/continuous/` from touch list. Earlier "CLEAN-REN-AUDIT-REFS-1" prose was wrong — `outputs/audits/continuous/` is historical immutable payload, EXCLUDED from rename gates per the canonical gate spec, NEVER updated. PR-5 touch list now solely contains the 8-file post-PR-4 active list.
- **iter8 CLEAN-MANIFEST-STUB-2 (P1)** FIXED: §5 cherry-pick stub schema replaced `entries: []` with `entries:` followed by indented comment placeholder. Append-friendly YAML form; PR-1 can append `- entry_id: ...` items without rewriting the stub line.
- **iter8 CLEAN-OUTPUTS-DOCREF-1 (P1)** FIXED: §3.8 `outputs/honest_sweep_*` row reclassified — verified at reset target via `git ls-tree`: `honest_sweep_*` subdirs are gitignored runtime artifacts, NOT tracked. Cleanup PRs cannot touch them via git. Active doc references (CLAUDE.md, README.md, architecture.md, runbook.md, release_notes_v1.0.md, v1_1_backlog.md, pipeline_audit_context/{00,01,02,03,04,07,08,10,11}, file_directory.md, test_failure_triage_2026-04-27.md, scripts/docker_entrypoint.sh — 19+ files) remain valid because the dirs are still expected runtime output paths. Earlier ARCHIVE row was wrong (would have implied `git rm` on untracked paths); removed.
- **iter8 CLEAN-REN-REFLIST-SCOPE-1 (P2)** FIXED: §5 PR-5 8-file `_v2` rename list explicitly qualified as "post-Cleanup-PR-4". Pre-PR-4 raw count includes `.codex/v6_phase_0_1_*_review_brief.md` + `.codex/_archive_pre_v6_2/`, `.codex/continuous/`, etc.; PR ordering invariant (PR-4 before PR-5) makes the 8-file list operative at PR-5 execution time.
- **iter8 CLEAN-M54-DEST-1 (P2)** FIXED: §3.2 m54 collision rows' archive destinations corrected from `codex_briefs_milestones_m28_to_m72` → `codex_briefs_milestones_m28_to_m63` per iter-8 CLEAN-INVENTORY-RANGE-2 range tightening.
- **iter8 CLEAN-GATE-ALLOWLIST-1 (P2)** FIXED: §5 zero_hit_gate.sh allowlist convention clarified: entries are `<path>:<lineno>:` (with trailing colon) to anchor on grep -n line boundary. Code's `path:line:` matching now consistent with documented convention.
- **iter8 CLEAN-STALE-NOOP-ROWS-1 (P2)** FIXED: §3.2/§3.7/§3.8/§3.10/§3.11 reset-removed rows rewritten. Affected rows for post-drift scripts (8 files), slice 2-5 golden runners, post-drift tests, post-PR-72 docs (mission_status, demo_runbook, demo_e2e), post-drift demo outputs (pipeline_full_demo, pipeline_smoke), post-drift demo benchmark (clinical_n10_demo etc.) — all changed from "ARCHIVE → archive/2026-05-05/post_drift_*" to "(NOT present at reset target) | no cleanup PR action; tag pre_restart_2026_05_05 preserves for forensic recovery". Eliminates executor confusion.

Codex: this is the cleanup audit iter 9. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3.

Specific risks to audit on this iter 9:

1. The PR-7 split (carney 2 files vs full_online 6 files) — should this be ONE PR with two atomic sub-operations, or split into Cleanup-PR-7a (carney ref-update-only) and Cleanup-PR-7b (full_online mv + ref-update)? Atomic-PR convention pick.
2. The post-PR-4 qualification of PR-5 8-file list — is this clear enough to a future executor, or does the brief need a dedicated "Pre-Cleanup-PR-4 vs Post-Cleanup-PR-4 raw count" enumeration table? Convention pick.
3. The append-friendly manifest stub — does PR-1 require a CI step that re-validates the YAML (e.g., `python -c "import yaml; yaml.safe_load(open('state/polaris_restart/cleanup_manifest.md').read())"`) after each append, OR is this enforced by Codex review only?
4. The `outputs/honest_sweep_*` "no cleanup PR action" classification — do any of the 19+ doc references need updating to reflect that these dirs are runtime-generated and not part of source-controlled state? E.g., should runbook.md explicitly say "outputs/honest_sweep_*/ is created at runtime by run_honest_sweep_r3.py"? Convention pick.
5. The reset-removed row rewrites — the §6 INSPECT list still references items that may or may not be at reset target; should §6 also be re-verified against `365f334` and reset-removed items demoted to a "preserved in pre_restart_2026_05_05 tag for forensic recovery; not part of cleanup scope" sub-list?
6. The gate allowlist `<path>:<lineno>:` convention — bash `grep -qF` matches substrings; `path:line:` could false-match `path:line:5:` if line 5 starts with content matching pattern. Should the match be anchored (`^<path>:<lineno>:` regex with `grep -qE`) instead?
7. The 9-iter trajectory now stands at: 1 P0 (iter 1 CLEAN-EXEC-1, fixed iter 2), 5 continuing P0 trajectory was always 0 except iter 1, plus per-iter P1/P2 distinct findings ~30+ total, ~25 catastrophic-or-real-failure-class. Fully consistent with feedback_codex_iteration_no_cap_no_toothpaste.md memory entry.

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 8

This iter 8 brief addresses iter-7 findings (4 P1 + 6 P2):

- **iter7 CLEAN-REN-REFS-4 (P1)** FIXED: §3.2 protocol-rename rows + §5 PR-5/6/7 prose now contain AUTHORITATIVE rename-touch lists VERIFIED by direct `git grep -l ... 365f334 --` execution at reset target. The 8-file list for `_v2` protocol files (stop_hook_v3.py, CLAUDE.md, canonical_pin.txt, codex_verdict.schema.json, autoloop/orchestrator.py, strip_changelog_markers.py, polaris_v6/memory/store.py, test_workspace_memory.py) is now complete. The 7-file list for pg_preflight_v2 (CLAUDE.md, soc2_evidence_map.md, file_directory.md, env_var_inventory.md, ground_rules.md, docker_entrypoint.sh, pg_preflight_v2.py self) is complete. Iter 7 misattributions (schema/orchestrator/strip_changelog/store.py/test_workspace wrongly bucketed under pg_preflight) corrected.
- **iter7 CLEAN-TASKBRIEFS-MATRIX-2 (P1)** FIXED: §3.2 task_briefs row updated. Verified at reset target: `.codex/task_briefs/` does NOT exist at `365f334` (empty `git ls-tree`). Cleanup PRs touch nothing. The matrix.yaml at `365f334` does still contain stale internal references to `.codex/task_briefs/v6_phase_0_1_substrate_round_3_review_brief.md` and `.codex/task_briefs/**` — that is a stale-internal-ref issue in the matrix YAML resolved by the post-PR-14 (now Cleanup-PR-10-followup) matrix-decommission PR, NOT by this cleanup audit.
- **iter7 CLEAN-OUTPUTS-CONTRADICTION-2 (P1)** FIXED: §3.8 v25/v26/v27 ARCHIVE row REMOVED. Verified at reset target: v25/ and v26/ do NOT exist at `365f334`; v27/ DOES exist and is now KEEP per §3.2 immutability policy. PR-12 (now Cleanup-PR-8) schedule no longer touches `outputs/audits/v25-27`.
- **iter7 CLEAN-DOC-RENAME-MISSING-1 (P1)** FIXED: §3.7 row updated — `docs/carney_delivery_plan_FINAL.md` does NOT exist at `365f334` (verified via `git ls-tree -r --name-only 365f334 docs/`). PR-7 (now Cleanup-PR-7) DROPS the `git mv` for this name. (Note: the iter-9 CLEAN-PR7-REFLIST-1 fix corrected this iter-8 attribution: real touch list is 2 files for `carney_delivery_plan_FINAL` and 6 for `full_online_plan_FINAL`, not 8 files for `carney`. See iter-9 §8 fix-summary.) `full_online_plan_FINAL.md` DOES exist; standard atomic `git mv` + ref update.
- **iter7 CLEAN-GATE-COMMENT-2 (P2)** FIXED: §5 zero_hit_gate.sh REMOVED the indiscriminate `^[^:]*:[0-9]+:[[:space:]]*#` strip. Replaced with per-pattern allowlist file at `scripts/cleanup/gate_allowlists/<pattern_slug>.txt` (one `path:line` entry per line, empty by default, reviewed in PR). Markdown headings, multiline-string boundaries, Python comments — none auto-stripped.
- **iter7 CLEAN-INVENTORY-RANGE-2 (P2)** FIXED: §3.2 ranges tightened. Verified at reset target via `git ls-tree -r --name-only 365f334 .codex/ \| grep '^\.codex/m[0-9]'` and `... '^\.codex/v[0-9]'`:
  - M-range: M28-M63 only (gaps at m39, m49, m53). M64-M72 do NOT exist at reset target.
  - V-range: V6, V17, V23, V27, V28, V29, V30 only. V31-V33 do NOT exist at reset target.
  - Iter 7 row "v28-v33 38 files" is wrong; replaced with V27-V30 row (and separate V17/V23 row). Iter 6 row "m28-m72 78 files" is wrong; replaced with M28-M63 row.
- **iter7 CLEAN-HELM-EVIDENCE-1 (P2)** FIXED: §3.2 helm/ row reclassified KEEP-pending-inspect; added to §6 INSPECT list. Default behavior: cleanup PRs do NOT touch helm/.
- **iter7 CLEAN-DELETE-ACL-1 (P2)** FIXED: §3.3 PowerShell delete script wrapped `Remove-Item` in try/catch. Failed paths captured to `state/polaris_restart/cleanup_delete_failures.txt` with path + error type + message. Apply mode exits with code 3 on partial failure; PR-1 review halts on this signal.
- **iter7 CLEAN-PR-NUMBERING-3 (P2)** FIXED: Sequential renumbering adopted. Cleanup-PR-1 through Cleanup-PR-10 (no gaps). Old → new ID mapping table added in §6 prose. All §5 prose references new IDs.
- **iter7 CLEAN-CHERRYPICK-STUB-1 (P2)** FIXED: §5 cherry-pick step now specifies `cleanup_manifest.md` is a Codex-APPROVE'd schema-header stub (not empty file). Stub YAML content shown inline; PR-1 appends entries onto stable schema target.

Codex: this is the cleanup audit iter 8. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3.1-§8.3.4. List ALL findings; do NOT toothpaste-squeeze across iterations.

Specific risks to audit on this iter 8:

1. The 8-file `_v2` protocol rename touch list — verified by `git grep -l 365f334 --`, but each file's actual line-level reference count was not enumerated (file count yes, hit count per file no). Is per-file hit count needed for atomic-PR review, or is path list sufficient?
2. The 7-file `pg_preflight_v2` rename — `scripts/pg_preflight_v2.py` itself has self-references that change in same PR (sha256_old != sha256_new). Manifest schema in §4 already accommodates this (CLEAN-MANIFEST-RENAME-1 fix iter 5); confirm §4 schema is sufficient.
3. The 8-file `carney_delivery_plan_FINAL` reference-update list — should this be its own Cleanup-PR separate from `full_online_plan_FINAL.md` rename, since the operations are different (mv vs ref-update-only) and a single failed ref-update shouldn't block the mv? Convention pick.
4. Sequential renumbering Cleanup-PR-1..10 — does any other doc in `state/polaris_restart/` reference the old PR-N IDs? Sanity check needed before commit.
5. The `cleanup_manifest.md` stub schema — does it correctly document all directory-archive fields (permission_denied_sidecar_path, merkle_root_sha256, per_file_checksums_sidecar_path, unreadable_marker)? Is the schema sufficiently formal for PR-1 to validate its own additions against?
6. The gate allowlist mechanism — is `scripts/cleanup/gate_allowlists/<pattern_slug>.txt` the right convention, or should it be inline in the cleanup_audit row that justifies the allowlist? Convention pick.
7. M28-M63 enumeration — the gaps at m39/m49/m53 were noted in this iter. Should those gap milestones be explicitly asserted (e.g., "m39 does not exist; m49 does not exist; m53 does not exist") so a future PR-2 reviewer doesn't worry that briefs were missed? Convention pick.
8. PR-1 delete-failure manifest at `state/polaris_restart/cleanup_delete_failures.txt` — should this path be added to the cherry-pick (so it has a Codex-APPROVE'd location) or created on first PR-1 apply-mode failure?

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 7

This iter 7 brief addresses iter-6 findings (4 P1 + 4 P2):

- **iter6 CLEAN-TARGET-INVENTORY-3 (P1)** FIXED: §3.2 added 14 new rows for verified-at-reset-target items via `git ls-tree -r 365f334`: `.codex/REVIEW_BRIEF.md`, `.codex/ROUND_N_BRIEF_TEMPLATE.md`, `.codex/loop_state.json`, `.codex/config.toml`, 38 v28-v33 brief files (verified count: `git ls-tree | grep -E "v2[7-9]_|v3[0-3]_" | wc -l = 38`), `outputs/audits/{continuous,v27,v28,v29,v30_phase2,verdicts,manifests}/`, `.legacy/`, `logs/`, `config/`, `helm/`. All rows reference what their KEEP/ARCHIVE classification is at reset target.
- **iter6 CLEAN-REN-REFS-3 (P1)** FIXED: §5 PR-5/6/7 sections now contain explicit ACTIVE-rename-touch lists at reset target `365f334`. For `pg_preflight_v2`: 13 files including ground_rules.md (1 hit), state/restart_instructions.md (3 hits). For `REVIEW_BRIEF_FORMAT_v2|AUDIT_CYCLE_PROTOCOL_v2`: 4 files (stop_hook_v3.py + CLAUDE.md + canonical_pin.txt + carney_delivery_plan_v6_2.md). For `carney_delivery_plan_FINAL`: 2 files post-PR-4 (state/restart_instructions.md + docs/carney_delivery_plan_v6_2.md). PR ordering invariant added: PR-4 archives `.codex/*` briefs BEFORE PR-5/6/7 so renames don't have to update files no longer present.
- **iter6 CLEAN-OUTPUTS-SCHEDULE-1 (P1)** FIXED: §3.2 explicit row added classifying `outputs/audits/v27/`, `v28/`, `v29/`, `v30_phase2/`, `continuous/`, `verdicts/`, `manifests/` all as KEEP at reset target per immutability policy. Earlier iter `v25/v26/v27` ARCHIVE classification was wrong for reset target — those don't exist there as the v25/v26 trees claimed; reset has v27-v30_phase2 as KEEP audit history. Schedule corrected.
- **iter6 CLEAN-GATE-EXEC-1 (P1)** FIXED: §5 PR-5 / PR-6 / PR-7 canonical gate replaced with `scripts/cleanup/zero_hit_gate.sh` wrapper script that captures `git grep` output via `|| true` (handles zero-match nonzero exit), then evaluates output: empty = pass, non-empty after comment-strip = fail. Replaces the broken `git grep ... | grep -v ...` pipe-chain that was failing CI on zero matches.
- **iter6 CLEAN-PR-NUMBERING-2 (P2)** FIXED: §6 prose now correctly states "10 PRs total numbered PR-1..PR-7 + PR-12..PR-14 with PR-8..PR-11 dropped per CLEAN-POSTRESET-SCHEDULE-2". Iter 5 prose `PR-1 through PR-14` and any residual `12 PRs` stale references replaced.
- **iter6 CLEAN-BASH-FALLBACK-2 (P2)** FIXED: §3.3 bash `ALLOWLIST` now includes `outputs/codex_tmp_pytest`, `outputs/pytest_basetemp`, `outputs/pytest_temp`, `outputs/pytest_tmp` plus `write_probe_root.txt`, achieving full parity with PowerShell allowlist.
- **iter6 CLEAN-INSPECT-STALE-2 (P2)** FIXED: §6 INSPECT list narrowed. Items definitively classified KEEP elsewhere (`.private/codex_hmac.key` per §3.6, `docs/task_acceptance_matrix.yaml` per §3.7, 6 small state sqlites per §3.9) and ARCHIVE (`.codex/task_briefs/` per §3.2) are now strikethrough'd from INSPECT with cross-reference. Remaining INSPECT count reduced from 19+ to ~13 truly-needs-future-iter items.
- **iter6 CLEAN-REN-HISTORICAL-POLICY-2 (P2)** FIXED: §5 PR-5/6/7 canonical gate spec now explicitly excludes the full historical-policy path set (`archive/`, `state/polaris_restart/`, `outputs/audits/`, `outputs/codex_findings/`, `.codex/_archive_pre_v6_2/`, `.codex/continuous/`, `.codex/round_*/`, `.codex/deep_dive_round_*/`, `logs/session_log.md`). Prose explicitly clarifies these are EXCLUDED from rename gates per immutability policy, NOT updated. Earlier rename-row prose wrongly implied refs in `.codex/_archive_pre_v6_2/` and `.codex/continuous/` would be updated; corrected.

Codex: this is the cleanup audit iter 7. Same verdict format. Same exhaustivity bar regardless of iter count per CLAUDE.md §8.3.

Specific risks to audit on this iter 7:

1. The 14 new rows in §3.2 for reset-target items (`.legacy/`, `helm/`, `logs/`, `config/`, `outputs/audits/v27..v30_phase2/`) — any classified KEEP that is actually stale or was supposed to ARCHIVE? In particular `helm/` is an unverified-vs-active classification.
2. The PR ordering invariant (PR-4 before PR-5/6/7) — any case where a file ARCHIVED in PR-4 is also referenced in a non-archive path that PR-5/6/7 would still need to update?
3. The canonical gate spec wrapper script (`scripts/cleanup/zero_hit_gate.sh`) — completeness: does the comment-strip regex `^[^:]*:[0-9]+:[[:space:]]*#` correctly handle Python `#` comments, YAML `#` comments, Markdown reference-style links containing `:` characters, multiline-string boundaries?
4. The bash variant allowlist now matches PowerShell. But `write_probe_root.txt` is a file not a directory — does the bash `[[ -e ... ]]` test handle it correctly with `rm -rfv`? PowerShell `Remove-Item -Recurse -Force` does. Symmetry check.
5. iter 7 clarification of `.codex/loop_state.json` KEEP — is this Plan-v13-specific runtime data that should ARCHIVE if Plan v13 is being deprecated, or is it canonical autoloop V2 state?
6. iter 7 INSPECT narrowing — are any of the strikethrough'd items actually still needing INSPECT review because the iter-3-or-4 classification fix was incomplete?
7. The PR numbering "10 PRs (gap PR-8..PR-11 dropped)" — should the schedule renumber to sequential PR-1..PR-10, OR keep the gap so PR numbers remain stable across iterations? Convention pick.
8. §5 cherry-pick-state-restart preservation — does `state/polaris_restart/cleanup_manifest.md` (empty stub) need to be Codex-APPROVE'd as part of the cherry-pick content, or can it be created blank in cherry-pick and populated by PR-1?

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

---

## §8 Codex review request iter 6

This iter 6 brief addresses iter-5 findings (7 P1 + 2 P2):

- **iter5 CLEAN-CODEX-INVENTORY-2** FIXED: §3.2 added explicit rows for `m28-m72` series (~78 files), `v27/v30/v31/v32/v33` briefs, `shippable_plan_*` briefs (3 files), `v6_phase_0_1_*` briefs. All routed to `archive/2026-05-05/` subdirs. PR-4 schedule references these batches.
- **iter5 CLEAN-EXEC-PS1-ENUM-1** FIXED: §3.3 PowerShell script now uses `Get-Item -LiteralPath` for non-wildcard literal paths (matches the directory itself) and `Get-ChildItem -Filter` only when pattern contains `*` or `?`.
- **iter5 CLEAN-OUTPUTS-ALLOWLIST-2** FIXED: §3.3 PowerShell `$allowlist` now includes `outputs\codex_tmp_pytest`, `outputs\pytest_basetemp`, `outputs\pytest_temp`, `outputs\pytest_tmp`.
- **iter5 CLEAN-GATE-SCOPE-2** FIXED: §5 PR-5/6/7 all use identical canonical gate spec with explicit exclusions for `archive/`, `state/polaris_restart/`, `outputs/audits/`, `outputs/codex_findings/`, `.codex/_archive_pre_v6_2/` plus comment exclusion. Loose `rg` documented inadequate.
- **iter5 CLEAN-POSTRESET-SCHEDULE-2** FIXED: §5 Cleanup-PR-8 explicitly DROPPED (post-drift scripts not at reset target); PR-9, PR-10, PR-11 explicitly DROPPED for same reason. Pre-reset content preserved in `pre_restart_2026_05_05` tag, not in active branch. Schedule reduced to PR-1 through PR-7 + PR-12 (state) + PR-13 (file_directory regen).
- **iter5 CLEAN-MATRIX-CONTRADICTION-2** FIXED: `docs/task_acceptance_matrix.yaml` now classified KEEP unambiguously in §3.7 (was INSPECT). §5 PR-4 explicitly excludes it. Decommission deferred to a separate post-PR-14 atomic PR.
- **iter5 CLEAN-V6-PHASE-REFS-1** FIXED: `.codex/v6_phase_0_1_*` row added to §3.2 classification table (was prose-only).
- **iter5 CLEAN-M54-COLLISION-1** FIXED: `.codex/m54_code_audit_brief.md` and `_v2` variant both archived with disambiguating `_v1`/`_v2` suffix in archive path; original RENAME row marked superseded.
- **iter5 CLEAN-PR1-RGIGNORE-STAGE-1** FIXED: §5 Cleanup-PR-1 staged-files list explicitly includes `.ignore` and `.rgignore`.

Codex: this is the cleanup audit iter 6. Verdict format same as plan iter 4:

This iter 5 brief addresses iter-4 findings (8 P1 + 5 P2):

- **iter4 CLEAN-RESET-TAGS-1** FIXED: §5 pre-reset checklist now requires `pre_restart_2026_05_05` tag verification step BEFORE reset. HALT if absent.
- **iter4 CLEAN-RESET-STATE-1** FIXED: §5 introduces cherry-pick-state-restart step between archived-tags and reset. The `state/polaris_restart/*` files are carried forward as a one-commit cherry-pick onto `365f334`. Reset target = cherry-pick HEAD, not raw `365f334`. Audit substrate preserved across reset.
- **iter4 CLEAN-EXEC-WINDOWS-1** FIXED: §5 Cleanup-PR-1 now stages `scripts/cleanup/delete_pytest_tmpdirs.ps1` (NOT `.sh`). PowerShell canonical on Windows. Bash variant remains optional Linux fallback.
- **iter4 CLEAN-MATRIX-LIVE-1** FIXED: §5 Cleanup-PR-4 reclassifies `docs/task_acceptance_matrix.yaml` as KEEP (not archived in PR-4). Separate decommission PR (post-PR-14) handles it atomically with all referencing files. Archives only `task_briefs/` content (which references matrix, not vice versa per Codex iter 3 confirmation).
- **iter4 CLEAN-REN-GATE-1** FIXED: §5 Cleanup-PR-5 zero-hit gate uses `git grep -n -E ... -- ':!archive/' ':!state/polaris_restart/cleanup_manifest_sidecars/'` (tracked-only, path-explicit). Loose `rg` is documented as inadequate.
- **iter4 CLEAN-REN-AUDIT-REFS-1** FIXED: §5 Cleanup-PR-5 explicitly excludes `outputs/audits/` via policy ("historical audit payloads are immutable references; never rewrite") with `':!outputs/audits/'` exclusion in gate.
- **iter4 CLEAN-CODEX-SCHEDULE-1** FIXED: §5 Cleanup-PR-4 explicitly includes `.codex/_archive_pre_v6_2/`, `.codex/continuous/`, `.codex/deep_dive_round_*/`, `.codex/round_{2..5}/`. Also need to classify `.codex/v6_phase_0_1_*` — adding to PR-4 batch as "v6_2 phase 0/1 transition briefs" (Plan-v13-era).
- **iter4 CLEAN-OUTPUTS-TMP-1** FIXED: §3.8 added `outputs/codex_tmp_pytest`, `outputs/pytest_basetemp`, `outputs/pytest_temp`, `outputs/pytest_tmp` as DELETE under §3.3 allowlist; permission-denied subfolder noise excluded from grep gates via `.ignore`/`.rgignore`.
- **iter4 CLEAN-FENCE-1** FIXED: malformed nested code fence in bash variant block removed.
- **iter4 CLEAN-STALE-PATHS-1** FIXED: §6 + §7 risk text corrected to `scripts/autoloop/*` and `.claude/hooks/*`.
- **iter4 CLEAN-PR-COUNT-1** FIXED: §6 + §7 prose say "14 PRs" / "PR-1 through PR-14" matching actual schedule.
- **iter4 CLEAN-MANIFEST-RENAME-1** FIXED: §4 RENAME schema explicitly shows `sha256_old` + `sha256_new` + `reference_update_count` + `reference_files_updated` fields.
- **iter4 CLEAN-PRIVATE-FENCE-1** FIXED: kept .private/ fix as explicit PR-1 gate per Codex retention.

Codex: this is the cleanup audit iter 5. Verdict format same as plan iter 4:

This iter 4 brief addresses iter-3 findings (6 P1 + 5 P2):

- **iter3 CLEAN-CODEX-INVENTORY-1** FIXED: §3.2 added explicit ARCHIVE rows for `.codex/_archive_pre_v6_2/`, `.codex/continuous/`, `.codex/deep_dive_round_*/`, `.codex/round_{2..5}/`. All folded into `archive/2026-05-05/` subdirs.
- **iter3 CLEAN-SLICE-PROVENANCE-1** + **iter3 CLEAN-BENCHMARK-CONTRACT-1** + **iter3 CLEAN-WALKTHROUGH-SEQ-1** ALL FIXED via §5 ordering invariant: cleanup PRs run AFTER ROAD B reset to `365f334`. Reset removes slice 002-005 backend code, demo scripts, walkthrough dirs, post-drift docs FROM the active branch. The `pre_restart_2026_05_05` tag preserves them for forensic recovery. So cleanup audit's classifications for slice-002-005-era artifacts ONLY apply to items that exist post-reset (essentially: prior-session `.codex/` briefs, untracked tmpdirs). The Codex-flagged refs (src/polaris_graph/retrieval2/* etc, web/app/benchmark/*, demo_runbook references) ARE NOT IN the reset target. Cleanup ordering is now: ROAD B reset → cleanup PR-1 through PR-14.
- **iter3 CLEAN-TASKBRIEFS-REF-1** FIXED: §3.2 row updated to ARCHIVE `.codex/task_briefs/` IN SAME PR-4 as `docs/task_acceptance_matrix.yaml` archival (they reference each other; same PR).
- **iter3 CLEAN-DELETE-EXEC-3** FIXED: §3.3 delete script rewritten as PowerShell (Windows canonical) with bash variant for Linux CI. Both implement identical allowlist + DO-NOT-TOUCH refusal + dry-run/apply mode handling.
- **iter3 CLEAN-REN-REFLIST-1** FIXED: §3.2 protocol rename rows expanded to include all extra refs Codex found: `.codex/continuous/`, `.codex/_archive_pre_v6_2/`, `src/polaris_v6/memory/store.py`, `scripts/strip_changelog_markers.py`, `tests/v6/test_workspace_memory.py`. Plus pg_preflight self-references documented.
- **iter3 CLEAN-PRIVATE-GITIGNORE-1** FIXED: §3.6 row rewritten to specifically replace `.gitignore:9` (inline-comment bug) with two-line fix: real comment line + real `.private/` rule. Verifies via `git check-ignore` returning path AND `git status --short -- .private` returning empty.
- **iter3 CLEAN-STATE-CLASSIFY-1** FIXED: §3.9 6 small state sqlites moved from INSPECT to KEEP per Codex confirmation of active references.
- **iter3 CLEAN-OUTPUTS-NESTED-TMP-1** FIXED: §3.8 `outputs/codex_findings/` row updated to add ripgrep tooling exclusions (`.ignore`/`.rgignore`) for nested pytest tmpdirs in audit payload; do NOT delete (audit content KEEP).
- **iter3 CLEAN-MANIFEST-SIDECAR-1** FIXED: §4 directory schema adds `entry_id` (unique per entry) and `permission_denied_sidecar_path` (state/polaris_restart/cleanup_manifest_sidecars/<entry_id>.permission_denied.txt) and `per_file_checksums_sidecar_path`.

Codex: this is the cleanup audit iter 4. Verdict format same as plan iter 4:

This iter 3 brief addresses iter-2 findings (1 continuing P0 + 6 P1 + 5 P2):

- **iter2 CLEAN-EXEC-1 (continuing P0)** FIXED: §5 Cleanup-PR-1 line rewritten to remove `git clean -fd`; replaced with `scripts/cleanup/delete_pytest_tmpdirs.sh --dry-run` then `--apply`. plan §8 §625 also patched to remove `git clean -fd` in favor of the allowlisted script.
- **iter2 CLEAN-PRIVATE-2 (P1)** FIXED: §5 Cleanup-PR-1 step 1 explicitly adds `.private/` line to `.gitignore` before any deletion runs. Verifies effectiveness via `git check-ignore .private/codex_hmac.key` returning the path.
- **iter2 CLEAN-EXEC-2 (P1)** FIXED: §3.3 delete script now has full `--dry-run|--apply` mode handling, resolved-path checks (`realpath` against `DO_NOT_TOUCH_PREFIXES`), exit codes per failure type. Cleanup-PR-1 reviews dry-run transcript.
- **iter2 CLEAN-SCRIPT-1 (P1)** FIXED: §5 Cleanup-PR-8 (renamed) atomically moves all 8 post-drift scripts AND all 6 dependent tests AND scrubs README + web/app/benchmark + docs references in ONE PR. CI gate via ripgrep zero-hits. PR-9/PR-10 split eliminated.
- **iter2 CLEAN-REN-2 (P1)** FIXED: §3.10 pg_preflight row now lists ALL 5 referencing files (docker_entrypoint.sh + CLAUDE.md + file_directory.md + soc2_evidence_map.md + env_var_inventory.md). CI gate ripgrep zero hits.
- **iter2 CLEAN-ARCHIVE-1 (P1)** FIXED: §10 manifest path now consistent at `state/polaris_restart/cleanup_manifest.md` (tracked); plan §8.0a updated to match. No more contradiction between cleanup audit and plan.
- **iter2 CLEAN-GOLDEN-SEQ-1 (P1)** FIXED: §5 Cleanup-PR-9 atomically moves slice 2-5 golden_drafts + architecture proposals + test_slice_NNN_goldens.py runners in same PR. Tests + their data move together; no silent-skip window.
- **iter2 CLEAN-PATH-1 (P2)** FIXED: §3.10 paths corrected — `scripts/autoloop/*` (was `autopilot`) and `.claude/hooks/*` (was `scripts/hooks`).
- **iter2 CLEAN-INV-1 (P2)** FIXED: §3.1 inventory verified by `ls`; nonexistent files (`pyproject.toml`, `package.json`, `LICENSE`, `conftest.py`, `requirements-cpu.txt`, `requirements-gpu.txt`) removed; actual root files listed (`requirements-orchestrator.txt`, `requirements-v6.txt`, `m_int_7_manual_probe.txt` for D, `write_probe_root.txt` for D).
- **iter2 CLEAN-DOC-REN-1 (P2)** FIXED: §3.7 full_online_plan_FINAL row now requires CI gate ripgrep zero hits; §5 Cleanup-PR-7 atomically renames + updates all referencing scripts/tests/.github files.
- **iter2 CLEAN-MANIFEST-2 (P2)** FIXED: §4 directory entries now record `recursive_file_count`, `permission_denied_count`, `permission_denied_paths`, `merkle_root_sha256`, `per_file_checksums`. Permission-denied subfolders accounted forensically.
- **iter2 CLEAN-TASKBRIEFS-1 (P2)** FIXED: §3.2 row classified `.codex/task_briefs/` as ARCHIVE (was INSPECT).

Codex: this is the cleanup audit iter 3. Verdict format same as plan iter 4:

This iter 2 brief addresses iter-1 findings (1 P0 + 4 P1 + 3 P2):

- **iter1 CLEAN-EXEC-1 (P0)** — `git clean -fdX` / `git clean -fd` are catastrophic for POLARIS (would nuke `.env`, 2.2GB pg_checkpoints.sqlite, web/node_modules, archive/, .private/). FIXED: §3.3 DELETE method replaced with explicit allowlisted-paths bash script with hard-protected refusal of DO-NOT-TOUCH paths. Cleanup-PR-1 reviews dry-run output for Codex APPROVE before execution.
- **iter1 CLEAN-REN-1 (P1)** — `_v2` Codex protocol filenames referenced from CLAUDE.md, canonical_pin.txt, orchestrator.py, stop_hook_v3.py, schemas, tests. FIXED: §3.2 rename rows now mark renames as ATOMIC PR with all references updated in same PR + CI gate via ripgrep for old name returning zero hits post-rename.
- **iter1 CLEAN-REN-2 (P1)** — `pg_preflight_v2.py` referenced from `scripts/docker_entrypoint.sh:63`. FIXED: §3.10 row notes atomic rename PR also updates docker_entrypoint.sh + verification via `docker compose run preflight` smoke test.
- **iter1 CLEAN-SCRIPT-1 (P1)** — Script archival breaks 5 dependent tests. FIXED: §3.11 row added entries for `test_run_benchmark_cli.py`, `test_seed_demo_benchmark.py`, `test_demo_smoke.py`, `test_setup_gpg_for_demo.py`, `test_provision_vast_dev_cluster.py`, `test_default_llm_completion_async_fix.py`; §3.10 row notes atomic-with-test archival in same Cleanup-PR-9.
- **iter1 CLEAN-ARCHIVE-1 (P1)** — `archive/` is gitignored; manifest won't stage. FIXED: §4 manifest moved to TRACKED path `state/polaris_restart/cleanup_manifest.md`; archive payloads stay local-only gitignored; manifest cross-references git history for tracked items.
- **iter1 CLEAN-DOC-1 (P2)** — Archiving demo docs leaves stale README refs. FIXED: §3.7 doc rows note atomic with README update + ripgrep CI gate.
- **iter1 CLEAN-MANIFEST-1 (P2)** — Manifest schema lacks `size_bytes` + `sha256`. FIXED: §4 schema adds both fields.
- **iter1 CLEAN-PRIVATE-1 (P2)** — `.private/` ignore rule not verified. FIXED: §3.6 row adds `git check-ignore` verification step before any cleanup runs.

Codex: this is the cleanup audit iter 2. Verdict format same as plan iter 4:

```
verdict: APPROVE | REQUEST_CHANGES
novel_p0:
  - <id>: <one-sentence finding>
continuing_p0:
  - <id from prior iter>: <one-sentence finding>
p1:
  - <id>: <one-sentence finding>
p2:
  - <id>: <one-sentence finding>
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: <list any user-blocked items>
```

Specific risks to audit:
1. §3.3-§3.5 DELETE for ~150 untracked tmpdirs/sqlites: any of these actually referenced from active scripts (e.g., `scripts/autoloop/*` reads `state/orchestrator_status.json` and may cascade to tmpdirs)? (iter 5 CLEAN-STALE-PATHS-1: path corrected.)
2. §3.2 ARCHIVE for 200+ Codex briefs: any of the briefs actively imported or referenced from current docs (CHARTER, PLAN, agent_architecture, substrate_audit, Carney v6.2)?
3. §3.7 docs ARCHIVE: are any of the marked-A docs (mission_status, demo_runbook, demo_e2e_verification) referenced from CLAUDE.md or active scripts?
4. §3.8 outputs ARCHIVE: are post-drift demo benchmark artifacts referenced anywhere?
5. §3.10 scripts ARCHIVE: today's seven scripts (`screenshot_walkthrough.js`, `screenshot_benchmark.js`, `seed_demo_benchmark.py`, `demo_smoke.py`, `setup_gpg_for_demo.py`, `verify_audit_bundle_e2e.py`, `provision_vast_dev_cluster.py`) — any still imported by `Dockerfile` or `docker-compose.yml`?
6. §3.11 tests ARCHIVE: are slice 002-005 golden runners referenced from `pytest.ini` collect-config?
7. §5 sequencing: is 14 PRs the right granularity? Should DELETE batch be split further? (iter 5 CLEAN-PR-COUNT-1: count corrected from "12".)
8. §6 INSPECT list: any items that should be classified now (KEEP/ARCHIVE) instead of deferred?
9. §7 risk-residual: any do-not-touch items I missed? Any classification that risks runtime breakage?
10. Manifest schema §4: complete? Should it record file size + checksum for ARCHIVE entries to detect later corruption?

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

No exec exploration unless verifying a specific concern. List ALL remaining issues this iteration. No hard cap on iterations.
