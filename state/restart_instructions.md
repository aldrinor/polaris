# Restart Instructions — 2026-04-29 (full-online integration autoloop)

## Active state

**Canonical roadmap:** `docs/full_online_plan_FINAL.md` (v4
GREEN-signed by Claude+Codex across 3 review rounds, locked
2026-04-29).

**Active phase:** Phase E0 — Observability & repro prerequisites.

**Current milestone:** M-INT-0a — Decision telemetry recording.
Wires `decision_telemetry.record_decision(...)` into production
scope-gate + induction call sites.

## Autoloop semantics (canonical, no human-intervention)

For each milestone in `docs/todo_list.md` Phase E0..H sequence:

  1. Claude builds the integration → commits
  2. Claude writes a Codex review brief
  3. Codex reviews → GREEN | PARTIAL | BLOCKED
  4. **PARTIAL → integrate findings → re-review (NO human)**
  5. **GREEN → lock + move to next milestone (NO human)**
  6. **BLOCKED → pause + flag user (ONLY human-intervention case)**

Stop conditions (per `feedback_autoloop_default_behavior.md` +
`feedback_dont_pause_autoloop.md`):
- BLOCKED Codex verdict
- Asymptote: 5+ rounds same surface, no convergence
- Primary-source conflict (Codex contradicts locked memory)
- Cost concern (per-day OpenRouter spend over budget)

Otherwise continue without per-round confirmation.

## Acceptance bar (every Phase E milestone)

Codex grep-verifies all 4:
1. Substrate is **imported** by the named production file
2. Substrate is **invoked** at the import site
3. **Run-log evidence** with non-zero invocation count
4. **`PG_USE_*` rollback flag** actually disables the new path

"Imported but unused" doesn't pass.
Locked memory rule: `feedback_substrate_is_not_product.md`.

## To resume mid-autoloop

1. Read this file
2. Read `docs/todo_list.md` for current milestone position
3. Read `docs/full_online_plan_FINAL.md` for full context
4. `git log --oneline -10` for last commits
5. Check `outputs/codex_findings/` for in-flight Codex reviews
6. Continue from wherever the autoloop stopped

## Per-milestone process

```
For each M-INT-N in docs/todo_list.md:

  1. TaskUpdate → in_progress
  2. Read M-INT-N spec from docs/full_online_plan_FINAL.md
  3. Build:
     - Implement integration touching the named production file
     - Add PG_USE_* rollback flag (defaults to enabled)
     - Add tests proving:
       * substrate IS imported (import statement assertion)
       * substrate IS invoked (callsite assertion)
       * flag=0 disables (monkeypatch test)
       * existing behavior preserved (regression tests pass)
     - Update threat-model doc if applicable
     - git commit
  4. Write Codex review brief at .codex/M-INT-N_v{N}_review_brief.md
  5. Launch Codex sync review:
     cat brief | codex exec --model gpt-5.4 -c reasoning.effort=xhigh
     output → outputs/codex_findings/M-INT-N_v{N}_review/codex_stdout.log
  6. Read verdict:
     - GREEN → lock, TaskUpdate completed, next milestone
     - PARTIAL → integrate findings → v{N+1} → loop step 4
     - BLOCKED → pause + flag user
  7. After GREEN-lock:
     - Update docs/todo_list.md status
     - Append to logs/session_log.md
     - Continue autoloop
```

## Files-of-record

- **Plan**: `docs/full_online_plan_FINAL.md`
- **Todo**: `docs/todo_list.md`
- **Memory (load-on-startup)**:
  `~/.claude/projects/C--POLARIS/memory/MEMORY.md`
- **Autoloop default behavior**: locked memory
  `feedback_autoloop_default_behavior.md`
- **Don't-pause rule**: locked memory
  `feedback_dont_pause_autoloop.md`
- **Substrate-not-product rule**: locked memory
  `feedback_substrate_is_not_product.md`

## What "fully online" means

End of Phase H: public URL → FastAPI Evidence Inspector →
controlled-access pilot users sign in → workspaces → audit-grade
clinical research → click-to-source citations → contradiction
matrix → citation-preserving exports → BEAT-BOTH telemetry vs
ChatGPT/Gemini DR → one paying pilot live.

Not a ChatGPT clone — audit-grade clinical research engine.
Deliberate scope per FINAL_PLAN.md positioning. 14-23 calendar
weeks ETA from 2026-04-29.

---

## Predecessor: Autoloop V2 was in force from 2026-04-21

Original V28→V29 runbook archived at
`state/autoloop_v2_runbook.md`. The integration autoloop
(this doc) supersedes the model-version-bump autoloop pattern,
but inherits the same Claude+Codex cross-review discipline.
