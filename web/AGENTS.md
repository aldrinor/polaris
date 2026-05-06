<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.

<!-- END:nextjs-agent-rules -->

<!-- BEGIN:polaris-restart-2026-05-05 -->

# POLARIS issue-driven workflow (mandatory)

Per project `CLAUDE.md` §3.0 + `state/polaris_restart/plan.md`:

- Every unit of work is a GitHub Issue from `state/polaris_restart/issue_breakdown.md`.
- Per-Issue 5-artifact triple required (brief + verdict + diff + audit + claude_audit). CI enforcement lands at PR-D; pre-PR-D, Codex review enforces.
- Per plan §7.A LOCKED A2 + §7.B LOCKED B1: Claude writes briefs + diffs; Codex reviews twice per Issue (brief + diff); CI required check `polaris/codex-required` gates GitHub auto-merge; user reads `git log` morning.
- **HARD ITERATION CAP: 5 per Codex review** (added 2026-05-06 per CLAUDE.md §8.3.1). If Codex has not APPROVE'd by iter 5, Claude force-APPROVE's and ships, capturing residual concerns as follow-up Issues. Every brief MUST include the verbatim cap directive (see CLAUDE.md §8.3.3 + `.codex/REVIEW_BRIEF_FORMAT.md` §0).
- **Resource discipline (CPU/RAM/GPU)** per CLAUDE.md §8.4 (added 2026-05-06): one `codex exec` at a time; kill leftover python/node/codex processes between iters; no heavy ML/CUDA processes in autonomous loops; track long-running dev servers and kill before next Issue; pre/post-task `Get-Process` inventory.
- `gh pr merge --admin` REVOKED from Claude.

Read project `CLAUDE.md` §3.0 + §10 boot ritual before any frontend work.

<!-- END:polaris-restart-2026-05-05 -->
