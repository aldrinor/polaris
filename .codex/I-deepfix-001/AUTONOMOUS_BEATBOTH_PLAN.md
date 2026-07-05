# I-deepfix-001 — AUTONOMOUS BEAT-BOTH PLAN (operator away 2026-07-05)

GOAL: a rendered report that GENUINELY beats DeepTRACE (faithfulness) AND DRB-II (coverage). Autonomous. Surface ONLY genuine blocker / operator-decision / SCORED beat-both results. NEVER victory on deficient. NEVER fake.

## STATE (2026-07-05 ~22:44)
- Box B ssh6.vast.ai:34874 run FINISHED with abort_run_validity_gate (4IR reformulation). PID dead. Box FREE.
- corpus_snapshot.json PRESERVED on Box B (1.9MB) → fast resume-resmoke (0 re-fetch) for downstream (compose/verify/render) fixes.
- Investigation workflow wbpc2n0qb RUNNING → produces prioritized fix-wave plan for 7 defect classes.

## 7 DEFECT CLASSES (all must be fixed + proven)
FAITHFULNESS-FORM (validate via resume-from-corpus, fast ~15min):
1. chrome survived (offline-journal[11], OpenAlex-metadata[12][19], byline[23], masthead[16]) — blind chrome/span-quality predicate
2. truncation ("within C"[22], "pedicurists is"[20], "in China."[18]) — blind truncation predicate
3. off-topic subtle (L2-writing[21] grounds Abstract+Opportunities) — entity-match beats aspect-match
4. date-window leak (2024/2025/2026 sources vs pre-June-2023 game-rule) — scope date-constraint not enforced
7. validity-gate 4IR reformulation → abort_run_validity_gate — pipeline invents aspect not in question
COVERAGE/DEPTH (SEPARATE co-equal track, needs FRESH front-half):
5. thin coverage + ~0 synthesis (missing GenAI RCTs Noy-Zhang/Brynjolfsson[7]-strict-verify-failed; 1 rubric aspect uncovered; depth_synth 0/3; 0 cross-source; 0 multi-source corroboration)
INFRA:
6. D8 judge blank-under-429 (reasoning judge starved/rate-limited → blank → stall). MUST fail CLOSED.

## PHASES (autonomous)
P1 INVESTIGATE (wf wbpc2n0qb running) → fix plan. On notify: read journal, extract plan.
P2 BUILD + DUAL-GATE: workflow per fix — worktree build + RED/GREEN test + real Codex CLI gate + real Fable5 gate (BOTH APPROVE), self-commit gated diffs. Fold in 4IR. Faithfulness NEVER relaxed. §-1.3 WEIGHT/WIDEN only.
P3 RESMOKE: kill any Box B leftover; resume-from-corpus_snapshot for form fixes (fast); FRESH front-half run for coverage fixes. .venv/bin/python. Judge-blank fix must be in so resmoke completes.
P4 §-1.1 AUDIT resmoke report (fan-out 1 agent/section + coverage critic) → any surviving defect → back to P2. NEVER victory on deficient.
P5 CLEAN resmoke → PAID beat-both run(s) (real judged questions).
P6 SCORE: DeepTRACE (our proven scorer) + DRB-II (official Gemini). beat-both? NO → iterate P2-P6. YES → surface SCORED RESULTS.
P7 Surface ONLY: genuine blocker / operator-decision (e.g. date-window hard-exclude vs disclose; judge GLM-maxtok vs model-swap) / SCORED beat-both.

## GUARDRAILS
faithfulness NEVER relaxed; §-1.3 WEIGHT-not-FILTER + WIDEN-only (no caps/targets/thinners); dual-gate (real Codex + real Fable5) EVERY fix; NEVER victory on deficient; NO permission-asking (authorized); NO rm -rf variable paths (git worktree remove --force + prune); use /root/polaris/.venv/bin/python; heavy runs on VM not local; ≤4 codex/agents in flight; crash→resume-closest-checkpoint never fresh.

## HANDLES
repo /c/POLARIS branch bot/I-wire-001-integration; Box B ssh6.vast.ai:34874 key /c/Users/msn/.ssh/id_ed25519; corpus_snapshot @ outputs/honest_sweep_r3/workforce/drb_72_ai_labor/; SC scratchpad; anchors: this file + RESUME_POINT.md + BOXC_OVERNIGHT_AUTONOMOUS.md + PREFLIGHT_EARLY_AUDIT_FINDINGS.md; investigation wf wbpc2n0qb.
