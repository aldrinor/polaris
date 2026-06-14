# Codex INDEPENDENT chokepoint investigation — g4_prompts_citations

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this is (operator §-1.1: BOTH Claude and Codex run independent line-by-line audits in parallel; cross-review combines findings)
You are the INDEPENDENT second auditor. POLARIS deep-research pipeline, repo root is the current dir (C:\POLARIS).
Live run path = scripts/run_honest_sweep_r3.py + scripts/dr_benchmark/run_gate_b.py and everything they import
(generator/multi_section_generator, generator/provenance_generator, roles/*, authority/*, retrieval/*, agents/*,
llm/openrouter_client). UI (web/**), frozen legacy (src/orchestration/**), tests = OUT OF SCOPE.

CONTEXT: a 3-hour validation run just DIED at status=error_unexpected — a report section exceeded a 600s
wall-clock TWICE and the section gathers lack return_exceptions=True so one slow section cancels all siblings
and crashes the whole run. The 600s came from a smoke env file (PG_SECTION_WALLCLOCK_SECONDS=600,
PG_LLM_TIMEOUT_SECONDS=300); code default is 0=unlimited / GENERATOR_TIMEOUT=1800. Operator directives:
timeouts UNLIMITED-with-watchdog OR 1.5x the realistic generate time (sized off the 64000-token section
budget, not the stale 16384); EVERY param must be a PG_ .env var (hardcoding is "super lethal"); the pipeline
MUST have CHECKPOINTS (carry DATA not VERDICTS — always re-run faithfulness gates on resume). Locked models:
generator=deepseek/deepseek-v4-pro, mirror=z-ai/glm-5.1, sentinel=minimax/minimax-m2, judge=qwen/qwen3.6-35b-a3b;
no gemma/closed-source on the live path.

## YOUR JOB — independently re-investigate YOUR dimensions (prompts, citation_traceability) line-by-line in the LIVE code, then for
## EACH Claude finding below: CONFIRM / REFUTE / PARTIAL by reading the actual file:line yourself (do NOT
## just agree). Then find any chokepoint in your dimensions Claude MISSED. Read the API/code, don't guess.

## Output schema (YAML, required — loose prose rejected):
```yaml
verdict: APPROVE | REQUEST_CHANGES   # APPROVE iff Claude's findings for your dims are sound AND complete (no missed P0/P1)
confirmed: [ ...finding locations you verified correct... ]
refuted: [ {location: , why_claude_is_wrong: } ]
partial: [ {location: , correction: } ]
novel_chokepoints: [ {location: , what: , why_it_chokes: , fix: , severity: P0|P1|P2|P3} ]
notes: ""
```

## CLAUDE'S FINDINGS FOR YOUR DIMENSIONS (verify each against the real code):


### dimension: prompts
Claude SUMMARY: 3 P1 prompt bugs, live DR path.

- [P1] multi_section_generator.py:2378-2383
  WHAT: Legacy section prompt never passes the research question (only title+focus+evidence).
  CURRENT: 'Research question context: (see overall corpus)' placeholder.
  CLAUDE_FIX: Interpolate research_question via _run_section into _call_section.
  WHY: Scope/disambiguation rules need the question; without it the writer off-targets.

- [P1] multi_section_generator.py:5465-5472 vs slot_fill.py:644-671
  WHAT: JSON-only system msg reused for the V30 slot NARRATIVE prose call (contract_section_runner.py:705).
  CURRENT: system 'JSON-only, no prose' vs narrative 'plain prose, 14-20 sentences'.
  CLAUDE_FIX: Prose system msg (or None) for narrative; split into JSON caller + prose caller.
  WHY: System-vs-user contradiction on the live V30 path; empties the narrative completeness lever.

- [P1] multi_section_generator.py:1655-1729 vs :2206-2268
  WHAT: Length maximizers (10-18/20-35 sentences, 50-200 cites) vs atom contract 'OMIT, fewer beat many'.
  CURRENT: rule 8 '10-18'; M-42c '20-35'; atom 'OMIT the claim, fewer beat many'.
  CLAUDE_FIX: Toward WEIGHT-and-CONSOLIDATE; reframe omit to consolidate-and-attribute, don't lower length.
  WHY: Thin atoms make the halves order opposite things; model pads-then-drops or undershoots; amplified the strangled long generation.


### dimension: citation_traceability
Claude SUMMARY: I read the full citation/provenance traceability chain on the live DR path line-by-line: token grammar + parse + strict_verify (provenance_generator.py, 2718 lines), the [ev_XXX]->[#ev:] span rewriter (live_deepseek_generator.py), the entailment NLI judge (entailment_judge.py), consolidation (fact_dedup.py / finding_dedup.py), re-anchor + span_resolver, and the resolver/citation-health surfacing. The faithfulness gates themselves are strong and fail-closed by design. The traceability RISKS that survive are: (P1) a sentence that PASSES strict_verify can still be SILENTLY DROPPED from the rendered report by a hardcoded 3-content-word / 15-char heuristic inside resolve_provenance_to_citations — it is counted as "verified" but never appears and is NOT logged in dropped[], so the verified-count and the rendered report disagree and a real cited claim can vanish untraceably; (P1) the NLI entailment judge's terminal sentinel is ("ENTAILED","judge_error:") and is only treated as fail-closed when PG_STRICT_VERIFY_ENTAILMENT=enforce — under the also-valid "off"/"warn" modes (and "off" is the literal module default), a citation's entailment link is never enforced, so a mis-pointed [#ev] span ships VERIFIED with no traceable check that the span supports the claim; (P1) the same default-OFF gating applies to PG_PROVENANCE_REANCHOR / PG_SPAN_RESOLVER / PG_VERIFICATION_MODE — the span-repointing that makes a citation point at the genuinely-entailing span is OFF by default, so by default a ke

- [P1] src/polaris_graph/generator/provenance_generator.py:2692-2695
  WHAT: resolve_provenance_to_citations silently drops a sentence that PASSED strict_verify (is_verified=True, has valid [#ev] tokens) when its cleaned prose has <3 content words OR <15 chars. The drop happens AFTER strict_verify counted it as verified, and it is NOT recorded in dropped_sentences — so a genuinely cited, verified claim can vanish from the rendered report with zero trace, and sentences_verified over-counts what actually ships.
  CURRENT: if len(_content_w) < 3 or len(_for_count) < 15: continue  (hardcoded 3 and 15; BUG-M-8 degenerate-fragment guard)
  CLAUDE_FIX: Make the two bounds env vars (PG_RESOLVER_MIN_CONTENT_WORDS / PG_RESOLVER_MIN_PROSE_CHARS), and when a verified sentence is dropped here, append it to a tracked 'dropped_post_verify_degenerate' list and decrement sentences_verified so the counts and the rendered report agree. Better: only drop a fra
  WHY: A short-but-real verified clinical sentence (e.g. 'Contraindicated in pregnancy [#ev:..]', ~2 content words after stopword/number stripping) is deleted from the report while still counted in sentences_verified. The claim is now in NO traceable place: not rendered, not in dropped[], not in the bibliography unless another sentence cites the same ev. The verified-count vs rendered-report mismatch als

- [P1] src/polaris_graph/llm/entailment_judge.py:398-403 + src/polaris_graph/generator/provenance_generator.py:1966-1967,2156-2168
  WHAT: The NLI entailment judge (check (f), the gate that verifies the cited SPAN actually entails the SENTENCE) only DROPS on its judge_error sentinel / NEUTRAL / CONTRADICTED when PG_STRICT_VERIFY_ENTAILMENT=enforce. Under 'warn' it logs only and under 'off' the judge never runs at all. The clinical_generator default mode and PG_STRICT_VERIFY_ENTAILMENT history is 'enforce' per I-bug-095, but the mode is a free env string with off/warn fully wired — and the production behavior of the whole span->claim support link hinges entirely on that one env value being 'enforce'.
  CURRENT: mode = _entailment_mode() (PG_STRICT_VERIFY_ENTAILMENT, values off|warn|enforce); only mode=='enforce' appends entailment_failed / fail-closed. Terminal judge sentinel is ('ENTAILED','judge_error: ...').
  CLAUDE_FIX: Treat 'enforce' as the production default and FAIL LOUD at preflight if PG_STRICT_VERIFY_ENTAILMENT is unset/off/warn on a paid live run (assert in preflight, surface in manifest). Keep the env var (LAW VI) but make the live-path require enforce, and record the active mode in the manifest so an audi
  WHY: If the run env does not pin PG_STRICT_VERIFY_ENTAILMENT=enforce (a single missing/typo'd env var), every citation passes on mechanical numeric+content-word overlap alone, with NO check that the cited span semantically supports the claim. A [#ev] token pointing at the right row but the WRONG span (numbers coincidentally present) then ships VERIFIED and traceable-looking but the link is hollow — exa

- [P1] src/polaris_graph/generator/provenance_generator.py:1048-1066 + 1264-1298 + 1119-1130 (PG_PROVENANCE_REANCHOR / PG_SPAN_RESOLVER / PG_VERIFICATION_MODE)
  WHAT: The machinery that REPOINTS a citation token to the span that genuinely entails the claim (re-anchor + boilerplate-aware span_resolver + Phase-0b local-window rescue with re-point) is DEFAULT-OFF on all three env gates. With them off, a sentence that strict_verify keeps on the back of a local-window rescue still ships with its [#ev] token bound to the ORIGINAL, possibly mis-pointed narrow span (the resolver only re-points when PG_SPAN_RESOLVER is truthy).
  CURRENT: _provenance_reanchor_enabled(): PG_PROVENANCE_REANCHOR default '' (off); _span_resolver_enabled(): PG_SPAN_RESOLVER default '' (off); _verification_mode(): PG_VERIFICATION_MODE default 'off'
  CLAUDE_FIX: Enable PG_SPAN_RESOLVER (and PG_PROVENANCE_REANCHOR under enforce) by default on the live DR path so a kept citation always points at the genuinely-entailing span, and assert the active values in preflight/manifest. Keep the kill-switch env (LAW VI) but flip the live default to ON.
  WHY: By default the displayed citation span can be a span that does NOT itself contain the support (the claim was rescued by a DIFFERENT in-row window, or re-anchor never ran). A reader clicking the citation lands on a span that does not show the claim — the traceability link is technically valid (in-bounds, in-pool) but not GROUNDING. The drb_76 case (re-anchored to the row TITLE) is the documented sy

- [P2] src/polaris_graph/generator/live_deepseek_generator.py:380-396 + multi_section_generator.py:2764 (rewritten,_converted,_unver = _rewrite_draft_with_spans(...))
  WHAT: When the model cites [ev_XXX] but the evidence id is not in the pool, OR the row's direct_quote is empty, the rewriter silently strips that marker from the sentence (replace(...,'',1)) and only bumps an 'unverifiable' counter — which the live multi_section path DISCARDS as `_unver`. There is no per-claim record of WHICH source citation was lost.
  CURRENT: if not ev: unverifiable += 1; continue  /  if span is None: new_sent = new_sent.replace(f'[{marker}]','',1); unverifiable += 1  — and caller does `rewritten, _converted, _unver = _rewrite_draft_with_spans(...)` (counts dropped on the floor)
  CLAUDE_FIX: Capture and surface the unverifiable/stripped-marker count and the specific (sentence, ev_id) pairs into the section telemetry / manifest (mirror reanchor_telemetry). Do not silently discard `_unver`. Distinguish 'ev_id not in pool' (a real provenance bug) from 'empty direct_quote' (a fetch/distill 
  WHY: On a multi-citation sentence (the WEIGHT-AND-CONSOLIDATE basket case the DNA wants), one of several corroborating [ev_XXX] markers can be dropped while the sentence survives on its remaining markers — so the claim loses a real supporting source with no trace. On a single-marker sentence it falls to no_provenance_token and drops, but again the lost source id is invisible. The discarded `_unver` cou

- [P2] src/polaris_graph/generator/fact_dedup.py:65-203 (apply_span_cite_cap, PG_SPAN_PER_SOURCE_CITE_CAP)
  WHAT: When PG_SPAN_PER_SOURCE_CITE_CAP > 0, a per-(evidence_id,start,end) citation cap DROPS the excess citing sentences whose every cited span is already saturated. This is a selection-stage thinner that removes already-VERIFIED cited claims to limit re-citation of one span.
  CURRENT: SPAN_CITE_CAP_ENV = 'PG_SPAN_PER_SOURCE_CITE_CAP'; default 0 (off). When >0, telemetry n_span_cite_dropped sentences are removed from the report.
  CLAUDE_FIX: Keep it OFF on the live path (it already defaults off) and prefer CONSOLIDATE (group the same-span re-cites into one multi-citation basket entry) over DROP. If concentration must be surfaced, surface it as a weight/telemetry signal, never by deleting verified cited sentences. Document that this knob
  WHY: This is exactly the number-forcing 'thinner' the §-1.3 DNA bans (PG_SPAN_PER_SOURCE_CITE_CAP is named in the banned-bolt-on list in CLAUDE.md). If an operator sets it to make a breadth/concentration number look better, it DROPS real verified, traceable citations rather than consolidating them into a basket. A dropped over-concentrated sentence's claim loses its rendered citation even though it was

- [P2] src/polaris_graph/generator/provenance_generator.py:590-593,656-657,1754 (_DOSE_PATTERN_RE strip before numeric match)
  WHAT: Before the numeric-in-span check, dose-shaped numbers ('2.4 mg','0.5 mcg', etc.) are stripped from BOTH the sentence and the span so they are never required to appear in the cited span. The strip is a broad regex over mg/ug/mcg/kg/g/ml/mL/L units.
  CURRENT: _DOSE_PATTERN_RE = r'-?\d+(?:\.\d+)?\s*(?:mg|µg|ug|mcg|kg|g|ml|mL|L)\b' ; applied via _strip_dose_patterns to sentence_for_numbers and span_text — hardcoded unit list, no env toggle
  CLAUDE_FIX: Do not blanket-exempt dose numbers from span presence; instead require the dose value to appear in SOME cited span (treat it like _INTEGER_PERCENT_RE percent-claims, which ARE required). At minimum gate the strip behind an env var (PG_VERIFY_EXEMPT_DOSE_NUMBERS, default OFF for clinical) and surface
  WHY: A dose IS frequently the clinically load-bearing claim (e.g. 'tirzepatide 15 mg achieved...'). By exempting every dose-shaped number from the span-presence requirement, a sentence can assert a dose that does NOT appear in its cited span and still verify — the citation no longer traces the dose value. This is a faithfulness/traceability hole, not just cosmetic: wrong-dose is in the §-1.1 lethal set

- [P2] src/polaris_graph/synthesis/finding_dedup.py:18-41,246-256 (DOCUMENTED RESIDUAL 1/2)
  WHAT: finding_dedup clusters/collapses rows by an extracted numeric finding key that does NOT include population or comparator (RESIDUAL 1), and returns ZERO findings for non-clinical numerics so those rows are kept as un-clustered singletons earning no corroboration (RESIDUAL 2). Under the legacy (redesign OFF) path, a non-representative finding-bearing row is DROPPED.
  CURRENT: _finding_key omits population/comparator; legacy path: `if not redesign_on and not (ri in rep_indices or not row_has_finding[ri]): continue` (drops non-rep rows). PG_SWEEP_CREDIBILITY_REDESIGN gates the keep-all behavior.
  CLAUDE_FIX: Run the live path with PG_SWEEP_CREDIBILITY_REDESIGN ON so finding_dedup CONSOLIDATES (keeps all same-claim rows as a basket) instead of dropping non-representatives, and add population/comparator to _finding_key (or block merges when either is unextracted) so a citation never silently spans two dif
  WHY: RESIDUAL 1: two rows sharing a number but differing in an UNEXTRACTED qualifier (T2D vs obesity population) can merge, so the surviving representative's citation no longer distinguishes which population the source actually studied — a traceability over-collapse with clinical-safety relevance. Legacy DROP path means the dropped row's source URL disappears from the basket entirely (the DNA wants CON

- [P2] src/polaris_graph/generator/provenance_generator.py:2498-2514 (strict_verify Limitations pass-through) + 2260-2292
  WHAT: When telemetry_block is None (the default when strict_verify is called from multi_section_generator at line 2768 — no telemetry_block arg is passed), every Limitations-paragraph sentence is passed through as is_verified=True with NO provenance or numeric check (soft_warning='limitations_paragraph_pass_through').
  CURRENT: telemetry_block defaults None; multi_section call is `strict_verify(rewritten, evidence_pool)` (no telemetry_block) -> Limitations sentences bypass verification entirely
  CLAUDE_FIX: Always pass the real telemetry_block from the live path so Limitations numbers are verified against telemetry (the verify_limitations_sentence_against_telemetry path already exists), or require Limitations sentences to carry no claimed source-numbers. Make the pass-through explicit and visible in th
  WHY: Any sentence the splitter places after a 'Limitations:' heading ships verified-and-rendered with no citation requirement and no number check. A fabricated numeric claim about the corpus (or a mis-placed findings sentence that lands after the heading) becomes an untraceable, uncited 'verified' statement. The I-pipe-016 skip-empty guard only removes empty fragments; a content-bearing Limitations sen
