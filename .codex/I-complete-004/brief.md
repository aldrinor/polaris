# I-complete-004 (#1190) — targeted required-entity retrieval lane (faithfulness-safe)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## HARD CONSTRAINTS (operator-locked, NOT consultable)
1. **ENV-GATE** `PG_REQUIRED_ENTITY_RETRIEVAL` (default OFF). Flag-OFF = BYTE-IDENTICAL: no search call, no fetch call, no evidence injected, `_frame_rows` unchanged.
2. **FAITHFULNESS-SAFE.** The lane CANNOT fabricate or force a slot. It only re-fetches an entity's OWN canonical `url_pattern` and replaces the gap FrameRow IF real content is retrieved. The replacement FrameRow carries the ACTUAL resolved URL — NEVER a relabel of foreign content with the entity's canonical URL (the §-1.1 citation-faithfulness lie). All downstream gating is UNCHANGED: the slot fills only if the new evidence passes the SAME strict_verify + the SAME exact-equality `_entity_canonical_match`; otherwise it stays a gap-disclosure.
3. **BOUNDED.** Named-const cap on targeted queries per entity AND total entities processed; env-overridable; no runaway.
4. **NAMED CONSTS** (LAW VI) — `PG_REQUIRED_ENTITY_DOMAINS` default = `fda.gov, dailymed.nlm.nih.gov, ema.europa.eu, nice.org.uk, who.int, drugs.com` (operator-approved clinical-authority set), plus each entity's OWN `url_pattern` host is added to the per-entity domain bias (so `ods.od.nih.gov` / `accessdata.fda.gov` / `health-products.canada.ca` entities are reachable — the default list alone cannot surface them under exact-URL coverage).

## WHAT THE LANE DOES
Inserted in `scripts/run_honest_sweep_r3.py` immediately AFTER `fetch_compiled_frame` (~:4694), inside the existing `PG_V30_PHASE2_ENABLED` block, where both the contract (`_cf`/`_template`) AND the corpus (`retrieval`/`evidence_for_gen`) are in scope.

For each FrameRow in `_frame_rows` that is UNSATISFIED — `provenance_class == FRAME_GAP_UNRECOVERABLE` OR (`== METADATA_ONLY` AND `len(direct_quote.strip()) < _MIN_VERIFIABLE_SPAN_CHARS`), mirroring the gap-routing test in `contract_section_runner.py:370-386`:
1. Build targeted queries from `(intervention anchor, entity term)` — e.g. `"<intervention> contraindications"`, `"<intervention> dosing"`, `"<intervention> safety adverse"` — biased to `PG_REQUIRED_ENTITY_DOMAINS` ∪ {entity's own url_pattern host} via the EXISTING `domains=[...]` → `site:` mechanism (`search_agent._serper_search_sync:513-516`). **CONSUME** the search output to collect candidate authoritative URLs (capped).
2. FETCH the collected candidate URLs through the EXISTING live retriever (`run_live_retrieval(seed_urls=..., seed_only=True, anchor_seed=False)` — same AccessBypass/Zyte chokepoint, NO Serper/S2 fan-out; the deepener/gap precedent at `live_retriever.py:2766-2786`), producing canonical evidence rows with REAL fetched URLs.
3. MERGE the fetched rows into the corpus (`evidence_for_gen` + `retrieval.evidence_rows`) with the SAME canonical-URL dedup + global `evidence_id` renumber the saturation gap-round uses (`run_honest_sweep_r3.py:5105-5139`).

Result: the generator (`generate_multi_section_report` → `strict_verify`) can now write VERIFIED contraindication/dosing claims from the newly-present authoritative content. The FrameRow is NEVER mutated; the must-cover slot stays a gap-disclosure if no verifiable evidence is found.

## HONEST SCOPE (stated finding — verify, don't discover)
The 4-role coverage gate for url-pattern regulatory entities requires `record.url == entity.url_pattern` EXACTLY (`_entity_canonical_match`, operator-locked, NOT touched). Injecting an ALTERNATE authoritative URL therefore CANNOT flip THAT entity's 4-role coverage. The lane's value is getting authoritative SAFETY CONTENT into the corpus so the generator can make VERIFIED claims (directly addressing #1190's "absent from the cited research corpus"). It flips 4-role coverage only for DOI/PMID-keyed entities, or when the entity's exact `url_pattern` is itself among the fetched URLs — NOT for the url-pattern regulatory entity class as a rule. This is a deliberate faithfulness boundary, not a defect.

## FILES
- NEW `src/polaris_graph/retrieval/required_entity_retrieval.py` — pure helpers + DI'd orchestrator (search_fn, retrieval_fn injected; NO network in tests; returns fetched rows, NEVER keyed to entity_id).
- EDIT `scripts/run_honest_sweep_r3.py` — env-gated lane call + corpus merge at the seam.
- NEW `tests/polaris_graph/test_required_entity_retrieval.py` — offline.

## Files I have ALSO checked and they're clean
- `native_gate_b_inputs.py` (`_entity_canonical_match` EXACT-equality, normalize lookup) — UNCHANGED, reused as the binding contract.
- `contract_section_runner.py` (gap routing, `register_frame_rows_into_evidence_pool`) — UNCHANGED, reused.
- `frame_fetcher.py` (`fetch_frame_entity`, `_fetch_url_pattern`, FrameRow, ProvenanceClass) — UNCHANGED, reused.
- `search_agent.py` (`_serper_search_sync` domain `site:` bias) — UNCHANGED, reused.
- `strict_verify` / `multi_section_generator.py` — UNCHANGED, NOT touched.

## TESTS (offline, no network)
(a) targeted query built with authoritative-domain bias (default ∪ entity host) for a missing entity; label_name-anchor priority; host extraction; domain override;
(b) lane finds NO candidate URLs → NO evidence injected AND retrieval NEVER called (no fabrication, no wasted fetch); candidates found → rows fetched seed-only with honest labels and returned for merge;
(c) `PG_REQUIRED_ENTITY_RETRIEVAL` OFF → `lane_enabled()` False; already-satisfied frame rows never searched/fetched;
(d) §-1.1: a fetched corpus row carries its REAL fetched URL, is NOT keyed to any entity_id, is NOT relabeled with the entity's `url_pattern`, and FAILS exact-equality coverage on an alternate URL (provenance honesty — the operator-locked gate cannot be tricked).

## SCHEMA
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
