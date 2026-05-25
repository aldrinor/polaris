# POLARIS — Restart Instructions

**Last update:** 2026-05-25 09:50 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge

- #873, #875, #877 — earlier sub-PRs
- #880 — I-ux-001d 95-frame design lock
- #881 — sub-PR 1 (Inspector v6)
- #883 — sub-PR 2 (Home v6) — Visual APPROVE 14/16 PASS — + #892 CI-wiring amend
- ⚠️ **#885 — sub-PR 3 (Intake v6) — SUPERSEDED by #901** (incomplete descope broke typecheck; #901 restores chip + un-breaks CI). Operator: merge #901 instead.
- #888 — sub-PR 4 (Source Review v6) — + #892 CI-wiring amend
- #890 — sub-PR 5 (Plan v6) — + #892 CI-wiring amend
- #893 — sub-PR 6 (Dashboard v6) — already CI-wired
- #895 — sub-PR 7 (/runs/[runId] v6) — already CI-wired
- #897 — sub-PR 8 (Compare v6 + first CI spec) — already CI-wired
- #899 — sub-PR 9 (/sign-in v6 + CI auth wiring) — already CI-wired
- **#901 — sub-PR 3b (AutoDomainChip restore, supersedes #885)** — Codex APPROVED iter-1

## Follow-up issues

- ✅ #892 CI dead-tests — CLOSED. All 5 v6 specs wired via per-sub-PR amends.
- 🔵 #886 AutoDomainChip — root-caused (Turbopack-dev-mode HMR bug on Windows; works in prod). P1→P3. Chip restored on PR #901.

## Brand-red authorization (3 paths, locked)

1. Brand identity (eyebrow, primary CTA, decorative)
2. Evidence-role semantic (TIER_DOT['T1'] = #c8102e per I-p2-003 #742)
3. Interactive affordance (text-primary on links + retry buttons)

## Next session pickup

Remaining v6 pages to rebuild (any of these — pattern matured):
- /transparency — public disclosure page
- /upload — document grounding upload surface
- /memory or /graph — knowledge graph surface
- /audit_live — DEV/OPERATOR observability (reconsider whether v6 chrome applies)

Branch off polaris HEAD. Pattern: GH issue → branch → brief → Codex iter-1 (often clean) → build → diff → Codex iter-1 (often clean) → PR.

## Operating model (binding) — unchanged

1. CODEX DECIDES; NEVER use advisor.
2. NO ITERATION CAP on plan; per-PR 5-cap §8.3.1.
3. DON'T checkpoint (§8.3.10).
4. ONE codex exec at a time; §8.4 resource discipline.
5. gh pr merge --admin REVOKED per CHARTER §1.
6. Honest sovereignty wording only.
7. Per-sentence provability + signed two-family bundle differentiator.
8. On context-fill: update + auto-compact + CONTINUE.

## Session summary (final)

Shipped:
- 9 v6 chrome PRs (#883 Home through #899 Sign-in)
- 1 chip restore PR (#901, supersedes #885)
- 4 per-sub-PR CI-wiring amends (#892 fix) — all Codex APPROVED
- 1 root-cause investigation (#886) with debug evidence
- All Codex-approved; all queued for operator merge
