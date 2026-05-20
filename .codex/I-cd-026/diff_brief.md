# Codex diff — I-cd-026 (#616) — /upload rebuild

Canonical-diff-sha256: `1ef540e46ee547e9adb0e0596416660e999bd1d0a140c2228bbf0d1cb40076d4`.

## Diff summary
- `web/app/upload/page.tsx`: replaced `<main>` with `<section data-testid="upload-page">` so AppShell provides the single main landmark.
- `web/tests/e2e/upload_g1_g8.spec.ts`: G1+G6 single header+main, G2 (body+titles+aria-labels), G1 nav parity, G8 (no console errors).
- `web_ci.yml`: binding CI step.

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
