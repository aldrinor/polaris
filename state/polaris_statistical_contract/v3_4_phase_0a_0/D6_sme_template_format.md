# D6 — SME Construction Template Format (draft for Codex review)

**Deliverable**: Phase 0a.0 / D6 — the SME construction-template schema + ID scheme.
**Status**: LOCKED (Codex APPROVE 2026-05-27 after 3 rounds; pending operator sign-off).
**Parent**: 0a.-1.A (roles/assignment) + §3.4 criterion 3 (template_id match); depends on D1a, D2, D3, D7', D4, 0a.-1.A, 0a.-1.B.
**Plan**: `PHASE_0a_0_PLAN.md` (D6 SME template format, semantic IDs — Codex plan round-2 P2-2).
**Codex review**: `.codex/I-safety-001b/codex_d6_review.txt`.
**Version**: 1 (draft)

**Why this exists**: a `sme_template_id` is (a) §3.4 criterion 3's match unit (same template + same constructor + within 24h → related), and (b) the construction recipe an SME follows to build a claim+packet scenario. The criterion-3 dependency on a stable template ID originates in 0a.-1.A §1/0a.-1.C §2.1; D6 locks the schema, the semantic-ID scheme, and how the template binds the locked strata (D2/D3), fabrication taxonomy (0a.-1.B), packet methodology (D7'), and roles (0a.-1.A).

---

## §1. Semantic template ID (locked — Codex plan round-2 P2-2)

`sme_template_id` = semantic string + version: `"<domain>_<complexity_tier>_<evidence_pool_bin>_<l2_focus>_v<N>"`, e.g. `clinical_C2_E3_safety_signal_v1`.

- Components: domain (D1a), complexity_tier (D2 {C1,C2,C3}), evidence_pool_bin (D3 {E1..E4}), `l2_focus` (the primary D4 L2 category the template targets, e.g. `safety_signal`), version `vN`.
- A content `hash_pin` accompanies the ID (the template's frozen content SHA256). UUIDs are internal-only; the semantic ID is the human/audit handle.

**Anchored regex (Codex round-1 #1 — resolves underscore ambiguity)**: `domain`, `complexity_tier`, `evidence_pool_bin` are CLOSED vocabularies, so the ID is parsed by anchoring on them (NOT naive `_` split, since `due_diligence` and `safety_signal` contain underscores):

```
^(clinical|due_diligence|policy|tech|ai_sovereignty|canada_us)_(C1|C2|C3)_(E1|E2|E3|E4)_([a-z][a-z0-9_]*)_v([0-9]+)$
```

Group 4 = `l2_focus` (the remaining slug before `_v<N>`); group 5 = version integer. The parser uses this anchored regex; `l2_focus` must resolve to a D4 L2 category id for the template's domain. Two templates with the same semantic ID but different content are a versioning error (bump `vN`).

**Criterion-3 match (0a.-1.C §2.1)**: two claims share a template iff their `sme_template_id` strings are byte-equal (same domain+tier+bin+focus+version). A version bump (`v1`→`v2`) makes them NON-matching — correct, since a re-versioned template is a different recipe.

## §2. Template schema (locked)

```
{
  sme_template_id: str,                 # §1 semantic ID
  version: str,                         # "v<N>" matching the _v<N> ID suffix; the integer N is the version (§2.1 validator enforces equality)
  content_hash: str,                    # SHA256 of the frozen template body
  domain: enum[6],                      # D1a
  complexity_tier: enum[C1,C2,C3],      # D2
  evidence_pool_bin: enum[E1,E2,E3,E4], # D3 (target bin; actual bin is per-packet, D3 §2)
  l2_focus: str,                        # D4 L2 category id (the template's primary topical focus)
  construction_protocol: {
    claim_count_target: int,            # >= 1
    severity_distribution_target: { S0:int, S1:int, S2:int, SUPPORTED:int },  # 0a.-1.B; NO S3 — see §2.2
    fabrication_type_mix_target: { quantitative:int, qualitative_negation:int,
      relation_direction:int, citation_swap:int, entity_swap:int, temporal:int,
      scope_overreach:int },            # 0a.-1.B §2 (7 types) — target counts
    source_packet_protocol_ref: str,    # D7' (curation + source_selection_manifest + downselect)
    fabrication_injection_protocol_ref: str,  # 0a.-1.B §3 (plausible, matched-control)
    blinded_labeling_protocol_ref: str, # 0a.-1.A §5 + 0a.-1.B §4 (first-pass blinded)
    tiebreak_protocol_ref: str          # 0a.-1.A §6 tiebreak workflow
  },
  sme_qualifications_required: [str],   # 0a.-1.A §3 evidence tags for this domain
  estimated_time_per_claim_minutes: int,
  created_by: str,                      # sme_id (constructor-author)
  created_at: utc,
  status: enum[active, deprecated],
  supersedes?: str, replaced_by?: str
}
```

The template is a RECIPE, not a claim. It carries TARGETS (counts, mixes) the constructor fills; the actual constructed claims live in `construction_manifest` (0a.-1.C).

### §2.1 Hard invariants + validator (Codex round-1 #1/#2/#7 — enforcement, not prose)

A **`template_manifest.schema.json`** is authored (`state/data_lineage/schemas/template_manifest.schema.json`, this commit) + a **D6 validator** enforces (fail-closed):
- ID matches the §1 anchored regex; parsed (domain, tier, bin, l2_focus, version) are CONSISTENT with the schema's `domain`/`complexity_tier`/`evidence_pool_bin`/`l2_focus`/`version` fields.
- All target counts are non-negative integers.
- `severity_distribution_target` values SUM to `claim_count_target`.
- `fabrication_type_mix_target` values SUM to the FABRICATED target = `claim_count_target − SUPPORTED` (SUPPORTED are non-fabrications; the 7 fab-type counts partition the fabricated remainder).
- `version` integer equals the `_v<N>` suffix.
- Each `*_protocol_ref` resolves to a locked, hash-pinned artifact ID (D7'/0a.-1.B/0a.-1.A).
- `l2_focus` resolves to an active D4 L2 category for the template's domain.

**Construction-manifest acceptance check (Codex round-1 #7)**: at `construction_manifest` acceptance, every claim's `sme_template_id` MUST resolve to an `active`, hash-pinned template, and the parsed ID components MUST equal the claim's `domain` + `complexity_tier` (D2) + realized `evidence_pool_bin` (see §2.3). A claim referencing an unknown/deprecated template, or whose metadata diverges from the parsed ID, is rejected (fail-closed). The relation-builder's fail-closed (0a.-1.C §2.3) is NOT this check — this is a separate D6 acceptance validator.

### §2.2 S3 is NOT a gold-set stratum (Codex round-1 #3)

The locked `severity_stratum_manifest` + pairwise schema + relation-builder + Gate A accept only {S0, S1, S2, SUPPORTED}. 0a.-1.B's S3 (stylistic/non-decision-relevant) is therefore NOT a gold-set construction stratum: `severity_distribution_target` has NO S3 key. An item an adjudicator would rate S3 is OBSERVABILITY-ONLY (logged, not part of Gate-A stratification); the gold set's fabricated strata are S0/S1/S2 and SUPPORTED is the non-fab class. (If S3-level gold-set stratification is ever wanted, it requires an approved 0a.-1.C/relation-builder/severity_stratum_manifest extension — out of scope here.)

### §2.3 Target bin vs realized bin — fail-closed (Codex round-1 #2)

`evidence_pool_bin` in the template is the TARGET; the realized bin is the packet's actual distinct-admissible-source count (D3 §2). At acceptance, the claim's `construction_manifest.evidence_pool_bin` MUST equal the realized D3 packet bin AND equal the template's target bin. A mismatch (template targets E3, packet realizes E2) is fail-closed: the claim is rejected and reconstructed/reassigned (to a packet that realizes the target, or to a template whose target matches the realized bin) BEFORE acceptance. This keeps the semantic template ID aligned with the actual stratum cell.

## §3. Binding to locked deliverables (no re-definition)

D6 REFERENCES, does not re-define:
- **D2** complexity_tier (the template's tier; the constructor assigns per-claim complexity per D2, must match the template's tier or the claim is mis-templated).
- **D3** evidence_pool_bin target + the downselect rule (D7'/D3 govern the actual packet).
- **0a.-1.B** severity rubric + 7-type fabrication taxonomy + injection protocol (the template's `severity_distribution_target` + `fabrication_type_mix_target` reference 0a.-1.B's locked enums).
- **D7'** packet curation + source_selection_manifest + matched-control parity.
- **0a.-1.A** roles (constructor authors the template; adjudicators are role-disjoint), blinding, tiebreak.
- **D4** l2_focus (a locked L2 category id; resolved against the D4 ontology).

A template whose targets violate a locked enum (e.g. an unknown fabrication_type, a non-{C1,C2,C3} tier) is a construction error (fail-closed).

## §4. Template lifecycle + governance

- Templates are hash-pinned custody artifacts (0a.-1.E §1).
- A template is authored + frozen (content_hash) before use; a change bumps `version` (deprecate-not-mutate, like D4 L3s): the old template `status=deprecated`, `replaced_by` set; in-flight claims keep their original `sme_template_id`.
- A template change after structural exposure (it affects criterion-3 relations + the severity/fab distribution → DEFF + stratum counts) is a §P4 Category-3 amendment (pre-outcome) / Category-4 (post-outcome), per 0a.-1.E §6 windows.
- `created_by` (the constructor who authored the template) does NOT bar other constructors from using it; criterion-3 matching is on the template_id + the CLAIM's constructor (0a.-1.A §1 / 0a.-1.C §2.1 criterion 3 requires same `constructor_sme_id` AND same template AND within 24h).

## §5. Definition of done (D6)

Locked: semantic template_id scheme (anchored regex resolving the underscore ambiguity + content_hash), template schema + `template_manifest.schema.json` (APPLIED) + D6 validator with hard invariants (count sums, version match, ref resolution, ID-component consistency) + construction-manifest acceptance check, S3-not-a-gold-stratum (§2.2), target-vs-realized bin fail-closed (§2.3), binding-by-reference to D2/D3/D4/D7'/0a.-1.A/0a.-1.B, lifecycle/governance (deprecate-not-mutate, §P4 windows), criterion-3 match semantics. Codex §-1.1 APPROVE. Operator sign-off.

**D6-templates HARD GATE (Codex round-1 #8, like D4-seed)**: the per-cell template CONTENT set must be authored, validator-passed (§2.1), and hash-pinned BEFORE any SME construction, construction-manifest acceptance, D8 allocation, relation-builder dry-run, or pilot. D6 locks the FORMAT + validator; the content set is gated.

## §6. Dependencies + forward notes

- Needs D1a, D2, D3, D4, D7', 0a.-1.A, 0a.-1.B — all LOCKED.
- `sme_template_id` consumed by relation-builder criterion 3 (0a.-1.C §2.1) + construction_manifest (0a.-1.C §1.1).
- Template files + content hashes are custody artifacts (0a.-1.E §1).
- The per-cell template CONTENT is a Phase-0a authoring step (gated like D4-seed); D6 locks the format/schema/governance.
