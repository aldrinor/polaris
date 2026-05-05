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
- `gh pr merge --admin` REVOKED from Claude.

Read project `CLAUDE.md` §3.0 + §10 boot ritual before any frontend work.

<!-- END:polaris-restart-2026-05-05 -->
