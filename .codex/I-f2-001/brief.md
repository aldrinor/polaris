# Codex Brief Review — I-f2-001 (ITER 2 of 5)

## Iter-1 fixes
- **P1: HDBSCAN default `allow_single_cluster=False`** — single-dense-cluster test would return `num_clusters=0` not `1`. Iter-2 fix: pass `allow_single_cluster=True` to HDBSCAN constructor. Per https://hdbscan.readthedocs.io/en/latest/api.html.
- **P2: hdbscan latest is 0.8.42 (Mar 2026), not 0.8.40.** Iter-2 fix: pin `hdbscan>=0.8.40,<0.9` (lower-bound 0.8.40 still safe; upper bound prevents accidental 0.9.x breakage). Wording corrected.

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-001 — Backend: HDBSCAN clustering on top-K retrieval candidates
**Phase:** 1 / **Feature:** F2 (disambiguation modal)
**LOC budget:** 180 net per `state/polaris_restart/issue_breakdown.md`. **CHARTER §1 hard cap: 200.**

## Mission

Add `src/polaris_graph/intake/disambiguation_clusterer.py` — a pure-Python module that takes top-K candidate embeddings and returns HDBSCAN cluster labels. >1 cluster = ambiguous query (BPEI = syndrome / institute / chemical → 3 clusters). 1 dense cluster = unambiguous (tirzepatide → all candidates about the drug → 1 cluster).

Per Carney plan §F2: "Diversify-then-Verify pipeline (Agentic Verification, ICLR 2025); HDBSCAN clustering on candidate embeddings."

## Substrate (HONEST)

- `src/polaris_graph/intake/__init__.py` exists with `question_normalizer` (slice 001).
- `numpy>=1.24` already in `requirements.txt` (line 111). **`hdbscan` is NOT in requirements.txt.** Must add.
- `pooled_embedder.py` exists at `src/polaris_graph/retrieval/`; this Issue does NOT call it (test-isolated; consumes pre-computed embedding arrays).
- This Issue is substrate ONLY. Wiring into `live_retriever.py` is I-f2-003 scope.
- F2 substrate per Carney plan §F2 also flags spaCy NOT installed; this module does NOT need spaCy (operates on numeric embeddings only).

## Acceptance criteria (binding)

1. **`src/polaris_graph/intake/disambiguation_clusterer.py`** (NEW): exports `cluster_candidates(embeddings: np.ndarray, min_cluster_size: int = 2) -> ClusterResult` where:
   - `embeddings` is shape `(K, D)` array of floats (K candidates, D embedding dim).
   - Returns `ClusterResult` dataclass with `labels: list[int]` (HDBSCAN cluster id per candidate; -1 = noise/outlier per HDBSCAN convention), `num_clusters: int` (count of distinct non-noise labels), `is_ambiguous: bool` (= num_clusters > 1).
   - Wraps `hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean", allow_single_cluster=True)` from the `hdbscan` package. `allow_single_cluster=True` is required so a tightly-packed candidate set returns 1 cluster rather than 0 (P1-iter1 fix).
   - Edge case: K < min_cluster_size → `num_clusters=0`, `is_ambiguous=False`, all labels = -1 (no clustering possible). Document this in the docstring.
   - Edge case: empty input array → raises `ValueError` (LAW II — fail loudly).
   - LOC: ~70-90 (module + dataclass + docstring).

2. **`tests/polaris_graph/intake/test_disambiguation_clusterer.py`** (NEW): unit tests using **synthetic numpy arrays** (no real embedding model load — keeps test fast + GPU-free per CLAUDE.md §8.4 "no heavy ML in autonomous loops"):
   - `test_three_clear_clusters`: 3 well-separated point clouds (e.g. center [0,0], [10,10], [-10,-10] each ×5 with small Gaussian noise) → `num_clusters == 3`, `is_ambiguous == True`.
   - `test_single_dense_cluster`: 1 tight cloud of 10 points around [0,0] → `num_clusters == 1`, `is_ambiguous == False`.
   - `test_below_min_cluster_size`: 1 point → `num_clusters == 0`, `is_ambiguous == False`, labels `[-1]`.
   - `test_empty_input_raises`: `np.empty((0, 384))` → raises ValueError.
   - `test_two_clusters_ambiguous`: 2 separated point clouds → `num_clusters == 2`, `is_ambiguous == True`.
   - LOC: ~80.

3. **`requirements.txt`**: add `hdbscan>=0.8.40,<0.9` (stable Python 3.13-compatible range; latest 0.8.42 released Mar 2026 per pypi.org/project/hdbscan; pure-Python + C extension; no GPU dep).
   - Verify build works on Linux CI (hdbscan has C extensions; pip-install needs gcc — already present in `web_ci.yml` Python step).
   - LOC: +1.

## Planned diff shape

```
src/polaris_graph/intake/disambiguation_clusterer.py    NEW +85
tests/polaris_graph/intake/test_disambiguation_clusterer.py    NEW +80
requirements.txt                                         MOD +1
```

LOC: +166 net. Under 180 issue-budget AND CHARTER §1 200-cap.

## Out of scope (deferred per breakdown)

- LLM cluster-labeling (assigning "syndrome" / "institute" / "chemical" labels) → I-f2-002.
- Disambiguation API endpoint exposing cluster results → I-f2-003.
- Frontend modal → I-f2-004.

## Non-acceptance / explicit exclusions

- Does NOT call any embedding model at runtime (test-isolated; consumes pre-computed `np.ndarray`).
- Does NOT add spaCy or any NER tool.
- Does NOT depend on `pooled_embedder.py` (called by future Issue at integration time).
- Does NOT modify `live_retriever.py` (that's I-f2-003).
- Does NOT modify `question_normalizer.py`.

## Risks for Codex Red-Team

1. **`hdbscan` package install failures.** hdbscan 0.8.x ships C extensions (Cython); on Windows requires MSVC build tools, on Linux requires gcc. Both present in standard dev/CI environments. Pinned `>=0.8.40` is the latest stable per pypi.org/project/hdbscan as of 2026-05-06; this version supports Python 3.13. Verify the version constraint doesn't conflict with numpy>=1.24 already in requirements.

2. **`min_cluster_size=2` semantics.** HDBSCAN with `min_cluster_size=2` is unusually aggressive — it'll form clusters around any 2+ close points. The breakdown spec explicitly calls for `min_cluster_size=2` (default). Documented + asserted in tests.

3. **Noise-label convention (-1).** HDBSCAN labels outlier points as -1 (not part of any cluster). `num_clusters` excludes -1 from the count: `len(set(labels) - {-1})`. Edge case: ALL points are noise → `num_clusters == 0`, `is_ambiguous == False`. Acceptable.

4. **`euclidean` metric for normalized embeddings.** Most modern embedding models output L2-normalized vectors. Euclidean distance on normalized vectors is monotonic with cosine distance, so clustering quality is equivalent. Pre-condition documented in module docstring: "embeddings should be L2-normalized for best results."

5. **Synthetic test fixtures use `np.random.default_rng(seed)` for determinism.** Per CLAUDE.md §9.4, `np.random` is forbidden outside tests/fixtures/. Tests file explicitly sets seeded RNG within each test body — deterministic, reproducible, lint-clean for the LAW.

6. **Test must NOT load any real embedding model.** Per CLAUDE.md §8.4: "Heavy ML / vector / CUDA processes are forbidden in autonomous loops." Tests use synthetic numpy arrays only. No `sentence-transformers`, no `pooled_embedder` import.

7. **`tests/polaris_graph/intake/__init__.py`** — does it exist? Check before writing the test file. If not, create an empty `__init__.py` to make pytest discovery work. Adds 1 file but 0 LOC (empty marker).

## Output schema (mandatory)

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
