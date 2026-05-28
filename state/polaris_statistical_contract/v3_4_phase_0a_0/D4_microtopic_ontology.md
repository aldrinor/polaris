# D4 — Microtopic Ontology: Structure + Governance (draft for Codex review)

**Deliverable**: Phase 0a.0 / D4 — the microtopic ontology STRUCTURE + GOVERNANCE (the L3 seed content is a gated follow-on, §6).
**Status**: LOCKED (Codex APPROVE 2026-05-27 after 2 rounds; pending operator sign-off).
**Parent**: contract v3.3 §3.4 criterion 5; depends on D1a.
**Plan**: `PHASE_0a_0_PLAN.md` (hybrid controlled L1/L2 + governed append-only L3 — Codex plan round-1 P2-1).
**Codex review**: `.codex/I-safety-001b/codex_d4_review.txt`.
**Version**: 1 (draft)

**Scope (Codex round-1 #6 — resolves the seed contradiction)**: D4 locks the ONTOLOGY STRUCTURE + ID SCHEME + GOVERNANCE + VALIDATOR SUBSTRATE. The machine-readable L3 SEED content is NOT in D4 — it is a hard-gated follow-on (`D4-seed`, §6) that must be authored + hash-pinned BEFORE any SME COI screening, claim construction, construction_manifest acceptance, relation-builder dry-run, D8 allocation, or pilot. "Before pilot" alone is too late (construction/COI can start earlier); §6 makes the gate precede all of those.

**Why this exists**: §3.4 criterion 5 fires partly on shared microtopic tags; 0a.-1.A §4 COI uses `topic_conflict_ids` keyed to D4 microtopic IDs. D4 supplies the **shared-microtopic predicate** only — the full criterion-5 rule (shared microtopic AND same stratum AND ≥1 additional correlation) stays in 0a.-1.C §2.1.

---

## §1. Ontology structure (3 levels, locked)

| Level | What it is | Control |
|---|---|---|
| **L1 — domain** | the 6 validation domains (D1a) | CLOSED (exactly the 6) |
| **L2 — category** | within-domain subject category | CLOSED (locked enumeration §3; changes are §P4 Category-3, NOT append-log) |
| **L3 — microtopic** | the specific reusable semantic topic | HYBRID: seed locked (§6 gate); governed append (§4) |

**Criterion-5 match unit = L3** (full canonical ID). L2 is closed because it is part of the canonical ID namespace — append-only L2 would be a gaming path (move a semantically identical L3 under a new L2 to dodge exact-match relations/COI). L2 changes are §P4 Category-3.

## §2. Microtopic ID scheme + L3 metadata (locked)

`microtopic_id` = `"<L1_domain>.<L2_category>.<L3_slug>"`, e.g. `clinical.intervention_or_exposure.glp1_ra`.

**Strict ID regex (locked, Codex round-1 #2)**: `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — lowercase ASCII slugs only; `.` reserved as the level separator; underscores within a level. An alias is NEVER an ID.

**L3 metadata schema (Codex round-1 #2 — prevents accidental-synonym topics)**: each L3 entry carries:
```
{ microtopic_id, display_name, aliases[], definition,
  inclusion_criteria, exclusion_criteria,
  status: enum[active, deprecated], ontology_version, ontology_hash,
  supersedes?, replaced_by?, assignable_to_new_claims: bool,
  coi_screened_against_ontology_hash }
```
`aliases[]` collapses `glp1_ra` / `glp_1_ra` / `glp1_receptor_agonist` into ONE topic (they are aliases of one `microtopic_id`, not separate IDs). Tagging resolves an alias → its canonical `microtopic_id` before any matching.

## §3. Locked L2 categories per domain (CLOSED — revised per Codex round-1 #2)

"Six per domain" is NOT sacred (Codex round-1); defensible taxonomy wins over cosmetic balance.

| Domain | L2 categories |
|---|---|
| `clinical` | `intervention_or_exposure` (drugs/devices/procedures/diagnostics/exposures — replaces too-narrow `drug_class`), `indication`, `outcome_endpoint` (efficacy/biomarker/mortality/hospitalization/surrogate — NEW), `safety_signal` (harms), `regulatory_pathway`, `study_design`, `population` |
| `due_diligence` | `financial_metric`, `liability_risk` (incl. IP, material-contract, operational risk — definitions in seed), `governance`, `market`, `regulatory_filing`, `transaction_structure` |
| `policy` | `legal_obligation`, `stakeholder`, `implementation`, `economic_effect`, `jurisdiction`, `enforcement` |
| `tech` | `architecture`, `standard`, `performance`, `security`, `interoperability`, `deployment` |
| `ai_sovereignty` | `governance_framework`, `data_residency`, `procurement`, `model_provenance`, `security_control` (incl. `lawful_access`), `compute_infrastructure` (NEW — placed explicitly), `vendor_risk` |
| `canada_us` | `trade_tariff`, `immigration`, `defense_security`, `energy`, `regulatory_alignment`, `economic_policy` (replaces `binding_agreement` — a legal FORM that crosscut all subjects; agreements are now L3s under their topical L2, e.g. `canada_us.trade_tariff.cusma`) |

`binding_agreement` REMOVED as an L2 (Codex round-1 #2: it crosscut the whole domain → inconsistent tagging / false negatives under full-ID match). Agreements live as L3s under the topical L2 they govern.

## §4. Append governance — three windows (Codex round-1 #3)

L3 additions/splits are governed by exposure window (per 0a.-1.E §6 / contract §P4.2):

1. **Pre-structural exposure**: recorded append allowed (append-log entry, no amendment).
2. **Post-structural, pre-outcome** (after any allowed read of relation P/N/degree/DEFF/relation-hash — these are STRUCTURAL): an L3 add/split changes clustering/DEFF → it is a §P4 **Category-3** amendment with uniform re-tag/rebuild of affected manifests + both old and new runs retained + hash-pin.
3. **Post-outcome**: §P4 **Category-4** — confirmatory analysis becomes exploratory/remedial per contract.

**Append-log entry** (richer than v0): the full L3 metadata schema (§2) PLUS `added_by, added_at, rationale, parent_L2`. Append-only: **no deletion, no re-meaning**. A wrong L3 is `deprecated` (status flips, `replaced_by` set, `assignable_to_new_claims=false`), NOT deleted; affected claims re-tagged under the appropriate §P4 window; corrected claim manifests get new versions/hashes.

## §5. Anti-gaming rules (Codex round-1 #4) + COI re-screening (#5)

### §5.1 L3 well-formedness (anti-gaming)
An L3 tag MUST be a reusable semantic topic. It MUST NOT be claim-specific, source-specific, packet-specific, entity-specific, severity-specific, or fabricated-claim-specific (any of these would let a constructor manipulate criterion-5 relations). Validator rejects an L3 used by ≤1 claim-family as a candidate hyper-specific tag for review.

### §5.2 Complete tagging
A claim carries ALL material L3 microtopics it touches, not just one primary tag (under-tagging deflates P/DEFF — the dangerous direction). Adjudication-independent: tagging is part of construction metadata.

### §5.3 Split uniformity
Splitting an over-broad L3 RE-TAGS ALL claims under the old semantic scope UNIFORMLY (no cherry-picking relation-reducing pairs). Enforced as part of the §4 Category-3 amendment.

### §5.4 Over-breadth audit (blocking, pre-outcome)
The 0a.-1.C §2.4 within-stratum degree audit (95th-pctile > 25) is a BLOCKING pre-outcome structural audit (not advisory) — an over-broad L3 is split before outcome. It catches BROAD tags; §5.1/§5.2 catch HYPER-SPECIFIC/under-tag (deflating) tags, which the degree audit cannot.

### §5.5 COI re-screening on ontology change
Every L3 append TRIGGERS COI re-screening before claims using that L3 can be assigned: an SME with a `topic_conflict_id` matching the new L3 (or an L2/domain-level declared conflict that EXPANDS to all current descendant L3s) is excluded. The L3 entry records `coi_screened_against_ontology_hash`. The 0a.-1.A §2.2 validator fails closed on unresolved SME `topic_conflict_ids` AND unresolved claim `microtopic_tags`. A new topic appearing after roster screening cannot silently bypass an SME's topic conflict.

## §6. The D4-seed gate (Codex round-1 #6 — hard prerequisite)

`D4-seed` = the machine-readable L3 seed (a YAML/JSON per domain, each L3 with the full §2 metadata + definitions/inclusion/exclusion). It is NOT this deliverable. It is a HARD GATE that MUST be authored + hash-pinned BEFORE any of: SME COI screening, claim construction, construction_manifest acceptance, relation-builder dry-run, D8 allocation, the pilot. Until D4-seed is locked, "unresolved microtopic" is mechanically defined (any tag not `active` in the locked ontology version) and the validator rejects construction.

## §7. Validator substrate (Codex round-1 #7)

D4 locks the resolver/validator substrate the relation-builder + COI need:
- **Canonical seed file** (D4-seed gate, §6) + **append-log** (§4) — the ontology's content.
- **Ontology version + hash** — every tag resolution is against a pinned ontology version.
- **`active`/`deprecated` status** — only `active` tags are assignable to new claims.
- **Resolver**: alias → canonical `microtopic_id`; rejects (fail-closed) any tag not `active` in the locked ontology version → THIS is the mechanical definition of "unresolved microtopic".
- D4 supplies the shared-microtopic PREDICATE only; the full criterion-5 rule (shared microtopic AND same stratum AND ≥1 additional correlation) remains 0a.-1.C §2.1.

## §8. Definition of done (D4 structure/governance)

Locked: 3-level structure (L1/L2 closed, L3 hybrid), revised L2 enumeration (clinical +outcome_endpoint/intervention_or_exposure; canada_us economic_policy replacing binding_agreement; ai_sovereignty compute_infrastructure + lawful_access placed; DD liability_risk scope), ID regex + L3 metadata schema (display_name/aliases/definition/inclusion/exclusion/status/version/supersedes), 3-window append governance + append-log, anti-gaming rules (§5.1-5.4), COI re-screening (§5.5), the D4-seed hard gate (§6), validator substrate (§7). Codex §-1.1 APPROVE. Operator sign-off. NOTE: the L3 seed CONTENT is gated (D4-seed), not in this lock.

## §9. Dependencies + forward notes

- Needs D1a (6 domains = L1) — DONE.
- `microtopic_id`s consumed by relation-builder criterion 5 (0a.-1.C §2.1) + 0a.-1.A §4 COI.
- Ontology file + append-log + D4-seed are custody artifacts (0a.-1.E §1 hash registry).
- D4-seed gate (§6) precedes COI screening / construction / dry-run / D8 / pilot.
- Over-breadth caught by 0a.-1.C §2.4 (blocking pre-outcome); hyper-specific/under-tag caught by §5.1/§5.2.
