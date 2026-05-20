HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-014 / GH#610

Brief APPROVE'd at iter 3/5 (clean: zero P0/P1/P2). 8 files / +259 / -7 / +252 net LOC.

## §A — Diff summary

- 2 hygiene files (.gitignore + .dockerignore) — close Codex iter-2 P1 Docker-context leak.
- 2 deploy doc updates (docs/carney_demo_runbook.md + infra/vexxhost/README.md) — outside-repo path for real static_accounts.
- 1 new client component (auth_redirect.tsx) — UX-only redirect with explicit security framing.
- 1 sign-in page update (?next= URL validation + data-testids).
- 1 new e2e spec (sign_in.spec.ts; 9 cases).
- 1 new test fixture (test_static_accounts.yaml; verified bcrypt hashes).

## §B — Acceptance check

| Criterion | Verified |
|---|---|
| static_accounts hygiene closed (gitignore + dockerignore + 2 doc updates) | YES — git check-ignore matches; .dockerignore lists config/static_accounts.yaml; both deploy docs use /etc/polaris path |
| `?next=` URL validation via `new URL` + same-origin | YES — `safeNextPath()` in sign-in/page.tsx |
| AuthRedirect security framing | YES — explicit "NOT an authz boundary" in module docstring; useRef sentinel SSR-safe |
| Test fixture bcrypt hashes verified | YES — bcrypt.checkpw confirmed both hashes |
| G1-G8 e2e coverage | YES — render/console/responsive cases in spec |

## §C — Codex Red-Team checklist

1. `.gitignore` line matches `config/static_accounts.yaml` (verify via `git check-ignore`).
2. `.dockerignore` exclusion sits AFTER any earlier `!config/` un-ignore rules (no negation override).
3. `auth_redirect.tsx` `useRef` sentinel pattern avoids the react-hooks lint error AND doesn't introduce a flash-of-protected-content on slow auth checks.
4. `safeNextPath` correctly rejects: absolute URLs / protocol-relative // / backslash separators / fragment-only / parse errors.
5. Test fixture bcrypt hashes are valid bcrypt format AND verify against documented plaintext.
6. `?next=` e2e test cases cover the 3 validation paths (same-origin honor / absolute URL fallback / protocol-relative fallback).
7. Sign-in page no longer hardcodes redirect to `/` — uses `safeNextPath()` result.
8. Deploy docs no longer instruct operator to stage `config/static_accounts.yaml` inside repo.
9. No accidental file additions beyond the 8-file scope.

## §D — What this PR does NOT do (per scope discipline)

- Real production bcrypt hashes (operator-provisioned).
- `/inspector/[runId]` `<AuthRedirect>` wrap (deferred to I-B-08).
- Other-route wrappers (subsequent A-rebuilds).
- Cookie session migration / SSO.
- Visual baseline PNG capture (test.fixme deferred).

## §E — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
