Diff review for GH#405 I-tpl-009. Output YAML.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Brief lineage

Brief APPROVE iter 2 (`.codex/GH405/codex_brief_verdict_iter_2.txt`). This diff implements that brief exactly.

# Test results (offline)

```
$ PYTHONPATH=src python -m pytest tests/polaris_graph/test_corpus_adequacy_r6_gap1.py tests/polaris_graph/retrieval2/test_corpus_adequacy_gate.py tests/polaris_graph/test_regression_alerts.py
75 passed
```

- `test_corpus_adequacy_r6_gap1.py`: 17/17 (11 pre-existing + 6 new GH#405 tests)
- `retrieval2/test_corpus_adequacy_gate.py`: 24/24 (separate slice-002 gate, unchanged)
- `test_regression_alerts.py`: 34/34 (consumes adequacy.decision — unaffected by new finding)

# Diff (canonical patch saved at `.codex/GH405/codex_diff.patch`)

## Production code: `src/polaris_graph/nodes/corpus_adequacy_gate.py`

```diff
@@ AdequacyThresholds dataclass @@
     min_t1_plus_t2_plus_t3: int = 3
+    min_t3_plus_t4_plus_t6: int = 0  # GH#405: emerging-policy quality floor
     min_evidence_rows: int = 5

@@ _DEFAULT_DOMAIN_THRESHOLDS @@
     "policy": AdequacyThresholds(
-        min_total_sources=8, min_t1_count=1,
-        min_t1_plus_t2=2, min_t1_plus_t2_plus_t3=5,
+        min_total_sources=8, min_t1_count=0,
+        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
+        min_t3_plus_t4_plus_t6=5,
         min_evidence_rows=5,
         ...
     ),
+    "ai_sovereignty": AdequacyThresholds(
+        min_total_sources=8, min_t1_count=0,
+        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
+        min_t3_plus_t4_plus_t6=4,
+        min_evidence_rows=5,
+        max_t5_plus_t6_fraction=0.80, max_t7_fraction=0.40,
+    ),
+    "canada_us": AdequacyThresholds(  # same as ai_sovereignty
+        ...
+    ),
+    "workforce": AdequacyThresholds(
+        min_total_sources=6, min_t1_count=0,
+        min_t1_plus_t2=0, min_t1_plus_t2_plus_t3=0,
+        min_t3_plus_t4_plus_t6=4,
+        min_evidence_rows=5,
+        max_t5_plus_t6_fraction=0.85, max_t7_fraction=0.40,
+    ),

@@ _get_thresholds @@
     min_t1_plus_t2_plus_t3=int(ca.get("min_t1_plus_t2_plus_t3", base.min_t1_plus_t2_plus_t3)),
+    min_t3_plus_t4_plus_t6=int(ca.get("min_t3_plus_t4_plus_t6", base.min_t3_plus_t4_plus_t6)),
     min_evidence_rows=int(ca.get("min_evidence_rows", base.min_evidence_rows)),

@@ assess_corpus_adequacy @@
     t3 = tier_counts.get("T3", 0)
+    t4 = tier_counts.get("T4", 0)
     t5 = tier_counts.get("T5", 0)

@@ _record calls @@
     _record("t1_plus_t2_plus_t3", t1 + t2 + t3, thr.min_t1_plus_t2_plus_t3, "min")
+    _record("t3_plus_t4_plus_t6", t3 + t4 + t6, thr.min_t3_plus_t4_plus_t6, "min")
     _record("evidence_rows", evidence_row_count, thr.min_evidence_rows, "min")
```

Stats: `src/polaris_graph/nodes/corpus_adequacy_gate.py | 46 ++++++++++-` (44 additions, 2 deletions).

## Tests: `tests/polaris_graph/test_corpus_adequacy_r6_gap1.py`

```diff
+ test_ai_sovereignty_emerging_policy_proceeds  (Q1 actual counts; proceed/expand)
+ test_canada_us_emerging_policy_proceeds       (Q2 actual; proceed/expand)
+ test_workforce_t4_only_proceeds               (Q3 actual T4-only; proceed/expand)
+ test_housing_policy_proceeds_after_relax      (Q4 actual; proceed/expand)
+ test_clinical_still_strict_regression         (clinical T1=0 must still abort)
+ test_protocol_override_t3_plus_t4_plus_t6     (protocol passthrough)
```

Stats: `+93 lines, 6 new tests`.

# Verification

1. ✅ Schema field added with default=0 (backwards-compat)
2. ✅ Policy P1 fix applied: min_t1_plus_t2_plus_t3=0 (not 2), so Q4 (observed=1) is "ok" not "critical"
3. ✅ 3 new emerging-policy domain entries with min_t1=0/min_t1+t2=0/min_t1+t2+t3=0
4. ✅ min_t3_plus_t4_plus_t6 finding wired through assess_corpus_adequacy
5. ✅ Protocol passthrough added in _get_thresholds
6. ✅ Manifest serialization works via existing `asdict(thr)` + AdequacyFinding (no schema change needed)
7. ✅ Q1-Q4 + Q5 + clinical-regression test fixtures pass
8. ✅ Downstream consumers unaffected: regression_alerts (reads .decision), evaluator_gate (consumes shape), section_blueprint (consumes shape) — none of these care about which findings exist or new thresholds

# Out of scope (deferred per brief)

- Scope template → protocol.json passthrough wiring (Codex iter-1 caveat #1 — not blocking because sweep uses domain defaults directly)
- Tier-classifier upgrade for gov-stats agencies → T3 (GH#406 follow-up)
- T6 calibration tightening (GH#406 follow-up)

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
