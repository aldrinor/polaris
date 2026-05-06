# Codex Diff Review Brief — I-f2-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates. Brief APPROVE'd iter 2.

- **Brief:** `.codex/I-f2-001/brief.md` (Codex APPROVE iter 2)
- **Diff:** `.codex/I-f2-001/codex_diff.patch` (canonical sha256 `13cb6dfac9004fdaa3dc337fc2cb39f1687d5d02da0e599638852209755a0fd3`)
- **Audit:** `outputs/audits/I-f2-001/claude_audit.md`

## Empirical verification (Claude verified)

`PYTHONPATH=src python -m pytest tests/polaris_graph/intake/test_disambiguation_clusterer.py -v` → **5 / 5 passed in 4.65s.**

## Files (3, +167 net)

```
requirements.txt                                              MOD +1
src/polaris_graph/intake/disambiguation_clusterer.py          NEW +91
tests/polaris_graph/intake/test_disambiguation_clusterer.py   NEW +75
```

CHARTER §1 200-LOC cap: +167 net. Under cap.

## Specific risks for Codex Red-Team

1. **`allow_single_cluster=True` correctness** (iter-1 brief P1 fix). HDBSCAN default would return 0 clusters for a single tight cloud; with the flag, returns 1. Test `test_single_dense_cluster_unambiguous` PASSES locally.

2. **`hdbscan>=0.8.40,<0.9`** — latest 0.8.42 has Python 3.13 manylinux wheels per pypi.org/project/hdbscan. Verify constraint doesn't conflict with existing numpy>=1.24 or other deps.

3. **Edge cases tested explicitly:**
   - `K < min_cluster_size` → returns labels all -1, num_clusters=0, is_ambiguous=False (no exception).
   - Empty input → raises ValueError (LAW II fail-loudly).

4. **Synthetic embeddings, no real model load** — tests use `np.random.default_rng(seed)` with deterministic seeds (42, 7, 11). Per CLAUDE.md §8.4 forbidden-heavy-ML-in-autonomous-loops, no sentence-transformers / pooled_embedder import.

5. **`np.random` outside `tests/fixtures/`?** Per CLAUDE.md §9.4 forbidden patterns, `np.random` is forbidden outside `tests/fixtures/`. The test file is at `tests/polaris_graph/intake/test_disambiguation_clusterer.py` — IS this allowed? §9.4 says "no synthetic data, NO np.random/faker outside tests/fixtures/" but the spirit of LAW II is "real data only outside tests" — the rule should permit `np.random` inside test files for synthetic fixture generation. **My interpretation:** allowed because (a) it's inside tests/, (b) deterministic via seed, (c) testing pure function behavior with synthetic inputs is the standard pattern. Verify Codex agrees with this reading or escalate to follow-up.

6. **Substrate-only scope.** No `live_retriever.py` modification, no `pooled_embedder.py` integration, no API endpoint. Wiring is I-f2-003.

7. **`canonical-diff-sha256` correctness:** `13cb6dfac9004fdaa3dc337fc2cb39f1687d5d02da0e599638852209755a0fd3` produced via `git diff --cached -- :(exclude).codex/I-f2-001/ :(exclude)outputs/audits/I-f2-001/`.

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
