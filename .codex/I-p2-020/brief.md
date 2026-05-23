# Codex DESIGN+DIFF review — I-p2-020 (#759): audit / export page

HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `8d40465ef3b0dc8c26a6513574bd83cff11f197de8a573b5ab5510f0f1762dbe`. web/ only, 3 files. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## iter-1 → iter-2 delta (all 3 findings fixed)
- **P1 (overclaim — FIXED):** you flagged that the JSON download (`/api/inspector_bundle/<runId>` → `NextResponse.json(bundle)`, parsed objects not byte-preserving files) can't be re-hashed against the manifest SHA-256s, so the copy overclaimed offline verification. Reworded: integrity-manifest copy now says the hashes are the manifest-recorded ones (real) + the GPG signature (pending) seals the manifest; export copy now says the download is a convenience JSON snapshot and that byte-preserving verification (`.tar.gz` + `gpg --verify` + per-file SHA-256 re-hash) comes from the sovereign signer, NOT yet live. No promise the JSON re-hashes.
- **P2 (≠ hardcode — FIXED):** two-family detail is now conditional — `Distinct lineages — gen ≠ eval` when passed, `Same lineage — gen, eval` when failed.
- **P2 (gate wording — FIXED):** "Every gate this run cleared" → "Gate outcomes recorded for this run" (the loader serves aborted/failing bundles too).

## iter-2 → iter-3 delta (your iter-2 P1 fixed)
- **P1 (count — FIXED):** you flagged that `verified_sentences.length` includes BOTH passed AND dropped sentences (audit completeness), overstating coverage. Now I count `verifier_pass === true`: the subtitle reads "{passed} of {attempted} sentences span-verified" and each section row reads "{passed}/{attempted} sentences passed". For the all-pass canonical bundle this renders "8 of 8" / "2/2" — verified in the standalone harness. (`VerifiedSentenceShape.verifier_pass: boolean` confirmed in inspector_bundle_loader.ts.)

## iter-3 → iter-4 delta (your iter-3 findings fixed)
- **P1 (signature overclaim — FIXED):** `signaturePresent` is only an .asc PRESENCE check (loader), not a crypto verify, and the v1_canonical fixture has a placeholder stub. Present-branch now reads "Detached signature present · verify with gpg" + a `title` pointing to offline `gpg --verify` against the published key. Never says "GPG-signed".
- **P2 (nested main — FIXED):** BundlePendingCta renders its own `<main>`, so the null-bundle path double-nested `<main>`. Restructured — only the loaded path wraps in this page's `<main>`; the null path uses the CTA's own. Verified 1 `<header>` + 1 `<main>` on BOTH paths in the standalone harness.

## 200-LOC cap exemption (please validate)
Diff is ~378 patch lines / ~350 net additions — over the 200-LOC cap. **Exemption: one atomic new TIER-3 page.** ~340 lines are the single new file `web/app/runs/[runId]/audit/page.tsx` (a dense compliance surface with two tables + small render helpers); the other two files are a 6-line chromeless-pattern add + an 8-line deep-link button. Splitting the page would fragment a cohesive UI unit with no review benefit. Consistent with prior Phase-2 page builds (#761 dashboard was 668 lines). If you judge the size a real review risk, say so; otherwise the exemption stands.

## Context
#759 = "Page: Audit / export (signed package + manifest + audit log; dense-table gates)". This is the COMPLIANCE/EXPORT artifact — **distinct from `/inspector/[runId]`** (the evidence EXPLORER: per-claim proof replay, evidence, reasoning, sources). The inspector already has Hash-chain + Metadata + Scope tabs; this page is the focused "take the proof with you" surface: provenance + gate ledger + integrity manifest + download.

## Data source (LAW II — proven-live only)
Server component on `loadBundle(runId)` → `LoadedBundle` — the SAME proven loader the inspector page AND `/api/inspector_bundle/[runId]/route.ts` use. Every field is fully typed from `signed_bundle.ts` (BundleManifest, BundleMetadata, FileEntry) + `inspector_bundle_loader.ts` (VerifiedReportShape). NO fabricated fields.

**Deliberately NOT used:** `getAuditRun` → `AuditIrRun` (`GET /api/inspector/runs/{id}`) which has the richer per-gate log (adequacy/approval/evaluator rule-checks). That endpoint is referenced by ZERO frontend code today, so I can't prove it's live without running the heavy v6 backend (forbidden in autonomous loops per §8.4). Building the dense gate-table on an unverified endpoint would risk LAW II → captured as a documented follow-up instead. The gate ledger here is composed only from the proven `verified_report`.

## Honesty (LAW II + sovereignty)
The canonical bundle ships WITHOUT `manifest.yaml.asc` (the GPG seal was deliberately deferred — operator "skip the seal, build the real proof"). So `signaturePresent` is false and the page shows exactly that: **"Integrity manifest present · GPG signature pending"** (muted pill + tooltip explaining the sovereign signer is not yet live). It NEVER claims a signature that isn't on disk. The SHA-256 integrity manifest IS real and shown.

## Diff (3 files)
1. `web/app/runs/[runId]/audit/page.tsx` (NEW): the page. Chromeless (own header + `<main data-testid="audit-export-page">`). Sections: (a) Integrity & provenance card (bundle_id, schema, version, generator+evaluator models, created-at, honest signature pill); (b) Pipeline gate ledger dense table — pipeline verdict / strict-verify overall (rate vs threshold) / two-family segregation / per-section verify rates, each a Pass/Fail pill from `text-verified`/`text-refusal` tokens; (c) Integrity manifest dense table — every FileEntry (path/content_type/size/SHA-256, full hash on `title`); (d) Export — `<a download>` to `/api/inspector_bundle/<runId>` + "Open in Inspector". `null` bundle → `BundlePendingCta` inside the chromeless header.
2. `web/components/app_shell_gate.tsx`: added `/^\/runs\/[^/]+\/audit$/` to CHROMELESS_PATTERNS (same focused-drill-down pattern as `/graph`).
3. `web/app/runs/[runId]/page.tsx`: added an "Audit & export" deep-link button in the affordances row.

## Files I have ALSO checked and they're clean
- `loadBundle` / `LoadedBundle` / `VerifiedReportShape` / `BundleManifest` / `BundleMetadata` / `FileEntry` — all imported types verified present + field names exact (no fabrication).
- State tokens `text-verified`/`bg-verified/10`/`border-verified`/`text-refusal` confirmed in `globals.css` + used by dashboard/source_card.
- `Button` `nativeButton={false}` + `render={<a/Link>}` pattern matches the graph/runs pages.
- Chromeless regex anchored (`$`) — only `/runs/<id>/audit`, not nested paths.

## Claude visual audit (standalone harness @1366, real bundle v1-canonical-success)
Chromeless verified (0 global nav, 1 own header). Renders: provenance card (real deepseek generator + google/gemma evaluator, honest "GPG signature pending" pill), gate ledger (verdict success + strict-verify 100% + two-family + 4 section rows all PASS — real data), integrity manifest (scope_decision/evidence_pool/verified_report/metadata/reasoning_trace + source snapshots with real SHA-256), download + inspector buttons. On-brand Frontier-Minimal (white, red accent on the primary download CTA, hairline tables).

## Review focus (8-dim design rubric + diff)
1. Distinct from inspector (not a duplicate of Hash-chain/Metadata tabs)? Does the "compliance/export" framing hold?
2. Honesty: signature-pending disclosure correct + never overclaims a seal? Gate ledger only from real verified_report fields?
3. Design dims: hierarchy, density (two dense tables readable?), token use (state colors ≠ national red), a11y (table semantics, chromeless landmark single header/main), responsive (overflow-x on tables).
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
