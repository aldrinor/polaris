# Claude architect audit — PR2 query decomposition (#951 q1d-a, the S0)

## What this fixes (pre-Q1 build step 2 — the highest-leverage depth gap)
Codex-verified S0: 4 of 5 golden benchmark questions ship with no hand-authored `amplified` query list,
so a 40-70-word multi-clause paragraph was fired as ~one keyword query (Q76 ≈ 5 sub-questions in one).
Keyword engines retrieve poorly on long paragraphs → low lane-2 coverage → POLARIS could fail a golden
question at 100% faithfulness. Lands on PR1's rerank+reservation base (#959) so the new sub-queries
survive into the corpus rather than being truncated by arrival order.

## Design (both Codex gates APPROVE; diff iter 3)
- **`src/polaris_graph/retrieval/query_decomposer.py`** — pure, NO network / NO LLM:
  - `decompose_question(question, max_subqueries=6)`: split on sentence terminators / `;` / enumerators /
    safe top-level connectives (` and `, ` as well as `, ` versus `, ` vs `). NEVER on bare commas.
  - Conjunction/`versus` splits require BOTH sides ≥4 content words, so compounds ("type 2 diabetes",
    "non-small cell lung cancer") are preserved by construction.
  - **Protected-compound guard** (Codex diff iter-1): an additive `and`/`as well as` flanked by a
    protected clinical pair ("safety and efficacy", "signs and symptoms", "risks and benefits",
    "morbidity and mortality", "sensitivity and specificity", …) is NOT split — but comparators
    ("safety versus efficacy") ARE (additive-only scope, Codex diff iter-2 P2).
  - **Abbreviation protection** (Codex diff iter-1/iter-2): `vs.` normalized to `vs`; `e.g./i.e./etc./
    et al./fig./no./approx./ca.` internal periods masked CASE-INSENSITIVELY (preserving casing) so
    "E.g."/"Fig." at a clause start aren't split at their period; unmasked per clause.
  - Fragment filter (≥3 content words), case-insensitive dedup, cap, `[]` for a short single-clause Q.
  - `build_amplified_query_list(*, hand_authored, decomposed, regulatory, trial)`: deterministic prepend
    order + case-insensitive dedup; the anchor full question is NEVER added (run_live_retrieval seeds it).
- **Wiring** (`run_honest_sweep_r3.py`): flag `PG_SWEEP_QUERY_DECOMPOSE` (default "1"); builds
  `_amplified_effective` via the pure helper. Sub-queries pass the same `validate_amplified_queries`
  scope gate as hand-authored ones.

## Verification (offline, no spend)
- 14 tests (`tests/polaris_graph/test_query_decomposer.py`) PASS, incl. all Codex edge cases: multi-clause
  → multiple sub-queries; "safety and efficacy" preserved (short AND long clause); "type 2 diabetes" /
  "non-small cell lung cancer" preserved; no bare-comma split; `vs.` short not split / long split;
  capitalized "E.g."/"Fig." protected; long "safety versus efficacy" comparator IS split; dedup + cap +
  determinism; list-builder order/dedup.
- `verify_lock --consistency` OK. Both Codex gates APPROVE (brief re-gate; diff iter 3).
- Frozen/untouched: strict_verify / provenance_generator / D8 / runtime lock / evidence_selector / the 5
  PR-10 contracts. This only adds INPUT sub-queries; verification semantics unchanged.

## Clinical-safety note
Conservative by design — errs toward NOT splitting (protected compounds, ≥4 guard, no bare-comma). A
mis-decomposition can only add a (scope-validated) search query; it cannot affect what strict_verify
accepts. The anchor full question is always seeded separately.
