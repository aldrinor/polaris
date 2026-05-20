# Codex diff — I-cd-028 (#618) — /contracts rebuild

Canonical-diff-sha256: `07d43deb7e08eb87698bc484a40f83448852f7b5700916cac3123caa26137faa`.

## Diff summary
- `web/app/contracts/page.tsx`: wrap in `<section data-testid="contracts-page">`. Strip Issue id + env-var name from user-visible copy.
- New `web/tests/e2e/contracts_g1_g8.spec.ts` with G1+G6+G2+nav+G8 assertions; BANNED_DEV_LANGUAGE extends to `\bi-ecg-/` + `POLARIS_REQUIRE_CONTRACT/i`.
- `web_ci.yml` binding step.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
