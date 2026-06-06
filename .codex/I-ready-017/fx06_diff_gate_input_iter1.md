# FX-06 (#1120) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
**FAITHFULNESS-RELEVANT** (corpus approval is the pre-generation abort gate, invariant #5) but the
change is ARTIFACT-ONLY — it must NOT alter the abort short-circuit / pre-spend gate timing. Diff:
`.codex/I-ready-017/fx06_codex_diff.patch` (vs FX-15b verified tip `3cbd84ce`). Depends on FX-15b
(#1119, DONE).

## Bug — confirmed §-1.1 on the REAL held artifacts
The corpus-approval gate scores the FINAL post-merge `dist` (`run_honest_sweep_r3.py` ~3093,
`report=dist`), but `corpus_adequacy.json` was last written PRE-merge (~2535 base / ~2698 expansion;
the deepener + agentic merges reassign `dist`/`adequacy` in memory at ~2971-2975 but never re-wrote
the JSON). Held drb_72: `corpus_approval.json.report.total_sources = 145` (T4=31.72%) vs
`corpus_adequacy.json.total_sources = 45` — the gate scored a DIFFERENT population than adequacy +
the report consumed (gate-on-the-wrong-population). Full §-1.1: `outputs/audits/I-ready-017/fx06_s11_audit.md`.

## Fix (artifact-only; abort control-flow UNCHANGED)
After `_flush_retrieval_trace()` and BEFORE the inadequate-abort, re-write `corpus_adequacy.json`
ONCE from the FINAL `adequacy` (post base + expansion + deepener + agentic) so adequacy + approval +
report describe the SAME corpus on EVERY exit path (inadequate-abort, approval-denied, success). Plus
a fail-loud invariant: `adequacy.total_sources == dist.total_sources` (both `sum(tier_counts)`) —
refuse to proceed if a future merge reassigns `dist` without recomputing `adequacy` from it. The
abort still uses the in-memory `adequacy.decision`; the pre-spend gate timing is unchanged.

## Evidence
- **§-1.1 on REAL held artifacts**: approval=145 vs adequacy=45 divergence confirmed.
- **Offline smoke — `test_fx06_approval_population_iready017.py` → 2 passed**: invariant holds
  (`compute_tier_distribution(srcs).total_sources == assess_corpus_adequacy(tier_counts=that dist,
  ...).total_sources`, 45==45); divergence detected for a pre-merge adequacy (45) vs post-merge
  approval dist (145) — the exact held bug shape.
- **Regression**: 425 passed (corpus_approval enforcement b2, adequacy gate, manifest contract,
  run-events, plan_sufficiency, etc.).

## Also checked
- adequacy.json = `asdict(adequacy)` (top-level `total_sources`); approval.report = `dist`
  (`CorpusDistributionReport.total_sources`); both = `sum(tier_counts)`.
- The single final write supersedes the earlier ~2535/2698 writes and also fixes the deepener path
  (which likewise never re-wrote adequacy.json). Earlier writes left in place (cheap).
- The inadequate-abort (~2994) and approval-denied (~3102) paths now read the final adequacy.json.

## Question for you
The invariant is a hard `raise RuntimeError` on divergence (never fires in correct operation, since
`adequacy` is always computed from `dist`). Is a hard raise the right fail-loud here, or do you
prefer a graceful `error_corpus_population_mismatch` abort-manifest (like the other abort paths) so a
single query's invariant violation can't crash a multi-query sweep? Anything else blocking APPROVE?

## THE DIFF UNDER REVIEW (vs FX-15b verified tip 3cbd84ce)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index d749286e..c7a65123 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -2983,6 +2983,31 @@ async def run_one_query(
         # retrieval_trace.jsonl now so EVERY exit path below (abort_corpus_inadequate, approval-denied,
         # and the success path) ships the full per-call search/fetch trace for line-by-line audit.
         _flush_retrieval_trace()
+
+        # FX-06 (#1120): the corpus-approval gate below scores the FINAL `dist` (post base + R-6
+        # expansion + deepener + agentic merges), but corpus_adequacy.json was last written PRE-merge
+        # (~2535 base / ~2698 expansion; the deepener + agentic merges reassign `dist`/`adequacy` in
+        # memory but never re-wrote the JSON). On the held drb_72 run that left approval=145 sources
+        # vs adequacy=45 — the gate scored a DIFFERENT population than adequacy + the report consume.
+        # Re-write corpus_adequacy.json ONCE here from the FINAL `adequacy` so adequacy + approval +
+        # the report all describe the SAME delivered corpus on EVERY exit path below (inadequate-abort,
+        # approval-denied, and success). Artifact-only: the abort decision still uses the in-memory
+        # `adequacy.decision`, so control flow / the pre-spend gate timing is unchanged.
+        (run_dir / "corpus_adequacy.json").write_text(
+            json.dumps(asdict(adequacy), indent=2, sort_keys=True, default=str) + "\n",
+            encoding="utf-8",
+        )
+        # FX-06 invariant (fail-loud): the approval gate (`report=dist`) and the adequacy artifact
+        # MUST score the SAME population. Both are `sum(tier_counts)`; they can only diverge if a
+        # future merge reassigns `dist` without recomputing `adequacy` from it — refuse to proceed
+        # rather than gate/approve on a population the report does not consume.
+        if adequacy.total_sources != dist.total_sources:
+            raise RuntimeError(
+                f"FX-06 invariant violated: corpus_adequacy.total_sources={adequacy.total_sources} "
+                f"!= corpus_approval dist.total_sources={dist.total_sources} — the approval gate "
+                f"would score a different population than the adequacy artifact + report consume."
+            )
+
         # R-6 Gap-1: if adequacy still says ABORT after optional
         # expansion, refuse to synthesize — emit a short "corpus
         # inadequate" manifest and return status=abort_corpus_inadequate.
diff --git a/tests/polaris_graph/test_fx06_approval_population_iready017.py b/tests/polaris_graph/test_fx06_approval_population_iready017.py
new file mode 100644
index 00000000..a685f31c
--- /dev/null
+++ b/tests/polaris_graph/test_fx06_approval_population_iready017.py
@@ -0,0 +1,71 @@
+"""FX-06 (I-ready-017 #1120): corpus-approval scores the SAME population as adequacy + the report.
+
+Bug (held drb_72): corpus_approval.json scored the FINAL post-merge dist (total_sources=145, padded
+with agentic junk) while corpus_adequacy.json was written PRE-merge (total_sources=45) — the gate
+scored a different population than adequacy + the report consumed. FX-06 re-writes corpus_adequacy.json
+from the FINAL dist and adds a fail-loud invariant `adequacy.total_sources == dist.total_sources`.
+
+These component tests prove the invariant the orchestrator relies on: an adequacy computed from a
+dist's tier_counts has total_sources == that dist's total_sources (so writing adequacy from the
+final dist makes the two artifacts agree); and that a pre-merge adequacy diverges from a post-merge
+dist (the bug the invariant catches). Offline, no network.
+"""
+from __future__ import annotations
+
+from types import SimpleNamespace
+
+from src.polaris_graph.nodes.corpus_adequacy_gate import assess_corpus_adequacy
+from src.polaris_graph.nodes.corpus_approval_gate import compute_tier_distribution
+
+_PROTOCOL = {
+    "expected_tier_distribution": [
+        {"tier": "T1", "min_fraction": 0.10, "max_fraction": 0.90},
+        {"tier": "T4", "min_fraction": 0.0, "max_fraction": 0.60},
+    ]
+}
+# Held drb_72 corpus_adequacy tier_counts (sum = 45 = the report-consumed set).
+_HELD_45 = {"T1": 6, "T2": 3, "T4": 23, "T5": 2, "T6": 7, "UNKNOWN": 4}
+
+
+def _sources(tier_counts: dict[str, int]) -> list:
+    out: list = []
+    i = 0
+    for tier, n in tier_counts.items():
+        for _ in range(n):
+            out.append(SimpleNamespace(tier=tier, url=f"https://example.org/s{i}"))
+            i += 1
+    return out
+
+
+def test_fx06_invariant_holds_when_adequacy_from_same_dist():
+    """FX-06's guarantee: adequacy written from `dist.tier_counts` has total_sources == dist's."""
+    srcs = _sources(_HELD_45)
+    dist = compute_tier_distribution(srcs, _PROTOCOL)
+    adequacy = assess_corpus_adequacy(
+        tier_counts=dist.tier_counts,
+        evidence_row_count=len(srcs),
+        domain="workforce",
+        protocol=_PROTOCOL,
+    )
+    assert dist.total_sources == 45
+    assert adequacy.total_sources == dist.total_sources  # the invariant the orchestrator asserts
+
+
+def test_fx06_divergence_detected_pre_vs_post_merge():
+    """The bug: a PRE-merge adequacy (45) vs the POST-merge dist the approval scores (~145).
+    The FX-06 fail-loud invariant catches exactly this inequality."""
+    pre_dist = compute_tier_distribution(_sources(_HELD_45), _PROTOCOL)
+    pre_adequacy = assess_corpus_adequacy(
+        tier_counts=pre_dist.tier_counts,
+        evidence_row_count=45,
+        domain="workforce",
+        protocol=_PROTOCOL,
+    )
+    # Post-merge dist padded to ~145 (the held approval total_sources).
+    post_dist = compute_tier_distribution(
+        _sources({"T1": 54, "T4": 46, "UNKNOWN": 45}), _PROTOCOL
+    )
+    assert post_dist.total_sources == 145
+    # Pre-merge adequacy vs post-merge approval population diverge — the FX-06 invariant fails loud.
+    assert pre_adequacy.total_sources != post_dist.total_sources
+    assert (pre_adequacy.total_sources, post_dist.total_sources) == (45, 145)
```
