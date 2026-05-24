# Restart Instructions — ACTIVE: I-ux-001 S-tier experience initiative (2026-05-24)

## ⚡ CURRENT WORKSTREAM (resume point as of 2026-05-24)

**I-ux-001 — S-tier experience plan + execution (GitHub #872).** Operator directive 2026-05-24, operator ASLEEP, **FULL AUTHORIZATION**. Autonomous, multi-session.

**Read first on resume:**
1. `docs/stier_experience_directive_2026_05_24.md` — the full directive + operating model + research synthesis.
2. `.claude/hooks/stier_directive.txt` — the TL;DR (also auto-injected by the SessionStart hook after compaction).
3. Memory `feedback_codex_decides_all_stier_uncapped_2026_05_24.md`.

**Operating model (binding):** Codex decides ALL — never ask the operator. NO iteration cap on the plan review. Don't checkpoint/report/pause. On context-fill: update THIS file, auto-compact, continue. One codex at a time (§8.4). Route everything to Codex CLI (`env -u OPENAI_API_KEY codex exec`, visual via `-i`); NEVER the Opus advisor() tool.

**Anti-drift machinery (LIVE, verified 2026-05-24):**
- SessionStart hook `.claude/hooks/stier_session_start.py` → re-injects directive on startup/resume/compact.
- Stop hook `.claude/hooks/stier_stop_hook.py` → blocks premature stop while #872 OPEN; gates on objective GitHub state; escape valves = `state/stier_halt_*.md` / gh-failure / issue-closed / 60-block stuck-cap.
- Both wired in `.claude/settings.json` (single committed source; `settings.local.json` hooks block removed to avoid double-fire).

**Current step:** SETUP COMPLETE (memory + directive doc + hooks + issue #872 + task). NEXT = draft the S-tier experience PLAN (`docs/stier_experience_plan.md`) covering: product-direction decisions (multi-turn vs one-shot, branching→knowledge-graph, agentic visible work, proof-as-hero) decided WITH evidence; end-to-end UX flow; visual/design system; per-page spec; differentiation thesis; execution sequence. THEN brief Codex for an UNCAPPED deep review until APPROVE at its highest bar.

**Figma:** OAuth started; operator must open the URL (in session_log 2026-05-24) to authorize `mcp__figma__*`. Non-blocking.

**Known constraint (Codex decides priority):** #871 (I-bug-900) — a real flagship clinical run aborts `corpus_inadequate` (tier classifier mis-tiers FDA/NICE/WHO/PubMed; T1=0). The demo journey can't render a real verified brief until this is fixed. Surface to Codex in the plan; let Codex sequence it.

## Boot ritual (mandatory per CLAUDE.md §10)

1. Read `CLAUDE.md` completely (esp. §3.0 + §10 + §-1).
2. Read `polaris-controls/CHARTER.md` + `PLAN.md`; verify SHAs vs `state/polaris_restart/charter_sha_pin.txt` (mismatch = HARD STOP).
3. Read `state/active_issue.json`.
4. Read the three "Read first on resume" files above.
5. State to user: active issue (#872 I-ux-001) + current step + next action — then CONTINUE (no pause).

## Workflow rules (binding)

Per CLAUDE.md §3.0 + plan §7.A LOCKED A2 + §7.B LOCKED B1:
- **Claude:** writes briefs + diffs (`.codex/<issue_id>/brief.md`, `codex_diff.patch`, `outputs/audits/<issue_id>/claude_audit.md`).
- **Codex:** reviews — brief gate + diff gate + (for UI) 16-dimension VISUAL design audit via `codex exec -i`. The ONLY decision-maker.
- **User:** spec owner; reads `git log` in the morning. CI `polaris/codex-required` enforces.
- **Per-page UI lifecycle:** issue → branch → brief → Codex brief review → build → Codex visual design audit (screenshot matrix, standalone harness) → Codex code-diff review → merge → redeploy → screenshot-verify LIVE → close → next.

**Iteration cap:** the I-ux-001 **plan** review is UNCAPPED (operator 2026-05-24). Per-page diff/design reviews use the standard §8.3.1 5-cap unless the operator says otherwise.

**Forbidden:** `gh pr merge --admin` (REVOKED); issue jump; PR without artifact triple; "while we're at it" polish; STATUS/recap prose between work items; self-initiated cadence stops (§8.3.10); calling the Opus advisor() tool.

## Halt conditions (each emits `state/halt_<utc>_<reason>.md` or `state/stier_halt_<reason>.md`)
- canonical pin / CHARTER / PLAN SHA mismatch
- issue jump attempt · PR missing artifact triple · Codex unavailable >1h
- 2-cycle repeated root cause · 200-LOC PR cap exceeded · 3+ PRs queued for user in 24h

## Critical memory entries
- `feedback_codex_decides_all_stier_uncapped_2026_05_24.md` — THIS initiative's operating model
- `feedback_no_opus_advisor_use_codex_cli_2026_05_23.md` — route all review/decisions to Codex CLI
- `feedback_codex_has_vision_use_image_flag_2026_05_23.md` — `codex exec -i` for visual audits
- `feedback_top_tier_visually_verified_not_merged_2026_05_21.md` — "complete" = visually verified live
- `feedback_dont_pause_keep_executing_2026_05_07.md` — Claude is the working hand; don't pause
- `forbidden_admin_merge.md` — no admin-merge authority
