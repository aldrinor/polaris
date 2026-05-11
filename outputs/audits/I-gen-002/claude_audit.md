# Claude Architect Audit — I-gen-002 Phase 3 (fact_dedup overlap matcher)

## Scope
GH#423 Phase 3 ships the overlap-based grouping core for `fact_dedup`. Phases 1 (module API) and 2 (orchestrator integration) shipped earlier under PRs #425 and #426. This PR changes only `src/polaris_graph/generator/fact_dedup.py` + its tests; no production code outside the module is touched, no integration changes.

## Architecture review

The matcher is a pure-function 5-path classifier on `FactSignature` triples:
- **Path 0 (exact equality)** — preserves legacy "$200 ≡ $200" behavior.
- **Top-level conflict guard** — populated-axis disjointness (year XOR dollar) returns False before any heuristic path runs. Critical for clinical soundness: 3.7% in 2014 vs 3.7% in 2016 are DIFFERENT facts and must not be deduped.
- **Path 1** — ≥2 shared decimals (year drift tolerated for the supporting axes, but the top-level guard blocks the truly conflicting cases).
- **Path 2** — full decimal-set equality + supporting year/dollar overlap, or both sides empty contextual axes.
- **Path 3** — ≥2 shared dollar buckets.

Clustering layer (`build_groups`) is a transitive-closure builder bounded by per-member compatibility + pairwise-cluster compatibility against a growing target. The four invariants:
1. Candidate joins cluster iff it overlaps with ≥1 member AND no member conflicts with it.
2. When candidate bridges multiple clusters, non-target clusters fold into target only if pairwise-compatible with the target's current membership.
3. Cluster ordering inside a group: PRIMARY = first by section_order; redundants = rest.
4. Filter: distinct_sections ≥ 2 (single-section clusters dropped).

## Soundness check vs clinical context (§-1.1 line-by-line standard)

The matcher's soundness target is "no false-positive merge that could conflate two semantically distinct facts." Failure mode that matters in clinical context: a per-claim auditor sees each instance individually VERIFIED but the report-level reader sees two distinct numeric facts merged into one cross-reference, masking either the conflict or one of the two real findings.

The conflict guard architecture protects this: any time two sentences carry both a populated year set AND a populated dollar set, they're tested for disjointness. Disjoint = conflict = no merge. Same logic applies under Path 1 / Path 2 / Path 3 because the guard is at the top.

The contextless-bridge edge case (caught by Codex brief iter 1+2 reviews) was a real soundness gap: a no-context bridge sentence could transitively fuse year-conflicting endpoints via the cluster layer even though direct `_signatures_overlap` would have correctly rejected the endpoint pair. Fixed via `_cluster_is_compatible` (per-member conflict check) and incremental compat-against-growing-target merging (`_clusters_pairwise_compatible`).

## Tests

47 tests in `tests/polaris_graph/test_fact_dedup.py`:
- 25 baseline Phase-1 module API tests.
- 6 Phase-3 iter-1 (overlap matcher positive/negative + Q5 pattern + transitive chain).
- 3 iter-2 (P1-1 same-decimal-diff-year + P1-2 non-vacuous transitive).
- 3 iter-3 (P1 regression — exact-signature equality preserved through Path 0).
- 3 iter-4 (Path 2 conflict-axis guard).
- 3 iter-5 (top-level conflict guard lifted above Path 1 / Path 3 + positive Path 1 case).
- 4 brief-review iterations (3 contextless-bridge regressions + 1 non-target-cluster cross-conflict + 1 conflict-free transitive chain preserved).

All 47 pass. `PYTHONPATH=src pytest tests/polaris_graph/test_fact_dedup.py -q` → `47 passed in 4.58s`.

## Integration verification

This PR does not change any consumer of `fact_dedup`. The Phase-2 orchestrator integration in `src/polaris_graph/generator/multi_section_generator.py` (lines ~3521-3650 around the dedup_pass invocation) and the manifest persistence in `scripts/run_honest_sweep_r3.py` are unchanged. Smoke test path: post-merge run of Q5 sweep is the next step to confirm `n_groups` / `n_redundants` telemetry on production data with the new matcher.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Matcher over-merges (false-positive cluster) → loses a real fact instance | Top-level conflict guard + per-member + pairwise compatibility. 47 tests cover all four match paths and three conflict scenarios. |
| Matcher under-merges (legacy exact match broken) | Path 0 exact-signature fast-path preserves legacy behavior. iter-3 regression test guards this. |
| Rewrite fails strict_verify → original sentence dropped | Phase 2 integration uses safe try/except + strict_verify on rewrites; failures fall back to keeping originals (already shipped in PR #426). |
| Q5 telemetry shows 100% rewrite-strict-verify-failure → no dedup applied | This was observed in PR #426 (16/16 rewrites failed overlap). Phase 3 changes the GROUPING; rewrite-content quality is a separate Phase 4 follow-up. |

## Recommendation

APPROVE. Codex iter 5 of 5 on the diff = APPROVE; Codex iter 3 of 5 on the brief = APPROVE. Both reviewers converged at `accept_remaining` with zero P0 and zero P1 outstanding. Ship.
