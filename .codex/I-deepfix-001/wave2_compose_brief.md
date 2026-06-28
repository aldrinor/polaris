HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## CHANGES SINCE ITER 1 (your P1 + P2 on B13 fixed — re-verify FIRST)
- **P1 (B13 timeout not actually bounded — hang class) FIXED** in analyst_synthesis_deviation_check.py: replaced `with ThreadPoolExecutor(...) as pool:` (whose context exit does `shutdown(wait=True)` and re-blocks on a timed-out Sentinel worker) with a manual pool + `try/finally: pool.shutdown(wait=False, cancel_futures=True)`. Also switched from a PER-FUTURE deadline (which summed across sentences) to ONE TOTAL wall deadline via `time.monotonic()` (the futures run concurrently in the pool, so one wall budget bounds the whole batch). Any future unresolved within the total deadline fail-CLOSES to LOW (`supported.setdefault(i, False)`). Verified offline: a 10s judge with a 1s deadline returns in 1.01s, the sentence is KEPT + LOW-labeled, a fast supporting judge leaves the sentence unlabeled.
- **P2 (outer caller fail-opens silently to unlabeled) FIXED** in analyst_synthesis.py: an unexpected checker/wiring exception now increments a DISTINCT `synthesis_deviation_check_error_count` telemetry counter and logs `logger.error(..., exc_info=True)` (fail-LOUD), so a wiring break is visible in the manifest rather than mistaken for a clean no-deviation run. (An in-checker judge fault is still handled LOW per-sentence as before.)
- Verified offline: 4/4 standalone checks (prompt timing + KEEP-and-LABEL + fast-path).

## (Original iter-1 brief follows.)
HARD ITERATION CAP (orig): 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Same bar every iter. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining-non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

REVIEW MODE: STATIC ONLY. Read `.codex/I-deepfix-001/wave2_compose.patch` + changed regions only. No pytest/pipeline. Emit the schema at the end.

# I-deepfix-001 WAVE 2 — WIRER-COMPOSE: composition/synthesis firing-seams (FAITHFULNESS-CRITICAL)

Files: weighted_enrichment.py (CRLF), credibility_pass.py, independence_collapse.py, provenance_generator.py, analyst_synthesis.py, analyst_synthesis_deviation_check.py (NEW), sentence_repair.py + test.

## Seams wired
- **B6(a)** chrome screen in weighted_enrichment.sanitize_rendered_report (PG_CORROBORATION_SANITIZE default-ON): a chrome basket HEADER bullet's claim text is replaced with a placeholder; the verified-source COUNT + every SUPPORT/GROUNDED-BUT-WEAK/CONTRADICTED sub-bullet are KEEP-ONLY (no source dropped). NOTE the agent deliberately screens ONLY the header claim string, NOT the sub-bullets (screening a url/DOI locator line risks the chrome predicate dropping a corroborating source) — this is a conscious §-1.3 keep-all choice.
- **B9(a)** deterministic tier-authority prior in credibility_pass._run_chain (PG_CREDIBILITY_TIER_AUTHORITY_JOIN default-ON): a tier-derived authority_score joins onto any row missing one BEFORE collapse, so weight_mass goes non-zero. Fail-loud canary on all-zero authority (hard-raise opt-in only via PG_REQUIRE_NONZERO_AUTHORITY).
- **B9(b)** origin_cluster_id collision fix in independence_collapse: distinct non-empty DOIs NEVER union; identical non-empty DOI IS a positive union trigger (overrides the mirror-allowlist skip) so two mirrors of one paper share one cluster; claim-local direct_quote prioritized for the cosine.
- **B9(c)** mirror-cite collapse in provenance_generator.resolve_provenance_to_citations_with_count (PG_MIRROR_CITE_COLLAPSE default-ON): inline numbers sharing one origin_cluster_id fold to one citation + "(also mirrored)" note + telemetry.
- **B13** NEW analyst_synthesis_deviation_check wired into analyst_synthesis.generate_analyst_synthesis AFTER _screen_qualitative_negations BEFORE return (PG_ANALYST_SYNTHESIS_DEVIATION_CHECK default-ON, shares PG_SWEEP_ANALYST_SYNTHESIS kill-switch): bounded-parallel Sentinel groundedness, KEEP-and-LABEL (BUCKET_LOW unsupported / BUCKET_NO_SOURCE uncited), fail-closed to LOW.
- **B17** sentence_repair marker-prune (PG_REPAIR_MARKER_PRUNE_ENABLED default-ON): prompt constraint #1 -> keep-supporting/drop-unsupported/never-add; orchestrator equality test replaced with non-empty-SUBSET test; each dropped marker confirmed unsupported via _EntailmentJudge (prune ONLY on NEUTRAL/CONTRADICTED; fail-closed KEEP on judge_error/ENTAILED); retained markers re-verify via UNCHANGED verify_sentence_provenance.

## VERIFY HARDEST (adversarial — faithfulness boundary)
1. **B9 CONSOLIDATE-not-DROP (§-1.3):** confirm the origin-cluster fix + mirror-cite collapse NEVER delete a corroborating source — they collapse DISPLAY citations sharing one origin, keeping all sources in the basket. Distinct DOIs must never merge (that would hide independent corroboration). Confirm same-DOI union is the only positive trigger beyond the cosine.
2. **B17 fail-CLOSED (P0 if wrong):** confirm a marker is pruned ONLY when _EntailmentJudge returns NEUTRAL/CONTRADICTED; on judge_error OR ENTAILED the marker is KEPT. Confirm the subset test accepts a drop but REJECTS an added/empty marker set. Confirm retained markers still pass the UNCHANGED verify_sentence_provenance (a pruned sentence cannot ship an unverified claim).
3. **B13 KEEP-and-LABEL never drops:** confirm the deviation check only appends a confidence LABEL (BUCKET_LOW/NO_SOURCE) and NEVER deletes an analyst-synthesis sentence; fail-closed to LOW on Sentinel error (not drop, not silent-pass-as-grounded).
4. **B6 keep-all:** confirm the chrome screen replaces only a chrome HEADER claim string and never drops a SUPPORT/source sub-bullet or a verified count.
5. **B9(a) weight not laundering:** confirm the tier-authority prior is a transparent WEIGHT (credibility surfaced), not a fabricated authority that promotes a junk source; confirm it only fills a MISSING authority_score, never overwrites a real one.
6. **No faithfulness-engine relaxation:** strict_verify / NLI entailment / span / 4-role / provenance-token parsing UNCHANGED. B17 reuses the existing _EntailmentJudge; B13 reuses Sentinel; neither loosens a threshold.

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
