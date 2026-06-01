HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero P0 AND zero P1.

# Codex DIFF gate iter 2 — I-meta-005 Phase 3 (#987): plan-sufficiency money-gate

iter-1 = REQUEST_CHANGES (1 P1; deviations A/B/C ruled acceptable). This AUTHORIZES THE MERGE. §8.3.9 YAML FIRST.
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## ITER-1 P1 FIX (verify): the per-facet reserved set could still be truncated by the max_ev_per_section
ceiling when a section maps MORE facets than the cap (your repro: 31 facets, target 31, cap 30 -> facet 30
dropped). FIX: clamp ORDER in _assign_evidence_to_planned_outline — cap=min(target,max_ev_per_section)
FIRST, THEN cap=max(cap,len(reserved)), so the reserved per-facet rows are NEVER truncated (size cap applies
only to filler). Confirm: a SUFFICIENT section with N mapped facets (N possibly > max_ev_per_section) bills
>=min_per_facet rows for EVERY facet. Regression P3-15g reproduces your exact 31-facet case.

## SMOKE: 26 Phase-3 (incl P3-15e/f/g per-facet + size-cap + floor-threading) + 44 generator/planner regression green.

APPROVE iff the reserved-set-sacred fix is complete (no certified facet can be dropped at any cap boundary).
Deviations A/B/C were already ruled acceptable iter-1.

--- DIFF (assignment fix + P3-15g) ---
```diff
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 1607f9d5..78ca1ca8 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -695,12 +695,17 @@ def _assign_evidence_to_planned_outline(
             # 2. Fill the rest: remaining above-floor, then below-floor as filler.
             rest = [e for e in section_above_any[i] if e not in reserved]
             rest += [e for e in section_below_any[i] if e not in reserved]
-            # cap = evidence_target, but NEVER below the reserved set (the
-            # certified-facet rows MUST reach the generator); hard ceiling at
-            # max_ev_per_section.
+            # cap = evidence_target, clamped to the soft section size cap FIRST,
+            # then raised to never drop the RESERVED set (architect/Codex P1: the
+            # max_ev_per_section ceiling must apply only to the FILLER — the
+            # per-facet reserved rows are SACRED, never truncated, else a section
+            # mapped to MORE facets than max_ev_per_section would silently drop a
+            # certified facet's only row, billing a section whose sub-question has
+            # ZERO evidence. Repro: 31 facets, target 31, cap 30 -> facet 30
+            # dropped. Clamp ORDER guarantees len(reserved) survives.).
             cap = target if target > 0 else max_ev_per_section
-            cap = max(cap, len(reserved))
             cap = min(cap, max_ev_per_section)
+            cap = max(cap, len(reserved))
             ordered_ev = reserved + rest
             plans.append(SectionPlan(
                 title=title,
diff --git a/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py b/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py
index 69538273..d852ade1 100644
--- a/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py
+++ b/tests/polaris_graph/adequacy/test_plan_sufficiency_phase3.py
@@ -553,6 +553,41 @@ def test_p3_15f_assignment_uses_threaded_floor_not_just_env(monkeypatch):
     assert set(plans_lo[0].ev_ids) == {"mid_0", "mid_1"}
 
 
+def test_p3_15g_reserved_survives_when_facets_exceed_section_cap():
+    """Codex diff-gate P1: a section mapped to MORE facets than max_ev_per_section
+    must STILL bill >=min_per_facet for EVERY facet — the per-facet reserved set
+    is sacred and the section size cap applies only to the filler. Codex's exact
+    repro: 31 mapped facets, target=31, 31 above-floor rows (one per facet),
+    max_ev_per_section=30. Gate PROCEED; the assignment must emit all 31, not
+    drop facet 30."""
+    from src.polaris_graph.adequacy.plan_sufficiency_gate import (
+        assess_plan_sufficiency,
+    )
+    from src.polaris_graph.generator.multi_section_generator import (
+        _assign_evidence_to_planned_outline,
+    )
+    n = 31
+    sub = [f"facet {k} unique terms" for k in range(n)]
+    outline = [_section("S0", n, list(range(n)))]
+    evidence = [_row(f"ev_{k:02d}", f"facet {k} unique terms", 0.9) for k in range(n)]
+    report = assess_plan_sufficiency(
+        plan=_plan(sub, outline), corpus_rows=evidence,
+        authority_floor=0.3, round_index=0, max_rounds=0,
+    )
+    assert report.verdict == "proceed"
+    plans = _assign_evidence_to_planned_outline(
+        outline, evidence, sub_queries=sub, authority_floor=0.3,
+        max_ev_per_section=30,
+    )
+    billed = set(plans[0].ev_ids)
+    # Every facet's only row must be billed — none truncated by the size cap.
+    missing = [f"ev_{k:02d}" for k in range(n) if f"ev_{k:02d}" not in billed]
+    assert not missing, (
+        f"SIZE-CAP TRUNCATION REGRESSION: {missing} dropped; a certified facet "
+        f"has ZERO evidence in the billed set. billed={len(billed)}/{n}"
+    )
+
+
 def test_p3_15d_off_path_round_robin_ignores_authority():
     """Off-path (sub_queries=None) assignment is byte-identical round-robin —
     it must NOT read authority at all (no sidecar on off-mode rows)."""
```
