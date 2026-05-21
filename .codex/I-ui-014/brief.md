# Codex BRIEF — I-ui-014 (#734) report = Proof Replay (CENTERPIECE) + wire report-viewable (#728)

HARD ITERATION CAP: 5. iter 1 of 5. Front-load ALL findings. P0/P1 = real execution risk / fails the Proof-Replay contract / no-synthetic-proof violation. APPROVE iff zero P0/P1.

## Goal
The product's defining page (epic #729; plan Codex-APPROVED). The report's DEFAULT experience = **Proof Replay**: read⇄audit, click any sentence → its exact source span. Closes the critical **#728** (loadBundle is fixture-only → real runs show "not ready"). The home (#731) later reuses this proof component.

## Verified facts (grounded — substrate exists)
- `web/lib/inspector_bundle_loader.ts`: `loadBundle(runId)` resolves ONLY `KNOWN_FIXTURES` (v1-canonical[-success]) → returns null for real/golden runs (= #728). `LoadedBundle { signature?, evidencePool, verifiedReport, sources }`; `VerifiedReportShape.sections[].verified_sentences[] { text?, provenance_tokens[] }`.
- `web/app/inspector/[runId]/page.tsx`: `loadBundle(runId)` → null → BundlePendingCta ("not ready"). `inspector_view.tsx` already renders: `VerifiedReportSections`, `SourcesPanel`, `EvidencePoolTable`, `signaturePresent`, tabs.
- Backend bundles: golden → `GET /api/v6/runs/{id}/bundle` (JSON EvidenceContract, 200); real → `GET /api/v6/runs/{id}/bundle.tar.gz` (signed; #631 has an offline in-browser tar.gz renderer to reuse). api.ts has span types (`span_start`/end; the `evidence_pool[start:end]` auditable slice).
- Provenance token format `[#ev:<evidence_id>:<start>-<end>]` → resolves into evidencePool[evidence_id].body[start:end] = the exact quoted span.
- Live design system = Frontier Minimal (I-ui-010 merged: blue accent, hairline, sovereign shell mark).

## Scope
1. **Wire loadBundle (closes #728):** beyond KNOWN_FIXTURES, fetch the real bundle — golden/JSON via `/runs/{id}/bundle`; real via `/runs/{id}/bundle.tar.gz` parsed client-side (reuse the #631 offline parser). Return a LoadedBundle. On 422/404/parse-fail → an honest **broken-proof state** (not a fake).
2. **Proof Replay interaction (H3 contract):** default report renders read mode (clean prose, every verified sentence subtly marked); **audit/replay** toggle. Click a sentence → lock → source document + **exact span highlighted with quote bounds** (resolve provenance_tokens → evidencePool slice) → support verdict → independent-verifier result → contradictions/dropped-claim log adjacent → **signed-bundle hash anchored to that claim**. Reuse VerifiedReportSections + SourcesPanel; add the click→span lock.
3. **Header marks:** sovereignty attestation + "Signed ✓" + claim/unverified counts. Frontier Minimal.
4. **No-synthetic-proof (binding):** every Proof-Replay element comes from a LoadedBundle typed field or renders a broken-proof state. No mocked/decorative proof.
5. Mobile: stacked sentence → source → verdict drawers.

## Acceptance
- typecheck/lint/build green; home_g1_g8 unaffected.
- SCREENSHOT-verify on a REAL seeded completed run (local stack + vision): report renders (no "not ready"), click-a-sentence→source-span works, signed/sovereign marks show. Operator visual sign-off.
- Codex diff APPROVE. No "done" without the screenshot.

## Review focus
1. loadBundle wiring: golden JSON + real signed tar.gz both → LoadedBundle; broken-proof on failure; does it correctly close #728 for real runs?
2. provenance_token → evidencePool span resolution correct (the click→exact-quote)?
3. Read⇄audit + the H3 lock contract complete + executive-readable (not a forensic debugger)?
4. No-synthetic-proof honored (every element typed-field-backed)?
5. Frontier Minimal consistent with I-ui-010; mobile drawers.
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

---
## Implementation plan (traced 2026-05-21 — exact, for a clean fresh pass)
**loadBundle wiring (closes #728):**
1. Refactor `web/lib/inspector_bundle_client_loader.ts`: extract `loadBundleFromTarGz(file)` body (lines 213→end: ungzip → _extractTarBytes → manifest parse → version/required-type checks → SHA/size verify → assemble) into `export async function loadBundleFromGzBytes(bytes: Uint8Array): Promise<LoadedBundle>`. Keep `loadBundleFromTarGz` as a thin File→bytes wrapper.
2. `web/lib/inspector_bundle_loader.ts` (server): if `!KNOWN_FIXTURES[runId]`, fetch `${INTERNAL_API_URL}/runs/{id}/bundle.tar.gz`. 200 → arrayBuffer → `loadBundleFromGzBytes` → LoadedBundle. 404/422/parse-fail → null (→ honest CTA; ideally a typed reason: not-found vs aborted/release-blocked).
3. **INTEGRATION RISK to verify:** `inspector_bundle_client_loader.ts` uses `pako` + `tar-stream` (browser build) + `crypto.subtle`. Confirm they run server-side in Next 16 RSC (node 20 has crypto.subtle; tar-stream "browser build" + pako must import cleanly in the server module — may need the node entrypoint, or move the shared parser to a runtime-neutral module). This is the main thing to smoke before building on it.

**Proof Replay (on top of the wired loader):** read⇄audit toggle in inspector_view; verified_report_sections parses `[#ev:id:start-end]` → evidencePool[id].body[start:end] → highlight in SourcesPanel on sentence-lock; bundle_header adds sovereignty + Signed✓ + claim/unverified counts; no-synthetic-proof.

**Verification (REQUIRED before "done"):** needs a real signed bundle → throwaway GPG key (POLARIS_GPG_KEY_ID) + seeded completed run + local stack (the same path used to verify #725) → screenshot the report rendering + click→span. Cannot be verified without GPG.
