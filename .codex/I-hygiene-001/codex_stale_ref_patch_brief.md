HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-hygiene-001 stale-ref patches — review (closes prior diff P2)

Commit: `6053ef17` on `bot/I-hygiene-001-root-folder-cleanup`.

## Context

Your prior diff verdict (iter 1, commit `9348deaa`) was APPROVE with P2:
> "Stale doc/comment refs remain, including .gitignore line 162 and the known docs/workflow/script references. These are not runtime blockers; patch them in the docs-update step."

This commit is that patch step.

## Diff

```
.github/workflows/codex-required.yml                   |  4 +++-
.github/workflows/web_ci.yml                           |  3 ++-
docs/file_directory.md                                 | 10 ++++++----
docs/pipeline_audit_context/04_sample_run_artifacts.md |  2 +-
docs/task_acceptance_matrix.yaml                       |  4 ++--
scripts/codex_loop_parse.py                            |  6 ++++--
scripts/v28_post_manifest_pipeline.sh                  |  2 +-
7 files changed, 19 insertions(+), 12 deletions(-)
```

## What was patched

1. `.github/workflows/web_ci.yml:148` — comment ref `.codex/continuous/2057fac_2c2_visual_regression.md` → archived path
2. `.github/workflows/codex-required.yml:107` — comment ref `.codex/pr_d_mechanical_gates_review_brief.md` → archived path
3. `scripts/codex_loop_parse.py:19-20` — docstring example genericized (no longer asserts specific `.codex/round_3/` path); archived `round_*/` note added
4. `scripts/v28_post_manifest_pipeline.sh:40` — runtime `cat` reference `.codex/v28_deep_content_audit_brief.md` → archived path
5. `docs/pipeline_audit_context/04_sample_run_artifacts.md:70` — `loop_state.json` reference → archived path
6. `docs/task_acceptance_matrix.yaml:1114,1116` — `task_briefs/` references → archived path
7. `docs/file_directory.md:206-211` — §"Audit-loop infrastructure" table rewritten to reflect issue-driven layout (`I-<prefix>-NNN/` dirs) instead of historical `REVIEW_BRIEF.md` + `loop_state.json` + `round_{2,3,4,5}/` rows

## What was NOT patched (and why)

- `scripts/cleanup/count_hits.sh:13` + `zero_hit_gate.sh:22-24` — git pathspec exclusions `:!.codex/continuous/`, `:!.codex/round_*/`, `:!.codex/deep_dive_round_*/`. These reference paths that no longer exist after the archive move, but the exclusions are no-op on non-existent paths. Both files already have `:!archive/` at top (lines 11 / 17) which covers the moved destinations. Functionally correct; cosmetic stale.

## Questions for Codex

1. Does this patch close the iter-1 P2 "stale doc/comment refs" item?
2. Any P0/P1 in the 7-file diff?
3. Should `scripts/cleanup/*.sh` also be patched (the stale `:!.codex/continuous/` exclusions), or is the `:!archive/` umbrella sufficient?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
prior_p2_resolved: yes | partial | no
convergence_call: continue | accept_remaining
remaining_blockers_for_merge: [...]
```
