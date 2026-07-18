# Lessons: Debugging & forensic monitoring methodology

Canonical home: memory `feedback_monitor_means_line_by_line_forensic_2026_06_14.md`, `feedback_trace_path_replay_harness_debug_2026_06_17.md`, `project_iwire013_blind_predicate_independent_detector_2026_06_26.md`, `feedback_offline_tests_not_real_preflight_prove_small_real_run_2026_07_02.md`.

This hub covers how POLARIS is debugged and monitored: forensic content reads, trace-the-path, behavioral replay harnesses, independent detectors, and the built-is-not-wired root cause.

## For any "X is broken," grep for an existing module/flag FIRST — winners are usually built but default-OFF

The recurring "still heavily broken" loop is largely that winning machinery is already built and benchmarked in-tree but ships default-OFF, advisory-only, on a retired/free-routed role key, or with a dead call site. For any "X is broken," first grep for a module or flag that already does X. If it exists, the work is flip-ON + wire + prove-it-fires-in-real-output (a fail-loud canary), not a rebuild. Every flag-gated fix campaign MUST end with an explicit ACTIVATE + ARCHIVE phase: make the correct module the production default and move the wrong/superseded module to `archive/` with its import sites removed. After building anything, assert a behavioral canary (manifest `.fired=True`, a multi-source-basket replay assertion) on a REAL run — wiring that fires is the acceptance test, not the code existing.

Why: A capability that is built-but-default-OFF reads identically to "not built" from the output, so "we already fixed that" was false for months. Building a second scorer or extractor when one exists forks the design.

Evidence: `pipeline_redesign_master_plan.md` §2.2 MISS 1 + §8 (Codex caught a re-build of `weight_mass.py`, `claim_graph.py`, `credibility_pass.py`, `weighted_corpus_gate.py`, all already in-tree behind an unset `PG_SWEEP_CREDIBILITY_REDESIGN`); `beatboth_p1_codex_verdict.txt` CX-06 (basket consolidation behind default-off `PG_BASKET_CONSUME_FINDING_DEDUP` → 1 multi-source cluster vs 1347 single-origin), CX-19; I-arch-004 F07/F11/F01/F09; the topical-relevance fix `content_relevance_judge.py` was fully built but all three flags were OFF, leaving ~50% off-topic corpus; memory `project_winners_built_but_default_off_the_loop_root_2026_06_28.md`, `feedback_wire_activate_core_archive_wrong_modules_2026_07_05.md`.

Recurrence: Named as the systemic root of the "same issues, no way out" loop; ~41 folders with a matching finding line.

## Gate on a re-read of the real output — never on green tests, a gate approval, or a self-reported counter

Committed + green tests + Codex-approved does NOT equal the effect appearing in real output. For any defect where the OUTPUT is wrong or thin (breadth collapse, too-few citations, a feature that "didn't fire") — not a hard crash — trace the whole data-flow path end-to-end (basket → consolidation → generator → verify → render), find EVERY chokepoint (one reader per hop plus a completeness critic), and gate on a BEHAVIORAL replay harness whose acceptance is that the effect actually appears in the real output (fails loud otherwise). Gate on a re-read of the composed/redacted final text, not on a retrieval-presence count, a stale collapsed/dropped metric, or a hand-copied predicate.

Why: Diff-review and green tests check code and config, not output behavior on real data. This is the §-1.1 faithfulness ghost turned inward on the pipeline's own numbers — a match or count is never a quality verdict, and reviewers repeatedly found a green metric sitting on top of missing or dropped content.

Evidence: `feedback_trace_path_replay_harness_debug_2026_06_17.md` (operator-locked, "pin it to the wall"); `beatboth_p1_codex_verdict.txt` CX-20 (adequacy reports 8/8, 6/6 while the report misses required gold slots), CX-21, CX-08, CX-27 (selected=794 of 789); I-arch-004 F15 (log says dropped=0 while 44 reputable journals were hard-dropped); `B_gen/codex_diff_audit.txt` C07 (a gap-stub with sentences_verified=0 returns as "verified").

Recurrence: Recurring across many folders; the single most-recurring failure family, confirmed in both clinical and backend-generator lanes.

## Validate a detection/predicate fix with an INDEPENDENT test that drives the live production predicate

A fix is not fixed until a regression that CALLS the production predicate/path fails BEFORE the change and passes AFTER. Build the checker as a second, independent detector that imports zero production code and reproduces the original failure. Do not accept a test that mocks the judge, hand-copies the render predicate, or asserts a re-implemented copy — all pass while the real defect survives.

Why: A test built on the same helper as the code under test inherits the same blind spot, so green means nothing. This is why the low "no test" keyword count was misleading — the diff-gate does force a test, so the recurring failure is a test that exercises a stand-in instead of the live path.

Evidence: I-wire-013 #1327 (chrome/truncation fixes committed, gate-approved, and run, but did not clean the render; production and the v1 test false-passed on the same blind predicate; `scripts/iwire013_sec11_forensic_audit.py` with zero production imports reproduced the failure — a blind chrome predicate reported ~0 chrome while the forensic read found ~85); `B_gen/codex_diff_audit.txt` P1-1 (regression replaces the entailment judge with a fake NEUTRAL, so the real "judge returns ENTAILED for scope-widening" defect is reported-not-fixed), P1-2; `I-cd-013b/codex_diff_audit.txt`.

Recurrence: One documented instance invalidated a whole fix cycle; the pattern recurs in the backend-generator and UI lanes.

## Offline tests are NOT a preflight — prove each fix's effect in a small REAL run

Offline unit tests plus a green product-test gate prove a fix's LOGIC, not its live wiring. The real preflight is: (1) prove the fix in isolation with a short real test; (2) run ONE small-scale REAL pipeline run and forensically READ the output to confirm each fix's EFFECT appears (build a per-fix PROVEN/NOT table); (3) any effect that doesn't appear is a real gap — fix and re-smoke; (4) only then the large paid run.

Why: A fix can pass every offline check and still fail, hang, or no-op live. Mineru passed offline (installed, imports, parse-OK) then HUNG live retrieval on the first real PDF — and the corpora are ~72% PDFs, so it was a hard blocker the offline tests never saw.

Evidence: `feedback_offline_tests_not_real_preflight_prove_small_real_run_2026_07_02.md` (operator flagged hard, twice).

Recurrence: Operator flagged hard twice.

## "Monitor" / "read every line" means a forensic content read of quality across all stages, not a status check

When the operator says "monitor" or "read every line every 5 min," that means a forensic §-1.1-style QUALITY read of the actual content the run produces, line by line, across ALL stages (the breadth funnel of fetched vs tiered vs kept vs cited, tier quality, extraction cleanliness, baskets forming, verify drop rate, the intermediate section drafts read claim-by-claim). Surface liveness checks (proc-alive, etime, tail -1, stage name, /health) are NOT monitoring — they are a FAIL. Even a "first let me see what's alive" pre-step is itself the violation; go straight to the forensic read.

Why: Liveness tells you alive-vs-dead, nothing about whether the run is doing the RIGHT thing. Turning the directive into a status check let a whole day tunnel-vision on one fix while other quality problems blocked SOTA. The live logs, reasoning, and intermediate output carry most of the SOTA-blocking signal BEFORE the render — that early warning is the whole point of the cadence.

Evidence: `feedback_monitor_means_line_by_line_forensic_2026_06_14.md`, `feedback_read_every_line_means_forensic_quality_not_status_check_2026_07_01.md`.

Recurrence: Twice-flagged (2026-06-14, 2026-06-15), re-flagged 2026-07-01; a repeat violation.

## Measure the per-stage source funnel on REAL run data before you conclude or write a brief

Measure discovered → fetched → extracted → deduped → relevance-floored → selected → cited on real run data before writing any brief, and never let a brief assert a quantity that was not measured. The Claude-Codex workflow verifies a diff against its brief; it cannot catch a brief that asserts the wrong number or aims at the wrong stage.

Why: On the saved drb_76 run the dominant ~90% source loss was UPSTREAM at fetch→extract→merge (~500 fetched → 46 rows; the selection cap never even engaged, dropped_count=0). Everyone assumed the cap; the cap was innocent. A brief written on that assumption would have fixed a no-op.

Evidence: `source_funnel_first_plan.md` "The lesson" + "Banked rule" (#1204); `permanent_fix_migration_blueprint.md` I-perm-003.

Recurrence: Recurring — measurement-before-brief flagged repeatedly.

## Documented gates and statuses with no reachable code branch are lies — verify each against the code with a contract test

For every documented gate, status, or contract, confirm there is an actual branch that emits it and add a contract test asserting every exit path conforms. Do not trust the doc or a log line over the code.

Why: Contract drift silently voids safety gates you believe are protecting the run, and it is only caught by grounding docs against code.

Evidence: `logs/bug_log.md` BUG-B-100 (scope gate never rejects, so `abort_scope_rejected` is unreachable), BUG-B-101 (success manifest lacks a status key while docs say `manifest.status` is authoritative), BUG-M-207 (no manifest-contract test), BUG-M-208 (frozen pipeline C advertises broken imports).

Recurrence: Recurring — multiple documented-vs-actual mismatches surfaced in one audit pass.
