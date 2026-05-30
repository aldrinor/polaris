# 0a.-1.C (schema/spec half) — Metadata Schema + Relation-Builder Spec (draft for Codex review)

**Deliverable**: Phase 0a.0 / 0a.-1.C, SCHEMA+SPEC half (the CODE + edge-fixture dry-run is the post-0a.-1.E half per plan).
**Status**: LOCKED (schema/spec half — Codex §-1.1 APPROVE 2026-05-27 "Lock 0a.-1.C-schema" after 3 rounds: 7 build-blocking gaps + §4 process fix + 3 consistency fixes, all closed; pending operator sign-off). The CODE + edge-fixture RUN half is post-0a.-1.E.
**Parent**: contract v3.3 §3.4; depends on D1a + 0a.-1.A + 0a.-1.B + 0a.-1.D (all LOCKED).
**Plan**: `PHASE_0a_0_PLAN.md` — "C-schema/spec BEFORE E; C-fixture dry-run AFTER E".
**Codex review**: `.codex/I-safety-001b/codex_0a1C_review.txt` + `codex_0a1C_confirm{,2}.txt`.
**Version**: 1 (LOCKED — schema/spec half)

**Scope clarification (Codex round-1 §4 process fix)**: this half locks the schema SPEC (field definitions, relation algorithm, determinism rules, per-stratum output schema, fixture spec, fail-closed rules). The literal hash-pinned JSON Schema FILES in `state/data_lineage/schemas/`, the relation-builder CODE, and the edge-fixture RUN are ALL the post-0a.-1.E half — custody (0a.-1.E) must govern those artifacts before they count. This half does NOT claim hash-pinned schema files exist yet.

**Why this exists**: contract §3.4 is conceptually specified but operationally unbuildable without (a) the machine-readable manifest schemas the prior deliverables fed into, and (b) the deterministic relation-builder spec that computes `pairwise_relation_manifest` + the `1 + 2Pρ/N` DEFF. This deliverable LOCKS the schemas + the builder spec (algorithm, determinism rules, edge-case behavior). The actual Python implementation + edge-fixture test run is the post-0a.-1.E half (custody must govern the fixtures).

---

## §1. The manifest set (locked machine-readable schemas)

EIGHT JSON-Lines manifests (one row per entity). Their literal JSON Schema FILES + hash-pins are created in the post-0a.-1.E half (per the §4 scope clarification — NOT in this spec half). Field provenance from the locked deliverables noted below.

### §1.1 `construction_manifest` (STRUCTURAL exposure — no labels; from 0a.-1.A §note + 0a.-1.C split)

```
{
  claim_id: str,
  scenario_id: str,
  blinding_unit_id: str,              # 0a.-1.A §1
  source_report_id: str,              # criterion-1 (same report)
  domain: enum[6 validation domains], # D1a
  complexity_tier: enum[C1,C2,C3],    # D2 (forward — placeholder until D2 locks)
  evidence_pool_bin: enum[E1,E2,E3,E4],# D3 (forward)
  microtopic_tags: [microtopic_id],   # D4 (forward), criterion-5
  sme_template_id: str,               # D6 (forward), criterion-3
  constructor_sme_id: str,            # 0a.-1.A
  construction_window_start: utc,     # criterion-3 (24h window)
  generator_prompt_family_id: str,    # D5 (forward), criterion-4
  verifier_prompt_family_id: str,     # D5 (forward), criterion-4
  evidence_packet_id: str,            # 0a.-1.D / criterion-2
  claim_cited_source_ids: [canonical_source_id],  # 0a.-1.D §4 claim-level set
  claim_entity_ids: [entity_id],      # 0a.-1.D §5 (source ∪ claim-subject)
  created_at: utc
}
```

NO severity/fab_status here (anti-leak per 0a.-1.A/0a.-1.B).

### §1.2 `constructor_intent_labels` (SEALED — 0a.-1.B §4)

```
{ claim_id, intended_severity, intended_fab_status, fabrication_type_primary,
  fabrication_type_secondary?, injection_notes }   # sealed; not adjudicator-visible; not IRR
```

### §1.3 `blinded_adjudication_labels` (IRR object — 0a.-1.B §4 / contract §7.3)

```
{ claim_id, facet_id | null,            # label_scope: null facet_id = claim-level
  label_scope: enum[claim, facet],      # Codex round-1: facet-label keying
  adjudicator_id, first_pass_severity, severity_lower_candidate?,
  severity_uncertain: bool, first_pass_fab_status, evidence_cited_span,
  rationale, s0_trigger_record?, time_on_claim_sec }
```

### §1.4 `consensus_gold_labels` (the gold truth — 0a.-1.B §4)

```
{ claim_id, facet_id | null, label_scope: enum[claim, facet],
  final_severity, final_fab_status,
  adjudication_path: enum[agree,tiebreak,panel], resolved_at }
```

### §1.4b `severity_stratum_manifest` (SEALED — derived from consensus gold; Codex round-1 #1)

The relation-builder needs each claim's severity stratum to scope P per stratum, but `construction_manifest` (correctly) has NO labels. v1 adds a SEALED stratum manifest derived from `consensus_gold_labels`:

```
{ claim_id, severity_stratum: enum[S0,S1,S2,SUPPORTED] }   # derived from final_severity/final_fab_status
```

This is ALLOWED structural exposure pre-outcome (severity labels are structural per contract §P4.2; only MISS COUNTS are outcome). Access is custody-controlled (0a.-1.E). The builder consumes `severity_stratum_manifest` (NOT the raw labels) — it sees the stratum, never the miss outcome.

### §1.5 `facet_manifest` (atomic-claim layer — 0a.-1.A/0a.-1.B; neutral, deterministic)

```
{ facet_id, claim_id, facet_text, facet_atomic_assertion }
```

Facets produced NEUTRALLY (deterministic, uniform across all claims, no spotlighting — 0a.-1.A §5 / 0a.-1.B §3).

**Facet→claim rollup (Codex round-1 #2)**: facet-level labels (§1.3/§1.4 with `label_scope=facet`) roll up to the claim's `final_severity`/`final_fab_status` for Gate A by: claim `final_fab_status = fabrication` iff ANY facet is a fabrication; claim `final_severity = max(facet severities)` (most-critical facet governs, consistent with 0a.-1.B fail-upward being resolved at gold-label per §1.3 boundary discipline). A claim with no facet-level heterogeneity carries a single `label_scope=claim` label.

### §1.6 `source_packet_manifest` (0a.-1.D)

```
{ evidence_packet_id, canonical_source_ids: [canonical_source_id],
  packet_class, sha256_of_sorted_canonical_ids }
```

### §1.7 `pairwise_relation_manifest` (COMPUTED — §2 builder output)

```
{ claim_id_i, claim_id_j, related: bool,
  criteria_matched: [enum: same_report, evidence_jaccard_ge_0.5,
                     same_template_sme_24h, same_prompt_family,
                     microtopic_stratum_plus],
  stratum_i, stratum_j }   # base manifest holds ALL pairs incl. cross-stratum;
                           # per-stratum P_S filters to stratum_i==stratum_j==S.
                           # deduplicated: one row per unordered pair {i,j}, i<j
```

## §2. Relation-builder spec (deterministic algorithm)

Input: `construction_manifest` + `source_packet_manifest` + `severity_stratum_manifest` (§1.4b, sealed, custody-controlled). Output: `pairwise_relation_manifest` (all pairs) + per-stratum summary (§2.4).

### §2.1 Pairwise relation rule (contract §3.4, criteria 1-5) — scoping corrected (Codex round-1 #3)

**Two-step (base relations over ALL pairs, then per-stratum filter)**: criteria 1-4 are NOT intrinsically same-stratum (a same-report or same-prompt-family relation can span strata); only criterion 5 requires same-stratum by definition. So:

- **Base relations**: for EVERY unordered claim pair `{i, j}` (i<j, across all strata), `related = OR` over criteria 1-5. The `pairwise_relation_manifest` records ALL base relations (this is the contract's full pairwise lookup table / degree audit — not truncated to within-stratum).
- **Per-stratum P** (§2.2): `P_S = count of related pairs where BOTH claims ∈ stratum S`. DEFF for stratum S uses `P_S` and `N_S`.

`related = OR` over:

1. `same_report`: `source_report_id_i == source_report_id_j`
2. `evidence_jaccard_ge_0.5`: `Jaccard(claim_cited_source_ids_i, claim_cited_source_ids_j) >= 0.5` (0a.-1.D §4: alias-resolved canonical_source_id; empty-set→0)
3. `same_template_sme_24h`: `sme_template_id_i == sme_template_id_j` AND `constructor_sme_id_i == constructor_sme_id_j` AND `|construction_window_start_i − construction_window_start_j| <= 24h`
4. `same_prompt_family`: `generator_prompt_family_id` match OR `verifier_prompt_family_id` match
5. `microtopic_stratum_plus`: shared microtopic tag AND same severity stratum AND ≥1 of {shared sme_template (any time), shared source-packet class, evidence-Jaccard ∈ [0.2, 0.5)}

**Deduplication (contract §3.4 / Codex)**: a pair matching multiple criteria is ONE related pair (boolean OR), recorded once with all matched criteria listed. Unordered: `(i,j) == (j,i)`, canonicalized as i<j.

### §2.2 Pairwise DEFF (0a.-1.D-consistent, contract §3.2)

Per stratum S:
```
N_S = number of claims in stratum S
P_S = number of related unordered pairs where BOTH claims ∈ S (§2.1 per-stratum filter)
DEFF_S = 1 + 2 * P_S * rho / N_S    # rho = ICC ceiling (default 0.10; §4.4 escalation)
n_eff_S = N_S / DEFF_S
```
Edge behavior (0a.-1.D / contract): `P_S=0 → DEFF_S=1`; `P_S=N_S(N_S-1)/2 (saturation) → DEFF_S=1+(N_S-1)rho`.

### §2.3 Determinism requirements (so two runs produce identical output)

- Canonical pair ordering i<j by claim_id lexical sort.
- Alias-resolution (0a.-1.D §2.3) applied BEFORE Jaccard; **claim-level cited-source sets de-duplicated to distinct canonical_source_id BEFORE Jaccard** (Codex round-1 #5).
- 24h comparison on UTC epoch seconds, inclusive boundary (`<= 24h` exactly; 23h59m related, 24h00m00s related, 24h01m not).
- **Criterion-2 Jaccard ≥0.5, float-free**: `2*|∩| >= |∪|` (integer cross-multiply, NOT float division).
- **Criterion-5 Jaccard interval [0.2, 0.5), float-free** (Codex round-1 #5): `5*|∩| >= |∪|` AND `2*|∩| < |∪|`.
- Pairwise relations are PAIRWISE (not transitive / not connected-component) — per contract §3.4: A-B related, B-C related does NOT imply A-C.
- **Fail-closed (Codex round-1 #7)**: the builder RAISES (never silently treats as unrelated) if ANY relation-input field is missing/null/unresolved. The relation-input fields are, per their schemas: from `construction_manifest` — `source_report_id`, `claim_cited_source_ids`, `sme_template_id`, `constructor_sme_id`, `construction_window_start`, `generator_prompt_family_id`, `verifier_prompt_family_id`, `evidence_packet_id`, `microtopic_tags`; from `source_packet_manifest` — `canonical_source_ids`, `packet_class`; from `severity_stratum_manifest` — `severity_stratum`. Unresolved forward-placeholder values (D2-D6 enums / packet_class registry) are INVALID at accepted-builder-run time.

### §2.4 Per-stratum output schema (LOCKED — Codex round-1 #4)

The builder emits a per-stratum summary row (not prose):
```
{ stratum: enum[S0,S1,S2,SUPPORTED], N: int, P: int, rho: float,
  DEFF: float, n_eff: float,
  max_claim_degree: int, p95_claim_degree: int,   # contract §3.4 audit (within-stratum)
  relation_table_sha256: str, input_manifest_sha256s: {construction, source_packet, severity_stratum} }
```
`max_claim_degree` / `p95_claim_degree` are computed WITHIN-stratum (degree = # of related partners in S). The contract §3.4 audit prerequisite (95th-pctile degree > 25 → tighten) reads this.

## §3. Edge fixtures (SPEC — the actual test RUN is post-0a.-1.E)

The post-E half MUST exercise these deterministic fixtures, each with hand-computed expected (per-stratum P, N, DEFF):
- nominal 50-claim integration
- `P=0` (no relations) → DEFF=1
- saturation (all related) → DEFF=1+(N-1)rho
- exact Jaccard 0.5 boundary (`2|∩| == |∪|` → related)
- Jaccard just below 0.5 (`2|∩| == |∪|-1` → not related) and just above
- criterion-5 0.2 boundary (`5|∩| == |∪|` → in-interval) and just below
- duplicate canonical_source_ids in a packet AND in a claim-level cited set (dedup → one member)
- alias-resolved IDs (PMID + DOI of same source → one member)
- empty packets / empty cited set (∅ → Jaccard 0)
- multi-criterion pair (matches ≥2 → counts once, all criteria listed)
- transitive trap (A-B, B-C related, A-C NOT → no merge; P counts 2 not 3)
- same-SME 24h boundary (23h59m related; exact 24h00m00s related; 24h01m not)
- **cross-stratum pair** (criteria 1-4 fire across strata → in base manifest but NOT in any single stratum's P_S)
- **criterion-5 same-stratum gating** (microtopic+correlation match but different strata → NOT related via criterion 5)
- **each criterion firing ALONE** (5 fixtures, one per criterion)
- **prompt-family role matching** (generator-family match alone; verifier-family match alone)
- **missing/null relation field** → builder RAISES (fail-closed)
- unordered-pair determinism ((i,j)==(j,i))

## §4. Definition of done (0a.-1.C schema/spec half)

Locked (SPEC only — no literal files): 8 manifest schemas incl. severity_stratum + facet keying (field provenance + anti-leak split), relation-builder algorithm (base-relations-all-pairs + per-stratum P_S filter, criteria 1-5 + dedup), pairwise DEFF formula + edge behavior, per-stratum output schema, determinism requirements (integer Jaccard ≥0.5 + criterion-5 interval, dedup-before-Jaccard, UTC boundary, pairwise-not-transitive, fail-closed), edge-fixture SPEC. Codex §-1.1 APPROVE. Operator sign-off.

**Deferred to the post-0a.-1.E half** (custody must govern before they count): the literal hash-pinned JSON Schema FILES in `state/data_lineage/schemas/`, the relation-builder Python + validators, and the edge-fixture test RUN that proves per-stratum P/N/DEFF match hand-computed expected.

## §5. Dependencies + forward notes

- Needs D1a + 0a.-1.A + 0a.-1.B + 0a.-1.D (all LOCKED) ✓.
- Forward placeholders (Codex round-1 #7 — fail-closed at builder-run time): complexity_tier (D2), evidence_pool_bin (D3), microtopic_tags (D4), sme_template_id (D6), prompt_family_ids (D5), **packet_class (provenance: 0a.-1.D source_packet_manifest — used by criterion 5)**. Schemas reserve the fields; the post-E dry-run RUN cannot be accepted until these governing enums/registries are locked AND no unresolved value remains (builder RAISES on unresolved).
- Builder code hash + edge-fixture hashes + literal JSON Schema files recorded in 0a.-1.E custody; the dry-run RUN happens after E.
- Feeds Gate A (per-stratum DEFF-adjusted Wilson) + D8 (allocation runs the builder on the planned allocation pre-unblinding).
