HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-021 (#631) — Offline Inspector

Brief APPROVE'd iter 2. Iter-1 + iter-2 fixes applied. Canonical-diff-sha256: `f9da55f2dabf91da0c7ddb29ca002247a99e950494c56afab4ee53c990898c53`.

**Iter-2 fix (P1.1 streaming):** Refactored from one-shot `pako.ungzip()` to streaming `pako.Inflate`.

**Iter-3 fixes:**
- P1.1 (true abort): onData now THROWS `_GzipBombAbort` when cumulative bytes exceed cap. The throw propagates out of `inflator.push` and is caught locally — pako stops decompressing immediately, not just stops collecting (the iter-2 stop-collecting code still let pako process the rest of the stream).
- P1.2 (lint): replaced inline `require('node:fs')` in the Playwright spec with a static `import { writeFileSync } from 'node:fs'`. Lint passes (0 errors).

Canonical-diff-sha256: `5633064dbe6ee6fcc22ba58cf73b1ad08aa3759b9dceb41574b50c8f4324292f`.

**Iter-1 fixes:**
- P1.1 (gzip bomb): `MAX_DECOMPRESSED_BYTES = 200 MB` checked AFTER `pako.ungzip` — prevents 50MB compressed → 50GB decompressed OOM.
- P1.2 (missing required content type): added `source_snapshot` to `REQUIRED_CONTENT_TYPES` — now 6 types matching `_REQUIRED_CONTENT_TYPES` in `src/polaris_graph/audit_bundle/conformance.py:70-78`.
- P1.3 (metadata schema mismatch producer vs fixture): carved to follow-up Issue **#682**. Producer at `manifest_builder.py:196-213` emits different field names than the v1_canonical fixture; both schemas need reconciliation. Out of scope for this PR.
- P2.1 (CI wiring): added `run_e2e_inspector_offline_fallback` step to `.github/workflows/web_ci.yml`.
- P2.2 (Windows CRLF/LF fixture): added `tests/fixtures/signed_bundle/.gitattributes` with `** -text` to prevent line-ending translation that would invalidate SHA hashes.

## §A Canonical diff summary

**New code (~559 net LOC):**
- `web/lib/inspector_bundle_client_loader.ts` (NEW, 271 LOC) — `loadBundleFromTarGz(file: File): Promise<LoadedBundle>` via pako (gzip) + tar-stream. Verifies tar.gz size ≤ 50MB, manifest.yaml parses, `bundle_version == "1.0"`, all 5 required content types present, every declared file present in tar, SHA-256 + size match for every manifest entry.
- `web/app/inspector/offline/page.tsx` (NEW, 129 LOC) — client component with drag-drop + file picker; on load reuses `<InspectorView>` (the same component used by `/inspector/[runId]`). WCAG: dropzone is `role="button"` + `tabIndex={0}` + Enter/Space keyboard activation + aria-label.
- `web/components/inspector/metadata_panel.tsx` (NEW, 59 LOC) — surfaces all 5 BundleMetadata fields (polaris_version, generator_model, evaluator_model, bundle_created_at_utc, schema_version). Fixes Codex iter-1 P1.2.
- `web/app/inspector/[runId]/inspector_view.tsx` (MOD, +5 LOC) — adds "Metadata" tab to the existing route (so the metadata panel surfaces on BOTH /inspector/[runId] AND /inspector/offline).
- `web/tests/e2e/inspector_offline_fallback.spec.ts` (NEW, 91 LOC) — Playwright e2e: builds tar.gz from `tests/fixtures/signed_bundle/v1_canonical_success/` at setup, drops it via the file input, asserts InspectorView mounts + Metadata tab renders all 5 fields with non-empty values + no error card. Second test: malformed file → visible error card.
- `web/package.json` + `web/package-lock.json` — new deps `pako@^2.1.0`, `tar-stream@^3.2.0`, `@types/pako`, `@types/tar-stream`.

## §B Acceptance check

| Criterion | Met by |
|---|---|
| Inspector renders v1.0 bundle without backend running | offline/page.tsx + inspector_bundle_client_loader.ts |
| Same `<InspectorView>` component used (no duplicate renderer) | offline/page.tsx:55 imports InspectorView |
| `LoadedBundle` shape identical to server loader | `import type { LoadedBundle } from "@/lib/inspector_bundle_loader"` |
| SHA-256 verify every file vs manifest | _sha256Hex + entry.sha256 check per file |
| Size verify every file vs manifest | candidate.bytes.length === entry.size_bytes check |
| Bundle version=1.0 enforced | inspector_bundle_client_loader.ts:170 |
| 5 required content_types present | inspector_bundle_client_loader.ts:128-134 + 176-183 |
| signaturePresent: detects manifest.yaml.asc | inspector_bundle_client_loader.ts:255 |
| GPG cryptographic verify explicitly out-of-scope (documented) | offline/page.tsx:75-77 + loader docstring |
| WCAG: dropzone keyboard-accessible | role=button, tabIndex=0, Enter/Space, aria-label, focus-visible:ring |
| Metadata panel renders all 5 fields | metadata_panel.tsx + 5 data-testid attrs |
| Playwright e2e covers success + malformed-file error path | inspector_offline_fallback.spec.ts |
| No backend / API call on the offline path | page.tsx is "use client", no /api/ fetch |
| TypeScript clean (`npx tsc --noEmit` rc=0) | confirmed locally |
| 50MB file size limit prevents OOM | MAX_TAR_GZ_BYTES = 50 \* 1024 \* 1024 |

## §C Red-team checklist

1. **pako vs tar-stream** — pako handles gzip (mature, browser-tested, GitHub uses it); tar-stream is the standard Node tar parser. `tar-stream@3.x` is browser-build-compatible via Webpack/Next bundling.
2. **SHA-256 verification** — uses `crypto.subtle.digest("SHA-256", ...)` (browser-native since 2016). Result is base16 hex matching the manifest hash format.
3. **ArrayBuffer typing** — `bytes.buffer.slice(...)` ensures we pass `ArrayBuffer` (not `SharedArrayBuffer`) per TypeScript's strict BufferSource check.
4. **`_findFile` suffix-match** — handles both `tar -czf bundle.tar.gz <dir>` (entries prefixed with `<dir>/`) and `tar -czf bundle.tar.gz -C <dir> .` (entries without prefix).
5. **Filename traversal safety** — `_findFile` does NOT use the entry name directly for fs access (we're in-browser); manifest declares paths; no traversal vector.
6. **`runId` derivation** — `BundleMetadata` does not carry run_id in the v1.0 frozen schema; falls back to filename stem. Documented in loader.
7. **Tab IDs** — added "metadata" tab. Existing Tabs component uses `value=` keys; no collision.
8. **MetadataPanel data-testid** — 5 specific testids let Playwright assert each field individually.
9. **`InspectorView` import from offline/** — page.tsx imports `@/app/inspector/[runId]/inspector_view`. Next.js App Router permits this; component is "use client" already.
10. **Error code surfacing** — `BundleClientLoaderError.code` ("ungzip_failed", "manifest_missing", "sha256_mismatch", etc.) is included in the error card for debugging.

## §D Files I have ALSO checked and they're clean

- `web/lib/inspector_bundle_loader.ts:13-32` — server loader's `LoadedBundle` interface is the shared contract; client loader matches.
- `web/lib/signed_bundle.ts` — `parseManifest`, `parseReasoningTraceJsonl`, `BundleMetadata` are isomorphic; no node-only deps.
- `web/components/inspector/` — 9 existing components; no breakage.
- `web/components/ui/tabs.tsx` — wraps `@base-ui/react/tabs`; supports any number of tabs.
- `web/next.config.ts` — pako + tar-stream get bundled by Next.js webpack; no special config needed.
- `tests/fixtures/signed_bundle/v1_canonical_success/` — used as the test bundle source.
- `.codex-tmp/i-cd-021-bundles/` — gitignored; e2e setup builds the tar.gz here.

## §E Smoke test

```bash
cd web && npx tsc --noEmit  # rc=0 confirmed
cd /c/POLARIS && wc -l .codex/I-cd-021/codex_diff_canonical.patch  # 915 lines (188 of which is package-lock)
```

Playwright e2e requires `next dev` server running on port 3737 + the fixture bundle building — runs in CI workflow `web_ci.yml` against a built/started Next.js production server, so cannot be smoke-tested headless on Windows in this dev shell. Codex runs `web_ci.yml` as the binding gate.

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
