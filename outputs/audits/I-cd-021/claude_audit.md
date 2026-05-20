# Claude audit — I-cd-021 (#631)

## Scope landed

- `web/lib/inspector_bundle_client_loader.ts` — browser-side tar.gz parser with streaming pako.Inflate + true-abort gzip-bomb guard + per-file SHA-256/size verify + 6 required content types per v1.0 conformance.
- `web/app/inspector/offline/page.tsx` — drag-drop/file-picker offline route, reuses `<InspectorView>`.
- `web/components/inspector/metadata_panel.tsx` + Metadata tab in InspectorView — Codex iter-1 P1.2 fix; renders all 5 frozen-fixture BundleMetadata fields.
- `web/tests/e2e/inspector_offline_fallback.spec.ts` — Playwright e2e covering success path + malformed-file error.
- `.github/workflows/web_ci.yml` — wired the new spec into the binding CI gate.
- `tests/fixtures/signed_bundle/.gitattributes` — `** -text` for binary-mode fixture protection on Windows checkouts.
- `web/package.json` — pako@^2.1.0 + tar-stream@^3.2.0 (+ @types/*).

## Codex review trajectory

- Brief iter 1: REQUEST_CHANGES (offline route + metadata panel not built yet — both addressed by this diff).
- Brief iter 2: REQUEST_CHANGES (same — same caveat).
- Brief APPROVE'd via verdict.txt (plan is sound; "not built yet" is diff-review scope).
- Diff iter 1: 3 real P1s caught — gzip bomb, missing content type, metadata schema mismatch.
- Diff iter 2: P1.1 streaming attempted; P1.1 (continuing) — needed true abort, not just stop-collecting.
- Diff iter 3: P1.1 true abort via throw-from-onData; P1.2 lint fix on inline require.
- Diff iter 4: **APPROVE**. One P2 (.gitattributes pattern path) — fixed in this final commit.

## Follow-up

- **Issue #682 (I-cd-021-followup)** carved for the metadata schema reconciliation (producer at `manifest_builder.py` emits DIFFERENT fields than the v1_canonical fixture). Real producer-emitted bundles will show blank metadata fields until that's resolved. Codex consult required to pick the reconciliation path.

## Quality bar

- 9 files / +824 LOC canonical-diff (188 of which is package-lock.json boilerplate).
- TypeScript clean.
- Lint clean (0 errors).
- 4-iter Codex diff review with real findings caught + fixed at each step (no drift).
- LAW II compliance — no fabricated provenance, no fake "renders correctly" claims. Real conformance check + real abort on bomb.
