# I-deepfix-001 — RESUME POINT (read this FIRST on any wake or fresh session)

**If you are a fresh session:** read this file, then `.codex/I-deepfix-001/BOXC_OVERNIGHT_AUTONOMOUS.md` (full history) + `$SC/preflight_audit/disposition_table.md`, verify git HEAD, check which workflows finished (their `$TD/<id>.output`), and CONTINUE the 7-step plan below. Do NOT restart from scratch. Do NOT launch any paid VM run — HOLD for operator GO.

## Handles
- repo `/c/POLARIS`, branch `bot/I-wire-001-integration`
- SC = `/c/Users/msn/AppData/Local/Temp/claude/C--POLARIS/dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391/scratchpad`
- TD = `/c/Users/msn/AppData/Local/Temp/claude/C--POLARIS/dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391/tasks`
- disposition = `$SC/preflight_audit/disposition_table.md` (23 findings, all dispositioned)
- Box B `ssh6.vast.ai:34874`, Box A `ssh3.vast.ai:12228`, key `/c/Users/msn/.ssh/id_ed25519`
- Every fix gated by REAL Codex CLI (`env -u OPENAI_API_KEY codex exec -s workspace-write` in a throwaway `git worktree` for tests) + REAL Fable 5 (`agent(..,{model:'fable'})`). BOTH must APPROVE. 5-iter cap.

## Committed + gated so far (HEAD should be at or past 5fd99879)
- P0-2 render-verdict-drop (#2) — 48e0ee93
- DeepTRACE source_necessity min-cover (scorer paper-faithful 8/8) — 5fd99879
- (P7 summary table #6 committed earlier)
- rank-19 contradiction non-quantity-number fix (#19) — 5e94e6f0 (Codex+Fable APPROVE, clean-committed via the safe recipe: staged==3 files verified)

## ⚠️ CONTAMINATION FOUND 2026-07-05 ~02:58 — handle at scope-commit time
- Commit **56c50838** (the RESUME anchor commit) ACCIDENTALLY baked in 6 scope-gate ITER-1 files that a build agent left staged in the index: config/scope_ontology/source_types.yaml, src/polaris_graph/retrieval/{constraint_enforcement,forbidden_identity_gate,scope_facet_classifier}.py, tests/polaris_graph/{test_forbidden_identity,test_scope_timeline_gate}.py. These are ITER-1 (have the include-boost P1) — NOT final.
- Working tree is DIRTY (unstaged) with stale iter-1/2 edits to 5 scope existing files (run_honest_sweep_r3.py, scope_gate.py, blocked_reference_registry.py, evidence_selector.py, intake_constraint_extractor.py) + 2 rank19 files (contradiction_detector.py, live_deepseek_generator.py) + rank19 test. Index is CLEAN.
- **ROOT CAUSE: build agents wrote edits directly into the MAIN tree AND left files staged. LESSON: before ANY commit, run `git diff --cached --name-only` and `git status`; stage ONLY the explicit fix files with `git add <exact paths>`; NEVER `git add -A`/`git commit -a`; verify the staged set == the fix's file set before commit.**
- **CLEAN-COMMIT RECIPE for scope (when iter-3 BOTH-APPROVED):** authoritative content = the verified $SC/scope_gate_build.diff (final iter, against 5fd99879). To commit clean: (a) `git checkout 5fd99879 -- <5 existing scope files>` to revert dirty edits to pre-scope baseline; (b) `git rm -f <the 6 new scope files>` to drop the iter-1 committed versions; (c) `git apply $SC/scope_gate_build.diff` (against 5fd99879 → clean, recreates the 6 new + edits the 5); (d) run the scope tests to confirm green; (e) `git add <exactly the 11 scope files>`, verify `git diff --cached --name-only` == those 11, commit. This OVERWRITES the iter-1 files from 56c50838 with the final gated versions.
- **rank19 commit:** materialize $SC/tail_rank19.diff final content for ONLY contradiction_detector.py + live_deepseek_generator.py + test_deepfix_rank19_non_quantity_contradiction.py; do NOT touch scope files.
- Stashes intact incl wave1-iter3-wip (stash@{1}) — do NOT drop.

## Workflows in flight (check `$TD/<id>.output` items[].both_approve)
- `wcll34qxh` — scope-gate build iter-2 (fix include-boost wiring + TWO-SIDED real-drb_72 extraction test + fail-closed redaction). both_approve → COMMIT `$SC/scope_gate_build.diff` (stage only scope-gate files; no judge-swap; push; disposition #1/#3/#23). REVISE → iterate ≤5.
- `w6xfcd7go` — tail rank19 (contradiction non-quantity numbers). both_approve → COMMIT `$SC/tail_rank19.diff` (only contradiction_detector.py + live_deepseek_generator.py + tests; disposition #19).

## The 7-step plan (in order — do NOT skip, do NOT reorder)
1. **Scope gate** (iter-2 wcll34qxh running) → commit. Closes #1/#3/#23. HARD pre-commit: the diff MUST prove BOTH sides of extraction intelligence on the REAL drb_72 question — FULL question → catches pre-June-2023 + forbidden Salari (by identity) + scope; STRIPPED question → EMPTY → widest+deepest. Both Codex+Fable-gated.
2. **rank19** (w6xfcd7go running) → commit. #19.
3. **Coupled tail SEQUENTIAL** (14 findings share run_honest_sweep_r3.py → one commit at a time on evolving HEAD, per `$SC/tail_partition_plan.md`): B1 citation #7/#8/#10 → B2 disclosure #11/#12/#14/#15/#17/#18 → B3 composition #4/#5 + completeness-gate-lies(#6b) → B4 render/chrome #9/#13/#22 + #16-honesty. Each: build → Codex[workspace-write]+Fable gate → commit → next. Update disposition each.
4. **Box prep + funds**: Box A parity (git reset final HEAD, .venv transformers 5.8.1, models, scorers, mineru_svc venv, .env) + Box B pull. VERIFY FUNDS (vast + OpenRouter + Gemini) before any spend.
5. **Preflight**: SMALL real run on Box B proving each fix fires + scope/timeline behavior → fresh §-1.1 audit WITH evidence_pool.json + Codex+Fable sign-off on the preflight. Survivors → fix → gate. Verify #21 + #6.
6. **GREEN GATE → AUTO-PROCEED (operator switched from HOLD to AUTO-LAUNCH 2026-07-05 ~02:07).** When all fixes gated + preflight is Codex+Fable CLEAN → do NOT wait for operator; proceed straight to step 7. Write the green recap to disk + PushNotification the operator that the runs are LAUNCHING. **Conditional gate: auto-launch ONLY if preflight is genuinely CLEAN + funds verified. If preflight cannot get clean after ≤5 gate iters, OR funds insufficient, OR a genuine blocker → do NOT launch; PushNotification operator + wait.** Never launch on a deficient preflight.
7. **Two VM runs (AUTO after preflight clean — no operator GO needed)**: both drb_72, both boxes. RUN1 = game-rule (gate ON, full question w/ pre-June-2023 + forbidden Salari + required sections). RUN2 = full-power (gate ON, SAME question with source/timeline clauses STRIPPED — tests extractor intelligence, NOT flag-off). Launch carefully → forensic 5-min monitor (read every line). **ON A BUG DURING THE RUN (operator directive 2026-07-05 ~02:11): escalate IMMEDIATELY to Codex + Fable 5 → fix → test → gate → RELAUNCH from nearest checkpoint (corpus_snapshot) RIGHT AWAY — do NOT hold, do NOT wait for operator, do NOT re-run fresh — then KEEP MONITORING.** Only exception that still holds for operator: a fix that would RELAX the faithfulness engine or override an operator-locked gate (that still pauses + notifies). Everything traced + faithfulness-neutral = fix + relaunch immediately. After: §-1.1 serious audit + score both boards (DeepTRACE our paper-faithful scorer + DRB-II official Gemini) vs floor → honest. PushNotification operator with the SCORED RESULTS when done.

**FUNDS: operator confirmed 2026-07-05 ~02:11 that funds on ALL boxes are SUFFICIENT (vast + OpenRouter + Gemini). Skip the funds-block; a quick sanity glance is fine but funds are not a gate.**

## Anti-failure defenses (drift / diff / miss / stall / sloppy / API-error / die)
- **drift**: re-read this file + disposition + guardrails every wake; plan is pinned in order.
- **diff (contamination)**: parallel builds FILE-DISJOINT only; coupled tail is SEQUENTIAL (one commit at a time).
- **miss (orphan)**: disposition table tracks all 23; fresh preflight §-1.1 re-checks every one.
- **stall/hang**: long ~25-min heartbeat wakes even with no notification; if a workflow is "building" but its newest `agent-*.jsonl` mtime is stale >15min → TaskStop + relaunch/resume.
- **sloppy**: every fix Codex+Fable gated; never victory on deficient (score=floor is NOT a win); §-1.1 line-by-line, no metadata/pattern shortcuts.
- **API-error / workflow death**: workflows retry transient errors; a died workflow (errored, no .output) gets relaunched; §8.4 kill orphans + ≤4-6 concurrent.
- **session death**: THIS file + committed git + the persisted workflow scripts make a fresh session fully resumable — operator says "resume the deepfix loop" and a new session continues from here.

## Guardrails (never trade)
faithfulness engine NEVER relaxed; §-1.3 WEIGHT-not-FILTER (user-asked scope=honor; no-constraint=widest+deepest byte-identical); scope gate = selection/weight/disclose, never faithfulness-relax; deepener/R2/L2 WIDEN-ONLY; killed losers STORM/F2 OFF; do NOT commit unsigned sovereign-lock (judge-swap files: polaris_runtime_lock.yaml / canonical_pin.txt / openrouter_client.py / test_runtime_lock.py); mineru OWN venv NOT main; prove-internal-scorer-correct not official-harness-flag; heavy on VM not local; do NOT drop wave1-iter3-wip stash; PushNotification ONLY blocker / scored-result / needs_operator_decision / root-cause-proven / CLEAN-GREEN-RECAP-ready.

## 4-BOX SAFE+AGGRESSIVE STRATEGY (operator 2026-07-05 ~09:50 — maximize DRB-II chance in ONE wave)
Instead of safe-run → discover-short → second-cycle, run SAFE and AGGRESSIVE settings IN PARALLEL, score all, keep the winner per board.
- 2 boxes SAFE: current fixes + standard settings (game-rule + full-power questions). Known-good high-faithfulness.
- 2 boxes AGGRESSIVE: same 2 questions, breadth levers MAXED — widen-only wideners (deepener/R2/L2 armed hard), more query facets, more adequacy-loop passes. Faithfulness STILL fully gated (never relaxed).
DEPENDENCY (resolved by the coverage audit wviar8c9x → $SC/drb2_coverage_audit.md): "aggressive" = Tier A (max EXISTING widen-only levers, runnable now, NO build) + Tier B (deep RC-E synthesis for the ~18% analysis component — may be a genuine BUILD not a flag). Aggressive boxes run Tier A for sure; add Tier B only if the audit says it's a flag (else Tier B = second-cycle build, gated first). §-1.3: breadth via WIDEN-ONLY, never a cap/target/thinner.
BOXES: have Box A (ssh3.vast.ai:12228) + Box B (ssh6.vast.ai:34874). Provision 2 MORE once the audit defines the aggressive config (avoid rent-then-reconfigure). Cost not a limit (DNA fast+beat-both only params).
EXECUTION: after all 23 fixes committed + preflight clean + Codex+Fable sign-off → provision+configure the 4 boxes (2 safe std-config, 2 aggressive Tier-A[+B if flag]) → launch all 4 in parallel → forensic monitor → §-1.1 audit each → score all 4 vs floor (DeepTRACE + DRB-II) → keep the winner per board → honest report.

## ★ CURRENT AUTOMATED END-TO-END PLAN (2026-07-05 ~10:20 — SUPERSEDES the 7-step plan above; operator walked away, run UNATTENDED to scored results)
Drive this fully automated; surface to operator ONLY: a genuine blocker, a needs-operator-decision, root-cause-proven, or SCORED RESULTS. No permission-asking. Tight 240s loop; no rm -rf variable paths.

STATE: HEAD 403f79e8. 9/23 faithfulness findings committed. Branch bot/I-wire-001-integration.

RUNNING PARALLEL (commit each on BOTH-approve via the clean rebase recipe; REVISE→fix→re-gate ≤5):
- Faithfulness: B3-iter2 #4/#5/#6b (w2x1p9as7), B4 #9/#13/#16/#22 (wl8aedgtd), B2 #11/#12/#14/#15/#17/#18 (weym7qlvl).
- COVERAGE build (co-equal): w7g7v04qa — C1 R2 query-expansion recall fix + engage wideners (WIDEN-ONLY), C2 activate M6 + depth_synthesis (analysis off zero), faithfulness re-passed per clause. diff $SC/drb2_coverage_build.diff.
- read-only LOSS-RISK critic wwfohleig → $SC/lose_risk_register.md.

THEN (automated, in order):
1. Commit all built+gated fixes (faithfulness + coverage) via the safe recipe (grep '^+++ b/' the diff; git checkout HEAD -- those files; git apply --check; apply; run its tests in MAIN tree [artifact dir present]; git add EXACT; verify staged count==expected + no judge-swap/runtime_lock; commit+push; update disposition). Serial commits, rebase later batches onto new HEAD; on conflict rebuild vs new HEAD.
2. LOSS-RISK register: for each CRITICAL/HIGH closeable-before-run → build+gate (same rigor). The single-task(drb_72)-vs-full-132-task-leaderboard question → PushNotification as needs_operator_decision (do NOT block the drb_72 4-box run on it — that is the agreed run). Any fix-flag-defaults-OFF (won't fire in the run) → enable in the run env config.
3. Box prep: Box A (ssh3:12228) parity + Box B (ssh6:34874) pull to final HEAD; PROVISION 2 more boxes; config 2 SAFE (std) + 2 AGGRESSIVE (max wideners + synthesis on). Funds confirmed (not a gate).
4. PREFLIGHT: small real run (safe config) on Box B → fresh §-1.1 audit WITH evidence_pool.json + PROVE each fix FIRES (P0-2 verdict-drop, scope gate two-sided, citation, composition, disclosure, render/chrome, AND coverage: effective_query_count>>15, R2 expansion rounds>0, cross-source connectives/DS->0, unfetched_relevant_tail=0, cited-breadth count) + Codex+Fable sign-off. Survivors → fix→gate→re-preflight. Never launch on deficient.
5. GREEN GATE: preflight CLEAN → write recap + PushNotification 'runs LAUNCHING' → PROCEED (no waiting). Deficient/blocker/needs-operator-decision → PushNotification + wait.
6. AUTO-LAUNCH 4 VM RUNS (the agreed originals + safe/aggressive split), all gate ON + faithfulness NEVER relaxed:
   - Box1 SAFE game-rule (full drb_72: pre-June-2023 + forbidden Salari + required sections)
   - Box2 SAFE full-power (same question, source/timeline clauses STRIPPED — extractor intelligence)
   - Box3 AGGRESSIVE game-rule (max wideners + synthesis)
   - Box4 AGGRESSIVE full-power
7. Forensic 5-min monitor EVERY box: read every line (breadth + tier mix + extraction cleanliness + synthesis firing + effective_query_count, §-1.1 quality). ON BUG: escalate Codex+Fable → fix → test → gate → RELAUNCH from nearest checkpoint (corpus_snapshot) IMMEDIATELY, never fresh, keep monitoring. Only a faithfulness-relaxing / operator-locked-gate change pauses + notifies.
8. After each run: §-1.1 serious line-by-line audit + score both boards (DeepTRACE our paper-faithful scorer + DRB-II official Gemini run_evaluation.py) vs floor (DeepTRACE 0.8636 / DRB-II 0.0571). Keep the WINNER per board across the 4. PushNotification the SCORED RESULTS — honest (top / competitive / short + the real numbers + the 2nd-cycle items).

PAUSE-AND-NOTIFY conditions (only these): preflight cannot get clean after ≤5 gate iters; a fix would relax the faithfulness engine or override an operator-locked gate; funds insufficient; the full-132-task-leaderboard scope decision; a genuine unrecoverable blocker. Everything else = execute.

## ★ ALL BOARDS + ALL DIMENSIONS EQUAL (operator 2026-07-05 ~10:18 — "don't miss anything for all scoreboards, they are equally important")
Weight EVERY board + EVERY scored dimension equally through fixes → preflight → scoring. Miss none:
- DeepTRACE (faithfulness, all 8 metrics: citation-accuracy, thoroughness, relevant, unsupported, uncited, source-necessity, one-sided, overconfident) — served by the 23 faithfulness fixes + the paper-faithful scorer.
- DRB-II, ALL 3 dimensions co-equal: RECALL ~74% (coverage build C1: R2 query-expansion + wideners), ANALYSIS ~18% (coverage build C2: M6 + depth_synthesis), PRESENTATION ~8% (chrome-scrub #13, 5-col table #6, citation cleanup #7/#8, honest labels — plus check report formatting/tables/readability in the preflight §-1.1 audit).
- If POLARIS targets any OTHER board (e.g. DeepResearch-Bench RACE/FACT), score it too — do NOT assume only 2 boards; enumerate the target boards from the benchmark harness (scripts/dr_benchmark/) and score every one.
PREFLIGHT must prove fixes fire for EVERY board/dimension (faithfulness metrics + recall breadth + analysis synthesis + presentation formatting). SCORING reports EVERY board honestly (no board omitted, no dimension unmeasured). The loss-risk critic (wwfohleig) covers both boards; extend if a third board exists. Equal effort, equal measurement, no board left behind.

## ⛔ LOSS-RISK CRITIC (wwfohleig) — CRITICAL FINDINGS 2026-07-05 ~10:20 — LAUNCH HELD pending fixes + operator decision
Register: $SC/lose_risk_register.md. Launching the 4 drb_72 runs AS-IS = ~0 result (deficient). MUST-FIX + DECIDE before any paid spend:
- C2 WRONG-QUESTION RENDER BUG: PG_BENCHMARK_OFFICIAL_QUESTION defaults OFF → run silently generates against a REWRITTEN prompt (last scored report answered "Fourth Industrial Revolution / English-journals-only" NOT task72 → info_recall 0/57). MUST set =1 + add a render-time question-fidelity gate (assert report.md H1 matches bound question.txt; fail loud on reformulation).
- H1 SCOPE GATE DARK: PG_SCOPE_CONSTRAINT_ENFORCE + PG_EXTRACT_SCOPE_CONSTRAINTS + PG_RELEVANCE_PRESERVE_ANCHORS + PG_CORPUS_TIER_DISCLOSURE_MODE all default OFF, set NOWHERE in run_gate_b → the scope gate (64c10a49) produces ZERO effect on the run. MUST wire =1 in run_gate_b slate (~528/4213) + add to _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS (~1574) so it FAILS CLOSED if off. Smoke-grep run.log for '[select] I-scope-001: DEMOTED' + 'PINNED' — if absent, gate dark, DO NOT launch.
- Contract-scaffold gate: task72 requires 4 named sections + a final 5-col table (presentation rubric) — assert present, fail loud.
- C3 DEEPTRACE SELF-GRADED: our 0.8636 reuses the run's OWN kimi D8 verdicts (grades own homework, cite-acc ~1.0 by construction); independent GPT-5+jina on same report = 95% unsupported / 0% thoroughness. Our number is an INTERNAL ESTIMATE, not comparable. DECISION: build the independent-judge DeepTRACE path or label the number honestly.
- C1 N=1 vs N=132 (OPERATOR DECISION): a drb_72 win is NOT a board win. DRB-II = 132 tasks / 9415 rubrics, 66 Chinese; only datapoint = 7.1% stale; no Chinese pipeline (66/132 ~0 by construction); Western-only tier classifier. "Low-60s" = competitor SOTA DuMate 61.95%, not ours. Real leaderboard = full 132-task multi-language run — a big build, not these 4 runs.
AUTONOMOUS MUST-FIX BUILD (gated) launching now: wire the 4 dark flags + PG_BENCHMARK_OFFICIAL_QUESTION ON in the run_gate_b slate + preflight-required (fail-closed) + question-fidelity gate + contract-scaffold gate. After: preflight smoke MUST prove gate fires ('[select]... DEMOTED/PINNED') + right question + contract before ANY launch. LAUNCH HELD for operator decision on: (a) proceed with 4 valid drb_72 runs (real single-task signal, honestly N=1) vs redirect to the full-132-task+Chinese+independent-judge leaderboard build; (b) DeepTRACE independent judge.

## ★ OPERATOR CORRECTIONS 2026-07-05 ~10:25 (supersede parts of the loss-risk register)
1. C2 "wrong question" = MISREAD. Adding scope+timeline INTO the question is the INTENTIONAL game-rule capability test (does the pipeline restrict to in-scope sources). NOT a bug. Two distinct runs: GAME-RULE run uses the operator's scope-augmented question BY DESIGN; LEADERBOARD/FULL-POWER run must answer the OFFICIAL question (PG_BENCHMARK_OFFICIAL_QUESTION=1 applies to the leaderboard/full-power run only, NOT the game-rule run).
2. H1 scope-gate-DARK STANDS + is HIGH VALUE — a dark enforcement gate means the game-rule test cannot demonstrate scope-selection. Wiring the 4 flags ON (validity build w2ptbe1dy) directly serves the operator's test. KEEP.
3. C3 DeepTRACE self-graded / vs-GPT-5: DROPPED per operator standing rule (feedback_prove_internal_scorer_correct_not_official_harness_flag). Our scorer is PROVEN formula-correct → TRUST it, optimize against it. NO external-scorer spend at this stage, NO "not official harness" flagging. If our own number says short → fix the pipeline.
4. C1 Chinese pipeline: SET ASIDE. Target = DRB-II ENGLISH subset (66 en tasks) FIRST. Clear English, THEN add other languages. Do NOT block on the 66 Chinese now. "Beat DRB-II" this phase = beat the ENGLISH set.
NET: keep the validity build (scope flags ON for game-rule; official-question for full-power; question-fidelity gate applies to full-power/leaderboard run; contract-scaffold gate). Focus DRB-II English. Trust our proven scorer.

## 🔒 HARD PRE-LAUNCH GATE (operator 2026-07-05 ~10:50): ALL 29 FIXES MUST BE WIRED + FIRE — NONE DARK
29 fixes = 23 faithfulness + 2 coverage + 4 validity. Before ANY paid VM run:
1. FIRE MANIFEST ($SC/fire_manifest.md, build wgsuwmmxm): every fix → its PG_* flag(s) → default (ON/OFF) → force-set-in-run? Any flag default-OFF and NOT force-enabled = a DARK fix = RED LINE.
2. If the manifest lists ANY dark fix → BUILD+GATE the wiring (force-enable in run_gate_b slate + add to _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS so the run FAILS CLOSED if off) before launch. Extends the validity build.
3. PREFLIGHT SMOKE must PROVE each of the 29 fired (not just flag set — took effect): per-fix log-grep signature from the manifest (e.g. scope '[select] I-scope-001: DEMOTED/PINNED'; coverage effective_query_count>>15 + R2 rounds>0 + connectives/DS->0; P0-2 verdict-drop; B2 §8 authority-weight lines; etc.). If ANY fix's signature is ABSENT in the smoke run.log → that fix is DARK → DO NOT launch, fix the wiring, re-smoke.
4. all_wired=true (zero dark) + every fire-signature present + preflight §-1.1 clean = the ONLY green-to-launch condition. Never launch with a dark fix.
