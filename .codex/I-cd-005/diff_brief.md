HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-005/codex_diff.patch` (141 lines incl. the
`# canonical-diff-sha256:` trailer). Read ONLY that one file.

# Codex DIFF review — I-cd-005 / GH#637: evaluator pick lock

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-005/brief.md` (brief
APPROVE iter 4 after 3 RC iters expanding the candidate set). Three files in
the canonical diff:

- `docs/models/evaluator_pick.md` (NEW, 105 LOC) — the locked pick + hard
  fallback + 6 alternatives + scope boundaries + constraint reaffirmation.
  All 5 iter-4 P2 confirmations/clarifications folded in (ERNIE -PT semantics,
  largest/highest-active wording, ranking caveat, multimodality consistency,
  Hunyuan EU clause).
- `.gitignore` (+3 LOC) — negate the broad `models/` rule for the
  `docs/models/` subtree (text docs, not weights). Lets I-cd-009/011 use the
  same dir for future model docs.
- `state/polaris_restart/iteration_trajectory.md` (~+10 LOC) — mandatory
  §8.3.5 log.

## §B — Red-team focus

1. **Pick correctness against the iter-4-APPROVE'd brief.** The doc names
   `meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8` as primary and
   `meta-llama/Llama-3.1-405B-Instruct` as hard fallback. Does the doc
   faithfully reflect the iter-4 brief's decision rule, or has it drifted?
2. **Alternatives table accuracy** — 6 alternatives with HF ids, licenses,
   params, and notes. Are any of the licenses / param counts / HF ids
   misstated relative to the iter-4 brief?
3. **Iter-4 P2 fold-in completeness** — every P2 should appear in the
   deliverable doc, not just in the verdict file:
   - ERNIE `-PT` = PyTorch format (Posttraining/Chat, usable as evaluator)
   - MiniMax-M1 = 456B largest; Hunyuan-Large = 52B highest active
   - "No published RAG-faithfulness numbers; weighting deployment maturity"
     section present
   - Multimodality caveat applied to Maverick + Qwen3.5 (not just ERNIE)
   - Hunyuan EU-territory clause noted
4. **Scope discipline** — the diff touches only the pick doc, the
   `.gitignore` exception, and the trajectory log. No config changes, no
   `.env` edits, no `src/` touches.
5. **`.gitignore` exception** — tightly scoped to `docs/models/` only; does
   not weaken the broader `models/` exclusion.

## §C — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
