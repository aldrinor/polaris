HARD ITERATION CAP: 3 per document. This is iter 1 of 3.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 3 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-arch-011 F2a + F2b (the 794->9 breadth-collapse fix)

Review the patch FILE (do NOT run pytest; static review only):

    .codex/iarch011_campaign/f2_diff.patch   (read it with cat; 3 files changed)

Workdir is C:/POLARIS (read-only sandbox). Read any surrounding source you need with cat/grep, but do NOT execute anything.

## CONTEXT — what broke and what this fixes
POLARIS deep-research run #5 RENDERED but cited only **9 of 794** generator-visible sources. Root cause, traced end-to-end:
- To kill a thread/GIL deadlock in the LLM *credibility scoring* judge, the run sets `PG_CREDIBILITY_LLM_JUDGE=off`, so the judge arrives `None` into generation.
- `multi_section_generator._credibility_guard_decision(judge=None, gov_suffixes=<present>, always_release=True)` returned `"degrade"` → `credibility_analysis` stays `None` → the ITEM-2 BREADTH enrichment (`weighted_enrichment.diagnose_unbound_supports_selection`) has NO baskets to surface → only the ~9 contract-bound sources render. That is the entire 794→9 funnel.

## THE FIX (two parts)
**F2a** (multi_section_generator.py): split the guard. `not gov_suffixes` keeps the legacy degrade(always-release)/raise(legacy). A MISSING JUDGE with gov_suffixes present now returns `"run"` under always-release (was `"degrade"`). `run_credibility_analysis(judge=None)` runs a COMPLETE priors-only pass (ZERO scoring LLM calls — scoring needs a judge), every source LABELED `credibility_unscored` (a disclosed gap, never fabricated), which BUILDS the per-claim baskets the breadth enrichment surfaces. Legacy (always-release OFF) keeps the byte-identical fail-closed `raise`.

**F2b** (credibility_pass.py): the ADVISORY per-member basket verify calls `verify_sentence_provenance`, whose 6th-check entailment judge defaults to ENFORCE (`PG_STRICT_VERIFY_ENTAILMENT`, default "enforce") and fires ONE serial LLM call per member. With F2a building the priors-only basket over ~767 members that is a SERIAL-entailment HANG (the same Q72/Q76/Q90 hang). `_advisory_entailment_disabled()` forces `PG_STRICT_VERIFY_ENTAILMENT=off` for the DURATION of the single `_assemble_baskets` call (the per-member ThreadPoolExecutor is created AND joined inside that call, so workers only READ the off value — no per-thread race), then restores the prior value.

The test file change updates the one unit test that ENCODED the old judge=None→"degrade" assertion (it now asserts judge=None→"run" + keeps gov-missing→"degrade").

## BEHAVIORAL PROOF already obtained (offline, banked drb_78 corpus, 794 rows, no VM)
- guard judge=None → "run"; priors-only pass COMPLETES in 11.0s under PG_STRICT_VERIFY_ENTAILMENT=enforce (was hanging indefinitely); 1433 SUPPORTS members.
- breadth enrichment surfaces **754** unbound-SUPPORTS candidates (was 0, reason=credibility_analysis_none); deterministic render upper bound **663** distinct sources. Existing credibility/basket/guard tests: 40 pass.

## YOUR JOB — the 3-PRONG MANDATE (reject the fix if ANY holds)
1. **Faithfulness relaxation?** Does F2a or F2b WEAKEN any binding gate (strict_verify / NLI / 4-role D8 / span-grounding)? Specifically scrutinize F2b: I claim disabling the entailment 6th-check in the ADVISORY basket verify is faithfulness-NEUTRAL because (a) it is advisory (never a release gate — see `_verify_member_in_isolation` docstring), and (b) every surfaced member is RE-VERIFIED by the BINDING section gate (`_run_section`→`strict_verify`) at render under entailment-ENFORCE. VERIFY that the binding section render gate is a genuinely SEPARATE call path that still runs entailment=enforce (i.e. `_advisory_entailment_disabled` restores the env BEFORE Stage-2 section generation). If the env override leaks into the binding render gate, that IS a P0 faithfulness hole — find it or refute it.
2. **Grandfather / outdated?** Any stale assumption or reliance on removed behavior?
3. **Cap / floor / throttle / hard-filter (§-1.3)?** Does either change add a cap/target/top-N/relevance-DROP, or WRONG-MERGE non-same claims? (F2a/F2b add none; confirm.)

Also flag: env-mutation thread-safety (is the single set/restore around `_assemble_baskets` actually race-free given the run's concurrency?), restore-on-exception correctness (try/finally), and any way `judge=None` could now make hundreds of LLM scoring calls (it must not — confirm priors-only).

## OUTPUT SCHEMA (return EXACTLY this, last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
