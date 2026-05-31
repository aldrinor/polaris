# Codex gate — the COMPLETE solution to beat frontier: complete, safe, cost-honest?

ADVERSARIAL §-1.1 + clinical-safety auditor. A workflow produced the plan below (its sub-agents leaked a
forbidden advisor tool, so do NOT trust their self-checks — re-verify). Rule whether the plan is sound,
complete, cost-honest, and SAFE. Hardest scrutiny on the composition fix (could it re-open a fabrication
hole?) and the GPU cost (the workflow self-corrected it mid-run). Output YAML verdict FIRST. 5-cap; iter 1.

```yaml
verdict: SOUND | NEEDS_CHANGES | OVERCLAIMS
safety_holes: [...]          # esp. the verifier-window widening
overstated_claims: [...]     # esp. "free clinical channels", GPU cost, per-parameter "beats"
missing_pieces: [...]        # anything the plan omits to beat frontier
cost_realistic: <true|false>
honest_one_line: "<your verdict on the plan for the operator>"
```

## The plan (verify each load-bearing claim)
TIER 1 (FREE): deepener default-ON for golden set + raise its URL cap (off 20) + thinness-floor trigger
(fire on <~40 sources even if "adequate") + fail-loud on missing key; raise breadth 12/12->25 +
PG_SWEEP_FETCH_CAP 40->120 + PG_LIVE_MAX_EV_TO_GEN 20->50; open 3 NEW clinical channels claimed FREE — keyed
PubMed E-utilities search (NCBI_API_KEY present), ClinicalTrials.gov, Cochrane.
TIER 2 (LOW-SPEND <$1/q): build an iterative retrieval loop (8 rounds default-ON; search->read->gap-analysis->
search; claim: EVERY new source still passes the same tier-classify + per-sentence verify gate; kill-switch).
TIER 3 (SPEND, authorize): self-host Mirror(Cohere Command A 111B)/Sentinel/Judge on Vast GPUs; claim: Command A
111B needs ~135GB => 2x80GB cards; ~$5-15/hr live serving; ~$25-75 total for the few-hour proving window;
Vast balance currently 0. Generator stays hosted (no GPU cost).
TIER 4 (BUILD): 3 clinical backends + deepener fixes; the iterative loop module; COMPOSITION FIX — verifier
recall: 18 of the dropped sentences failed because the writer cited the RIGHT document but the WRONG paragraph;
fix = teach the verifier to search the WHOLE cited document for the best supporting passage and re-judge,
"without loosening the standard"; ALSO shrink the unverified Analyst-Synthesis layer; contradiction feed-through
(qualitative conflicts -> generator prompt + two-family evaluator, not just contradictions.json+Methods);
4-role serving configs + production caller; the guardrail.
PROVING: offline mocked dry-run (free) -> load credit -> live 4-role canary (1 Q) -> golden-5 -> walled-off
dual scoring (POLARIS self-gates on native checklist, NEVER the rubric; external scorer claim-by-claim vs
frozen rubric identically for all 3 systems; report clinical-3 + overall-5 separately; POLARIS blind to key).
DISCLOSURE+GUARDRAIL: file 5 retroactive §6.2 degradation records (the 5 silent downgrades); build a CAPABILITY
MANIFEST (declares rounds/sources/deepener-on/contradiction-feed/min-verified-fraction) + a conformance check
at startup + merge gate that FAILS LOUDLY if the running config is below the manifest (same pattern as the
existing architecture-drift gate).
PER-PARAMETER MAP: BEATS = faithfulness, auditability, contradiction-surfacing, clinical-channel authority;
PARITY = depth, breadth; BEHIND-deliberate = report length, semantic memory.

## The real risks to rule on
1. SAFETY: does "search the whole cited document for the best supporting passage and re-judge" re-open a
   fabrication hole — could a sentence match an UNRELATED passage in a long doc and pass? Is "without loosening
   the standard" actually achievable, or is this the dangerous one? Prescribe the guard if so.
2. Are the 3 clinical channels genuinely FREE/keyless (PubMed E-utilities with the present key, ClinicalTrials.gov
   v2 API, Cochrane)? Or does Cochrane need a paid license / no public API?
3. Is the GPU sizing right (Command A 111B -> 2x80GB) and is ~$25-75 for the proving window realistic, or
   understated?
4. Does "every new source in the iterative loop passes the same verify gate" hold, or is there a laundering
   risk in the loop?
5. Is the per-parameter map honest — is "clinical authority BEATS" overclaimed (frontier may also hit PubMed)?
   Is "depth PARITY" right, or still behind?
6. COMPLETENESS: to beat frontier on the parameters that decide a clinical DR tool, is anything MISSING from
   this plan?

## Your ruling
Rule SOUND / NEEDS_CHANGES / OVERCLAIMS. List safety holes (esp. the verifier window), overstated claims,
missing pieces. Is the cost realistic? Your honest one-line verdict for the operator.
