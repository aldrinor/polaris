# POLARIS — Restart Instructions

**Last update:** 2026-05-25 07:45 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge (cage blocks Claude per CHARTER §1)

- #873, #875, #877 — earlier sub-PRs
- #880 — I-ux-001d 95-frame design lock
- #881 — I-ux-001c sub-PR 1 (Inspector v6)
- #883 — I-ux-001c sub-PR 2 (Home v6) — Visual APPROVE iter-4 14/16 PASS
- #885 — I-ux-001c sub-PR 3 (Intake v6) — chip descoped to #886
- #888 — I-ux-001c sub-PR 4 (Source Review v6)
- #890 — I-ux-001c sub-PR 5 (Plan Review v6) — Brief APPROVE iter-1 clean, Diff APPROVE iter-2

## Active work

### Sub-PR 6 — Dashboard v6 (just started)
- Branch: `bot/I-ux-001c-sub-pr-6-dashboard`
- GH issue: TBD next call
- Goal: rebuild `/dashboard` page chrome to v6 (eyebrow + display H1 + tightened subtitle); preserve runs-monitoring logic

## Follow-up issues filed

- #886 — AutoDomainChip SSR/hydration silent-bailout (descoped from #885)

## Operating model (binding)

1. CODEX DECIDES EVERYTHING. NEVER ask operator. NEVER use Opus `advisor()` tool.
2. NO ITERATION CAP on the I-ux-001 plan review only; per-PR uses §8.3.1 5-cap.
3. DON'T checkpoint/pause/report. Per CLAUDE.md §8.3.10 forbidden self-stops.
4. §8.4 resource discipline: ONE `codex exec` at a time; kill leftover python/node/codex.
5. `gh pr merge --admin` REVOKED per CHARTER §1.
6. Honest sovereignty wording only.
7. Per-sentence provability + signed two-family bundle = core differentiator.
8. On context-fill: update this file, auto-compact, CONTINUE.

## Per-PR lifecycle

GH issue → branch → brief → Codex brief APPROVE (5-cap) → build → Codex diff APPROVE → (Codex visual when dev-runnable) → PR for operator merge queue → next.

## Sub-PR plan order (I-ux-001c)

1. ✅ Inspector (#881)
2. ✅ Home (#883)
3. ✅ Intake (#885)
4. ✅ Source Review (#888)
5. ✅ Plan Review (#890)
6. 🔨 Dashboard — in progress (this branch)
7. ⏳ /runs/[runId] (live progress)
8. ⏳ Compare
9. ⏳ Knowledge graph / Audit / Sign-in / Transparency

## Brand-red authorization (3 paths, locked)

1. Brand identity (eyebrow, primary CTA, decorative)
2. Evidence-role semantic (TIER_DOT['T1'] = #c8102e per I-p2-003 #742)
3. Interactive affordance (text-primary on links + retry buttons)

## Pattern established (transfer to remaining sub-PRs)

For visual-only chrome rebuild:
- Single-file header chrome edit + 1 NEW e2e test file
- Brief: phase-explicit "BRIEF REVIEW not diff review" header + iter-1 typically APPROVE clean
- Diff: typically APPROVE iter-1 or iter-2 after a mock URL fix
- Mock auth-gated API in tests via page.route — use BROADEST sensible glob (e.g. `**/api/intake**` not `**/api/v6/intake**`) because BACKEND_URL prefix
- Pin exact subtitle copy verbatim before submitting brief
- Preserve all backend logic + all testids + all handoff contracts
