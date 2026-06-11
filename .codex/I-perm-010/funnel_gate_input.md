HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

# Codex gate: verify the offline source-funnel trace for run drb_76 (#1204 / I-perm-010, Task 1)

## What you are gating

Claude built an OFFLINE forensic source-funnel for a saved POLARIS run (`drb_76`, gut microbiota / colorectal cancer, status `abort_four_role_release_held`). The funnel reconstructs, stage by stage, how many candidate sources entered the pipeline and where they were dropped, ending at the 4-role claim audit. The deliverable is `outputs/audits/I-perm-010/funnel_trace_drb76.json` (reproduced below).

The PURPOSE of #1204 is to locate where the "~90% source loss" actually happens and to honestly classify each drop as **legitimate** (genuinely-unusable source or correct faithfulness gate) vs **throttle** (a good source discarded by an arbitrary number/cap). **The dangerous error this gate must catch is a THROTTLE wrongly classified as LEGITIMATE** — that would hide a quality-suppressing cap behind a "working as intended" label, which in a clinical pipeline is exactly the silent-downgrade failure mode POLARIS forbids.

You have read access to the real saved artifacts. Verify against them; do not take the trace's word.

## Ground-truth artifact locations (all under repo root)

- Manifest:        `outputs/audits/beatboth8/drb_76/manifest.json`
- Evidence pool:   `outputs/audits/beatboth8/drb_76/evidence_pool.json` (a JSON list)
- Verification:    `outputs/audits/beatboth8/drb_76/verification_details.json`
- 4-role audit:    `outputs/audits/beatboth8/drb_76/four_role_claim_audit.json`
- Code paths cited: `src/polaris_graph/retrieval/live_retriever.py`

## The funnel trace under review (verbatim JSON)

```json
{
  "stages": [
    {"name": "discovered (unique candidate pool, all backends)", "count_in": 2981, "count_out": 2981, "dropped": 0, "source_field": "retrieval.pre_filter (=2981). Task anchor agentic_search.urls_discovered_total=800 is the AGENTIC SUB-LANE only; raw backend returns s2=1402/serper=1251/openalex=700 (discovery_funnel.*.returned) deduped to 2981."},
    {"name": "pre-fetch cull (off-topic relevance filter + fetch_cap truncation)", "count_in": 2981, "count_out": 740, "dropped": 2241, "source_field": "in=retrieval.pre_filter(2981); out=retrieval.candidates_processed=candidates_total=740. Off-topic-vs-cap split ABSENT (live_retriever notes list not persisted to manifest.json)."},
    {"name": "fetched (HTTP fetch loop over capped candidates)", "count_in": 740, "count_out": 500, "dropped": 240, "source_field": "in=retrieval.candidates_total(740); out=retrieval.fetched(500); dropped=retrieval.failed(240); fetch_success_rate=0.6757."},
    {"name": "fetched-non-empty / extracted to evidence (finding) rows", "count_in": 500, "count_out": 55, "dropped": 445, "source_field": "in=retrieval.fetched(500); out=finding_dedup.raw_row_count=55 (==len(evidence_pool.json)=55). Per-source extraction yield ABSENT (no fetched->finding-row counter); partial: tool_utilization fetched_200_but_empty_extract=26, frame_coverage_report.frame_gap_count=3."},
    {"name": "merged / deduped findings -> selection pool", "count_in": 55, "count_out": 46, "dropped": 9, "source_field": "in=finding_dedup.raw_row_count(55); out=evidence_selection.evidence_total(46). finding_dedup.collapsed_row_count=0. 9-row reduction = pool-assembly pruning (metadata_only=2 + curator_gap=3 + curator/quant); NOT a single counter."},
    {"name": "relevance-floored / tier-balanced selection -> generator", "count_in": 46, "count_out": 46, "dropped": 0, "source_field": "evidence_selection.evidence_selected=46, dropped_count=0, note 'pool_size<=max_rows (46/150)' — cap never bound."},
    {"name": "generated sentences (across 5 kept sections) [EXPANSION not drop]", "count_in": 46, "count_out": 81, "dropped": 0, "source_field": "generator.sentences_verified(40)+sentences_dropped(41)=81 candidate sentences; count_in is the 46 evidence rows. This is a generation fan-out, not a drop (verification_details.sections total_in 23+18+14+13+13=81)."},
    {"name": "survived strict_verify (provenance + numeric + content-overlap + NLI entailment)", "count_in": 81, "count_out": 40, "dropped": 41, "source_field": "verification_details.totals.sentences_dropped=41, sentences_verified=40. drop_reason_counts: entailment_failed=29, no_provenance_token=5, no_content_word_overlap_any_cited_span=4, no_integer_overlap_any_cited_span=2."},
    {"name": "survived 4-role claim audit (after D8 redaction)", "count_in": 37, "count_out": 23, "dropped": 14, "source_field": "four_role_evaluation.final_verdicts: 37 judged, 23 VERIFIED/14 UNSUPPORTED; report_redaction.redacted_count=14. Run HELD on D8 coverage 0.40<0.70 + S0 contraindications must-cover missing (NOT a source-count problem)."}
  ],
  "dominant_loss_stage": "pre-fetch cull (off-topic relevance filter + fetch_cap truncation): 2981 -> 740, absolute drop 2241. This is ~5x the next stage (extraction 500->55, drop 445) and ~55x the strict_verify drop (41). The headline '~90% source loss' lives HERE, not in the verifier. The 800-discovered anchor in the task is the agentic sub-lane only; the real discovered pool is retrieval.pre_filter=2981.",
  "dominant_reason_breakdown": [
    {"reason": "off-topic / low semantic-relevance rejection (prefetch_offtopic filter)", "count": 0, "classification": "unknown", "evidence": "live_retriever.py:2962-2982 filter_search_results appends 'prefetch_offtopic: N kept / M rejected' to a local notes list NOT persisted in manifest.json; no tool_trace.jsonl in outputs/audits/beatboth8/drb_76/. Count ABSENT -> unknown. Borderline (legitimate if genuinely off-topic, throttle if threshold over-aggressive)."},
    {"reason": "fetch_cap hard truncation of ranked-but-uncapped candidates (candidates[:fetch_cap+seeds] slice)", "count": 0, "classification": "throttle", "evidence": "live_retriever.py:2573-2647 _rerank_and_reserve returns candidates[:fetch_cap + n_seed_injected] — a HARD slice discarding every ranked candidate past the cap. DEFAULT_FETCH_CAP=40 (line 92); this sweep raised it (740 entered loop). The cap slice is PURE THROTTLE. Exact count ABSENT in manifest; count=0 is a placeholder, not a measured zero. corpus_truncated=false covers only the POST-fetch loop, not this pre-fetch cap."},
    {"reason": "aggregate measured pre-fetch drop (off-topic + cap combined)", "count": 2241, "classification": "throttle", "evidence": "retrieval.pre_filter(2981) - retrieval.candidates_total(740) = 2241 (measured). Internal off-topic/cap split is ABSENT. Classified throttle-leaning because the fetch_cap component is a pure number-driven throttle; the off-topic component is unmeasured."}
  ],
  "legitimacy_call": "MIXED, leaning THROTTLE at the dominant stage but UNMEASURED. The dominant loss (2981->740 pre-fetch cull, drop 2241) contains a PURE-THROTTLE component (fetch_cap hard slice) AND a borderline off-topic-filter component. NEITHER sub-count is persisted in the manifest, so the throttle-vs-legitimate split of the single largest drop CANNOT be adjudicated from the saved artifacts — this absence is itself the #1 forensic finding for #1204. What IS measured and legitimate: the fetch-failure tail (no_content=247 / empty_extract=26 / S2-landing=2 / timeout=2, whole-run 906-call superset) and the entire back-half verifier drop (41 sentences = 29 entailment + 5 no-token + 4 no-overlap + 2 no-integer) are genuinely-unusable-source or correct-faithfulness drops. The run was NOT held on source count — it was held by the 4-role D8 coverage gate (0.40<0.70 + S0 contraindications must-cover missing). NET: the headline ~90% source loss is NOT primarily a verifier over-drop; it is the pre-fetch cull, whose throttle component (fetch_cap) is a real number-driven throttle but whose exact magnitude is not instrumented."
}
```

(The full saved file `outputs/audits/I-perm-010/funnel_trace_drb76.json` additionally carries `meta.anchor_reconciliation`, `secondary_loss_stage`, `fetch_failure_breakdown_whole_run`, `verifier_drop_breakdown`, and `instrumentation_gaps_for_1204`. Open it if you want the long form; the summarized stages above are the load-bearing claims.)

## Independent verification Claude already ran (verify these, don't trust them)

Every count below was pulled directly from the artifacts:

- `retrieval.pre_filter=2981`, `retrieval.candidates_processed=740`, `retrieval.candidates_total=740`, `retrieval.fetched=500`, `retrieval.failed=240`, `retrieval.fetch_success_rate=0.67567...` — all present in manifest.json, exact.
- discovery_funnel backends: `s2.returned=1402`, `serper.returned=1251`, `openalex_search.returned=700` — present.
- `agentic_search.urls_discovered_total=800` — present (correctly footnoted as agentic sub-lane only, NOT the discovered pool).
- `len(evidence_pool.json)=55` == `finding_dedup.raw_row_count=55`; `finding_dedup.collapsed_row_count=0`.
- `evidence_selection.evidence_total=46`, `evidence_selected=46`, `dropped_count=0`.
- `generator.sentences_verified=40`, `sentences_dropped=41`; verification_details per-section `total_in` = 23+18+14+13+13 = 81; `drop_reason_counts` = entailment_failed 29 / no_provenance_token 5 / no_content_word_overlap 4 / no_integer_overlap 2 (sum 40) + `dedup_redundant_count=1` = 41.
- `four_role_evaluation.final_verdicts` = 37 entries, dist {VERIFIED:23, UNSUPPORTED:14}; `release_allowed=false`; `coverage_fraction=0.4`; `held_reasons=["d8_unsupported_residual_below_coverage","d8_s0_must_cover_missing:contraindications","d8_pending_rewrite"]`; `report_redaction.redacted_count=14`.
- `retrieval.corpus_truncated=false` (only location; trace correctly states this covers the POST-fetch loop, not the pre-fetch cap).
- fetch_content `error_reasons` = {no_content:247, fetched_200_but_empty_extract:26, "S2 landing pages have no content":2, access_bypass_timeout_90s:2}; `total_calls=906` (the 906-call superset, NOT the 740-loop — so `failed=240` cannot be reason-decomposed, which the trace states).
- Code: `live_retriever.py:92` = `DEFAULT_FETCH_CAP = int(os.getenv("PG_LIVE_FETCH_CAP","40"))`; `:2647` = `return candidates[:fetch_cap + n_seed_injected]` (the hard slice); `:2979-2980` appends `prefetch_offtopic: N kept / M rejected` to a local `notes` list. String `prefetch_offtopic`/`offtopic` is NOT present anywhere in manifest.json, and `retrieval` has no `notes` key — confirming the off-topic-vs-cap split is genuinely absent from saved artifacts.
- Arithmetic: every drop-stage reconciles (in - out = dropped); the two non-reconciling lines (generated 46->81, and 4-role 37<-40) are correctly labeled a generation fan-out and a post-strict_verify entry respectively.

## Your job (4 checks)

(a) **Counts trace to real keys.** Spot-check the key manifest paths above against the actual files. Confirm every funnel count maps to a real artifact key (not invented). Flag any count that does NOT resolve, OR any case where the cited key holds a different value than the trace states.

(b) **Dominant-loss-stage pick is correct.** By the task's definition (largest absolute drop), confirm the pre-fetch cull (drop 2241) is the dominant loss and that the trace did not mis-rank it. Confirm the trace correctly corrected the task's "discovered=800" anchor to `pre_filter=2981` (same unit as 740/500) rather than chaining mismatched units (e.g. chaining 800 or corpus.count=849 into the funnel, which would create fake drops).

(c) **Legitimate-vs-throttle honesty (the critical check).** For EACH classified drop reason, confirm the legitimate/throttle/unknown label is honest and evidence-backed. Specifically:
   - Is any **throttle** wrongly labeled **legitimate**? (the dangerous direction — hidden quality suppression)
   - Is the fetch_cap slice correctly called THROTTLE (a hard `candidates[:fetch_cap+seeds]` numeric cut), and is the trace honest that its exact magnitude is ABSENT (count=0 = placeholder, not a measured zero)?
   - Is the off-topic component correctly left UNKNOWN rather than assumed legitimate?
   - Are the verifier drops (entailment/no-token/overlap/integer) and the fetch-failure tail (no_content/empty_extract/S2/timeout) correctly LEGITIMATE?
   - Is the trace honest that the run was held by the D8 coverage gate, NOT by source count?

(d) **Final line.** Emit, as the LAST line, EXACTLY one of:
   `verdict: APPROVE`
   `verdict: REQUEST_CHANGES`

APPROVE iff: every count resolves to a real key with the stated value, the dominant-loss pick is correct, and no throttle is dishonestly labeled legitimate (unknowns honestly marked unknown is acceptable and expected given the instrumentation gap). REQUEST_CHANGES if any count is wrong/invented, the dominant stage is mis-ranked, OR any drop is mis-classified in the dangerous direction.

Also emit the schema before the final line:

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
