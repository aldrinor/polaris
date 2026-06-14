You are CODEX performing an INDEPENDENT line-by-line cross-audit (POLARIS CLAUDE.md §-1.1, clinical-safety-critical) of a Claude forensic of a DEAD POLARIS paid run.

Do your OWN verification from the raw artifacts. A separate agent already formed opinions; you are NOT given them on purpose. Re-derive every verdict from the data yourself. Output only your independent findings.

## Artifact location (absolute)
C:\POLARIS\.codex\I-arch-004\deadrun_artifacts\drb_72_ai_labor

This is a real paid run (drb_72_ai_labor) that died at section composition after ~3h20m.

## CRITICAL: two-pass provenance (state matters for timestamps)
The artifact directory mixes TWO passes:
- DEATH-RUN evidence (2026-06-13/14): manifest.json, run_status.json, run_log.txt, cost_ledger.jsonl, llm_io/*, reasoning_trace.jsonl, tool_trace.jsonl, retrieval_trace.jsonl, live_corpus_dump.json, corpus_*.json, tool_summary.json, refetch_diagnostics.json.
- EARLIER FAITHFULNESS/D8 evidence (2026-06-10): four_role_claim_audit.json, four_role_role_calls.jsonl, verification_details.json, report.md, evidence_pool.json, nli_verification.json.
The run died at composition BEFORE the 4-role D8 verification re-ran, so any faithfulness finding (findings 10-13) rests on the 2026-06-10 artifacts. Note this in your provenance reasoning; do not misattribute 2026-06-10 verdicts to the dead run's composition.

## PERFORMANCE: do NOT read multi-MB files whole
- tool_trace.jsonl ~4.8MB, contradictions.json ~3.5MB, evidence_pool.json ~1.1MB, four_role_role_calls.jsonl ~1.7MB, reasoning_trace.jsonl ~180KB, cost_ledger.jsonl ~464KB.
- Use grep / python json streaming / slicing. The llm_io/ directory has 1622 small JSON files; open only the specific call_ids cited.
- llm_io record schema: top-level keys = call_id, call_type, role, status, timestamp_utc, duration_ms, request, raw_response. The model content lives at raw_response.choices[0].message.content and raw_response.choices[0].message.reasoning_content; usage at raw_response.usage; requested params at request.{model,max_tokens,reasoning,provider}. On Windows use UTF-8 (io.open(..., encoding='utf-8')) - some files contain non-cp1252 bytes.
- four_role_role_calls.jsonl rows: {claim_id, role (mirror|sentinel|judge), raw_text, reasoning, model_slug, served_model}. Sentinel raw_text is JSON with an "atoms" list and a "verdict" field; note some rows use compact JSON (no space after colon) so a naive '"verdict": "unsupported"' substring will undercount - parse the JSON.

## Your job (§-1.1, claim-by-claim against the REAL data)
1. Spot-verify EACH of the 18 Claude findings below against the actual artifact files (open the cited call_id / file / value). Mark CONFIRMED / REFUTED / PARTIAL with the EXACT value you checked (cite the number/string you read).
2. Independently HUNT for any data-visible chokepoint or faithfulness leak Claude may have MISSED - especially in faithfulness / provider-lock / truncation / silent-ok masking.

## The 18 Claude findings to verify (verbatim, no conclusions attached)

F1 (P0, death): Per-section 600s wall (PG_SECTION_WALLCLOCK_SECONDS=600) is incompatible with sections holding 2+ sequential narrative calls. A single narrative dc9b004f ran 329.3s and 32748b88 ran 231.1s; two sequential = 560s, + slot extraction a4743a4d 374s pushes past 600s. Section attempt-2 LLM work = 231+329+12+71 = 643s > 600s.

F2 (P0, llm_provider_error): Empty-completion reasoning runaway burned 473.5s for zero content. Call 268e2f24: duration_ms=473519.18, content='' (len 0), reasoning_content len 19797 chars, finish_reason None, usage={'finish_reason': None} (no token counts). reasoning_content stuck self-counting (63x '[acemoglu_restrepo_robots_jobs]', 7x 'Sentence ', tail enumerating word counts). Identical-prompt retry dc9b004f returned finish_reason stop with full usage in 329s. max_tokens=32768, reasoning.max_tokens=6553. The empty text is silently skipped at contract_section_runner.py:710.

F3 (P1, death): GENERATOR_TIMEOUT_SECONDS=1800 vs section 600s are inconsistent; a single call's budget is 3x the section budget that must hold several calls. deepseek-v4-pro gets the 1800s timeout; section wall reads PG_SECTION_WALLCLOCK_SECONDS=600. Dying section made 2x600s attempts while each call (max 473.5s) stayed under its own 1800s ceiling.

F4 (P1, death, already fixed post-death): Bare asyncio.gather with no return_exceptions turned one section TimeoutError into whole-run error_unexpected. run_log traceback multi_section_generator.py:5509 bare gather; manifest.status='error_unexpected'. Current repo patched to _gather_sections_isolated (I-arch-004 A1 #1248).

F5 (P2, cost): Final dying call uncaptured, ~$0.30 spend unaccounted. cost_ledger last record cumulative=6.4389 at 05:16:13; run_status.running_cost_usd=6.741256. Last captured llm_io a0dc4db9 ends 05:16:13; death 05:18:19 - a call in-flight ~05:15:59..05:18:19 cancelled at the wall, no llm_io/cost capture.

F6 (P0, token_starvation): reasoning.max_tokens cap is silently ignored by providers, letting one generator call run 473s pure reasoning zero content (proximate death cause). 268e2f24 == reasoning_trace call c8fbf3bc, status truncated. Request reasoning={'exclude':False,'max_tokens':6553} not honored; 3fc52 requested reasoning.max_tokens=1000 billed reasoning_tokens=5599 (5.6x over); dc9b0 requested 6553 billed 7997. run_log: asyncio CancelledError -> TimeoutError 600s wall x2.

F7 (P1, token_starvation): DeepSeek-V4-Pro spends 80-98% of each generator call on reasoning, making per-call wall-time 12-473s for 3-sentence outputs. 9809f content=263/reasoning=11510 chars (43.8x) dur 224964ms reason_tok 2890 vs comp_tok 2526; 32748 1851/20761 dur 231149ms reason_tok 5200; dc9b0 3528/31809 dur 329275ms reason_tok 7997. 12 contract_slot calls span 964.8s (05:00:08 -> 05:16:13). raw_response.provider is None on every generate call.

F8 (P2, llm_provider_error): One death-run credibility_judge returned a blank verdict (GMICloud empty-200) yet logged status=ok. 9793eee1: call_type credibility_judge, status ok, provider GMICloud, duration 5104ms, content None, reasoning '', usage null, request max_tokens 8000 reasoning effort high. 1 of 1599 death-run side-judge calls (entailment/credibility/nli_conflict).

F9 (P1, death): Section composition wall-clock (600s x2) is the cancellation cause. manifest.error exact string; run_status.stage error, elapsed_s 12002.1; run_log traceback raises TimeoutError at multi_section_generator.py:93. No new report.md written (report.md is stale Jun-10, 18553 bytes).

F10 (P1, faithfulness_leak): 4-role D8 Judge overrode Sentinel 'unsupported' on 100% (12/12) of flagged claims; sentinel compressed to a bare 'ungrounded' token the judge dismisses as a 'distractor'. Claim_ids: 00-021-3a3f32a1, 00-023-865dc382, 00-028-ccd32de2, 02-003-84d92a96, 02-004-f6b4ee25, 03-003-e3109d66, 03-004-1027928f, 03-007-07d83405, 04-001-9d689e9e, 04-002-405a9f39, 04-003-a6f2ef60, 08-002-0ff16220. In four_role_role_calls.jsonl each of these has sentinel raw_text with document-level "verdict":"unsupported" yet judge raw_text = VERIFIED. Judge reasoning for 03-004/03-007/02-003 calls the sentinel signal a distractor/red herring/metadata. All 12 appear in verification_details.json kept lists, none in dropped.

F11 (P1, faithfulness_leak): Claim 02-003 VERIFIED on a methodology misattribution: claim says researchers 'implemented' a staggered design; cited span says they 'study' it. four_role_claim_audit.json 02-003-84d92a96 sentence cites [#ev:brynjolfsson_genai_at_work:0-800]. evidence_pool brynjolfsson_genai_at_work direct_quote[0:800] = 'Abstract We study the staggered introduction of a generative AI-based conversational assistant using data from 5,172 customer-support agents.' Sentinel flagged atom 'implemented...' status unsupported (why: span says study not implemented). Judge concluded VERIFIED.

F12 (P2, faithfulness_leak): Multi-citation claim 07-000 VERIFIED with one of two cited spans not supporting the figure (40% WEF working-hours). 07-000-d5cbff58 cites [#ev:ev_009:4900-5700][#ev:ev_547:1400-2200]. ev_547:1400-2200 contains 'up to 40% of total global working hours (World Economic Forum)'. ev_009:4900-5700 has NO WEF/40%/working-hours (skill-set / section 5.1.3 text). Claim passed carrying a non-supporting citation.

F13 (P3, retrieval_quality): frey_osborne 'direct_quote' is the ORA metadata/abstract page, not the paper body. evidence_pool frey_osborne_computerisation direct_quote is the Oxford ORA repository PAGE (BibTeX/EndNote/APA boilerplate, 'URL Source: https://ora.ox.ac.uk/...'). Span frey:1000-1800 (claims 01-002, 03-003, 04-001) lands on the abstract sentence ('702 detailed occupations, Gaussian process classifier'). Methods/results body is not in the pool.

F14 (P0, retrieval_quality): 185 demanded journal sources fetched ONLY paywall stubs incl. the two flagship Acemoglu-Restrepo papers. tool_trace.jsonl: 185 reputable journal/DOI URLs had no 'ok' fetch across all backends, only stub/no_content. Hosts: academic.oup.com=34, journals.uchicago.edu=34, sciencedirect.com=25, doi.org=22, mdpi.com=16, wiley=10, aeaweb=10, nber=6, science.org=5. journals.uchicago.edu 'Robots and Jobs' = tier T7 stub. tool_summary s2 success_rate=0.158.

F15 (P0, retrieval_quality): Backend status='ok' masks paywall stubs: zyte (1651x) and crawl4ai (1297x) returned ok on journals that were 304-374 char stubs; refetch_diagnostics.json empty []. live_corpus_dump classifies e.g. sciencedirect S2199853125001428 as T7 'Fetched body is 374 chars (< 1000 threshold)'.

F16 (P1, retrieval_quality): R9_openalex_unverified_host_demoted_to_t4 demotes confirmed peer-reviewed journals to T4 solely because the URL is doi.org. live_corpus_dump doi.org/10.1257/jep.33.2.3 (Journal of Economic Perspectives) -> tier T4 reason 'OpenAlex said peer-reviewed article in journal, but domain doi.org'. 50 doi.org sources carry this rule. corpus_credibility_disclosure every per_source weight_basis='tier_prior' (803/803), so credibility_weight is 100% a function of tier.

F17 (note: Claude numbered this P1/retrieval - some lists merge F15/F17): content_starved hard-DROPS 44 reputable journals (Research Policy, Technological Forecasting, World Development) - a FILTER that violates WEIGHT-AND-CONSOLIDATE; 'select dropped=0' is misleading. retrieval_trace.jsonl: 49 content_starved drops (44 reputable-venue), 539 rerank_not_selected drops (457 journal/DOI). run_log '[select] selected=649 of 649 dropped=0' true only because real drops happened upstream at rerank + content_starved.

F18 (P1, faithfulness/architecture): same as F17 framing - per CLAUDE.md §-1.3 CONSOLIDATE-DONT-DROP, content_starved and rerank_not_selected should down-weight not hard-drop demanded journal sources, especially when the drop is caused by an upstream FETCH failure (content_starved).

(Note: the source list double-numbered the retrieval findings; treat F14-F18 as the retrieval-quality cluster and verify each distinct claim.)

## Output: write EXACTLY this YAML shape as your stdout, nothing else before it
verdict: APPROVE | REQUEST_CHANGES
confirmed: [ list each finding id you verified true, with the exact value you checked ]
refuted: [ findings you found false, with the contradicting value ]
partial: [ findings partly right, state which part holds and which doesn't, with values ]
novel_data_findings: [ {location, what, why, severity} ... for anything Claude missed ]
faithfulness_verdict: <one line: did any fabrication/weak-grounding survive verification in this run's data? cite claim_id or say none-found>

APPROVE iff Claude's forensic has no material error that would mislead the fix (a slightly-off count with intact substance is PARTIAL not REFUTE, and does not block APPROVE). REQUEST_CHANGES only if a finding is substantively wrong or a real data-visible defect was missed that changes the fix priority.
