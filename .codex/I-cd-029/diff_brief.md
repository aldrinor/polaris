# Codex diff — I-cd-029 (#619) — /pin_replay rebuild

Canonical-diff-sha256: `919025f66484e1a8c663b0a6bee0ad4e30d01834e0a7a9f63e6d35a151e74f71`.

## Diff summary
- `web/app/pin_replay/page.tsx`: drop dual `<main>` wrappers; replace with `<section data-testid="pin-replay-empty">` and `<section data-testid="pin-replay-page">`. Strip "Seq 29 / I-A-12 / #619" + "M-INT-0b post-Carney" dev-language.
- New `web/tests/e2e/pin_replay_g1_g8.spec.ts`: G1+G6+G2+nav-parity+G8 with title/aria scanning. BANNED_DEV_LANGUAGE extended with `M-INT-0b` and `I-A-12`.
- `web_ci.yml`: new binding step.

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
