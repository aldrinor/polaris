HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: P6 weight-mass (#1155) — DIFF gate ITER 3. Iter-2 REQUEST_CHANGES (2 P1) addressed: cluster_mass = authority_score(canonical) ONLY (plan §148). The authority×credibility formula is REMOVED — it (a) drifted from the Codex-plan-approved §148 and (b) broke no-inflation (high-auth/low-cred 0.8×0.1=0.08 overtaken by a lower-auth NO-judgment copy 0.3×1.0=0.3, so adding a copy RAISED the mass). credibility_weight is now a DISCLOSED OriginContribution field, NOT a mass factor (credibility combines downstream in Phase 7/8). Regression test_credibility_is_disclosed_not_a_mass_factor_no_inflation: high-auth/low-cred origin NOT overtaken (0.8 -> 0.3, no inflation). Canonical stays a validated hard precondition (fail-loud missing/duplicate). SMOKE: 19 passed.
```diff
diff --git a/src/polaris_graph/synthesis/weight_mass.py b/src/polaris_graph/synthesis/weight_mass.py
new file mode 100644
index 00000000..8ebf8967
--- /dev/null
+++ b/src/polaris_graph/synthesis/weight_mass.py
@@ -0,0 +1,181 @@
+"""I-cred-006 (Phase 6, L5) — origin-cluster weight-mass aggregator (pure module).
+
+Aggregate, per claim cluster, a **weight-mass** = Σ over INDEPENDENT origin clusters of
+``cluster_mass``, where ``cluster_mass = authority_score(canonical_origin)`` (plan §148 — credibility
+is disclosed separately, NOT a mass factor) and every derivative copy contributes ZERO. This is the executable form of plan
+§148: 50 copies of one press release count ONCE, at the origin's authority — the vax-defense.
+
+POSTURE (binding):
+  * ADVISORY ONLY. Weight-mass is a DISCLOSED side-output. The 4-role D8 release policy
+    (``roles/release_policy.py``) stays the single binding release gate; ``strict_verify``'s six
+    checks stay the only binding faithfulness gate. This module touches neither.
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_WEIGHT_MASS`` (no production caller; pure library).
+  * Copies contribute ZERO to the mass; adding a copy of ANY authority cannot inflate the mass
+    (origin-cluster invariant — copies are excluded, the canonical origin alone carries the mass).
+  * PURE: no row mutation, no network, no faithfulness-file import; LAW VI env-overridable; snake_case.
+
+This issue ships ONLY the pure aggregator. Removing the journal count-floor, wiring weight-mass into
+``corpus_adequacy_gate``, and the per-claim clinical source-type veto are the gate-touching follow-up
+(I-cred-006b) with their own flag — they modify faithfulness-adjacent gates.
+
+INPUT join (all on the stable per-evidence ``evidence_id``):
+  * ``rows``: evidence rows, each carrying ``evidence_id``, ``origin_cluster_id`` + ``is_canonical_origin``
+    (Phase-4 assignment merged onto the row by the caller), and ``authority_score``. A row with no
+    ``origin_cluster_id`` is treated as its OWN independent origin (it was never flagged a copy).
+  * ``claims``: Phase-5 atomic claims (``claim_cluster_id`` + ``evidence_id``).
+  * ``judgments``: Phase-2 credibility judgments (``evidence_id`` -> ``credibility_weight``); a canonical
+    with NO judgment uses ``credibility_weight = 1.0`` (mass = pure authority).
+"""
+from __future__ import annotations
+
+import math
+import os
+from dataclasses import dataclass
+from typing import Any
+
+_FLAG = "PG_SWEEP_WEIGHT_MASS"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+
+def weight_mass_enabled() -> bool:
+    """True unless ``PG_SWEEP_WEIGHT_MASS`` is unset/falsey (default OFF => byte-identical)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _num(value: Any) -> float:
+    """Coerce to a finite float; non-numeric / NaN / inf -> 0.0 (fail-soft on a disclosure signal)."""
+    try:
+        x = float(value)
+    except (TypeError, ValueError):
+        return 0.0
+    return 0.0 if (math.isnan(x) or math.isinf(x)) else x
+
+
+def _clamp01(value: Any) -> float:
+    x = _num(value)
+    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
+
+
+@dataclass
+class OriginContribution:
+    """One independent origin's contribution to a claim cluster's weight-mass."""
+
+    origin_cluster_id: str
+    canonical_evidence_id: str
+    authority_score: float       # of the canonical origin
+    credibility_weight: float    # Phase-2 weight of the canonical origin (1.0 if none)
+    cluster_mass: float          # = authority_score(canonical) ONLY (plan §148); credibility disclosed, not a factor
+    copy_count: int              # derivative copies attributed to this origin (disclosure)
+
+
+@dataclass
+class ClaimWeightMass:
+    """A claim cluster's aggregated, copy-uninflatable weight-mass + its origin breakdown."""
+
+    claim_cluster_id: str
+    weight_mass: float
+    independent_origin_count: int
+    contributions: list
+
+
+def _origin_id_for_row(row: dict[str, Any]) -> str:
+    ocid = str(row.get("origin_cluster_id", "") or "").strip()
+    # An uncollapsed row (never flagged a copy) is its OWN independent origin.
+    return ocid if ocid else f"origin::{row.get('evidence_id', '')}"
+
+
+def aggregate_weight_mass(
+    claims: list,
+    rows: list[dict[str, Any]],
+    judgments: list,
+) -> list[ClaimWeightMass]:
+    """Aggregate per-claim-cluster origin-cluster weight-mass — ADVISORY, pure, no row mutation.
+
+    For each claim cluster, group its supporting rows by ``origin_cluster_id``; for each origin use the
+    CANONICAL origin's ``authority_score`` as the cluster mass (credibility is disclosed, not a factor —
+    plan §148); copies contribute
+    ZERO (only ``copy_count`` for disclosure). The claim weight-mass is the sum once per origin cluster.
+    """
+    rows = list(rows or [])
+    row_by_eid = {str(r.get("evidence_id", "")): r for r in rows}
+    cred_by_eid: dict[str, float] = {}
+    for judgment in (judgments or []):
+        eid = str(getattr(judgment, "evidence_id", "") or "")
+        if eid:
+            cred_by_eid[eid] = _clamp01(getattr(judgment, "credibility_weight", None))
+
+    # The canonical row per origin cluster (global across all rows), so a claim supported only by
+    # COPIES still attributes the mass to the origin's authority, never a copy's. VALIDATED: each
+    # COLLAPSED origin must carry EXACTLY ONE is_canonical_origin row (Phase-4 metadata) — FAIL-LOUD
+    # on missing/duplicate, never fail-soft to a member (a copy must never become the mass carrier;
+    # Codex #1155 P1-1). An uncollapsed row is its own singleton canonical.
+    canonical_by_origin: dict[str, dict[str, Any]] = {}
+    canonical_counts: dict[str, int] = {}
+    collapsed_origins: set[str] = set()
+    for row in rows:
+        ocid = _origin_id_for_row(row)
+        if str(row.get("origin_cluster_id", "") or "").strip():
+            collapsed_origins.add(ocid)
+            if row.get("is_canonical_origin"):
+                canonical_counts[ocid] = canonical_counts.get(ocid, 0) + 1
+                canonical_by_origin[ocid] = row
+        else:
+            canonical_by_origin.setdefault(ocid, row)  # uncollapsed singleton = its own canonical
+    for ocid in sorted(collapsed_origins):
+        count = canonical_counts.get(ocid, 0)
+        if count != 1:
+            raise ValueError(
+                f"weight_mass: origin cluster {ocid!r} must carry EXACTLY ONE is_canonical_origin "
+                f"row (Phase-4 canonical metadata); found {count}. No fail-soft fallback — a copy "
+                f"must never become the mass carrier (Codex #1155 P1-1)."
+            )
+
+    claim_eids: dict[str, list] = {}
+    for claim in (claims or []):
+        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
+        eid = str(getattr(claim, "evidence_id", "") or "")
+        if ccid:
+            claim_eids.setdefault(ccid, []).append(eid)
+
+    out: list[ClaimWeightMass] = []
+    for ccid in sorted(claim_eids):
+        members_by_origin: dict[str, set] = {}
+        for eid in claim_eids[ccid]:
+            row = row_by_eid.get(eid)
+            if row is None:
+                continue
+            members_by_origin.setdefault(_origin_id_for_row(row), set()).add(eid)
+
+        contributions: list[OriginContribution] = []
+        for ocid in sorted(members_by_origin):
+            members = members_by_origin[ocid]
+            canonical = canonical_by_origin[ocid]  # guaranteed present by the validation above
+            canon_eid = str(canonical.get("evidence_id", ""))
+            authority = _clamp01(canonical.get("authority_score"))
+            credibility = cred_by_eid.get(canon_eid, 1.0)  # no judgment => neutral 1.0
+            contributions.append(OriginContribution(
+                origin_cluster_id=ocid,
+                canonical_evidence_id=canon_eid,
+                authority_score=authority,
+                credibility_weight=credibility,
+                # cluster_mass = authority_score(canonical origin) ONLY (plan §148). credibility_weight
+                # is carried as a DISCLOSED field but is NOT a mass factor: folding it in breaks the
+                # no-inflation invariant (a high-authority / low-credibility origin, 0.8x0.1=0.08, could
+                # be OVERTAKEN by adding a lower-authority copy with no judgment, 0.3x1.0=0.3 — adding a
+                # copy raises the mass). Mass is pure independence-authority; credibility is disclosed
+                # separately and combined downstream (Phase 7/8). Codex #1155 iter-2 P1.
+                cluster_mass=authority,
+                # Supporting members that are NOT the canonical = the derivative copies of this
+                # origin backing this claim. Counting "members minus canonical" (not len-1) is
+                # correct even when the claim is supported ONLY by copies and the canonical row
+                # backs a different claim (Codex #1155 P2-2 — no 0-copy undercount).
+                copy_count=sum(1 for m in members if m != canon_eid),
+            ))
+
+        out.append(ClaimWeightMass(
+            claim_cluster_id=ccid,
+            weight_mass=sum(c.cluster_mass for c in contributions),
+            independent_origin_count=len(contributions),
+            contributions=contributions,
+        ))
+    return out
diff --git a/tests/polaris_graph/synthesis/test_weight_mass_phase6.py b/tests/polaris_graph/synthesis/test_weight_mass_phase6.py
new file mode 100644
index 00000000..b6d4c710
--- /dev/null
+++ b/tests/polaris_graph/synthesis/test_weight_mass_phase6.py
@@ -0,0 +1,182 @@
+"""I-cred-006 (Phase 6) — origin-cluster weight-mass aggregator. Offline, deterministic, no network.
+Each test maps to a brief acceptance criterion (AC-1..AC-8)."""
+from __future__ import annotations
+
+import copy
+
+import pytest
+
+from src.polaris_graph.synthesis.weight_mass import (
+    ClaimWeightMass,
+    OriginContribution,
+    aggregate_weight_mass,
+    weight_mass_enabled,
+)
+
+
+def _claim(ccid, eid):
+    return type("C", (), {"claim_cluster_id": ccid, "evidence_id": eid})()
+
+
+def _judg(eid, weight):
+    return type("J", (), {"evidence_id": eid, "credibility_weight": weight})()
+
+
+def _row(eid, ocid, canonical, authority):
+    return {
+        "evidence_id": eid,
+        "origin_cluster_id": ocid,
+        "is_canonical_origin": canonical,
+        "authority_score": authority,
+    }
+
+
+# ── AC-1 ──────────────────────────────────────────────────────────────────────
+def test_flag_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_WEIGHT_MASS", raising=False)
+    assert weight_mass_enabled() is False
+
+
+@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on(monkeypatch, on):
+    monkeypatch.setenv("PG_SWEEP_WEIGHT_MASS", on)
+    assert weight_mass_enabled() is True
+
+
+# ── AC-2: single origin + the vax invariant (copies cannot inflate) ───────────
+def test_single_origin_copies_uninflatable():
+    rows = [
+        _row("e0", "o1", True, 0.8),    # canonical
+        _row("e1", "o1", False, 0.3),   # copy
+        _row("e2", "o1", False, 0.9),   # copy with HIGHER authority
+    ]
+    claims = [_claim("c1", "e0"), _claim("c1", "e1"), _claim("c1", "e2")]
+    out = aggregate_weight_mass(claims, rows, [_judg("e0", 0.5)])
+    assert len(out) == 1
+    cm = out[0]
+    assert cm.independent_origin_count == 1
+    assert abs(cm.weight_mass - 0.8) < 1e-9   # = authority(canonical) ONLY (plan §148)
+    assert cm.contributions[0].credibility_weight == 0.5  # credibility is DISCLOSED, not in the mass
+    assert cm.contributions[0].copy_count == 2
+
+    # Add MORE copies of ANY authority -> weight_mass is UNCHANGED (the vax-defense).
+    rows2 = rows + [_row("e3", "o1", False, 0.99), _row("e4", "o1", False, 0.99)]
+    claims2 = claims + [_claim("c1", "e3"), _claim("c1", "e4")]
+    out2 = aggregate_weight_mass(claims2, rows2, [_judg("e0", 0.5)])
+    assert abs(out2[0].weight_mass - 0.8) < 1e-9
+    assert out2[0].independent_origin_count == 1
+
+
+# ── AC-3: two independent origins sum ─────────────────────────────────────────
+def test_two_independent_origins_sum():
+    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o2", True, 0.6)]
+    claims = [_claim("c1", "e0"), _claim("c1", "e1")]
+    cm = aggregate_weight_mass(claims, rows, [])[0]
+    assert cm.independent_origin_count == 2
+    assert abs(cm.weight_mass - 1.4) < 1e-9  # 0.8*1.0 + 0.6*1.0
+
+
+# ── AC-4: a higher-authority copy contributes ZERO ────────────────────────────
+def test_higher_authority_copy_contributes_zero():
+    rows = [_row("e0", "o1", True, 0.2), _row("e1", "o1", False, 0.99)]
+    claims = [_claim("c1", "e0"), _claim("c1", "e1")]
+    cm = aggregate_weight_mass(claims, rows, [])[0]
+    assert abs(cm.weight_mass - 0.2) < 1e-9  # canonical 0.2, never the 0.99 copy
+
+
+# ── AC-5: canonical with no judgment uses neutral 1.0 ─────────────────────────
+def test_canonical_no_judgment_uses_neutral_one():
+    cm = aggregate_weight_mass([_claim("c1", "e0")], [_row("e0", "o1", True, 0.7)], [])[0]
+    assert abs(cm.weight_mass - 0.7) < 1e-9  # 0.7 * 1.0
+
+
+# ── AC-6: distinct claim clusters aggregate independently ─────────────────────
+def test_distinct_claim_clusters_independent():
+    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o2", True, 0.6)]
+    claims = [_claim("c1", "e0"), _claim("c2", "e1")]
+    by = {c.claim_cluster_id: c for c in aggregate_weight_mass(claims, rows, [])}
+    assert abs(by["c1"].weight_mass - 0.8) < 1e-9
+    assert abs(by["c2"].weight_mass - 0.6) < 1e-9
+
+
+# ── AC-7: missing authority on the canonical -> 0.0, no crash ─────────────────
+def test_missing_authority_is_zero_no_crash():
+    rows = [{"evidence_id": "e0", "origin_cluster_id": "o1", "is_canonical_origin": True}]
+    cm = aggregate_weight_mass([_claim("c1", "e0")], rows, [])[0]
+    assert cm.weight_mass == 0.0
+
+
+# ── AC-8: purity — no row mutation ────────────────────────────────────────────
+def test_no_row_mutation():
+    rows = [_row("e0", "o1", True, 0.8)]
+    before = copy.deepcopy(rows)
+    aggregate_weight_mass([_claim("c1", "e0")], rows, [_judg("e0", 0.5)])
+    assert rows == before
+
+
+def test_uncollapsed_row_is_its_own_origin():
+    """A row with no origin_cluster_id is treated as its OWN independent origin (never a copy)."""
+    rows = [{"evidence_id": "e0", "authority_score": 0.5, "is_canonical_origin": False}]
+    cm = aggregate_weight_mass([_claim("c1", "e0")], rows, [])[0]
+    assert cm.independent_origin_count == 1
+    assert abs(cm.weight_mass - 0.5) < 1e-9
+
+
+# ── Codex #1155 P2-1: the binding invariant is NO INFLATION (monotonic non-increase) ──
+def test_lower_authority_copy_becoming_canonical_lowers_mass_never_inflates():
+    """If Phase-4's conservative-min re-marks a LOWER-authority member as canonical (all-undated
+    case), the mass DROPS — monotonically non-increasing under copy additions, never inflating."""
+    high = aggregate_weight_mass([_claim("c1", "e0")], [_row("e0", "o1", True, 0.8)], [])[0]
+    assert abs(high.weight_mass - 0.8) < 1e-9
+    # A lower-authority copy is added AND marked canonical (Phase-4 conservative-min); e0 demoted.
+    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", True, 0.3)]
+    low = aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])[0]
+    assert low.weight_mass <= high.weight_mass        # never increases
+    assert abs(low.weight_mass - 0.3) < 1e-9
+
+
+def test_credibility_is_disclosed_not_a_mass_factor_no_inflation():
+    """Codex #1155 iter-2 P1: cluster_mass = authority(canonical) ONLY. A high-authority / LOW-
+    credibility origin must NOT be overtaken (inflated) by adding a lower-authority copy with no
+    judgment — the bug that folding credibility into the mass would cause (0.8*0.1=0.08 < 0.3)."""
+    before = aggregate_weight_mass(
+        [_claim("c1", "e0")], [_row("e0", "o1", True, 0.8)], [_judg("e0", 0.1)])[0]
+    assert abs(before.weight_mass - 0.8) < 1e-9   # authority ONLY, never 0.8*0.1
+    # A lower-authority copy with NO judgment is re-marked canonical (Phase-4 conservative-min).
+    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", True, 0.3)]
+    after = aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [_judg("e0", 0.1)])[0]
+    assert after.weight_mass <= before.weight_mass  # NO inflation
+    assert abs(after.weight_mass - 0.3) < 1e-9
+
+
+# ── Codex #1155 P2-2: copy-only support uses the GLOBAL canonical, not the copy ──
+def test_copy_only_support_uses_global_canonical():
+    """A claim cluster supported ONLY by a derivative copy uses the GLOBAL Phase-4 canonical row's
+    authority for that origin, not the copy's own."""
+    rows = [_row("e0", "o1", True, 0.9), _row("e1", "o1", False, 0.1)]  # canonical e0 supports c2 only
+    claims = [_claim("c2", "e0"), _claim("c1", "e1")]
+    by = {c.claim_cluster_id: c for c in aggregate_weight_mass(claims, rows, [])}
+    assert abs(by["c1"].weight_mass - 0.9) < 1e-9  # uses canonical e0's 0.9, NOT copy e1's 0.1
+    assert by["c1"].contributions[0].copy_count == 1  # e1 is a derivative copy backing c1 (no undercount)
+
+
+# ── Codex #1155 P1-1: canonical metadata is a required, validated precondition (fail-loud) ──
+def test_duplicate_canonical_fails_loud():
+    rows = [_row("e0", "o1", True, 0.8), _row("e1", "o1", True, 0.6)]  # TWO canonicals for one origin
+    raised = False
+    try:
+        aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])
+    except ValueError as exc:
+        raised = True
+        assert "EXACTLY ONE" in str(exc)
+    assert raised, "duplicate canonical must fail loud"
+
+
+def test_missing_canonical_fails_loud():
+    rows = [_row("e0", "o1", False, 0.8), _row("e1", "o1", False, 0.6)]  # NO canonical for a collapsed origin
+    raised = False
+    try:
+        aggregate_weight_mass([_claim("c1", "e0"), _claim("c1", "e1")], rows, [])
+    except ValueError:
+        raised = True
+    assert raised, "a collapsed origin with no canonical must fail loud, never fail-soft to a copy"
```
