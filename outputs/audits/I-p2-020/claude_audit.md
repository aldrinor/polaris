# Claude architect audit — I-p2-020 (#759): audit / export page

## Scope
#759 = "Page: Audit / export (signed package + manifest + audit log; dense-table
gates)". New chromeless route `/runs/[runId]/audit` — the COMPLIANCE/EXPORT
artifact, deliberately distinct from `/inspector/[runId]` (the evidence
explorer). Deep-linked from `/runs/[runId]`. 3 files; the bulk is one new
`page.tsx`.

## Data source (LAW II)
Server component on `loadBundle(runId)` → `LoadedBundle` — the SAME proven
loader the inspector page + `/api/inspector_bundle/[runId]/route.ts` use. Every
field is fully typed (`BundleManifest`, `BundleMetadata`, `FileEntry`,
`VerifiedReportShape`). NO fabricated fields. The richer per-gate audit log
(`AuditIrRun` via `GET /api/inspector/runs/{id}`) was deliberately NOT used: it
is referenced by zero frontend code, so its liveness can't be proven without the
heavy v6 backend (forbidden in autonomous loops per §8.4). Building the dense
gate-table on an unverified endpoint would risk LAW II → captured as a
documented follow-up.

## What the page shows (all real)
- **Integrity & provenance**: bundle_id, schema, POLARIS version, generator +
  evaluator models (two-family), created-at, and an HONEST signature pill —
  presence-only ("Detached signature present · verify with gpg" when an .asc is
  present; "Integrity manifest present · GPG signature pending" otherwise). Never
  claims cryptographic signing the page hasn't verified.
- **Pipeline gate ledger** (dense table): pipeline verdict, strict-verify
  overall (rate vs threshold), two-family segregation (conditional detail), and
  per-section verify rates. Sentence counts use `verifier_pass === true` (passed
  of attempted), not array length.
- **Integrity manifest** (dense table): every FileEntry — path, content_type,
  size, SHA-256 (full hash on `title`).
- **Export**: download the bundle contents as JSON (convenience snapshot, NOT
  the byte-preserving signed package) + open in Inspector. Copy explicitly
  defers byte-preserving `.tar.gz` + `gpg --verify` + per-file re-hash to the
  sovereign signer (not yet live).

## §-1.1 / honesty discipline
Codex's 4-iteration line-by-line review caught FOUR real honesty/correctness
issues, all fixed:
1. (i1 P1) The JSON download can't be re-hashed against the manifest SHA-256s →
   reworded so the page never promises offline hash verification of that export.
2. (i1 P2) Two-family detail hardcoded "≠" even when the gate failed → conditional.
3. (i2 P1) `verified_sentences.length` includes dropped sentences → count
   `verifier_pass === true` (passed of attempted).
4. (i3 P1) `signaturePresent` is presence-only (a fixture has a placeholder .asc
   stub) → "present · verify with gpg", never "GPG-signed".
Plus (i3 P2) a nested-`<main>` landmark fix on the null-bundle path.
This is exactly the class of overclaim §-1.1 exists to catch.

## Staled-consumer / adjacency scan
- All imported types verified present + exact field names (no fabrication).
- State tokens `text-verified`/`bg-verified/10`/`border-verified`/`text-refusal`
  confirmed in globals.css.
- Chromeless regex anchored (`$`) — only `/runs/<id>/audit`.
- `BundlePendingCta` renders its own `<main>` (verified) — null path no longer
  double-nests.
- 1 `<header>` + 1 `<main>` confirmed on BOTH the loaded and null paths in the
  standalone harness.

## 200-LOC cap
Diff ~350 net additions, over 200. **Exemption: one atomic new TIER-3 page**
(~340 lines = the single new page.tsx; the other two files are a 6-line
chromeless add + an 8-line deep-link). Consistent with prior Phase-2 page builds
(#761 dashboard 668 lines). Codex was asked to validate the size and APPROVE'd.

## Verification
`npm run typecheck` clean; `npm run build` Compiled successfully; `npm run lint`
0 errors. Screenshot-verified @1366 against the real canonical bundle
(v1-canonical-success): real tirzepatide provenance, honest signature-pending
pill, gate ledger "8 of 8 sentences span-verified" + per-section "2/2 passed",
integrity manifest with real SHA-256s, export actions. Null path verified too.

## Verdict
Codex DESIGN+DIFF: **APPROVE at iter 4**, zero P0/P1, MERGE AUTHORIZED.
