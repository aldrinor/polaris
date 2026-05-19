HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-006/codex_diff.patch` (~144 lines incl. trailer).
Read ONLY that one file.

# Codex DIFF review — I-cd-006 / GH#638: license sign-off

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-006/brief.md`
(brief APPROVE iter 2 after iter 1 RC surfaced 2 P1 — Llama 4 EU-no-grant
clause + Hunyuan EU prohibition — both addressed). Two files in the canonical
diff:

- `docs/models/evaluator_license_signoff.md` (NEW, 122 LOC) — per-license
  headline + Carney-fit clearance + deployment-step dependencies for I-cd-009
  + attribution implementation plan + explicit §E sign-off declaration.
- `state/polaris_restart/iteration_trajectory.md` (+~10) — §8.3.5 log.

**Sign-off mode (operator's session re-classification):** "Auto-merge per
Codex." Your APPROVE on this diff completes the operator's legal acceptance.

## §B — Red-team focus

1. **Per-license clearance accuracy** — every clause in §B of the deliverable
   doc matches your iter-1/iter-2 web-verified license text. Any clause you
   verified that the doc misstates is a P1.
2. **Llama 4 EU-no-grant resolution** — the doc records "POLARIS operator is
   Canada-domiciled, EU clause does not apply, even if compute relocates to
   EU GPU per the 2026-05-18 relaxation." Confirm this is the right legal
   formulation (domicile = legal entity, not compute location).
3. **Hunyuan conditional** — the doc records Hunyuan as ACCEPTED only if
   Carney compute stays outside the EU AND all licensed acts (use,
   reproduction, modification, distribution, display, output) stay outside
   EU. Confirm this captures iter-2 P2.
4. **3 deployment dependencies** for I-cd-009 — HF gated access for Meta
   Llama 4 + Llama 3.1, + community INT4 quant wrapper-license check.
   Anything else?
5. **Attribution plan** — `docs/transparency.md` sentence + demo UI footer
   landing at I-cd-022; sufficient for Meta's "prominent + visible + legible"
   requirement?
6. **Scope discipline** — diff touches only the sign-off doc + trajectory
   log. No `.env` / config / src changes.

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
