HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Generator (active runtime)**: `deepseek/deepseek-v4-pro` (per I-cd-009).
- **Evaluator (active runtime)**: `google/gemma-4-31b-it` (per I-cd-005-followup).
- **Bundle schema SoT**: `src/polaris_graph/audit_bundle/bundle_schema.py` (`BundleManifest`, `BUNDLE_VERSION = "1.0"`) — **FROZEN v1.0 at this PR**.
- **Real reasoning trace filename**: `reasoning_trace.jsonl` (per `manifest_builder.py:55`).

# Codex diff review — I-cd-012 / GH#608

## §0 — Context

Brief APPROVE'd at iter 3/5 (clean convergence; novel_p0=0, continuing_p0=0, p1=0, p2=0, convergence_call: accept_remaining). 16 files / +1216 / -2 LOC implementing the v1.0 freeze + 12-layer conformance + canonical fixture + TS mirror.

## §A — Diff summary

16 files / **+1216 / -2 / +1214 net LOC** (above 200-LOC PR cap, but justified: 8 fixture files are content data + ~280 LOC test suite + ~250 LOC conformance module + ~180 LOC TS mirror + ~180 LOC regen script; the bulk is test fixtures + tests not source code).

Per CLAUDE.md §3.0 + the breakdown's "schema locked; I-B-08 carries a conformance check": the freeze + conformance + fixture are unitary; splitting would leave the I-B-08 contract undefined.

## §B — Acceptance criteria check

| Criterion | Status |
|---|---|
| #608: "fixture schema locked" | YES — BundleManifest pinned to Literal["1.0"]; freeze docstring + REVIEWER_README footer + 8-step bump cascade documented; canonical fixture at v1_canonical/ |
| #608: "I-B-08 carries a conformance check" | YES — `check_bundle_conformance` is the public-API contract; 12 layers; structured error codes |

## §C — Smoke evidence

- `pytest tests/polaris_graph/audit_bundle/test_conformance.py` → **17 passed**
- `pytest tests/polaris_graph/audit_bundle/` (regression) → **108 passed + 4 skipped (zero regression from path-validator tightening)**
- `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` → **5 passed**
- Canonical fixture round-trips → `valid=True`
- `cd web && npm install` → clean (js-yaml + @types/js-yaml installed)
- `cd web && npx prettier --write lib/signed_bundle.ts` → clean
- `cd web && npm run typecheck` → clean (0 errors)
- `cd web && npm run lint` → clean (3 pre-existing warnings)

## §D — What this diff does NOT do (per scope discipline)

- Inspector route rebuild → I-A-03 (Seq 13).
- Real-run bundle emitter → I-B-08 (Seq 20).
- GPG `gpg --verify` cryptographic verification → operator-side tooling.
- BundleManifest field changes → forbidden post-freeze without bump cascade.

## §E — Codex Red-Team checklist for THIS diff

Reviewer please verify:
1. Path validator tightening rejects all 4 categories (backslash + drive + UNC + rooted) AND existing valid paths still parse (regression test: 108 + 4 skipped pre-existing audit_bundle tests still pass).
2. `check_bundle_conformance` correctly implements all 12 layers — no skipped layer, no double-counted error.
3. Canonical fixture is **deterministic** (regen script `scripts/regen_signed_bundle_canonical_fixture.py` produces byte-identical output every run; no `datetime.now()` / `uuid.uuid4()`).
4. `manifest.yaml.asc` presence-only check (NO `gpg --verify`) is the right line — does NOT require crypto verification at conformance time (real bundles get signed by the operator key after conformance passes at I-B-08).
5. `reasoning_trace.jsonl` filename matches `manifest_builder.py:55 FILE_REASONING_TRACE`.
6. TypeScript mirror covers BundleManifest envelope + ReasoningTraceRecord JSONL shape; defers content-type detail rendering to the Inspector route.
7. `web/package.json` + `web/package-lock.json` regenerated cleanly; js-yaml + @types/js-yaml correctly declared.
8. `.gitignore` exemption for `tests/fixtures/signed_bundle/**` correctly overrides the default `*.jsonl` ignore so the fixture trace ships.
9. No accidental file additions beyond the 16-file scope.
10. Bump cascade docs are accurate AND mention all 8 steps (schema + conformance + fixture + manifest_builder + bundle_builder + audit_bundle_route + bundle.py + Inspector + I-B-08 + web mirror).

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
