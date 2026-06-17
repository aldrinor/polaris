# I-arch-007 death-fix — DEPLOY RECIPE (ready for the moment the build APPROVEs + preflight passes)

Operator GO given 2026-06-16: build → preflight canary → resume ALL 5 from checkpoints ASAP in PARALLEL. "Very behind."

## Deploy mechanism = scp (NOT git)
The boxes' `/root/polaris` is NOT a git checkout (branch/head/remote all empty). So deploy by **scp of the changed files** to the matching paths on each box. Files the build touches (confirm exact set from the build's `git diff -- src tests scripts`):
- `src/polaris_graph/llm/entailment_judge.py`            (ITEM 2a)
- `src/polaris_graph/synthesis/credibility_pass.py`      (ITEM 1b)
- `src/polaris_graph/generator/multi_section_generator.py` (ITEM 1 + 1b-wiring + 5-inject)
- `src/polaris_graph/generator/generation_snapshot.py`   (ITEM 5 / 5a; from Lane B + recursive guard)
- `scripts/run_honest_sweep_r3.py`                       (ITEM 3 + 5-wiring)
- `scripts/dr_benchmark/run_gate_b.py`                   (ITEM 6 + slate env)
- `src/polaris_graph/roles/sentinel_adapter.py`          (ITEM 4 — sentinel 376ac812, currently grep=0 on every box)
After scp: `python -c "import ast; ast.parse(open(f).read())"` each file to catch a broken transfer; grep the new env knobs / `PG_SENTINEL_TRANSPORT_DEGRADE` are present.

## The 5 boxes (all have corpus_snapshot, resumable)
| Run | host:port | domain | slug | snapshot | postgen | live |
|---|---|---|---|---|---|---|
| Q72 | ssh4.vast.ai:27202 | workforce | drb_72_ai_labor | 7.4MB | 63KB | wedged |
| Q76 | ssh7.vast.ai:23714 | clinical | drb_76_gut_microbiota_crc | 7.86MB | - | wedged |
| Q75 | ssh2.vast.ai:27070 | clinical | drb_75_metal_ions_cvd | 5.5MB | - | wedged |
| Q90 | ssh2.vast.ai:27886 | policy | drb_90_adas_liability | 2.98MB | - | dead |
| Q78 | ssh5.vast.ai:27242 | clinical | drb_78_parkinsons_dbs | 4.96MB | 32KB | dead(abort) |

## Per-box sequence (PID/slug-scoped kills ONLY)
1. scp the changed files (above) to `/root/polaris/<same path>`.
2. PID/slug-scoped kill any live `run_gate_b --only <slug>` (Q72/Q76/Q75); sleep 4.
3. Resume with the env slate below, from `corpus_snapshot` (ALL 5 → re-GENERATE+verify). **BREADTH-FIX OVERRIDE (advisor 2026-06-16):** every run MUST re-generate so the new `PG_BREADTH_ENRICHMENT_ENABLED=1` enrichment section fires; reusing pre-breadth postgen drafts (the old Q78 "reuse postgen cheap" note) would make breadth INERT and waste the spend. `PG_RESUME_REUSE_POSTGEN` stays default-OFF (ITEM-5 deferred) — do NOT enable it for any run here.
4. Confirm `BEHAVIORAL_CANARY_OK` in the new log + grep the box proc env has the new knobs.

## Env slate (READ the exact wall/inflight pair from the SLATE build agent — Codex P2-1: sized as a pair)
- `PG_CREDIBILITY_PASS_WALL_S=<pair>`  `PG_CREDIBILITY_PASS_MAX_INFLIGHT=<pair>`  (e.g. inflight 12-16 / wall 1200-1800)
- `PG_SENTINEL_TRANSPORT_DEGRADE=1`  `PG_TRAFILATURA_SUBPROCESS=1`
- `PG_BREADTH_ENRICHMENT_ENABLED=1`  ← BREADTH item-2 master flag; committed≠wired, so canary MUST show MORE distinct verified sources behaviorally, not just "flag set" (advisor 2026-06-16; arch005 lesson).
- entailment self-heal flag (per ITEM 2a). `PG_RESUME_REUSE_POSTGEN` = OFF for ALL runs (breadth needs fresh generation).
- carry the existing run env: `OPENROUTER_PROVIDER_ORDER=baidu,siliconflow,novita,streamlake,deepseek,wandb`,
  `OPENROUTER_ALLOW_FALLBACKS=true`, `PG_ENTAILMENT_TOTAL_S=45`, `PG_ROLE_CALL_TIMEOUT_S=900`,
  `PG_ALWAYS_RELEASE=1`, `PG_REDACT_HELD_UNSUPPORTED=1`, `PG_FOUR_ROLE_REASONING_EFFORT=medium`, ZYTE key.

## Gate before deploy
- Build Workflow (wzn7jtlc2): Codex diff gate APPROVE (0 P0/P1).
- Preflight behavioral canary: 1-query run exercising the credibility pass + a forced trickle/closed-client →
  wall-deadline degrades, parallel pass produces identical baskets, judge self-heals (no hang, no over-drop).
- Credit headroom ≥ ~$150 (5 concurrent end-to-end ~$100-200). Top up if short (operator: money no issue).

## Acceptance = ONE completed run, §-1.1 line-by-line audited (claim-by-claim vs fetched span). "Gates green" ≠ faithful.

## LAUNCHED 2026-06-16 ~22:24 — all 5 resumed on VMs with the hardened+breadth code
Deploy = scp tarball(src/scripts/config) + extract(preserve .env+outputs) + `python -m scripts.dr_benchmark.run_gate_b --only <slug> --resume --out-root outputs/beatboth_fixed`. Env: OPENROUTER_PROVIDER_ORDER=baidu,siliconflow,novita,streamlake,deepseek,wandb + PG_ENTAILMENT_TOTAL_S=45 PG_ROLE_CALL_TIMEOUT_S=900 PG_ALWAYS_RELEASE=1 PG_REDACT_HELD_UNSUPPORTED=1 PG_FOUR_ROLE_REASONING_EFFORT=medium PG_AUTHORIZED_SWEEP_APPROVAL=1 PG_MAX_COST_PER_RUN=60 PG_RESUME_REUSE_POSTGEN=0; slate force-sets breadth/wall(3000)/total-deadlines/caps-zero. Budget shown $50. ALL 5 BEHAVIORAL_CANARY_OK + ALIVE:
- Q72 ssh4:27202 workforce drb_72_ai_labor pid132991 ; log outputs/beatboth_fixed/workforce/drb_72_ai_labor/relaunch_iarch007.log
- Q76 ssh7:23714 clinical drb_76_gut_microbiota_crc pid136561
- Q75 ssh2:27070 clinical drb_75_metal_ions_cvd pid96510
- Q90 ssh2:27886 policy drb_90_adas_liability pid69027
- Q78 ssh5:27242 clinical drb_78_parkinsons_dbs pid105272
MONITOR: forensic every 5 min (log+reasoning_trace+cost_ledger+stage+breadth source count, judge soundness+faithfulness). ACCEPTANCE: §-1.1 line-by-line beat-both audit on first completion.
