# Codex Diff Review Brief — I-policy-001 (ITER 1)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

This is the SECOND of two Codex review gates per CLAUDE.md §3.0 5-artifact contract for Issue I-policy-001:

1. ✅ **Brief review:** iter 5 of 5 force-APPROVE'd per CLAUDE.md §8.3.1 cap (annotation: `.codex/I-policy-001/codex_brief_verdict_iter5_force_approve.txt`).
2. ⏳ **Diff review** (this iter): verify the actual diff matches the iter-5 brief intent.

## Scope: pure governance/doc PR

No code changes. The 12-file diff:

- CLAUDE.md (canonical 5-cap §8.3.1; resource discipline §8.4)
- web/AGENTS.md (cap + resource pointers)
- .codex/REVIEW_BRIEF_FORMAT.md (v3, §0 references CLAUDE.md by pointer)
- state/restart_instructions.md (memory-list update)
- docs/handover.md (memory-list update)
- state/polaris_restart/cleanup_audit.md (3 supersession annotations)
- state/polaris_restart/plan_amendment_skip_road_b_reset.md (1 supersession annotation)
- state/polaris_restart/iteration_trajectory.md (I-policy-001 section)
- .codex/I-policy-001/* (review artifacts; excluded from canonical diff)
- outputs/audits/I-policy-001/claude_audit.md (excluded from canonical diff)

Canonical-diff-sha256: `b97692b7118c5c66336474e9f269cf90dc217ea16d950e9412fb7605b396e095`. LOC: +94 net.

## Constraints

- DO NOT review for code correctness — there is no code change.
- DO review for: (a) every diff hunk matches the iter-5 brief acceptance criteria, (b) no surprise scope-creep beyond the 5-cap policy + §8.4 resource discipline, (c) the §8.3.1 force-approve procedure correctly names CI-checked artifact files (this was iter-5's P1; verify the fix landed).
- "Don't pick bone from egg": cosmetic wording, comma placement, paragraph order = P3 / out-of-scope. Reserve P0/P1 for real execution risk.
- The brief was iter-5 force-APPROVE'd; do NOT relitigate brief-level policy decisions (e.g., whether the cap should be 5 vs 7). Review the diff against the iter-5 spec.

## Specific risks for Codex Red-Team

1. **§8.3.1 force-approve artifact-name fix.** Verify `CLAUDE.md` §8.3.1 force-approve procedure now names `codex_brief_verdict.txt` (brief gate) + `codex_diff_audit.txt` (diff gate) per `.github/workflows/codex-required.yml:155-158,192-193`. Iter-5 P1 fix.

2. **Single source of truth for cap directive.** Verify CLAUDE.md §8.3.1's "Communication to Codex" fenced block is the only canonical definition. §8.3.3 should reference §8.3.1 ("inherit verbatim, do not paraphrase"). REVIEW_BRIEF_FORMAT §0 should reference §8.3.1 by pointer. The new memory file should NOT have an inline cap block.

3. **Supersession integrity.** Every reference to `feedback_codex_iteration_no_cap_no_toothpaste.md` in active restart-surface docs (CLAUDE.md, restart_instructions.md, handover.md, cleanup_audit.md, plan_amendment, memory) must include explicit "(SUPERSEDED 2026-05-06)" framing. The old memory file itself has a `[SUPERSEDED 2026-05-06]` banner at top.

4. **§8.4 resource discipline.** New section in CLAUDE.md after §8.3.9. 8 numbered rules. web/AGENTS.md has a one-line pointer. Memory file authored at `~/.claude/projects/C--POLARIS/memory/feedback_resource_discipline_2026_05_06.md` (out-of-tree; Codex sandbox can't see it — accept).

5. **`canonical-diff-sha256` trailer correctness.** `b97692b7118c5c66336474e9f269cf90dc217ea16d950e9412fb7605b396e095` produced via `git diff --cached -- ":(exclude).codex/I-policy-001/" ":(exclude)outputs/audits/I-policy-001/"`. CI gate parses `codex_diff.patch` for `^# canonical-diff-sha256: [a-f0-9]{64}$`.

6. **iteration_trajectory.md append.** New "I-policy-001 — iter 5 cap-hit + force-APPROVE (2026-05-06)" section at end. P1 trajectory 4→2→2→1→1.

7. **Force-APPROVE marker on `codex_brief_verdict.txt`.** Verify the file ends with `verdict: APPROVE` + `# force-approved at iter 5 cap per CLAUDE.md §8.3.1` so CI gate sees APPROVE on the LAST verdict line.

## Output schema (mandatory)

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
