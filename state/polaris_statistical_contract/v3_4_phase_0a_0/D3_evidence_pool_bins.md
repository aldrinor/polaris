# D3 — Evidence-Pool-Size Bins (draft for Codex review)

**Deliverable**: Phase 0a.0 / D3 — the evidence-pool-size bins (E1/E2/E3/E4).
**Status**: LOCKED (Codex §-1.1 APPROVE 2026-05-27 "Lock D3" after 3 rounds; pending operator sign-off).
**Parent**: contract v3.3 (evidence-pool is a stratification axis); depends on D1a + 0a.-1.D (packet definition).
**Plan**: `PHASE_0a_0_PLAN.md` (E4 = 41-80, don't lift packet cap — Codex plan round-2 answer 3).
**Codex review**: `.codex/I-safety-001b/codex_d3_review.txt`.
**Version**: 1 (draft)

**Why this exists**: `evidence_pool_bin` (E1-E4) is a stratification axis (0a.-1.C `construction_manifest`, D8 allocation). It is the ORTHOGONAL axis to D2 complexity (D2 §orthogonality): D2 = question difficulty, D3 = how many sources the packet contains. This deliverable locks the bin boundaries + how the bin is assigned + the downselect rule when production retrieval exceeds the packet cap.

---

## §1. Repo grounding (production retrieval depth)

| Setting | Value | Source |
|---|---|---|
| `top_k_per_query` | 50 | `config/settings/thresholds.yaml:106` |
| `max_sources_per_vector` | 300 | `config/settings/sota_parameters.yaml:61` |

Production can retrieve up to 50/query and accumulate up to 300/vector. The D3 packet cap (80, §2) is deliberately BELOW the production ceiling — so a packet is a downselected subset, not the full production retrieval (§3).

## §2. The four evidence-pool bins (locked)

`evidence_pool_bin` is assigned by the **count of admissible distinct sources in the locked packet** (admissible per 0a.-1.D; distinct = distinct `canonical_source_id`; the packet, NOT the full production retrieval):

| Bin | Packet source count |
|---|---|
| E1 | 1-5 |
| E2 | 6-20 |
| E3 | 21-40 |
| E4 | 41-80 |

**Packet cap = 80** (Codex plan round-2 answer 3: do NOT lift the cap — a lifted cap creates a context-handling confound, where a larger packet conflates "more evidence" with "harder to process in-context"). 80 is feasible for SME construction + sits below the production ceiling.

### §2.1 Zero-source = fail-closed construction error (Codex round-1 #1)

A packet with **0 admissible distinct sources is NOT E1 and NOT a new "E0"** — it is a fail-closed construction error. The bin enum is exactly {E1, E2, E3, E4}; a 0-source packet cannot be assigned a bin and the claim CANNOT enter the gold set. It is reconstructed/replaced per 0a.-1.E §8 before construction proceeds. Rationale: a fabricated claim with no admissible cited evidence breaks label-symmetric packet construction (0a.-1.B §3) and hands the adjudicator an obvious no-evidence tell. The 0a.-1.C `source_packet_manifest` schema is amended (§6) to require `minItems: 1` on `canonical_source_ids`.

## §3. Downselect rule (when production retrieval > 80 — Codex plan round-2 answer 3)

If the production retrieval for a scenario returns more than the target packet size:
- Record `retrieved_source_count` (the full production count) SEPARATELY in the construction metadata — the gap between "what production found" and "what the packet contains" is auditable.
- Record `target_packet_source_count` (the N to downselect to, ≤80) BEFORE downselect (Codex round-1 #2 — N must not be implicit; it is a pre-registered/recorded design choice per scenario, e.g. 60, capped at 80).
- DOWNSELECT to the target via a deterministic **rank tuple** (NOT ad-hoc): order admissible sources by `(scope-template authority/tier priority ASC, pinned authority_score DESC, canonical_source_id lexical ASC)`; missing/NaN authority_score is fail-closed (the source is rejected, not silently ordered). Take the top `target_packet_source_count`. The selected set is the packet; its size sets `evidence_pool_bin`.
- **Downselect manifest (Codex round-1 #2)**: hashing the rule + seed alone is insufficient. The full pre-downselect input universe is pinned in a `downselect_manifest`: every candidate's `canonical_source_id`, admissibility class/tier, the authority inputs used for ranking, a `selected|dropped` flag, the `target_packet_source_count`, and the downselect-code hash. This lets an auditor reproduce WHICH sources were dropped, not just that some were. Stored under 0a.-1.E custody.

`retrieved_source_count` is a DIAGNOSTIC field (records production reality); `evidence_pool_bin` is set by the PACKET (downselected) size (≤80). Distinct: a scenario with `retrieved_source_count=250`, `target_packet_source_count=60` → 60-source packet → `E4`, with both counts + the downselect_manifest recorded.

## §4. Orthogonality (locked)

- **D3 (evidence-pool) ≠ D2 (complexity)**: a C1 lookup can have an E4 packet (many sources, easy question); a C3 cross-jurisdiction synthesis can have an E1 packet (few sources, hard question). They are independent stratification axes (D2 §orthogonality).
- **Bin assigned from the PACKET, not the question**: unlike D2 (assigned pre-retrieval from the question), D3's bin is set by the constructed packet's source count. This is a packet property, recorded at construction.

## §5. Definition of done (D3)

Locked: 4 bins (E1 1-5 / E2 6-20 / E3 21-40 / E4 41-80), zero-source fail-closed (§2.1), packet cap 80 (not lifted), downselect rule (record retrieved_source_count + target_packet_source_count separately + deterministic rank-tuple downselect + full downselect_manifest, hash-pinned), bin assigned from packet distinct-admissible-source count, orthogonality with D2. Codex §-1.1 APPROVE. Operator sign-off.

## §6. Schema + custody addendum (APPLIED with D3)

Per Codex round-1 #3, D3 requires concrete schema + custody edits (not just a forward note), because `construction_manifest.schema.json` has `additionalProperties: false`:

- **`construction_manifest.schema.json`**: add optional `retrieved_source_count` (int ≥0) + `target_packet_source_count` (int 1-80). Both STRUCTURAL (pre-outcome production-retrieval counts; not label-derived) — added to 0a.-1.E §6 structural-exposure list.
- **`source_packet_manifest.schema.json`**: add `minItems: 1` to `canonical_source_ids` (enforces §2.1 zero-source fail-closed at the schema level).
- These edits are applied in this commit (the schema files exist post-0a.-1.C code half).

## §7. Dependencies + forward notes

- Needs D1a + 0a.-1.D (admissibility + canonical_source_id for "distinct admissible source"). Independent of D2.
- `evidence_pool_bin` enum {E1,E2,E3,E4} consumed by `construction_manifest` (0a.-1.C §1.1 forward placeholder) + D8 allocation.
- `retrieved_source_count` + `target_packet_source_count` are STRUCTURAL diagnostic fields (per §6); added to 0a.-1.E §6 structural-exposure handling.
- Downselect rule + child seed + `downselect_manifest` recorded in 0a.-1.E custody.
