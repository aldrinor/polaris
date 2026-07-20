---
name: baseline-next-step
description: "The immediate next action — run the baseline noise-floor harness before any improvement work"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**NEXT ACTION (agreed 2026-07-20): establish the scoreboard's noise floor BEFORE any improvement work.** A future "gain" smaller than the measured spread is noise, not progress.

Run the staged harness (durable, syntax-checked): `bash /home/polaris/wt/faithoff/scripts/baseline_triple.sh` (logs to `outputs/baseline_triple.log`, prints `BASELINE_DONE`). It has two phases:
- **Phase A (fast, no browser):** re-scores the frozen faith-off report `outputs/faithoff_t72/report.md` 3x → JUDGE variance alone.
- **Phase B (slow, live browser):** 3 full `run_raw_a.sh` pipelines + score → TOTAL variance (pipeline + judge), 45-min timeout each.

Run from the **faithoff worktree** (`/home/polaris/wt/faithoff`) — it is self-contained: faith-off code + the frozen corpus (`data/cp4_corpus_s3gear_329.json`, md5 `c7829cc...`, gitignored, identical across worktrees). Foundation code is byte-equivalent on gate-inversion (merged `15fcdda`). Reference points: champion 0.4447, earlier faith-off 0.4486.

Caveat: the composer does live gap-fill retrieval on a shaky browser, so Phase B runs may vary or fail (harness marks FAIL and continues). Then follows the improvement loop in [[governance-kit-operating-rule]]. See [[race-champion-config]].
