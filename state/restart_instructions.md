## ⚡ RESUME NOW (2026-06-07) — observability COMPLETE; Q1 paid run prepped ONE go-ahead away (operator asleep, autonomous, do NOT launch paid spend)

**I-obs-001 (#1141) full-run observability is COMPLETE** — AC1 heartbeat / AC2 retrieval-trace / AC3 raw-LLM-IO all Codex diff-gate APPROVE; 113/113 §5.2 faithfulness-guard + obs unit tests green (faithfulness untouched); commits `c8bc5ef5`..`2e247098` pushed to `origin/bot/I-ready-017-faithfulness`. Ledger `state/iobs001_observability.json`.

**Run-gating P0s already fixed+active on branch (verified, NOT re-done):** #1070 evidence-drop (`PG_LIVE_MAX_EV_TO_GEN=150` + preflight floor + capped dedup), #1071 verifier fail-open (`judge_error_rate>0.10 → abort_verifier_degraded`). Both OPEN pending the operator-gated live-run §-1.1 audit.

**Q1 (drb_72) paid run = ONE operator go-ahead away.** Exact launch sequence: `state/q1_run_prep_one_go_ahead.md`. **DO NOT** launch Step 2, DO NOT self-set `PG_AUTHORIZED_SWEEP_APPROVAL`/budget/journal-only. Overnight heartbeat cron `0c6a34c7` armed (every 12 min). Only halt on faithfulness-invariant risk or CHARTER/canonical-pin mismatch.

**On morning go-ahead:** run the NO-SPEND `--list` preview first → operator sets the auth env vars → `python -m scripts.dr_benchmark.run_gate_b --only drb_72_ai_labor` (built-in canary + $25 cap) → monitor via `tail -f state/run_status.json` + `<run_dir>/retrieval_trace.jsonl` every 15 min, update GitHub → §-1.1 line-by-line audit of `report.md` vs cited spans, then vs in-repo Q72 ChatGPT/Gemini outputs.

---

### PRIOR CONTEXT (2026-06-06) — I-ready-017 drb_72 FIX CAMPAIGN (superseded by the observability work above; campaign artifacts retained)

**The paid drb_72 smoke (#1098) completed: HELD at coverage 0.286, $7.86.** Forensic + missed-bugs + SOTA-research workflows produced a **Codex-APPROVED fix-campaign plan** (operator signed off 2026-06-06).

- **Plan:** `outputs/audits/I-ready-017/fix_campaign_plan.md` (plan-gate iter-2 APPROVE).
- **Ledger / wall-pin (THE resume anchor):** `state/ready017_fix_audit.json` — `current_pointer` + per-issue `phase_step`. Read this FIRST.
- **Bugs:** `outputs/audits/I-ready-017/missed_bugs_audit.md` (15, Codex-confirmed) + `forensic_root_cause.md`. Umbrella GH **#1100**; keystone PR #1101; fail-loud #1102.
- **Heartbeat cron:** job `62ef3e0a` (every 10 min, session-only) re-invokes the loop; if the session died, RE-ARM it (CronCreate, the runbook prompt in the plan §4) on resume.

**ON RESUME:**
1. Read `state/ready017_fix_audit.json` → `current_pointer` + the next `phase_step=todo` issue.
2. Continue the per-issue loop (plan §5): GitHub issue → fix (flag-gated, faithfulness-safe) → heavy smoke → **§-1.1 line-by-line audit on a REAL micro-run output** → ONE codex gate at a time via `state/codex_gate.lock` (5-iter cap). Evidence bar (plan §9): smoke PASS + Codex diff-APPROVE + §-1.1 audit table + tracker-fired proof. "Tests green" is NOT evidence.
3. Sequence (plan §6): PHASE 0 finish #1102 (FL-01 graph wrappers + FL-02 planner) → PHASE 1 faithfulness P0s (FX-01/FX-02/FX-03) + CANARY-01 → PHASE 2 P1 gates → PHASE 3 breadth → PHASE 4 telemetry → PHASE 5 **RERUN (HARD-gated behind FX-01+FX-02+FX-03+CANARY-01 + operator budget Q4)**.
4. **Update GitHub #1100 + the per-issue + the ledger + `logs/session_log.md` in REAL TIME.** Announce each codex launch + read each verdict inline (operator BLIND).
5. **Operator-only decisions pending:** Q5 chromium-on-VM (Phase 2 / FX-16), Q4 re-run budget (Phase 5).
6. **Only halt on:** a faithfulness-invariant risk (provenance/strict_verify/4-role) or a CHARTER/canonical pin mismatch. API errors are NOT a halt — back off + resume (§8.4, PID-scoped cleanup, NEVER name-global process kill).

---

# Restart Instructions — issue-driven workflow (post 2026-05-05 restart)

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (project directives, especially §3.0 + §10).
2. Read `polaris-controls/CHARTER.md` and `PLAN.md` (admin-only sister repo nested under POLARIS at `C:\POLARIS\polaris-controls\` per PR-B2 relocation 2026-05-05; gitignored from POLARIS).
3. Verify BOTH `polaris-controls/CHARTER.md` AND `polaris-controls/PLAN.md` SHAs against `state/polaris_restart/charter_sha_pin.txt`. Either-file mismatch = HARD STOP per §3.1 step 0.
4. Read `state/active_issue.json` — currently shows `I-carney-001` umbrella with `next_pr_task_id: I-arch-001a`.
5. **Read `.codex/I-carney-001/codex_brief_v2_iter5_force_approve.txt`** — the iter-5 force-APPROVE'd architecture plan for Posture C live submission, with residuals captured.
6. State explicitly to user: active issue ID + current step + next action.

## CURRENT WORKSTREAM (resume point as of 2026-05-12 22:00 UTC)

**I-carney-001 — Carney 1-week production deploy (Posture C live submission)** — GH#462 umbrella.

**Scope**: Boss directive 2026-05-12. User picked Posture C (live submission, ~3-4 week timeline). Demo target: 2026-06-05 to 2026-06-09.

**Codex APPROVE'd architectural decisions** (brief v1 iters 1-4 converged):
- Sovereignty bar **(c)** — Canadian-hosted public-policy research; foreign API egress permitted (OpenRouter/Serper/Semantic Scholar); transparency endpoint discloses
- Vendor **AWS ca-central-1 Montréal** — m7i-flex.4xlarge EC2 single-instance docker-compose
- Auth **static_accounts** — admin/operator/viewer pre-provisioned named accounts
- Concurrency **1 active research run** + N viewers
- Terminology: "Canadian-hosted public-policy research" (NOT "sovereign Canadian AI")

**Codex APPROVE'd architecture plan** (brief v2 iter 5 force-APPROVE per §8.3.1):
- 12 sub-issues opened GH#463-474
- Force-APPROVE artifact `.codex/I-carney-001/codex_brief_v2_iter5_force_approve.txt` captures residuals
- Residuals are I-arch-001d scope (verifier-span text, Pydantic Literal values, VerifiedReport required fields)

**24-day calendar**:

| Day | Issue | Title |
|---|---|---|
| 1-3 | GH#463 I-arch-001a | run_store schema + pipeline-A manifest augmentation |
| 4-6 | GH#464 I-arch-001b | v30_contract_synthesizer + 8 template golden fixtures |
| 4-6 | GH#465 I-arch-001c | scope_domain mapping at actor boundary |
| 7-8 | GH#466 I-arch-001d | artifact_to_slice_chain bridge + loader extension |
| 9-10 | GH#467 I-arch-001e | SSE Redis Streams + async + Last-Event-ID |
| 11 | GH#468 I-arch-001f | e2e test with pinned AuditIR fixture |
| 12-13 | GH#469 I-carney-005 | Deploy substrate (Dockerfile/entrypoint/compose/Next/GPG) |
| 14 | GH#470 I-carney-002 | AWS Canada infra |
| 14-15 | GH#471 I-carney-003 | Sovereignty + transparency endpoint |
| 16-17 | GH#472 I-carney-004 | Static_accounts auth + GPG keys |
| 18-22 | GH#473 I-carney-006 | Live-submission rehearsal §-1.1 audit |
| 23-24 | GH#474 I-carney-007 | Demo runbook + Codex sign-off |

**Next concrete action**: write `.codex/I-arch-001a/brief.md` and run Codex iter 1.

## Deferred (post-Carney-demo)

Phase 0 hardware + sovereign migration chain (#257-271 in TaskCreate; GH#85-91, #199-206) is deferred until after the Carney demo lands. Posture (c) means the Carney demo uses OpenRouter, not sovereign vLLM. The sovereign migration becomes Phase 2 of the project (replace OpenRouter with vLLM on OVH H200 or similar once Carney's office signs off on the audit-grade public-policy research deliverable).

## F-snowball workstream (completed earlier this session 2026-05-12)

6 PRs merged: #447 (canonical-pin), #456 (backend graph endpoint), #458 (ClaimGraph component), #459 (interactions+a11y), #460 (BFS expand), #461 (PNG/JSON export + Playwright). 8 GH issues closed (#448-455). The `/runs/[runId]/graph` route is live.

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely.
2. Read `polaris-controls/CHARTER.md` + `PLAN.md`.
3. Verify SHAs against `state/polaris_restart/charter_sha_pin.txt`.
4. Read `state/active_issue.json`.
5. Read `.codex/I-carney-001/codex_brief_v2_iter5_force_approve.txt`.
6. Active issue is `I-arch-001a` (GH#463). Next step: write brief.

## Workflow rules (binding)

Per CLAUDE.md §3.0 + plan §7.A LOCKED A2 + §7.B LOCKED B1:

- **Claude:** writes code (briefs AND diffs). Author of `.codex/<issue_id>/brief.md` AND `.codex/<issue_id>/codex_diff.patch` AND `outputs/audits/<issue_id>/claude_audit.md`.
- **Codex:** reviews. Two APPROVE gates per Issue (brief + diff). 5-iter cap per §8.3.1.
- **User:** spec owner + after-the-fact merge gate. Reads `git log` in morning (B1 pure auto-merge). CI required check `polaris/codex-required` enforces.

**Per-Issue 5-artifact triple** (CI rejects PR without these):
- `.codex/<issue_id>/brief.md`
- `.codex/<issue_id>/codex_brief_verdict.txt` (APPROVE)
- `.codex/<issue_id>/codex_diff.patch`
- `.codex/<issue_id>/codex_diff_audit.txt` (APPROVE)
- `outputs/audits/<issue_id>/claude_audit.md`

**Forbidden:**
- `gh pr merge --admin` (REVOKED per CHARTER §1)
- Issue jump (start `I-X-NNN+1` before `I-X-NNN` merged)
- Autonomous task pickup (user assigns; Claude doesn't pick)
- "While we're at it" polish in same PR
- STATUS blocks / recap text between work items

## Halt conditions (each emits `state/halt_<utc>_<reason>.md`)

- canonical pin SHA mismatch
- CHARTER.md OR PLAN.md SHA pin mismatch
- issue jump attempt
- PR opened with missing artifact triple
- Codex unavailable >1h
- 2-cycle repeated root cause
- 200-LOC PR cap exceeded
- 3+ PRs queued for user in 24h (reviewer fatigue)

## Critical memory entries

- `polaris_restart_2026_05_05.md` — cage tightened, role split, per-Issue triple
- `forbidden_admin_merge.md` — `gh pr merge --admin` REVOKED
- `feedback_codex_iteration_5cap_2026_05_06.md` — 5-iter cap per Codex review; force-APPROVE at iter 5
- `feedback_dont_pause_keep_executing_2026_05_07.md` — Claude is working hand, not decision-maker
- `feedback_route_policy_questions_to_codex.md` — brief Codex first; don't enumerate options to user
- `feedback_codex_approve_is_user_approve.md` — Codex APPROVE = user approve for engineering decisions

## Old auto-loop pattern (REVOKED 2026-05-05)

The previous "triangle loop" + auto-resume + `gh pr merge --admin` pattern is REVOKED. See `failure_28_commits_2026_05_03.md` for why.
