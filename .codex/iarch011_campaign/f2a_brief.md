HARD ITERATION CAP: 3 per document. This is iter 2 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 3 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-arch-011 F2a-ALONE (F2b REVERTED) — the 794->9 breadth-collapse fix

Review the patch FILE (static only, do NOT run pytest):

    .codex/iarch011_campaign/f2a_diff.patch   (3 files; workdir C:/POLARIS read-only — cat/grep surrounding code as needed)

## WHAT CHANGED SINCE YOUR ITER-1 REVIEW
Your iter-1 verdict on the PREVIOUS diff was REQUEST_CHANGES with TWO P0s, BOTH about F2b (a context manager `_advisory_entailment_disabled()` that forced `PG_STRICT_VERIFY_ENTAILMENT=off` around `_assemble_baskets`):
 - P0-1: entailment-off advisory `span_verdict==SUPPORTS` members get rendered as inline corroborator citations (provenance_generator.py:3246 `_verified_corroborators_for_tokens`) WITHOUT re-verification -> un-entailed citations in the report.
 - P0-2: the process-global env mutation could leak into Stage-2 on the credibility-pass `asyncio.wait_for` timeout (to_thread not cancellable) -> binding gate runs with entailment off.

BOTH P0s ARE ACCEPTED AS CORRECT. The fix: **F2b is FULLY REVERTED.** The `_advisory_entailment_disabled()` context manager, the `import contextlib`, and the `with` wrapper are all GONE. The basket per-member verify now runs under entailment-ENFORCE (the `PG_STRICT_VERIFY_ENTAILMENT` default), exactly as before this campaign. `grep -c "_advisory_entailment_disabled\|environ\[.PG_STRICT" f2a_diff.patch` == 0 (no env mutation anywhere in the diff).

## WHAT REMAINS (the F2a-alone fix)
1. **multi_section_generator.py `_credibility_guard_decision`**: split the guard so `not gov_suffixes` keeps the legacy degrade(always-release)/raise; a MISSING JUDGE with gov_suffixes present returns `"run"` under always-release (was `"degrade"`). `run_credibility_analysis(judge=None)` then runs the COMPLETE priors-only pass (ZERO scoring LLM calls; every source LABELED `credibility_unscored` — a disclosed gap, never fabricated), which BUILDS the per-claim baskets the breadth enrichment surfaces. The old `"degrade"` threw the basket away -> the 794->9 collapse. Legacy (always-release OFF) keeps the byte-identical fail-closed `raise`.
2. **credibility_pass.py**: COMMENT-ONLY change (+10 lines, 0 code) at the `_assemble_baskets` call — an anti-regression note documenting WHY the per-member verify MUST stay entailment-ENFORCE (because span_verdict==SUPPORTS is consumed at render without re-verification), and that the serial-entailment hang is avoided by the architecture's existing bounded parallelism (`PG_CREDIBILITY_PASS_MAX_INFLIGHT`, slate=16, over the I-arch-007 ITEM-2a per-thread `threading.local` judge client — deadlock-safe) + the `PG_CREDIBILITY_PASS_WALL_S=3000` wall. NO behavior change.
3. **test_lane_section_arch005.py**: updates the one unit test that ENCODED the old `judge=None -> "degrade"` assertion; it now asserts `judge=None+gov-present -> "run"` and keeps `gov-missing -> "degrade"` + the legacy `raise`.

## BEHAVIORAL PROOF (offline, banked drb_78 corpus, no VM)
guard judge=None -> "run"; priors-only basket builds; breadth enrichment surfaces 754 unbound-SUPPORTS candidates (was 0, reason=credibility_analysis_none); 663 distinct render sources. 50 guard/basket/cred tests pass. (Note: that 754/663 is the entailment-OFF MEMBERSHIP CEILING measured by the offline harness; PRODUCTION ships entailment-ENFORCE which culls the ceiling to the real cited count, proven on the VM — the harness is explicit about this, it is NOT a faithfulness relaxation.)

## YOUR JOB — confirm the P0s are resolved + 3-PRONG on F2a
A. Confirm BOTH iter-1 P0s are RESOLVED by the F2b revert: (P0-1) the basket verify now runs entailment-enforce so every span_verdict==SUPPORTS appended at provenance_generator.py:3246 / contract_section_runner.py is entailment-verified; (P0-2) no env mutation remains, so no leak into Stage-2 is possible. Grep the tree to confirm there is no OTHER writer of PG_STRICT_VERIFY_ENTAILMENT in src/.
B. 3-PRONG on F2a: does it (1) relax any binding gate (strict_verify/NLI/4-role D8/span-grounding)? (2) grandfather/outdated? (3) add a cap/floor/throttle/hard-filter or WRONG-MERGE non-same claims? F2a adds none — confirm. Specifically confirm run_credibility_analysis(judge=None) makes ZERO scoring LLM calls (priors-only) and ships a disclosed gap, never a silent false-green and never a hold.
C. Any NEW P0/P1 introduced by the guard split itself (e.g. a path where judge=None + gov-present should still have degraded)?

## OUTPUT SCHEMA (return EXACTLY this; last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
