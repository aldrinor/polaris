# POLARIS — Restart Instructions

**Last update:** 2026-05-25 09:35 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge

- #873, #875, #877 — earlier sub-PRs
- #880 — I-ux-001d 95-frame design lock
- #881 — sub-PR 1 (Inspector v6)
- #883 — sub-PR 2 (Home v6) — Visual APPROVE 14/16 PASS — **+ #892 CI-wiring amend (Codex APPROVED)**
- #885 — sub-PR 3 (Intake v6) — chip descoped (see #886 below) — **+ #892 CI-wiring amend (Codex APPROVED)**
- #888 — sub-PR 4 (Source Review v6) — **+ #892 CI-wiring amend (Codex APPROVED)**
- #890 — sub-PR 5 (Plan v6) — **+ #892 CI-wiring amend (Codex APPROVED)**
- #893 — sub-PR 6 (Dashboard v6) — already CI-wired (g1_g8 folded)
- #895 — sub-PR 7 (/runs/[runId] v6) — already CI-wired
- #897 — sub-PR 8 (Compare v6 + first CI spec) — already CI-wired
- #899 — sub-PR 9 (/sign-in v6 + CI auth wiring) — already CI-wired

## Follow-up issues

- ✅ #892 CI dead-tests — CLOSED 2026-05-25. All 5 v6 specs wired into web_ci.yml via per-sub-PR amends (Codex APPROVED clean).
- 🔵 #886 AutoDomainChip SSR/hydration — **root cause clarified, downgraded P1→P3**. Root cause is Next.js 16 + Turbopack-dev-mode HMR WebSocket handshake failure on Windows. Production build (next start, what CI + Carney demo run on) renders the chip CORRECTLY. The chip itself is fine; dev-mode-only state-propagation bug. Recommended action: re-introduce chip in a future PR (works in prod), or accept dev-mode limitation. See #886 comment 2026-05-25 for full investigation evidence.

## Next session pickup

Remaining v6 pages to rebuild (any of these — pattern matured):
- /transparency — public disclosure page
- /upload — document grounding upload surface
- /memory or /graph — knowledge graph surface
- /audit_live — DEV/OPERATOR observability (reconsider whether v6 chrome applies)
- Restore AutoDomainChip in a follow-up PR (works in prod per #886 investigation)

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

## Brand-red authorization (3 paths, locked)

1. Brand identity (eyebrow, primary CTA, decorative)
2. Evidence-role semantic (TIER_DOT['T1'] = #c8102e per I-p2-003 #742)
3. Interactive affordance (text-primary on links + retry buttons)

## Session summary

This session (autonomous, operator asleep) shipped:
- 9 v6 chrome PRs (Home through Sign-in) — all Codex-approved, queued for operator merge
- 4 per-sub-PR CI-wiring amends (#892 fix) — all Codex APPROVED iter-1 clean
- Root-cause investigation for #886 chip bug — Turbopack-dev-mode HMR issue, not chip itself; prod works
- Pattern fully matured for remaining v6 page rebuilds
