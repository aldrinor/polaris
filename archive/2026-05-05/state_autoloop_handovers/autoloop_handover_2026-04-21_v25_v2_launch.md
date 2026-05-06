# POLARIS Autoloop V2 — V25 Launch Handover (2026-04-21)

Previous handovers:
- `state/autoloop_handover_2026-04-21_current.md` — V23 resume /
  DR pass 11 PARTIAL (superseded)
- `state/autoloop_handover_2026-04-20_TOPTIER.md` — V17 historical

## Stop condition

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on 7 dimensions.

## Protocol in force: Autoloop V2 (Codex-hardened)

Full runbook: `state/autoloop_v2_runbook.md`.
Memory rule: `memory/autoloop_v2_audit_cross_review.md`.

### Autonomous launch rule (load-bearing)

> **Claude launches the next V{N} sweep WITHOUT asking for user
> approval** as long as (a) code audit is Codex READY, (b) prior
> V{N-1} did not produce SHIPPABLE, and (c) no halt condition is
> triggered.

User directive 2026-04-21: "you don't need me to approve V25, if
both Claude and Codex agree, just auto launch".

V25 IS LAUNCHED. Future wake-ups check progress, generate audits,
and (after gate) launch V26 without re-prompting the user.

## Current cycle state

### V25 sweep (autonomous launch 2026-04-21)
- PID 5394 (at launch); log `outputs/_V25_sweep_stdout.log`
- Launcher: `scripts/run_full_scale_v25.py` (commit `6eb93ac`)
- Env: Serper/S2=50, fetch_cap=500, ev=600, budget $10/run
- Code: V24 + full M-41 bundle pass-2 Codex READY
- Target: `clinical_tirzepatide_t2dm`
- Expected: 90-130 min typical, 150-200 min if DNS issues

### Fix stack active in V25 (Codex READY)

| M-NN | Scope | Closes |
|------|-------|--------|
| M-35 | SURPASS/SURMOUNT anchor queries (retrieval) | Citations |
| M-36 | Trial Summary table (post-synthesis) | Structural depth |
| M-37 | Health Canada tier fix + prompt rule | Regulatory/Jurisdictional |
| M-38 | Claim-frame prompt rule | Claim frames |
| M-40 | Mechanism section + outline title visibility | Narrative depth |
| M-41a | Outline cap 5→6 (Mechanism additive) | Regulatory regression |
| M-41b | Trial table thin-row drop | Structural depth (guardrail) |
| M-41c | Deterministic claim-frame post-check | Claim frames (deterministic) |
| M-41d | Evidence selector T3 jurisdictional floor | Regulatory/Jurisdictional deterministic |

## Next V2 actions (autonomous, no user check-in)

Upon V25 manifest.json landing:

1. **Step 2a — Claude output audit** → `outputs/audits/v25/claude_audit.md`
   - Line-by-line 7-dim verdict vs `state/compare_chatgpt_dr.txt` + `state/compare_gemini_dr.txt`
   - Each dimension: concrete POLARIS-output line + competitor line + source URL
   - Required: BEAT_BOTH / BEAT_ONE / LOSE_BOTH per dim, evidence-grounded

2. **Step 2b — Codex output audit** → `outputs/audits/v25/codex_audit.md`
   - Brief staged at `.codex/dr_output_audit_pass_13_v25_v2_brief.md`
   - Parallel with 2a

3. **Step 3 — Cross-review** → `outputs/audits/v25/cross_review.md`
   - Per-disagreement table (finding_id, dimension, claude_verdict, codex_verdict, claude_evidence, codex_evidence, adjudicated_outcome, reason, required_action)
   - Lower-verdict-controls rule
   - Unresolved-finding auto-red

4. **Step 4 — Gate verdict** → `outputs/audits/v25/gate_verdict.md`
   - Per-dim outcomes + cycle count + wall-clock + spend
   - SHIPPABLE → stop loop, PushNotification, declare
   - CONTINUE → step 5
   - HALT → §7 trigger, user notification

5. **Step 5 — Fix plan** (if CONTINUE) → `outputs/audits/v25/fix_plan.md`
   - Per-item schema: causal_stage, prior_mechanism_gap, preservation_risks, acceptance_criteria, test_coverage, classification
   - Dimension-preservation statement (whole plan)

6. **Step 6 — Codex plan review** → `outputs/audits/v25/codex_plan_review.md`
   - Band-aid vs root-cause per item
   - Red → Claude revises; Green → implement

7. **Step 7 — Implementation + code audit** (M-42 if needed)

8. **Step 8 — V26 launch** (autonomous if conditions met)

## Halt conditions (§7 triggers, user notification)

1. ~~3 consecutive V sweeps without SHIPPABLE~~ — **REMOVED**
   per user directive 2026-04-21. Cycle cap is gone; loop is
   bounded only by spend + wall-clock.
2. 24h wall-clock cap (runaway safety)
3. $100 USD default spend cap (runaway safety)
4. Artifact integrity (manifest/report/bibliography disagree)
5. Baseline access failure (compare_*.txt unreadable)
6. Repeated-root-cause failure for 2 consecutive cycles
7. Dimension regression (BEAT_BOTH → not, or BEAT_ONE → LOSE_BOTH) without prior approval
8. Test-quality failure (skip/xfail/string-only/metadata-only)
9. Cross-review integrity violation
10. Code-audit bypass (Codex BLOCKED, V launched anyway)
11. Plan-review ping-pong > 3

On halt: `outputs/audits/v{N}/_halt_reason.md` with last good V,
failing V, failed dims, counters, exact next human decision.

## Trajectory

| Sweep | Pass | Verdict | Notes |
|------:|-----:|---------|-------|
| V17 | 8 | TOP-TIER (single-dim) | pre-BEAT-BOTH mandate |
| V18-V22 | — | (V1 iterations) | M-28..M-32 |
| V23 | 11 | PARTIAL | 1 BEAT_BOTH / 2 BEAT_ONE / 4 LOSE_BOTH |
| V24 | 12 | **REGRESSED** | 1 BEAT_BOTH / 1 BEAT_ONE / 5 LOSE_BOTH |
| V25 | (V2 auto) | in-flight | Target: ≥ V23 + Regulatory/Jurisdictional restored |
