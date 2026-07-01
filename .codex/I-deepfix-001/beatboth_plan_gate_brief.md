HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex gate — POLARIS BEAT-BOTH master plan (strategic plan review)

Review the master plan at `.codex/I-deepfix-001/BEATBOTH_MASTER_PLAN.md` (Part 1-5 = the plan; Appendices A-H = the research + gap analyses it rests on). Repo root `C:/POLARIS`. This is a STRATEGIC plan to (a) remove 6 residual §-1.1 audit defects + run-level weaknesses, and (b) take POLARIS #1 on 5 deep-research scoreboards. It was produced by a 9-agent research/gap Workflow. You are the ONLY review gate.

## Context you must hold
- POLARIS is **WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP** (§-1.3). The ONLY hard gate is the FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 / span-grounding / provenance). The banned "day-waster" anti-pattern is bolting a hard cap/floor/thinner/target to force a breadth number.
- The audit (`.codex/I-deepfix-001/RESMOKE_S11_FORENSIC_AUDIT.md`) found the drb_72 re-smoke FAITHFUL (0 fabrication) with 6 residual defects (D1-D6) + run-level weaknesses (coverage 0.571, 12 of 88 cited, zero multi-source corroboration, GLM-tiering degraded, GPU-OOM→lexical, retrieval-wall, quantified-rejected, 3 D8 false-negatives).
- The plan's master root cause: the WEIGHT-and-CONSOLIDATE winners (PG_CONSOLIDATION_NLI / PG_CROSS_SOURCE_SYNTHESIS / PG_BREADTH_ENRICHMENT_ENABLED / PG_DOCUMENT_TYPE_WEIGHT) are default-OFF (only ON via apply_full_capability_benchmark_slate) and/or degraded under GPU-OOM + an off-vLLM judge enum.

## VERIFY (grep/read the real code — do not trust the plan's line numbers blindly)
1. **Root-cause soundness:** confirm the 4 named flags are default-OFF and that the paid `run_honest_sweep_r3.py` path does NOT apply the full slate (the plan cites `operational_readiness_preflight.py:448` warning + `apply_full_capability_benchmark_slate()` in `run_gate_b.py`). Is the "winners shipped OFF / GPU-degraded" diagnosis correct, or did the drb_72 re-smoke (which used `run_gate_b.py --smoke-scale` + explicit PG_CROSS_SOURCE_SYNTHESIS=1) actually have some winners ON? Reconcile.
2. **§-1.3 compliance of EVERY workstream (WS-0..WS-16):** flag any WS that is actually a hard-drop / cap / floor / thinner / target rather than a weight / consolidation / surfacing / disclosure / degrade-fix. Specifically scrutinize WS-8 (must stay a WEIGHT re-rank, PG_JOURNAL_ONLY OFF), WS-3 (must stay keep-all), WS-10 (Source-Necessity quarantine — must keep sources in the audit ledger + Bibliography, not delete). Any WS that relaxes the frozen faithfulness engine is a P0.
3. **Faithfulness-adjacent WS (WS-1 judge swap, WS-4 coverage credit, WS-5 D1 annotator re-key + effect-size guard, WS-11 debate router):** confirm each is safe-direction (adds caveats / credits only already-verified support / removes only transport-noise convictions / span-grounds both sides) and cannot silently relax a gate or over-claim. WS-1 swaps the D8 judge to kimi-k2.6 — confirm two-family segregation vs the deepseek-v4-pro generator holds and PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY stays 0.
4. **Module/root-cause correctness:** spot-check the D1-D6 root-cause mappings (D1→report_redactor claim_id vs span-identity keying + abstract_conclusion re-lift; D2→_basket_corroboration_block count source vs verified_support_origin_count; D3→chrome canary bullets-only; D4→M2 double-gate OFF; D5→_claim_covers_entity exact-match + empty DOI URL; D6→contradiction count + weight_basis). Are the named modules/functions real and the root causes plausible?
5. **The WS-10 orientation guard** ("point Uncited/Necessity at the 12-cited list, NOT the 88-corpus disclosure, or a win reads as a catastrophic loss") — is this correct and is the risk real?
6. **Board facts:** the plan corrects DeepTRACE lab (Salesforce not Microsoft) + metric #4 orientation (uncited/listed lower-better). Are the leaderboard numbers (AI21-DeepResearch DRB-II 64.38 #1; GPT-5-DR DeepTRACE leader) plausible/current, or is any a hallucination? Flag any board claim you cannot corroborate.
7. **Sequencing + dependencies:** is Wave A→E ordering sound (WS-0/WS-1 gate everything; WS-2 depends on WS-0; single-writer on run_honest_sweep_r3.py for WS-2/4/6/8/9)? Any missing dependency or a WS that will collide?
8. **Acceptance gate rigor:** is the GATE (fresh A100 run, kimi judge, slate ON, 6 residuals gone via fail-loud replay assertions, §-1.1 clean, scored on both harnesses) sufficient to PROVE #1 + zero residuals, or are there holes (e.g. the B1 self-graded-scorer risk the plan discloses)?
9. **Completeness:** is any residual, board, or systemic blocker MISSED? Is any WS over-optimistic (the plan itself flags WS-11 debate router + WS-15 TTD-DR as the least-de-risked + the coverage-ceiling risk — do you agree, and is anything else under-estimated)?

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
root_cause_sound: true | false   # is the winners-OFF/degraded diagnosis correct
s13_violations: [ WS-# : how it drops/caps/floors ]   # empty if none
faithfulness_engine_relaxed_by: [ WS-# ]   # empty if none
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
board_facts_unverifiable: [ ... ]   # any leaderboard number you cannot corroborate
missed_workstreams_or_blockers: [...]
sequencing_ok: true | false
acceptance_gate_sufficient: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
