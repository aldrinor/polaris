# Claude Architect Audit — I-f2-002 (cluster_labeler)

**Issue:** I-f2-002 — Backend: LLM cluster-labeling per primary entity
**Branch:** bot/I-f2-002
**Diff SHA256:** `b04ace8bb0c21e649f563dc0ab74ecb89cebfe25863e280aebf10b4cf56efc8d`
**LOC:** 192 net (under CHARTER §1 200-cap)
**Local tests:** 6/6 PASS via `python -m pytest tests/polaris_graph/intake/test_cluster_labeler.py -v` (intake suite 37/37)

## Mission compliance

Per Carney v6.2 §F2 ("Modal shows candidate meanings with one-line description per candidate"): the diff adds `label_clusters()` consuming I-f2-001's `ClusterResult` and producing one `LabeledCluster` per non-noise cluster. UI surface (modal) lands at I-f2-004; this is the substrate behind the API at I-f2-003.

## Architecture review

1. **Protocol-based LLM client.** `ClusterLabelClient(Protocol)` decouples this module from the async `OpenRouterClient`. Tests stub with a tiny `FakeClient` (regular class, NOT `unittest.mock` — CLAUDE.md §9.4 forbidden pattern). I-f2-003 will wire the real client via a thin sync adapter (`asyncio.run` per call or persistent loop).

2. **Validation order applied (Codex iter-1 brief P2).** Length check fires BEFORE the `num_clusters == 0` early return. A malformed input where `len(candidate_snippets) != len(cluster_result.labels)` AND `num_clusters == 0` would otherwise return `[]` silently — that violates LAW II ("fail loudly"). Now raises ValueError unconditionally on length mismatch.

3. **LAW II compliance — empty LLM response.** `_truncate_label("")` returns `""`; the explicit `if not label:` raises ValueError. Consumers cannot accidentally render an empty cluster button.

4. **Truncation cap.** ≤ `MAX_LABEL_WORDS` (= 8) words. Defensive against verbose LLM output. Per Carney plan §F2 "one-line description" — 8-word ceiling matches typical UI badge constraints. Module-level constant per CLAUDE.md §9.4 (no magic numbers).

5. **Sample snippet selection.** First `max_snippets_per_cluster` candidates per cluster (default 3). Centroid-distance ordering would require embedding access; out of scope per breakdown. Acceptable: HDBSCAN already groups by density so the first-3 samples within a cluster are mutually consistent.

6. **Sort order determinism.** Output sorted by `cluster_id` ascending via `sorted({…})`. Stable across runs.

7. **No new dependencies.** Uses stdlib `dataclasses` + `typing.Protocol` + I-f2-001's `ClusterResult`. No httpx/asyncio in `src/`; no real model load in tests.

## LAW + invariant checks

- **LAW II (No Fake Working):** zero placeholders, zero mocks in `src/`, fail-loudly on mismatch + empty LLM response. ✓
- **LAW V (Hygiene):** snake_case file + functions; PascalCase only on classes (`LabeledCluster`, `ClusterLabelClient`). ✓
- **LAW VI (Zero Hard-Coding):** `MAX_LABEL_WORDS` is a module constant; `max_snippets_per_cluster` is a parameter with default 3. ✓
- **LAW VII (CLI Isolation):** module is in `src/polaris_graph/intake/`, consumed via standard import. No phase boundary crossed. ✓
- **CHARTER §1 (200 LOC cap):** 192 net. ✓
- **§9.4 (no magic numbers, no `unittest.mock` in `src/`):** ✓
- **§8.4 (resource discipline):** no real ML loads in tests; FakeClient is a regular class returning fixed strings. ✓

## Test plan coverage

| Test | Acceptance criterion (brief §27 #2) |
|---|---|
| `test_labels_one_per_cluster` | 2 clusters of 3 snippets each → 2 labels in cluster_id order |
| `test_no_clusters_returns_empty` | `num_clusters=0` → returns `[]` (after length check passes) |
| `test_mismatched_lengths_raises` | snippets shorter than labels → ValueError |
| `test_empty_llm_response_raises` | FakeClient returns whitespace → ValueError |
| `test_long_label_truncated` | 20-word response → 8-word output |
| `test_skip_noise_label` | cluster_result includes `-1` → output skips noise; non-noise clusters labeled in id order |

All 6 tests pass.

## Out of scope (deferred per breakdown)

- Disambiguation API endpoint → I-f2-003.
- Frontend modal → I-f2-004.
- Real OpenRouter integration test (BPEI 3-cluster ground-truth) → I-f2-003 + Sep 6 evaluator walkthrough.

## Verdict

APPROVE for Codex diff review.
