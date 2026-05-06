# Claude architect self-audit — I-f2-001

**Issue:** I-f2-001 — Backend HDBSCAN clustering on top-K retrieval candidates (F2)
**Brief:** `.codex/I-f2-001/brief.md` (Codex APPROVE iter 2)
**Diff:** `.codex/I-f2-001/codex_diff.patch` (canonical sha256 `13cb6dfac9004fdaa3dc337fc2cb39f1687d5d02da0e599638852209755a0fd3`)

## What the diff does

1. **`requirements.txt`** (MOD +1): adds `hdbscan>=0.8.40,<0.9` (pure-Python + C extension; Python 3.13 manylinux wheels available).
2. **`src/polaris_graph/intake/disambiguation_clusterer.py`** (NEW +91): exports `cluster_candidates(embeddings, min_cluster_size=2) → ClusterResult`. Wraps `hdbscan.HDBSCAN(min_cluster_size, metric="euclidean", allow_single_cluster=True)`. `allow_single_cluster=True` is critical so a tightly-packed candidate set returns 1 cluster rather than 0 (P1-iter1 fix). Edge cases: K < min_cluster_size → labels all -1, num_clusters=0; empty input → ValueError (LAW II fail-loudly).
3. **`tests/polaris_graph/intake/test_disambiguation_clusterer.py`** (NEW +75): 5 tests via synthetic `np.random.default_rng(seed)` Gaussian clouds. **All 5 PASS in 4.65s** (verified locally with hdbscan installed).

## Empirical verification

`PYTHONPATH=src python -m pytest tests/polaris_graph/intake/test_disambiguation_clusterer.py -v`:

```
test_three_clear_clusters_ambiguous PASSED
test_single_dense_cluster_unambiguous PASSED
test_two_clusters_ambiguous PASSED
test_below_min_cluster_size_returns_noise PASSED
test_empty_input_raises PASSED

============================== 5 passed in 4.65s ==============================
```

## LOC

```
requirements.txt                                              MOD +1
src/polaris_graph/intake/disambiguation_clusterer.py          NEW +91
tests/polaris_graph/intake/test_disambiguation_clusterer.py   NEW +75
```

**Total: +167 net.** Under 180 issue-budget AND CHARTER §1 200-cap.

## Iter trajectory

- Brief iter 1: 1 P1 (HDBSCAN default `allow_single_cluster=False` makes single-dense-cluster test impossible) + 1 P2 (hdbscan version 0.8.42 latest, not 0.8.40).
- Brief iter 2: APPROVE.
- Diff: not yet reviewed.

Codex's empirical pypi.org + readthedocs.io check caught a real API contract issue before code was written. Test would have failed at runtime; iter-2 fix added `allow_single_cluster=True`.

## Risks acknowledged

- **`min_cluster_size=2`** is unusually aggressive; per Carney v6.2 §F2 spec.
- **Synthetic embeddings** in tests are 2-D for visualization clarity; production embeddings will be 384-D or higher. Module accepts any (K, D) shape.
- **No spaCy / NER dependency** — this Issue is pure clustering on numeric arrays.
- **Wiring deferred to I-f2-003.** This Issue is substrate-only.
- **Pre-condition documented in module docstring:** embeddings should be L2-normalized for euclidean metric to be monotonic with cosine.

## What this Issue does NOT do

- Does NOT call any embedding model.
- Does NOT modify `live_retriever.py` (I-f2-003).
- Does NOT label clusters (I-f2-002 will do `cluster_labeler.py`).
- Does NOT add disambiguation API endpoint (I-f2-003).
- Does NOT add frontend modal (I-f2-004).

## Output schema for Codex review

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
