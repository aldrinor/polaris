# I-complete-004 (#1190) — Claude architect audit

## Change
Adds an ENV-GATED, faithfulness-safe **targeted required-entity retrieval lane**:
a second-chance retry on the must-cover S0 safety entities (contraindications /
dosing_limits / black_box_warnings / regulatory_status) that the normal V30
Phase-2 frame fetch returned as GAPS — the recurring cause of `four_role_held`
on clinical questions.

## Files changed (exclusive)
- NEW `src/polaris_graph/retrieval/required_entity_retrieval.py` (366 LF lines)
  — pure helpers + DI'd orchestrator. No network in the module; `search_fn` /
  `fetch_fn` injected.
- EDIT `scripts/run_honest_sweep_r3.py` (+52 lines, 0 deletions) — env-gated lane
  call at the V30 Phase-2 seam, immediately after `fetch_compiled_frame`
  (~:4694) and before `compose_outline_from_contract` / the
  `_contract_evidence_rows` build (~:4747).
- NEW `tests/polaris_graph/test_required_entity_retrieval.py` (12 tests, offline).

## Faithfulness argument (§-1.1 — the load-bearing review surface)
Three outcomes; only the faithful ones are reachable:

- **(A) Faithful win:** the lane re-fetches the entity's **OWN** canonical
  `url_pattern` via `fetch_frame_entity`. The returned FrameRow re-binds to the
  SAME `entity_id` and carries the entity's REAL resolved URL. If it now has a
  verifiable span (non-gap), the gap row is replaced. Coverage can flip ONLY
  through the unchanged exact-equality `_entity_canonical_match` +
  `coverage_content_requirements` + strict_verify.
- **(B) Honest fallback:** no verifiable authoritative content → the FrameRow
  stays the gap it already was → slot gap-discloses. No fabrication, no forced
  coverage.
- **(C) Provenance lie — STRUCTURALLY PREVENTED:** the targeted SEARCH results
  are NEVER injected as the entity's coverage evidence. Re-binding happens ONLY
  via the entity's own `url_pattern` re-fetch, so a satisfied row can never
  carry a canonical URL the content did not come from. Test (d) proves a
  foreign-URL re-fetch keeps its real URL and fails exact-equality coverage.

The lane touches NO faithfulness gate: `strict_verify`, `native_gate_b_inputs`
(`_entity_canonical_match`), and `contract_section_runner` gap routing are all
reused unchanged.

## HARD constraints — verification
1. **Env-gate / byte-identical OFF:** `PG_REQUIRED_ENTITY_RETRIEVAL` default OFF.
   When OFF the caller skips the lane entirely (no search, no fetch, `_frame_rows`
   untouched). Only two no-op symbol imports are added unconditionally. Test (c).
2. **Faithfulness-safe:** see above; tests (b) and (d).
3. **Bounded:** named-const caps — `PG_REQUIRED_ENTITY_MAX_QUERIES_PER_ENTITY`
   (3), `PG_REQUIRED_ENTITY_MAX_ENTITIES` (12), `PG_REQUIRED_ENTITY_MAX_RESULTS_PER_QUERY`
   (5), all env-overridable.
4. **Named consts (LAW VI):** `PG_REQUIRED_ENTITY_DOMAINS` default = fda.gov,
   dailymed.nlm.nih.gov, ema.europa.eu, nice.org.uk, who.int, drugs.com —
   UNIONed per-entity with the entity's OWN `url_pattern` host so url-only
   entities (ods.od.nih.gov, accessdata.fda.gov, health-products.canada.ca) are
   reachable under exact-URL coverage. Test (a).

## Tests (12, offline, deterministic)
(a) targeted query + authoritative-domain bias (default ∪ entity host);
label_name-anchor priority; host extraction; domain override.
(b) no evidence → gap stays a gap (no fabrication); satisfied re-fetch replaces
gap + binds on real canonical URL.
(c) flag-OFF → `lane_enabled()` False; satisfied input rows never searched/fetched.
(d) §-1.1: foreign-URL re-fetch keeps real URL, does NOT cover the entity.
Plus the unsatisfied classifier.

## Regression
- New lane: 12/12 pass.
- Reused contracts unbroken: `test_m56_frame_fetcher` (67), `test_m55_frame_compiler`,
  `test_m60_frame_manifest`, `test_m63_contract_section_runner` (18),
  `test_fx03_gate_b_cited_span_iready017` (8), `test_native_gate_b_inputs` (37),
  `test_gate_b_seam` (8) — all green.
- Pre-existing collection errors in unrelated `scope/`, `intake/`, `sovereignty/`
  test dirs are a bare-`polaris_graph`-import issue independent of this change.

## Honest scope note
This lane is faithfulness-safe and gap-disclosing by construction; the OFFLINE
tests prove that. They do NOT prove the live `four_role_held` flips — that
depends on live search/AccessBypass surfacing canonically-matching authoritative
content for each entity's `url_pattern`, which is a live-run property.
