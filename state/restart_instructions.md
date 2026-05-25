# POLARIS — Restart Instructions

**Last update:** 2026-05-25 08:10 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge (cage blocks Claude per CHARTER §1)

- #873, #875, #877 — earlier sub-PRs
- #880 — I-ux-001d 95-frame design lock
- #881 — I-ux-001c sub-PR 1 (Inspector v6)
- #883 — I-ux-001c sub-PR 2 (Home v6) — Visual APPROVE iter-4 14/16 PASS
- #885 — I-ux-001c sub-PR 3 (Intake v6) — chip descoped to #886
- #888 — I-ux-001c sub-PR 4 (Source Review v6)
- #890 — I-ux-001c sub-PR 5 (Plan Review v6)
- #893 — I-ux-001c sub-PR 6 (Dashboard v6) — Brief 5-cap converged, Diff APPROVE iter-1

## Active work

### Sub-PR 7 — /runs/[runId] v6 (just started)
- Branch: `bot/I-ux-001c-sub-pr-7-runs-runid`
- GH issue: TBD
- Goal: rebuild `/runs/[runId]` page chrome to v6 (eyebrow + display H1 + tightened subtitle); preserve SSE live progress logic

## Follow-up issues filed

- #886 — AutoDomainChip SSR/hydration silent-bailout (descoped from #885)
- #892 — CI dead-tests: sub-PRs 2-5 v6 specs not in web_ci.yml enumeration

## Operating model (binding)

1. CODEX DECIDES EVERYTHING. NEVER ask operator. NEVER use Opus `advisor()`.
2. NO ITERATION CAP on the I-ux-001 plan only; per-PR uses §8.3.1 5-cap.
3. DON'T checkpoint/pause/report (§8.3.10 forbidden self-stops).
4. §8.4 resource discipline: ONE `codex exec` at a time; kill strays.
5. `gh pr merge --admin` REVOKED per CHARTER §1.
6. Honest sovereignty wording only.
7. Per-sentence provability + signed two-family bundle = core differentiator.
8. On context-fill: update this file, auto-compact, CONTINUE.

## Pattern established (transfer to remaining sub-PRs)

For visual-only chrome rebuild:
- Brief: explicit "BRIEF REVIEW not diff review" phase header
- Brief iter-1 OR iter-2 should APPROVE if pattern followed
- Mock auth-gated API URLs via page.route — match BACKEND_URL prefix
- Honest sovereignty wording — "audit bundle" not "signed bundle"
- v6 tests folded into existing g1_g8.spec.ts (CI-run) not standalone
- Pin exact subtitle copy in brief before submitting
- Preserve all backend logic + testids + handoff contracts
- Single-file header chrome edit + test file update

## Sub-PR plan order (I-ux-001c)

1. ✅ Inspector (#881)
2. ✅ Home (#883)
3. ✅ Intake (#885)
4. ✅ Source Review (#888)
5. ✅ Plan Review (#890)
6. ✅ Dashboard (#893)
7. 🔨 /runs/[runId] live progress — in progress (this branch)
8. ⏳ Compare
9. ⏳ Knowledge graph / Audit / Sign-in / Transparency

## Brand-red authorization (locked, 3 paths)

1. Brand identity (eyebrow, primary CTA, decorative)
2. Evidence-role semantic (TIER_DOT['T1'] = #c8102e per I-p2-003 #742)
3. Interactive affordance (text-primary on links + retry buttons)
