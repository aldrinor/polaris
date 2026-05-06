# POLARIS Autoloop V2 — V26 Launch Handover (2026-04-22)

Previous handovers:
- `state/autoloop_handover_2026-04-21_v25_v2_launch.md` — V25 launch
- `state/autoloop_handover_2026-04-21_current.md` — V23 resume (historical)
- `state/autoloop_handover_2026-04-20_TOPTIER.md` — V17 historical

## Stop condition

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on 7 dimensions.

## Current cycle state

### V26 sweep (autonomous launch 2026-04-22 03:44 PDT)

- PID 1303 (at launch); log `outputs/_V26_sweep_stdout.log`
- Launcher: `scripts/run_full_scale_v26.py` (commit `3660217`)
- Env: Serper/S2=50, fetch_cap=500, ev=600, budget $10/run,
  **PG_M41D_HC_QUOTA=2** (M-42d new knob)
- Code: V25 + full M-42 bundle
- Target: `clinical_tirzepatide_t2dm`
- Expected: 90-150 min typical, longer if DNS issues

### Parallel: Codex M-42d pass-2 confirm

- PID 1305 (at launch); log `outputs/codex_findings/m42d_code_audit_pass2/_codex_stdout.txt`
- Expected: 10-15 min
- Worst case (Codex red): halt V26 mid-run, fix, resume
- Best case (READY): no action

## V25 final verdict (prior cycle)

Per `outputs/audits/v25/gate_verdict.md`:

| Dim | V25 | V24 | V23 |
|---|---|---|---|
| 1. Citations | BEAT_ONE | LOSE_BOTH | LOSE_BOTH |
| 2. Regulatory | BEAT_ONE | LOSE_BOTH | BEAT_ONE |
| 3. Jurisdictional | BEAT_ONE | LOSE_BOTH | BEAT_ONE |
| 4. Claim frames | **LOSE_BOTH** | LOSE_BOTH | LOSE_BOTH |
| 5. Structural depth | **LOSE_BOTH** | LOSE_BOTH | LOSE_BOTH |
| 6. Contradiction handling | **BEAT_BOTH** | BEAT_BOTH | BEAT_BOTH |
| 7. Narrative depth | BEAT_ONE | BEAT_ONE | LOSE_BOTH |

**V25 aggregate: 1 BEAT_BOTH + 4 BEAT_ONE + 2 LOSE_BOTH.** Best so
far, zero regressions from V24.

**V26 target**: close Claim frames + Structural depth LOSE_BOTH →
BEAT_ONE or BEAT_BOTH. Preserve all others.

## M-42 bundle active in V26

| ID | Scope | Closes | Codex verdict |
|---|---|---|---|
| M-42e | Named-trial primary-paper T1 floor | Citations, Claim frames | READY pass-3 |
| M-42a | Anaphoric + group-reference claim-frame prompt | Claim frames | READY pass-2 (bundle with M-42b) |
| M-42b | Direct_quote-only trial summary table + timeline | Structural depth | READY pass-2 |
| M-42c | Mechanism T1+T2 floor + conditional section target | Claim frames, Narrative depth | CONDITIONAL pass-1 no-blockers |
| M-42d | HC T3 quota 1→2 + hpfb-dgpsa.ca anchor + preservation guard | Jurisdictional, Regulatory | CONDITIONAL pass-1 + pass-2 fixes applied |
| M-42 preservation suite | V26 vs V25 baseline tests | Regression guard | 12 tests (8 V26-gated + 4 self-tests) |

## V2 next actions (autonomous, no user check-in)

1. Wait for V26 manifest.json and Codex M-42d pass-2 findings.
2. **Step 2a — Claude output audit** → `outputs/audits/v26/claude_audit.md`
3. **Step 2b — Codex output audit** (parallel) → `outputs/audits/v26/codex_audit.md`
4. **Step 3 — Cross-review** → `outputs/audits/v26/cross_review.md`
5. **Step 4 — Gate verdict** → `outputs/audits/v26/gate_verdict.md`
6. **Step 5 — Fix plan** (if CONTINUE) → `outputs/audits/v26/fix_plan.md`
7. **Step 6 — Codex plan review** → `outputs/audits/v26/codex_plan_review.md`
8. **Step 7 — Launch V27** if plan approved.

## Cycle counters (informational; cap removed)

- Cycle count: V23, V24, V25 complete; V26 launched. 4th under BEAT-BOTH mandate.
- Wall-clock since loop start: ~12.5h as of V26 launch.
- Cumulative spend: ~$0.02 sweep + ~$4-6 Codex = ~$4-6 total (well under $100).
- Regressions: V23→V26 net +2 dims. No cycle-over-cycle regression.

## Halt conditions check (§7) at V26 launch

1. ~~Cycle cap (REMOVED)~~
2. 24h wall-clock: 12.5h < 24h — not triggered
3. $100 spend: ~$5 < $100 — not triggered
4. Artifact integrity: V25 manifest + all artifacts consistent — not triggered
5. Baseline access: state/compare_*.txt readable — not triggered
6. Repeated-root-cause 2 cycles: no — V26 targets different gaps than V25 — not triggered
7. Dimension regression: no dim went down V24→V25 — not triggered
8. Test-quality failure: 121/121 M-41+M-42 tests + 12 preservation tests pass — not triggered
9. Cross-review integrity: V25 cross-review honored lower-verdict-controls — not triggered
10. Code-audit bypass: M-42 bundle Codex-audited (all CONDITIONAL-no-blockers or READY) — not triggered
11. Plan ping-pong: no prior plan cycle for V26 — N/A

**No halt condition triggered. Autoloop continues.**

## Outstanding tasks at V26 launch

- Task #31 (pending): M-42c tightening — reservation accounting +
  mech_ev_count injection into section prompt. Non-blocker per
  Codex M-42c pass-1; defer unless V26 shows Mechanism regression.
