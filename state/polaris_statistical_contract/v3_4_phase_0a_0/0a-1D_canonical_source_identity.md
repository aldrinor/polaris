# 0a.-1.D — Canonical Source Identity + Admissibility (draft for Codex review)

**Deliverable**: Phase 0a.0 / 0a.-1.D — canonical source identity scheme + per-domain admissibility table + Jaccard set-membership rule.
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock 0a.-1.D" after 4 rounds: 7 build-blocking issues + authority/heading consistency fixes, all closed; pending operator sign-off).
**Parent**: contract v3.3 §3.4 criterion 2 (evidence-Jaccard ≥0.5); depends on D1a (6 domains).
**Plan**: `PHASE_0a_0_PLAN.md`. MUST precede 0a.-1.C (relation-builder consumes source identity). Feeds 0a.-1.A §4 COI entity_ids.
**Codex review**: `.codex/I-safety-001b/codex_0a1D_review.txt` + `codex_0a1D_confirm{,2,3,4}.txt`.
**Version**: 1 (LOCKED)

**Note (Codex round-1)**: `SRC-NNN` (the run-local `source_registry.py` citation ID) is NEVER a canonical source identity — it is run-local citation machinery. `canonical_source_id` (§2.1) is the cross-run identity.

**Why this exists**: contract §3.4 criterion 2 computes scenario-family relations via Jaccard ≥0.5 on the "cited evidence-document set." This is unbuildable without (a) a canonical source-IDENTITY scheme (so two citations of the same source resolve to the same set member), and (b) a per-domain ADMISSIBILITY summary that defers to the per-domain scope template (`config/scope_templates/{domain}.yaml`) as the authoritative allowlist for what sources may enter a packet. Codex round-2 flagged that `audit_ir/registry.py` is a run registry, NOT the source allowlist — real admissibility lives in the scope templates (authoritative), supported by clinical retrieval + tier classifier + source registry.

---

## §1. Repo grounding (where source identity + admissibility currently live)

| Concern | Repo location | What it provides |
|---|---|---|
| Source record | `src/polaris_graph/retrieval/source_registry.py` — `SourceEntry` | `source_id` (SRC-NNN), `url`, `title`, `source_type` (web/academic/pdf/government/standard), `authors`, `year`, `venue`, `doi`, `domain` (url-derived), `authority_score` |
| Clinical tier rules | `src/polaris_graph/clinical_retrieval/clinical_source_registry.py` | T1/T2/T3 `_DomainRule` set + `_DENY_DOMAINS` frozenset; `classify_url` |
| Citation normalize | `src/polaris_graph/retrieval/citation_normalizer.py` | SRC-NNN normalization, citation stats |
| Domain admissibility (AUTHORITATIVE) | `config/scope_templates/{domain}.yaml` | per-domain complete admissible-source set + tier caps — the §3 allowlist authority |

0a.-1.D EXTENDS these — it does not replace them. The canonical-identity scheme adds the stronger identifiers (DOI/PMID/NCT/reg-id + archive snapshot + content SHA) the contract needs but `SourceEntry` lacks; the admissibility table reconciles the per-domain rules into one auditable place.

## §2. Canonical source identity (locked scheme — SOURCE-CLASS-CONDITIONED per Codex round-1 #1)

**Critical fix (Codex round-1 #1 — identity over-collapse)**: identity precedence is conditioned on the source's CLASS. A registry/regulatory ID wins ONLY when it identifies the source DOCUMENT itself — NOT when it is merely mentioned inside another document. An NCT ID cited inside a journal article does NOT make the article `nct:*` (that would collapse all papers about one trial); the article keeps its DOI. FDA app numbers / Health Canada DINs are product/application identifiers → they go in `source_subject_ids[]` / `entity_ids[]`, NOT the source identity, unless they identify the actual regulatory source document.

**Source-class-conditioned precedence**:

- **Registry/regulatory source record** (the source document IS a trial-registry page, an FDA label, an EMA EPAR, a gazette entry, a standard): canonical id = that document's own registry/regulatory/standard ID (`nct:`, `eudract:`, `fda-label:`, `ema-epar:`, `gazette:`, `iso:`, etc.) + `source_version_id` (§2.2).
- **Peer-reviewed literature**: canonical id = `doi:` (normalized); if no usable DOI, `pmid:`.
- **Web/government/standards lacking the above**: canonical id = `url:` (canonicalized per §2.3).

Registry/trial/product IDs MENTIONED in a literature source are recorded in `source_subject_ids[]` (e.g., the NCTs a review discusses) — they are subject metadata, never the source's identity.

PLUS, ALWAYS (every source):
- `archive_snapshot_url`: Wayback/Perma snapshot at packet-construction time (reproducibility — content drifts).
- `content_sha256`: SHA256 of fetched bytes at construction time.
- `version_date`: the source's own version/publication date.
- `source_version_id` (NEW #2): for regulatory/legal/standards sources, the official version identifier. Distinct official versions are DISTINCT sources (auditable, not silently collapsed); a mere re-snapshot (SHA drift, same version) is the SAME source.
- `landing_vs_pdf`: distinguishes a landing page from its PDF (same source — actively aliased per §2.3, not merely flagged).

### §2.1 `canonical_source_id` (the resolved identity)

```
canonical_source_id = <scheme>:<normalized_value>
  scheme ∈ {nct, eudract, fda-label, ema-epar, gazette, iso, ieee, ... , doi, pmid, url}
  chosen by §2 source-class-conditioned precedence.
aliases[]            = other identifiers that resolve to this same source (§2.3)
work_id (optional)   = shared study/work grouping for preprint↔published (NOT identity)
source_subject_ids[] = registry/product IDs mentioned IN the source (subject metadata, not identity)
```

Two citations resolve to the SAME source iff their resolved `canonical_source_id` (after alias resolution) matches. `content_sha256` is a CONSISTENCY check, NOT identity (same canonical_source_id, two snapshot times, differing sha → flagged for review, not two sources).

**Preprint↔published (Codex round-1 #2)**: a preprint and its later published version are DIFFERENT `canonical_source_id`s (different documents), optionally sharing a `work_id` — they are NOT the same source.

### §2.2 / §2.3 Normalization + alias resolution (locked — Codex round-1 #2)

The canonicalizer (deterministic, hash-pinned, runs before any Jaccard) applies:
- **DOI**: lowercase, strip `https://doi.org/` / `doi:` prefixes → `doi:10.xxxx/...`.
- **PMID→DOI crosswalk**: if a source cited by PMID has a recoverable DOI, the canonical id is the DOI and the PMID is an alias. (So a PMID-citation and a DOI-citation of the same paper resolve to ONE source.)
- **URL canonicalization**: scheme+host+path, strip query/fragment/tracking params per a locked param-strip list; host lowercased.
- **landing↔PDF active aliasing**: when a landing page and its full-text PDF are the same source, the canonicalizer ALIASES them to one `canonical_source_id` (Codex round-1 #6 — a flag alone doesn't de-dup; the canonicalizer must actively merge). Two DIFFERENT PDFs stay distinct.
- **`aliases[]`** records every alternate identifier that maps to the canonical id, so the relation-builder is alias-stable.

## §3. Per-domain admissibility summary (scope template is the actual allowlist)

**Class-label fix (Codex round-1 #3)**: the repo overloads "T1/T2/T3" — `clinical_source_registry.py` (T1=regulatory+Cochrane/SR, T2=peer-reviewed primary, T3=registries/guidelines/gov) DIFFERS from `tier_classifier.py` (T1=primary, T2=SR/MA, T3=gov/regulatory). To avoid creating a THIRD meaning, 0a.-1.D names admissible source classes with INDEPENDENT labels (A-class names below), and the validator (§3.1) consumes the per-domain **scope template** as the authority for admissibility (NOT the overloaded T labels). The clinical tier classifiers remain for retrieval/authority scoring; they are not the admissibility authority here.

**Authority (Codex round-1 #4 — resolves table-vs-template conflict)**: the per-domain **scope template is the COMPLETE and AUTHORITATIVE admissible-source set**, INCLUDING all of its tiers and their caps/context-limits (e.g., `clinical.yaml` admits T1-T7: T1 primary RCT, T2 SR/MA, T3 regulatory/guideline, T4 narrative reviews [context/mechanism, ≤20%, not for novel efficacy], T5 HCP/marketing [≤15%, only when corroborated by T3], T6 commentary/blog [supporting only], T7 abstracts/preprints [hypothesis-generating only]; with the template's `expected_tier_distribution` caps). The validator (§3.1) consumes the scope template, not the table below.

The table below is an authority-ordered SUMMARY of the HIGH-authority classes per domain — it is NOT the exhaustive admissible set and does NOT narrow the template. The complete admissible set + caps = the scope template.

| Domain | High-authority class summary (full set + caps = scope template) |
|---|---|
| `clinical` | T1 primary RCT, T2 SR/MA, T3 regulatory/guideline (full T1-T7 + caps per `clinical.yaml`); `_DENY_DOMAINS` HARD-excluded |
| `due_diligence` | regulatory filings (SEC/SEDAR), audited financials, court/litigation, primary disclosures + press releases, patents, peer-reviewed tech/mechanism articles, systematic/narrative market reviews, white papers, analyst reports, conference/preprint early signals, business news (full set + caps per `due_diligence.yaml`) |
| `policy` | primary legislation/regulation, official gazettes, government/parliamentary records, regulator publications, HTA reports, NGO reports, named commentary, peer-reviewed policy analysis (full set + caps per `policy.yaml`) |
| `tech` | standards bodies (ISO/IEC/IEEE/NIST/W3C/IETF), vendor specs/docs, OSS docs, peer-reviewed engineering lit, preprints, attributed technical blogs, certification bodies (full set + caps per `tech.yaml`) |
| `ai_sovereignty` | AI regulation/governance frameworks (EU AI Act, NIST AI RMF, national strategies), data-residency/sovereignty law, procurement standards, policy-institute reports, vendor sovereign-cloud docs, peer-reviewed AI-policy lit (full set + caps per `ai_sovereignty.yaml`) |
| `canada_us` | binding treaties/agreements, CA+US primary law/regulation, official bilateral bodies, gov trade/immigration/defense/energy publications, HTA/policy analyst reports, systematic + narrative reviews, industry/vendor positions, official statistics, peer-reviewed bilateral lit (full set + caps per `canada_us.yaml`) |

`ai_sovereignty.yaml` + `canada_us.yaml` completeness checklists do not yet exist (D1 authors them); their scope templates DO exist and are the admissibility authority. Any validation-specific narrowing of a template class is recorded as an explicit hash-pinned override with rationale (none currently).

### §3.1 Admissibility validator (deterministic, blocking — Codex round-1 #5)

`validate_source_admissibility` runs over each packet's `source_packet_manifest` (0a.-1.C). For each source it **independently RECOMPUTES the admissible class** from: the (canonicalized) URL, source metadata, the PINNED classifier version, the per-domain scope template, and the deny rules — the `canonical_source_id` does NOT itself carry the class. REJECTS the packet if any source's recomputed class is not admissible for the claim's domain AND lacks a §3.2 exception.

`_DENY_DOMAINS` (from `clinical_source_registry.py`) is **HARD-DENY and NON-EXCEPTIONABLE** — a deny-listed source cannot be admitted via §3.2; removing a deny entry requires a formal contract §P4 amendment. Hash-pinned per 0a.-1.E.

### §3.2 Exception governance (Codex round-1 #5)

A source outside the admissible classes (but NOT deny-listed) may be admitted ONLY via a pre-registered exception: `{canonical_source_id, domain, justification, approved_by (≥1 domain SME, role-disjoint at the blinding_unit_id level per 0a.-1.A — NOT merely from the claim's constructor), approved_at}`. The approver MUST NOT subsequently adjudicate any claim in that blinding unit. Logged, hash-pinned, surfaced in audit. No silent admission.

## §4. Jaccard set-membership rule (contract §3.4 criterion 2 — Codex round-1 #6)

Granularity: **source-document level** (one `canonical_source_id` = one member, regardless of how many spans cited; span-level would overweight heavily-quoted documents).

**Set definition for 0a.-1.C (claim-level vs packet-level — locked)**: contract §3.4 criterion 2 relates two CLAIMS. The evidence set compared is the **claim-level cited-source set**: the distinct `canonical_source_id`s actually cited by that claim. (The packet-level set — all sources in the packet — is recorded too, but criterion-2 Jaccard is computed on the CLAIM-level cited sets, because two claims in one packet may cite different subsets.) 0a.-1.C consumes the claim-level sets; the packet-level set is available for diagnostics.

- `Jaccard(A, B) = |set_A ∩ set_B| / |set_A ∪ set_B|`, membership keyed on alias-resolved `canonical_source_id`.
- **Empty-set behavior (Codex round-1 #6)**: if either claim cites zero sources (`set = ∅`), `Jaccard` is DEFINED as 0 (no criterion-2 relation); `|A ∪ B| = 0` does not raise — it returns 0. (Two source-less claims are not related via criterion 2; they may still relate via criteria 1/3/4/5.)
- Threshold ≥0.5 → criterion-2 relation (per contract §3.4).
- A landing page and its PDF resolve (via §2.3 active aliasing) to ONE `canonical_source_id` → ONE member (no double-counting); two different PDFs stay distinct members.

## §5. COI entity-ID linkage (feeds 0a.-1.A §4 — Codex round-1 #7)

0a.-1.A §4 requires canonical `entity_ids` for COI. A claim's COI entity set is the **UNION of two sources** (Codex round-1 #7 — source entities alone are insufficient):

1. **Source entities**: the publishing/sponsoring/regulator entities of the claim's cited sources. Entity identity: registry ID where available (LEI for companies, GRID/ROR for institutions, official regulator IDs), else canonical domain. Recorded as `entity_ids[]` on each source record.
2. **Claim-subject entities**: entities MENTIONED IN the claim itself — companies, drugs/devices, regulators, governments, vendors, comparators, beneficiaries — even when not the publisher of any cited source. Resolved to the same entity-ID scheme.

`claim.entity_ids = source_entities(claim) ∪ claim_subject_entities(claim)`. Per 0a.-1.A §2.2, the COI validator FAILS CLOSED if any claim entity ID is unresolved.

- Topic-level COI (`topic_conflict_ids`) is keyed to D4 microtopic IDs (forward dependency to D4).
- Claim-subject entity extraction is performed neutrally (no spotlighting per 0a.-1.A §5 / 0a.-1.B §3) and uniformly across all claims.

## §6. Definition of done (0a.-1.D)

Locked: source-class-conditioned canonical-identity precedence (no over-collapse) + always-on fields (archive/sha/version_date/source_version_id/landing) + normalization/alias/crosswalk rules + preprint↔published work_id, per-domain admissibility table (independent class labels, scope-template-aligned) + recompute-class validator + hard-deny + blinding-unit-scoped exception governance, claim-level Jaccard source-document set-membership + empty-set behavior + active landing/PDF aliasing, COI entity union (source ∪ claim-subject) + fail-closed. Codex §-1.1 APPROVE. Hash-pin. Operator sign-off.

## §7. Dependencies + forward notes

- Needs D1a (6 domains) — DONE.
- PRECEDES 0a.-1.C (relation-builder consumes `canonical_source_id` for Jaccard).
- Feeds 0a.-1.A §4 COI: `claim.entity_ids = source_entities ∪ claim_subject_entities` per §5 (NOT source records alone).
- `topic_conflict_ids` keyed to D4 microtopic — forward dependency.
- Admissibility validator + exception records hash-pinned in 0a.-1.E custody.
- Extends (does not replace) `source_registry.py` / `clinical_source_registry.py` — the contract's stronger identity fields layer on top of `SourceEntry`.
