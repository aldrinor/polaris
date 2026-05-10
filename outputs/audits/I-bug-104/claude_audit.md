# I-bug-104 Claude architect audit

## Issue
GH#358 — Archive failed prompt-rewrite experiment.

## Codex review
- Brief iter-1: APPROVE (0 P0/P1/P2, accept_remaining)
- Diff iter-1: APPROVE (0 P0/P1/P2, accept_remaining)

## Architectural review
Pure documentation. Captures hypothesis (per-decimal discipline) + result (−15pp regression, drop-reason shift no_provenance_token dominant) + lesson (over-strict prompts shift failure modes laterally) + forward-pointers (I-bug-101 FPR audit, I-bug-105/108 already shipped, Path A bakeoff).

## Verdict
**SHIP.**
