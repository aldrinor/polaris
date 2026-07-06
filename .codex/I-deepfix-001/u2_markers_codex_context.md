HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks; APPROVE iff zero P0 and zero P1.

# Wave-3a U2 diff review — per-module ACTIVATION FIRE MARKERS + 2 silent-failure fail-loud fixes

CONTEXT: POLARIS I-deepfix-001 (#1344). The dual-approved routing proof found the new-core modules were DARK on the paid path. Before wiring their flags ON, each activated module needs a stable "[activation] <module>:" fire-marker log line so the activation canary (built next) can prove the NEW module actually fired and did NOT silently degrade to the old path. This diff (Claude-authored, you are the independent gate) adds those markers across 6 files + makes two previously-silent failures loud. It does NOT touch verified_compose.py or run_gate_b.py, and does NOT touch the faithfulness engine (strict_verify / consolidation_nli / 4-role D8 / provenance verify / span grounding) — logging/telemetry only, plus one warning-instead-of-swallow.

REVIEW for:
1. **FAITHFULNESS ENGINE BYTE-UNTOUCHED.** Every change is an additive log line or a telemetry out-param; NO verdict/threshold/gate/judge logic changed. The one behavior change is `except: ...=None` → `except ... as e: logger.warning(...); ...=None` (numeric swallow made loud, gated behind PG_NUMERIC_COMPARATOR). The finding_dedup change threads a `telemetry` out-param to surface the previously-silent cross-encoder OOM fallback (degraded=True) — confirm it does NOT change the CLUSTERING RESULT, only reports it. Confirm no strict_verify/NLI/provenance code touched.
2. **OFF = NO EMIT = BYTE-IDENTICAL.** Each marker sits behind its own flag read at CALL time; when the flag is OFF, NO log line is emitted and NO telemetry field appears → the run_log + manifests are byte-identical to pre-U2. Confirm every marker (and the numeric warning + the finding_dedup telemetry field) is gated. Confirm the anchor_equality tripwire marker (cross_source_synthesis.py:580) does not emit in normal ON operation (it is a degrade-detector).
3. **MARKERS ARE STRUCTURAL, NOT QUANTITY THRESHOLDS (§-1.3).** Each marker reports a presence + COUNT (directional_merges/pairs/upgraded/facets/expanded_queries/minimized/accepted) + boolean honesty fields (degraded/noop/build_ok/wall_truncated/input_threaded). A count of 0 with the flag ON is itself the eligible-yet-zero signal — there is NO "must be >= K" target anywhere. Confirm no banned count threshold is introduced.
4. **HONESTY BOOLS CORRECT.** degraded=True on the finding_dedup cross-encoder fallback (None on non-empty reps → fail-closed singletons); noop=True when basket_consume returns the input graph unchanged; build_ok=False when the numeric lookup build swallowed; input_threaded reflects whether equiv_clusters+agree_map reached the plan-driven pairer. Confirm each bool actually reflects its condition.
5. **provenance_generator.py NOT touched** — the reanchor markers surface via run-level telemetry snapshot in run_honest_sweep_r3.py (reset_reanchor_telemetry before gen, get_reanchor_telemetry after). Confirm the reanchored_local_window (:2892) and reanchored_argmax (:1614) literals are untouched.
6. Any P0/P1: a marker that changes a result, an ungated emit (OFF not byte-identical), a banned count threshold, a wrong honesty bool, or reformat/scope-creep. (git diff -w == git diff confirmed per file — no whitespace churn.)

THE COMBINED DIFF (6 files):
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 065ef7b1..6a8fcbc2 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -105,6 +105,12 @@ from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
     get_token_honesty_telemetry,
     reset_token_honesty_telemetry,
     _token_honest_drop_enabled,
+    # I-deepfix-001 Wave-3a (#1344): per-run reset + snapshot of the re-anchor counters so the
+    # provenance-reanchor activation marker surfaces the argmax-leg firing at RUN level. `_provenance_
+    # reanchor_enabled` gates reset/snapshot/emit so a PG_PROVENANCE_REANCHOR=0 run stays byte-identical.
+    get_reanchor_telemetry,
+    reset_reanchor_telemetry,
+    _provenance_reanchor_enabled,
 )
 from src.polaris_graph.llm.openrouter_client import (  # noqa: E402
     BudgetExceededError,
@@ -3396,6 +3402,12 @@ def _basket_corroboration_block(
     seen_blocks: set[str] = set()
     _dedup_blocks = corroboration_block_dedup_enabled()
     blocks: list[str] = []
+    # I-deepfix-001 Wave-3a (#1344): ADDITIVE min-cite-set activation accumulators (one aggregated marker
+    # per corroboration block, emitted before the returns below). Behavior-inert — they only feed the
+    # ``[activation] min_cite_set:`` line; nothing is dropped and no render text changes.
+    _mc_minimized = 0
+    _mc_demoted = 0
+    _mc_faults = 0
     for b in bibliography:
         for basket in (b.get("baskets") or []):
             ccid = str(basket.get("claim_cluster_id") or "")
@@ -3613,6 +3625,10 @@ def _basket_corroboration_block(
                         _min_res = _minimize_citation_set(claim, _render_members)
                         _inline_members = _min_res.inline_members
                         _min_cite_active = True
+                        # Wave-3a (#1344): ADDITIVE activation counts (keep-all — demoted members still
+                        # render as weight-channel SUPPORT bullets below, none dropped).
+                        _mc_minimized += len(_min_res.inline_members)
+                        _mc_demoted += len(_min_res.weight_members)
                     except Exception as _mc_exc:  # noqa: BLE001 — fail-open: keep ALL inline, never crash
                         logging.getLogger(__name__).warning(
                             "[min_cite_set] wiring fault (%s); keeping all members inline (fail-open).",
@@ -3620,6 +3636,7 @@ def _basket_corroboration_block(
                         )
                         _inline_members = _render_members
                         _min_cite_active = False
+                        _mc_faults += 1  # build_ok=false signal for the activation marker
                 _inline_ev_ids = {str(m.get("evidence_id") or "") for m in _inline_members}
                 # Header multi-cite = the INLINE members' ``[N]`` only (== all members when the minimizer
                 # is inactive => byte-identical). Demoted members' numbers are withheld from the claim's
@@ -3689,6 +3706,20 @@ def _basket_corroboration_block(
                     continue
                 seen_blocks.add(_block)
             blocks.append(_block)
+    # I-deepfix-001 Wave-3a (#1344): the min-cite-set ACTIVATION fire marker — ONE aggregated line per
+    # corroboration block. Emitted ONLY when PG_MIN_CITE_SET is ON so OFF is byte-identical (no line).
+    # minimized = inline ``[N]`` citations kept; demoted_to_weight = corroborators moved to the weight
+    # channel (keep-all, none dropped); build_ok=false surfaces any fail-open minimizer fault. minimized=0
+    # with the flag ON (e.g. the layer-2 dependency OFF so the minimizer never ran) is the eligible-yet-zero
+    # signal the canary reads. Structural presence + counts, never a threshold (§-1.3).
+    from src.polaris_graph.generator.citation_set_minimizer import (  # noqa: PLC0415
+        min_cite_set_enabled as _min_cite_set_enabled_marker,
+    )
+    if _min_cite_set_enabled_marker():
+        logging.getLogger(__name__).info(
+            "[activation] min_cite_set: minimized=%d demoted_to_weight=%d build_ok=%s",
+            _mc_minimized, _mc_demoted, _mc_faults == 0,
+        )
     if not blocks:
         return ""
     return (
@@ -14640,6 +14671,11 @@ async def run_one_query(
         # it cannot outlive the phase or land a stale "generation_in_progress" after a terminal
         # stage. Faithfulness-safe: pure observability — it never reads/writes a span, provenance,
         # strict_verify / NLI / 4-role check, or any verdict.
+        # I-deepfix-001 Wave-3a (#1344): zero the re-anchor counters BEFORE generation so the snapshot
+        # below reflects THIS query only. Gated on PG_PROVENANCE_REANCHOR => an OFF run touches nothing
+        # (byte-identical). The counters are read + emitted after generation completes.
+        if _provenance_reanchor_enabled():
+            reset_reanchor_telemetry()
         _gen_hb_ticker = asyncio.ensure_future(
             _periodic_heartbeat_ticker(
                 _hb, "generation_in_progress", generation_heartbeat_tick_seconds(),
@@ -14829,6 +14865,25 @@ async def run_one_query(
              f"dropped={multi.total_sentences_dropped}, "
              f"limitations_words={len(multi.limitations_text.split())}")
 
+        # I-deepfix-001 Wave-3a (#1344): provenance-reanchor ACTIVATION fire marker at RUN level (via the
+        # _log tee sink). Emitted ONLY when PG_PROVENANCE_REANCHOR is ON (OFF => no reset/snapshot/line =>
+        # byte-identical). accepted = total re-anchor recoveries this run; reanchored_argmax = the span-
+        # resolver boilerplate-aware argmax-leg recoveries (the span-resolver positive signal). build_ok is
+        # false only if the telemetry read itself faults. Structural presence + counts, never a threshold.
+        if _provenance_reanchor_enabled():
+            try:
+                _reanchor_snap = get_reanchor_telemetry()
+                _log(
+                    "[activation] provenance_reanchor: accepted=%d reanchored_argmax=%d build_ok=%s"
+                    % (
+                        int(_reanchor_snap.get("reanchor_recovered", 0)),
+                        int(_reanchor_snap.get("reanchor_argmax_recovered", 0)),
+                        True,
+                    )
+                )
+            except Exception:  # noqa: BLE001 — a telemetry read must never break the paid run
+                _log("[activation] provenance_reanchor: accepted=0 reanchored_argmax=0 build_ok=False")
+
         # A12 (iarch006 epic-failure): post-GENERATION checkpoint — DATA ONLY (raw drafts + identity
         # hashes), written right after generation completes and BEFORE verification, so a resume can
         # re-enter before the verify/judge stages. Stores NO verdict; a resume re-runs every gate.
diff --git a/src/polaris_graph/generator/cross_source_synthesis.py b/src/polaris_graph/generator/cross_source_synthesis.py
index 8d3fea82..c4083027 100644
--- a/src/polaris_graph/generator/cross_source_synthesis.py
+++ b/src/polaris_graph/generator/cross_source_synthesis.py
@@ -562,12 +562,22 @@ def _anchor_candidate_pairs(baskets: list):
         anchor = _basket_anchor(b)
         if anchor:
             by_anchor.setdefault(anchor, []).append(b)
+    _emitted = 0
     for _anchor, group in by_anchor.items():
         if len(group) < 2:
             continue
         for i in range(len(group)):
             for j in range(i + 1, len(group)):
+                _emitted += 1
                 yield group[i], group[j]
+    # I-deepfix-001 Wave-3a (#1344): anchor-equality ACTIVATION DEGRADE tripwire. Emitted ONLY when
+    # PG_CROSS_SOURCE_BODY is ON — which in normal operation is exactly the case where the plan-driven
+    # pairing (NOT this legacy path) is used, so this marker stays ABSENT (the canary asserts absence). It
+    # fires only if the body ever degrades to anchor pairing under the ON flag. On the OFF path the flag is
+    # OFF => no line => byte-identical (the ``_emitted`` counter produces no output). This runs on generator
+    # exhaustion, which the single full-drain consumer loop guarantees.
+    if cross_source_body_enabled():
+        logger.info("[activation] cross_source_body: anchor_equality pairs=%d", _emitted)
 
 
 def _plan_driven_candidate_pairs(baskets: list, *, edges: Any, agree_map: Any, equiv_clusters: Any):
@@ -601,6 +611,7 @@ def _process_pair(
     entail_fn: Optional[Callable[[str, str], Optional[bool]]],
     clause_cache: dict,
     numeric_key_by_cluster: Optional[dict],
+    numeric_upgrade_counter: Optional[list] = None,
 ) -> Optional[str]:
     """Build ONE cross-source analytical unit for a candidate pair, or ``None`` when it fails to build.
 
@@ -659,6 +670,9 @@ def _process_pair(
             )
             if comp:
                 rel = comp
+                # Wave-3a (#1344): ADDITIVE activation count (never changes ``rel`` or the licensing).
+                if numeric_upgrade_counter is not None:
+                    numeric_upgrade_counter[0] += 1
     connective = LICENSED_CONNECTIVES.get(rel, LICENSED_CONNECTIVES["neutral"])
     # Strip clause_A's terminal so the join reads as one flowing sentence "[clause A]<connective>[clause B]".
     joined = _join_verified_clauses(
@@ -720,8 +734,19 @@ def compose_cross_source_analytical_units(
     # For the deterministic writer_fn/verify_fn the composer is given (precomputed-dict lookup / strict
     # verify) the RESULT is identical; only the number of internal calls changes (no observable effect).
     if cross_source_body_enabled():
-        candidate_pairs = _plan_driven_candidate_pairs(
+        # Materialize so the plan-driven pair COUNT can be reported by the activation marker; the single
+        # full-drain loop below is behaviorally identical to iterating the generator (same pairs, order).
+        candidate_pairs = list(_plan_driven_candidate_pairs(
             baskets, edges=edges, agree_map=agree_map, equiv_clusters=equiv_clusters
+        ))
+        # I-deepfix-001 Wave-3a (#1344): plan-driven ACTIVATION fire marker. Emitted ONLY under
+        # PG_CROSS_SOURCE_BODY (this branch) so OFF is byte-identical. ``input_threaded`` is true when the
+        # certified consolidation inputs (equiv_clusters / agree_map) were threaded — false means the
+        # pairing degraded to same-facet/edge/refuter candidacy only. Structural presence + count (§-1.3).
+        _input_threaded = bool(equiv_clusters) or bool(agree_map)
+        logger.info(
+            "[activation] cross_source_body: plan_driven pairs=%d input_threaded=%s degraded=%s",
+            len(candidate_pairs), _input_threaded, not _input_threaded,
         )
     else:
         candidate_pairs = _anchor_candidate_pairs(baskets)
@@ -729,6 +754,10 @@ def compose_cross_source_analytical_units(
     units: list[str] = []
     seen_pair_keys: set[frozenset] = set()
     eligible_pairs = 0
+    # Wave-3a (#1344): ADDITIVE numeric-comparator upgrade counter (a one-element mutable, threaded into
+    # ``_process_pair`` and incremented where a NEUTRAL pair is upgraded to ``comparison``). Behavior-inert
+    # — it only feeds the numeric_comparator activation marker emitted after the loop.
+    _numeric_upgrades = [0]
     # cluster_id -> Optional[str]; each basket's verified clause is built at most ONCE (deterministic given
     # the same basket/pool/fns), so caching changes call-count only, never the emitted units (see above).
     clause_cache: dict = {}
@@ -747,10 +776,24 @@ def compose_cross_source_analytical_units(
             edges=edges, equiv_clusters=equiv_clusters, agree_map=agree_map,
             entail_fn=entail_fn, clause_cache=clause_cache,
             numeric_key_by_cluster=numeric_key_by_cluster,
+            numeric_upgrade_counter=_numeric_upgrades,
         )
         if unit:
             units.append(unit)
 
+    # I-deepfix-001 Wave-3a (#1344): numeric-comparator ACTIVATION fire marker. Emitted ONLY when
+    # PG_NUMERIC_COMPARATOR is ON (OFF => no line => byte-identical). ``upgraded`` counts NEUTRAL pairs the
+    # deterministic comparator lifted to ``comparison``; ``build_ok`` is false when the upstream numeric
+    # merge-key lookup was not threaded (None) — the silent-swallow signal now made loud at the build site.
+    from src.polaris_graph.generator.numeric_comparator import (  # noqa: PLC0415
+        numeric_comparator_enabled as _numeric_comparator_enabled,
+    )
+    if _numeric_comparator_enabled():
+        logger.info(
+            "[activation] numeric_comparator: upgraded=%d build_ok=%s",
+            _numeric_upgrades[0], numeric_key_by_cluster is not None,
+        )
+
     if eligible_pairs and not units:
         # Fail-LOUD canary (the "verify the feature fired in output, not in config" rule): candidate
         # cross-source pairs EXISTED, yet zero analytical units survived per-clause re-verify/licensing.
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 3f5bd0b5..63f81192 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -4885,6 +4885,20 @@ def _two_sided_debate_enabled() -> bool:
     return os.getenv(_TWO_SIDED_DEBATE_ENV, "0").strip().lower() not in ("", "0", "false", "off", "no")
 
 
+def _emit_two_sided_debate_marker(leg2_inspected: int, con_disclosed: int) -> None:
+    """I-deepfix-001 Wave-3a (#1344): two-sided-debate ACTIVATION fire marker. Emitted ONLY when
+    PG_TWO_SIDED_DEBATE is ON so OFF is byte-identical (the run_log carries no ``[activation]`` line).
+    ``leg2_inspected`` = composed real units examined for a verified CON clause; ``con_disclosed`` = the
+    honest asymmetry disclosures appended (0 = both sides present, no note). Structural presence + counts,
+    never a threshold (§-1.3). Side-effect only; the composed disclosures are byte-untouched."""
+    if not _two_sided_debate_enabled():
+        return
+    logger.info(
+        "[activation] two_sided_debate: leg2_inspected=%d con_disclosed=%d",
+        int(leg2_inspected), int(con_disclosed),
+    )
+
+
 def _is_debate_section(section: Any) -> bool:
     """True iff the section's PLAN framing (``title`` + ``focus``) asks for both sides — pro/con,
     benefits/risks, positive vs negative, for/against. Uses the SHARED
@@ -5177,8 +5191,19 @@ async def _run_section(
                 _vc_numeric_keys = _vc_build_numeric_keys(
                     getattr(credibility_analysis, "claims", None) or []
                 )
-        except Exception:  # noqa: BLE001 — additive comparator lookup; never break composition
+        except Exception as _vc_numeric_exc:  # noqa: BLE001 — additive comparator lookup; never break composition
+            # I-deepfix-001 Wave-3a (#1344): FAIL-LOUD (was a silent ``= None`` swallow). Composition still
+            # proceeds fail-open (keys=None => the comparator is simply never consulted downstream — the
+            # numeric logic is UNCHANGED), but an ON-flag build failure is now surfaced so the
+            # numeric_comparator activation marker reads build_ok=false instead of the fault vanishing. The
+            # warning is gated on the flag so an OFF run stays byte-identical even if the import itself fails.
             _vc_numeric_keys = None
+            if os.getenv("PG_NUMERIC_COMPARATOR", "0").strip().lower() not in ("", "0", "false", "off", "no"):
+                logger.warning(
+                    "[multi_section] %s numeric_comparator key-lookup build failed (%s); cross-source "
+                    "numeric comparison DISABLED for this section (build_ok=false)",
+                    getattr(section, "title", "?"), _vc_numeric_exc,
+                )
         # I-beatboth-005 (#1282): the FAITHFUL ABSTRACTIVE WRITER. Default-OFF
         # (PG_ABSTRACTIVE_WRITER). OFF => the deterministic short-writer stub + bare _vc_verify
         # below are BYTE-IDENTICAL and the new module is NEVER imported on the hot path (the flag is
@@ -5307,9 +5332,16 @@ async def _run_section(
         # fabricates a con and NEVER asserts an ungrounded balancing claim (fabricating balance is the
         # lethal direction). Default OFF (PG_TWO_SIDED_DEBATE) => the guard is False => byte-identical.
         if _two_sided_debate_enabled() and _is_debate_section(section):
+            _pre_debate_disc = len(_vc_degraded_disclosures or [])
             _vc_degraded_disclosures = _maybe_two_sided_debate_disclosure(
                 section, _vc_baskets, _vc_real_units, _vc_degraded_disclosures,
             )
+            # I-deepfix-001 Wave-3a (#1344): two-sided-debate ACTIVATION fire marker (see helper). Reached
+            # ONLY under PG_TWO_SIDED_DEBATE + a plan-framed debate section => OFF byte-identical.
+            _emit_two_sided_debate_marker(
+                len(_vc_real_units or []),
+                len(_vc_degraded_disclosures or []) - _pre_debate_disc,
+            )
         raw = "\n".join(c for c in _vc_real_units if c and c.strip())
         # I-deepfix-001 WS-3 (#1344): NO-PROVENANCE-TOKEN LEAK REPAIR. Before `raw` flows into the
         # UNCHANGED _rewrite_draft_with_spans + strict_verify tail (where an untokened sentence is
diff --git a/src/polaris_graph/retrieval/fs_researcher_query_gen.py b/src/polaris_graph/retrieval/fs_researcher_query_gen.py
index 6f9f858b..1feab87e 100644
--- a/src/polaris_graph/retrieval/fs_researcher_query_gen.py
+++ b/src/polaris_graph/retrieval/fs_researcher_query_gen.py
@@ -25,11 +25,14 @@ contract as today. Mirrors `iterresearch_query_gen.py` (`merge_retrieval_results
 
 from __future__ import annotations
 
+import logging
 import os
 import re
 import time
 from typing import Any, Callable
 
+logger = logging.getLogger("polaris_graph.fs_researcher_query_gen")
+
 # (research_question, **kw) -> LiveRetrievalResult. Injected so this module never imports the
 # 1000-line live_retriever at module load (and so it is unit-testable on a stub).
 PerQueryRetrieveFn = Callable[..., Any]
@@ -322,6 +325,12 @@ def _plan_expert_facet_queries(
 
     # R1: build the facet tree (one bounded LLM call) and its scope-anchored angle queries.
     facets = _efp.plan_expert_facets(question, llm)
+    # I-deepfix-001 Wave-3a (#1344): expert-facet-planner ACTIVATION fire marker. Emitted ONLY when
+    # PG_EXPERT_FACET_PLANNER is ON (this whole facet path is reached only under the flag; the guard keeps
+    # the marker OFF byte-identical even if a test drives this helper directly). facets=0 with the flag ON
+    # is the eligible-yet-zero (degenerate-LLM-reply) signal. Structural presence + count (§-1.3).
+    if _efp.expert_facet_enabled():
+        logger.info("[activation] expert_facet_planner: facets=%d", len(facets))
 
     # R1+R2 seed/reserve split (I-deepfix-001, #1344). Seed BREADTH-FIRST (every facet's
     # primary angle before any facet's deeper angle) so the query budget spreads across ALL
@@ -398,13 +407,20 @@ def _plan_expert_facet_queries(
     from src.polaris_graph.retrieval import sub_entity_query_expander as _sqe
     if _sqe.sub_entity_expansion_enabled() and not _wall_passed():
         _sub_qs = _sqe.plan_sub_entity_queries(question, llm)
+        _new_sub_count = 0
         if _sub_qs:
             _seed_keys = {(q or "").strip().lower() for q in seed_queries}
             _new_sub = [q for q in _sub_qs if (q or "").strip().lower() not in _seed_keys]
+            _new_sub_count = len(_new_sub)
             if _new_sub:
                 seed_queries, max_queries = _sqe.widen_with_sub_entities(
                     list(seed_queries), _new_sub, max_queries
                 )
+        # I-deepfix-001 Wave-3a (#1344): sub-entity-expansion ACTIVATION fire marker. Emitted ONLY inside
+        # this PG_SUBENTITY_QUERY_EXPANSION-gated block => OFF byte-identical. expanded_queries = the NET
+        # NEW sub-entity queries added on top of the current frontier (0 = LLM named none / all duplicates,
+        # the eligible-yet-zero signal). Structural presence + count (§-1.3).
+        logger.info("[activation] subentity_query_expansion: expanded_queries=%d", _new_sub_count)
 
     # Issue the seed frontier directly (facet-angle queries are already full queries — no
     # per-todo llm() derivation needed). Record ONLY the queries ACTUALLY issued in the
diff --git a/src/polaris_graph/synthesis/credibility_pass.py b/src/polaris_graph/synthesis/credibility_pass.py
index c7a790ef..8598490f 100644
--- a/src/polaris_graph/synthesis/credibility_pass.py
+++ b/src/polaris_graph/synthesis/credibility_pass.py
@@ -698,6 +698,21 @@ def _run_member_verifies(
     return [v for v in results if v is not None]
 
 
+def _emit_basket_consume_marker(regrouped: int, *, noop: bool) -> None:
+    """I-deepfix-001 Wave-3a (#1344): the HOP-A basket-consume ACTIVATION fire marker. Emitted ONLY when
+    PG_BASKET_CONSUME_FINDING_DEDUP is ON so the OFF path (this whole regroup is skipped at the caller)
+    stays byte-identical — the run_log carries no ``[activation]`` line. ``noop=True`` is the silent-no-op
+    the routing proof flagged (the function returned the input graph UNCHANGED). Structural presence +
+    count, never a threshold (§-1.3). Side-effect only; the returned graph is byte-untouched."""
+    if not basket_consume_finding_dedup_enabled():
+        return
+    import logging as _logging  # noqa: PLC0415
+    _logging.getLogger(__name__).info(
+        "[activation] basket_consume_finding_dedup: regrouped old_to_new=%d noop=%s",
+        int(regrouped), bool(noop),
+    )
+
+
 def _regroup_graph_by_finding_dedup(
     graph: Any,
     annotated: list[dict],
@@ -736,6 +751,7 @@ def _regroup_graph_by_finding_dedup(
 
     claims = list(getattr(graph, "claims", None) or [])
     if not claims:
+        _emit_basket_consume_marker(0, noop=True)
         return graph
 
     # claim_graph emits AT MOST ONE numeric AtomicClaim per evidence_id (extract_numeric_claims emits
@@ -853,6 +869,7 @@ def _regroup_graph_by_finding_dedup(
 
     if not old_to_new:
         # No merge happened (e.g. finding_dedup found nothing to group) -> the legacy grouping stands.
+        _emit_basket_consume_marker(0, noop=True)
         return graph
 
     # ── Remap edges so a refuter reference still lands on the MERGED cluster id (never hide a
@@ -866,6 +883,7 @@ def _regroup_graph_by_finding_dedup(
         }))
         new_edges.append(dataclasses.replace(edge, claim_cluster_ids=ids))
 
+    _emit_basket_consume_marker(len(old_to_new), noop=False)
     return dataclasses.replace(
         graph,
         claims=claims,
diff --git a/src/polaris_graph/synthesis/finding_dedup.py b/src/polaris_graph/synthesis/finding_dedup.py
index 4d3da127..1bae4843 100644
--- a/src/polaris_graph/synthesis/finding_dedup.py
+++ b/src/polaris_graph/synthesis/finding_dedup.py
@@ -1197,6 +1197,7 @@ def _apply_finding_dedup_nli_grouping(
     clusters: list[list[Any]],
     *,
     entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
+    telemetry: Optional[dict[str, Any]] = None,
 ) -> list[list[Any]]:
     """PG_FINDING_DEDUP_NLI (I-deepfix-001 Wave 1b, #1344; REAL_PLAN_2026 coverage_fix item 1):
     union lexical qualitative candidate clusters whose REPRESENTATIVE claim texts STRICTLY
@@ -1243,6 +1244,13 @@ def _apply_finding_dedup_nli_grouping(
 
     rep_texts = [_row_text(rows[cluster[2][0]]) for cluster in clusters]
     rep_polarity = [cluster[1] for cluster in clusters]
+    # I-deepfix-001 Wave-3a (#1344): ADDITIVE activation telemetry (never changes a merge). A one-element
+    # mutable flag is set when the cross-encoder returns None on a pair of NON-empty representatives — the
+    # DEGRADE sentinel (infra fault: model unavailable / OOM CPU-degrade failed), distinct from a genuine
+    # empty-text None. Only surfaced through the ``telemetry`` out-param; discarded (behavior-inert) when
+    # the caller passes no dict (the deterministic-stub test path).
+    rep_nonempty = [bool(t and t.strip()) for t in rep_texts]
+    _degraded_flag = [False]
 
     # Candidate cluster-index pairs (i < j). The POLARITY hard-block excludes a
     # mismatched-polarity pair from scoring entirely (it can never link — defense in depth).
@@ -1278,9 +1286,16 @@ def _apply_finding_dedup_nli_grouping(
     def _bidirectional(pair: tuple[int, int]) -> Optional[tuple[int, int]]:
         i, j = pair
         fwd = entail_fn(rep_texts[i], rep_texts[j])
+        # ADDITIVE degrade observation (Wave-3a #1344): a None verdict on two NON-empty texts means the
+        # cross-encoder was unavailable (infra fault) — record it WITHOUT changing the fail-closed edge
+        # decision below. Thread-safe: a single-element list write is atomic under the GIL.
+        if fwd is None and rep_nonempty[i] and rep_nonempty[j]:
+            _degraded_flag[0] = True
         if fwd is not True:
             return None  # one-direction / contradiction / None => no edge (fail-closed)
         rev = entail_fn(rep_texts[j], rep_texts[i])
+        if rev is None and rep_nonempty[i] and rep_nonempty[j]:
+            _degraded_flag[0] = True
         if rev is not True:
             return None
         return (i, j)
@@ -1348,6 +1363,13 @@ def _apply_finding_dedup_nli_grouping(
         )
 
     edges.sort()
+    # Wave-3a (#1344): surface the degrade + wall-truncation observations now that scoring is done. The
+    # directional_merges count is finalized at the merged-return below (0 on the no-edge path). Behavior-
+    # inert when ``telemetry`` is None (the stub-test path); populated only for the run-logger caller.
+    if telemetry is not None:
+        telemetry["degraded"] = bool(_degraded_flag[0])
+        telemetry["wall_truncated"] = bool(truncated)
+        telemetry["directional_merges"] = 0
     if not edges:
         return clusters
 
@@ -1375,6 +1397,10 @@ def _apply_finding_dedup_nli_grouping(
             consumed[j] = True
         consumed[i] = True
         out.append([clusters[i][0], clusters[i][1], sorted(set(merged_ris))])
+    # Wave-3a (#1344): each consumed cluster reduces the output count by one, so ``n - len(out)`` is the
+    # number of DIRECTIONAL merges this pass performed (behavior-inert when ``telemetry`` is None).
+    if telemetry is not None:
+        telemetry["directional_merges"] = n - len(out)
     return out
 
 
@@ -1477,7 +1503,22 @@ def _build_qualitative_groups(
     # (no merge); contradiction => no merge; polarity hard-block defense-in-depth. OFF =>
     # byte-identical (this call is skipped). Additive / keep-all with the guarded pass above.
     if _finding_dedup_nli_enabled():
-        clusters = _apply_finding_dedup_nli_grouping(rows, clusters)
+        _nli_telemetry: dict[str, Any] = {}
+        clusters = _apply_finding_dedup_nli_grouping(
+            rows, clusters, telemetry=_nli_telemetry,
+        )
+        # I-deepfix-001 Wave-3a (#1344): the finding-dedup-NLI ACTIVATION fire marker. Emitted ONLY under
+        # PG_FINDING_DEDUP_NLI (this branch is skipped when the flag is OFF => the run_log carries no
+        # ``[activation]`` line => OFF byte-identical). Structural presence + count, never a threshold
+        # (§-1.3): directional_merges=0 with the flag ON on eligible input is itself the eligible-yet-zero
+        # signal the activation canary reads; degraded=true is the cross-encoder-fallback signal;
+        # wall_truncated=true is the scoring-wall under-merge signal.
+        logger.info(
+            "[activation] finding_dedup_nli: invoked directional_merges=%d degraded=%s wall_truncated=%s",
+            int(_nli_telemetry.get("directional_merges", 0)),
+            bool(_nli_telemetry.get("degraded", False)),
+            bool(_nli_telemetry.get("wall_truncated", False)),
+        )
 
     out: dict[tuple, list[int]] = {}
     for cluster in clusters:
```

THE NEW TEST (tests/polaris_graph/test_activation_markers_wave3a.py):
```python
"""I-deepfix-001 Wave-3a (#1344) — activation FIRE-MARKER behavioral tests.

OFFLINE + ISOLATED: no paid API, no GPU, no live model. Every ``[activation] <module>:`` marker built
in Wave-3a U2 is proven, per module, to:
  (a) NOT emit when its flag is OFF (OFF byte-identical — the run_log carries no ``[activation]`` line);
  (b) emit with the RIGHT count + bool fields when its flag is ON on eligible input; and
  (c) flip its degraded / noop / build_ok / con-disclosed bool on the silent-fallback path.

The counts are STRUCTURAL presence signals (§-1.3), never thresholds: a count of 0 with the flag ON on
eligible input is itself a valid emission (the "eligible-yet-zero" canary signal).

Covered markers: finding_dedup_nli, basket_consume_finding_dedup, cross_source_body,
numeric_comparator, two_sided_debate.
"""
from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path

import pytest

# Repo root on path (tests/polaris_graph/<this> -> parents[2] == repo root).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no judge calls, no network entailment, deterministic render-chrome behavior.
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

from src.polaris_graph.synthesis import finding_dedup as fd  # noqa: E402
from src.polaris_graph.synthesis import credibility_pass as cp  # noqa: E402
from src.polaris_graph.generator import cross_source_synthesis as css  # noqa: E402
from src.polaris_graph.generator import numeric_comparator as ncmod  # noqa: E402
from src.polaris_graph.generator import multi_section_generator as msg  # noqa: E402
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402


# ── log-capture helper ─────────────────────────────────────────────────────────────────────────────
def _marker_lines(caplog, name: str) -> list[str]:
    """Formatted log messages whose text is the ``[activation] <name>:`` marker."""
    prefix = f"[activation] {name}:"
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]


# ── tiny basket builders (mirror the Wave-2a cross-source test) ─────────────────────────────────────
def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url="", source_tier="",
        origin_cluster_id=f"origin::{eid}", credibility_weight=1.0, authority_score=1.0,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, subject: str, predicate: str, eids) -> ClaimBasket:
    members = [_member(e, f"{subject} {predicate} finding.") for e in eids]
    return ClaimBasket(
        claim_cluster_id=cluster_id, claim_text=f"{subject} {predicate}", subject=subject,
        predicate=predicate, supporting_members=members, refuter_cluster_ids=(),
        weight_mass=1.0, total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members), basket_verdict="full",
    )


_CLAUSES = {
    "cA": "Study A reported an effect [#ev:eA:0-5].",
    "cC": "Study C reported a side effect [#ev:eC:0-5].",
}


def _stub_clause_builder(clause_by_cluster: dict):
    def _stub(basket, _pool, *, writer_fn, verify_fn):
        return clause_by_cluster.get(str(getattr(basket, "claim_cluster_id", "") or ""))
    return _stub


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 1) finding_dedup_nli
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def _fd_rows(bodies):
    return [
        {
            "evidence_id": f"ev{i}",
            "source_url": f"https://host{i}.example.org/x",
            "direct_quote": body,
            "authority_score": 0.7,
            "selection_relevance": 0.7,
        }
        for i, body in enumerate(bodies)
    ]


def _fd_singletons(rows):
    return [[frozenset({rows[i]["direct_quote"]}), (), [i]] for i in range(len(rows))]


def test_finding_dedup_nli_telemetry_merge_and_not_degraded():
    """Real telemetry: a bidirectional-entailing pair MERGES => directional_merges=1, degraded=False."""
    a, b = "AI adoption is concentrated among the largest firms.", \
           "Uptake of these tools skews heavily toward big incumbents."
    rows = _fd_rows([a, b])
    tele: dict = {}
    out = fd._apply_finding_dedup_nli_grouping(
        rows, _fd_singletons(rows),
        entail_fn=lambda p, h: {(a, b): True, (b, a): True}.get((p, h), False),
        telemetry=tele,
    )
    assert any(len(c[2]) >= 2 for c in out), "bidirectional entail must merge"
    assert tele["directional_merges"] == 1
    assert tele["degraded"] is False
    assert tele["wall_truncated"] is False


def test_finding_dedup_nli_telemetry_degraded_on_infra_none():
    """Silent-fallback path: the cross-encoder returns None on NON-empty reps => degraded=True."""
    a, b = "Remote work raised measured output in knowledge roles.", \
           "Distributed teams recorded higher productivity in knowledge work."
    rows = _fd_rows([a, b])
    tele: dict = {}
    out = fd._apply_finding_dedup_nli_grouping(
        rows, _fd_singletons(rows),
        entail_fn=lambda p, h: {(a, b): True, (b, a): None}.get((p, h), False),  # reverse UNAVAILABLE
        telemetry=tele,
    )
    assert not any(len(c[2]) >= 2 for c in out), "an infra None must fail-closed (no merge)"
    assert tele["degraded"] is True, "a None verdict on non-empty reps is the degrade signal"
    assert tele["directional_merges"] == 0


def test_finding_dedup_nli_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_FINDING_DEDUP_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_QUALITATIVE", raising=False)
    with caplog.at_level(logging.INFO, logger="polaris_graph.finding_dedup"):
        fd._build_qualitative_groups([], [], set(), threshold=0.5)
    assert _marker_lines(caplog, "finding_dedup_nli") == [], "OFF must emit no [activation] line"


def test_finding_dedup_nli_marker_on_emits_fields(monkeypatch, caplog):
    monkeypatch.setenv("PG_FINDING_DEDUP_NLI", "1")
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_QUALITATIVE", raising=False)

    def _stub_grouping(rows, clusters, *, entail_fn=None, telemetry=None):
        if telemetry is not None:
            telemetry.update(directional_merges=3, degraded=True, wall_truncated=False)
        return clusters

    monkeypatch.setattr(fd, "_apply_finding_dedup_nli_grouping", _stub_grouping)
    with caplog.at_level(logging.INFO, logger="polaris_graph.finding_dedup"):
        fd._build_qualitative_groups([], [], set(), threshold=0.5)
    lines = _marker_lines(caplog, "finding_dedup_nli")
    assert len(lines) == 1
    assert "invoked directional_merges=3" in lines[0]
    assert "degraded=True" in lines[0]
    assert "wall_truncated=False" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 2) basket_consume_finding_dedup
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_basket_consume_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_BASKET_CONSUME_FINDING_DEDUP", raising=False)
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        cp._emit_basket_consume_marker(5, noop=False)
    assert _marker_lines(caplog, "basket_consume_finding_dedup") == []


def test_basket_consume_marker_on_regrouped_and_noop_flip(monkeypatch, caplog):
    monkeypatch.setenv("PG_BASKET_CONSUME_FINDING_DEDUP", "1")
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        cp._emit_basket_consume_marker(4, noop=False)
        cp._emit_basket_consume_marker(0, noop=True)
    lines = _marker_lines(caplog, "basket_consume_finding_dedup")
    assert len(lines) == 2
    assert "regrouped old_to_new=4 noop=False" in lines[0]
    assert "regrouped old_to_new=0 noop=True" in lines[1]


def test_basket_consume_real_noop_path_emits_noop_true(monkeypatch, caplog):
    """The REAL silent-no-op path (an empty-claims graph returns the input UNCHANGED) => noop=True."""
    monkeypatch.setenv("PG_BASKET_CONSUME_FINDING_DEDUP", "1")
    graph = types.SimpleNamespace(claims=[], clusters={}, edges=[])
    with caplog.at_level(logging.INFO, logger=cp.__name__):
        out = cp._regroup_graph_by_finding_dedup(graph, [], gov_suffixes=(), domain=None)
    assert out is graph, "no-claims graph must be returned UNCHANGED (the no-op)"
    lines = _marker_lines(caplog, "basket_consume_finding_dedup")
    assert len(lines) == 1 and "noop=True" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 3) cross_source_body
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_cross_source_body_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_CROSS_SOURCE_BODY", raising=False)
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
        )
    assert _marker_lines(caplog, "cross_source_body") == [], "OFF must emit no plan-driven/anchor marker"


def test_cross_source_body_on_plan_driven_degraded_when_not_threaded(monkeypatch, caplog):
    """ON + no equiv_clusters/agree_map threaded => input_threaded=False, degraded=True, pairs=1."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])  # SAME subject => a plan-driven facet pair
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
        )
    lines = _marker_lines(caplog, "cross_source_body")
    assert len(lines) == 1
    assert "plan_driven pairs=1" in lines[0]
    assert "input_threaded=False" in lines[0]
    assert "degraded=True" in lines[0]


def test_cross_source_body_on_input_threaded_not_degraded(monkeypatch, caplog):
    """ON + a threaded agree_map => input_threaded=True, degraded=False (the not-degraded field)."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
            agree_map={("cA", "cC"): True},
        )
    lines = _marker_lines(caplog, "cross_source_body")
    assert len(lines) == 1
    assert "input_threaded=True" in lines[0]
    assert "degraded=False" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 4) numeric_comparator
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_numeric_comparator_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_NUMERIC_COMPARATOR", raising=False)
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
        )
    assert _marker_lines(caplog, "numeric_comparator") == []


def test_numeric_comparator_on_build_ok_false_when_lookup_none(monkeypatch, caplog):
    """ON + numeric_key_by_cluster=None (the silent-swallow-made-loud signal) => build_ok=False."""
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None,
            numeric_key_by_cluster=None,
        )
    lines = _marker_lines(caplog, "numeric_comparator")
    assert len(lines) == 1
    assert "upgraded=0" in lines[0]
    assert "build_ok=False" in lines[0]


def test_numeric_comparator_on_counts_upgrades_build_ok_true(monkeypatch, caplog):
    """ON + a threaded key lookup + a NEUTRAL pair the comparator upgrades => upgraded=1, build_ok=True."""
    monkeypatch.setenv("PG_CROSS_SOURCE_BODY", "1")
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    monkeypatch.setattr(css, "_first_verified_clause", _stub_clause_builder(_CLAUSES))
    # Force the deterministic comparator to license "comparison" for the neutral facet pair.
    monkeypatch.setattr(ncmod, "license_numeric_comparison", lambda ka, kb: "comparison")
    a = _basket("cA", "drug x", "reduces a1c", ["eA"])
    c = _basket("cC", "drug x", "causes nausea", ["eC"])
    keys = {"cA": ("k", 1.0), "cC": ("k", 2.0)}  # non-None => build_ok True
    with caplog.at_level(logging.INFO, logger=css.__name__):
        css.compose_cross_source_analytical_units(
            [a, c], {}, writer_fn=lambda *_: "", verify_fn=lambda *_: None, entail_fn=lambda *_: None,
            numeric_key_by_cluster=keys,
        )
    lines = _marker_lines(caplog, "numeric_comparator")
    assert len(lines) == 1
    assert "upgraded=1" in lines[0]
    assert "build_ok=True" in lines[0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# 5) two_sided_debate
# ═══════════════════════════════════════════════════════════════════════════════════════════════════
def test_two_sided_debate_marker_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_TWO_SIDED_DEBATE", raising=False)
    with caplog.at_level(logging.INFO, logger="polaris_graph.multi_section"):
        msg._emit_two_sided_debate_marker(7, 1)
    assert _marker_lines(caplog, "two_sided_debate") == []


def test_two_sided_debate_marker_on_con_disclosed_flip(monkeypatch, caplog):
    """ON: con_disclosed=1 is the one-sided-pro asymmetry-disclosed signal; con_disclosed=0 = balanced."""
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    with caplog.at_level(logging.INFO, logger="polaris_graph.multi_section"):
        msg._emit_two_sided_debate_marker(9, 1)  # pro present, no con => one asymmetry disclosure
        msg._emit_two_sided_debate_marker(4, 0)  # both sides present => nothing disclosed
    lines = _marker_lines(caplog, "two_sided_debate")
    assert len(lines) == 2
    assert "leg2_inspected=9 con_disclosed=1" in lines[0]
    assert "leg2_inspected=4 con_disclosed=0" in lines[1]


def test_two_sided_debate_real_con_disclosure_when_pro_only(monkeypatch):
    """The REAL con-disclosure helper appends ONE honest asymmetry note when a verified pro but no
    verified con clause is present (the con_disclosed=1 the marker reports)."""
    section = types.SimpleNamespace(title="Benefits and risks", focus="pros and cons of drug x")
    pro_only_units = ["Drug x reduces a1c [#ev:eA:0-5]."]
    out = msg._maybe_two_sided_debate_disclosure(section, [], pro_only_units, [])
    assert len(out) == 1, "a one-sided-pro debate section must disclose exactly one asymmetry note"
```

OUTPUT SCHEMA (return exactly):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
faithfulness_untouched: true|false
off_no_emit_byte_identical: true|false
markers_structural_not_threshold: true|false
honesty_bools_correct: true|false
convergence_call: continue | accept_remaining
notes: <short>
```
APPROVE iff faithfulness untouched, OFF no-emit byte-identical, markers structural, honesty bools correct, zero P0/P1.
