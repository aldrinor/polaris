# POLARIS — Restart Instructions

**Last update:** 2026-05-25 07:30 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge (cage blocks Claude per CHARTER §1)

- #873, #875, #877 — earlier sub-PRs
- #880 — I-ux-001d 95-frame design lock
- #881 — I-ux-001c sub-PR 1 (Inspector v6) — Brief APPROVE iter-2 · Diff APPROVE iter-4
- #883 — I-ux-001c sub-PR 2 (Home v6) — Brief APPROVE iter-4 · Diff APPROVE iter-4 · Visual APPROVE iter-4 (14/16 PASS)
- #885 — I-ux-001c sub-PR 3 (Intake v6) — visual rebuild only; chip descoped to #886
- #888 — I-ux-001c sub-PR 4 (Source Review v6) — Brief APPROVE iter-3 · Diff APPROVE iter-1

## Active work

### Sub-PR 5 — Plan Review v6 (just started)
- Branch: `bot/I-ux-001c-sub-pr-5-plan-review`
- GH issue: TBD (next call)
- Goal: rebuild `/plan` page chrome to v6 (eyebrow + display H1 + tightened subtitle); preserve all run-start logic

## Follow-up issues filed

- #886 — AutoDomainChip SSR/hydration silent-bailout (descoped from #885)

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

GH issue → branch → brief → Codex brief APPROVE (5-cap, force-APPROVE at iter-5) → build → Codex diff APPROVE → (Codex visual audit when dev-server-runnable) → PR for operator merge queue → next sub-PR.

## Sub-PR plan order (I-ux-001c)

1. ✅ Inspector (#881)
2. ✅ Home (#883)
3. ✅ Intake (#885) — chip = #886 follow-up
4. ✅ Source Review (#888)
5. 🔨 Plan Review — in progress (this branch)
6. ⏳ Run Progress / Dashboard
7. ⏳ Compare
8. ⏳ Knowledge graph / Audit / Sign-in / Transparency

## Brand-red authorization (3 paths, locked)

1. Brand identity (eyebrow, primary CTA, decorative)
2. Evidence-role semantic (TIER_DOT['T1'] = #c8102e per I-p2-003 #742)
3. Interactive affordance (text-primary on links + retry buttons)

## Lessons applied (carry across sub-PRs)

- Visual-only scope from the start (no auto-domain chip; no synthetic metrics; LAW II)
- No backend logic changes
- Preserve all existing testids + handoff contracts
- Mock auth-gated API endpoints in new e2e tests (page.route)
- Brief BEFORE build; Codex review brief BEFORE Codex review diff
- Per Codex iter-2 P2 patterns: pin exact subtitle copy; verify against actual config/v6_templates/*.json
