# Codex BRIEF review — I-p2-009 (#748): sovereignty proof panel + signed-bundle mark

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task
A reusable **sovereignty proof panel + signed-bundle mark** — surfaces POLARIS's sovereignty + integrity story as VERIFIABLE facts (not a marketing badge).

## Verified current state (grounded — REAL fields only; HONESTY is P0-critical here)
- Sovereign mark wording already in shell (app_shell.tsx:50,52): "Canadian AI processing · public-source retrieval via logged Canadian egress · no external AI vendor" — HONEST (NOT air-gapped; public sources fetched via logged Canadian egress). Reuse this exact framing.
- Real signed-bundle data (signed_bundle.ts): BundleMetadata {polaris_version, generator_model, evaluator_model, bundle_created_at_utc, schema_version "1.0"}; BundleManifest {bundle_id, decision_id, pool_id, report_id, generator_model, polaris_version, files[] each with sha256, bundle_created_at_utc}.
- There is NO top-level cryptographic SIGNATURE field in the manifest — integrity is content-addressed (per-file sha256 in the manifest). So the mark is "integrity-hashed / tamper-evident" — do NOT claim "cryptographically signed" unless a signature is explicitly passed in.
- Two-family invariant: generator_model vs evaluator_model are different lineages (existing family_segregation_badge.tsx renders this).
- #742 tokens; copy discipline: "verified provenance"/"integrity-hashed", NEVER "guaranteed true"/"cryptographically signed" without a real signature.

## Acceptance criteria (diff implements; brief reviews the plan)
1. `web/components/sovereignty/sovereignty_panel.tsx`: props = metadata (generator_model, evaluator_model, polaris_version, bundle_created_at_utc) + OPTIONAL manifest (bundle_id, files for the integrity hash) + OPTIONAL signature (rendered as "cryptographically signed" ONLY when present).
2. Renders three honest sections: (a) Sovereignty — the exact shell wording (Canadian processing, logged egress, no external AI vendor); (b) Two-family — generator vs evaluator model (different lineages); (c) Bundle integrity — bundle_id, schema 1.0, created_at, polaris_version, + "integrity-hashed (N files, sha256)" or, if signature passed, "cryptographically signed".
3. HONESTY: render only fields present; NO "cryptographically signed" without a signature; NO "air-gapped"; NO fabricated counts. Missing fields omitted.
4. Frontier-Minimal (white, Canada-red, mono for ids/hashes); WCAG 2.2 AA.

## Files I have ALSO checked and they're clean
- web/lib/signed_bundle.ts (BundleManifest/BundleMetadata real fields), web/components/inspector/family_segregation_badge.tsx (two-family render to reuse/mirror), web/components/app_shell.tsx (the honest sovereign wording), web/app/globals.css (#742 tokens).

## Review focus
1. HONESTY (P0/P1 if violated): any overclaim — "cryptographically signed" without a signature, "air-gapped", fabricated hash/count? The mark must match what the bundle actually proves (content-addressed integrity).
2. Real-field grounding (no invented manifest fields)?
3. Two-family render correct (generator vs evaluator lineage)? a11y/tokens.
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```

---
## iter-2 corrections (all iter-1 findings folded)
- **P1 (two-family honesty):** add prop `familySegregationPassed?: boolean` (from verified_report.family_segregation_passed — the real source of truth). The two-family section ALWAYS shows the raw generator + evaluator model NAMES, but asserts "Two-family invariant verified" (green/verified token) ONLY when familySegregationPassed === true; when undefined → show model names with NO pass claim; when false → show an honest "not verified" state. NEVER infer "different lineages passed" from two names alone.
- **P2 (schema source):** the bundle-version/schema label comes from metadata.schema_version (or manifest.bundle_version) and is rendered ONLY when that field is present — do NOT hardcode "1.0" or import BUNDLE_VERSION as if it were the bundle's own value.
Re-confirm APPROVE or list only true remaining P0/P1.
