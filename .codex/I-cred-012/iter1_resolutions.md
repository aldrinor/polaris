## ITER-1 RESOLUTIONS (binding amendments to §2 — supersede the proposed integration)

All 4 P1 + the P2 refinements resolved at the design-principle level. Each per-hook SUB-ISSUE (007b/008b/010b/006b) grounds + implements its EXACT line-level call site under its own diff-gate; this architecture locks the ordering / corpus-universe / fail-loud / budget PRINCIPLES.

**P1-1 — P8 render ordering (FIXED):** P8 hooks INSIDE `multi_section_generator`, AFTER `strict_verify` produces the per-section `SentenceVerification[]` but BEFORE `resolve_provenance_to_citations` (the per-section render, ~multi_section_generator.py:2264) — so the populated disclosure fields actually render. NOT a post-`generate_multi_section_report` step. P8's inputs (`credibility_by_evidence`, `origin_by_evidence`) come from the pre-generation credibility pass and are threaded into the generator; P8 populates the kept verifications, then resolve renders them.

**P1-2 — corpus universe per product (DEFINED):**
- The credibility pass runs over the **FINAL generator-visible evidence set** (`evidence_for_gen` — AFTER expansion/deepener/agentic merge, journal_only filtering, V30/upload prepend, saturation reselect, finding-dedup), NOT the raw first-`run_live_retrieval` corpus. It RE-RUNS after any dissent gap-round so the analysis reflects the enlarged corpus.
- P4 / P5 / P6 / P7 operate over that same final generator-visible set.
- P8 operates over every `evidence_id` that `strict_verify` actually cites (the kept verifications' tokens).
- P10 builds dissent queries from the round-N contested set (P5 edges + P6 weights) BEFORE the final pass.

**P1-3 — fail-LOUD at activation (FIXED — also kills the silent-downgrade false alarm):** the `run_credibility_analysis` orchestrator, under the master slate, converts a P2 `judge_error` (or any wired-module exception) into `abort_credibility_pass_error` — it does NOT accept the priors-only fallback as a green pass. A dead production judge ABORTS, never silently degrades to a false-green advisory. (The P2 module's per-row `judge_error` fail-soft is for OFFLINE/robustness; the activation orchestrator escalates it to a hard abort.)

**P1-4 — dissent budget (FIXED):** P10's dissent retrieval runs as a BOUNDED round that shares the EXISTING saturation budget counters (`PG_SATURATION_MAX_ROUNDS`, `PG_SATURATION_MAX_RETRIEVAL_CALLS`) + telemetry — it never opens an out-of-budget retrieval path. Activation precondition: the planner saturation path is available, OR the dissent round is accounted in the same budget ledger. The fail-closed preflight asserts this.

**P2 refinements:**
- Q1/Q2 confirmed: pure `synthesis/credibility_pass.py` orchestrator called from the RUNNER at the final-corpus hook (not inside `live_retriever`); master `PG_SWEEP_CREDIBILITY_REDESIGN` + per-module sub-flags, Gate-B preflight force-on all required + fail-closed if any off.
- **P3 downstream contract:** `supersession_adjustment(row)` POST-MULTIPLIES the P2 credibility judgment (advisory) — its `multiplier` scales the disclosed `credibility_weight`, its `soft_warning`/`certainty_downgrade` flow to the disclosure; it does NOT mutate rows in place beyond the analysis result, and is telemetry'd.
- **P7 disclosure isolation:** the both-sides block is appended as a DISCLOSURE appendix OUTSIDE the release-scored prose — the 4-role D8 evaluator + native claim-extraction must NOT see its numeric weights as report claims. (Same posture as `limitations_text`.) The sub-issue 007b test asserts the D8/claim-extraction input excludes the block.
- **P4 gating:** P4 has no per-module sub-flag; documented as MASTER-ONLY gated (the master slate `PG_SWEEP_CREDIBILITY_REDESIGN` is its switch). OFF byte-identity holds via the master flag.

**Net activation order (locked):** retrieve+mutate → (master-on) credibility_pass over `evidence_for_gen` [P4 origins → P3 temporal → P2 score (FAIL-LOUD on judge_error) → P5 claims/edges → P6 weight-mass] → if edges: P10 dissent bounded saturation round (shared budget) → re-run pass on enlarged corpus → generate → strict_verify (BINDING) → P8 populate (before resolve) → resolve render → 4-role D8 (BINDING, block excluded) → assemble [P8 disclosure fields + P7 both-sides appendix].
