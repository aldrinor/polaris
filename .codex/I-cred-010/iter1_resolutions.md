## 8. ITER-1 RESOLUTIONS (binding amendments to §2/§3/§4 — all implemented)

Brief iter-1 AND diff iter-1 both returned REQUEST_CHANGES; all findings addressed:

- **MINORITY-TARGETING (brief P1) — the core fix.** A `ContradictionEdge`'s `claim_cluster_ids` are SORTED,
  not stance/weight-ordered, so the builder CANNOT identify the minority from the edge alone (generic
  "contrary" queries could reinforce the majority). `build_dissent_queries` now takes a 3rd input
  **`weight_by_cluster`** (Phase-6 `weight_mass` per cluster — accepts a dict OR a list of ClaimWeightMass).
  The MINORITY = the edge's cluster with the **LOWEST** `weight_mass` (ties + unknown-weight broken
  deterministically by cluster_id; unknown treated as 0.0 = under-evidenced); the builder seeks evidence
  FOR that minority cluster's ASSERTION (its claim text). Regressions:
  `test_targets_minority_side_assertion` (queries derive from the minority's "no effect", NOT the majority's
  "reduced") + `test_minority_flips_when_weights_flip`.
- **ZERO/NEGATIVE CAP (diff P1).** `max_queries <= 0` (direct or via `PG_DISSENT_QUERIES_MAX=0`) now returns
  `[]` BEFORE any append (spend/recall control). Regression in `test_max_queries_cap_and_zero`.
- **LAW VI (diff P2).** The assertion truncation length is now `PG_DISSENT_ASSERTION_CHARS` (default 120),
  not a hardcoded literal. The `Any` import is now used (`weight_by_cluster` typing + `_coerce_weight_map`).
- **Deferred (confirmed):** `live_retriever`/`saturation` wiring + dissent-seed fallback eligibility remain
  scoped to I-cred-010b.

SMOKE after these amendments: 15 passed.
