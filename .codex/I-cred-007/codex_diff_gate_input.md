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
## PHASE: P7 both-sides composer (#1156) — DIFF gate iter 1 (brief in parallel review). PURE composer only (wiring into the report assembler + UI deferred to I-cred-007b). compose_both_sides(contradiction_edges, weight_mass, claims) -> list[BothSidesBlock]: maps each Phase-5 ContradictionEdge's two claim_cluster_ids to their Phase-6 weight_mass + independent_origin_count + Phase-5 evidence_ids; sides ordered by weight_mass DESC (discloses which side has more evidence weight, NEVER asserts which is true); the LOW-weight side is KEPT, never dropped (operator Decision 2); missing weight -> 0.0/0 fail-soft. render_both_sides -> NEUTRAL markdown ('' for [] = default-OFF byte-identity); a guardrail test asserts NONE of {fringe,misinformation,debunked,conspiracy,warning,unreliable,false claim,discredited}. ADVISORY/disclosure only — separate block like limitations_text, NEVER edits verified prose / strict_verify / 4-role D8; default-OFF PG_SWEEP_BOTHSIDES_DISCLOSURE; pure. SMOKE: 14 passed.
```diff
diff --git a/src/polaris_graph/synthesis/both_sides.py b/src/polaris_graph/synthesis/both_sides.py
new file mode 100644
index 00000000..43c2051f
--- /dev/null
+++ b/src/polaris_graph/synthesis/both_sides.py
@@ -0,0 +1,158 @@
+"""I-cred-007 (Phase 7, L6) — NEUTRAL both-sides disclosure composer (pure module).
+
+For a CONTESTED claim (a claim-cluster pair joined by a Phase-5 ``ContradictionEdge``), compose a
+NEUTRAL both-sides disclosure: each side shown as a LEGITIMATE position with its transparent evidence
+weight (Phase-6 origin-cluster ``weight_mass``), its independent-origin count, and its cited
+``evidence_id``s — in neutral language, ALWAYS visible. The user judges; POLARIS discloses the weight
+behind each side honestly rather than labelling one "true" or "fringe" (operator Decision 2, plan §9.3).
+
+POSTURE (binding):
+  * ADVISORY / DISCLOSURE ONLY. This is a SEPARATE block (rendered like ``limitations_text``), appended
+    AFTER verified prose. It NEVER edits verified sentences, NEVER runs inside ``strict_verify``, NEVER
+    touches the 4-role D8 release gate. strict_verify's six checks stay the only binding faithfulness gate.
+  * NEUTRAL framing: no "fringe / misinformation / warning / debunked / conspiracy / unreliable" labels.
+  * DEFAULT-OFF byte-identical: ``PG_SWEEP_BOTHSIDES_DISCLOSURE`` (no production caller; pure library).
+  * Weight is the Phase-6 origin-cluster ``weight_mass`` (authority of independent canonical origins),
+    never headcount. Both sides get their honest weight; the LOW-weight side is shown, not dropped.
+  * PURE: no input mutation, no network, no faithfulness-file import; LAW VI; snake_case.
+
+This issue ships the pure composer ONLY; wiring the rendered block into the report assembler + the UI
+affordance is a separate step (I-cred-007b), keeping this faithfulness-safe and default-OFF.
+"""
+from __future__ import annotations
+
+import os
+from dataclasses import dataclass
+from typing import Any
+
+_FLAG = "PG_SWEEP_BOTHSIDES_DISCLOSURE"
+_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})
+
+
+def bothsides_disclosure_enabled() -> bool:
+    """True unless ``PG_SWEEP_BOTHSIDES_DISCLOSURE`` is unset/falsey (default OFF => byte-identical)."""
+    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES
+
+
+def _num(value: Any) -> float:
+    try:
+        x = float(value)
+    except (TypeError, ValueError):
+        return 0.0
+    return 0.0 if (x != x or x in (float("inf"), float("-inf"))) else x
+
+
+@dataclass
+class SidePosition:
+    """One side of a contested claim, with its transparent evidence weight."""
+
+    claim_cluster_id: str
+    subject: str
+    predicate: str
+    weight_mass: float            # Phase-6 origin-cluster weight-mass behind this side
+    independent_origin_count: int
+    evidence_ids: tuple           # the cited evidence for this side (one-click span access)
+
+
+@dataclass
+class BothSidesBlock:
+    """A contested topic + its 2+ positions, ordered by evidence weight (NOT by "correctness")."""
+
+    subject: str
+    sides: list
+    source: str                   # which detector raised the contradiction (numeric/qualitative/semantic)
+    severity: str
+
+
+def compose_both_sides(
+    contradiction_edges: list,
+    weight_mass: list,
+    claims: list,
+) -> list[BothSidesBlock]:
+    """Compose one BothSidesBlock per contradiction edge — pure, no input mutation.
+
+    Maps each ``ContradictionEdge``'s two ``claim_cluster_ids`` to their Phase-6 ``ClaimWeightMass``
+    (weight + independent-origin count) and Phase-5 ``AtomicClaim`` info (subject/predicate/evidence_ids).
+    Sides are ordered by ``weight_mass`` DESC — disclosing which side has MORE evidence weight, never
+    asserting which is true; the low-weight side is kept, never dropped. A missing weight defaults to
+    0.0 / 0 (fail-soft disclosure, never a crash, never a fabricated weight).
+    """
+    weight_by_cluster: dict[str, Any] = {}
+    for cwm in (weight_mass or []):
+        ccid = str(getattr(cwm, "claim_cluster_id", "") or "")
+        if ccid:
+            weight_by_cluster[ccid] = cwm
+
+    info: dict[str, dict[str, Any]] = {}
+    for claim in (claims or []):
+        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
+        if not ccid:
+            continue
+        rec = info.setdefault(ccid, {"subject": "", "predicate": "", "evidence_ids": set()})
+        if not rec["subject"]:
+            rec["subject"] = str(getattr(claim, "subject", "") or "")
+        if not rec["predicate"]:
+            rec["predicate"] = str(getattr(claim, "predicate", "") or "")
+        eid = str(getattr(claim, "evidence_id", "") or "")
+        if eid:
+            rec["evidence_ids"].add(eid)
+
+    blocks: list[BothSidesBlock] = []
+    for edge in (contradiction_edges or []):
+        cluster_ids = tuple(getattr(edge, "claim_cluster_ids", ()) or ())
+        if len(cluster_ids) < 2:
+            continue  # a both-sides block needs two distinct positions
+        sides: list[SidePosition] = []
+        for raw_ccid in cluster_ids:
+            ccid = str(raw_ccid)
+            cwm = weight_by_cluster.get(ccid)
+            rec = info.get(ccid, {})
+            sides.append(SidePosition(
+                claim_cluster_id=ccid,
+                subject=str(rec.get("subject", "") or getattr(edge, "subject", "") or ""),
+                predicate=str(rec.get("predicate", "") or getattr(edge, "predicate", "") or ""),
+                weight_mass=_num(getattr(cwm, "weight_mass", 0.0)) if cwm is not None else 0.0,
+                independent_origin_count=(
+                    int(getattr(cwm, "independent_origin_count", 0) or 0) if cwm is not None else 0
+                ),
+                evidence_ids=tuple(sorted(rec.get("evidence_ids", set()))),
+            ))
+        # Order by weight DESC; stable claim_cluster_id tiebreak for determinism. This discloses which
+        # side carries more independent-origin evidence weight — it does NOT assert which is correct.
+        sides.sort(key=lambda s: (-s.weight_mass, s.claim_cluster_id))
+        blocks.append(BothSidesBlock(
+            subject=str(getattr(edge, "subject", "") or (sides[0].subject if sides else "")),
+            sides=sides,
+            source=str(getattr(edge, "source", "") or ""),
+            severity=str(getattr(edge, "severity", "") or "review"),
+        ))
+    return blocks
+
+
+def render_both_sides(blocks: list) -> str:
+    """Neutral markdown disclosure section. Empty string for no blocks (default-OFF byte-identity).
+
+    Uses only neutral framing ("the evidence diverges", "evidence weight", "independent origins",
+    "weigh them yourself") — never a judgemental label. Shows EVERY side with its weight; the user judges.
+    """
+    if not blocks:
+        return ""
+    lines = [
+        "## Where sources diverge",
+        "",
+        "On the topics below the evidence does not agree. Each position is shown with its evidence "
+        "weight (origin-cluster weight-mass) and the number of independent origins behind it, plus its "
+        "cited sources. Both positions are shown as they stand in the evidence; weigh them yourself.",
+        "",
+    ]
+    for block in blocks:
+        lines.append(f"### On {block.subject}, the evidence diverges")
+        for index, side in enumerate(block.sides):
+            label = chr(ord("A") + index)
+            cited = ", ".join(side.evidence_ids) if side.evidence_ids else "—"
+            lines.append(
+                f"- **Position {label}** — evidence weight {side.weight_mass:.2f} across "
+                f"{side.independent_origin_count} independent origin(s). Cited: {cited}."
+            )
+        lines.append("")
+    return "\n".join(lines).rstrip() + "\n"
diff --git a/tests/polaris_graph/synthesis/test_both_sides_phase7.py b/tests/polaris_graph/synthesis/test_both_sides_phase7.py
new file mode 100644
index 00000000..3ae011dc
--- /dev/null
+++ b/tests/polaris_graph/synthesis/test_both_sides_phase7.py
@@ -0,0 +1,119 @@
+"""I-cred-007 (Phase 7) — neutral both-sides composer. Offline, deterministic, no network."""
+from __future__ import annotations
+
+import pytest
+
+from src.polaris_graph.synthesis.both_sides import (
+    BothSidesBlock,
+    SidePosition,
+    bothsides_disclosure_enabled,
+    compose_both_sides,
+    render_both_sides,
+)
+
+_BANNED = ["fringe", "misinformation", "debunked", "conspiracy", "warning",
+           "unreliable", "false claim", "discredited"]
+
+
+def _edge(ccids, subject="vaccine safety", predicate="rate", source="numeric", severity="review"):
+    return type("E", (), {"claim_cluster_ids": tuple(ccids), "subject": subject,
+                          "predicate": predicate, "source": source, "severity": severity})()
+
+
+def _cwm(ccid, weight, origins):
+    return type("W", (), {"claim_cluster_id": ccid, "weight_mass": weight,
+                          "independent_origin_count": origins})()
+
+
+def _claim(ccid, eid, subject="vaccine safety", predicate="rate"):
+    return type("C", (), {"claim_cluster_id": ccid, "evidence_id": eid,
+                          "subject": subject, "predicate": predicate})()
+
+
+# ── AC-1 ──────────────────────────────────────────────────────────────────────
+def test_flag_default_off(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_BOTHSIDES_DISCLOSURE", raising=False)
+    assert bothsides_disclosure_enabled() is False
+
+
+@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
+def test_flag_on(monkeypatch, on):
+    monkeypatch.setenv("PG_SWEEP_BOTHSIDES_DISCLOSURE", on)
+    assert bothsides_disclosure_enabled() is True
+
+
+# ── AC-2: single edge, two sides ordered by weight DESC ──────────────────────
+def test_single_edge_two_sides_ordered_by_weight():
+    blocks = compose_both_sides(
+        [_edge(["cA", "cB"])],
+        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
+        [_claim("cA", "e0"), _claim("cB", "e1")],
+    )
+    assert len(blocks) == 1
+    b = blocks[0]
+    assert len(b.sides) == 2
+    assert b.sides[0].claim_cluster_id == "cA"  # higher weight first
+    assert abs(b.sides[0].weight_mass - 0.9) < 1e-9 and b.sides[0].independent_origin_count == 3
+    assert abs(b.sides[1].weight_mass - 0.2) < 1e-9 and b.sides[1].independent_origin_count == 1
+    assert b.sides[0].evidence_ids == ("e0",)
+
+
+# ── AC-3: render([]) is byte-empty (default-OFF byte-identity) ───────────────
+def test_render_empty_is_byte_empty():
+    assert render_both_sides([]) == ""
+    assert compose_both_sides([], [], []) == []
+
+
+# ── AC-4: neutral language + both weights shown ──────────────────────────────
+def test_render_is_neutral_and_shows_both_weights():
+    text = render_both_sides(compose_both_sides(
+        [_edge(["cA", "cB"])],
+        [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)],
+        [_claim("cA", "e0"), _claim("cB", "e1")],
+    )).lower()
+    for banned in _BANNED:
+        assert banned not in text, f"neutral-language guardrail: '{banned}' must not appear"
+    assert "0.90" in text and "0.20" in text  # BOTH sides' weights are disclosed
+    assert "diverge" in text and "weigh" in text  # neutral frame, user judges
+
+
+# ── AC-5: a claim with no contradiction edge produces no block ───────────────
+def test_claim_with_no_edge_no_block():
+    assert compose_both_sides([], [_cwm("cA", 0.9, 3)],
+                              [_claim("cA", "e0"), _claim("cB", "e1")]) == []
+
+
+# ── AC-6: the low-weight side is shown, never dropped ────────────────────────
+def test_low_weight_side_not_dropped():
+    b = compose_both_sides(
+        [_edge(["cA", "cB"])],
+        [_cwm("cA", 0.99, 5), _cwm("cB", 0.01, 1)],
+        [_claim("cA", "e0"), _claim("cB", "e1")],
+    )[0]
+    assert len(b.sides) == 2
+    assert any(s.claim_cluster_id == "cB" for s in b.sides)  # low-weight side present
+    assert "0.01" in render_both_sides([b])
+
+
+# ── AC-7: missing weight_mass -> 0.0 / 0 fail-soft (no crash, no fabrication) ─
+def test_missing_weight_is_fail_soft():
+    b = compose_both_sides(
+        [_edge(["cA", "cB"])],
+        [_cwm("cA", 0.9, 3)],  # cB has NO weight entry
+        [_claim("cA", "e0"), _claim("cB", "e1")],
+    )[0]
+    side_b = next(s for s in b.sides if s.claim_cluster_id == "cB")
+    assert side_b.weight_mass == 0.0 and side_b.independent_origin_count == 0
+
+
+# ── AC-8: purity — inputs not mutated ────────────────────────────────────────
+def test_no_input_mutation():
+    weights = [_cwm("cA", 0.9, 3), _cwm("cB", 0.2, 1)]
+    claims = [_claim("cA", "e0"), _claim("cB", "e1")]
+    compose_both_sides([_edge(["cA", "cB"])], weights, claims)
+    assert weights[0].weight_mass == 0.9 and claims[0].evidence_id == "e0"
+
+
+def test_edge_with_one_cluster_is_skipped():
+    """An edge with fewer than two claim_cluster_ids produces no block (needs two positions)."""
+    assert compose_both_sides([_edge(["cA"])], [_cwm("cA", 0.9, 3)], [_claim("cA", "e0")]) == []
```
