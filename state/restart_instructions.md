# POLARIS — Restart Instructions

**Last update:** 2026-05-25 08:50 UTC
**Active initiative:** I-ux-001 (GH #872) — S-tier experience initiative
**Operator status:** ASLEEP, FULL AUTHORIZATION granted

## PRs queued for operator merge (9 v6 chrome PRs from this session + 4 earlier)

- #873, #875, #877, #880 — earlier sub-PRs + design lock
- #881 — sub-PR 1 (Inspector v6)
- #883 — sub-PR 2 (Home v6, 14/16 visual PASS)
- #885 — sub-PR 3 (Intake v6, chip→#886)
- #888 — sub-PR 4 (Source Review v6)
- #890 — sub-PR 5 (Plan v6)
- #893 — sub-PR 6 (Dashboard v6)
- #895 — sub-PR 7 (/runs/[runId] v6, clean iter-1)
- #897 — sub-PR 8 (Compare v6 + first CI spec)
- #899 — sub-PR 9 (/sign-in v6 + CI auth wiring)

## Next session pickup

### Sub-PR 10 candidates (any of the remaining v6 surfaces):
- /transparency — public disclosure page
- /upload — document grounding upload surface
- /memory or /graph — knowledge graph surface
- /audit_live — DEV/OPERATOR observability (may not need v6 chrome; reconsider scope)

All branches: clean off polaris HEAD. Pattern fully matured:
- gh issue → branch → brief → Codex iter-1 (often clean) → build → diff → Codex iter-1 (often clean) → PR
- v6 tests folded into existing g1_g8.spec.ts (CI-run) OR new g1_g8 + web_ci.yml entry
- Auth-gated pages need CI env (sub-PR 9 added POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH)
- Honest sovereignty — never "signed bundle" overclaim; "audit bundle" is honest

## Follow-up issues filed in this session

- #886 — AutoDomainChip SSR/hydration silent-bailout
- #892 — CI dead-tests across sub-PRs 2-5 (standalone v6 specs not in web_ci.yml)

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
