# Claude audit — I-cd-026 (#616)

- /upload page renders `<section data-testid="upload-page">` directly; AppShell provides the single header + main.
- New tests/e2e/upload_g1_g8.spec.ts: G1+G6 + G2 (body+titles+aria-labels) + nav parity + G8.
- web_ci.yml binding gate wired.
- Codex diff APPROVE iter 1.
