HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-007/codex_diff.patch` (~130 lines incl. trailer).
Read ONLY that one file.

# Codex DIFF review — I-cd-007 / GH#639: serving engine lock

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-007/brief.md`
(brief APPROVE iter 2 after iter 1 RC pivoted recommendation; iter 2's
3 P2 clarifications all folded into the deliverable doc). Two files in the
canonical diff:

- `docs/models/serving_engine_pick.md` (NEW, 108 LOC) — vLLM locked for both
  boxes + per-role SGLang contingencies + TensorRT-LLM direct-backend
  fallback + I-cd-011 empirical-verification triggers + Dynamo deferred-
  decision note.
- `state/polaris_restart/iteration_trajectory.md` (+~10) — §8.3.5 log.

## §B — Red-team focus

1. Does the doc faithfully reflect iter-2's APPROVE'd decision tree, or has
   it drifted?
2. **Per-role contingency branches** — Box 1 SGLang swap trigger
   (empirical FP4 V4 Pro failure on vLLM, NOT "no FP4 path"); Box 2 SGLang
   swap trigger (symmetric: Maverick INT4 works on SGLang but not vLLM).
   Both folded?
3. **TensorRT-LLM direct-backend fallback** — recorded separately from
   Dynamo wrapper note (per iter-2 P2)?
4. **Constraint reaffirmation** — two boxes, two-family, EU/Canada GPU,
   FP4/INT4 weight residency, MoE trillion-class maturity.
5. **Scope discipline** — doc-only ship; no `.env`/config/src changes; no
   per-route changes; no engine wiring (that's I-cd-009).

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
