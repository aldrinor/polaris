# Codex Brief Review — I-policy-001 (ITER 5 — FINAL)

**HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (FINAL).**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- **This is the last iteration.** If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; no iter 6 will follow. Banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-policy-001 — Apply 5-iter Codex review cap per user directive 2026-05-06

## Why iter 5 exists (final)

Iter 4: REQUEST_CHANGES, 1 P1 + 2 P2.

- **I4-P1-001 (cleanup_audit.md:1933 stale "No hard cap on iterations"):** the iter-2 prompt block trailer at line 1933 still contained the binding-looking phrase. **Fix iter-5:** replaced with `... List ALL remaining issues this iteration. (HISTORICAL iter-2 prompt boilerplate; the "no hard cap" rule was REVOKED 2026-05-06 — current binding policy is the 5-iter cap per CLAUDE.md §8.3.1.)`. The historical prompt is preserved (audit trail) with explicit "HISTORICAL ... REVOKED 2026-05-06" framing.
- **I3-P2-001 / I4-P2-001 carryover (`plan_amendment_skip_road_b_reset.md:102`):** Codex iter-3 + iter-4 classified non-blocking ("if this doc is reused"). **Fix iter-5 (preemptive):** annotated line 102 with `(HISTORICAL boilerplate; the "no hard cap" rule was REVOKED 2026-05-06 — if this advisory doc is reused, replace this line with the canonical CLAUDE.md §8.3.1 cap directive.)`. Same supersession framing applied as cleanup_audit.md.
- **I4-P2-001 (memory file location verification):** Codex sandbox could not access `~/.claude/projects/...` (out-of-tree user-side memory). Environmental, not a code/doc issue. The memory file was authored locally and is verified via `head -1` returning the SUPERSEDED frontmatter on the user's box. Not a code review concern; iter-5 leaves as documented.

## Verification command (iter-5 should run on its own check)

```bash
grep -nE "No hard cap on iterations" state/polaris_restart/cleanup_audit.md state/polaris_restart/plan_amendment_skip_road_b_reset.md docs/handover.md state/restart_instructions.md CLAUDE.md web/AGENTS.md .codex/REVIEW_BRIEF_FORMAT.md \
  | grep -vE "REVOKED|HISTORICAL|SUPERSEDED"
```

Expected output: empty. After iter-4 + iter-5 fixes, every remaining occurrence of "No hard cap on iterations" in active restart-surface docs is annotated with REVOKED / HISTORICAL / SUPERSEDED framing.

## Done-when

- cleanup_audit.md:1933 has supersession framing (iter-5 fix).
- plan_amendment_skip_road_b_reset.md:102 has supersession framing (iter-5 preemptive fix).
- All other constraints from iter-1/2/3/4 unchanged: §8.3.1 single canonical block, §8.3.3 references §8.3.1, §0 of REVIEW_BRIEF_FORMAT references §8.3.1, force-APPROVE artifact procedure documented in CLAUDE.md, iteration_trajectory.md has the I-policy-001 entry, restart/handover/cleanup_audit/memory all reference 5-cap memory with explicit supersession of no-cap memory.

## Constraints

- DO NOT review for code correctness — pure governance/doc update.
- "Don't pick bone from egg": cosmetic wording / phrasing preference is P3 / out-of-scope.
- The memory file `feedback_codex_iteration_no_cap_no_toothpaste.md` SUPERSEDED banner is at line 1 of that file (verified locally `head -1` returns `[SUPERSEDED 2026-05-06]`); Codex sandbox cannot access user-side memories — accept this as out-of-sandbox per iter-4 P2.
- This is iter 5 of 5. If REQUEST_CHANGES returned, Claude will append `verdict: APPROVE` + `# force-approved at iter 5 cap per CLAUDE.md §8.3.1` to this verdict file and ship per the cap directive's force-approve procedure.

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
