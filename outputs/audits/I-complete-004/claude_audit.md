# I-complete-004 (#1190) — Claude architect audit

## Change
Adds an ENV-GATED, faithfulness-safe **targeted required-entity retrieval lane**:
a second-chance, additive corpus-enrichment pass on the must-cover S0 safety
entities (contraindications / dosing_limits / black_box_warnings /
regulatory_status) the normal V30 Phase-2 frame fetch returned as GAPS — the
recurring cause of clinical-question reports lacking verified safety content
(#1188 + canary diagnosis).

## Files changed (exclusive)
- NEW `src/polaris_graph/retrieval/required_entity_retrieval.py` — pure helpers +
  DI'd orchestrator. No network in the module; `search_fn` / `retrieval_fn`
  injected. Returns fetched corpus rows; NEVER mutates frame rows; NEVER keys a
  row to an entity_id.
- EDIT `scripts/run_honest_sweep_r3.py` (+78 lines vs pre-issue parent, additive)
  — env-gated lane call + corpus merge at the V30 Phase-2 seam (~:4694), where
  the contract (`_cf`/`_template`) AND the corpus (`retrieval`/`evidence_for_gen`)
  are in scope.
- NEW `tests/polaris_graph/test_required_entity_retrieval.py` (11 tests, offline).

## Mechanism (the corrected design)
1. Identify each must-cover entity STILL unsatisfied after the frame fetch
   (`frame_row_is_unsatisfied`: gap, or METADATA_ONLY with a sub-floor span).
2. Build targeted `<intervention anchor> <s0-category safety term>` queries and
   fire `_serper_search_sync(query, domains=...)` biased to
   `PG_REQUIRED_ENTITY_DOMAINS` ∪ the entity's own `url_pattern` host. **Consume**
   the results -> collect candidate authoritative URLs (capped).
3. FETCH the candidates through `run_live_retrieval(seed_urls=..., seed_only=True,
   anchor_seed=False)` — the same AccessBypass/Zyte chokepoint, no Serper/S2
   fan-out (the deepener/gap precedent) — yielding canonical evidence rows with
   their REAL fetched URLs.
4. MERGE into `retrieval.evidence_rows` (append) + `evidence_for_gen`
   (**PREPEND**, like the V30 contract + upload injections) with the SAME
   canonical-URL dedup + global `evidence_id` renumber the saturation gap-round
   uses. The prepend preserves the I-meta-005 money-gate suffix-diff invariant
   (`_selection_base_rows` snapshot at :4641 must stay the contiguous SUFFIX;
   `_gate_injected_prepend_rows` at :5019 then correctly captures the lane rows
   as part of the injected prepend a gap-round re-applies).

**journal_only guard:** the lane is SKIPPED when `_jo_active` — the must-cover
authorities are drug labels / guidelines (not peer-reviewed journals), so under
journal_only they carry no sidecar metadata and would either leak into the
citeable corpus or trip the pre-generator no-leak assert. The two modes are
mutually exclusive by intent (journal_only prunes drug labels anyway), so the
lane fail-safes off.

The generator then writes verified contraindication/dosing claims from the
newly-present content via the UNCHANGED strict_verify. The FrameRow / V30 slot
stays a gap-disclosure when no verifiable evidence is found.

## Faithfulness argument (§-1.1 — the load-bearing review surface)
- **No fabrication / no forced coverage.** Fetched content only enters the report
  through the unchanged strict_verify (overlap + numeric + NLI). An entity with
  no verifiable authoritative content stays a gap-disclosure.
- **No provenance lie (relabel).** The fetched rows are ORDINARY corpus evidence
  carrying their REAL fetched URLs. They are NEVER keyed to an entity_id and
  NEVER assigned an entity's canonical `url_pattern`. Test (d) proves an
  alternate-URL row keeps its real URL and FAILS exact-equality
  `_entity_canonical_match` — the operator-locked coverage gate cannot be tricked.
- **No gate touched.** `strict_verify`, `native_gate_b_inputs`
  (`_entity_canonical_match`), and `contract_section_runner` gap routing are all
  reused unchanged.

## HONEST SCOPE (what it does and does NOT do)
Because the 4-role coverage gate for url-pattern regulatory entities requires
`record.url == entity.url_pattern` EXACTLY, injecting an ALTERNATE authoritative
URL CANNOT flip that specific entity's 4-role coverage. The lane's value is
getting authoritative SAFETY CONTENT into the corpus so the generator can make
VERIFIED contraindication / dosing claims (directly addressing #1190's "absent
from the cited research corpus"). It flips 4-role coverage only for DOI/PMID-keyed
entities, or when the entity's exact `url_pattern` is itself among the fetched
URLs — NOT for the url-pattern regulatory entity class as a rule. This is a
deliberate faithfulness boundary, not a defect. The offline tests prove the lane
is faithfulness-safe + additive; they do NOT prove `four_role_held` flips (a
live-run property).

## HARD constraints — verification
1. **Env-gate / byte-identical OFF:** `PG_REQUIRED_ENTITY_RETRIEVAL` default OFF.
   When OFF the caller skips the lane entirely (no search, no fetch, corpus
   untouched). Test (c).
2. **Faithfulness-safe:** see above; tests (b) and (d).
3. **Bounded:** named-const caps — `PG_REQUIRED_ENTITY_MAX_QUERIES_PER_ENTITY`
   (3), `PG_REQUIRED_ENTITY_MAX_ENTITIES` (12),
   `PG_REQUIRED_ENTITY_MAX_RESULTS_PER_QUERY` (5),
   `PG_REQUIRED_ENTITY_MAX_SEED_URLS_PER_ENTITY` (3), all env-overridable.
4. **Named consts (LAW VI):** `PG_REQUIRED_ENTITY_DOMAINS` default = fda.gov,
   dailymed.nlm.nih.gov, ema.europa.eu, nice.org.uk, who.int, drugs.com —
   UNIONed per-entity with the entity's OWN `url_pattern` host so url-only
   entities (ods.od.nih.gov, accessdata.fda.gov, health-products.canada.ca) are
   reachable. Test (a).

## Tests (11, offline, deterministic)
(a) targeted query + authoritative-domain bias (default ∪ entity host);
label_name-anchor priority; host extraction; domain override.
(b) no candidates → no injection, retrieval never called, frame row unmutated;
candidates found → rows fetched seed-only with honest labels and returned.
(c) flag-OFF → `lane_enabled()` False; satisfied input rows never searched/fetched.
(d) §-1.1: fetched row keeps real URL, not keyed to entity, fails alternate-URL
exact-equality coverage. Plus the unsatisfied classifier.

## Regression
- New lane: 11/11 pass.
- Reused contracts unbroken: `test_m56_frame_fetcher` (67),
  `test_m63_contract_section_runner` (18),
  `test_fx03_gate_b_cited_span_iready017` (8), `test_native_gate_b_inputs` (37),
  `test_gate_b_seam` (8) — all green (149 total with the lane).
- Pre-existing collection errors in unrelated `scope/`, `intake/`, `sovereignty/`
  test dirs are a bare-`polaris_graph`-import issue independent of this change.
