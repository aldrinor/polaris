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
## PHASE: I-cred-004b (#1161) — DIFF gate iter 1. Brief APPROVED (.codex/I-cred-004b/codex_brief_verdict.txt — conservative-min undated policy ACCEPTED as binding-no-inflation; fail-loud on missing evidence_id; amend docstrings/plan). This diff: (1) missing evidence_id -> FAIL-LOUD ValueError (was origin::idx{n} positional fallback); (2) module docstring amended — DATED cluster = strict copy-equality (authority not consulted), ALL-UNDATED cluster = lowest-authority canonical (conservative-min, monotonic non-increase, no inflation); (3) plan §148 binding-invariant amended to the dated/undated distinction; (4) regression test_missing_evidence_id_fails_loud. SMOKE: 28 passed.
```diff
diff --git a/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md b/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
index 3d70089d..452afe24 100644
--- a/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
+++ b/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
@@ -145,7 +145,7 @@ Each phase below = one GitHub Issue, one brief → Codex APPROVE → one diff 
 - **Faithfulness-safety:** analysis side-output; the conflict detectors keep their existing safety contracts (semantic fail-open never fabricates a conflict; qualitative escalates-to-review never silent-drops). OFF = byte-identical.
 
 ### Phase 6 — Weighted aggregation (replace count with weight-mass). [L5]
-- **Scope:** Replace COUNT aggregation with **origin-cluster weight-mass**, computed by this EXECUTABLE invariant (Codex iter-2 P1-2): group every supporting row by `(claim_cluster_id, origin_cluster_id)`; for each origin cluster L3 designates exactly ONE **canonical origin** (the syndication root / earliest independent publication; the other members are derivative copies — genuinely-INDEPENDENT corroboration has different content and forms its OWN cluster, it does not join an existing one). `cluster_mass = authority_score(canonical origin)`; copy/derivative members are attributed for disclosure ("N copies → 1 origin") but contribute ZERO to the mass. The claim-side weight-mass = Σ of `cluster_mass`, once per origin cluster within the claim cluster. **No row-level term, no averaging, no max-over-copies.** A row joins an existing `origin_cluster_id` only because L3 flagged it a copy of that cluster's canonical origin — so it adds NOTHING to the mass **even if its own `authority_score` is higher than the canonical origin's** (a high-authority verbatim republisher is still derivative; only its own *independent* content would form a new cluster). **Binding invariant (mathematically closed, Codex iter-3):** `weight_mass(rows + copied_row) == weight_mass(rows)` for ANY authority of the copier, whenever the added row joins an existing origin cluster. This requires **L3 to emit a stable `origin_cluster_id`, the canonical-origin designation, and membership** (NOT merely an `independent_origin_count` scalar) and L4 to emit `claim_cluster_id`, both BEFORE L5. Without it, copied rows re-inflate the false majority and the vax test fails. Applies in plan-sufficiency AND journal-only adequacy. Per-facet weighting preserved.
+- **Scope:** Replace COUNT aggregation with **origin-cluster weight-mass**, computed by this EXECUTABLE invariant (Codex iter-2 P1-2): group every supporting row by `(claim_cluster_id, origin_cluster_id)`; for each origin cluster L3 designates exactly ONE **canonical origin** (the syndication root / earliest independent publication; the other members are derivative copies — genuinely-INDEPENDENT corroboration has different content and forms its OWN cluster, it does not join an existing one). `cluster_mass = authority_score(canonical origin)`; copy/derivative members are attributed for disclosure ("N copies → 1 origin") but contribute ZERO to the mass. The claim-side weight-mass = Σ of `cluster_mass`, once per origin cluster within the claim cluster. **No row-level term, no averaging, no max-over-copies.** A row joins an existing `origin_cluster_id` only because L3 flagged it a copy of that cluster's canonical origin — so it adds NOTHING to the mass **even if its own `authority_score` is higher than the canonical origin's** (a high-authority verbatim republisher is still derivative; only its own *independent* content would form a new cluster). **Binding invariant (Codex iter-3 + #1161):** for a DATED origin cluster (canonical = earliest publication date) `weight_mass(rows + copied_row) == weight_mass(rows)` for ANY copier authority (strict copy-equality). For an ALL-UNDATED cluster the canonical is the LOWEST-`authority_score` member (conservative-min): the mass is MONOTONICALLY NON-INCREASING under copy additions — a higher-authority copy can NEVER inflate it (the binding no-inflation property), and a lower-authority copy can only LOWER it (honest, never inflating). Either way a copied row can NEVER inflate the false majority. This requires **L3 to emit a stable `origin_cluster_id`, the canonical-origin designation, and membership** (NOT merely an `independent_origin_count` scalar) and L4 to emit `claim_cluster_id`, both BEFORE L5. Without it, copied rows re-inflate the false majority and the vax test fails. Applies in plan-sufficiency AND journal-only adequacy. Per-facet weighting preserved.
 - **Files:** `plan_sufficiency_gate.py:312-317` (verdict math), `journal_only_filter.py:543-607` (`assess_journal_only_adequacy` weight path; demote `DEFAULT_MIN_DISTINCT_JOURNALS=12` count-floor to a weight-floor when journal-only is NOT protocol-pinned).
 - **Clinical source-type veto (Codex iter-1 P1-3 — wired, not a slogan):** a clinical-domain claim requires ≥1 **independent clinical-tier source (T1/T2 clinical)** in its origin-clustered support; if absent, Phase 6 emits a **`not_weight_adequate` / `clinical_source_type_veto`** signal REGARDLESS of news/commercial weight-mass; **Phase 7 (L6) consumes that signal to render ABSTAIN/fringe** (the rendering is Phase 7, not here). Wired to the existing clinical adequacy floor (`corpus_adequacy_gate.py` `_DEFAULT_DOMAIN_THRESHOLDS['clinical']`: `min_t1_count=3`, `min_t1_plus_t2=5`) The source-type veto is OWNED and EMITTED at Phase 6 (the `clinical_source_type_veto` signal); web/news/commercial weight can NEVER substitute for the clinical-tier floor; Phase 7 only RENDERS the resulting ABSTAIN/fringe. **Brief-time note (Codex iter-5 P2):** the per-claim source-type VETO (a claim needs ≥1 independent clinical-tier source) is DISTINCT from the corpus-level clinical adequacy FLOOR (`min_t1_count=3`, `min_t1_plus_t2=5`) — the Phase-6 implementation brief must keep them separate (the veto is a per-claim absence-check; the floor is a corpus threshold). They are not the same gate and must not be conflated.
 - **Offline tests:** **the vax adversarial test** (N independent-LOOKING-but-copied low-cred sources vs few high-cred — naive count flips to the false majority, weight+collapse picks the high-cred side); **copy-invariance fixture (Codex iter-3): a copier whose own `authority_score` is HIGHER than the cluster's canonical origin joins that origin cluster → `weight_mass` is UNCHANGED (the copier is derivative, excluded from the cluster mass)**; drb_72 regression **(CONDITIONAL on the journal-only audit, Decision #4)** — assert weight-floor passage for drb_72 ONLY if the audit confirms journal-only was an implementation choice, not a protocol requirement; otherwise assert on a non-protocol-pinned fixture (a protocol-pinned `source_restriction: journal_only` keeps its hard T1+T2 filter); corpus_approval still blocks material-deviation auto-approve even when weight-adequate (AuthorizedSweep still required); **clinical veto test (adequacy-level, Codex iter-2)** — a clinical claim with only news/commercial support is **NOT weight-adequate** / the clinical source-type veto fires (the T1/T2 clinical-tier floor is empty), even at high weight-mass. The ABSTAIN/fringe *rendering* is asserted in Phase 7 (L6 composition), not here.
diff --git a/src/polaris_graph/synthesis/independence_collapse.py b/src/polaris_graph/synthesis/independence_collapse.py
index 5b60eead..fbcd5d21 100644
--- a/src/polaris_graph/synthesis/independence_collapse.py
+++ b/src/polaris_graph/synthesis/independence_collapse.py
@@ -27,16 +27,21 @@ echo-collapse false-positive bound, plan §6 RISKS).
 
 CANONICAL-ORIGIN INVARIANT (the load-bearing safety property)
 =============================================================
-Each cluster designates exactly ONE **canonical origin** — the earliest /
-seed member — using ONLY an order signal: an explicit publication-date key
-when present and parseable, else the corpus order (lowest input index).
-The per-row ``authority_score`` is DELIBERATELY NOT consulted for the
-canonical choice or for cluster membership.
+Each cluster designates exactly ONE **canonical origin**. When ANY member
+carries a parseable publication date, the canonical is the EARLIEST-dated
+member and ``authority_score`` is NOT consulted — a DATED cluster keeps
+STRICT copy-invariance (adding a same/later/undated copy of ANY authority
+leaves the canonical + cluster_mass unchanged). When EVERY member is undated
+there is no date to identify the seed, so the canonical is the LOWEST-
+``authority_score`` member (conservative-min, Codex #1161): a higher-authority
+copy can NEVER become canonical or inflate cluster_mass, and the worst a copy
+can do is LOWER the mass (monotonic non-increase) — never inflate.
 
 Therefore: adding a copied row to an existing cluster — **even a copy whose
 own ``authority_score`` is HIGHER than the cluster's canonical origin** —
-does NOT change the cluster set nor its canonical origin. A high-authority
-verbatim republisher is still derivative; only its own *independent* content
+does NOT change the cluster set nor its canonical origin nor inflate its
+mass. A high-authority verbatim republisher is still derivative; only its own
+*independent* content
 would form a new cluster. This is exactly what lets the L5 weighted tally
 (``cluster_mass = authority_score(canonical_origin)``, copies contribute
 zero) be uninflatable by copies. The invariant is proven by
@@ -405,18 +410,23 @@ def collapse_independent_origins(
 
     for member_indices in members_by_root.values():
         member_indices = sorted(member_indices)
-        # Canonical = earliest/seed by the order key (authority NOT consulted).
+        # Canonical = earliest-dated origin (authority not consulted), or for an all-undated
+        # cluster the LOWEST-authority member (conservative-min, no inflation — Codex #1161).
         canonical_index = min(
             member_indices, key=lambda idx: _order_key(rows[idx], idx)
         )
-        # Stable, copy-immune id: derived from the canonical row's EVIDENCE IDENTITY, NOT
-        # its input position — so a copy added BEFORE the canonical (prepended) does not
-        # shift the index and change the id (Codex iter-2 P2). Only when the canonical row
-        # carries no evidence_id do we fall back to the index.
+        # Stable, copy-immune id: derived from the canonical row's EVIDENCE IDENTITY, NOT its
+        # input position — so a copy added BEFORE the canonical (prepended) does not shift the
+        # index and change the id (Codex iter-2 P2). A missing evidence_id is a FAIL-LOUD data
+        # error (Codex #1161), never a position-relative fallback.
         canonical_eid = str(rows[canonical_index].get("evidence_id", "") or "").strip()
-        origin_cluster_id = (
-            f"origin::{canonical_eid}" if canonical_eid else f"origin::idx{canonical_index}"
-        )
+        if not canonical_eid:
+            raise ValueError(
+                "independence_collapse: canonical row is missing 'evidence_id'; a stable "
+                "origin_cluster_id requires every evidence row to carry evidence_id "
+                "(Codex #1161 — a positional fallback id is not copy-stable)."
+            )
+        origin_cluster_id = f"origin::{canonical_eid}"
         copy_indices = [i for i in member_indices if i != canonical_index]
         member_hosts = sorted({domains[i] for i in member_indices} - {""})
         clusters.append(
diff --git a/tests/polaris_graph/test_independence_collapse.py b/tests/polaris_graph/test_independence_collapse.py
index 3329c96a..9cbbb0e8 100644
--- a/tests/polaris_graph/test_independence_collapse.py
+++ b/tests/polaris_graph/test_independence_collapse.py
@@ -530,3 +530,16 @@ def test_empty_text_rows_do_not_falsely_collapse() -> None:
     ]
     result = _collapse(rows)
     assert result.independent_origin_count == 2
+
+
+def test_missing_evidence_id_fails_loud() -> None:
+    """Codex #1161: a canonical row without evidence_id raises (no position-relative fallback
+    id). Real evidence rows always carry evidence_id; a missing one is a data bug, fail-loud."""
+    rows = [{"source_url": "https://x.com/a", "direct_quote": _PRESS_RELEASE}]  # no evidence_id
+    raised = False
+    try:
+        _collapse(rows)
+    except ValueError as exc:
+        raised = True
+        assert "evidence_id" in str(exc)
+    assert raised, "a canonical row missing evidence_id must fail loud, not fall back to an index id"
```
