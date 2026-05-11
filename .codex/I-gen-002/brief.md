Brief review for GH#423 Phase 3 — fact_dedup overlap matcher. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Issue context

GH#423 — fact_dedup Phase 3: replace exact-FactSignature grouping (Phase 1) with an overlap-based matcher so semantic duplicates with drifting context numerics get clustered. Per `.codex/I-gen-002/codex_path_quality_brief.md` Codex chose Path A (post-generation dedup, recommended_path A, confidence 0.82). Phases 1+2 shipped earlier (module + integration). Phase 3 swaps the grouping core only — no integration changes.

# Iter-2 P1 RESOLVED — incremental compat-against-growing-target

You caught: `mergeable` checked each compatible cluster against the ORIGINAL target. Two non-target clusters that conflict with each other but both compatible with the original target could both fold in via a candidate bridge.

Fix: replaced the "compute mergeable then merge" pattern with incremental merge against the GROWING target. For each follow-on compatible cluster, the pairwise check tests against `target` as it currently exists (including any clusters already folded in by this candidate). The first conflicting cluster encountered is refused; subsequent ones are checked against the now-extended target.

```python
target = clusters[compat_idx[0]]
target.append(loc)
merged_idx: list[int] = []
for j in compat_idx[1:]:
    if _clusters_pairwise_compatible(target, clusters[j]):
        target.extend(clusters[j])
        merged_idx.append(j)
for j in sorted(merged_idx, reverse=True):
    del clusters[j]
```

# Iter-2 P1 regression test added

`test_build_groups_no_cross_merge_of_mutually_conflicting_clusters` (the exact scenario you described):
- X={1.1%,2.2%, 2014+2016 superset} seeds
- B={3.3%,4.4%, 2014 cohort} seeds (no decimal overlap with X)
- C={5.5%,6.6%, 2016 cohort} seeds (no decimal overlap with X or B)
- D arrives with {3.3%,4.4%,5.5%,6.6%} bridge facts. D's compat list = [B, C]. Incremental: D joins B's cluster, then C is checked against [B,D]: B↔C conflict on years → C rejected.

Final assertion: no group contains both `"2014 cohort"` and `"2016 cohort"` text.

# Test results

```
PYTHONPATH=src pytest tests/polaris_graph/test_fact_dedup.py
47 passed (46 iter-2 baseline + 1 incremental-merge regression)
```

# Acceptance criteria summary (final)

1. `_signatures_overlap(a, b)`: True iff Path 0 exact equality OR top-level conflict guard passes AND (Path 1 ≥2 shared decimals OR Path 2 full-decimal-set match + supporting overlap OR Path 3 ≥2 shared dollar buckets).
2. `build_groups` clusters via transitive overlap subject to per-member compatibility AND pairwise-cluster-compatibility against the growing target on each fold-in.
3. ≥47 unit tests including the year-bridge / dollar-bridge / non-target-cluster-conflict scenarios.
4. No production-code changes outside `src/polaris_graph/generator/fact_dedup.py`.

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
