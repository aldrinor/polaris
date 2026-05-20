HARD ITERATION CAP: 5 per document. This is iter 1 of 5.

# Codex diff review — I-cd-016a (under #626; harness only)

Brief APPROVE'd at iter 3/5. 3 files / +379 LOC. Path-A split per Codex scope-consult 2026-05-20.

## §A — Canonical diff summary (excludes .codex/ + outputs/audits/ per-issue convention)

The reviewable canonical diff contains:
- 1 NEW operator-runs harness (`scripts/live_run_smoke.py`).
- 1 docs section appended (`docs/runbook.md` "Live-run smoke").
- 1 trajectory log append (`state/polaris_restart/iteration_trajectory.md`).
- iter-1+iter-2 fold-in commits: `template_id` → `template`, SSE degraded-status handling, cancel-on-SSE-error, tarfile path-traversal hardening pre-lstrip detection, runbook STATIC_ACCOUNTS_PATH default correction, _env() exit code, "Does NOT close #626" heading.

Out-of-canonical-diff (audit substrate; reviewed separately):
- `outputs/audits/I-cd-016/harness_ready.md` (Phase-N-PARTIAL-honest manifest).
- `.codex/I-cd-016/` brief + verdict files.

## §B — Acceptance check

| Criterion | Status |
|---|---|
| 9-layer flow: transparency preflight + auth + POST /runs + SSE wait + lifecycle poll + bundle fetch + conformance check + verified-content assert + wallclock report | YES |
| Race-handling: post-run_complete lifecycle poll (30 × 2s) | YES |
| Cancel-on-timeout to prevent runaway OpenRouter spend | YES |
| 9 structured exit codes for diagnosis | YES |
| httpx (already pinned in requirements-v6) — no new dependency | YES |
| Documents known limitations: lock-verification deferred to I-cd-016b; GPG preflight stub | YES |
| Does NOT close #626 (PR description states harness-only) | YES |
| Two carved bug issues filed (I-cd-016c #675 + I-cd-016d #676) | YES |

## §C — Codex Red-Team checklist

1. Smoke script flow matches brief §A exactly.
2. SSE-completion race handled: lifecycle poll AFTER run_complete + BEFORE bundle fetch.
3. Cancel-on-timeout: POST /runs/{id}/cancel before exit 13.
4. No lock-verification assertions (deferred to I-cd-016b after I-cd-016c fixes the bridge).
5. GPG preflight uses /transparency stub + documents the limitation (real preflight at I-cd-016d).
6. Exit codes are stable + documented in module docstring.
7. No accidental file additions beyond the 3-file scope.
8. Manifest only references real paths + frozen-schema fields.

## §D — Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
