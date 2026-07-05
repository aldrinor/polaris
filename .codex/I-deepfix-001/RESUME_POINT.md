# I-deepfix-001 RESUME POINT (re-read FIRST every wake)

## MODE: AUTONOMOUS BEAT-BOTH (operator away 2026-07-05 ~22:44)
Goal: rendered report that GENUINELY beats DeepTRACE + DRB-II, or surface a genuine blocker. NEVER fake victory on deficient. NO permission-asking (authorized). Full plan: `.codex/I-deepfix-001/AUTONOMOUS_BEATBOTH_PLAN.md`.

## CURRENT PHASE: P2 BUILD+DUAL-GATE (in progress)
- P1 INVESTIGATE ✅ DONE — wf wbpc2n0qb. 6 root-cause briefs at `.codex/I-deepfix-001/fixwave/inv_*.md` + `fix_wave_plan.json` (7 faithfulness-form fixes + coverage track + judge fix).
- P2 BUILD+GATE Wave-1 (5 faithfulness-form fixes) ⏳ RUNNING — wf **wc0wcngqp** (run wf_c589b022-188). FF1-CHROME (weighted_enrichment.py), FF2-TRUNC-DET (key_findings.py), FF4-ASPECT (topic_relevance_gate.py), FF5-DATE-RESOLVE (new publication_date_resolver.py), JUDGE-CAP (openrouter_role_transport.py).
- P2 COVERAGE TRACK (4 arms, CO-EQUAL, building IN PARALLEL not deferred — operator flagged coverage is huge) ⏳ RUNNING — wf **w6mgdjqv8** (run wf_a131082a-5da). COV-C1-PAIR-RECALL (cross_source_synthesis.py — recall-first pairing, NLI still gate, unblocks 0-cross-source), COV-C2-CONSOLIDATE-RECALL (credibility_pass.py — agglomerative embed-merge confirmed by bidirectional NLI, keep >=2 floor), COV-A-LANDMARK-SNOWBALL (new landmark_study_expander.py + fs_researcher wiring — surface Noy&Zhang/Peng/Felten), COV-FETCH-OA-RECOVER (frame_fetcher.py — OA-preprint discovery recovers Brynjolfsson + S2/OpenAlex citation snowball). Root cause = 3 starved WIDEN/CONSOLIDATE chokepoints (retrieval never targets empirical core; DOI-only OA miss drops landmark primary; exact-anchor pairing too tight → 0 cross-source). Full detail: fixwave/inv_5_coverage-depth-an-absence-of-r.md. Coverage arms need a FRESH front-half run to validate (not resume).
- Each fix: worktree build + RED/GREEN + real Codex CLI + real Fable5 gate; returns approved diffs.
- P2b COVERAGE FIRING FORENSICS (operator flagged "why did built machinery fire ZERO?") ⏳ RUNNING — wf **wp1mfgjvt** (run wf_1c6acb81-bd1). Evidence agent + Codex + Fable5 independently deep-investigate why coverage/depth fired 0 (per-mechanism FIRED/DARK/STARVED). KEY tension to resolve: run log says "1 anchored cross-source pair but 0 survived licensing" — pairing DID fire once + LICENSING killed it, which is DIFFERENT from inv_5's "exact-anchor gives 0 pairs". **GATE: do NOT commit any coverage fix (from w6mgdjqv8) until wp1mfgjvt confirms it hits the TRUE cause (not a misdirected symptom fix). If forensic finds a deeper cause inv_5 missed (dark flag / wiring break / swallowed exception / over-strict licensing) → adjust the coverage fixes before commit.** Form fixes (wc0wcngqp) are NOT gated on this — commit those when approved.

## ★UNIVERSAL COMMIT GATE (operator asked for Codex+Fable deep-dive on ALL issues)★
NO fix commits (form OR coverage) until BOTH: (a) its build-gate APPROVED (codex+fable review the DIFF), AND (b) the FORENSIC confirms its defect fix_verdict=ON_TARGET (Codex+Fable confirm the ROOT CAUSE + that the fix hits it, not a symptom/misdirect). Two forensics: wp1mfgjvt (coverage) + **wjixpytfc run wf_1da2bb34-62c (all 6 non-coverage: chrome/truncation/off-topic/date/judge/4IR)**. If a forensic returns fix_verdict NEEDS_ADJUSTMENT/MISDIRECTED for a defect → do NOT commit that fix; build the CORRECTED fix per the forensic, dual-gate, then commit. PushNotification the operator the plain forensic answers.

## ON WAKE (build wf notification OR backstop):
1. If wf wc0wcngqp NOT done → wait/reschedule.
2. If DONE → Read its journal.jsonl (subagents/workflows/wf_c589b022-188/journal.jsonl); for each APPROVED fix hold until the forensic (wjixpytfc) clears its defect ON_TARGET, THEN apply its diff to the main tree (`git apply --check` then apply; ONLY the named files + test), run the test in the MAIN tree (TMPDIR=/c/POLARIS/_tmp), commit each, push. Any fix NOT approved by build-gate OR not ON_TARGET by forensic → read the reason, re-brief/correct that ONE fix (resumeFromRunId caches the good ones), do NOT commit.
3. P2 Wave-2: build+gate FF3-TRUNC-SEM (span_quality_gate.py, after FF2), FF6-DATE-POLICY (constraint_enforcement.py, default resolve_then_mask), FF7-DATE-DISCLOSE (multi_section_generator.py), + the 4IR validity-gate fix (7th defect: pipeline invented a "Fourth Industrial Revolution" aspect not in the question → abort_run_validity_gate; trace run_validity_gate + scope). New build+gate workflow on committed HEAD.
4. COVERAGE track (Arm A landmark_study_expander + citation snowball; cross_source_synthesis fix) — separate build+gate.
5. P3 RESMOKE: kill any Box B leftover (preserve corpus_snapshot); resume-from-corpus_snapshot for form fixes (fast ~15min, .venv/bin/python); FRESH front-half for coverage. Judge-cap committed so resmoke completes.
6. P4 §-1.1 audit resmoke report (fan-out) → any surviving defect → back to build. NEVER victory on deficient.
7. P5 clean → PAID beat-both run(s). P6 SCORE (DeepTRACE floor 0.8636 + DRB-II floor 0.0571) → beat-both? iterate. YES → PushNotification SCORED results.

## DECISIONS (proceeding on recommended defaults; operator can override):
- Date undated-row policy: resolve_then_mask (mask only rows still undated after FF5). Every masked row stays in pool+disclosure.
- Judge budget: cap kimi-k2.6 reasoning below the 16384 top-level (reuse reasoning_cap_for); do NOT raise max_tokens (re-opens 429/provider-filter). Keep the model (21 providers).

## GUARDRAILS
faithfulness NEVER relaxed; §-1.3 WEIGHT-not-FILTER + WIDEN-only; dual-gate real-Codex+real-Fable5 EVERY fix; NEVER victory on deficient / NEVER fake a score; NO permission-asking; NO rm -rf variable paths (git worktree remove --force + prune); /root/polaris/.venv/bin/python; heavy on VM not local; ≤4 in flight; crash→resume-closest-checkpoint never fresh; read EVERY log line line-by-line (Read not grep).

## HANDLES
repo /c/POLARIS branch bot/I-wire-001-integration; Box B ssh6.vast.ai:34874 -p 34874 root@ssh6.vast.ai key /c/Users/msn/.ssh/id_ed25519; corpus_snapshot @ /root/polaris/outputs/honest_sweep_r3/workforce/drb_72_ai_labor/corpus_snapshot.json (1.9MB preserved, box FREE); SC=/c/Users/msn/AppData/Local/Temp/claude/C--POLARIS/dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391/scratchpad; build wf wc0wcngqp (run wf_c589b022-188); investigation wf wbpc2n0qb (run wf_50f8753a-41f). Box A spare ssh3.vast.ai:12228.
