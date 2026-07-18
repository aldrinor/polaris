# 0026. Resume from the closest checkpoint after a downstream crash; never re-run fresh

Status: accepted

Date: 2026-07-01

## Context

The operator corrected a fresh re-run and called this "our original ground rule" (2026-07-01). When a paid run errors or crashes AFTER a checkpoint was written, re-running fresh re-does the expensive already-completed upstream stages — retrieval, fetch, tiering, approval — that were saved to disk and are unaffected by a downstream crash, wasting 40+ minutes and real spend. Over-caution about "reusing a crashed run's state" is not justified when the crash is downstream of the checkpoint; that data is intact.

## Decision

When a paid run crashes after a checkpoint, relaunch with `--resume` from the closest checkpoint; do not re-run fresh. Before relaunching, check the output directory for a resumable checkpoint (`fetch_snapshot.json`, `corpus_snapshot`, `corpus_approval.json`). If its mtime predates the crash and the crash was later-stage, the checkpoint is good. Kill any fresh relaunch you already started before it overwrites the good snapshot.

## Consequences

- The checkpoints ARE the ground rule; they exist to be resumed from, so bypassing them wastes the compute they were written to save.
- A downstream crash does not corrupt upstream checkpoint data, so caution about "a crashed run's state" does not apply to the intact upstream stages.
- A fresh relaunch is actively dangerous because it can overwrite the good snapshot; kill it before it does.
- This pairs with the resource discipline of running heavy work on the VM: resume-from-checkpoint is the cheapest recovery path and should be the default reaction to any post-checkpoint crash.
