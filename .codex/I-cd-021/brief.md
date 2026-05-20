HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-021 (#631) — Inspector offline fallback

## §A Scope

Acceptance: "Offline fallback: Inspector renders a signed bundle in-browser, no GPU/no backend."

This is the **disconnected-reviewer** path. A reviewer (or Carney's office) receives a `.tar.gz` audit bundle as an email attachment / USB drop, opens a static deployment of the Inspector, drops the tar.gz, and sees the full bundle rendered (manifest + verified report + reasoning trace + sources + metadata + signature presence).

Companion to I-cd-020 (which confirmed the I-A-02b frozen schema is **BundleManifest v1.0**, served by `/bundle.tar.gz` for real runs and also as a static .tar.gz produced by `tar -czf` against a v1.0 bundle directory).

### Implementation plan

1. **Add browser-tar dependencies** to `web/package.json`:
   - `pako` (≈45KB minified, mature, browser-tested gzip) — same lib used by GitHub's own tarball viewer.
   - `tar-stream` browser build OR a lighter alternative like `js-untar` (≈10KB). Decision: pick `js-untar` for size; pako handles gunzip then js-untar reads tar.
2. **NEW `web/lib/inspector_bundle_client_loader.ts`** — `loadBundleFromTarGz(file: File): Promise<LoadedBundle>`:
   - `pako.inflate(arrayBuffer)` → tar bytes
   - Iterate tar entries via `js-untar` (or `tar-mini`); collect `{name, content}` map
   - Parse `manifest.yaml` via existing `parseManifest()` from `web/lib/signed_bundle.ts`
   - Use the same `LoadedBundle` interface shape as `inspector_bundle_loader.ts` (server-side loader) — components don't care which loader produced the data
   - Run 12-layer conformance check (or a browser-safe subset — signature verify uses GPG which is browser-incompatible; mark `signaturePresent = bundle contains manifest.yaml.asc with content`)
3. **NEW `web/app/inspector/offline/page.tsx`** — client component:
   - Drag-drop OR file-picker for .tar.gz
   - On drop: call `loadBundleFromTarGz`, render the SAME components used by `/inspector/[runId]/page.tsx` (`<BundleHeader>`, `<FamilySegregationBadge>`, `<ScopeDecisionCard>`, etc.)
   - Error state: malformed tar / missing manifest.yaml / schema violation → user-visible error card
4. **NEW `web/components/inspector/metadata_panel.tsx`** + add a "Metadata" tab to `web/app/inspector/[runId]/inspector_view.tsx` (Codex diff iter-1 P1.2 fix). Currently `LoadedBundle.metadata` is parsed but never rendered. Acceptance for both /inspector/[runId] AND the new offline route requires the metadata panel to display:
   - run_id, query, queued_at, finished_at, pipeline_status
   - generator_model, evaluator_model, family_segregation
   - cost_usd, latency_ms
5. **NEW Playwright test** `web/tests/e2e/inspector_offline_fallback.spec.ts`:
   - Build a tar.gz from `tests/fixtures/signed_bundle/v1_canonical_success/` at test setup
   - Set the file input → expect rendering
   - Assert verified-report section count + family-segregation badge + signature-presence indicator
6. **Frontend tests** with vitest (if not present, use Playwright unit-test mode) for the loader function shape.
7. Playwright e2e ALSO asserts metadata panel visibility (Codex iter-1 P1.2 fix).

Estimated canonical diff: **~250-300 LOC** + ~80KB of new node_modules (pako + js-untar).

## §B Acceptance check

| Criterion | Met by |
|---|---|
| Inspector renders a v1.0 bundle without any backend running | offline/page.tsx + inspector_bundle_client_loader.ts |
| Same UI components reused (no duplicate renderer) | imports from `web/components/inspector/` |
| `LoadedBundle` shape identical to server-side loader | same interface in inspector_bundle_loader.ts |
| Signature presence surfaced (manifest.yaml.asc detected; cryptographic verify is browser-incompatible) | `signaturePresent: boolean` |
| Conformance check runs in-browser | port of `check_bundle_conformance` (Python) to TS — OR re-use the SAME validation logic via `parseManifest` + per-content-type required-file lookup |
| Playwright e2e: drop a real tar.gz, assert rendered content | inspector_offline_fallback.spec.ts |
| No GPU, no backend, no API call | offline route is a pure client component |
| WCAG: file-drop accessible via keyboard (label + role=button + aria) | offline/page.tsx |

## §C Codex Red-Team checklist

1. **Library choice**: pako (gzip) is the established browser-safe gzip implementation. js-untar is well-known but unmaintained — alternatives: `tar-mini` (TS, maintained), `it-tar` (streaming). RECOMMEND `pako` + `tar-mini`. Pin specific versions in package.json.
2. **GPG signature verify**: explicitly NOT in scope. The bundle's `.asc` file's existence is checked, but cryptographic verification requires a CLI tool. Document this in the offline page.
3. **Conformance check parity**: server has 12-layer `check_bundle_conformance`. Browser MUST do at least: manifest parse, version=1.0, required ContentTypes present, SHA256 of each file matches manifest (browser crypto.subtle.digest is available).
4. **SHA256 verification**: browser `crypto.subtle.digest("SHA-256", arrayBuffer)` available without polyfill in all modern browsers. MUST verify file SHAs match manifest hashes — that's the audit-integrity contract.
5. **Memory**: bundles are typically small (<5MB) so in-memory tar extraction is fine. Reject files >50MB to avoid OOM.
6. **CORS / SSR**: the offline page MUST be `"use client"` since it uses File API + crypto.subtle.
7. **Reuse**: existing `parseManifest`, `parseReasoningTraceJsonl` from `web/lib/signed_bundle.ts` are isomorphic — usable in client and server.
8. **404 / no-backend hint**: the offline page must work even when /api/v6 is unreachable (Inspector frontend dev server alone, no FastAPI).

## §D Files I have ALSO checked and they're clean

- `web/lib/inspector_bundle_loader.ts:1-13` — explicit comment "Real-bundle backend wiring lands at I-B-08 (Seq 20); offline fallback (in-browser bundle render) at I-B-09 (Seq 21). This module is the swappable seam."
- `web/lib/signed_bundle.ts` — `parseManifest()` + `parseReasoningTraceJsonl()` are isomorphic; client-safe.
- `web/components/inspector/` — 9 components consuming `LoadedBundle`; usable from offline page.
- `web/package.json` — no existing tar/gzip dep; new deps need to be added.
- `tests/fixtures/signed_bundle/v1_canonical_success/` — 9 files; tar.gz builds cleanly via `tar -czf v1_canonical_success.tar.gz -C tests/fixtures/signed_bundle/v1_canonical_success .`.
- `web/app/inspector/[runId]/page.tsx` — server component; unchanged.
- `src/polaris_graph/audit_bundle/conformance.py` — 12-layer check (I-cd-012); browser port covers manifest + version + required-types + SHA256 verify (~6 layers); the other 6 (signature crypto, JSONL line validity, typed-JSON-schema) handled separately.

## §E Smoke test

```bash
cd web
npm install
npx playwright test inspector_offline_fallback --reporter=line
npx tsc --noEmit
```

## §F Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
