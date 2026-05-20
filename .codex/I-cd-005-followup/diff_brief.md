HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-005-followup/codex_diff.patch` (464 lines incl.
trailer). Read ONLY that one file.

# Codex DIFF review — I-cd-005-followup: re-lock evaluator to google/gemma-4-31B-it

## §A — What this is

The diff implements the Codex-APPROVED brief
`.codex/I-cd-005-followup/brief.md` (iter 2 APPROVE — iter 1 RC surfaced
Gemma 4 400B is unreleased; operator escalated → Claude picked 31B dense;
iter 2 APPROVE with 8 operational P2s folded into the docs). Three files in
the canonical diff:

- `docs/models/evaluator_pick.md` — REWRITE (supersedes the I-cd-005 Llama
  4 Maverick lock with `google/gemma-4-31B-it` + community AWQ
  `ebircak/gemma-4-31B-it-4bit-W4A16-AWQ` via vLLM
  `--quantization compressed-tensors`).
- `docs/models/evaluator_license_signoff.md` — REWRITE (supersedes the
  I-cd-006 Llama 4 sign-off with Apache 2.0 + Gemma PUP overlay shape).
- `state/polaris_restart/iteration_trajectory.md` — §8.3.5 log.

## §B — Red-team focus

1. **HARD CONSTRAINTS section in the pick doc** — does it lock
   `google/gemma-4-31B-it` unambiguously at the top, with explicit
   superseding language for I-cd-005? Per the operator's "100% failure"
   feedback on the original I-cd-005 brief, this is the structural-quality
   gate this followup MUST get right.
2. **All 8 iter-2 brief P2s folded** — HF id, no Google quant siblings,
   Apache 2.0 + Gemma PUP overlay, `--quantization compressed-tensors`
   (NOT `awq`), vLLM Gemma4 recipe + parser, two-family `('deepseek',
   'gemma')`, no LLM-as-judge weakness P1, NVIDIA NVFP4 Blackwell-only
   sibling noted but not the 4×H100 target.
3. **Apache 2.0 vs Llama Community delta** correctly recorded in the
   sign-off doc: no MAU threshold, no HF gating, Apache-style attribution
   only (NO "Built with Gemma" placement requirement, vs Llama's required
   "Built with Llama" prominence).
4. **Hard fallback preserved**: Llama 3.1 405B + AWQ/GPTQ-INT4 on vLLM is
   still recorded as the safety net (kept from I-cd-005).
5. **Two-family check**: `check_family_segregation('deepseek/deepseek-v4-pro',
   'google/gemma-4-31b-it')` returns `('deepseek', 'gemma')` per Codex iter-2
   P2 verification. Recorded in the pick doc.
6. **I-cd-008 impact note** — relaxed topology risk profile correctly
   captured (Gemma 4 31B INT4 ≈ 16 GB on 4×H100=320GB → massive headroom
   vs Maverick's 17B-active MoE).
7. **Scope discipline** — diff touches only the two pick/signoff docs +
   trajectory log. No `.env`/config/src/web changes.

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
