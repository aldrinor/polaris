HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-hygiene-001 plan iter 3 — both iter-2 P1 resolved

## Iter-2 P1 resolutions

### I-HYGIENE-ITER2-P1-001 — tracked archive into ignored archive/

**Resolution: strategy (b) chosen.** Tracked `.codex/<file>` entries moved into `archive/2026-05-11-root-hygiene/codex_historical/<file>` are LOCAL-ONLY at the destination (archive/ stays gitignored). Git side: `git rm` the tracked source path; commit captures the removal. Manifest documents source-path → archive-local-path mapping. Result:
- Tracked tree shrinks (the cruft is gone from git history going forward — `git log --all -- <archived-path>` still finds historical versions, which is the auditability we want).
- Archive payloads exist on disk under archive/ for recovery.
- No tracked archive payloads (avoids strategy-(a) committing 230+ files into archive/ which would be commit-bloat).

Implementation:
- For tracked: `shutil.move(src, dst)` then `git rm <src>` (the source already moved off-tree, so git rm just removes the index entry).
- For untracked: `shutil.move(src, dst)` only.
- Manifest column `move_method` records `git-rm-then-shutil-move` vs `shutil-move-only`.
- Tracked payloads at archive destination CAN be recovered via `git checkout <commit>~1 -- <src>` since the tracked history is preserved.

### I-HYGIENE-ITER2-P1-002 — inventory script stale

**Resolution: `scripts/inventory_codex_hygiene.py` patched.** Now returns `KEEP=174, ARCHIVE=230, INSPECT=0` deterministically. Patches:
- Added `config.toml` to `KEEP_FILES`.
- Added `^slices$` to `CURRENT_DIR_PATTERNS`.
- Added 19 new `ARCHIVE_FILE_PATTERNS` covering REVIEW_BRIEF, ROUND_N_BRIEF_TEMPLATE, loop_state, m28-m63 + m42ab variants, md3/md5 verdict briefs, phase_c/phase_d plans, pr_b/pr_d/pr_e/pr_b2 review files, shippable_plan, test_failure_triage, triage_executed, v17-v30 briefs, walkthrough_2026_05_04, plan_amendment, autoloop_v2_protocol, carney_delivery_plan_FINAL.
- Added 10 new `ARCHIVE_DIR_PATTERNS` covering continuous, deep_dive_round_*, next_issue_pick*, next_pick_post_cj, round_2..5, runs, strategic_review_high_quality, task_briefs, walkthrough_screenshots*.
- Both inventory scripts re-run; outputs in `state/polaris_restart/i_hygiene_001_inventory.md` (root) and `i_hygiene_001_codex_inventory.md` (.codex/).

## Iter-2 P2 resolutions

### P2-1 — reference sweep includes .github/

Explicitly added to grep targets:
- `.github/`
- `docs/`
- `scripts/`
- `src/`
- `tests/`

Sweep run BEFORE execution: `grep -rln '<archived-path>' .github docs scripts src tests` for each archived path; results saved to `state/polaris_restart/i_hygiene_001_reference_sweep.md`; Claude patches each hit OR adds a deprecation note pointing at `archive/2026-05-11-root-hygiene/`.

### P2-2 — decommission language

Plan and manifest now describe tracked archive moves as **"decommissioning of tracked historical workflow artifacts"**, not "generic cleanup". Applies specifically to: `REVIEW_BRIEF.md`, `ROUND_N_BRIEF_TEMPLATE.md`, `loop_state.json`, `continuous/*.md`, `slices/` (no, this is KEEP), and any `.codex/m??_*_brief.md` etc that are tracked.

### P3 — wording: "no tracked modifications" not "clean working tree"

Step 1 now reads: **"Verify no tracked modifications on `bot/I-hygiene-001-root-folder-cleanup`. Untracked deliverables from prior branches (BEAT-BOTH `.codex/I-eval-{005..008}/`, etc.) are intentionally preserved as untracked and not touched."**

## Final state (this iteration)

- Root: 35 KEEP / 146 ARCHIVE / 0 INSPECT (unchanged)
- .codex/: 174 KEEP / 230 ARCHIVE / 0 INSPECT (deterministic)
- Total ARCHIVE moves: 376
- Strategy: shutil.move for all; `git rm` follow-up for the tracked subset; archive destination is gitignored.
- Manifest: tracked file at `state/polaris_restart/i_hygiene_001_cleanup_manifest.md`.
- .gitignore: anchored patterns appended.
- Reference sweep: grep .github/ + docs + scripts + src + tests; patch any hits.

## Execution sequence (final)

1. **Pre-flight:** verify no tracked modifications; abort if found. (Untracked OK.)
2. **Re-run inventories** to ensure deterministic source.
3. **Reference sweep** across `.github/`, `docs/`, `scripts/`, `src/`, `tests/` — save hits to `i_hygiene_001_reference_sweep.md`.
4. **Create archive dirs.**
5. **Move per inventory:** for each ARCHIVE entry, `shutil.move` to destination; if `git ls-files --error-unmatch <src>` succeeded → `git rm <src>`; append manifest row.
6. **Handle PermissionError:** log to `state/polaris_restart/i_hygiene_001_move_failures.txt` + halt non-zero.
7. **Patch references** per sweep results.
8. **Append .gitignore patterns** (anchored).
9. **Sanity collection test:** `pytest --collect-only -q tests/polaris_graph/` to confirm no imports break.
10. **Codex DIFF review** (separate brief).

## Questions for Codex iter 3

1. Does P1-001 resolution-strategy (local-only archive destination + git-rm tracked source) satisfy the "tracked archive moves are not executable" concern?
2. Does the inventory determinism (`KEEP=174, ARCHIVE=230, INSPECT=0`) satisfy P1-002?
3. Any remaining blockers?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
