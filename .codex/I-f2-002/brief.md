# Codex Brief Review — I-f2-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-002 — Backend: LLM cluster-labeling per primary entity
**Phase:** 1 / **Feature:** F2 (disambiguation modal)
**LOC budget:** 130 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Add `src/polaris_graph/intake/cluster_labeler.py` — given a list of candidate-text-snippets-grouped-by-cluster (from I-f2-001's ClusterResult), call an LLM to produce a one-line label per cluster naming the primary entity. Example: BPEI clusters → 3 labels: "syndrome", "institute", "chemical".

Per Carney v6.2 §F2: "Modal shows candidate meanings with one-line description per candidate."

## Substrate (HONEST)

- `src/polaris_graph/llm/openrouter_client.py` exists with `OpenRouterClient` (async, httpx-based; calls Qwen 3.5 Plus via OpenRouter). Family-segregation rule (CLAUDE.md §9.1) is for generator/evaluator pairing, not relevant here.
- I-f2-001 just merged: `disambiguation_clusterer.py` returns `ClusterResult(labels, num_clusters, is_ambiguous)`.
- This module consumes the cluster output, fetches the candidate snippets per cluster, calls the LLM with a structured prompt, and returns a parallel list of labels.

## Acceptance criteria (binding)

1. **`src/polaris_graph/intake/cluster_labeler.py`** (NEW): exports:
   ```python
   @dataclass(frozen=True)
   class LabeledCluster:
       cluster_id: int       # HDBSCAN cluster id (>= 0; -1 noise excluded)
       label: str            # one-line entity description, e.g. "syndrome", "institute"
       sample_snippets: list[str]  # up to 3 snippets used for labeling

   class ClusterLabelClient(Protocol):
       def complete(self, prompt: str, *, max_tokens: int = 50) -> str: ...

   def label_clusters(
       cluster_result: ClusterResult,
       candidate_snippets: list[str],
       client: ClusterLabelClient,
       max_snippets_per_cluster: int = 3,
   ) -> list[LabeledCluster]:
       ...
   ```
   - For each non-noise cluster: take up to `max_snippets_per_cluster` snippets; build a prompt asking "what entity is described by these snippets? Reply with one short noun phrase only"; call `client.complete()`; trim to ≤8 words.
   - Returns labels in cluster_id ascending order.
   - Empty cluster_result (num_clusters == 0) → returns [].
   - Mismatched lengths (`len(candidate_snippets) != len(cluster_result.labels)`) → raises ValueError (LAW II).
   - Bad LLM response (empty string after strip) → raises ValueError ("LLM returned empty label").
   - LOC: ~80.

2. **`tests/polaris_graph/intake/test_cluster_labeler.py`** (NEW): unit tests with a `FakeClient` (test fixture) that returns fixed strings. Tests:
   - `test_labels_one_per_cluster`: 2 clusters of 3 snippets each → 2 labels in cluster_id order.
   - `test_no_clusters_returns_empty`: `ClusterResult(labels=[-1,-1], num_clusters=0, ...)` → returns [].
   - `test_mismatched_lengths_raises`: snippets list shorter than labels → raises ValueError.
   - `test_empty_llm_response_raises`: FakeClient returns "" → raises ValueError.
   - `test_long_label_truncated`: FakeClient returns 20-word label → truncated to ≤8 words.
   - `test_skip_noise_label`: cluster_result includes label=-1; output skips it, returns labels only for non-noise clusters.
   - LOC: ~50.

## Planned diff shape

```
src/polaris_graph/intake/cluster_labeler.py            NEW +85
tests/polaris_graph/intake/test_cluster_labeler.py     NEW +55
```

LOC: +140 net. Slightly over 130 budget but under CHARTER §1 200-cap.

## Out of scope (deferred per breakdown)

- Disambiguation API endpoint → I-f2-003.
- Frontend modal → I-f2-004.

## Non-acceptance / explicit exclusions

- Does NOT call the real OpenRouter API in tests (uses FakeClient stub).
- Does NOT call any embedding model.
- Does NOT depend on `OpenRouterClient` directly — uses `Protocol` interface so tests stub easily and integration (I-f2-003) wires up the real client with a thin adapter.
- Does NOT require `async`. Protocol uses sync `complete()`. The integration adapter at I-f2-003 wraps async OpenRouterClient with `asyncio.run` or maintains a thread-bound event loop.

## Risks for Codex Red-Team

1. **Protocol-vs-concrete-client trade-off.** Using `Protocol` keeps this module unit-testable without httpx + API key. Integration (I-f2-003) wires the real client. Acceptable separation of concerns.

2. **Sync `complete()` vs async OpenRouterClient.** OpenRouterClient is async. The adapter layer in I-f2-003 will run the async call (e.g., via `asyncio.run` per-request, or via a persistent event loop). For this Issue, sync Protocol is the test-friendly choice.

3. **Label truncation to ≤8 words.** Defensive against verbose LLM output. Per Carney plan §F2: "one-line description." 8-word ceiling matches typical UI badge constraints; ratchet later if needed.

4. **Empty response → ValueError.** LAW II: fail loudly. An empty LLM label should not silently render an empty UI.

5. **Sample snippet selection.** Currently FIRST `max_snippets_per_cluster` candidates per cluster. Could improve via centroid-distance ordering, but that requires embeddings — out of scope. Documented in docstring.

6. **No mocking of `OpenRouterClient.complete()` directly** — Protocol means tests build a tiny `FakeClient` class. Per CLAUDE.md §9.4 forbidden patterns: `unittest.mock` is banned in `src/`; this Issue's tests don't use it (FakeClient is a regular class).

7. **Real-data integration BPEI test deferred.** The breakdown spec says "BPEI clusters → 3 labels: syndrome, institute, chemical." That's an integration test against the real LLM — deferred to I-f2-003 (API endpoint test) or evaluator walkthrough at Sep 6. THIS Issue's unit tests stub LLM responses.

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
