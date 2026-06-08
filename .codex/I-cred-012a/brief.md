# I-cred-012a — runner/generator INTEGRATION of the credibility pass (implementation approach) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

This is the IMPLEMENTATION-APPROACH brief for the FIRST and DEEPEST activation hook — running the
committed `synthesis/credibility_pass.run_credibility_analysis` orchestrator in the LIVE path over the
generator's EFFECTIVE evidence pool, under the locked I-cred-012 architecture (force-APPROVE iter-5).
NO code yet — confirm the hook placement + threading + fail-closed against the spend-bearing generation
core BEFORE I edit it. The per-resolve-site P8 render is 008b; the both-sides appendix is 007b; this
issue is ONLY: run the pass over the effective pool + thread its outputs to where 008b/007b consume them.

## 0. HARD CONSTRAINTS

- ADVISORY only — strict_verify + 4-role D8 stay the ONLY binding gates. default-OFF `PG_SWEEP_CREDIBILITY_REDESIGN` ⇒ byte-identical (no call, no thread, no signature behavior change).
- FAIL-LOUD (drb_72 lesson): the orchestrator already aborts on missing eid / judge_error / judge-absent. The runner must pass the PRODUCTION judge + gov_suffixes; under the master slate the fail-closed preflight asserts they're present.
- Do NOT mutate the binding flow: generation, strict_verify, D8 unchanged when OFF.

## 1. Grounded sites (already read)

- Runner generation call: `scripts/run_honest_sweep_r3.py:4707` `multi = await generate_multi_section_report(research_question=q["question"], evidence=evidence_for_gen, ...)`.
- Generator M-52 effective-pool pull: `multi_section_generator.py:4628` `_m52_pull_from_live_corpus(evidence_pool, live_corpus, primary_trial_anchors)`; M-44 injection 4638-4669. After ~4670 `evidence_pool` is the EFFECTIVE pool (every row the generator can cite).
- P8 consumes the analysis at the 4 resolve sites (2264 / 4910+4950 alias / contract 845 / quantified 380) — 008b.

## 2. The implementation decision (PLEASE CONFIRM)

The architecture P1-2 said: run the pass over the EFFECTIVE pool — "hoist the M-52 pull before the pass, OR define the universe as the generator's effective evidence pool." Two options:

- **(A) Generator-internal pass:** call `run_credibility_analysis` INSIDE `generate_multi_section_report`, just AFTER the M-52/M-44 block (~4670), over the post-M-52 `evidence_pool`. The generator gets `credibility_judge` + `gov_suffixes` + the master flag as new optional params; the resulting `CredibilityAnalysis` is held in the generator and handed to the per-section P8 wrapper (008b). PRO: sees the true effective pool with no refactor. CON: the generator now imports `credibility_pass` + carries the judge.
- **(B) Runner hoist:** lift the M-52 selection out of the generator to the runner, run the pass in the runner over the hoisted effective pool, pass `CredibilityAnalysis` into `generate_multi_section_report` as a param. PRO: keeps the generator pure-ish. CON: refactors M-52 (a belt-and-suspenders safety net) — higher regression risk in the spend-bearing path.

**I lean (A)** — least disturbance to the M-52 safety net, the pass sees exactly what the generator cites, and the flag-gate keeps OFF byte-identical. **Q1: confirm (A) vs (B)**, given (A) makes the generator depend on the credibility chain.

**Q2 — flag-gate + signature:** new params default to None/off so OFF is byte-identical (no pass, analysis=None, downstream P8 no-ops). Confirm the param-default approach can't change any existing call's behavior.

**Q3 — fail-closed preflight:** under master-on, assert `credibility_judge` callable + `gov_suffixes` non-empty BEFORE generation, else abort (not a silent skip). Confirm placement (runner preflight vs first generator use).

**Q4 — dissent/M-52 ordering:** 010b's append-only dissent round runs in the runner BEFORE generation and re-certs plan_sufficiency; so by the time generation's M-52 runs, `evidence_for_gen` already includes dissent rows. Confirm (A) still sees them (it runs after M-52 over the merged pool).

**Q5 — telemetry/no-throttle:** the pass must not silently drop rows from `evidence_for_gen` (no capability downgrade). It is READ-ONLY over the pool (annotates copies); confirm it cannot shrink the generator's citeable set.

## 3. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
