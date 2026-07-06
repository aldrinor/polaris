HARD ITERATION CAP: 5 per document. This is iter 3 of 5. APPROVE iff zero P0 and zero P1.

# Wave-3a U3-fix RE-GATE iter 3 — SELF-CONTAINED (your shell failed CreateProcessWithLogonW 1326 in iter 2; here is the surrounding code INLINED so you can verify the runtime claims WITHOUT any file read)

Your iter-2 verdict was REQUEST_CHANGES solely because your shell could not read files to verify: (1) in-process run_gate_b plumbing, (2) byte-unchanged faithfulness code, (3) the transport reachability. You said the diff/test are internally coherent with no source-level P0/P1. The INDEPENDENT Fable 5 gate (working file access) verified all of it and APPROVED: transport_fix_works_in_process=true, provenance_telemetry_only=true, off_byte_identical=true, faithfulness_untouched=true, 142 tests pass. Below is the exact surrounding code Fable cited, inlined from the real checked-out files, so you can confirm the same from text alone.

## CLAIM 1 — the sweep runs IN-PROCESS with run_gate_b (so a root-logger handler captures the module-logger [activation] markers)
```python
# run_gate_b.py — the sweep import + in-process await + asyncio.run:
7:hands the transport + builder into `run_one_query`.
90:# run_honest_sweep_r3.run_one_query -> journal_only_active (single source of truth, LAW VI).
215:    exist when the caller constructs the builder (they are produced inside `run_one_query` after
546:    # Retrieval breadth — the REAL run_one_query knobs (PG_SWEEP_*, default 12/12/40). NOT PG_LIVE_*.
701:    # found the paid Gate-B path (run_gate_b_query) NEVER wrapped run_one_query in asyncio.wait_for, so a
702:    # HANG anywhere inside = PERMANENT silence (run_one_query's inner B11 finally cannot fire on a hang) —
705:    # per-call 6500 < section 9000 < run-wall 10800, and run_gate_b_query now wraps run_one_query in
859:    # gate, lifted to the SECTION granularity): below it, run_one_query emits the NON-`partial`
1382:    # (-> RuntimeError), and run_one_query calls the loader with no surrounding try/except. The plan's
1481:    # are WIRED on the run path (each verified to have a live consumer that executes during run_one_query);
2479:    The wrong-question fix for the benchmark path. ``run_gate_b`` calls ``run_one_query`` DIRECTLY,
2520:    detached around a single ``asyncio.run(run_gate_b_query(...))`` so it never leaks across queries."""
```

## CLAIM 2 — the capture handler: class, root-logger attach, combined read, per-query detach in finally, fresh buffer
```python
2533: class _ActivationMarkerCaptureHandler(logging.Handler):
2534:     """Capture the Wave-3a ``[activation] <module>:`` marker lines so the post-run activation canary can
2535:     read the sink the markers actually reach. 10 of the 11 activated modules emit their marker via a Python
2536:     MODULE logger (``logger.info(...)``) that basicConfig streams to STDOUT ONLY — it NEVER reaches
2537:     run_dir/run_log.txt (Fable P0). The sweep runs run_gate_b_query IN-PROCESS, so attaching this to the
2538:     ROOT logger for the query's duration captures those records (child loggers propagate to root). Keeps
2539:     ONLY records whose message begins with ``[activation] `` (never the whole run's log stream — bounded
2540:     memory). A logging handler must NEVER raise into the caller, so ``emit`` swallows any formatting error.
2541:     Sequential-sweep safe (§8.4 — one query at a time); attached + detached around a single
2542:     ``asyncio.run(run_gate_b_query(...))`` so it never leaks across queries."""
2543: 
2544:     def __init__(self, sink: list[str]) -> None:
2545:         super().__init__()
2546:         self._sink = sink
2547: 
2548:     def emit(self, record: logging.LogRecord) -> None:
2549:         try:
2550:             _msg = record.getMessage()
2551:             if _msg.startswith(_ACTIVATION_MARKER_PREFIX):
2552:                 self._sink.append(_msg)
2553:         except Exception:  # noqa: BLE001 — a logging handler must never propagate an error to the caller
2554:             pass
2555: 
2556: 
    # ... attach + buffer (per query):
5605:         # handler attached, byte-identical). Root logger so a marker from ANY module logger is caught.
5606:         _activation_log_lines: list[str] = []
5607:         _activation_handler = None
5608:         _activation_root_logger = logging.getLogger()
5609:         if _activation_canary_enabled():
5610:             _activation_handler = _ActivationMarkerCaptureHandler(_activation_log_lines)
5611:             _activation_root_logger.addHandler(_activation_handler)
5612:         try:
5613:             summary = asyncio.run(
5614:                 run_gate_b_query(
5615:                     q, out_root, query_index=query_index, query_total=len(questions),
    # ... combined read (buffer + run_log):
5735:                     )
5736:                     if _activation_canary == "FAILED":
5737:                         overall_rc = 1
5738:             # OFF-purity (Codex+Fable P1): the shallow-report canary is a NEW Wave-1d record key. When the
5739:             # flag is OFF, _shallow_canary is None — adding "shallow_report_canary": null would give a
5740:             # flag-OFF sweep_summary.json a key the pre-Wave-1d baseline lacks (OFF not byte-identical). So
5741:             # the key is added ONLY when the wrapper actually ran (flag ON => always a string). The
5742:             # None-safe "ok" conjunct below is byte-identical when OFF (None != "FAILED" is True). The
5743:             # pre-existing "m6_cross_source_canary" key emission is left UNCHANGED (not a Wave-1d key).
5744:             _record = {
5745:                 "query_index": query_index,
    # ... detach in finally:
5820:             # so it never leaks into the next query's capture (sequential sweep, §8.4).
5821:             if _m6_handler is not None:
5822:                 _m6_logger.removeHandler(_m6_handler)
5823:             # Wave-3a (Fable P0): detach the activation capture handler on EVERY exit path too, so it never
5824:             # leaks into the next query's capture (mirror the M6 teardown).
5825:             if _activation_handler is not None:
5826:                 _activation_root_logger.removeHandler(_activation_handler)
5827:         _persist_sweep_summary()
    # ... OFF-purity: record key guard + None-safe ok:
5750:                     _status_ok
5751:                     and _breadth_canary != "FAILED"
5752:                     and _m6_canary != "FAILED"
5753:                     and _shallow_canary != "FAILED"
5754:                     and _activation_canary != "FAILED"
5755:                 ),
5756:                 "breadth_enrichment_canary": _breadth_canary,
5757:                 "m6_cross_source_canary": _m6_canary,
5758:                 "cost_usd": summary.get("cost_usd"),
5759:             }
5760:             if _shallow_canary is not None:
5761:                 _record["shallow_report_canary"] = _shallow_canary
5762:             # OFF-purity (Wave-3a): the activation canary is a NEW record key. When PG_ACTIVATION_CANARY is
5763:             # OFF, _activation_canary is None — adding "activation_canary": null would give a flag-OFF
5764:             # sweep_summary.json a key the pre-Wave-3a baseline lacks (OFF not byte-identical). So the key is
5765:             # added ONLY when the canary actually ran (flag ON => always a string). The None-safe "ok"
5766:             # conjunct above is byte-identical when OFF (None != "FAILED" is True). Mirrors the Wave-1d
5767:             # shallow-report guarded-key contract EXACTLY.
5768:             if _activation_canary is not None:
5769:                 _record["activation_canary"] = _activation_canary
5770:             _sweep_records.append(_record)
```

## CLAIM 3 — basicConfig ordering: run_honest_sweep_r3 is imported (firing its module-level basicConfig at INFO→stdout) BEFORE the handler attaches, so root level is INFO and module INFO records propagate
```python
# run_honest_sweep_r3.py module-level basicConfig:
55: sys.path.insert(0, str(ROOT / "src"))
56: 
57: logging.basicConfig(
58:     level=os.environ.get("PG_LOG_LEVEL", "INFO"),
59:     format="%(asctime)s %(name)s %(levelname)s %(message)s",
60:     datefmt="%H:%M:%S",
61:     stream=sys.stdout,
62: )
63: for noisy in ("httpx", "httpcore"):
# _log tee that writes run_log.txt (the ONE marker that rides the file):
9070:         # I-arch-004 F04 + GH #1259: on EITHER resume mode, APPEND so the pre-kill artifacts
9071:         # (retrieval/adequacy log lines) are preserved, not clobbered by the "w" truncation
9072:         # that a fresh run uses.
9073:         log_f = log_path.open("a" if (_resume_active or _resume_from_fetch) else "w", encoding="utf-8")
9074: 
9075:         def _log(msg: str) -> None:
9076:             print(msg)
9077:             log_f.write(msg + "\n")
9078:             log_f.flush()
9079: 
9080:         summary: dict = {
# provenance_reanchor marker emit incl local_window field + exception-fallback build_ok=False:
14874:             try:
14875:                 _reanchor_snap = get_reanchor_telemetry()
14876:                 # I-deepfix-001 Wave-3a (#1344, Fable P0 option-B): surface the local-window fallback
14877:                 # recovery COUNTER as local_window=<N>. On gate-B it is structurally 0 (fallback pinned OFF);
14878:                 # the activation canary FAILS if a regression re-opens the leg (N != 0).
14879:                 _log(
14880:                     "[activation] provenance_reanchor: accepted=%d reanchored_argmax=%d "
14881:                     "local_window=%d build_ok=%s"
14882:                     % (
14883:                         int(_reanchor_snap.get("reanchor_recovered", 0)),
14884:                         int(_reanchor_snap.get("reanchor_argmax_recovered", 0)),
14885:                         int(_reanchor_snap.get("reanchor_local_window_recovered", 0)),
14886:                         True,
14887:                     )
14888:                 )
14889:             except Exception:  # noqa: BLE001 — a telemetry read must never break the paid run
14890:                 _log(
14891:                     "[activation] provenance_reanchor: accepted=0 reanchored_argmax=0 "
14892:                     "local_window=0 build_ok=False"
14893:                 )
14894: 
14895:         # A12 (iarch006 epic-failure): post-GENERATION checkpoint — DATA ONLY (raw drafts + identity
```

## CLAIM 4 — provenance_generator.py change is TELEMETRY-ONLY (dict key + counter increment); verify/recover/soft-warning byte-unchanged; allow_local_window_fallback pinned off on gate-B
```python
# the telemetry dict + reset/get (auto-flow the new key):
1366: _REANCHOR_TELEMETRY: dict[str, int] = {
1367:     "reanchor_attempts": 0,
1368:     "reanchor_recovered": 0,
1369:     "reanchor_uncited_bound": 0,
1370:     # I-perm-004 (#1198) slice 2: recoveries via the boilerplate-aware argmax (subset of recovered).
1371:     "reanchor_argmax_recovered": 0,
1372:     # I-deepfix-001 Wave-3a (#1344, Fable P0 option-B): recoveries via the OLD local-window fallback leg
1373:     # (the reanchored_local_window soft-warning site). On gate-B allow_local_window_fallback is pinned OFF
1374:     # (:1580/:1607) so this leg is structurally unreachable => the counter is 0; the activation canary
1375:     # surfaces it as the provenance marker's ``local_window=<N>`` field and FAILS if a regression re-opens
1376:     # the leg (N != 0). Telemetry-only — NOT verify logic; auto-reset by reset_reanchor_telemetry().
1377:     "reanchor_local_window_recovered": 0,
1378: }
1379: 
1380: 
1381: def get_reanchor_telemetry() -> dict[str, int]:
1382:     """Snapshot of the re-anchor counters (attempts / recovered / uncited-bound)."""
1383:     return dict(_REANCHOR_TELEMETRY)
1384: 
1385: 
1386: def reset_reanchor_telemetry() -> None:
1387:     """Zero the re-anchor counters (call between runs / tests)."""
1388:     for k in _REANCHOR_TELEMETRY:
1389:         _REANCHOR_TELEMETRY[k] = 0
1390: 
# the recovery leg with the new counter increment (surrounding verify calls shown to prove they are unchanged):
2885: 
2886:     # I-perm-004 (#1198) slice 3: apply the gap-#18 RE-POINT. Only when the sentence is actually
2887:     # KEPT (is_verified) and SINGLE-token — rewrite the token to the rescue window so the report
2888:     # cites the span that genuinely entails (not the original mis-pointed narrow span). The window
2889:     # was numeric/content-matched AND judged ENTAILED, so the re-pointed token is faithful; the
2890:     # accept verdict is unchanged (relabel only, never a new pass). Flag-gated at capture time.
2891:     final_sentence = sentence
2892:     final_tokens = tokens
2893:     if reanchor_local_to is not None and is_verified and len(tokens) == 1:
2894:         _rev_id, _rev_start, _rev_end = reanchor_local_to
2895:         final_sentence = _rebind_single_token(sentence, _rev_id, _rev_start, _rev_end)
2896:         final_tokens = parse_provenance_tokens(final_sentence)
2897:         # I-deepfix-001 Wave-3a (#1344, Fable P0 option-B): count the OLD local-window fallback recovery so
2898:         # the activation canary can assert it stayed 0 on gate-B (where allow_local_window_fallback is pinned
2899:         # OFF => this block is unreachable). Telemetry-only; the recovery behavior + soft-warning below are
2900:         # BYTE-UNCHANGED — this is an observability counter, NOT a change to the verify/recover logic.
2901:         _REANCHOR_TELEMETRY["reanchor_local_window_recovered"] += 1
2902:         soft_warnings = list(soft_warnings) + [
2903:             f"reanchored_local_window:{_rev_id}:{_rev_start}-{_rev_end}",
2904:         ]
2905: 
# the argmax leg gate showing allow_local_window_fallback=False is pinned (unchanged):
1578:         # False) verifies. This closure is the binding judge handed to the resolver — so the resolver
1579:         # can only ever choose among spans that already pass this exact gate.
1580:         def _candidate_passes(_sentence: str, span: tuple[int, int], _span_text: str) -> bool:
1581:             cand = _rebind_single_token(sentence, evidence_id, span[0], span[1])
1582:             return verify_sentence_provenance(
1583:                 cand, evidence_pool,
1584:                 require_number_match=require_number_match,
1585:                 quantified_models=quantified_models,
1586:                 allow_local_window_fallback=False,
1587:             ).is_verified
1588: 
1589:         if _span_resolver_enabled():
1590:             # BOILERPLATE-AWARE ARGMAX: choose the best ENTAILING prose span instead of the first
1591:             # passing candidate in enumeration order (drb_76 rebound to the TITLE). Bounded judge
1592:             # calls (top_k). A title-only-supported claim is still recovered but LABELED with its
1593:             # provenance_quality so the report ships it caveated, never silently high-confidence.
1594:             from src.polaris_graph.generator.span_resolver import (  # noqa: PLC0415
1595:                 resolve_best_entailing_span,
1596:             )
1597:             best = resolve_best_entailing_span(
1598:                 direct_quote,
1599:                 sentence,
1600:                 _reanchor_candidate_spans(direct_quote),
1601:                 judge_fn=_candidate_passes,
1602:                 top_k=_span_resolve_topk(),
1603:             )
1604:             if best is None:
1605:                 return None
1606:             rebound = _rebind_single_token(
1607:                 sentence, evidence_id, best.best_span[0], best.best_span[1],
1608:             )
1609:             v = verify_sentence_provenance(
1610:                 rebound, evidence_pool,
1611:                 require_number_match=require_number_match,
1612:                 quantified_models=quantified_models,
```

## CLAIM 5 — two_sided_debate: accumulate under the existing guard, reset once, ONE unconditional flag-ON summary marker; never fabricates a con
```python
5370:         # marker-less disclosure to the held-aside list, which renders AFTER strict_verify via
5371:         # render_degraded_disclosures (never verified prose, never counted as support). It NEVER
5372:         # fabricates a con and NEVER asserts an ungrounded balancing claim (fabricating balance is the
5373:         # lethal direction). Default OFF (PG_TWO_SIDED_DEBATE) => the guard is False => byte-identical.
5374:         if _two_sided_debate_enabled() and _is_debate_section(section):
5375:             _pre_debate_disc = len(_vc_degraded_disclosures or [])
5376:             _vc_degraded_disclosures = _maybe_two_sided_debate_disclosure(
5377:                 section, _vc_baskets, _vc_real_units, _vc_degraded_disclosures,
5378:             )
5379:             # I-deepfix-001 Wave-3a (#1344, Fable P1): ACCUMULATE this debate section's counts into the
5380:             # per-run totals instead of emitting a per-section marker. The ONE per-run summary marker is
5381:             # emitted by _emit_two_sided_debate_run_summary() after all sections compose, so "flag ON" always
5382:             # yields exactly one marker even when NO section is debate-framed. Reached ONLY under
5383:             # PG_TWO_SIDED_DEBATE + a plan-framed debate section => OFF byte-identical.
5384:             _accumulate_two_sided_debate(
5385:                 len(_vc_real_units or []),
5386:                 len(_vc_degraded_disclosures or []) - _pre_debate_disc,
5387:             )
5388:         raw = "\n".join(c for c in _vc_real_units if c and c.strip())
5389:         # I-deepfix-001 WS-3 (#1344): NO-PROVENANCE-TOKEN LEAK REPAIR. Before `raw` flows into the
5390:         # UNCHANGED _rewrite_draft_with_spans + strict_verify tail (where an untokened sentence is
# ... reset before sections:
9508: 
9509:     # I-deepfix-001 Wave-3a (#1344, Fable P1): zero the per-run two-sided-debate totals BEFORE any section
9510:     # runs, so the once-per-run summary marker (emitted after assembly, below) reflects THIS run only.
9511:     # Flag-gated => OFF byte-identical.
9512:     if _two_sided_debate_enabled():
9513:         _reset_two_sided_debate_telemetry()
9514: 
9515:     # I-arch-004 A1 (#1248): per-section crash isolation. Was a bare gather that re-raised when one
9516:     # V30 section hit the wall-clock x2 (the drb_72 death — a 3h20m run discarded). Now each failure
# ... unconditional flag-ON summary marker after sections:
9582:             section_results.append(legacy_results[legacy_idx])
9583:             legacy_idx += 1
9584: 
9585:     # I-deepfix-001 Wave-3a (#1344, Fable P1): emit the ONE per-run two-sided-debate summary marker now that
9586:     # every section has composed. Unconditional on the flag-ON path (leg2_inspected=0 if no section was
9587:     # debate-framed) so the activation canary always sees exactly one marker. OFF byte-identical.
9588:     _emit_two_sided_debate_run_summary()
9589: 
9590:     # GH#423 I-gen-002: cross-section fact-dedup pass. Runs AFTER all
9591:     # sections complete (preserves parallel generation per Codex Path A
9592:     # quality analysis) but BEFORE M-44 regen + final assembly. Identifies
```

## Given the inlined evidence above, verify from text alone:
1. transport_fix_correct: root-logger handler + in-process asyncio.run + basicConfig-before-attach ⇒ module markers ARE captured. Any way a marker is still unreachable?
2. provenance_telemetry_only: only a dict key + a counter increment; strict_verify/verify_sentence_provenance/allow_local_window_fallback/recovery/soft-warning byte-unchanged. Confirm.
3. off_byte_identical: flag OFF ⇒ no handler, no canary, no record key (guarded), None-safe ok, counter unreachable (allow_local_window_fallback=False), debate summary+field gated. Confirm.
4. debate_false_fail_fixed: unconditional flag-ON summary (leg2_inspected=0 when no debate section). Confirm.
5. faithfulness_untouched. Confirm.

OUTPUT SCHEMA (return exactly):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
transport_fix_correct: true|false
provenance_telemetry_only: true|false
off_byte_identical: true|false
debate_false_fail_fixed: true|false
faithfulness_untouched: true|false
convergence_call: continue | accept_remaining
notes: <short>
```
You now have the surrounding code inlined — do NOT abstain on shell-access grounds; verify from the inlined text. APPROVE iff all five true and zero P0/P1.
