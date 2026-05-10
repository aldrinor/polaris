# I-doc-001 Claude architect audit

## Issue
GH#376 — Codify §-1 line-by-line audit standard + standard debug workflow.

## Codex review trajectory
- Brief iter-1: APPROVE, 0 P0 / 0 P1, 3 P2 cosmetic.
- Diff iter-1: REQUEST_CHANGES, 1 P1 (§-1.2 ordering vs §3.1 boot ritual + §3.0 halt gates).
- Diff iter-2: **APPROVE**, 0 P0 / 0 P1, 3 P2 cosmetic, `convergence_call: accept_remaining`.

Total iters: 3 (within 5-cap).

## Architectural review

**§-1.1 line-by-line audit standard** — coherent with CLAUDE.md §9 quality-gate framing. Adds the per-claim VERIFIED/PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE verdict vocabulary, which is new but doesn't conflict with existing §9 status enum (success / abort_* / error_*). The two operate at different layers: §9 is pipeline-level verdict; §-1.1 is per-claim audit verdict.

**§-1.2 standard debug workflow** — initially conflicted with §3.1 boot ritual (the "FIRST tool call is gh issue create" assertion preempted §3.1 step-0 canonical-pin verification). Codex iter-1 caught this. Iter-2 fix scopes §-1.2 to *task-work* tool calls explicitly, deferring to §3.1 step-0 + §10 boot ritual + §3.0 halt-marker checks. Coherent post-fix.

**web/AGENTS.md mirror** — coherent with the parent §-1 spec, with light condensation appropriate for frontend-agent context.

**Helper scripts** — committed as historical artifacts of the 2026-05-09 cleanup. P2 hygiene findings (head-pipe-hides-failures, vestigial-label-param) are non-blocking; scripts will not be re-run.

## Tests
No source-code change. Smoke baseline (entailment-judge tests) re-verified green: 66 passed in 3.62s.

## Verdict
**SHIP.** PR ready.
