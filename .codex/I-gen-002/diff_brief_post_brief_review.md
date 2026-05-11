Diff re-audit after brief-review-driven changes. Output YAML.

HARD ITERATION CAP: 5 per document. This is a fresh diff audit at iter 1 of 5 for the brief-driven code changes. The earlier diff_audit_iter_5 APPROVE applies to the pre-brief-review code state; this audit reviews the additional contextless-bridge fixes Codex requested via the brief review at iter 1 and iter 2.

- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Context

Earlier diff iter-5 APPROVE'd the Path-0/Path-1/Path-2/Path-3 + top-level conflict guard implementation. The follow-up brief review (3 iters, latest APPROVE) surfaced a clustering-layer soundness gap: contextless candidates could bridge year-conflicting clusters even when direct `_signatures_overlap` would have rejected them. Two new helpers + a rewritten merge loop fix this.

# Brief-driven code changes since iter-5 diff APPROVE

1. New `_signatures_conflict(a, b)` helper: populated-axis-conflict check lifted out of `_signatures_overlap` Path 2 so the clustering layer can reuse it.
2. Replaced `_cluster_overlaps` with `_cluster_is_compatible`: requires candidate to overlap with ≥1 member AND not conflict with any member.
3. New `_clusters_pairwise_compatible(a, b)`: no member of a conflicts with any member of b.
4. Rewrote merge loop in `build_groups`: incremental compat-against-growing-target. Each follow-on cluster is checked against `target` as it currently exists.
5. 4 new tests:
   - `test_build_groups_no_contextless_bridge_merge_years` (A 2014, B no-year, C 2016 → A+B cluster, C alone).
   - `test_build_groups_no_contextless_bridge_merge_dollars` (A $40K, B no-$, C $200K → similar).
   - `test_build_groups_no_cross_merge_of_mutually_conflicting_clusters` (D bridges B and C; B and C year-conflict → B and C remain separate).
   - `test_build_groups_transitive_chain_without_conflict_still_merges` (3-chain with no year/dollar conflicts merges as one group).
6. Updated `test_build_groups_three_section_chain_clusters_correctly`: previously used years 2007 / none / 1997 (now correctly rejected as a contextless year bridge). Reframed without years; the original year-bridge scenario is now explicitly covered by test (1) above.

# Test results

```
PYTHONPATH=src pytest tests/polaris_graph/test_fact_dedup.py
47 passed in 4.58s
```

# Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
