# Claude architect self-audit — I-policy-001

**Issue:** I-policy-001 — 5-iter Codex review cap policy (+ §8.4 resource discipline)
**Brief:** `.codex/I-policy-001/brief.md` (Codex iter-5 force-APPROVE'd per CLAUDE.md §8.3.1 cap)
**Force-approve annotation:** `.codex/I-policy-001/codex_brief_verdict_iter5_force_approve.txt`

## What the diff does

Two coupled governance changes per user directives 2026-05-06:

### Part 1 — 5-iter Codex review cap (commercial viability override)

Per user: "let cap iteration with Codex to 5, if Codex fail to approve within 5 iteration, we will make it approve, then move to the next task. Our progress is just too slow now, it become commercially unviable."

- **CLAUDE.md §8.3.1** rewritten: "Hard cap of 5 iterations." Single canonical "Communication to Codex" fenced block (the source of truth — every brief copies this byte-for-byte). Force-approve artifact procedure documented (4-step), with correct CI-checked filenames (`codex_brief_verdict.txt` for brief gate, `codex_diff_audit.txt` for diff gate per `.github/workflows/codex-required.yml:155-158,192-193`).
- **CLAUDE.md §8.3.3** now says "every brief MUST inherit the §8.3.1 verbatim block; do not paraphrase or duplicate." Single source of truth.
- **CLAUDE.md §8.3.6** updated: cap-hit accepted as a legitimate stop-and-ship condition alongside Codex's "build harness" directive.
- **CLAUDE.md L640** (boot ritual) updated: references `feedback_codex_iteration_5cap_2026_05_06.md` with explicit supersession of `feedback_codex_iteration_no_cap_no_toothpaste.md`.
- **`.codex/REVIEW_BRIEF_FORMAT.md`** bumped to v3: §0 references CLAUDE.md §8.3.1 by pointer (no inline duplication); v2 sections preserved.
- **`web/AGENTS.md`** notes the 5-cap rule + pointer to CLAUDE.md §8.3.1.
- **`state/restart_instructions.md`** + **`docs/handover.md`** "Critical memory entries" updated: 5-cap memory listed as critical-current with explicit supersession of no-cap memory.
- **`state/polaris_restart/cleanup_audit.md`** L5 + L1756 + L1933 annotated as HISTORICAL with REVOKED 2026-05-06 framing on stale "no hard cap" references.
- **`state/polaris_restart/plan_amendment_skip_road_b_reset.md`** L102 same supersession framing on its iter-2 prompt.
- **`state/polaris_restart/iteration_trajectory.md`** appended dedicated I-policy-001 section: 5-iter trajectory + cap-hit force-APPROVE record.
- **Memory** (out of tree, `~/.claude/projects/C--POLARIS/memory/`):
  - NEW `feedback_codex_iteration_5cap_2026_05_06.md` (replaces inline cap block with a pointer to CLAUDE.md §8.3.1).
  - Old `feedback_codex_iteration_no_cap_no_toothpaste.md` got a `[SUPERSEDED 2026-05-06]` banner at the top + frontmatter flag.
  - `MEMORY.md` index updated.

### Part 2 — §8.4 Computer-resource discipline (CPU/GPU/RAM management)

Per user (after their machine rebooted from accumulated codex sub-process RAM): "you can still run them, but you need to have a good mind for CPU/GPU/RAM management and monitoring, and only run them for necessary task, and kill them when you finish the task."

- **CLAUDE.md §8.4 NEW**: 8-rule discipline (one codex at a time; pre/post-task `Get-Process` inventory; kill leftovers; no parallel pytest/npm; no heavy ML/CUDA in autonomous loops; track long-running servers; notify user on resource pressure; sub-process lingering empirical fact).
- **`web/AGENTS.md`** notes the rule with pointer to §8.4.
- **Memory**: NEW `feedback_resource_discipline_2026_05_06.md` documenting the empirical incident + binding rules.

## Iter trajectory

| Iter | Verdict | P1 | P2 | Key findings |
|---|---|---|---|---|
| 1 | REQUEST_CHANGES | 4 | 2 | canonical-block duplication; supersession leak L640; force-approve artifact procedure missing; trajectory log entry missing |
| 2 | REQUEST_CHANGES | 2 | 0 | restart/handover supersession leaks; memory file divergent inline block |
| 3 | REQUEST_CHANGES | 2 | 1 | old memory file lacks SUPERSEDED banner; cleanup_audit.md L5 + L1756 stale |
| 4 | REQUEST_CHANGES | 1 | 2 | cleanup_audit.md L1933 stale "No hard cap" |
| 5 | REQUEST_CHANGES → force-APPROVE | 1 | 2 | §8.3.1 force-approve artifact-name typo (fixed inline before force-approve); 2 cosmetic P2s deferred |

**P1 monotonic decrease** 4→2→2→1→1. Cap fired once (iter 5); zero gold left on the table since the iter-5 P1 was a typo IN the file Codex was reviewing (1-line fix applied inline before force-APPROVE).

## Force-APPROVE rationale

Per CLAUDE.md §8.3.1 cap rule: at iter 5 REQUEST_CHANGES, Claude force-APPROVE's. The iter-5 P1 was self-correcting (artifact-name typo in the canonical doc itself) and applied inline; the 2 P2s are documentation-precedence notes addressed in this same PR or absorbed into a follow-up REVIEW_BRIEF_FORMAT v3.1 update.

Annotation file: `.codex/I-policy-001/codex_brief_verdict_iter5_force_approve.txt`. The verdict file `codex_brief_verdict.txt` has `verdict: APPROVE` appended at the end with `# force-approved at iter 5 cap per CLAUDE.md §8.3.1` marker so the CI gate sees APPROVE.

## Risks acknowledged

- **Trust-Codex principle erosion at the 5-cap.** Iter-5 force-approve ships a small set of residual concerns. Mitigation: the brief directive demands front-loaded findings + "don't pick bone from egg" — incentivizing Codex to prioritize real P0/P1s in iter 1. Empirically validated this iter cycle: iter-1 had 4 P1, iter-5 had 1 P1 (a self-correcting typo).
- **§8.4 resource discipline is convention, not enforced by CI.** A hook or pre-commit check could enforce the process inventory pattern automatically; deferred to future Issue.
- **Memory file out-of-tree.** `feedback_codex_iteration_5cap_2026_05_06.md` lives at `~/.claude/projects/C--POLARIS/memory/` per Claude Code memory architecture. Codex sandbox cannot directly verify; relies on local-machine inspection. Acceptable per iter-4 P2-001 disposition.

## What I do NOT claim this PR does

- Does not enforce §8.4 via CI/hook — it's prose discipline.
- Does not retroactively re-iterate past Codex reviews under the new cap — only future briefs.
- Does not change branch protection rules / CODEOWNERS.
- Does not modify the autonomous merge flow (sotaleung-wec author + aldrinor approve + direct API merge stays the same).

## Output schema for Codex review

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
