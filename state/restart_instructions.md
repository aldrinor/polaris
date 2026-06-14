## ⚡ RESUME NOW (2026-06-14) — I-arch-004 dual-sourced forensic COMPLETE; A1 crash-isolation committed; A2 in gate; resume cache-reuse plan ready

**I-arch-004 (#1248) pipeline chokepoint forensic = COMPLETE + dual-sourced.** Static (9 Codex sessions g1-g5 verify + h1-h4 hunt) + run-data (`drb72-deadrun-forensic` workflow, 6 Claude slices + Codex cross-audit APPROVE, 27 findings / 25 novel over the REAL 1622-capture run). Combined ledger = `.codex/I-arch-004/combined_dual_sourced_ledger.md` (TIER A-E; **THE resume map**). Resume plan = `.codex/I-arch-004/resume_plan.md`. Run-data copy = `.codex/I-arch-004/deadrun_artifacts/` (gitignored).

**FIXES (branch `bot/I-arch-002-no-dumping`, each Codex-gated):**
- **A1 crash isolation — DONE, Codex diff-gate APPROVE iter-4, committed `8415d496`.** `_gather_sections_isolated` catches the EXACT httpx transient set the client re-raises → visible gap-stub; hard gates (`CredibilityPassError`/`BudgetExceededError`) + programming/config defects propagate + explicitly cancel siblings (fail-fast). 11 + 62 tests green. Follow-up P2s: M-47 `is_gap_stub` skip, M-44 fail-fast.
- **A2 timeout/token sizing — code+tests done, Codex diff-gate IN FLIGHT (`b5916a7ww`).** Slate floors `PG_SECTION_MAX_TOKENS=64000` / `PG_GENERATOR_LLM_TIMEOUT_SECONDS=6500` / `PG_SECTION_WALLCLOCK_SECONDS=9000` + fail-loud preflight (smoke value can never reach a paid run). Files: `run_gate_b.py`, `run_honest_sweep_r3.py:6132`, `openrouter_client.py:801`. On APPROVE → commit **A2 files only** (A1 already committed; diff via `git diff --cached <A2 files>`).
- **NEXT (reshaped by TIER-D):** (1) **#1254 D8 Judge rubber-stamp** [FAITHFULNESS #1, clinical-critical — VERIFIED 69/69, overrode Sentinel 12/12, dismissed it as "metadata"], (2) empty-completion/reasoning-runaway "A4" (`contract_section_runner.py:710` silent-skip of `content=''`; lower reasoning effort for contract_slot calls), (3) B-tier static faithfulness (g3 side-judge `evaluator`-key routing = D15; fail-open NLI/conflict = D14), (4) retrieval §-1.3 drops + paywall stubs under I-arch-001 #1245 (D9-D13), (5) rest.

**RESUME the dead drb_72 run (operator-agreed 2026-06-14): minimal A1+A2 resume FIRST (proves the pipeline completes + salvages the corpus), then B-tier → trustworthy re-run.**
- GATED behind A1+A2 committed + VM redeployed. Do NOT fire a paid resume on the broken 600s wall (it would die again).
- VM `51.79.90.35` (`ssh -i ~/.ssh/polaris_orchestrator_key ubuntu@`): drb_72 out-root (37M) + `state/pg_search_cache.sqlite` (231M retrieval cache) + `cache/authority_enrich.sqlite` + Zyte key — ALL intact → retrieval replays near-free. VM at `f174692`, needs `git pull` to new HEAD + container rebuild (`arch002_runner`, currently unhealthy). Run env = full `/home/ubuntu/polaris_run/.env` (NOT the smoke slate).
- Launch: same query, same `--out-root`, `python -m scripts.dr_benchmark.run_gate_b --only drb_72_ai_labor` (built-in canary + $25 cap). Monitor `tail run_status.json` + `<run_dir>/retrieval_trace.jsonl`. Acceptance = §-1.1 line-by-line audit of `report.md` vs cited spans.

---

## ⚡ RESUME NOW (2026-06-12) — keystone map-reduce COLLAPSE fixed+committed; thinness #1218 forensic running via the Workflow function

**#1217 (I-perm-025) keystone map-reduce live collapse: RESOLVED + committed** — `8d74d1bb` (fix) + `bd6bb0a9` (doc) on `origin/bot/I-ready-017-faithfulness`. Three stacked bugs: Bug A orphaned-citation reattach + tightened REDUCE prompt; Bug B `_fuzzy_locate_span` paraphrase recovery (negation-safe expand-to-sentence) + fuzzy-only blocking entailment; Bug C `DISTILLER_VERSION` v2→v4 cache-invalidation (stale cache had masked the fix). Codex diff-gate iter1+iter2 APPROVE (`faithfulness_fuzzy_gate_sound=true`). Live: distill drop_rate 1.00→0.33, faithful verified contraindications, §-1.1 zero fabrication. 21/21 distiller + 100/100 generator tests. Forensic: `docs/keystone_collapse_forensic_consolidated.md` (PART 1/2/3); harness `scripts/dr_benchmark/offline_distill_replay.py` + `scripts/dr_benchmark/probe_source_map.py`.

**OPERATOR PROGRAM (2026-06-12), every task via the Claude Codex Workflow (the Workflow FUNCTION as engine, Codex the only gate), dual Claude+Codex line-by-line forensic to clear all land mines, small fast PAID VM verify after each fix:**
1. **#1218 (I-perm-026) THINNESS — IN PROGRESS.** distill 2 < legacy 6 on drb_76 Safety = MAP under-extracts on-topic safety numerics + REDUCE packs multi-number sentences strict_verify can't bind. NOT a faithfulness defect. Forensic workflow `wf_8d9b3d59-f84` (dual Claude+Codex) running. NEXT: consolidate → fix (denser MAP prompt + one-number-per-sentence REDUCE; extraction/shaping-side ONLY, strict_verify/4-role/D8 byte-untouched) → cheap MAXEV=8 VM verify (announce paid launch; OR_KEY_OVERRIDE from local .env NEVER written to a VM file) → Codex diff-gate → commit. Acceptance: distill verified >= legacy on Safety, §-1.1 clean.
2. **Then the 5 downstream (#1213/#1214/#1215/#1216/#1210) via PARALLEL workflows** (same method, faster).
3. **Then a broad all-sections live run** (not just Safety) to see how the fixed keystone behaves.

**VM:** ssh -i ~/.ssh/polaris_orchestrator_key ubuntu@51.79.90.35; replay dir ~/polaris-replay-019; launcher ~/vm_launch_replay.sh (MAXEV/PG_DISTILL_DEBUG/OR_KEY_OVERRIDE envs); venv ~/polaris-beatboth/.venv/bin/python. Clear `~/polaris-replay-019/.cache/polaris/evidence_distiller/*.json` between logic changes (or rely on the DISTILLER_VERSION bump).

---

## ⚡ RESUME (2026-06-07) — observability COMPLETE; Q1 paid run prepped ONE go-ahead away (operator asleep, autonomous, do NOT launch paid spend)

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
