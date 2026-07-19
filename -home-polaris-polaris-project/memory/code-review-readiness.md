---
name: code-review-readiness
description: "Telus code-review-readiness — Plan V4 executable scope COMPLETE; codex-sol final token READINESS-READY (2026-07-19)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

Initiative (started 2026-07-18): make the deep-research pipeline pass an independent **Telus** code
review WITHOUT changing the RACE score or faithfulness. Plan **v4** (codex-approved). Product rebranded
**Deep Cove Research** (repo `aldrinor/deep-cove-research`); "Polaris" is the internal codename. PRs base
= `gate-inversion` (main is unrelated-history). Absolute rules: faithfulness FROZEN; "byte-identical or
don't ship"; oracle golden SHA `9c0a3d438da943242c98e2fe714494c342d42d02102202d75a61a4554339db98`.

**STATUS (2026-07-19): executable scope COMPLETE. codex-sol final token = `READINESS-READY`.**
23 PRs shipped (#1381–1403). codex-sol had rejected an earlier "complete" claim and named 5 executable
blockers; all 5 now closed:
1. 0A-5 graph-selector fixtures → #1403 (23 routing-selector fixtures byte-identical for v1/v2/v3;
   real production closures recovered from compiled graph, not reimplemented; full-graph + v2
   Send-emitters deferred to 3C; codex `0A5-SUFFICIENT`).
2. N-run flaky gate → #1392 (1 flaky non-governing quarantined, 0 flaky governing).
3+4. closeout danglings + `lethal_retrieve`→`high_recall_retrieve` same-object alias → #1402.
5. oracle matrix re-run → all 7 runtime heads (#1382/1388/1397/1394/1396/1400/1402) + phase0 reproduce
   9c0a3d43 byte-identical.

**Oracle replay recipe (CRITICAL, learned the hard way):** force-copy the phase0 harness+cassettes onto
the target, run `/opt/conda/bin/python tests/oracle/acceptance_portable.py --mode replay` (conda/CUDA).
`PG_OUTLINE_AGENT_MAX_TURNS` MUST be 3 — it's embedded verbatim in the decide-step prompt ("Max N turns
total.") so it's part of the LLM cassette request identity. A concurrent bot (f9978dac) had defaulted the
portable harness to 6, silently breaking out-of-box replay; **fixed in beb9968 (PR #1381)** → clean
no-override replay now yields 9c0a3d43. Interpreter matters: pipeline-env misses; conda reproduces.

**Owner-only remainders (NOT executor blockers, per codex-sol):** PG_GENERATOR_MODEL value decision (Q2
reverted+deferred — 4 sites have non-empty defaults deepseek-v4-pro/glm-5.2); graph DELETION
authorization (Plan V4 §3C — needs owner sign-off + compat matrix + rollback window); Telus review +
merge of the 23 open PRs.

Prior context still valid: box-3 GPU cu128 clone via `/home/polaris/pipeline-env`→conda_cu128 symlink;
the "0 searches" alarm was the degraded GPU env, not a bug. See [[research-planning-gate]],
[[investigate-then-consult]].
