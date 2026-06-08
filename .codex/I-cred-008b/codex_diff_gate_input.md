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
## PHASE: I-cred-008b (#1162) — DIFF gate. Per-claim disclosure POPULATE+SURFACE at all 4 cited-prose resolve sites. Built by subagent, Claude reviewed line-by-line (helper + 4 sites + ALL swallow points). Default-OFF byte-identical (credibility_analysis None => no populate/no artifact). ADVISORY ONLY — never re-runs strict_verify, never flips is_verified, 4-role D8 untouched.
- SHARED helper apply_disclosure_to_svs(svs, analysis) in credibility_pass.py = ONE copy of the faithfulness-critical logic for all 4 sites: (1) COVERAGE ASSERTION fail-LOUD BEFORE populate — every resolver-emitted cited token's eid MUST have credibility+origin coverage; a gap => CredibilityPassError(abort_credibility_coverage_gap); scoped to resolver-emitted cited SVs (deterministic table/timeline [N] markers never become SVs at these sites). (2) EvidenceCredibility->FLOAT adaptation {eid: ec.credibility_weight} -> populate_disclosure (which expects floats). (3) P3 CERTAINTY CARRIER — for each SV whose cited evidence has certainty_downgrade=True, cap certainty_label high->moderate + append soft_warning to soft_warnings. Inputs not mutated (dataclasses.replace).
- 4 sites: legacy _run_section (resolve 2267), fact-dedup re-resolve (the _resolve ALIAS 4976), V30 contract runner (845, before the manual prose regroup), quantified (380; no SectionResult so surfaced via telem['claim_disclosure']). All populate BEFORE resolve so disclosure rides into kept_sentences_pre_resolve.
- FAIL-LOUD HARDENING (the most important): enumerated EVERY swallow-point on the populate path and made it re-raise CredibilityPassError — fact-dedup except, M-44 regen (return_exceptions=True value), M-47 regen except, runner quantified except. A coverage gap can NEVER degrade into a silent false-green.
- SURFACE: claim_disclosure.json {sections:[{title,claims:[{sentence,span_verdict,credibility_weight,independent_origin_count,certainty_label,soft_warnings}]}]} written ONLY when credibility_analysis present. Named manifest status abort_credibility_coverage_gap registered in UNIFIED_STATUS_VALUES + _SUMMARY_TO_UNIFIED + the contract test's exact-equality set; run_one_query handler maps coverage-gap-by-message to the named status, other CredibilityPassError -> error_unexpected (both fail-loud). 
SMOKE: see the run above (generator+synthesis). Verify: flag-off byte-identity, the 4 swallow re-raises, the coverage assertion fires, EvidenceCredibility->float, certainty carrier.
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 82c432dc..d1028ca1 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -53,6 +53,10 @@ from src.polaris_graph.evaluator.live_judge import judge_report  # noqa: E402
 from src.polaris_graph.nodes.journal_only_filter import (  # noqa: E402  # I-ready-017 #1134
     JournalOnlyAbort as _JournalOnlyAbort,
 )
+# I-cred-008b (#1162): the credibility-disclosure coverage-gap abort (named manifest status).
+from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
+    CredibilityPassError as _CredPassErrForAbort,
+)
 # I-safety-002b (#925) PR-2: Path-B benchmark gate (preflight + capture + assert_post_run).
 from src.polaris_graph.benchmark import pathB_capture as _pathb  # noqa: E402
 from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
@@ -206,6 +210,7 @@ UNIFIED_STATUS_VALUES: frozenset[str] = frozenset({
     "abort_journal_only_contract_conflict",  # I-ready-017 (#1134): journal_only — a required report-contract slot is bound to a non-journal entity; refuse rather than cite a non-journal source in a journal-restricted review
     "error_journal_only_leak",       # I-ready-017 (#1134): journal_only — a non-journal row reached the generator past the source-filter (should never happen); fail-closed backstop, never synthesize
     "error_corpus_population_mismatch",  # I-ready-017 FX-06b (#1121): the corpus-approval gate and the adequacy artifact would score DIFFERENT populations (total_sources OR tier_counts diverge) — refuse rather than gate/approve on a population the report does not consume (defensive; should never fire)
+    "abort_credibility_coverage_gap",  # I-cred-008b (#1162): the activated credibility-disclosure pass found a cited token whose evidence has no credibility/origin coverage — fail-loud rather than disclose a claim whose source was never scored (only fires under PG_SWEEP_CREDIBILITY_REDESIGN)
     "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release (fabrication/coverage/S0/rewrite) — written via _SUMMARY_TO_UNIFIED["four_role_held"] at L4934/5065; was a real taxonomy gap
     "cancelled",                     # I-ready-016 (#1086): user-requested cancel terminal; _abort_if_cancelled writes manifest.status="cancelled" (consumed by v6 UI + SSE — value preserved, NOT renamed). Does NOT match the 4-prefix scheme — see the documented exception in test_manifest_contract_status_prefixes.
     # error — unhandled exception
@@ -248,6 +253,8 @@ _SUMMARY_TO_UNIFIED: dict[str, str] = {
     "abort_journal_only_contract_conflict": "abort_journal_only_contract_conflict",
     "error_journal_only_leak": "error_journal_only_leak",
     "error_corpus_population_mismatch": "error_corpus_population_mismatch",
+    # I-cred-008b (#1162): credibility-disclosure coverage gap — fail-loud named abort.
+    "abort_credibility_coverage_gap": "abort_credibility_coverage_gap",
     "error": "error_unexpected",
 }
 
@@ -259,6 +266,47 @@ def to_unified_status(summary_status: str) -> str:
     return _SUMMARY_TO_UNIFIED.get(summary_status, "error_unexpected")
 
 
+def _build_claim_disclosure_doc(multi: Any, quantified_telemetry: Any) -> dict | None:
+    """I-cred-008b (#1162): serialize the per-claim CREDIBILITY DISCLOSURE for claim_disclosure.json.
+
+    Returns ``None`` (=> no artifact, byte-identical) when ``multi.credibility_analysis`` is absent
+    (master flag off). Otherwise returns ``{"sections": [{"title", "claims": [...]}, ...]}`` where each
+    claim row carries the six advisory disclosure fields. Sites 1-3 surface via
+    ``SectionResult.kept_sentences_pre_resolve``; the quantified path (site 4) has no SectionResult, so
+    its rows arrive in ``quantified_telemetry["claim_disclosure"]``. Pure (no IO) for testability.
+    """
+    if getattr(multi, "credibility_analysis", None) is None:
+        return None
+    sections: list[dict] = []
+    for sr in getattr(multi, "sections", None) or []:
+        if getattr(sr, "dropped_due_to_failure", False):
+            continue
+        kept = getattr(sr, "kept_sentences_pre_resolve", None) or []
+        if not kept:
+            continue
+        sections.append({
+            "title": getattr(sr, "title", ""),
+            "claims": [
+                {
+                    "sentence": getattr(sv, "sentence", ""),
+                    "span_verdict": getattr(sv, "span_verdict", ""),
+                    "credibility_weight": getattr(sv, "credibility_weight", None),
+                    "independent_origin_count": getattr(sv, "independent_origin_count", None),
+                    "certainty_label": getattr(sv, "certainty_label", ""),
+                    "soft_warnings": list(getattr(sv, "soft_warnings", None) or []),
+                }
+                for sv in kept
+            ],
+        })
+    q_rows = (
+        quantified_telemetry.get("claim_disclosure")
+        if isinstance(quantified_telemetry, dict) else None
+    )
+    if q_rows:
+        sections.append({"title": "Quantified Trade-off", "claims": list(q_rows)})
+    return {"sections": sections}
+
+
 def make_feature_telemetry(feature: str, **extra: Any) -> dict[str, Any]:
     """I-ready-005 (#1076): default per-feature FIRING telemetry surfaced to the manifest so the operator
     can prove a forced-ON benchmark feature actually fired. firing_status: not_enabled ->
@@ -5116,6 +5164,9 @@ async def run_one_query(
                 _q_section_md, _quantified_telemetry = await run_quantified_section(
                     q["question"], _q_ev_pool,
                     spec_provider=_q_spec_provider, run_dir=str(run_dir),
+                    # I-cred-008b (#1162): thread the advisory credibility analysis from the
+                    # MultiSectionResult (None when the master flag is off => byte-identical).
+                    credibility_analysis=getattr(multi, "credibility_analysis", None),
                 )
                 if _q_section_md:
                     sections_concat += "\n\n" + _q_section_md
@@ -5130,6 +5181,15 @@ async def run_one_query(
                         f"(spec_produced={_quantified_telemetry.get('spec_produced')})"
                     )
             except Exception as _q_exc:  # never abort the run on quantified failure
+                # I-cred-008b (#1162): a credibility-disclosure coverage gap MUST stay fail-loud.
+                # The quantified block safe-degrades on its own faults, but a CredibilityPassError
+                # (a cited token with no credibility/origin coverage) is a faithfulness abort — let it
+                # propagate to the run_one_query handler, which maps it to abort_credibility_coverage_gap.
+                from src.polaris_graph.synthesis.credibility_pass import (
+                    CredibilityPassError as _CredPassErr,
+                )
+                if isinstance(_q_exc, _CredPassErr):
+                    raise
                 _log(f"[phase7]      quantified analysis skipped: {str(_q_exc)[:160]}")
                 _quantified_telemetry = {"enabled": True, "error": str(_q_exc)[:200]}
 
@@ -5601,6 +5661,17 @@ async def run_one_query(
             json.dumps(verif_details, indent=2, sort_keys=True, default=str) + "\n",
             encoding="utf-8",
         )
+        # I-cred-008b (#1162) DELIVERABLE 4: surface the populated per-claim CREDIBILITY DISCLOSURE.
+        # ONLY when the advisory credibility analysis is present (master flag on); None => no artifact,
+        # byte-identical. The populated SVs already flow out via SectionResult.kept_sentences_pre_resolve
+        # (sites 1-3); the quantified path (site 4) has no SectionResult, so its rows ride in
+        # _quantified_telemetry["claim_disclosure"]. ADVISORY: this is disclosure the user reads, never a gate.
+        _claim_disclosure_doc = _build_claim_disclosure_doc(multi, _quantified_telemetry)
+        if _claim_disclosure_doc is not None:
+            (run_dir / "claim_disclosure.json").write_text(
+                json.dumps(_claim_disclosure_doc, indent=2, sort_keys=True, default=str) + "\n",
+                encoding="utf-8",
+            )
         # I-obs-001 #1141 AC1 (Codex AC1-gate P1-2): generation + per-sentence verification complete
         # (generation is one batched await with no mid-stream hook, spec §1.8, so this is the earliest
         # truthful "generation_done" point — right before the 4-role seam).
@@ -6623,6 +6694,41 @@ async def run_one_query(
                 summary["cost_usd"] = run_cost
         except Exception as _ja_mw:  # noqa: BLE001 — best-effort; never mask the abort
             _log(f"[journal_only] abort manifest-write-also-failed: {_ja_mw}")
+    except _CredPassErrForAbort as _cge:
+        # I-cred-008b (#1162): a CredibilityPassError reached the run handler. The COVERAGE-GAP
+        # subclass-by-message (apply_disclosure_to_svs found a cited token with no credibility/origin
+        # coverage) gets its OWN named status so the manifest is self-documenting; any OTHER
+        # CredibilityPassError (judge_error / independence-annotation gap raised by the pass itself) is
+        # re-raised to the generic handler below => error_unexpected. Both are fail-loud (no false-green);
+        # only the STATUS label differs. Mirrors the _JournalOnlyAbort handler above.
+        if "abort_credibility_coverage_gap" not in str(_cge):
+            raise
+        _log(f"[credibility] ABORT: status=abort_credibility_coverage_gap — {_cge}")
+        summary["status"] = "abort_credibility_coverage_gap"
+        summary["error"] = str(_cge)[:300]
+        try:
+            if run_dir is not None:
+                run_cost = current_run_cost()
+                _cge_manifest = _base_manifest_envelope(
+                    run_id=run_id, q=q, retrieval=retrieval, run_cost=run_cost,
+                )
+                _cge_manifest["status"] = "abort_credibility_coverage_gap"
+                _cge_manifest["error"] = str(_cge)[:500]
+                _cge_manifest = augment_v6_manifest(
+                    _cge_manifest,
+                    external_run_id=q.get("external_run_id"),
+                    decision_id=q.get("decision_id"),
+                    query_slug=q.get("slug"),
+                )
+                _cge_manifest = _attach_tool_utilization(_cge_manifest, run_dir)
+                (run_dir / "manifest.json").write_text(
+                    json.dumps(_cge_manifest, indent=2, sort_keys=True, default=str) + "\n",
+                    encoding="utf-8",
+                )
+                summary["manifest"] = _cge_manifest
+                summary["cost_usd"] = run_cost
+        except Exception as _cge_mw:  # noqa: BLE001 — best-effort; never mask the abort
+            _log(f"[credibility] abort manifest-write-also-failed: {_cge_mw}")
     except Exception as exc:
         tb = traceback.format_exc()
         _log(f"[FATAL]       {exc}")
diff --git a/src/polaris_graph/generator/contract_section_runner.py b/src/polaris_graph/generator/contract_section_runner.py
index 53f852f5..224cd8ec 100644
--- a/src/polaris_graph/generator/contract_section_runner.py
+++ b/src/polaris_graph/generator/contract_section_runner.py
@@ -489,6 +489,7 @@ async def run_contract_section(
                                # circular import)
     strict_verify_fn: Any,     # strict_verify callable (injected)
     rewrite_fn: Any,           # _rewrite_draft_with_spans (injected)
+    credibility_analysis: Any = None,  # I-cred-008b (#1162): advisory per-claim disclosure; None => byte-identical
 ) -> tuple[Any, list[SlotFillPayload]]:
     """Run one contract SECTION. Returns (SectionResult,
     list[SlotFillPayload]). The payloads are threaded back to
@@ -817,6 +818,13 @@ async def run_contract_section(
     kept_sentences = (
         det_kept_sentences + reg_kept_sentences + narr_kept_sentences
     )
+    # I-cred-008b (#1162) SITE 3/4 (V30 contract): populate the advisory per-claim disclosure on the
+    # merged kept SVs BEFORE the resolve below — the contract runner then MANUALLY rebuilds prose from
+    # sv.sentence (the per-slot regroup), so populating here makes the four fields ride along into the
+    # SectionResult.kept_sentences_pre_resolve emitted at the end of this function. None => byte-identical.
+    if credibility_analysis is not None:
+        from ..synthesis.credibility_pass import apply_disclosure_to_svs
+        kept_sentences = apply_disclosure_to_svs(kept_sentences, credibility_analysis)
     rescued = det_rescued  # regulatory + narrative streams contribute no rescues
     # Combined raw + rewritten drafts (telemetry parity with pre-Fix-B).
     raw_draft = " ".join(
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index a9a20ff4..2266e181 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -2078,6 +2078,7 @@ async def _run_section(
     cross_trial_block: Any = None,  # CrossTrialSynthesisBlock | None
     use_field_agnostic_prompt: bool = False,
     advisory_text: str = "",  # I-meta-005 Phase 6 (#990): domain advisory append
+    credibility_analysis: Any = None,  # I-cred-008b (#1162): advisory per-claim disclosure; None => byte-identical
 ) -> SectionResult:
     """Run one section: generate, rewrite, verify, optionally regenerate.
 
@@ -2264,6 +2265,16 @@ async def _run_section(
     # actually ships.
     report.total_kept = len(report_kept_after_m41c)
 
+    # I-cred-008b (#1162) SITE 1/4 (legacy per-section): populate the advisory per-claim
+    # disclosure on the kept SVs IMMEDIATELY BEFORE resolve, so the fields ride along into
+    # kept_sentences_pre_resolve (set from report.kept_sentences below). None => byte-identical
+    # (no populate, no coverage check). ADVISORY: never re-runs strict_verify / flips is_verified.
+    if credibility_analysis is not None:
+        from ..synthesis.credibility_pass import apply_disclosure_to_svs
+        report.kept_sentences = apply_disclosure_to_svs(
+            report.kept_sentences, credibility_analysis,
+        )
+
     verified_text, biblio_slice = resolve_provenance_to_citations(
         report.kept_sentences, evidence_pool,
     )
@@ -4785,6 +4796,8 @@ async def generate_multi_section_report(
                 section_result_cls=SectionResult,
                 strict_verify_fn=strict_verify,
                 rewrite_fn=_rewrite_draft_with_spans,
+                # I-cred-008b (#1162): closure-captured local; None (master flag off) => byte-identical.
+                credibility_analysis=credibility_analysis,
             )
             contract_slot_payloads.extend(payloads)
             return result
@@ -4818,6 +4831,8 @@ async def generate_multi_section_report(
                 # I-meta-005 Phase 6 (#990): domain advisory writing-guidance,
                 # resolved once above (closure-captured; "" OFF -> no append).
                 advisory_text=advisory_text,
+                # I-cred-008b (#1162): closure-captured local; None (master flag off) => byte-identical.
+                credibility_analysis=credibility_analysis,
             )
 
     # V33 unified dispatch helper for downstream (M-44 regen) callers
@@ -4971,6 +4986,14 @@ async def generate_multi_section_report(
                     elif s in accepted_rewrite_by_str:
                         final_svs.append(accepted_rewrite_by_str[s])
                     # else: drop (LLM rewrite failed strict_verify)
+                # I-cred-008b (#1162) SITE 2/4 (fact-dedup re-resolve): the dedup pass produces FRESH
+                # post-dedup SVs (originals + re-verified rewrites). Populate them BEFORE the local
+                # `_resolve(...)` ALIAS (a literal grep for resolve_provenance_to_citations( misses it)
+                # so the disclosure rides into kept_sentences_pre_resolve set from final_svs below.
+                # None => byte-identical.
+                if credibility_analysis is not None:
+                    from ..synthesis.credibility_pass import apply_disclosure_to_svs
+                    final_svs = apply_disclosure_to_svs(final_svs, credibility_analysis)
                 # Update SectionResult fields with deduped + re-verified content
                 from .provenance_generator import resolve_provenance_to_citations as _resolve
                 new_text, new_biblio = _resolve(final_svs, evidence_pool)
@@ -5012,6 +5035,13 @@ async def generate_multi_section_report(
                 fact_dedup_telemetry.get("n_drops", 0),
             )
     except Exception as exc:  # noqa: BLE001 — safe-degrade per Codex review
+        # I-cred-008b (#1162): the credibility-disclosure coverage gap MUST stay fail-loud.
+        # The fact-dedup pass safe-degrades on its own faults, but a CredibilityPassError raised
+        # by apply_disclosure_to_svs (a cited token with no credibility/origin coverage) is a
+        # faithfulness abort — NEVER swallow it into a silent "continuing without dedup".
+        from ..synthesis.credibility_pass import CredibilityPassError
+        if isinstance(exc, CredibilityPassError):
+            raise
         logger.warning(
             "[multi_section] GH#423 fact_dedup pass failed (%s); "
             "continuing without dedup", exc,
@@ -5114,6 +5144,12 @@ async def generate_multi_section_report(
             )
             for (idx, plan), regen_result in zip(regen_items, regen_results):
                 if isinstance(regen_result, Exception):
+                    # I-cred-008b (#1162): a credibility-disclosure coverage gap raised during M-44
+                    # regen MUST stay fail-loud — never swallowed into "continue without the regen".
+                    # return_exceptions=True captured it as a value; re-raise it here.
+                    from ..synthesis.credibility_pass import CredibilityPassError
+                    if isinstance(regen_result, CredibilityPassError):
+                        raise regen_result
                     logger.warning(
                         "[multi_section] M-44 regen raised for %s: %s",
                         plan.title, regen_result,
@@ -5303,6 +5339,13 @@ async def generate_multi_section_report(
                                     orig_max, regen_max, regen_passed,
                                 )
                         except Exception as exc:
+                            # I-cred-008b (#1162): a credibility-disclosure coverage gap raised during
+                            # M-47 regen MUST stay fail-loud — never swallowed into "continue without
+                            # the regen" (regen runs _bounded_run -> _run_section/run_contract_section,
+                            # which populate the disclosure under activation).
+                            from ..synthesis.credibility_pass import CredibilityPassError
+                            if isinstance(exc, CredibilityPassError):
+                                raise
                             logger.warning(
                                 "[multi_section] M-47 regen raised: %s",
                                 exc,
diff --git a/src/polaris_graph/generator/quantified_analysis.py b/src/polaris_graph/generator/quantified_analysis.py
index 26d57e7a..01f4ad5a 100644
--- a/src/polaris_graph/generator/quantified_analysis.py
+++ b/src/polaris_graph/generator/quantified_analysis.py
@@ -310,6 +310,7 @@ async def run_quantified_section(
     *,
     spec_provider,
     run_dir: str | None = None,
+    credibility_analysis: Any = None,  # I-cred-008b (#1162): advisory per-claim disclosure; None => byte-identical
 ) -> tuple[str | None, dict[str, Any]]:
     """Sweep-facing orchestrator: Extract -> Model -> Execute -> Bind ->
     Verify(Regime C) -> verified "Quantified Trade-off" section.
@@ -377,6 +378,28 @@ async def run_quantified_section(
     if report.total_kept == 0:
         return None, telem
 
+    # I-cred-008b (#1162) SITE 4/4 (quantified trade-off): populate the advisory per-claim disclosure
+    # on the kept SVs BEFORE resolve. This path returns (section_md, telem) — it has NO SectionResult,
+    # so the populated SVs do NOT flow through kept_sentences_pre_resolve. To SURFACE them, we emit the
+    # per-claim disclosure rows in `telem["claim_disclosure"]` (the runner merges them into
+    # claim_disclosure.json). None => byte-identical (no populate, no telem key).
+    if credibility_analysis is not None:
+        from src.polaris_graph.synthesis.credibility_pass import apply_disclosure_to_svs
+        report.kept_sentences = apply_disclosure_to_svs(
+            report.kept_sentences, credibility_analysis,
+        )
+        telem["claim_disclosure"] = [
+            {
+                "sentence": getattr(_sv, "sentence", ""),
+                "span_verdict": getattr(_sv, "span_verdict", ""),
+                "credibility_weight": getattr(_sv, "credibility_weight", None),
+                "independent_origin_count": getattr(_sv, "independent_origin_count", None),
+                "certainty_label": getattr(_sv, "certainty_label", ""),
+                "soft_warnings": list(getattr(_sv, "soft_warnings", None) or []),
+            }
+            for _sv in report.kept_sentences
+        ]
+
     rendered, _biblio = resolve_provenance_to_citations(
         report.kept_sentences, evidence_pool,
     )
diff --git a/src/polaris_graph/synthesis/credibility_pass.py b/src/polaris_graph/synthesis/credibility_pass.py
index 248ff7b2..2fc867d1 100644
--- a/src/polaris_graph/synthesis/credibility_pass.py
+++ b/src/polaris_graph/synthesis/credibility_pass.py
@@ -200,3 +200,97 @@ def _run_chain(
         edges=graph.edges,
         weight_mass=weight_mass,
     )
+
+
+# ─────────────────────────────────────────────────────────────────────────────
+# I-cred-008b (#1162) — the SHARED per-claim disclosure populate+carrier+coverage
+# helper, called at ALL FOUR cited-prose resolve sites (legacy _run_section,
+# fact-dedup re-resolve, V30 contract runner, quantified-analysis). ONE copy of
+# this faithfulness-critical logic so it cannot drift across the four sites.
+# ─────────────────────────────────────────────────────────────────────────────
+
+def _cited_evidence_ids_for_coverage(sv: Any) -> list[str]:
+    """The cited evidence_ids on a RESOLVER-EMITTED SentenceVerification (its tokens)."""
+    out: list[str] = []
+    for token in (getattr(sv, "tokens", None) or []):
+        eid = str(getattr(token, "evidence_id", "") or "")
+        if eid:
+            out.append(eid)
+    return out
+
+
+def apply_disclosure_to_svs(svs: list, analysis: "CredibilityAnalysis") -> list:
+    """Populate the four advisory disclosure fields on each resolver-emitted SV, then carry the
+    P3 certainty downgrade — ONE shared implementation for all four cited-prose resolve sites.
+
+    Steps (ADVISORY only — never re-runs strict_verify, never flips ``is_verified``):
+      1. COVERAGE ASSERTION (fail-LOUD): every cited token's evidence_id on these SVs MUST have
+         credibility + origin coverage in ``analysis`` (both maps are co-built per-row in
+         ``_run_chain``). A cited token with none ⇒ ``CredibilityPassError(abort_credibility_coverage_gap)``.
+         Scoped to RESOLVER-EMITTED cited SVs (the SVs handed to ``resolve_provenance_to_citations``),
+         NOT every ``[N]`` marker in deterministic tables/timelines — those never become SVs at the
+         resolve sites, so they are excluded for free (Codex I-cred-012 iter-5 P2-3).
+      2. POPULATE: the EvidenceCredibility→float adaptation
+         (``{eid: ec.credibility_weight}``) feeds ``populate_disclosure`` (which expects FLOAT weights,
+         not the EvidenceCredibility object), populating span_verdict / credibility_weight /
+         independent_origin_count / certainty_label.
+      3. P3 CERTAINTY CARRIER (Codex I-cred-012 iter-5 P2): ``populate_disclosure`` derives certainty
+         from credibility/origins ONLY; it does NOT see the P3 supersession downgrade. So for each
+         populated SV whose cited evidence carries ``certainty_downgrade=True``, cap its certainty_label
+         (never above "moderate") and surface the source's ``soft_warning`` on the SV's ``soft_warnings``.
+
+    Inputs are NOT mutated; ``populate_disclosure`` returns NEW SVs via ``dataclasses.replace``.
+    """
+    from src.polaris_graph.synthesis.disclosure_population import populate_disclosure
+
+    cred_by_ev = analysis.credibility_by_evidence or {}
+    origin_by_ev = analysis.origin_by_evidence or {}
+
+    # ── Step 1: coverage assertion (fail-loud BEFORE populate) ──
+    for sv in (svs or []):
+        for eid in _cited_evidence_ids_for_coverage(sv):
+            if eid not in cred_by_ev or eid not in origin_by_ev:
+                raise CredibilityPassError(
+                    "abort_credibility_coverage_gap: a cited evidence_id "
+                    f"({eid!r}) emitted by the resolver has no credibility/origin coverage "
+                    "in the credibility analysis; refusing to disclose a claim whose source "
+                    "the activated pass never scored (fail-loud, never a false-green advisory)"
+                )
+
+    # ── Step 2: EvidenceCredibility → FLOAT adaptation, then populate ──
+    cred_floats = {
+        eid: ec.credibility_weight for eid, ec in cred_by_ev.items()
+    }
+    populated = populate_disclosure(svs, cred_floats, origin_by_ev)
+
+    # ── Step 3: P3 certainty carrier (downgrade + soft_warning surface) ──
+    out: list = []
+    for sv in populated:
+        downgrade = False
+        warnings: list[str] = []
+        for eid in _cited_evidence_ids_for_coverage(sv):
+            ec = cred_by_ev.get(eid)
+            if ec is None:
+                continue
+            if bool(getattr(ec, "certainty_downgrade", False)):
+                downgrade = True
+                warn = getattr(ec, "soft_warning", None)
+                if warn:
+                    warnings.append(str(warn))
+        if not downgrade:
+            out.append(sv)
+            continue
+        # Cap certainty at "moderate" (never "high") when any cited source was P3-downgraded.
+        new_label = sv.certainty_label
+        if new_label == "high":
+            new_label = "moderate"
+        existing_warnings = list(getattr(sv, "soft_warnings", None) or [])
+        for w in warnings:
+            if w not in existing_warnings:
+                existing_warnings.append(w)
+        out.append(dataclasses.replace(
+            sv,
+            certainty_label=new_label,
+            soft_warnings=existing_warnings,
+        ))
+    return out
diff --git a/tests/polaris_graph/generator/test_disclosure_failloud_wiring_icred008b.py b/tests/polaris_graph/generator/test_disclosure_failloud_wiring_icred008b.py
new file mode 100644
index 00000000..a2a3d262
--- /dev/null
+++ b/tests/polaris_graph/generator/test_disclosure_failloud_wiring_icred008b.py
@@ -0,0 +1,106 @@
+"""I-cred-008b (#1162) — the coverage-gap fail-loud SURVIVES every swallow-point + named-status routing.
+
+The disclosure populate runs at four resolve sites; sites 1/3 (and the M-44/M-47 REGEN re-runs of them)
+plus the fact-dedup re-resolve and the quantified path all sit inside broad ``except``/``return_exceptions``
+handlers that safe-degrade on their OWN faults. A credibility-disclosure coverage gap must NEVER be
+swallowed by any of them — it is a faithfulness abort that must reach the run handler as
+``abort_credibility_coverage_gap``. These tests pin that contract by SOURCE inspection (the swallow-points
+are inside one heavy async function; source assertions are the honest offline proof the guards exist on the
+exact handlers) plus a behavioral check of the run-handler discrimination predicate.
+"""
+from __future__ import annotations
+
+import inspect
+import re
+
+import src.polaris_graph.generator.multi_section_generator as m
+
+
+def _normalize(src: str) -> str:
+    return re.sub(r"\s+", " ", src)
+
+
+def test_fact_dedup_except_reraises_credibility_pass_error():
+    src = _normalize(inspect.getsource(m.generate_multi_section_report))
+    # The fact-dedup safe-degrade handler must re-raise CredibilityPassError before logging "without dedup".
+    assert "if isinstance(exc, CredibilityPassError): raise" in src, (
+        "fact-dedup except must re-raise CredibilityPassError (fail-loud), not swallow it"
+    )
+
+
+def test_m44_regen_reraises_credibility_pass_error():
+    src = _normalize(inspect.getsource(m.generate_multi_section_report))
+    # M-44 regen uses gather(return_exceptions=True); a captured CredibilityPassError must be re-raised.
+    assert "if isinstance(regen_result, CredibilityPassError): raise regen_result" in src, (
+        "M-44 regen must re-raise a captured CredibilityPassError (return_exceptions=True swallows otherwise)"
+    )
+
+
+def test_m47_regen_reraises_credibility_pass_error():
+    src = _normalize(inspect.getsource(m.generate_multi_section_report))
+    # M-47 regen's except Exception wraps _bounded_run; must re-raise CredibilityPassError.
+    # (two distinct re-raise sites carry isinstance(exc, CredibilityPassError): one fact-dedup, one M-47.)
+    assert src.count("if isinstance(exc, CredibilityPassError): raise") >= 2, (
+        "M-47 regen except must also re-raise CredibilityPassError (fact-dedup + M-47 = 2 sites)"
+    )
+
+
+def test_all_four_sites_present_in_source():
+    """Each of the four cited-prose resolve sites carries the apply_disclosure_to_svs call (site map)."""
+    gen_src = inspect.getsource(m.generate_multi_section_report)
+    run_section_src = inspect.getsource(m._run_section)
+    # site 1 (legacy _run_section) and site 2 (fact-dedup) live across the two functions
+    assert "apply_disclosure_to_svs" in run_section_src, "site 1 (legacy _run_section) missing populate"
+    assert gen_src.count("apply_disclosure_to_svs") >= 1, "site 2 (fact-dedup) missing populate"
+
+    import src.polaris_graph.generator.contract_section_runner as csr
+    assert "apply_disclosure_to_svs" in inspect.getsource(csr.run_contract_section), (
+        "site 3 (contract runner) missing populate"
+    )
+    import src.polaris_graph.generator.quantified_analysis as qa
+    assert "apply_disclosure_to_svs" in inspect.getsource(qa.run_quantified_section), (
+        "site 4 (quantified) missing populate"
+    )
+
+
+def test_run_section_has_additive_credibility_analysis_param():
+    sig = inspect.signature(m._run_section)
+    assert sig.parameters["credibility_analysis"].default is None  # byte-identical when unpassed
+
+    import src.polaris_graph.generator.contract_section_runner as csr
+    assert inspect.signature(csr.run_contract_section).parameters[
+        "credibility_analysis"].default is None
+    import src.polaris_graph.generator.quantified_analysis as qa
+    assert inspect.signature(qa.run_quantified_section).parameters[
+        "credibility_analysis"].default is None
+
+
+# ── named-status routing in the run handler (behavioral discrimination) ──────
+def test_named_status_routing_discrimination():
+    """The run handler maps ONLY a coverage-gap message to the named status; other
+    CredibilityPassErrors (judge_error / independence-gap raised by the pass itself) fall through."""
+    from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
+
+    coverage_gap = CredibilityPassError(
+        "abort_credibility_coverage_gap: a cited evidence_id ('e9') emitted by the resolver has no "
+        "credibility/origin coverage"
+    )
+    judge_err = CredibilityPassError(
+        "abort_credibility_pass_error: the production credibility judge failed for 2 source(s)"
+    )
+    # the handler predicate (mirrors run_honest_sweep_r3.run_one_query)
+    def routes_to_named(exc):
+        return "abort_credibility_coverage_gap" in str(exc)
+
+    assert routes_to_named(coverage_gap) is True
+    assert routes_to_named(judge_err) is False
+
+
+def test_runner_registers_named_status_and_handler():
+    import scripts.run_honest_sweep_r3 as r
+    assert "abort_credibility_coverage_gap" in r.UNIFIED_STATUS_VALUES
+    assert r.to_unified_status("abort_credibility_coverage_gap") == "abort_credibility_coverage_gap"
+    # the run handler distinguishes coverage-gap from other CredibilityPassErrors via the message.
+    src = _normalize(inspect.getsource(r.run_one_query))
+    assert 'except _CredPassErrForAbort' in src
+    assert 'if "abort_credibility_coverage_gap" not in str(_cge): raise' in src
diff --git a/tests/polaris_graph/generator/test_disclosure_resolve_sites_icred008b.py b/tests/polaris_graph/generator/test_disclosure_resolve_sites_icred008b.py
new file mode 100644
index 00000000..f4f4a901
--- /dev/null
+++ b/tests/polaris_graph/generator/test_disclosure_resolve_sites_icred008b.py
@@ -0,0 +1,288 @@
+"""I-cred-008b (#1162) — multi-site disclosure wiring smoke (offline, no network).
+
+Proves the populated per-claim disclosure rides through the resolve sites into
+``SectionResult.kept_sentences_pre_resolve``, at BOTH:
+  * the V30 CONTRACT runner (run_contract_section, site 3/4) — the iter-4 P1-1 multi-site requirement,
+  * the FACT-DEDUP re-resolve (site 2/4) — reproduces the edited code path,
+and that with ``credibility_analysis=None`` the SVs are byte-identical (no populate).
+
+The LLM is injected (fake); strict_verify + the citation rewriter are REAL (same as live sweeps).
+"""
+from __future__ import annotations
+
+import json
+import re
+from pathlib import Path
+from types import SimpleNamespace
+from typing import Any
+
+import pytest
+import yaml
+
+from src.polaris_graph.synthesis.credibility_pass import (
+    CredibilityAnalysis,
+    EvidenceCredibility,
+    apply_disclosure_to_svs,
+)
+
+
+@pytest.fixture(scope="module")
+def clinical_template() -> dict:
+    with Path("config/scope_templates/clinical.yaml").open("r", encoding="utf-8") as f:
+        return yaml.safe_load(f)
+
+
+def _stub_fetch_rows(compiled):
+    from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
+    return tuple(
+        FrameRow(
+            entity_id=b.entity_id,
+            entity_type=b.entity_type,
+            rendering_slot=b.rendering_slot,
+            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
+            direct_quote=(
+                "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change in "
+                "HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
+            ),
+            quote_source="crossref_abstract",
+            doi="10.1056/NEJMoa2107519" if "surpass_2" in b.entity_id else "10.1/stub",
+            pmid=None, oa_pdf_url=None, url=None,
+            title=f"Title {b.entity_id}", authors=("Smith J",), journal="Lancet",
+            year=2021, failure_reason=None, retrieval_attempts=(), retrieval_timings=(),
+        )
+        for b in compiled.evidence_bindings
+    )
+
+
+def _analysis_covering(evidence_pool: dict, *, downgrade_ids=()) -> CredibilityAnalysis:
+    """Build a CredibilityAnalysis covering EVERY evidence_id in the pool (no coverage gap)."""
+    cred: dict[str, EvidenceCredibility] = {}
+    origin: dict[str, str] = {}
+    for i, eid in enumerate(evidence_pool):
+        origin[eid] = f"origin_{i}"
+        cred[eid] = EvidenceCredibility(
+            evidence_id=eid,
+            credibility_weight=0.85,
+            reliability_score=0.85,
+            relevance_score=0.85,
+            origin_cluster_id=f"origin_{i}",
+            is_canonical_origin=True,
+            certainty_downgrade=(eid in downgrade_ids),
+            soft_warning=("superseded by a newer source" if eid in downgrade_ids else None),
+        )
+    return CredibilityAnalysis(
+        credibility_by_evidence=cred, origin_by_evidence=origin,
+        claims=[], edges=[], weight_mass=[],
+    )
+
+
+async def _fake_llm(prompt: str):
+    m = re.search(r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)", prompt, re.DOTALL)
+    if not m:
+        return json.dumps({"fields": []}), 500, 200
+    required = [
+        line.strip("- ").strip()
+        for line in m.group(1).strip().splitlines()
+        if line.strip().startswith("-")
+    ]
+    fields = []
+    for fname in required:
+        if fname == "N":
+            fields.append({"field_name": "N", "status": "extracted",
+                           "value": "N=1879", "source_span": "N=1879"})
+        else:
+            fields.append({"field_name": fname, "status": "not_extractable",
+                           "value": None, "source_span": None})
+    return json.dumps({"fields": fields}), 500, 200
+
+
+def _build_contract_inputs(clinical_template):
+    from src.polaris_graph.generator.contract_section_runner import (
+        ContractSectionPlanExt,
+        register_frame_rows_into_evidence_pool,
+    )
+    from src.polaris_graph.nodes.contract_outline import compose_outline_from_contract
+    from src.polaris_graph.nodes.frame_compiler import compile_frame
+
+    cf = compile_frame("tirzepatide evidence", clinical_template, "clinical_tirzepatide_t2dm")
+    rows = _stub_fetch_rows(cf)
+    outline = compose_outline_from_contract(cf, rows)
+    section = next(s for s in outline.sections if s.section == "Efficacy")
+    plan = ContractSectionPlanExt(
+        title=section.section, focus=section.focus,
+        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
+        slots=section.slots,
+        frame_rows_by_entity={r.entity_id: r for r in rows},
+        contract_entities_by_id=cf.contract.entities_by_id(),
+        research_question="tirzepatide evidence",
+    )
+    evidence_pool: dict[str, dict[str, Any]] = {}
+    register_frame_rows_into_evidence_pool(evidence_pool, rows)
+    return plan, evidence_pool
+
+
+class _SR:
+    def __init__(self, **kwargs):
+        self.__dict__.update(kwargs)
+
+
+# ── (b1) contract site: kept SVs carry the disclosure ────────────────────────
+@pytest.mark.asyncio
+async def test_contract_site_populates_disclosure(clinical_template):
+    from src.polaris_graph.generator.contract_section_runner import run_contract_section
+    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
+    from src.polaris_graph.generator.provenance_generator import strict_verify
+
+    plan, evidence_pool = _build_contract_inputs(clinical_template)
+    analysis = _analysis_covering(evidence_pool)
+
+    result, _payloads = await run_contract_section(
+        plan, evidence_pool,
+        llm_call=_fake_llm, section_result_cls=_SR,
+        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
+        credibility_analysis=analysis,
+    )
+    kept = result.kept_sentences_pre_resolve
+    assert kept, "contract section produced kept SVs"
+    # Every kept SV carries the populated disclosure (span_verdict + a certainty bucket).
+    for sv in kept:
+        assert sv.span_verdict in ("SUPPORTS", "UNSUPPORTED")
+        assert sv.certainty_label in ("high", "moderate", "low")
+    assert any(sv.credibility_weight is not None for sv in kept), (
+        "at least one kept SV must carry a credibility_weight (cited evidence is covered)"
+    )
+
+
+# ── (a) flag-OFF byte-identical at the contract site ─────────────────────────
+@pytest.mark.asyncio
+async def test_contract_site_flag_off_byte_identical(clinical_template):
+    from src.polaris_graph.generator.contract_section_runner import run_contract_section
+    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
+    from src.polaris_graph.generator.provenance_generator import strict_verify
+
+    plan, evidence_pool = _build_contract_inputs(clinical_template)
+
+    result_off, _ = await run_contract_section(
+        plan, evidence_pool,
+        llm_call=_fake_llm, section_result_cls=_SR,
+        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
+        credibility_analysis=None,
+    )
+    # OFF: SVs carry NONE of the disclosure fields (inert defaults), and verified_text is unchanged
+    # vs a separate OFF run (determinism check).
+    for sv in result_off.kept_sentences_pre_resolve:
+        assert sv.span_verdict == ""
+        assert sv.credibility_weight is None
+        assert sv.independent_origin_count is None
+        assert sv.certainty_label == ""
+
+    plan2, pool2 = _build_contract_inputs(clinical_template)
+    result_off2, _ = await run_contract_section(
+        plan2, pool2,
+        llm_call=_fake_llm, section_result_cls=_SR,
+        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
+        credibility_analysis=None,
+    )
+    assert result_off.verified_text == result_off2.verified_text
+
+
+# ── (b2) fact-dedup re-resolve site: reproduce the edited code path ──────────
+def test_fact_dedup_site_populates_disclosure():
+    """Reproduce the fact-dedup re-resolve block: build final_svs, apply the helper, resolve.
+
+    Mirrors multi_section_generator.py site 2/4 exactly: post-dedup SVs are populated BEFORE the
+    local `_resolve(...)` ALIAS, then assigned to kept_sentences_pre_resolve. We assert the populated
+    SVs survive resolution (verified_text renders) AND carry the disclosure.
+    """
+    from src.polaris_graph.generator.provenance_generator import (
+        SentenceVerification,
+        resolve_provenance_to_citations as _resolve,
+        strict_verify,
+    )
+
+    quote = "Tirzepatide reduced HbA1c by 2.07 percent at 40 weeks in SURPASS-2."
+    evidence_pool = {
+        "ev1": {
+            "evidence_id": "ev1",
+            "direct_quote": quote,  # strict_verify reads direct_quote (or statement), NOT text
+            "source_url": "https://example.org/surpass2",
+            "tier": "T1",
+        },
+    }
+    # A real kept SV (post-dedup "rewrite") with a valid provenance token over the evidence span.
+    sentence = f"Tirzepatide reduced HbA1c by 2.07 percent at 40 weeks in SURPASS-2.[#ev:ev1:0-{len(quote)}]"
+    report = strict_verify(sentence, evidence_pool)
+    final_svs = list(report.kept_sentences)
+    assert final_svs, "the rewrite sentence must pass strict_verify to be a kept post-dedup SV"
+
+    analysis = _analysis_covering(evidence_pool)
+    # ── the exact edited site-2 sequence ──
+    final_svs = apply_disclosure_to_svs(final_svs, analysis)
+    new_text, _new_biblio = _resolve(final_svs, evidence_pool)
+    kept_sentences_pre_resolve = list(final_svs)  # the SectionResult assignment
+
+    assert new_text, "resolve produced text"
+    assert kept_sentences_pre_resolve[0].span_verdict == "SUPPORTS"
+    assert kept_sentences_pre_resolve[0].credibility_weight is not None
+    assert kept_sentences_pre_resolve[0].certainty_label in ("high", "moderate", "low")
+
+    # flag-OFF parity: the SAME SVs without the helper carry no disclosure.
+    report_off = strict_verify(sentence, evidence_pool)
+    off_svs = list(report_off.kept_sentences)
+    assert off_svs[0].span_verdict == "" and off_svs[0].credibility_weight is None
+
+
+# ── (e at a resolve site) coverage gap fires fail-loud at the contract site ──
+@pytest.mark.asyncio
+async def test_contract_site_coverage_gap_fires(clinical_template):
+    from src.polaris_graph.generator.contract_section_runner import run_contract_section
+    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
+    from src.polaris_graph.generator.provenance_generator import strict_verify
+    from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
+
+    plan, evidence_pool = _build_contract_inputs(clinical_template)
+    # An analysis covering a DIFFERENT, irrelevant evidence_id => every cited token is uncovered.
+    empty_analysis = CredibilityAnalysis(
+        credibility_by_evidence={
+            "unrelated_ev": EvidenceCredibility(
+                evidence_id="unrelated_ev", credibility_weight=0.5,
+                reliability_score=0.5, relevance_score=0.5,
+                origin_cluster_id="oX", is_canonical_origin=True,
+                certainty_downgrade=False, soft_warning=None,
+            )
+        },
+        origin_by_evidence={"unrelated_ev": "oX"},
+        claims=[], edges=[], weight_mass=[],
+    )
+    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
+        await run_contract_section(
+            plan, evidence_pool,
+            llm_call=_fake_llm, section_result_cls=_SR,
+            strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
+            credibility_analysis=empty_analysis,
+        )
+
+
+# ── (d at a resolve site) certainty carrier rides through the contract site ──
+@pytest.mark.asyncio
+async def test_contract_site_certainty_carrier(clinical_template):
+    from src.polaris_graph.generator.contract_section_runner import run_contract_section
+    from src.polaris_graph.generator.live_deepseek_generator import _rewrite_draft_with_spans
+    from src.polaris_graph.generator.provenance_generator import strict_verify
+
+    plan, evidence_pool = _build_contract_inputs(clinical_template)
+    # Downgrade every cited source: every kept SV's certainty must be capped (never "high")
+    # and carry the soft_warning.
+    analysis = _analysis_covering(evidence_pool, downgrade_ids=tuple(evidence_pool.keys()))
+
+    result, _ = await run_contract_section(
+        plan, evidence_pool,
+        llm_call=_fake_llm, section_result_cls=_SR,
+        strict_verify_fn=strict_verify, rewrite_fn=_rewrite_draft_with_spans,
+        credibility_analysis=analysis,
+    )
+    kept = result.kept_sentences_pre_resolve
+    assert kept
+    for sv in kept:
+        assert sv.certainty_label != "high", "P3 downgrade must cap certainty below high"
+        assert "superseded by a newer source" in (sv.soft_warnings or [])
diff --git a/tests/polaris_graph/synthesis/test_disclosure_apply_icred008b.py b/tests/polaris_graph/synthesis/test_disclosure_apply_icred008b.py
new file mode 100644
index 00000000..43ebdd97
--- /dev/null
+++ b/tests/polaris_graph/synthesis/test_disclosure_apply_icred008b.py
@@ -0,0 +1,209 @@
+"""I-cred-008b (#1162) — the SHARED disclosure populate+carrier+coverage helper.
+
+Offline, deterministic, no network. Exercises ``apply_disclosure_to_svs`` directly:
+  (c) the EvidenceCredibility -> FLOAT credibility_weight adaptation,
+  (d) the P3 certainty downgrade CARRIER (cap certainty + surface soft_warning),
+  (e) ``abort_credibility_coverage_gap`` fires on an uncovered cited token (fail-loud),
+plus the no-mutation / no-verifier-touch posture the four resolve sites depend on.
+"""
+from __future__ import annotations
+
+from types import SimpleNamespace
+
+import pytest
+
+from src.polaris_graph.generator.provenance_generator import SentenceVerification
+from src.polaris_graph.synthesis.credibility_pass import (
+    CredibilityAnalysis,
+    CredibilityPassError,
+    EvidenceCredibility,
+    apply_disclosure_to_svs,
+)
+
+
+def _sv(sentence, eids, is_verified=True):
+    return SentenceVerification(
+        sentence=sentence,
+        tokens=[SimpleNamespace(evidence_id=e, start=0, end=1) for e in eids],
+        is_verified=is_verified,
+    )
+
+
+def _ec(eid, weight, *, downgrade=False, soft_warning=None, origin="o1"):
+    return EvidenceCredibility(
+        evidence_id=eid,
+        credibility_weight=weight,
+        reliability_score=weight,
+        relevance_score=weight,
+        origin_cluster_id=origin,
+        is_canonical_origin=True,
+        certainty_downgrade=downgrade,
+        soft_warning=soft_warning,
+    )
+
+
+def _analysis(ecs, origins):
+    return CredibilityAnalysis(
+        credibility_by_evidence={ec.evidence_id: ec for ec in ecs},
+        origin_by_evidence=dict(origins),
+        claims=[],
+        edges=[],
+        weight_mass=[],
+    )
+
+
+# ── (c) EvidenceCredibility -> FLOAT adaptation ──────────────────────────────
+def test_evidence_credibility_to_float_adaptation():
+    """The helper must feed populate_disclosure the FLOAT .credibility_weight, not the object.
+
+    Two cited sources at 0.9 / 0.3; MIN over cited = 0.3 proves the float (not the object) reached
+    populate_disclosure (an EvidenceCredibility object would have raised or produced None).
+    """
+    analysis = _analysis(
+        [_ec("e0", 0.9, origin="o1"), _ec("e1", 0.3, origin="o2")],
+        {"e0": "o1", "e1": "o2"},
+    )
+    out = apply_disclosure_to_svs([_sv("The rate was 5 percent.", ["e0", "e1"])], analysis)
+    assert out[0].span_verdict == "SUPPORTS"
+    assert abs(out[0].credibility_weight - 0.3) < 1e-9  # MIN over the FLOAT weights
+    assert out[0].independent_origin_count == 2  # two distinct origin clusters
+
+
+# ── (d) P3 certainty downgrade CARRIER ───────────────────────────────────────
+def test_certainty_carrier_caps_and_surfaces_warning():
+    """populate_disclosure would compute 'high' (two origins, cred 0.9); the P3 downgrade caps it."""
+    analysis = _analysis(
+        [
+            _ec("e0", 0.9, origin="o1", downgrade=True, soft_warning="superseded by 2026 guideline"),
+            _ec("e1", 0.9, origin="o2"),
+        ],
+        {"e0": "o1", "e1": "o2"},
+    )
+    out = apply_disclosure_to_svs([_sv("s", ["e0", "e1"])], analysis)
+    # Without the carrier this would be 'high'; the P3 downgrade caps it at 'moderate'.
+    assert out[0].certainty_label == "moderate"
+    assert "superseded by 2026 guideline" in out[0].soft_warnings
+
+
+def test_certainty_carrier_noop_when_no_downgrade():
+    """No cited source downgraded => certainty + soft_warnings unchanged from populate_disclosure."""
+    analysis = _analysis(
+        [_ec("e0", 0.9, origin="o1"), _ec("e1", 0.9, origin="o2")],
+        {"e0": "o1", "e1": "o2"},
+    )
+    out = apply_disclosure_to_svs([_sv("s", ["e0", "e1"])], analysis)
+    assert out[0].certainty_label == "high"
+    assert out[0].soft_warnings == []
+
+
+# ── (e) coverage-gap fail-loud ───────────────────────────────────────────────
+def test_coverage_gap_raises_on_uncovered_cited_token():
+    """A cited token whose evidence_id is absent from the analysis must FAIL LOUD."""
+    analysis = _analysis([_ec("e0", 0.8, origin="o1")], {"e0": "o1"})
+    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
+        apply_disclosure_to_svs([_sv("s", ["e0", "e_missing"])], analysis)
+
+
+def test_coverage_gap_raises_when_origin_missing_even_if_cred_present():
+    """Coverage requires BOTH credibility AND origin coverage (both maps co-built per row)."""
+    analysis = CredibilityAnalysis(
+        credibility_by_evidence={"e0": _ec("e0", 0.8, origin="o1")},
+        origin_by_evidence={},  # origin coverage missing
+        claims=[], edges=[], weight_mass=[],
+    )
+    with pytest.raises(CredibilityPassError, match="abort_credibility_coverage_gap"):
+        apply_disclosure_to_svs([_sv("s", ["e0"])], analysis)
+
+
+# ── posture: pure + never touches verifier fields ────────────────────────────
+def test_helper_is_pure_and_advisory():
+    analysis = _analysis([_ec("e0", 0.8, origin="o1")], {"e0": "o1"})
+    sv = _sv("s", ["e0"], is_verified=True)
+    out = apply_disclosure_to_svs([sv], analysis)
+    # input untouched
+    assert sv.span_verdict == "" and sv.credibility_weight is None
+    assert sv.certainty_label == "" and sv.soft_warnings == []
+    # output keeps verifier fields
+    assert out[0].is_verified is True
+    assert out[0].sentence == sv.sentence and out[0].tokens == sv.tokens
+
+
+def test_unverified_sentence_gets_unsupported_verdict_low_certainty():
+    analysis = _analysis([_ec("e0", 0.9, origin="o1")], {"e0": "o1"})
+    out = apply_disclosure_to_svs([_sv("s", ["e0"], is_verified=False)], analysis)
+    assert out[0].span_verdict == "UNSUPPORTED"
+    assert out[0].certainty_label == "low"
+
+
+# ── site 4 (quantified): the surfaced telem["claim_disclosure"] rows ─────────
+def test_quantified_site_surfaces_disclosure_in_telemetry():
+    """run_quantified_section (site 4, no SectionResult) must surface disclosure rows in telem.
+
+    Offline: a deterministic spec_provider + REAL execute/verify. credibility_analysis covers the two
+    cited inputs (ev_017, ev_021) so there is no coverage gap; telem['claim_disclosure'] carries the
+    per-claim disclosure the runner merges into claim_disclosure.json.
+    """
+    import asyncio
+
+    from src.polaris_graph.generator.quantified_analysis import run_quantified_section
+
+    evidence_pool = {
+        "ev_017": {
+            "evidence_id": "ev_017",
+            "direct_quote": "The program cost was $1.548 billion in fiscal 2024.",
+            "source_url": "https://example.org/a", "tier": "T1",
+        },
+        "ev_021": {
+            "evidence_id": "ev_021",
+            "direct_quote": "Annual maintenance is $120 million per year.",
+            "source_url": "https://example.org/b", "tier": "T1",
+        },
+    }
+
+    def _spec(_q, _sourced):
+        # Bind each datapoint_ref to the EXACT extracted sourced number (label/context/value),
+        # so build_quantified_spec's unique-literal match succeeds. We pick the 1.548e9 / 1.2e8 rows.
+        capex = next(d for d in _sourced if d.get("value") == "1548000000.0")
+        opex = next(d for d in _sourced if d.get("value") == "120000000.0")
+        return {
+            "model_id": "tco", "title": "Total cost of ownership",
+            "inputs": [
+                {"name": "capex", "datapoint_ref": {
+                    "ev_id": capex["evidence_id"], "label": capex["label"],
+                    "context": capex["context"], "value": capex["value"], "unit": "USD"}},
+                {"name": "opex", "datapoint_ref": {
+                    "ev_id": opex["evidence_id"], "label": opex["label"],
+                    "context": opex["context"], "value": opex["value"], "unit": "USD"}},
+                {"name": "years", "base": 5.0, "unit": "years",
+                 "sweep": [1.0, 10.0, 1.0], "modeled": True},
+            ],
+            "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
+                         "formula": "capex + opex * years"}],
+            "sensitivity": [{"input": "years", "output": "tco"}],
+        }
+
+    async def _spec_provider(_q, _s):
+        return _spec(_q, _s)
+
+    analysis = _analysis(
+        [_ec("ev_017", 0.8, origin="o1"), _ec("ev_021", 0.6, origin="o2")],
+        {"ev_017": "o1", "ev_021": "o2"},
+    )
+
+    # ON: telem carries the disclosure rows.
+    section_md, telem = asyncio.run(run_quantified_section(
+        "q", evidence_pool, spec_provider=_spec_provider, credibility_analysis=analysis,
+    ))
+    assert section_md is not None
+    rows = telem.get("claim_disclosure")
+    assert rows, "quantified telemetry must surface claim_disclosure rows when analysis present"
+    for r in rows:
+        assert r["span_verdict"] in ("SUPPORTS", "UNSUPPORTED")
+        assert "credibility_weight" in r and "certainty_label" in r
+
+    # OFF (analysis None): no claim_disclosure key (byte-identical telemetry).
+    section_md_off, telem_off = asyncio.run(run_quantified_section(
+        "q", evidence_pool, spec_provider=_spec_provider, credibility_analysis=None,
+    ))
+    assert section_md_off is not None
+    assert "claim_disclosure" not in telem_off
diff --git a/tests/polaris_graph/test_claim_disclosure_artifact_icred008b.py b/tests/polaris_graph/test_claim_disclosure_artifact_icred008b.py
new file mode 100644
index 00000000..3a5cd999
--- /dev/null
+++ b/tests/polaris_graph/test_claim_disclosure_artifact_icred008b.py
@@ -0,0 +1,96 @@
+"""I-cred-008b (#1162) — runner-side claim_disclosure.json serialization shape (offline, pure).
+
+Tests _build_claim_disclosure_doc, the pure helper that builds the claim_disclosure.json document:
+  * flag-OFF (credibility_analysis is None) => returns None => NO artifact (byte-identical),
+  * flag-ON => one entry per section per kept SV with the six advisory disclosure fields,
+  * the quantified path (no SectionResult) rides via telemetry["claim_disclosure"].
+"""
+from __future__ import annotations
+
+from types import SimpleNamespace
+
+from scripts.run_honest_sweep_r3 import _build_claim_disclosure_doc
+
+
+def _sv(sentence, *, span_verdict="SUPPORTS", cred=0.8, origins=2, certainty="high", warns=()):
+    return SimpleNamespace(
+        sentence=sentence,
+        span_verdict=span_verdict,
+        credibility_weight=cred,
+        independent_origin_count=origins,
+        certainty_label=certainty,
+        soft_warnings=list(warns),
+    )
+
+
+def _section(title, kept, *, dropped=False):
+    return SimpleNamespace(
+        title=title,
+        kept_sentences_pre_resolve=kept,
+        dropped_due_to_failure=dropped,
+    )
+
+
+def test_flag_off_returns_none_no_artifact():
+    """No credibility_analysis => None => the runner writes NO claim_disclosure.json."""
+    multi = SimpleNamespace(credibility_analysis=None, sections=[_section("Efficacy", [_sv("s")])])
+    assert _build_claim_disclosure_doc(multi, None) is None
+
+
+def test_flag_on_serializes_section_claims():
+    multi = SimpleNamespace(
+        credibility_analysis=object(),  # presence is all that matters here
+        sections=[
+            _section("Efficacy", [
+                _sv("Claim A.", cred=0.9, certainty="high"),
+                _sv("Claim B.", cred=0.3, certainty="low", warns=["superseded"]),
+            ]),
+            _section("Safety", [_sv("Claim C.", span_verdict="UNSUPPORTED", certainty="low")]),
+        ],
+    )
+    doc = _build_claim_disclosure_doc(multi, None)
+    assert doc is not None
+    titles = [s["title"] for s in doc["sections"]]
+    assert titles == ["Efficacy", "Safety"]
+    efficacy = doc["sections"][0]
+    assert len(efficacy["claims"]) == 2
+    a = efficacy["claims"][0]
+    assert set(a) == {
+        "sentence", "span_verdict", "credibility_weight",
+        "independent_origin_count", "certainty_label", "soft_warnings",
+    }
+    assert a["span_verdict"] == "SUPPORTS" and a["credibility_weight"] == 0.9
+    assert efficacy["claims"][1]["soft_warnings"] == ["superseded"]
+
+
+def test_dropped_and_empty_sections_excluded():
+    multi = SimpleNamespace(
+        credibility_analysis=object(),
+        sections=[
+            _section("Dropped", [_sv("x")], dropped=True),  # excluded (failure)
+            _section("Empty", []),                           # excluded (no kept)
+            _section("Kept", [_sv("y")]),
+        ],
+    )
+    doc = _build_claim_disclosure_doc(multi, None)
+    assert [s["title"] for s in doc["sections"]] == ["Kept"]
+
+
+def test_quantified_rows_appended_from_telemetry():
+    multi = SimpleNamespace(credibility_analysis=object(), sections=[])
+    telem = {
+        "claim_disclosure": [
+            {"sentence": "TCO is $2.1B.", "span_verdict": "SUPPORTS",
+             "credibility_weight": 0.7, "independent_origin_count": 2,
+             "certainty_label": "moderate", "soft_warnings": []},
+        ],
+    }
+    doc = _build_claim_disclosure_doc(multi, telem)
+    assert doc["sections"][-1]["title"] == "Quantified Trade-off"
+    assert doc["sections"][-1]["claims"][0]["sentence"] == "TCO is $2.1B."
+
+
+def test_quantified_absent_when_no_telemetry_rows():
+    multi = SimpleNamespace(credibility_analysis=object(), sections=[_section("S", [_sv("z")])])
+    doc = _build_claim_disclosure_doc(multi, {"enabled": True})  # no claim_disclosure key
+    assert [s["title"] for s in doc["sections"]] == ["S"]
diff --git a/tests/polaris_graph/test_manifest_contract.py b/tests/polaris_graph/test_manifest_contract.py
index f99b1718..929f7444 100644
--- a/tests/polaris_graph/test_manifest_contract.py
+++ b/tests/polaris_graph/test_manifest_contract.py
@@ -55,6 +55,7 @@ def test_manifest_contract_unified_taxonomy_defined() -> None:
         "abort_safety_refused",        # I-ready-007 (#1072): input harm-refusal before retrieval
         "abort_four_role_release_held",  # I-ready-016 (#1086): 4-role D8 held release
         "abort_journal_only_contract_conflict",  # I-ready-017 (#1134): journal_only required contract slot non-journal
+        "abort_credibility_coverage_gap",  # I-cred-008b (#1162): activated credibility-disclosure pass found an uncovered cited token
         "cancelled",                   # I-ready-016 (#1086): user-cancel terminal manifest status
         "error_unexpected",
         "error_journal_only_leak",     # I-ready-017 (#1134): journal_only fail-closed no-leak backstop
```
