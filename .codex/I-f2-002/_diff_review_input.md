# Codex Diff Review — I-f2-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-002 — Backend: LLM cluster-labeling per primary entity
**Branch:** bot/I-f2-002
**Brief verdict (iter 1):** APPROVE (1 P2: validation-order — applied in this diff)
**Canonical-diff-sha256:** `b04ace8bb0c21e649f563dc0ab74ecb89cebfe25863e280aebf10b4cf56efc8d`
**LOC:** 192 net (CHARTER §1 hard cap 200)
**Local tests:** 6/6 PASS

## Files

```
src/polaris_graph/intake/cluster_labeler.py        NEW +89
tests/polaris_graph/intake/test_cluster_labeler.py NEW +103
```

## What changed

`label_clusters(cluster_result, candidate_snippets, client, max_snippets_per_cluster=3) -> list[LabeledCluster]`:

1. Validation order (Codex brief iter-1 P2 fix): `len(candidate_snippets) != len(cluster_result.labels)` raises ValueError BEFORE the `num_clusters == 0` early return.
2. `num_clusters == 0` → return `[]`.
3. For each non-noise cluster id (sorted ascending): take first `max_snippets_per_cluster` snippets, build a prompt asking for a noun phrase, call `client.complete()`, truncate to ≤ `MAX_LABEL_WORDS` words.
4. Empty post-strip label → raise ValueError ("LLM returned empty label").
5. Returns list[LabeledCluster] sorted by cluster_id.

`ClusterLabelClient(Protocol)`: sync `complete(prompt, *, max_tokens=50) -> str`. Tests stub with regular `FakeClient` class (no `unittest.mock` in `src/` per CLAUDE.md §9.4).

## Tests (`test_cluster_labeler.py`)

1. `test_labels_one_per_cluster` — 2 clusters of 3 snippets each → labels in id order.
2. `test_no_clusters_returns_empty` — `num_clusters=0` + matching-length snippets → `[]`, zero LLM calls.
3. `test_mismatched_lengths_raises` — snippets shorter than labels → ValueError ("does not match").
4. `test_empty_llm_response_raises` — FakeClient returns "   " → ValueError ("empty label").
5. `test_long_label_truncated` — 20-word LLM response → 8-word output (`MAX_LABEL_WORDS`).
6. `test_skip_noise_label` — `labels=[-1, 0, 0, -1, 1, 1]` → output `[id=0, id=1]`; noise excluded; sample_snippets contain only non-noise positions.

All 6 pass; intake suite 37/37 pass.

## Risks for Codex Red-Team

1. **Validation order.** Length check FIRST (raises) → empty-cluster early return SECOND. Confirmed in diff lines 56-65 of `cluster_labeler.py`. Brief iter-1 P2 satisfied.

2. **Noise handling.** `set(labels) - {-1}` then `sorted(...)` → distinct cluster ids in ascending order. Cluster id `-1` (HDBSCAN noise) is NEVER labeled. Test `test_skip_noise_label` exercises this with mixed `[-1, 0, 0, -1, 1, 1]`.

3. **Async-vs-sync Protocol.** `ClusterLabelClient.complete()` is sync. The real `OpenRouterClient.complete()` is async. Adapter layer at I-f2-003 will bridge (per-request `asyncio.run` or shared event loop). NOT this Issue's concern; brief explicitly defers.

4. **Sample-ordering determinism.** First `max_snippets_per_cluster` snippets in original order (insertion order preserved since we iterate `enumerate(cluster_result.labels)`). Same input → same output. Acceptable for unit-level guarantees.

5. **`_truncate_label` empty-input behavior.** `"   ".strip().split()` → `[]` → `" ".join([]) == ""` → `if not label:` triggers ValueError. Confirmed via `test_empty_llm_response_raises`.

6. **No `unittest.mock` in `src/`.** Confirmed by grep: only `from typing import Protocol`, `from dataclasses import dataclass`. Test file uses `FakeClient` regular class.

7. **No new external deps.** `requirements.txt` not modified. `hdbscan` was already added in I-f2-001.

8. **CHARTER §1 LOC cap.** 192 net additions; well under 200.

9. **CLAUDE.md §9.4 hygiene.** No `try: ... except: pass`; no `time.sleep()`; no `# TODO` / `pass` body; no magic numbers (8 → `MAX_LABEL_WORDS`); no live-DB mocking (no DB in this module).

10. **Determinism in `sorted({...})`.** Sets are unordered but `sorted()` produces deterministic int order. Output stable across Python versions.

## Out of scope (do NOT regress on these)

- Real OpenRouter wiring → I-f2-003.
- Frontend modal rendering → I-f2-004.
- BPEI 3-cluster integration ground-truth → evaluator walkthrough Sep 6.

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


## Diff to review

```diff
diff --git a/src/polaris_graph/intake/cluster_labeler.py b/src/polaris_graph/intake/cluster_labeler.py
new file mode 100644
index 0000000..26b2c15
--- /dev/null
+++ b/src/polaris_graph/intake/cluster_labeler.py
@@ -0,0 +1,89 @@
+"""LLM cluster-labeling per primary entity (F2 substrate, I-f2-002).
+
+Given disambiguation clusters from `cluster_candidates` (I-f2-001),
+ask an LLM for a one-line label per cluster naming the primary entity
+(e.g. BPEI → syndrome / institute / chemical). Uses a Protocol so unit
+tests stub without httpx + API key; integration adapter wires the real
+OpenRouter client at I-f2-003.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Protocol
+
+from polaris_graph.intake.disambiguation_clusterer import ClusterResult
+
+MAX_LABEL_WORDS = 8
+
+
+@dataclass(frozen=True)
+class LabeledCluster:
+    cluster_id: int
+    label: str
+    sample_snippets: list[str]
+
+
+class ClusterLabelClient(Protocol):
+    def complete(self, prompt: str, *, max_tokens: int = 50) -> str: ...
+
+
+def _truncate_label(text: str) -> str:
+    words = text.strip().split()
+    if len(words) > MAX_LABEL_WORDS:
+        words = words[:MAX_LABEL_WORDS]
+    return " ".join(words)
+
+
+def _build_prompt(snippets: list[str]) -> str:
+    snippet_block = "\n".join(f"- {s}" for s in snippets)
+    return (
+        "What entity is described by these snippets? "
+        "Reply with ONE short noun phrase only (≤ 8 words). "
+        "No quotes, no explanation, no trailing punctuation.\n\n"
+        f"{snippet_block}"
+    )
+
+
+def label_clusters(
+    cluster_result: ClusterResult,
+    candidate_snippets: list[str],
+    client: ClusterLabelClient,
+    max_snippets_per_cluster: int = 3,
+) -> list[LabeledCluster]:
+    """Generate a one-line label per non-noise cluster.
+
+    Validation order (per Codex iter-1 brief P2): length-mismatch check
+    fires BEFORE the num_clusters == 0 early return so malformed
+    all-noise inputs do not silently slip through (LAW II).
+    """
+    if len(candidate_snippets) != len(cluster_result.labels):
+        raise ValueError(
+            f"label_clusters: candidate_snippets length ({len(candidate_snippets)}) "
+            f"does not match cluster_result.labels ({len(cluster_result.labels)})"
+        )
+    if cluster_result.num_clusters == 0:
+        return []
+
+    distinct_ids = sorted({lbl for lbl in cluster_result.labels if lbl != -1})
+    out: list[LabeledCluster] = []
+    for cid in distinct_ids:
+        snippets_for_cluster = [
+            candidate_snippets[i]
+            for i, lbl in enumerate(cluster_result.labels)
+            if lbl == cid
+        ][:max_snippets_per_cluster]
+        raw = client.complete(_build_prompt(snippets_for_cluster))
+        label = _truncate_label(raw)
+        if not label:
+            raise ValueError(
+                f"label_clusters: LLM returned empty label for cluster {cid}"
+            )
+        out.append(
+            LabeledCluster(
+                cluster_id=cid,
+                label=label,
+                sample_snippets=snippets_for_cluster,
+            )
+        )
+    return out
diff --git a/tests/polaris_graph/intake/test_cluster_labeler.py b/tests/polaris_graph/intake/test_cluster_labeler.py
new file mode 100644
index 0000000..511dfb2
--- /dev/null
+++ b/tests/polaris_graph/intake/test_cluster_labeler.py
@@ -0,0 +1,103 @@
+"""Unit tests for I-f2-002 — cluster_labeler.
+
+Uses a FakeClient stub (regular class, NOT unittest.mock per CLAUDE.md §9.4)
+so tests do not require httpx + API key.
+"""
+
+from __future__ import annotations
+
+import pytest
+
+from polaris_graph.intake.cluster_labeler import (
+    LabeledCluster,
+    label_clusters,
+)
+from polaris_graph.intake.disambiguation_clusterer import ClusterResult
+
+
+class FakeClient:
+    """Minimal sync LLM stub returning a fixed string per call.
+
+    `responses` is consumed in order; if exhausted, returns final string.
+    """
+
+    def __init__(self, responses: list[str]) -> None:
+        self._responses = list(responses)
+        self.calls: list[str] = []
+
+    def complete(self, prompt: str, *, max_tokens: int = 50) -> str:
+        self.calls.append(prompt)
+        if self._responses:
+            return self._responses.pop(0)
+        return "fallback"
+
+
+def test_labels_one_per_cluster() -> None:
+    cluster_result = ClusterResult(
+        labels=[0, 0, 0, 1, 1, 1],
+        num_clusters=2,
+        is_ambiguous=True,
+    )
+    snippets = ["a1", "a2", "a3", "b1", "b2", "b3"]
+    client = FakeClient(["syndrome", "institute"])
+
+    out = label_clusters(cluster_result, snippets, client)
+
+    assert len(out) == 2
+    assert out[0] == LabeledCluster(cluster_id=0, label="syndrome", sample_snippets=["a1", "a2", "a3"])
+    assert out[1] == LabeledCluster(cluster_id=1, label="institute", sample_snippets=["b1", "b2", "b3"])
+
+
+def test_no_clusters_returns_empty() -> None:
+    cluster_result = ClusterResult(labels=[-1, -1], num_clusters=0, is_ambiguous=False)
+    client = FakeClient(["unused"])
+
+    out = label_clusters(cluster_result, ["x", "y"], client)
+
+    assert out == []
+    assert client.calls == []
+
+
+def test_mismatched_lengths_raises() -> None:
+    cluster_result = ClusterResult(labels=[0, 0, 1], num_clusters=2, is_ambiguous=True)
+    client = FakeClient(["a", "b"])
+
+    with pytest.raises(ValueError, match="does not match"):
+        label_clusters(cluster_result, ["only_one_snippet"], client)
+
+
+def test_empty_llm_response_raises() -> None:
+    cluster_result = ClusterResult(labels=[0, 0], num_clusters=1, is_ambiguous=False)
+    client = FakeClient(["   "])
+
+    with pytest.raises(ValueError, match="empty label"):
+        label_clusters(cluster_result, ["s1", "s2"], client)
+
+
+def test_long_label_truncated() -> None:
+    cluster_result = ClusterResult(labels=[0, 0], num_clusters=1, is_ambiguous=False)
+    long_response = " ".join(f"word{i}" for i in range(20))
+    client = FakeClient([long_response])
+
+    out = label_clusters(cluster_result, ["s1", "s2"], client)
+
+    assert len(out) == 1
+    assert len(out[0].label.split()) == 8
+    assert out[0].label == " ".join(f"word{i}" for i in range(8))
+
+
+def test_skip_noise_label() -> None:
+    cluster_result = ClusterResult(
+        labels=[-1, 0, 0, -1, 1, 1],
+        num_clusters=2,
+        is_ambiguous=True,
+    )
+    snippets = ["noise1", "a1", "a2", "noise2", "b1", "b2"]
+    client = FakeClient(["cluster_zero", "cluster_one"])
+
+    out = label_clusters(cluster_result, snippets, client)
+
+    assert [lc.cluster_id for lc in out] == [0, 1]
+    assert out[0].sample_snippets == ["a1", "a2"]
+    assert out[1].sample_snippets == ["b1", "b2"]
+    assert len(client.calls) == 2

```
