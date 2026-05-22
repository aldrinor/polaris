# Codex review — I-p2-032 (#787): fix self-referential --font-sans

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `0a6e4db2546e2e49c8265894e2b53423b3ef439c4c06b444ab9e84263da237e2`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

One-line fix: web/app/globals.css:10 was `--font-sans: var(--font-sans);` (circular self-reference → font-sans resolves to nothing → all sans text falls back to browser-default serif, LIVE, incl. the flagship headline). layout.tsx loads Geist as `--font-geist-sans`. Fix sets `--font-sans: var(--font-geist-sans);` (parallel to the already-correct `--font-mono: var(--font-geist-mono)`). --font-heading already chains to --font-sans. Build green; headline now renders Geist Sans (screenshot-verified).

## Review focus
1. Is var(--font-geist-sans) the correct target (matches layout.tsx variable name)? Any other --font-sans consumer affected?
2. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
