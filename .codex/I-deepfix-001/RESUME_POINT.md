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
