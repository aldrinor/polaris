# 0a.-1.A — SME Panel + Role Governance (draft for Codex review)

**Deliverable**: Phase 0a.0 / 0a.-1.A — SME panel composition + role governance.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock 0a.-1.A" after 3 review rounds: 8 fixes + 3 consistency-propagation fixes + 2 residual cleanups, all closed; pending operator sign-off).
**Parent**: contract v3.3; depends on D1a (6 validation domains LOCKED).
**Plan**: `PHASE_0a_0_PLAN.md`. Implements carry-forward redline #3 (mechanical role separation).
**Codex review**: `.codex/I-safety-001b/codex_0a1A_review.txt` + `codex_0a1A_confirm{,2,3}.txt`.
**Version**: 1 (LOCKED)

**Scope split**: this deliverable locks the GOVERNANCE FRAMEWORK (roles, credential floors, COI rules, blinding, tiebreak, adjudication schema, mechanical role-disjointness enforcement). The actual SME identities/recruitment are operator-side procurement, captured in a roster manifest that this framework governs — NOT enumerated here.

---

## §1. SME roles (locked role taxonomy)

| Role | Responsibility | Constraints |
|---|---|---|
| **Constructor** | Builds a claim+evidence-packet scenario; injects fabrications per the 0a.-1.B fabrication taxonomy; records sealed constructor-intent labels | A constructor's claims are NEVER adjudicated by the same person |
| **Adjudicator** | Blinded first-pass labeling of severity + fabrication status against cited evidence; produces the IRR object (contract §7.3) | Must NOT have constructed the claim; must NOT see constructor-intent or consensus labels at first-pass |
| **Tiebreaker** | Resolves 2-adjudicator disagreement | Must NOT be constructor OR a first-pass adjudicator of that claim |
| **Panel (§-1.1)** | Final escalation for persistent disagreement | Operator + Codex line-by-line against cited evidence + ≥1 domain-qualified SME (clinical: MD/PharmD where applicable per §3) |

**Role-disjointness invariant (per `blinding_unit`, NOT just per claim — Codex round-1 fix #4)**: role-disjointness applies across a `blinding_unit_id`, not a single claim. A `blinding_unit` groups claims that share construction intent, fabrication pattern, evidence packet, or batch notes — i.e., a scenario-family for blinding purposes (it MAY equal a single claim; the manifest states which). Across a blinding unit:
`constructor_sme_id ∉ adjudicator_ids` AND `constructor_sme_id ≠ tiebreaker_id` AND `tiebreaker_id ∉ first_pass_adjudicator_ids`.

Rationale (Codex round-1 #4): if a constructor built sibling claim A in a unit, they must not adjudicate/tiebreak sibling claim B in the same unit — they already know the unit's fabrication pattern. The `blinding_unit_id` is the disjointness scope. If a unit is truly one claim, the manifest declares `blinding_unit_id == claim_id`.

## §2. Mechanical enforcement (NOT policy prose — Codex round-3 redline #3)

### §2.1 `assignment_manifest` (hash-pinned, append-only)

```json
{
  "claim_id": "<id>",
  "blinding_unit_id": "<id | == claim_id>",
  "constructor_sme_id": "<sme_id>",
  "adjudicator_ids": ["<sme_id>", "<sme_id>"],
  "tiebreaker_id": "<sme_id | null>",
  "assigned_at": "<utc>",
  "assignment_seed": "<pinned randomization seed ref>",
  "row_status": "live | superseded"
}
```

### §2.2 Role-disjointness validator (deterministic, blocking — completeness per Codex round-1 #3)

A Python validator (`validate_role_disjointness`) runs over `assignment_manifest` + `roster_manifest` + `exposure_log` and REJECTS (non-zero exit, blocks construction) any row where, evaluated across the row's `blinding_unit_id`:
- `constructor_sme_id ∈ adjudicator_ids`, OR
- `constructor_sme_id == tiebreaker_id`, OR
- `tiebreaker_id ∈ adjudicator_ids` (first-pass), OR
- `len(set(adjudicator_ids)) != 2` (exactly 2 first-pass adjudicators; multi-adjudicator consensus is not defined in this version), OR
- duplicate `sme_id` within `adjudicator_ids`, OR
- more than one `live` assignment row exists for the same `claim_id`, OR
- any `sme_id` absent from the locked roster manifest, OR
- any assigned `sme_id` is `active == false` or credential-unverified, OR
- any assigned `sme_id` lacks qualification for the claim's domain, OR
- the claim's entity/topic IDs are unresolved (fail-closed; see §4), OR
- a COI hit: an assigned `sme_id` has `sme.entity_ids ∩ claim.entity_ids ≠ ∅` OR `sme.topic_conflict_ids ∩ claim.microtopic_tags ≠ ∅`, OR
- exposure-log contamination: an assigned adjudicator/tiebreaker's exposure log shows a disqualifying prior read (constructor-intent, consensus label, or another adjudicator's first-pass for that blinding unit).

The validator is hash-pinned (per 0a.-1.E custody). Its code hash is recorded alongside the relation-builder/randomizer hashes.

### §2.3 Adjudication tool enforcement — POSITIVE authorization (Codex round-1 #1)

The adjudication UI/CLI does NOT merely block forbidden actions; it POSITIVELY AUTHORIZES. For any claim action:
- **First-pass view/write**: permitted ONLY IF `logged_in_sme_id ∈ adjudicator_ids` for that claim. (A non-constructor SME who is not an assigned adjudicator is also refused — block-list alone was an honor-system gap.)
- **Tiebreak view/write**: permitted ONLY IF `logged_in_sme_id == tiebreaker_id`.
- **Panel action**: permitted ONLY IF `logged_in_sme_id` holds the authorized panel role for that claim.
- **Constructor**: explicitly refused all adjudication/tiebreak/panel actions on any claim in a blinding unit they constructed.
- The tool never renders constructor-intent or consensus labels to a first-pass adjudicator; the tiebreaker sees neither prior first-pass labels nor constructor-intent until their own label is sealed.
- Every claim VIEW (read) and label WRITE is logged to the exposure log (per 0a.-1.E), reads included.

### §2.4 Controlled artifact / access layer (the 4th enforcement surface — Codex round-1 #2)

UI-level hiding is insufficient if SMEs can reach packet internals, constructor notes, prior labels, or consensus files OUTSIDE the tool. Binding rule:
- Direct storage/object access to construction-intent, blinded-adjudication, consensus, and packet-internal artifacts MUST be role-scoped at the storage layer (object ACLs / access tokens), not only at the UI.
- Any access path is wired to the exposure log (reads + writes).
- The §2.2 validator excludes any SME whose exposure log shows a disqualifying read.
- 0a.-1.E implements the storage-layer ACLs + exposure-log wiring; 0a.-1.A names it BINDING here.

## §3. Per-domain credential floors (framework; actual roster operator-filled)

Each credential floor maps to roster-verifiable evidence tags (Codex round-1 #5): the roster records the SPECIFIC qualifying evidence, not a free-text assertion.

| Domain | Credential floor (minimum) | Roster-verifiable evidence tags | COI screen |
|---|---|---|---|
| `clinical` | MD OR PharmD OR PhD (pharmacology/epidemiology/biostatistics) + ≥5y clinical-research, with relevant SPECIALTY tag | `degree`, `license_no`, `specialty`, `years_clinical_research`, `pubmed_authorships` | No financial interest in drugs/devices/sponsors under test |
| `due_diligence` | CFA OR CPA OR JD OR ≥7y M&A/regulatory due-diligence | `credential`, `years_dd`, `deal_sheet_ref` | No interest in entities under test |
| `policy` | PhD/Masters (public policy/law/economics) OR ≥7y legislative/regulatory analysis | `degree`, `years_policy`, `publication_refs` | No active lobbying/advocacy stake |
| `tech` | PhD/Masters (engineering/CS) OR ≥7y standards/architecture | `degree`, `years_tech`, `standards_body_refs` | No vendor stake in the technology under test |
| `ai_sovereignty` | ≥1 of: AI-governance program leadership; standards-body work; AI regulatory/procurement work; peer-reviewed/public AI-policy output; cloud/data-residency expertise; AI risk-evaluation experience — + ≥5y (per NIST AI RMF: documented roles/training/multidisciplinary expertise, NOT vague assertion) | `governance_role_ref`, `standards_work_ref`, `policy_output_ref`, `data_residency_ref`, `risk_eval_ref` | No vendor/government stake biasing the position under test |
| `canada_us` | Cross-border policy/legal/economic expertise + ≥7y | `degree`, `years_crossborder`, `publication_refs` | No active advocacy stake |

**Clinical adjudication-path rule (Codex round-1 #5)**: for claims about treatment / pharmacotherapy / device, at least one MD- or PharmD-qualified reviewer MUST appear in the adjudication path (first-pass OR tiebreak OR panel). Literature/evidence-only clinical claims may use the broader floor.

**Panel-size math (corrected — Codex round-1 #9; the constructor IS an SME and must be role-disjoint)**: per claim the MINIMUM unique eligible SMEs is **3** (1 constructor + 2 first-pass adjudicators), rising to **4** when the tiebreak path is live. After accounting for COI exclusions, scheduling, and the clinical MD/PharmD-in-path rule, the per-domain roster TARGET is **5-6 qualified SMEs**, not 3. The prior "minimum 2 to operate" was incorrect and is withdrawn.

## §4. COI screen protocol (mechanically enumerable — Codex round-1 #6)

Free-text declared-interest prose is NOT mechanically enumerable. v1 uses canonical IDs:

1. Each SME completes a declared-interest form recording canonical IDs, NOT prose:
   - `entity_ids[]`: companies, sponsors, drugs/devices, governments, regulators, vendors (canonical identity per 0a.-1.D — DOI/registry/org-id scheme)
   - `topic_conflict_ids[]`: topic-level advocacy conflicts, keyed to D4 microtopic IDs
2. Roster manifest records these per the §7 schema: `{sme_id, domains_qualified[], entity_ids[], topic_conflict_ids[], coi_cleared_per_domain{}, coi_screened_by, coi_screened_at}`.
3. Each claim carries resolved `entity_ids[]` + `microtopic_tags[]` (from 0a.-1.C construction_manifest). The §2.2 validator:
   - computes COI hit = (`sme.entity_ids ∩ claim.entity_ids ≠ ∅`) OR (`sme.topic_conflict_ids ∩ claim.microtopic_tags ≠ ∅`)
   - excludes a hit SME from constructing/adjudicating/tiebreaking that claim
   - **fails closed** if the claim's entity/topic IDs are unresolved (no silent pass)
4. Entity-ID resolution depends on 0a.-1.D (canonical source/entity identity) for `entity_ids` and D4 (microtopic ontology) for `topic_conflict_ids`. Until both exist, COI runs in fail-closed mode (claims with unresolved IDs cannot be assigned). This is a forward dependency, not a chicken-and-egg: the framework + validator are locked now; the ID resolution wires in when 0a.-1.D and D4 land.

## §5. Blinding protocol (label-symmetric packet construction — Codex round-1 #7)

Hiding labels is insufficient if packet CURATION leaks intent (a packet suspiciously built around the fabricated claim tips off the adjudicator). v1 requires **label-symmetric packet construction**:

- Same packet builder + same source-selection rules for fabricated and non-fabricated claims.
- Same facet generation (neutral, deterministic, uniform across all claims per 0a.-1.C facet label-safety — no constructor-authored spotlighting of the suspicious clause).
- No packet metadata that reveals fabrication rationale (no "injected here" markers, no asymmetric annotation).
- Adjudicators see: claim text + neutral facet views + rendered evidence packet + cited spans.
- Adjudicators do NOT see: constructor-intent labels, fabrication-injection notes, consensus gold labels, other adjudicators' first-pass labels.
- The TIEBREAKER receives the SAME blinded packet and does NOT see prior first-pass labels or constructor-intent until their own label is sealed.
- IRR (contract §7.3) is computed on first-pass blinded labels ONLY.

## §6. Tiebreak workflow (tuple-majority semantics — Codex round-1 #8)

The label is a TUPLE `(severity, fab_status)`. Majority is evaluated PER REQUIRED FIELD, not over the whole tuple as a unit:

1. 2 adjudicators label first-pass (blinded).
2. Both fields agree → consensus = agreement; path = `agree`.
3. Any field disagrees → tiebreaker (role-disjoint per §1) labels the disagreeing field(s); for each field, majority of 3 = consensus; path = `tiebreak`.
4. If ANY required field still lacks a majority (e.g., a 3-way ordinal severity split S1/S2/S3) → §-1.1 panel; path = `panel`. **Severity is NOT median/averaged** — ordinal disagreement escalates, it does not get numerically collapsed (no median/mean unless the rubric in 0a.-1.B later explicitly defines one).
5. **Panel composition (corrected — Codex round-1 #8)**: the §-1.1 panel is operator + Codex line-by-line vs cited evidence AND ≥1 domain-qualified SME (especially mandatory for clinical gold labels per §3 MD/PharmD-in-path rule). Operator+Codex alone is insufficient for clinical severity gold labels.
6. Consensus written to `consensus_gold_labels` (0a.-1.C); first-pass labels retained in `blinded_adjudication_labels` for IRR.

## §7. Roster manifest (operator-procurement; framework-governed)

```json
{
  "sme_id": "<stable id>",
  "domains_qualified": ["<domain>", ...],
  "credentials": ["<credential>", ...],
  "evidence_tags": {"<domain>": ["<roster-verifiable tag per §3>", ...]},
  "credential_verified_by": "<operator/custodian>",
  "credential_verified_at": "<utc>",
  "entity_ids": ["<canonical entity id per §4 / 0a.-1.D>", ...],
  "topic_conflict_ids": ["<D4 microtopic id per §4>", ...],
  "coi_cleared_per_domain": {"<domain>": true},
  "coi_screened_by": "<custodian>",
  "coi_screened_at": "<utc>",
  "active": true
}
```

(Free-text declared-interest prose, if collected on the intake form, is NON-BINDING and is NOT a validator input — only the canonical `entity_ids[]` / `topic_conflict_ids[]` per §4 are validator-consumed.)

The roster is operator-filled (real SME recruitment). The framework (this deliverable) governs its schema + the validators that consume it. Construction CANNOT begin until, per §3's corrected capacity rule, each validation domain has enough coi-cleared, credential-verified SMEs to satisfy the per-claim minimum of 3 unique eligible SMEs (1 constructor + 2 first-pass adjudicators), rising to 4 when the tiebreak path is live — with a per-domain roster TARGET of 5-6 to absorb COI exclusions, the clinical MD/PharmD-in-path rule, and scheduling.

---

## §8. Dependencies + ordering notes

- Needs D1a (6 domains) — DONE.
- 0a.-1.B (severity + fabrication rubric) must precede adjudicator CALIBRATION (can't calibrate against a rubric that doesn't exist) — but the GOVERNANCE framework (this deliverable) can lock first.
- `assignment_manifest` + `roster_manifest` schemas feed 0a.-1.C (integrated metadata) and 0a.-1.E (custody/exposure log).
- The role-disjointness validator + adjudication-tool enforcement are hash-pinned in 0a.-1.E.

## §9. Definition of done (0a.-1.A)

Framework locked: role taxonomy, role-disjointness invariant + validator spec, adjudication-tool enforcement rules, per-domain credential floors, COI protocol, blinding protocol, tiebreak workflow, roster + assignment manifest schemas. Codex §-1.1 APPROVE. Hash-pin. Operator sign-off (which also kicks off operator-side SME recruitment against the locked roster schema).

Deferred (operator procurement, NOT this deliverable): actual SME identities, credential verification, COI clearance.
