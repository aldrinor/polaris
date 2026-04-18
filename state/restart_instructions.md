# Restart Instructions

## Current state (2026-04-18) — Phase E operational reconciliation complete; deep-dive rounds queued

**Branch**: `PL-honest-rebuild-phase-1`
**HEAD**: (latest commit after Phase E — see `git log --oneline -1`)
**Test suite baseline**: 305 passing, 0 xfail, 0 failed

---

## What just happened (recap for a fresh session)

### Phases completed this session (2026-04-18)

1. **Codex↔Claude audit rounds 1-5** — closed with READY verdict on
   narrow B-1..B-5 invariant scope. 5 blockers fixed, 85 regression
   tests added, 220 → 305 tests. Commits `724edf5`, `9493326`,
   `3a90b4f`, `c2570b2`, `248382e`, `db59e22`.

2. **Phase A/B/C repo cleanup** — archived 162 orphan files (61
   scripts + 71 src modules + 37 stale docs + root junk + scratch
   dirs) to `archive/2026-04-18-pre-audit-cleanup/`. Rewrote
   `README.md`, `architecture.md` (was 135KB fiction), rebuilt
   `docs/file_directory.md`, refreshed `docs/todo_list.md`, wrote
   new `docs/runbook.md`, updated `CLAUDE.md §5` + `§9`. Flagged
   `src/orchestration/` as FROZEN. Commit `0cf2a65`.

3. **Phase D full-pipeline audit pass 1** — built
   `docs/pipeline_audit_context/` bundle, ran Codex scoping pass.
   **Verdict: PRIORITIZED — 3 blockers, 8 mediums, 1 minor.**
   See `outputs/codex_findings/full_audit_pass_1/findings.md`.

4. **Phase E operational state reconciliation** (in progress or
   just committed):
   - Refreshed `ground_rules.md` (was describing dead P0-P12 arch)
   - Appended `logs/session_log.md` per CLAUDE.md §2.2
   - Appended `logs/bug_log.md` — closed B-1..B-5, opened B-100/101/102,
     M-201..208, N-301
   - Wrote this `state/restart_instructions.md`
   - Updated Docker entrypoint to remove/warn about broken pipeline C
   - Audited `requirements.txt`, verified `.env.example`, bundled
     `config/` into audit context, produced env-var inventory

---

## Next action

**Launch deep-dive round 1 (orchestration)** addressing BUG-B-101
(success manifest lacks `status` key) per Codex's priority queue:

```
1. orchestration (B-101)       ← NEXT
2. pipeline_b_parity (B-102)
3. intake_scope (B-100)
4. generation (M-203)
5. evaluator (M-205)
6. retrieval_tiering (M-201)
7. contradictions (M-202)
8. observability (M-206)
9. testing (M-207)
10. strict_verify (M-204 — light touch)
11. budget_cost (N-301 — light touch)
12. frozen_c_disposition (M-208 — user-facing)
```

Each deep-dive round = scoped Codex brief + Claude fix + regression
test. Estimated ~30-45 min per round at round-1..5 cadence.
Full sweep: ~8-12 hours total.

---

## How to resume

1. `cd C:/POLARIS`
2. `git status` — should be clean (Phase E just committed)
3. `python -m pytest tests/polaris_graph/` — should be 305 passed
4. Read:
   - `outputs/codex_findings/full_audit_pass_1/findings.md` — the risk register
   - `outputs/codex_findings/full_audit_pass_1/claude_response.md` — classification
   - `docs/todo_list.md` — backlog view
5. Prepare round 1 brief at `.codex/deep_dive_round_1_orchestration/BRIEF.md`
   targeting the manifest-contract unification (B-101).
6. Launch Codex deep-dive via the same pattern used in rounds 1-5:
   ```bash
   cat .codex/deep_dive_round_1_orchestration/BRIEF.md | \
     codex exec --sandbox workspace-write --skip-git-repo-check \
     --output-last-message outputs/codex_findings/deep_dive_round_1/last_message.txt \
     > outputs/codex_findings/deep_dive_round_1/stdout.log \
     2> outputs/codex_findings/deep_dive_round_1/stderr.log
   ```

---

## What to NOT do

- Do NOT delete anything from `archive/2026-04-18-pre-audit-cleanup/`
  until Phase E + all deep-dives are complete. The archive is the
  safety net for any missed-dep discovery.
- Do NOT re-open B-1..B-5 unless a new evasion vector appears. Those
  are closed with Codex READY verdict.
- Do NOT touch `src/orchestration/` until the retire/repair/leave
  decision is made (see BUG-M-208).
- Do NOT touch `scripts/live_server.py` blindly — deep-dive 2
  (pipeline_b_parity) will define what to back-port.

---

## Known-good environment

- Python 3.11+ (tested on 3.13.5)
- `requirements.txt` installed (audit in Phase E pending)
- `.env` with `OPENROUTER_API_KEY` + `SERPER_API_KEY`
- Working directory `C:/POLARIS`

## Known blockers (for production)

- BUG-B-100: scope gate unreachable abort status
- BUG-B-101: manifest status contract drift
- BUG-B-102: UI pipeline entirely un-hardened
- BUG-M-208: Docker `research` subcommand broken (pipeline C)

Until B-101 is fixed at minimum, downstream consumers cannot trust
`manifest.status` as documented. Until B-102 is fixed, UI production
is un-hardened despite the 5-round audit.

## Related files

- `logs/session_log.md` — full action history (last updated 2026-04-18)
- `logs/bug_log.md` — defect registry (B-1..B-5 closed, B-100/101/102 + M-201..208 + N-301 open)
- `docs/todo_list.md` — forward-looking backlog
- `docs/runbook.md` — how to run each pipeline
- `docs/live_code_audit.{md,json}` — static import-closure evidence
- `.codex/loop_state.json` — 5-round audit state
- `outputs/codex_findings/` — full audit history
- `archive/2026-04-18-pre-audit-cleanup/` — reversible snapshot
