HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex DIFF review — I-perm-003 (#1197): corpus-size-scaled evidence-selection budget — ITER 1 of 5

You are the ONLY gate. Review `.codex/I-perm-003/build_patch.patch` (2 files: src/polaris_graph/retrieval/evidence_selector.py + a new test).

## What + why
PREVENTATIVE forward guard: the generator-facing selection cap is a FIXED `max_rows` (PG_LIVE_MAX_EV_TO_GEN default 20). At a genuinely large pool that truncates to a constant slice. This adds a corpus-size-scaled budget BEHIND a new default-OFF flag `PG_SWEEP_SELECTION_SCALE`. HONEST SCOPE: on beatboth8 the selector drops 0 (the ~90% loss is UPSTREAM extraction, owned by I-perm-007) — NO beatboth8 fix is claimed; proven only on a synthetic enlarged pool; default OFF; NOT in any run slate/preflight.

## CLAIMS LEDGER (verify each)
1. **Byte-identical when OFF (the load-bearing safety claim).** `_scaled_max_rows` returns `(base_max_rows, None)` when `PG_SWEEP_SELECTION_SCALE` is unset/0/false/no/off (evidence_selector.py ~line 36-41, 72-98); the caller (line ~115) reassigns `max_rows` to the identical int and skips both telemetry blocks (lines ~135, ~147). VERIFY no behavioural change when OFF — no selection_strategy change, no note added, same selected rows.
2. **Single chokepoint.** Applied only in `select_evidence_for_generation` AFTER the relevance-floor early return (so the floor-mode path is untouched). VERIFY this is the only generator-facing cap and the placement can't double-apply.
3. **Floor semantics never regress.** `effective = max(base_max_rows, ceil(pool_size*frac))`, ceiling clamp also floored by base (lines ~86-91). VERIFY a small pool / low frac / ceiling-below-base can NEVER drop the budget below the existing cap.
4. **Faithfulness UNTOUCHED.** Only the selection BUDGET (how many rows reach the generator) changes — NOT strict_verify, the §-1.1 numeric grounding, provenance, or any per-claim gate. VERIFY no faithfulness gate is weakened.
5. **Best-ranked, not first-N.** No new reranker; relies on the existing tier-balanced + relevance/recency ordering. VERIFY the scaled budget feeds best-ranked rows (the test `test_flag_on_feeds_best_ranked_not_first_n` uses an inverted-relevance pool).
6. **LAW VI / no magic numbers:** all knobs env-driven (`PG_SWEEP_SELECTION_SCALE`, `_FRAC`, `_CEILING`); named constants.

## Evidence pack (I ran these on the MAIN tree, this session — not the agent's self-report)
- `pytest tests/polaris_graph/test_selection_scale_iperm003.py tests/polaris_graph/test_m201_evidence_selection.py` → **16 passed** (7 new + 9 existing selector).
- `pytest tests/polaris_graph/replay/` (flag UNSET) → **20 passed, 1 xfailed** (no regression).
- Agent reported the broader byte-identical proof: 152 existing selector tests pass with the flag UNSET (test_m42d/e/c floors, m46, m51 custody, source_diversity, recency, pass2). VERIFY the OFF-path is truly inert.

## Red-team focus
The HIGHEST-stakes question: is the OFF path provably byte-identical (no clinical run can change behaviour unless an operator explicitly sets the flag)? And does raising the selection budget have ANY path to weakening a per-claim faithfulness gate downstream? Be adversarial.

## Output schema (REQUIRED — last `verdict:` line parsed by CI)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

========== THE DIFF UNDER REVIEW ==========

diff --git a/src/polaris_graph/retrieval/evidence_selector.py b/src/polaris_graph/retrieval/evidence_selector.py
index a8a5dc8f..fb5f9fb6 100644
--- a/src/polaris_graph/retrieval/evidence_selector.py
+++ b/src/polaris_graph/retrieval/evidence_selector.py
@@ -569,6 +569,98 @@ def _domain_cap_config() -> tuple[bool, float]:
     return enabled, frac
 
 
+# ── I-perm-003 (#1197): corpus-size-scaled evidence-selection budget ─────────
+# The generator-facing cap is a FIXED `max_rows` (PG_LIVE_MAX_EV_TO_GEN, default
+# 20 — #1070/#1078). At 1000-URL retrieval the fixed cap truncates the pool to a
+# constant slice regardless of how much best-ranked evidence the corpus actually
+# holds. This PREVENTATIVE knob scales the selection budget WITH the pool size so
+# a larger corpus feeds proportionally more BEST-ranked rows (the existing
+# tier-balanced + relevance/recency truncation already picks best-ranked, never
+# first-N — this only raises the budget it operates under).
+#
+# HONEST SCOPE: on the beatboth8 corpus the selector drops 0 sources (the ~90%
+# loss is UPSTREAM extraction, owned by I-perm-007), so this changes nothing
+# there. It is a forward guard for when the upstream pool is genuinely large.
+#
+# DEFAULT OFF. When `PG_SWEEP_SELECTION_SCALE` is unset/0/false/no/off the helper
+# returns `base_max_rows` UNCHANGED and `select_evidence_for_generation` is
+# byte-identical to the prior behaviour (no reassignment, no telemetry).
+#
+# FLOOR semantics: effective = max(base_max_rows, ceil(pool_size * frac)),
+# optionally clamped to a ceiling. The `max(...)` guarantees scaling NEVER drops
+# the budget below the operator/code cap (a small pool with a low frac keeps the
+# existing cap — never a regression).
+_SELECTION_SCALE_FRAC_DEFAULT = 0.30
+# 0 = no ceiling (scale unbounded with the pool). A positive value clamps the
+# scaled budget so an enormous pool can't blow past an operator-set ceiling.
+_SELECTION_SCALE_CEILING_DEFAULT = 0
+
+
+def _selection_scale_enabled() -> bool:
+    """Flag `PG_SWEEP_SELECTION_SCALE` (default OFF). ON only on explicit
+    truthy ('1'/'true'/'yes'/'on'). OFF → byte-identical prior selection AND
+    no scaling telemetry. Inverse default of `_env_flag_on` ON-by-default."""
+    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE", "0").strip().lower()
+    return raw in ("1", "true", "yes", "on")
+
+
+def _selection_scale_frac() -> float:
+    """Budget-per-pool-row fraction `PG_SWEEP_SELECTION_SCALE_FRAC`
+    (default 0.30). Non-positive / unparseable → default (FAIL SOFT to a sane
+    positive fraction; a 0 frac would make scaling a no-op via the floor)."""
+    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE_FRAC", "").strip()
+    if not raw:
+        return _SELECTION_SCALE_FRAC_DEFAULT
+    try:
+        frac = float(raw)
+    except (ValueError, TypeError):
+        return _SELECTION_SCALE_FRAC_DEFAULT
+    return frac if frac > 0 else _SELECTION_SCALE_FRAC_DEFAULT
+
+
+def _selection_scale_ceiling() -> int:
+    """Optional absolute ceiling `PG_SWEEP_SELECTION_SCALE_CEILING`
+    (default 0 = no ceiling). Clamps the scaled budget so an enormous pool can't
+    overshoot an operator cap. Values <= 0 / unparseable → no ceiling."""
+    raw = os.environ.get("PG_SWEEP_SELECTION_SCALE_CEILING", "").strip()
+    if not raw:
+        return _SELECTION_SCALE_CEILING_DEFAULT
+    try:
+        ceiling = int(raw)
+    except (ValueError, TypeError):
+        return _SELECTION_SCALE_CEILING_DEFAULT
+    return ceiling if ceiling > 0 else _SELECTION_SCALE_CEILING_DEFAULT
+
+
+def _scaled_max_rows(pool_size: int, base_max_rows: int) -> tuple[int, str | None]:
+    """Corpus-size-scaled selection budget (I-perm-003, default OFF).
+
+    Returns ``(effective_max_rows, note)``. When the flag is OFF, returns
+    ``(base_max_rows, None)`` — the caller MUST treat that as a byte-identical
+    no-op (no telemetry note appended). When ON, returns the FLOOR-guarded scaled
+    budget ``max(base_max_rows, ceil(pool_size * frac))`` (optionally clamped to a
+    ceiling) plus a single telemetry string for the selection notes.
+    """
+    if not _selection_scale_enabled():
+        return base_max_rows, None
+    frac = _selection_scale_frac()
+    ceiling = _selection_scale_ceiling()
+    scaled = math.ceil(pool_size * frac)
+    effective = max(base_max_rows, scaled)
+    clamped = False
+    if ceiling > 0 and effective > ceiling:
+        # Never below the base cap even when the ceiling is < base (floor wins).
+        effective = max(base_max_rows, ceiling)
+        clamped = True
+    note = (
+        f"selection_scale pool={pool_size} frac={frac} "
+        f"base_max_rows={base_max_rows} scaled={scaled} "
+        f"effective={effective} ceiling={ceiling or 'none'}"
+        f"{' clamped' if clamped else ''}"
+    )
+    return effective, note
+
+
 def _row_query_origin(row: dict[str, Any]) -> str:
     """The sub-query that surfaced the row (`query_origin`), or `_unlabeled`."""
     return str(row.get("query_origin") or "") or "_unlabeled"
@@ -1069,6 +1161,15 @@ def select_evidence_for_generation(
             primary_trial_anchors=primary_trial_anchors,
         )
 
+    # I-perm-003 (#1197): corpus-size-scaled budget (default OFF). Fixed-cap
+    # (tier-balanced max_rows) path only — the relevance-floor mode above already
+    # returns without a cap. When the flag is OFF, `_scaled_max_rows` returns the
+    # passed `max_rows` UNCHANGED and `_selection_scale_note` is None, so every
+    # branch below (short-pool + truncation) is byte-identical to the prior path
+    # and NO telemetry is appended. When ON, the floor-guarded scaled budget
+    # raises `max_rows` so a large pool feeds more BEST-ranked rows.
+    max_rows, _selection_scale_note = _scaled_max_rows(len(scored), max_rows)
+
     # M-46 (2026-04-22): when total <= max_rows, still keep everything,
     # BUT compute floor-detection + deterministic priority ordering
     # + telemetry so downstream consumers see the same reservation
@@ -1085,13 +1186,19 @@ def select_evidence_for_generation(
     # Notes include the m42e_primary_floor / m42c_mechanism_floor /
     # m42d_hc_quota_expand entries seen on truncating runs.
     if len(scored) <= max_rows:
-        return _m46_short_pool_ordered_selection(
+        _short = _m46_short_pool_ordered_selection(
             evidence_rows=evidence_rows,
             scored=scored,
             full_counts=full_counts,
             max_rows=max_rows,
             primary_trial_anchors=primary_trial_anchors,
         )
+        # I-perm-003: surface the scaling note (ON-mode only; None when OFF →
+        # byte-identical). The scaled budget can flip a pool that USED to
+        # truncate into this keep-everything short-pool branch.
+        if _selection_scale_note is not None:
+            _short.notes.append(_selection_scale_note)
+        return _short
 
     # Floors: reserve at least 1 slot for each present T1, T2, T3
     # (high-value tiers) if pool has any.
@@ -1559,6 +1666,10 @@ def select_evidence_for_generation(
         selected_counts[tier] = selected_counts.get(tier, 0) + 1
 
     notes: list[str] = []
+    # I-perm-003 (#1197): corpus-size-scaled budget telemetry (ON-mode only;
+    # None when the flag is OFF → byte-identical, no note).
+    if _selection_scale_note is not None:
+        notes.append(_selection_scale_note)
     # #956: source-diversity telemetry (empty unless a pass fired).
     notes.extend(_diversity_notes)
     # M-42e pass-2: surface the primary-floor telemetry so sweep
diff --git a/tests/polaris_graph/test_selection_scale_iperm003.py b/tests/polaris_graph/test_selection_scale_iperm003.py
new file mode 100644
index 00000000..354e111d
--- /dev/null
+++ b/tests/polaris_graph/test_selection_scale_iperm003.py
@@ -0,0 +1,217 @@
+"""I-perm-003 (#1197) — corpus-size-scaled evidence-selection budget (offline, deterministic).
+
+PREVENTATIVE knob: the generator-facing cap is a FIXED ``max_rows`` (PG_LIVE_MAX_EV_TO_GEN,
+default 20 — #1070/#1078). At a genuinely large pool the fixed cap truncates to a constant slice
+regardless of how much best-ranked evidence the corpus holds. ``PG_SWEEP_SELECTION_SCALE`` (default
+OFF) scales the budget WITH pool size so a large corpus feeds proportionally more BEST-ranked rows.
+
+HONEST SCOPE (do NOT over-claim): on the beatboth8 corpus the selector drops 0 sources — the ~90%
+loss is UPSTREAM extraction (I-perm-007), so this is a forward guard, proven here ONLY on a SYNTHETIC
+enlarged pool. No beatboth8 fix is claimed; the flag is default OFF and not in any run slate.
+
+Proves:
+  (a) flag ON  -> scaled selector feeds >46 BEST-ranked items from a large (~500-row) pool;
+  (b) flag OFF -> selection result is byte-identical to the current selector on the SAME input
+      (same selected_rows, same telemetry — the fixed cap throttles to exactly max_rows);
+  (c) FLOOR semantics: a small pool / low frac never scales BELOW the base cap;
+  (d) the scaled selection is genuinely BEST-ranked (highest-relevance rows), not first-N;
+  (e) ON-mode emits a single ``selection_scale`` telemetry note; OFF-mode emits none.
+"""
+
+from __future__ import annotations
+
+import os
+
+import pytest
+
+from src.polaris_graph.retrieval.evidence_selector import (
+    select_evidence_for_generation,
+)
+
+_SCALE_ENV = (
+    "PG_SWEEP_SELECTION_SCALE",
+    "PG_SWEEP_SELECTION_SCALE_FRAC",
+    "PG_SWEEP_SELECTION_SCALE_CEILING",
+)
+
+
+def _clear_scale_env() -> None:
+    for k in _SCALE_ENV:
+        os.environ.pop(k, None)
+
+
+def _synthetic_pool(n: int):
+    """Build ~n representative evidence rows + matching classified sources.
+
+    Rows replicate a representative shape (evidence_id, direct_quote, tier, url,
+    statement) with DISTINCT ids/urls and a MONOTONE-DECREASING relevance signal:
+    earlier rows share more content words with the fixed research question, so a
+    correct selector keeps the EARLIER (higher-relevance) rows when it truncates.
+    The question/statement vocabulary makes ``_row_relevance`` (lexical overlap)
+    meaningful rather than all-equal.
+    """
+    question = "tirzepatide weight glycemic efficacy cardiovascular safety outcomes"
+    q_words = question.split()
+    rows = []
+    sources = []
+    for i in range(n):
+        eid = f"ev_{i:04d}"
+        url = f"https://example.org/source/{i}"
+        tier = (i % 7) + 1  # 1..7 -> string-coerced; mirrors iready001 fixture
+        # Higher-index rows share FEWER question words -> lower lexical relevance.
+        n_words = max(1, len(q_words) - (i % len(q_words)))
+        statement = (
+            " ".join(q_words[:n_words])
+            + f" finding number {i} reported a {i % 100}.0 percent change"
+        )
+        rows.append({
+            "evidence_id": eid,
+            "direct_quote": f"finding {i} with value {i % 100}.0 percent in cohort {i}.",
+            "statement": statement,
+            "tier": tier,
+            "url": url,
+        })
+        sources.append(type("S", (), {"url": url, "tier": tier})())
+    return question, rows, sources
+
+
+def _select(question, rows, sources, max_rows):
+    return select_evidence_for_generation(
+        research_question=question,
+        protocol={},
+        classified_sources=sources,
+        evidence_rows=rows,
+        max_rows=max_rows,
+    )
+
+
+def test_flag_off_is_the_fixed_cap_throttle():
+    # (b) OFF-mode: a 500-row pool at base cap 20 selects EXACTLY 20 (the fixed throttle).
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(500)
+    sel = _select(question, rows, sources, max_rows=20)
+    assert len(sel.selected_rows) == 20, (
+        f"OFF-mode must honor the fixed max_rows cap; got {len(sel.selected_rows)}"
+    )
+    # OFF-mode emits NO selection_scale telemetry.
+    assert not any(note.startswith("selection_scale") for note in sel.notes)
+    _clear_scale_env()
+
+
+def test_flag_off_is_byte_identical_to_baseline():
+    # (b) OFF result == result with the env var explicitly absent: same rows, same notes.
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(500)
+    baseline = _select(question, rows, sources, max_rows=20)
+
+    # Explicit falsey values must ALSO be a no-op (default-OFF idiom).
+    for falsey in ("0", "false", "no", "off", "OFF", "False"):
+        os.environ["PG_SWEEP_SELECTION_SCALE"] = falsey
+        again = _select(question, rows, sources, max_rows=20)
+        assert (
+            [r["evidence_id"] for r in again.selected_rows]
+            == [r["evidence_id"] for r in baseline.selected_rows]
+        ), f"PG_SWEEP_SELECTION_SCALE={falsey!r} must be byte-identical to OFF"
+        assert again.notes == baseline.notes, (
+            f"PG_SWEEP_SELECTION_SCALE={falsey!r} must not add/alter telemetry"
+        )
+    _clear_scale_env()
+
+
+def test_flag_on_scales_budget_above_46(monkeypatch):
+    # (a) ON-mode: a 500-row pool at base cap 20 selects >46 (scaled with pool size).
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(500)
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE", "1")
+    sel = _select(question, rows, sources, max_rows=20)
+    assert len(sel.selected_rows) > 46, (
+        f"ON-mode should feed >46 best-ranked rows from a 500-row pool; "
+        f"got {len(sel.selected_rows)}"
+    )
+    # default frac 0.30 -> ~150 expected; assert it is materially scaled, not the 20 cap.
+    assert len(sel.selected_rows) >= 100
+    # ON-mode emits exactly one selection_scale telemetry note.
+    scale_notes = [n for n in sel.notes if n.startswith("selection_scale")]
+    assert len(scale_notes) == 1, f"expected one selection_scale note, got {scale_notes}"
+    assert "effective=" in scale_notes[0]
+    _clear_scale_env()
+
+
+def test_flag_on_feeds_best_ranked_not_first_n(monkeypatch):
+    # (d) The scaled selection must be BEST-ranked (highest lexical relevance), not first-N.
+    # Build a pool whose relevance order is INVERTED vs index order: LAST rows are most relevant.
+    _clear_scale_env()
+    question = "alpha beta gamma delta epsilon zeta relevance signal anchor"
+    q_words = question.split()
+    rows = []
+    sources = []
+    n = 500
+    for i in range(n):
+        eid = f"ev_{i:04d}"
+        url = f"https://example.org/inv/{i}"
+        # Relevance INCREASES with index: high-index rows share MORE question words.
+        n_words = min(len(q_words), 1 + (i * len(q_words)) // n)
+        rows.append({
+            "evidence_id": eid,
+            "direct_quote": f"row {i} value {i % 50}.0 units.",
+            "statement": " ".join(q_words[:n_words]) + f" measurement {i}",
+            "tier": "T1",  # single tier so tier-quota can't confound the ranking check
+            "url": url,
+        })
+        sources.append(type("S", (), {"url": url, "tier": "T1"})())
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE", "1")
+    sel = _select(question, rows, sources, max_rows=20)
+    selected_idx = {int(r["evidence_id"].split("_")[1]) for r in sel.selected_rows}
+    # If it were first-N it would contain low indices (least relevant). Best-ranked
+    # means the high-index (most relevant) rows dominate the selection.
+    assert max(selected_idx) == n - 1, "most-relevant (highest-index) row must be selected"
+    # The single most-relevant half must be over-represented vs the least-relevant half.
+    top_half = sum(1 for i in selected_idx if i >= n // 2)
+    bottom_half = sum(1 for i in selected_idx if i < n // 2)
+    assert top_half > bottom_half, (
+        f"best-ranked selection should favor the relevant (top) half; "
+        f"top={top_half} bottom={bottom_half}"
+    )
+    _clear_scale_env()
+
+
+def test_floor_semantics_small_pool_never_below_base_cap(monkeypatch):
+    # (c) A SMALL pool (30 rows) at base cap 20, ON with a low frac, must NOT drop below 20.
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(30)
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE", "1")
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE_FRAC", "0.10")  # 30*0.10 = 3 < base 20
+    sel = _select(question, rows, sources, max_rows=20)
+    # Pool (30) > effective floor (max(20, 3) = 20) -> truncates to exactly 20, never below.
+    assert len(sel.selected_rows) == 20, (
+        f"FLOOR: scaling must never drop below the base cap; got {len(sel.selected_rows)}"
+    )
+    _clear_scale_env()
+
+
+def test_ceiling_clamps_but_floor_still_wins(monkeypatch):
+    # The optional ceiling clamps an enormous scaled budget; the base-cap floor still wins.
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(500)
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE", "1")
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE_CEILING", "60")  # 500*0.30=150 -> clamp to 60
+    sel = _select(question, rows, sources, max_rows=20)
+    assert len(sel.selected_rows) == 60, (
+        f"ceiling should clamp the scaled budget to 60; got {len(sel.selected_rows)}"
+    )
+    scale_notes = [n for n in sel.notes if n.startswith("selection_scale")]
+    assert scale_notes and "clamped" in scale_notes[0]
+    _clear_scale_env()
+
+
+def test_floor_wins_even_when_ceiling_below_base(monkeypatch):
+    # Degenerate config: ceiling < base cap. The base-cap FLOOR must still win (no regression).
+    _clear_scale_env()
+    question, rows, sources = _synthetic_pool(500)
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE", "1")
+    monkeypatch.setenv("PG_SWEEP_SELECTION_SCALE_CEILING", "5")  # below base 20
+    sel = _select(question, rows, sources, max_rows=20)
+    assert len(sel.selected_rows) == 20, (
+        f"ceiling below base must not drop below base cap; got {len(sel.selected_rows)}"
+    )
+    _clear_scale_env()
