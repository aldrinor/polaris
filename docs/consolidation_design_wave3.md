# Wave 3 — Consolidation design: per-claim baskets (keystone, faithfulness-critical)

**Issue:** I-arch-001 (#1245) · Wave 3 of 5 · Posture: surgical re-wire of existing machinery, default-OFF, OFF = byte-identical.
**Provenance:** designed + stress-tested (`wf_30bf3a8a-5bd`); dual-gated iter 1 (`bmanay00c` + `wxbelib0y`) and iter 2 (`b68ozj1dx` + `whoy63y6n`). Iter-3 fixes below are flagged `[FIX-3]`; iter-2 `[FIX-2]`; original stress fixes `[STRESS-FIX]`.

This step turns "all relevant weighted sources" into **per-claim baskets** — groups of sources that carry the *same* claim — without fabricating corroboration by merging two near-but-distinct claims.

**The lethal asymmetry governs every decision:** under-merge loses only a corroboration count (safe); over-merge invents agreement that does not exist (clinical-lethal). **When in doubt, keep separate.** Breadth comes from never *dropping* a source, never from making baskets bigger.

We **reuse, not rebuild**: `claim_graph.py` spine, `weight_mass.py` independent-origin counter, `both_sides.py`/`ContradictionEdge` refuter side, `independence_collapse.py` copy-collapse. No new framework, no second scorer.

---

## §0. THE CRITICAL FINDING — span-grounding cannot backstop a false-merge (CONFIRMED both reviewers)

- The production verifier `strict_verify` runs **per sentence and is basket-blind**, calling `verify_sentence_provenance` per sentence (`provenance_generator.py:2456`). `[FIX-3, Codex iter-2]` It is **not literally "per-member"**: a single sentence that cites several spans **unions** their decimals/text (`:1722-1756`) and judges entailment against the **combined span** (`:1974`). The clinical twin combines token spans too (`clinical_generator/strict_verify.py:241,289`). It still **never cross-compares two basket members**, so the conclusion is unchanged and *reinforced*: it catches a mis-parse, never a false-**merge** (two distinct claims, each grounding its own span, jointly labelled "2 verified origins").
- **Consequence (the spine):** the **merge key is the SOLE defense against over-merge.** This is why §4 is a **spec-generated, catalog-covered** mechanism, not an enumerated list.
- `[FIX-3]` **The union behaviour creates a verification trap — see §5/§6:** `verified_support_origin_count` must be computed by verifying each member **against its own span in isolation**, never reused from one multi-citation `SentenceVerification` (whose union could pass while a single member fails alone).

---

## §1. Atomic-claim extraction + granularity (the fan-out)

**Reuse `claim_graph.extract_atomic_claims` (claim_graph.py:246-346).**
- **Fan-out: full on the QUALITATIVE path, PARTIAL on the numeric path** `[FIX-2, Codex P2]` — the default numeric extractor emits ≤1 (predicate,value) per row (`contradiction_detector.py:208,502-508`). Widening `extract_numeric_claims` to one atom per (predicate,value) is a scoped Wave-3 sub-task with a fan-out test; until then multi-finding numeric rows are honestly under-fanned, never wrongly merged.
- **Molecular minimality (Gunjal & Durrett 2024):** a clinical effect estimate is ONE atom; never split the effect tuple (≤1 effect-estimate atom per sentence). Not FActScore/SAFE maximal atomization.
- **Extract-only-verifiable (VeriScore):** rhetorical/hedged spans stay un-mergeable raw singletons (`("__raw__", evid, norm_text)`, L340).

---

## §2. Equivalence — deterministic exact spec-key ONLY for Wave 3

**Reuse `claim_graph.cluster_equivalent_claims` (L362-380)** — SHA-1 over the normalized key, O(n) bucketing, no embeddings/NLI/LLM in the merge path. Keep EXACT numeric value (L208); retire `finding_dedup._finding_key`'s `round(value,3)` (L91).

**`PG_SWEEP_CLAIM_EQUIV` (bidirectional-NLI equivalence merge) is DEFERRED OUT of Wave 3** `[FIX-2; confirmed grep-clean at iter 2]`. Exact spec-keys + the §4 mechanism are sufficient for the keystone. Any future NLI merge MUST be default-OFF, default-deny (merge IFF BOTH directions `entail` ≥ threshold), with an explicit `BudgetExceededError` catch that skips (never aborts), running only after the §3/§4 structural blocker. Not in Wave 3.

---

## §3. Conservative merge rule + PICO-TS blocking (before equivalence)

**Rule: "keep separate unless provably the same."** Two atoms merge ONLY if **every required-known discriminating slot for that (kind, domain) is positively known AND equal** — enforced generically by §4. Any unknown/defaulted required slot, or any mismatch, = two honest singletons (drops nothing).

---

## §4. The spec-generated, catalog-covered merge key (THE keystone — generic BY CONSTRUCTION)

`[FIX-3]` Iter 2 declared a generic mechanism but still described a *positional tuple checked against a separate constant* — which the audit showed is the enumeration-fragility renamed (a 9th positional field could be added without the set; `direction`, `comparator`, a missing non-clinical set, and `route/formulation` all slipped that way). The fix makes the key **generated from one ordered spec, and the spec required to cover a declared dimension catalog** — so omission is impossible by construction, not by a one-way test.

### §4.1 Single source of truth — the dimension catalog
`DISCRIMINATING_DIMENSIONS[domain]` is the authoritative set of dimensions where *a difference changes what the claim asserts* (so a merge across it fabricates a different claim):
- **numeric_clinical:** subject(intervention), outcome(predicate), value, unit, **dose (+ per-weight, e.g. mg vs mg/kg)**, **dose_frequency (per-time schedule: QD / BID / weekly — orthogonal to the per-mass dose axis; "15 mg weekly" ≠ "15 mg daily", the ISMP methotrexate sentinel error)** `[FIX-4]`, arm, comparator, **effect_measure (relative / absolute / HR / OR / raw)**, **direction/sign**, endpoint/timepoint, population, **route+formulation (IV vs PO, …)**.
- **numeric_nonclinical:** subject, predicate, value, unit, timeframe.
- **qualitative_clinical:** subject, concept_type, **causal_strength (causal vs associational)**, **warning_severity (boxed/regulatory vs routine-caution)**, object_slot, condition_scope(population), assertion_status.
- **qualitative_nonclinical:** subject, concept_type, object_slot, condition_scope, assertion_status. `[FIX-3, the 4th set, HOLE C2]`

### §4.2 The spec generates the key
`MERGE_KEY_SPEC[(kind, domain)]` is an **ordered list of `Slot(name, value_getter, role, unknown_predicate)`** where `role ∈ {TAG (constant), EXACT (compared exactly, e.g. value), DISCRIMINATOR (must be positively known)}`. The builder is **fail-closed on dispatch** `[FIX-4, Claude iter-3 P1 — the dispatch was not total]`:
```
def build_merge_key(claim):
    # (1) DISPATCH IS FAIL-CLOSED. Any claim whose (kind, domain) has no spec — incl.
    #     kind=="raw", a missing/None/un-normalized domain, or any unforeseen pair —
    #     forces a singleton. NEVER fall back to a coarse/default spec (that would be
    #     silent OVER-MERGE, the clinical-lethal direction).
    domain = normalize_domain(claim.domain)        # free-form hint -> {clinical, nonclinical}, else UNKNOWN
    spec = MERGE_KEY_SPEC.get((claim.kind, domain))
    if spec is None:                               # raw / unknown-domain / any uncatalogued pair
        return ("__unresolved__", claim.kind, str(claim.domain), claim.evidence_id, claim.atom_uid)
    # (2) PER-SLOT positive-known: any DISCRIMINATOR not positively known -> singleton.
    parts = []
    for slot in spec:
        v = slot.value_getter(claim)
        if slot.role == DISCRIMINATOR and slot.unknown_predicate(v):
            # globally-unique singleton id (Codex iter-3 P2): kind+domain+evidence_id+atom_uid
            return ("__unresolved__", claim.kind, domain, claim.evidence_id, claim.atom_uid)
        parts.append(canonicalize(slot, v))
    return tuple(parts)
```
**field-in-key ≡ field-in-spec, by construction** (the tuple is *emitted from* the spec, not hand-written and separately checked). `[FIX-3, HOLE C1 + Codex P2]` **`[FIX-4]`** `AtomicClaim` gains a normalized `domain` field (`claim_graph.py:140-148` has none today; §7 adds it), and `kind=="raw"` atoms — already raw singletons via `("__raw__", …)` — are explicitly excluded from spec dispatch (the `spec is None` branch). **`[FIX-5]`** `AtomicClaim` ALSO gains a **per-atom-unique `atom_uid`** (today per-atom uniqueness is a threaded `claim_index` *argument* the single-arg `build_merge_key(claim)` cannot read; `claim_graph.py:192,203,217,231`). Without it, two distinct *unresolved* atoms from the same `evidence_id` (which the §1 numeric fan-out produces) would collide on the singleton key and silently over-merge — so the singleton's uniqueness, the whole point of the fail-closed dispatch, requires this field. §7 provisions it (set at extraction from the existing `claim_index`). **Construction guarantee (precise, not overclaimed):** every *catalogued* dimension is forced into the key, every not-positively-known discriminator forces a singleton, and every *uncatalogued (kind, domain)* forces a singleton. Catalog *completeness* for novel within-domain dimensions remains human-seeded + §-1.1-audited (§9.1) — the construction guarantees fail-closed behaviour, not omniscience.

### §4.3 "Positively known" is a per-slot predicate from POSITIVE evidence — defaults are NOT known
`[FIX-3, HOLE B + the arm lesson, applied uniformly]` Every DISCRIMINATOR slot supplies an `unknown_predicate` that returns true unless the value came from **positive extracted evidence**. A defaulted or *derived* value is **not** known:
- **arm** → `None` when no placebo/comparator cue fired (not the `"treatment"` default).
- **direction** → unknown unless an **explicit increase/decrease token** was extracted; **never** the predicate-expected-direction fallback (that fallback made "rose 5%" and "fell 5%" merge and broke the design's own test #5).
- **dose** → unknown on `''`; **mg/kg preserved** (`_DOSE_CAPTURE_RE` keeps the per-weight denominator).
- **dose_frequency** `[FIX-4]` → new `ExtractedNumericClaim.dose_frequency`; unknown unless a cadence token (QD/BID/TID/once-daily/weekly/…) was positively extracted ⇒ singleton. Mirrors dose. ("15 mg weekly" must NOT merge with "15 mg daily".)
- **effect_measure, comparator, population, endpoint/timepoint, route+formulation** → each has an explicit extractor field + an unknown predicate; unknown ⇒ singleton. `comparator` and `route+formulation` are **new `ExtractedNumericClaim` fields** (HOLE A: a required slot with no extractor/recipe was undefined behaviour).
- **condition_scope, object_slot (qualitative)** → unknown on `''` ⇒ singleton.

### §4.4 Intra-slot ontological splits (the iter-2 P0 — causation ≠ association)
`[FIX-3, Claude iter-2 P0a]` Some discriminators live *inside* a slot's value-space that the lexicon collapses, so two genuinely different claims get an identical key even when every slot is positively known. These need an **ontology split**, exposed as their own catalog dimensions + key slots:
- **causal_strength:** `config/clinical_safety/qualitative_conflict_lexicon.yaml:40-45` lumps causal cues ("causes","leads to","induces") **and** associational cues ("is associated with","associated with") into one `ae_causation`. Split into `{causal, associational}`; add `causal_strength` to the qualitative key. "drug X **causes** pancreatitis" must NOT merge with "drug X **is associated with** pancreatitis" (the textbook correlation-as-causation error).
- **warning_severity:** lexicon `:36-39` lumps "boxed/black-box warning" with "caution in"/"increased risk of"/"should be monitored". Split into `{boxed_regulatory, routine_caution}`; add `warning_severity`. A boxed warning must NOT be corroborated by a routine caution (severity laundering).

### §4.5 Preserved guards
EXACT numeric value (no rounding); opposite `assertion_status`/direction ⇒ `ContradictionEdge`, never a basket; unknown-subject/raw-text ⇒ singleton; merge arbiter is the spec-key only (no cosine, no NLI in Wave 3).

---

## §5. Basket data model

Reuse `both_sides.SidePosition` as the basket carrier; extend additively. Keyed by `claim_cluster_id`; joined to `weight_mass` and refuter `ContradictionEdge`.

```
ClaimBasket: claim_cluster_id, claim_text, subject, predicate
  supporting_members: list[BasketMember]   # ALL sources — never dropped
  refuter_cluster_ids: tuple               # REFERENCE, not duplicated
  weight_mass: float                       # authority-only, copy-uninflatable
  total_clustered_origin_count: int        # ADVISORY ONLY — never rendered as support strength
  verified_support_origin_count: int       # origins each INDEPENDENTLY passing strict_verify on its OWN span  ◄ the only strengthening count
  basket_verdict: full | partial | contested | unverified
BasketMember: evidence_id, source_url, source_tier, origin_cluster_id, credibility_weight, authority_score,
  span:(start,end)+direct_quote, span_verdict: SUPPORTS|UNSUPPORTED|CONTEXT
```

**`[FIX-3]` `verified_support_origin_count` is computed by ISOLATED per-member verification.** Each member's claim is verified against **its own single span in isolation** (one member, one span — not a multi-citation union). A union that passes while a single member fails alone must count that member as **unverified**. This defeats Codex's "union-laundering" trap.

**`[FIX-2 + FIX-3 + FIX-4]` The unverified count is OVERRIDDEN at the render surfaces — by OVERWRITE (Reading A), not a parallel new field.** Two carriers ship `independent_origin_count` = unverified total: (a) `weight_mass.aggregate_weight_mass` (`weight_mass.py:178`) → `both_sides.SidePosition` (`:54,127-128`) → `render_both_sides` (`:168`); and (b) `disclosure_population.populate_disclosure` per-sentence (`disclosure_population.py:104→112`), which both operator-visible JSON emitters read (`generator/quantified_analysis.py:539`, `run_honest_sweep_r3.py:353`). `[FIX-4]` **The override mechanism is Reading A: OVERWRITE the existing `independent_origin_count` field with the isolated-verified count** — so a single overwrite at the populate site propagates to *both* JSON emitters (they read the same field); do NOT introduce a parallel `verified_support_origin_count` field at the render layer (that would leave the old unverified field still emitted = the conflation). `[FIX-4]` **Multi-cluster sentence rule:** a sentence whose cited tokens span >1 claim_cluster is verified per-cluster; the surfaced count for each rendered claim is that claim's own basket `verified_support_origin_count` (never the sentence-wide origin count). Bound by §8 tests #10 (both_sides), #18 (the `claim_disclosure.json` emit layer, not `populate`'s bare return).

Refuters referenced, not copied (`both_sides.compose_both_sides`).

---

## §6. Basket verification + render

**AND over independent grounding; may only downgrade / drop / label, NEVER upgrade.**
1. Every supporting member still independently span-grounded by strict_verify against its own cited span — unchanged hard gate.
2. **FORBIDDEN (named):** "supported if *any one* member loosely supports it." AND, never OR-that-lowers-the-bar.
3. **`basket_verdict` is a LABEL, not a verification authority** `[FIX-2]` — it can never resurrect a strict_verify-dropped sentence (§8 test #11).

**Render:** add a **sentence → claim_cluster_id binding** (`provenance_generator.py:2548` bibliography + `credibility_pass.py:222`/`disclosure_population.py:101` carry only cited tokens today); surface **"claim → supporting sources + weights + N *verified* independent origins; contested by D."** Contested → `both_sides` neutral block (user judges).

---

## §7. Files reused vs changed

**Reused unchanged:** `claim_graph.py` (extract/cluster spine), `weight_mass.py`, `independence_collapse.py`, `both_sides.py` (`compose_both_sides`), `authority/credibility_skill.py` (reuse, don't fork), `authority/corroboration.py`.

**Changed (surgical):**
- `retrieval/contradiction_detector.py` — add `effect_measure`, `direction`, `population`, `comparator`, `route_formulation`, **`dose_frequency`** `[FIX-4]` fields to `ExtractedNumericClaim`, each with a positive-known signal; `arm=None` when no cue; `dose` keeps `/kg`; `_extract_endpoint_phrase` day+year; (scoped) one numeric atom per (predicate,value).
- `config/clinical_safety/qualitative_conflict_lexicon.yaml` + `retrieval/qualitative_conflict_detector.py` — **split** `ae_causation` → causal/associational (`causal_strength`) and `warning` → boxed/routine (`warning_severity`); emit `condition_scope`/`object_slot` known/unknown signals.
- `synthesis/claim_graph.py` — replace the positional key with **`MERGE_KEY_SPEC` + `DISCRIMINATING_DIMENSIONS` + the spec-driven, FAIL-CLOSED `build_merge_key`**; 4 domain specs; `causal_strength`/`warning_severity`/`route_formulation`/`dose_frequency` slots. `[FIX-4]` add a normalized `domain` field to `AtomicClaim` (none today, `:140-148`) + `normalize_domain()` mapping the free-form domain hint to `{clinical, nonclinical}` (else UNKNOWN); the dispatch returns a forced singleton for any `(kind, domain)` with no spec (incl. `kind=="raw"`). `[FIX-5]` add a **per-atom-unique `atom_uid`** field to `AtomicClaim`, set at extraction from the threaded `claim_index` (`:192,203,217,231`), used in the fail-closed singleton key so two unresolved atoms of one `evidence_id` cannot collide.
- **`[FIX-5, Codex iter-4 P1] Thread the real query `domain` into the claim graph** — today `generate_multi_section_report` receives `domain` (`multi_section_generator.py:5224`, from `run_honest_sweep_r3.py:6146`) but calls `run_credibility_analysis(..., domain=None)` (`multi_section_generator.py:5471-5473`). With fail-closed dispatch, `domain=None` ⇒ every claim singletons ⇒ consolidation goes INERT (Principle 2 silently disabled — a safe under-merge, but it defeats the wave). Pass the normalized query domain through `run_credibility_analysis` → `build_claim_graph` → each `AtomicClaim.domain`. Verified by §8 test #22 (activated main-path).
- `synthesis/finding_dedup.py` — retire as source-dropper (stop collapse-to-representative + non-rep `continue`-drop, L196-210; retire `round(value,3)` L91); preserve safe behaviours.
- `synthesis/credibility_pass.py` — assemble `ClaimBasket`; compute `verified_support_origin_count` by ISOLATED per-member verification; add sentence→claim_cluster_id binding.
- `synthesis/both_sides.py` + `synthesis/disclosure_population.py` — **override BOTH** rendered origin counts to `verified_support_origin_count`.
- `generator/provenance_generator.py` (~L2548) — bibliography/resolver row carries basket weights + multi-attribution.
- `scripts/run_honest_sweep_r3.py` (~L1132) — thread the basket through; enable `PG_SWEEP_CREDIBILITY_REDESIGN` on the main path.
- **NOT changed:** `PG_SWEEP_CLAIM_EQUIV` (deferred); `PG_MAX_EV_PER_SECTION`/source caps (Wave 4).

Default-OFF flag; OFF = byte-identical; faithfulness fixture on drb_72 byte-identical before/after.

---

## §8. Mechanical proof tests

1. **`[FIX-3]` BIDIRECTIONAL generic guard:** (a) every `DISCRIMINATING_DIMENSIONS[domain]` entry appears as a DISCRIMINATOR slot in `MERGE_KEY_SPEC[(kind,domain)]`; (b) every key-tuple field is emitted from a spec slot (TAG/EXACT/DISCRIMINATOR) — no field exists outside the spec. Run **per (kind × domain)**. This makes omission impossible in both directions.
2. distinct-population qualitative, `condition_scope` unknown both → no merge (drb_76).
3. `object_slot`-unknown, different drugs → no merge.
4. "30% at 28 days" vs "at 1 year" → no merge.
5. "stroke rate rose 5%" vs "fell 5%" → no merge **(direction token-only — must pass on the FIX-3 construction)**.
6. distinct doses (2.4 mg vs 7.2 mg), dose unknown both → no merge.
7. "5 mg/kg" vs "5 mg" → no merge.
8. arm placebo-cue missed (both default) → no merge (arm `None`).
9. "30% relative risk reduction" vs "30% absolute risk reduction" → no merge (effect_measure).
10. mixed basket (one verifying, one failing) → **both_sides** rendered count == `verified_support_origin_count`.
11. `basket_verdict=full` cannot resurrect a strict_verify-dropped sentence.
12. true-negative: all slots known+equal → DO merge (verified_support_origin_count=2).
13. OFF = byte-identical on drb_72.
14. **`[FIX-3]` union-laundering:** a sentence/basket whose span-union passes but one member fails **alone** → `verified_support_origin_count == 1`, not 2. `[FIX-4]` Run **end-to-end against the `credibility_pass.py` basket-assembly path** (assemble a real `ClaimBasket`), not as a helper unit test.
15. **`[FIX-3]` "drug X causes Y" vs "drug X is associated with Y"** (same population/object/status) → no merge (causal_strength).
16. **`[FIX-3]` boxed warning vs routine caution** (same hazard/population) → no merge (warning_severity).
17. **`[FIX-3]` "1000 mg IV" vs "1000 mg PO"** (all else equal) → no merge (route_formulation).
18. **`[FIX-3]` disclosure_population render:** per-sentence mixed case → rendered count == `verified_support_origin_count`, not `independent_origin_count`. `[FIX-4]` Assert against the **operator-visible `claim_disclosure.json` emit** (`generator/quantified_analysis.py:539` / `run_honest_sweep_r3.py:353`), not `populate_disclosure`'s bare return.
19. **`[FIX-4]` dose_frequency:** "methotrexate 15 mg weekly" vs "15 mg daily" (all else equal) → no merge.
20. **`[FIX-4]` fail-closed dispatch:** a claim with `kind=="raw"`, or `(kind, domain)` not in `MERGE_KEY_SPEC`, or `domain` unset/unnormalizable → forced singleton (never a coarse default spec). Two such claims with identical fields → distinct cluster ids.
21. **`[FIX-4]` spec↔extractor binding:** every `DISCRIMINATOR` slot's `value_getter` targets a field that exists on the extractor dataclass (closes the catalog↔spec↔extractor 3-list drift; a spec slot pointing at a missing field would silently under-merge).
22. **`[FIX-5]` activated main-path consolidation:** with the real query `domain` threaded (not `None`), two all-known equal clinical atoms **merge** (basket of 2) while a missing/unknown-domain atom stays a **singleton** — proves consolidation is live on the production path (not inert) AND fail-closed at once.
23. **`[FIX-5]` unresolved-atom uniqueness:** two distinct *unresolved* atoms from the **same `evidence_id`** (different `atom_uid`) → distinct singleton cluster ids (no same-source collision under numeric fan-out).

---

## §9. Open risks (honest)

1. **The dimension catalog is the single source of truth and is EXTENSIBLE — but the MECHANISM is fail-closed.** `[FIX-3/FIX-4]` Two different guarantees, stated honestly:
   - **By construction (guaranteed):** every *catalogued* dimension is forced into the key; any not-positively-known discriminator forces a singleton; any *uncatalogued `(kind, domain)`* (incl. `raw`) forces a singleton (fail-closed dispatch, §4.2). The dispatch can never silently fall back to a coarse default spec.
   - **Human-seeded (not construction):** the *completeness* of the within-domain catalog. We seed `DISCRIMINATING_DIMENSIONS` with the known common clinical-lethal discriminators (PICO-TS + dose + **dose_frequency** + route/formulation + effect_measure + causal_strength + warning_severity). A *not-yet-catalogued* within-domain dimension (e.g. a rarer pharmacologic axis) could still let two distinct claims share a key — this is the one residual, bounded by (a) seeding every *common* lethal discriminator now, and (b) the §-1.1 line-by-line audit on real output as the human backstop. We never widen by loosening; we widen only by **adding a catalog dimension** (which test #1(a) then forces into the key).
2. **Corroboration counts go DOWN, not up** — the old numbers were inflated by over-merge. Breadth = no-drop multi-attribution, not bigger baskets.
3. **Extractor RECALL is the corroboration bottleneck** — required-known under-counts where slots don't extract; recover via a better extractor, NEVER a looser rule.
4. **Non-empty COLLISION** (an uncaptured qualifier giving two populations the same `condition_scope`; subject-synonym) remains a precision risk with no span backstop — capped to a count inflation, monitored via the loss ledger + §-1.1 audit; fixed only by better extraction.
5. **Numeric fan-out is 1 claim/row today** (scoped widening) — under-consolidation, never a false-merge.
6. **`_edge_cluster_pair` empty-subject fallback** (`claim_graph.py:410-429`) bounds refuter/contested-labeling accuracy, not the merge.
7. **`[FIX-5 P2, defense-in-depth — provision at implementation]` Raw-path singleton key.** The fail-closed `spec is None` branch keys on `(…, evidence_id, atom_uid)`, dropping the `norm_text` disambiguation the legacy raw key carried (`("__raw__", evid, _norm_text_key(text))`, `claim_graph.py:340`). The raw construction site (`:335`) has no threaded `claim_index`, so it can't source `atom_uid` the same way the numeric (`:289`) / qualitative (`:314`) sites can. Bounded: extraction yields exactly ONE raw atom per row and `evidence_pool` is keyed by unique `evidence_id`, so two raw atoms cannot collide on a non-empty `evidence_id` under normal invariants — collision needs duplicate/empty `evidence_id`s. At implementation, either provision `atom_uid` at the raw site too, or retain `norm_text` in the unresolved key for `kind=="raw"`.

---

## §10. Status

Iter 1: dual REQUEST_CHANGES → generic mechanism + per-slot sentinels. Iter 2: Codex 0 P0 (P1 union-laundering + P2 bidirectional test); Claude found NEW P0 (causation≠association ontology collapse) + the mechanism-completeness holes (positional tuple not spec-generated, missing 4th set, defaulted-known direction, comparator/route undefined, 2nd render surface). **Iter-3 integrates all:** the key is now **spec-generated and catalog-covered** (omission-proof by construction), every discriminator has a positive-known predicate, the causation/association + boxed/routine ontology splits + route/formulation are first-class dimensions, verified counts use **isolated** per-member verification, **both** render surfaces are overridden, and §8 has the bidirectional guard + union-laundering + the new no-merge tests. Iter 3: **Codex APPROVE** (0 P0/P1, accept_remaining); Claude caught a P0 Codex missed — **dosing-frequency over-merge** (methotrexate weekly-vs-daily, the ISMP sentinel error) — plus a P1 (the spec dispatch was not fail-closed). **Iter-4 integrates:** `dose_frequency` is now a seeded catalog dimension + key slot; `build_merge_key` dispatch is **fail-closed** (missing-spec / `raw` / unnormalizable-domain ⇒ forced singleton, never a coarse default); `AtomicClaim` gains a normalized `domain`; the render override is pinned to OVERWRITE (Reading A) with the multi-cluster rule; §8 adds dose_frequency / fail-closed-dispatch / spec↔extractor-binding tests and the end-to-end test layers; §9.1 states the construction-vs-completeness guarantees honestly. Iter 4: **both reviewers 0 P0, faithfulness SAFE, catalog complete** (Claude convergence lens CLEAN over 9 candidate dimensions; Codex "no other common discriminator missing"). Two complementary wiring P1s remained: Claude — the fail-closed singleton key used an unprovisioned `atom_uid`; Codex — the main path passes `domain=None` so fail-closed dispatch would make consolidation inert. **Iter-5 integrates:** `AtomicClaim` gains a per-atom-unique `atom_uid` (§4.2/§7, test #23); the real query `domain` is threaded through `run_credibility_analysis`→`build_claim_graph`→`AtomicClaim` (§7, activated main-path test #22); path typo fixed. **Iter 5 (FINAL): DUAL APPROVE — Codex (0 P0/P1/P2, accept_remaining) + Claude (0 P0/P1; one P2 defense-in-depth raw-path note, §9.7, for the implementation wave).** Both independently ground-truthed the two wiring fixes against the real code as genuinely closed (not phantom), confirmed strict_verify is basket-blind so the merge key is the sole over-merge defense, and confirmed all three operator principles preserved. **DESIGN LOCKED.** No code until the operator says go.
