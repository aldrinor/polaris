# Claude architect audit — I-meta-005 Phase 5 (#989) finding-dedup + relevance-floor

**Verdict: APPROVE (clinical-effective + non-clinical-safe, per Codex scope ruling A).**
Build matches the Codex-APPROVED brief (`.codex/I-meta-005-phase-5/brief.md`, iter 2)
+ build_spec. 15 smoke + 132 regression green; OFF byte-identical.

## Scope reviewed (diff vs base)
- NEW `src/polaris_graph/synthesis/finding_dedup.py` (pure dedup-by-finding +
  corroboration).
- `src/polaris_graph/retrieval/evidence_selector.py` (relevance-floor mode +
  `selection_relevance` sidecar + `parse_relevance_floor`).
- `scripts/run_honest_sweep_r3.py` (PG_USE_FINDING_DEDUP + PG_RELEVANCE_FLOOR + the
  pinned floor→inject→gate→dedup→generator order + manifest).
- `tests/polaris_graph/synthesis/test_finding_dedup_phase5.py` (15 cases).

## Axes (all CLEAN)
- **off_byte_identity_ok** — `relevance_floor=None` → existing tier-balanced
  max_rows path, adds NO new row key (P5-1); `PG_USE_FINDING_DEDUP` default OFF →
  no dedup, manifest key absent. Selector regression m201/m46/m51 = 29 green.
- **no_unique_claim_loss_ok** — CONSERVATIVE-SINGLETON: merge only on known-subject
  + value/unit + all extracted qualifiers equal; unknown subject → per-claim
  singleton; multi-finding row retained if it reps any finding (P5-3, P5-3b).
  Clinical-lethal collapse (same value, different endpoint) verified separate.
- **corroboration_independent_hosts_ok** — counts independent registrable-domains
  via authority/corroboration.py (hosts parsed from URLs, www-stripped); same-domain
  paths → 1 (P5-7); no host literals.
- **no_arbitrary_cap_ok** — floor mode keeps all rows ≥ floor (P5-4: 35 kept, not 20);
  primary trial anchors floor-EXEMPT (a relevant primary RCT never dropped on a low
  lexical score).
- **gate_sees_pre_dedup_ok** — dedup runs AFTER the Phase-3 gate (structurally placed
  right before the generator, after the terminal decision) AND `dedup_by_finding`
  returns shallow copies / never mutates input (`test_p5_purity...`), so the gate's
  corpus is never shrunk. Applies to full-plan AND partial pruned pool (P2-3).
- **money_ok** — pure CPU; no LLM, no network in dedup/selection; `_NoLiveClient`
  not needed since no client is constructed.

## Scope decision (Codex ruling A, 2026-06-01)
`extract_numeric_claims` is empirically clinical-tuned (≤1 claim/row; returns [] for
GDP/emissions/accuracy). Codex ruled A: ship clinical-effective + non-clinical-safe
(non-clinical numerics → safe singletons, no false merge, no corroboration), document
the limitation (DOCUMENTED RESIDUAL 2 in finding_dedup.py), and defer a field-agnostic
extractor to follow-up **#1002**. No unique-claim loss or wrong merge can result.

## Notes for the diff-gate (flagged honestly)
1. **Larger generator pool ON-mode.** Removing the 20-cap means the generator can
   receive more rows (floor + dedup bound it; `PG_MAX_COST_PER_RUN` is the backstop).
   This is the plan's intended "no arbitrary cap" tradeoff. Default floor 0.30.
2. **P5-10 ordering** is covered by the purity test + structural placement (dedup
   after the gate, before the generator) rather than a full-sweep integration test
   (which would need live retrieval / forbidden heavy mocking). Verify the placement.
3. **OFF stamps NO `selection_relevance` key** — stricter than the brief's both-mode
   suggestion, chosen for true OFF byte-identity (dedup only runs ON-mode, which
   always has the key). Confirm this is acceptable.
4. **kg-reuse** (advisory) reads `evidence_for_gen` before the dedup point; the
   generator (the billing consumer) reads the deduped pool. Confirm acceptable.
