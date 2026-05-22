# Codex review — I-p2-p0 (#789): fix inspector 500 (centerpiece down in prod)

HARD ITERATION CAP: 5. iter 3 (iter-2 P1: typeof guard — proto-name runIds null not 500; verified toString/__proto__ now graceful). Canonical-diff-sha256 `8bbf413558688eccf96f01a2bef76029d080270e4969990e6fe2e924aa4c7990`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

P0: /inspector/[runId] returned HTTP 500 LIVE (ENOENT on tests/fixtures path not in the prod image). Fix:
- web/lib/inspector_bundle_loader.ts: FIXTURE_ROOT = process.cwd()/public/canonical_bundles (Dockerfile COPYs public → /app/public, cwd=/app — resolves dev+standalone+prod). KNOWN_FIXTURES → v1_canonical / v1_canonical_success.
- loadBundle body wrapped in try/catch → return null on any error → page renders BundlePendingCta, never 500.
- Canonical signed bundles copied into web/public/canonical_bundles/ (25K+21K; synthetic public demo fixtures, no secrets).
Verified locally: /inspector/v1-canonical-success now HTTP 200 + renders the full proof-replay (signed-bundle card, two-family Pass, verified report w/ provenance tokens).

## Review focus
1. Does process.cwd()/public resolve in the prod container (Dockerfile WORKDIR /app + COPY public → ./public + CMD node server.js)? Any env where it breaks?
2. Try/catch graceful-null correct (no 500 path remains)? Any read outside the try?
3. Are the public fixtures safe to serve statically (synthetic, no secrets)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
