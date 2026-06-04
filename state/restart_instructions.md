# POLARIS — Restart Instructions

**Last update:** 2026-05-24 (UTC)
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## Active work (most recent first)

### sub-PR 3 — Intake v6 (in progress)
- Branch: `bot/I-ux-001c-sub-pr-3-intake`
- GH issue: #884
- Brief: APPROVED Codex iter-4 (`.codex/I-ux-001c-3/codex_brief_verdict.txt`)
- Code: built (textarea.tsx, auto_domain_chip.tsx, intake/page.tsx rebuild, intake_form.tsx rebuild, intake_v6.spec.ts, intake.spec.ts updated)
- **NEXT:** typecheck + lint + commit + push + codex diff review + visual audit + PR
- Cap: ONE codex exec at a time; kill leftover python/node/codex processes between iters

### sub-PR 2 — Home v6 (PR #883, awaiting operator merge)
- Branch: `bot/I-ux-001c-sub-pr-2-home`
- Brief APPROVE iter-4 · Diff APPROVE iter-4 · Visual APPROVE iter-4 (14/16 PASS)
- 5-artifact triple COMPLETE in `.codex/I-ux-001c-2/`
- Cage blocks Claude merge per CHARTER §1; operator must merge

### sub-PR 1 — Inspector v6 (PR #881, awaiting operator merge)
- Branch: `bot/I-ux-001c-hero-implementation`
- Already complete with 5-artifact triple

### Other PRs queued for operator (cage blocks Claude merge)
- #873, #875, #877, #880

## Operating model (binding)

1. CODEX DECIDES EVERYTHING. NEVER ask operator. NEVER use Opus `advisor()` tool.
2. NO ITERATION CAP on the I-ux-001 plan review only; per-PR uses §8.3.1 5-cap.
3. DON'T checkpoint/pause/report. Per CLAUDE.md §8.3.10 forbidden self-stops.
4. §8.4 resource discipline: ONE `codex exec` at a time; kill leftover python/node/codex; never touch operator's other-project processes.
5. `gh pr merge --admin` REVOKED per CHARTER §1.
6. Honest sovereignty wording only (LLM via OpenRouter-US disclosed at /transparency).
7. Per-sentence provability + signed two-family bundle = core differentiator.
8. On context-fill: update this file, auto-compact, CONTINUE.

## Per-PR lifecycle (military-order)

GH issue → branch → brief → Codex brief APPROVE (5-cap, force-APPROVE at iter-5) → build → Codex visual audit (16-dim via `codex exec -i`) → Codex diff APPROVE → PR for operator merge queue → next sub-PR.

## Sub-PR plan order (I-ux-001c)

1. ✅ Inspector (#881)
2. ✅ Home (#883)
3. 🔨 Intake (#884) — in progress
4. ⏳ Source Review / Plan
5. ⏳ Run Progress / Dashboard
6. ⏳ Compare
7. ⏳ Knowledge graph / Audit / Sign-in / Transparency
