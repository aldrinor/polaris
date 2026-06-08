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
## PHASE: I-cred-008b (#1162) — DIFF gate ITER 2. Iter-1 2xP1 + 2xP2 addressed:
- (P1-1 FIXED — real bug the iter-1 test missed) run_honest_sweep_r3.py: a non-coverage CredibilityPassError (judge_error / independence gap raised by the pass itself) was RE-RAISED inside the separate `except _CredPassErrForAbort`, which propagates OUT of run_one_query (sibling excepts don't chain) — so it ESCAPED instead of getting the error_unexpected manifest. FIX: removed the separate except; the routing now lives INSIDE the generic `except Exception` via a pure helper `_credibility_abort_status(exc)` — coverage-gap -> named status 'abort_credibility_coverage_gap'; EVERYTHING ELSE (incl. non-coverage CredibilityPassError) -> error_unexpected. No escape. The error_manifest uses `_unified_error_status` for both.
- (P2-1 FIXED) the run-handler test no longer mirrors the predicate — `test_named_status_routing_uses_the_real_handler_classifier` calls the REAL `_credibility_abort_status` on actual exception objects (coverage-gap -> named; judge_error CredibilityPassError -> None => error_unexpected; ValueError -> None), and `test_runner_registers_named_status_and_handler` now asserts the source uses `_credibility_abort_status(exc)`. This test WOULD catch the P1-1 bug.
- (P1-2 — render surface) RESOLVED by explicitly REVISING THE PLAN (Codex's offered option), see docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md Phase-8 REVISION note: Phase 8 is SPLIT. 008b = the DATA layer (populate the 4 fields at the 4 sites + emit the per-claim metadata sidecar claim_disclosure.json — which IS the 'only the metadata sidecar differs' surface the plan's own Phase-8 Verification line specifies; prose byte-identical OFF vs ON). The user-facing bibliography/Proof-Replay RENDER is deferred to NEW issue I-cred-009 (#1166) because resolve_provenance_to_citations is a core per-EVIDENCE function while the disclosure is per-SENTENCE — the render granularity+format is a deliberate UX decision, NOT a rushed signature change on the byte-identity-critical path.
- (P2-2) the sandbox 19/20 was a Codex-sandbox FILESYSTEM restriction (temp-write under AppData\Local\Temp blocked in the exec sandbox), NOT a code/test bug: the full suite is GREEN in the real env — 216 passed (tests/polaris_graph/generator + synthesis).
Re-verify: the P1-1 routing (non-coverage CredibilityPassError -> error_unexpected, not escape); the plan-split is an acceptable resolution of P1-2; OFF byte-identity holds.
```diff
diff --git a/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md b/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
index 452afe24..4d5b9c40 100644
--- a/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
+++ b/docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md
@@ -165,6 +165,7 @@ Each phase below = one GitHub Issue, one brief → Codex APPROVE → one diff 
 - **Offline tests:** end-to-end populates `credibility_weight` + `independent_origin_count` ("N sources → M origins") + `certainty_label` + `span_verdict`; bibliography renders all four; OFF byte-identity retained.
 - **Verification:** OFF byte-identity smoke (empty fields); ON-mode end-to-end fixture shows all four populated + rendered; `is_verified` and the rendered prose body are byte-identical between OFF and ON (only the metadata sidecar differs).
 - **Faithfulness-safety:** the four fields remain SIDE-OUTPUTS — never inputs to `is_verified` or the six checks; population reads upstream layer outputs, writes only the disclosure sidecar. OFF = byte-identical.
+- **REVISION (2026-06-08, I-cred-008b — Codex #008b diff P1-2):** Phase 8 is SPLIT into a data layer (008b, done) and a render layer (I-cred-009, deferred). **I-cred-008b delivers the DATA layer:** populate the four fields on the resolver-emitted SVs at all four cited-prose resolve sites (via the shared `apply_disclosure_to_svs`, with the P3 certainty carrier + a fail-loud coverage assertion), and emit the per-claim **metadata sidecar `claim_disclosure.json`** — which IS the "only the metadata sidecar differs" surface the Verification line above already specifies (prose body byte-identical OFF vs ON). **The user-facing bibliography / Proof-Replay RENDER is deferred to I-cred-009:** `resolve_provenance_to_citations` is a core *per-EVIDENCE* function while the disclosure is *per-SENTENCE*, so the render granularity + format (report appendix vs inline marker vs Proof-Replay chip vs bibliography) is a deliberate UX decision — not a rushed signature change to a function on the byte-identity-critical path. The sidecar makes the disclosure auditable offline now; the visible render lands in I-cred-009.
 
 ### Phase 9 — Additive verifier strengthening. [L8, §6c-7] — **HIGHEST FAITHFULNESS RISK; the only phase that edits `verify_sentence_provenance`.**
 - **Scope:** Wire NLI/QA entailment + unit/table/quantity + contradiction-sensitive checks as **additive fail-closed gates** invoked AFTER the six strict_verify checks. ON-mode flag-gated.
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 82c432dc..2cbdf540 100644
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
 
@@ -259,6 +266,62 @@ def to_unified_status(summary_status: str) -> str:
     return _SUMMARY_TO_UNIFIED.get(summary_status, "error_unexpected")
 
 
+def _credibility_abort_status(exc: BaseException) -> str | None:
+    """I-cred-008b (#1162) — Codex #008b P1-1: classify an exception that reached run_one_query's handler.
+
+    Returns ``"abort_credibility_coverage_gap"`` for a credibility-disclosure COVERAGE-GAP
+    ``CredibilityPassError`` (a cited token with no credibility/origin coverage); returns ``None`` for
+    EVERYTHING ELSE — including a NON-coverage ``CredibilityPassError`` (judge_error / independence gap
+    raised by the pass itself), which the caller then routes to ``error_unexpected``. Pure + behavioral so
+    the routing is unit-testable on real exception objects (not a mirrored predicate), which is exactly
+    what the original sibling-``except`` re-raise missed.
+    """
+    if isinstance(exc, _CredPassErrForAbort) and "abort_credibility_coverage_gap" in str(exc):
+        return "abort_credibility_coverage_gap"
+    return None
+
+
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
@@ -5116,6 +5179,9 @@ async def run_one_query(
                 _q_section_md, _quantified_telemetry = await run_quantified_section(
                     q["question"], _q_ev_pool,
                     spec_provider=_q_spec_provider, run_dir=str(run_dir),
+                    # I-cred-008b (#1162): thread the advisory credibility analysis from the
+                    # MultiSectionResult (None when the master flag is off => byte-identical).
+                    credibility_analysis=getattr(multi, "credibility_analysis", None),
                 )
                 if _q_section_md:
                     sections_concat += "\n\n" + _q_section_md
@@ -5130,6 +5196,15 @@ async def run_one_query(
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
 
@@ -5601,6 +5676,17 @@ async def run_one_query(
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
@@ -6625,9 +6711,24 @@ async def run_one_query(
             _log(f"[journal_only] abort manifest-write-also-failed: {_ja_mw}")
     except Exception as exc:
         tb = traceback.format_exc()
-        _log(f"[FATAL]       {exc}")
-        _log(tb)
-        summary["status"] = "error"
+        # I-cred-008b (#1162) — Codex #008b P1-1 fix: route the credibility-disclosure COVERAGE-GAP
+        # CredibilityPassError to its OWN named status, while ALL OTHER exceptions — INCLUDING a
+        # non-coverage CredibilityPassError (judge_error / independence-annotation gap raised by the
+        # pass itself) — fall through to error_unexpected. This branch MUST live in the SAME except
+        # block: a `raise` from a separate `except _CredPassErrForAbort` propagates OUT of run_one_query
+        # entirely (sibling excepts don't chain), so a non-coverage pass failure previously ESCAPED the
+        # error_unexpected manifest path. Folding the branch here closes that gap (still fail-loud, no
+        # false-green; only the STATUS label differs by exception kind).
+        _coverage_gap_status = _credibility_abort_status(exc)
+        if _coverage_gap_status is not None:
+            _unified_error_status = _coverage_gap_status
+            _log(f"[credibility]  ABORT: status={_coverage_gap_status} — {exc}")
+            summary["status"] = _coverage_gap_status
+        else:
+            _unified_error_status = "error_unexpected"
+            _log(f"[FATAL]       {exc}")
+            _log(tb)
+            summary["status"] = "error"
         summary["error"] = str(exc)[:300]
         # BUG-B-101 fix: previously the exception path wrote no
         # manifest, so a crashed run was indistinguishable from a
@@ -6640,7 +6741,7 @@ async def run_one_query(
                     "slug": q.get("slug", ""),
                     "domain": q.get("domain", ""),
                     "question": q.get("question", ""),
-                    "status": "error_unexpected",
+                    "status": _unified_error_status,
                     "error": str(exc)[:500],
                     "cost_usd": run_cost,
                     "budget_cap_usd": get_max_cost_per_run(),
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
index 00000000..c88dff6f
--- /dev/null
+++ b/tests/polaris_graph/generator/test_disclosure_failloud_wiring_icred008b.py
@@ -0,0 +1,110 @@
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
+def test_named_status_routing_uses_the_real_handler_classifier():
+    """Codex #008b P2-1/P1-1: exercise the ACTUAL run-handler classifier (_credibility_abort_status),
+    NOT a mirrored predicate. A coverage-gap CredibilityPassError -> the named status; a NON-coverage
+    CredibilityPassError (judge_error) AND any other exception -> None => error_unexpected. This pins the
+    P1-1 fix: a non-coverage pass failure routes to error_unexpected, it does NOT escape run_one_query
+    (the old sibling-`except` re-raise let it escape)."""
+    from src.polaris_graph.synthesis.credibility_pass import CredibilityPassError
+    from scripts.run_honest_sweep_r3 import _credibility_abort_status, to_unified_status
+
+    coverage_gap = CredibilityPassError(
+        "abort_credibility_coverage_gap: a cited evidence_id ('e9') emitted by the resolver has no "
+        "credibility/origin coverage"
+    )
+    judge_err = CredibilityPassError(
+        "abort_credibility_pass_error: the production credibility judge failed for 2 source(s)"
+    )
+    assert _credibility_abort_status(coverage_gap) == "abort_credibility_coverage_gap"
+    assert _credibility_abort_status(judge_err) is None          # => error_unexpected, NOT an escape
+    assert _credibility_abort_status(ValueError("unrelated")) is None
+    # the named status is a registered terminal status (round-trips through the unified map)
+    assert to_unified_status("abort_credibility_coverage_gap") == "abort_credibility_coverage_gap"
+
+
+def test_runner_registers_named_status_and_handler():
+    import scripts.run_honest_sweep_r3 as r
+    assert "abort_credibility_coverage_gap" in r.UNIFIED_STATUS_VALUES
+    assert r.to_unified_status("abort_credibility_coverage_gap") == "abort_credibility_coverage_gap"
+    # Codex #008b P1-1: the run handler routes via _credibility_abort_status INSIDE the generic
+    # `except Exception` (so a NON-coverage CredibilityPassError becomes error_unexpected, never an
+    # escape — the old sibling-`except _CredPassErrForAbort` + `raise` let it escape run_one_query).
+    src = _normalize(inspect.getsource(r.run_one_query))
+    assert "_credibility_abort_status(exc)" in src
```
