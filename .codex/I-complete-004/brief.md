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
Inserted in `scripts/run_honest_sweep_r3.py` immediately AFTER `fetch_compiled_frame` (~:4692) and BEFORE the `_contract_evidence_rows`/`register_frame_rows_into_evidence_pool` build (~:4747), inside the existing `PG_V30_PHASE2_ENABLED` block.

For each FrameRow in `_frame_rows` that is UNSATISFIED — `provenance_class == FRAME_GAP_UNRECOVERABLE` OR (`== METADATA_ONLY` AND `len(direct_quote.strip()) < _MIN_VERIFIABLE_SPAN_CHARS`), mirroring the gap-routing test in `contract_section_runner.py:370-386`:
1. Build targeted queries from `(intervention anchor, entity term)` — e.g. `"<intervention> contraindications"`, `"<intervention> dosing"`, `"<intervention> safety adverse"` — biased to `PG_REQUIRED_ENTITY_DOMAINS` ∪ {entity's own url_pattern host} via the EXISTING `domains=[...]` → `site:` mechanism (`search_agent._serper_search_sync:513-516`). (Built for telemetry/corpus discovery; capped.)
2. RE-FETCH the entity's OWN canonical `url_pattern` through `fetch_frame_entity` (reuses AccessBypass/Zyte — `frame_fetcher.py:973`), which re-binds to the SAME `entity_id` with the ACTUAL resolved URL. If the re-fetch now yields a non-gap FrameRow with a verifiable span, REPLACE the gap row in `_frame_rows`. Otherwise leave the gap row untouched.

Result flows through the EXISTING `_contract_evidence_rows` build + `register_frame_rows_into_evidence_pool` + `generate_multi_section_report` → `strict_verify` → 4-role `_entity_canonical_match`. No new verify path.

## FILES
- NEW `src/polaris_graph/retrieval/required_entity_retrieval.py` — pure helpers + DI'd orchestrator (search_fn, fetch_fn injected; NO network in tests).
- EDIT `scripts/run_honest_sweep_r3.py` — env-gated call to the lane at the seam.
- NEW `tests/polaris_graph/test_required_entity_retrieval.py` — offline.

## Files I have ALSO checked and they're clean
- `native_gate_b_inputs.py` (`_entity_canonical_match` EXACT-equality, normalize lookup) — UNCHANGED, reused as the binding contract.
- `contract_section_runner.py` (gap routing, `register_frame_rows_into_evidence_pool`) — UNCHANGED, reused.
- `frame_fetcher.py` (`fetch_frame_entity`, `_fetch_url_pattern`, FrameRow, ProvenanceClass) — UNCHANGED, reused.
- `search_agent.py` (`_serper_search_sync` domain `site:` bias) — UNCHANGED, reused.
- `strict_verify` / `multi_section_generator.py` — UNCHANGED, NOT touched.

## TESTS (offline, no network)
(a) targeted query built with authoritative-domain bias (default ∪ entity host) for a missing entity;
(b) lane finds NO verifiable evidence (fetch_fn returns gap) → FrameRow stays the gap (no fabrication, no relabel);
(c) `PG_REQUIRED_ENTITY_RETRIEVAL` OFF → lane is a no-op AND no search_fn/fetch_fn is called (byte-identical);
(d) §-1.1: a re-fetch that yields content whose resolved URL ≠ the entity's `url_pattern` is NOT relabeled to the entity's canonical URL (provenance honesty) — the satisfied row carries its REAL url.

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
