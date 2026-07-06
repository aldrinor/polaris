# I-deepfix-001 — TONIGHT ACTION PLAN (Codex + Fable + Claude, wpyb38srl, 2026-07-05)

## BIG CORRECTION (verified in the real tree)
Most of the "fix" is ALREADY BUILT + slate-pinned ON at HEAD — Codex thought we still had to build it; Fable proved we don't:
- PG_BASKET_CONSUME_FINDING_DEDUP already force-ON + preflight-required in the Gate-B slate (run_gate_b.py:1316).
- PG_CROSS_SOURCE_SYNTHESIS already slate-pinned ON, WITH a fire-canary that fails if it's ON but composes 0 while eligible pairs exist (run_gate_b.py:1500, :2431).
- The dead-synthesis span-join fallback already committed (depth_synthesis.py:106).
=> Tonight is NOT a build night. It is a MEASURE-and-find-the-real-break night.

## THE LIKELY TRUE ROOT (Fable's sharper diagnosis)
Every basket is a SINGLETON -> multi-origin baskets are structurally impossible -> depth + cross-source read 0 no matter what the composer does. Recent renders still show "Multi-source corroborated: 0" DESPITE the keystone being pinned ON. So the real break is probably UPSTREAM in finding_dedup producing all singletons, not in the composer.

## TONIGHT (2-GPU parallel, mostly FREE)
- ARM A (control): banked drb_72 replay, PG_BASKET_CONSUME_FINDING_DEDUP FORCED =0 -> the true singleton baseline. Box B GPU0. ~150-180 min.
- ARM B (variant): banked drb_72 replay, current HEAD Gate-B slate as-is (keystone already =1). Box B GPU1. Same corpus, same HEAD, parallel via device-split.
- Score BOTH: grounded_deeptrace_boxB.py (our proven DeepTRACE) + official DRB-II Gemini harness. Record HEAD sha + env manifest per arm.
- PARALLEL FREE (Claude local, no GPU): S2 forensic log-read (every line; 3 signals: do baskets group multi-origin? does depth fire? does cross-source fire?) + per-variant metric row; S3 canary-tighten (make a run with multi-origin==0 while keystone ON FAIL LOUD instead of passing silently) — behind default-OFF flag, dual-gated Codex+Fable.

## GO/NO-GO (from the two scored arms)
1. Keystone-credit gate: Arm B shows multi-origin>0 AND >=1 "[cross_source_synthesis] composed" AND depth kept_findings>0, with DeepTRACE citation-accuracy regression <=0.01 vs Arm A. Miss = keystone is WIRED-BUT-DEAD.
2. Promote gate: keep a variant only if DRB-II analysis/coverage +>=0.03 OR DeepTRACE overall +>=0.02 with ZERO faithfulness regression.
3. Diagnosis gate: Arm B multi-origin==0 -> confirmed root = finding_dedup singletons -> tomorrow's fix target = finding_dedup merge-key widening (composition builds are MOOT until baskets exist).

## HONEST TONIGHT RESULT
FINISHES tonight: the two-arm scored replay on drb_72 (definitive measurement of what the keystone actually does), the forensic diagnosis (which already-built lever is dead), the metric row, the canary tighten.
Expected score movement — modest and CONDITIONAL:
- If keystone FIRES: DeepTRACE +0.01..+0.03, DRB-II +0.03..+0.08 on drb_72. Small, visible, not a leap.
- If keystone DEAD-IN-SLATE (LIKELY, given "Multi-source corroborated: 0" at HEAD): tonight moves ~0 on score but delivers the CONFIRMED root (finding_dedup all-singletons) + exact fix target. That diagnosis is the real unlock.
SPILLS to tomorrow: (1) PG_SYNTH_PRIMARY grouped-narrative writer + bounded repair = the choppy-prose fix = primary-path rewrite, too big for one session — prose quality does NOT improve tonight; (2) frontier fresh-fetch run (not replay-provable); (3) if singleton-root confirmed, the finding_dedup merge-key fix + re-score.

## THE ONE GO DECISION
Approve the paid two-arm scored replay on Box B now (Arm A keystone-OFF control + Arm B current-HEAD keystone-ON) on banked drb_72, scored with our DeepTRACE + DRB-II Gemini, plus the parallel FREE Claude canary-tighten + log-read behind default-OFF flags. Faithfulness untouched; nothing merges without Codex + Fable approval.

## CODEX vs FABLE
Fable is closer to right (no build needed; sharper singleton root; 2-GPU parallel shape). Correction: the keystone is already =1 at HEAD so "flip vs HEAD" isolates nothing — you need a control arm forcing =0. Keep Codex's fail-loud canary discipline (the multi-origin==0 hole = S3).
