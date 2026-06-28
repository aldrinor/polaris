HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Read `.codex/I-deepfix-001/phase4_slate.patch` (run_gate_b.py only). Emit the schema at the end.

# I-deepfix-001 Phase 4 — activation slate (make every winner FIRE on the paid run)

The entire fix campaign (18 baskets + B2) is committed. This is the pre-paid-run preflight slate: run_gate_b.py's force-on block previously set NONE of the campaign flags, so the run could be a no-op for the default-OFF winners. This change force-ons the campaign winners in `run_gate_b_query` (entry-scoped, before run_one_query; read at CALL time by each module's *_enabled() helper — no import-time freeze).

## What it sets (faithfulness-NEUTRAL: WEIGHT/CONSOLIDATE/DISCLOSE + the one §-1.3 legit hard-drop B2; the faithfulness engine is untouched)
- **Default-OFF winners that MUST be set or they never fire:** PG_EXTRACT_USER_CONSTRAINTS (B10 date/journal/lang), PG_TITLE_BODY_CONSISTENCY (B14, never drops).
- **Default-ON winners pinned so a stray operator/.env=0 cannot silently disable them:** PG_BLOCKED_REFERENCE_DENYLIST (B2), PG_QUERY_DIRECTIVE_SCREEN (B3), PG_CORROBORATION_SANITIZE (B6a), PG_CLAIM_SHAPE_GATE (B6b/B8), PG_CREDIBILITY_TIER_AUTHORITY_JOIN (B9a), PG_MIRROR_CITE_COLLAPSE (B9c), PG_CONSOLIDATION_NLI_PROSE + PG_FACT_DEDUP_PROSE (B15), PG_EPISTEMIC_MARKER_GUARD + PG_TEMPORAL_SCOPE_GUARD (B16), PG_REPAIR_MARKER_PRUNE_ENABLED (B17), PG_RENDER_GFM_TABLE_NORMALIZE + PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH (B18), PG_REPORT_D8_BANNER + PG_REPORT_FULL_DROP_DISCLOSURE (B8), PG_OPENROUTER_PROVIDER_SLO (B11C1).
- **Run-config required for the all-GLM-5.2 run:** PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1 (else the two-family invariant aborts; B4 makes PT03/badge HONESTLY disclose the non-segregation).

## Deliberately NOT set (verify this reasoning is sound)
- PG_ANALYST_SYNTHESIS_DEVIATION_CHECK (B13): its parent PG_SWEEP_ANALYST_SYNTHESIS is force-OFF in the slate (benchmark report = verified-only surface); forcing the parent ON would surface an unverified interpretive layer (a faithfulness regression). Correct to leave off.
- PG_ROLE_MIN_TPS (B11 C2): numeric tok/s opt-in, default 0.0 (fail-open). PG_REQUIRE_NONZERO_AUTHORITY (B9a canary): fail-open opt-in; forcing it would ABORT on a wiring blip. Both correctly left off.

## VERIFY
1. The two default-OFF winners (B10, B14) are now force-ON (else they silently no-op — the campaign's whole point).
2. §-1.3 banned number-forcing knobs are NOT force-ON (PG_SPAN_PER_SOURCE_CITE_CAP + PG_CAPPED_FINDING_DEDUP are pinned "0" elsewhere in the slate; this change adds no cap/target/thinner).
3. Faithfulness-neutral: nothing here changes strict_verify/NLI/4-role/provenance; the only hard-drop activated is B2 (explicit operator prohibition).
4. The deliberate non-pins (B13 parent, ROLE_MIN_TPS, REQUIRE_NONZERO_AUTHORITY) are correctly left off.
5. CRLF: run_gate_b.py is CRLF-in-HEAD; confirm a partial diff, not a whole-file flip.

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
