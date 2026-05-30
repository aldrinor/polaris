# D7' — Source-Packet Curation Methodology (draft for Codex review)

**Deliverable**: Phase 0a.0 / D7' — how an evidence packet is curated for a claim-construction scenario.
**Status**: LOCKED (Codex APPROVE 2026-05-27 after 3 rounds; pending operator sign-off).
**Parent**: contract v3.3 §3.4 criterion 2 (Jaccard) + criterion 5 (packet_class); depends on 0a.-1.D (source identity/admissibility), D3 (downselect/bins), 0a.-1.B (label-symmetry).
**Plan**: `PHASE_0a_0_PLAN.md` (D7' after 0a.-1.D — cycle broken; packet methodology needs source identity first).
**Codex review**: `.codex/I-safety-001b/codex_d7_review.txt`.
**Version**: 1 (draft)

**Why this exists**: a "packet" is the set of source documents presented to the generator + adjudicator for one claim-construction scenario. The contract's Jaccard relation (criterion 2) and packet-class relation (criterion 5) both depend on a LOCKED definition of what a packet IS and how it's built. 0a.-1.D defined source IDENTITY + admissibility; D3 defined size bins + downselect; this deliverable defines the CURATION methodology + `packet_class` + the `source_packet_manifest` population.

---

## §1. What a packet is (locked)

A **packet** = the curated, ordered set of admissible distinct source documents (by `canonical_source_id`, 0a.-1.D) presented for ONE claim-construction scenario. It is:
- The unit of `source_packet_manifest` (0a.-1.C §1.6): `{evidence_packet_id, canonical_source_ids[], packet_class, sha256_of_sorted_canonical_ids}`.
- The downselected set when production retrieval exceeds the target (D3 §3) — the packet is the ≤80 downselected sources, NOT the full retrieval.
- The basis for `evidence_pool_bin` (D3 §2: bin from packet distinct-admissible-source count) and the claim-level Jaccard (0a.-1.D §4).
- Non-empty (D3 §2.1: 0-source packet is a fail-closed construction error; schema `minItems: 1`).

## §2. Curation protocol (locked, deterministic where it must be)

1. **Source gathering (provenance-recorded — Codex round-1 #2/#4)**: the constructor assembles candidates from production retrieval and/or direct SME selection. Because downstream admissibility/downselect validation CANNOT detect a constructor choosing a telltale source universe for fabricated claims, a **`source_selection_manifest`** is recorded per scenario: the retrieval queries used, each direct SME selection + inclusion rationale/provenance, and the matched-control pairing (which supported-claim scenario this fab scenario is parity-matched to per 0a.-1.B §3). Label-symmetry is enforced at SELECTION, not just rendering: the gathering procedure + query templates are identical for the fab scenario and its matched supported control. Stored under 0a.-1.E custody; a fab scenario whose selection manifest diverges from its matched control is a construction error.
2. **Admissibility filter**: each candidate is admissibility-checked (0a.-1.D §3.1 validator — recomputes class from URL/metadata/pinned-classifier/scope-template/deny). `_DENY_DOMAINS` hard-rejected. Out-of-class sources only via 0a.-1.D §3.2 exception.
3. **Canonicalization + dedup**: each admitted source resolved to its `canonical_source_id` (0a.-1.D §2.3 — alias resolution, landing/PDF merge). Duplicate canonical_source_ids collapse to one member.
4. **Downselect (if needed)**: if the admissible distinct count > `target_packet_source_count`, downselect per D3 §3 (deterministic rank tuple + downselect_manifest).
5. **Snapshot**: each packet source gets a self-contained rendered snapshot (0a.-1.E §5) at construction time.
6. **Manifest population**: `canonical_source_ids` = the sorted distinct canonical_source_ids; `sha256_of_sorted_canonical_ids` = SHA256 of those sorted ids (the packet's content identity); `packet_class` per §3.

## §3. `packet_class` definition (locked — used by criterion 5)

`packet_class` is a coarse equivalence label grouping packets that draw from the SAME curated source family, used by §3.4 criterion 5 ("shared packet class" as one correlation source). Locked definition (Codex round-1 #3/#6):

`packet_class` = canonical string `"<domain>|<evidence_pool_bin>|<dominant_source_class>"`

- **`complexity_tier` is NOT a component** (Codex round-1 #6): complexity is a per-CLAIM property (D2, assigned from the question), NOT a packet property. Including it in a packet-level field was ambiguous (one packet could back claims of different tiers). `packet_class` is now purely packet-level → unambiguous + computable from the packet alone.
- **`dominant_source_class`** = the admissibility class (0a.-1.D §3) contributing the PLURALITY of the packet's distinct sources. Class namespace = the scope-template tier/authority labels (0a.-1.D §3, e.g. `clinical:T1`). Ties broken by scope-template authority priority ASC, then class-token lexical ASC. A single-source packet's dominant class is that source's class. **Exception-admitted sources** (0a.-1.D §3.2) carry the class token `exception:<approved-class-or-EXC>` so they are deterministically classifiable.
- **Canonical serialization**: the three components are pipe-joined in fixed order (`domain|bin|dominant_source_class`); two packets share a class iff the serialized strings are byte-equal.

**Packet-ID reuse invariant (Codex round-1 #6)**: a single `evidence_packet_id` is homogeneous for `(domain, evidence_pool_bin)` by construction (a packet has one source set → one bin, built for one domain). Claims of different complexity tiers MAY share a packet_id (complexity is no longer in packet_class, so no ambiguity). The `source_packet_manifest.packet_class` is therefore well-defined per packet.

Rationale: criterion 5 fires (microtopic + same-stratum + shared packet class) when two claims draw from structurally similar source families — coarse enough not to be "same exact sources" (that's criterion 2's Jaccard), but a real correlation source. The within-stratum degree audit (0a.-1.C §2.4) catches over-saturation if microtopics or packet_classes are too broad.

## §4. Label-symmetry (0a.-1.B §3 — anti-pattern-leakage)

Packet curation MUST be label-symmetric: the SAME gathering → admissibility → canonicalization → downselect → snapshot pipeline is applied IDENTICALLY to packets backing fabricated claims and packets backing supported claims. No packet built around a fabricated claim may be curated differently (e.g. spotlighting the contradicting source, or omitting it) from a supported-claim packet. Per 0a.-1.B §3 matched-controls: the editing/paraphrase passes are identical across fab and supported. A packet must not encode whether its claim is fabricated.

## §5. Jaccard set membership (0a.-1.D §4 — reaffirmed)

The criterion-2 Jaccard compares the CLAIM-level cited-source sets (`claim_cited_source_ids`, the distinct canonical_source_ids a claim actually cites), NOT the full packet's `canonical_source_ids`. A packet may contain sources a given claim doesn't cite; two claims in one packet may cite different subsets.

**Anti-gaming derivation (Codex round-1 #5)**: `claim_cited_source_ids` is NOT hand-shaped. It is DERIVED from the rendered claim's actual cited spans / citation annotations (the sources the generated claim genuinely references), then alias-resolved by the canonicalizer (0a.-1.D §2.3), then VALIDATED as a subset of the claim's packet `canonical_source_ids` (a claim cannot cite a source not in its packet). A claim_cited set that is not a subset of the packet is a construction error. This prevents a constructor from inflating/deflating Jaccard by hand-editing the cited list.

The packet-level set is recorded (diagnostics); criterion-2 uses the claim-level set (0a.-1.C §4, relation-builder consumes `claim_cited_source_ids`).

## §6. Definition of done (D7')

Locked: packet definition (non-empty, downselected, manifest unit), curation protocol with provenance-recorded source-selection (gather+source_selection_manifest → admissibility → canonicalize/dedup → downselect → snapshot → manifest), `packet_class` = `domain|evidence_pool_bin|dominant_source_class` (complexity_tier removed — claim-level; canonical serialization; exception-class token; reuse invariant), selection-level label-symmetry (matched-control parity), claim_cited_source_ids derived-from-spans + alias-resolved + subset-validated. Codex §-1.1 APPROVE. Operator sign-off.

## §7. Dependencies + forward notes

- Needs 0a.-1.D (identity/admissibility), D3 (downselect/bins), 0a.-1.B (label-symmetry) — all LOCKED. NOT dependent on D2: `complexity_tier` is claim-level (D2) and is deliberately NOT a `packet_class` component (§3); packet_class is purely packet-level.
- `packet_class` consumed by relation-builder criterion 5 (0a.-1.C §2.1; the builder reads `packet_class` from `source_packet_manifest` per its fail-closed field list).
- Packet snapshots + downselect_manifest recorded in 0a.-1.E custody.
- `dominant_source_class` is computed from the admissibility classifier (0a.-1.D §3.1, pinned classifier version) — deterministic.
