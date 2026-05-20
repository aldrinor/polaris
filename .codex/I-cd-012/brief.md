HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Generator (active runtime)**: `deepseek/deepseek-v4-pro` (per I-cd-009).
- **Evaluator (active runtime)**: `google/gemma-4-31b-it` (per I-cd-005-followup).
- **Bundle schema SoT**: `src/polaris_graph/audit_bundle/bundle_schema.py` (`BundleManifest`, `BUNDLE_VERSION = "1.0"`).
- **Real reasoning trace filename**: `reasoning_trace.jsonl` (per `manifest_builder.py:55`).
- **Bundle contents** (per `bundle_builder.py` + `audit_bundle_route.py` + `manifest_augment.py`): manifest.yaml + manifest.yaml.asc + scope_decision.json + evidence_pool.json + verified_report.json + sources/<id>.txt + metadata.json + reasoning_trace.jsonl.
- **Windows path safety** (iter-2 P1): backslashes, drive-qualified, UNC paths MUST be rejected by BundleManifest validators (NOT just `/` + `..`).

# Codex brief review — I-cd-012 / GH#608

Closes #608. Acceptance: "fixture schema locked; I-B-08 (#630) carries a conformance check against this schema."

## §0 — Iter trajectory + final fold-in

- **iter 1** RC: 3 P1 (manifest.yaml.asc presence + required-content-type validation + reasoning_trace.jsonl filename) + 2 P2 (TypeScript JSONL handling + cross-reference active producer/consumer).
- **iter 2** RC: 1 NEW P1 (BundleManifest `_path_no_traversal` validator allows Windows backslash/drive/UNC paths — security hole that the new conformance check would inherit) + 2 P2 (declare js-yaml dependency explicitly in web/package.json + add manifest_builder.py + bundle_builder.py to the bump cascade).
- **iter 3** (this iter): all 4 distinct P1 + 4 P2 folded.

**iter-2 P1 (Windows path safety)**: `bundle_schema.py:71-79` `_path_no_traversal` only checks `v.startswith("/")` and `".." in v.split("/")`. The new conformance check resolving `extracted_dir / entry.path` on Windows would happily follow `..\\x.txt` (backslash separator) or `C:\\POLARIS\\x.txt` (drive) and read files outside the extracted bundle, masking a malformed/malicious manifest. Tightening this BEFORE the v1.0 freeze is a one-time clean-slate fix; tightening AFTER would be a SemVer-breaking change.

Resolution (3 layers, defense-in-depth):
- (1) Tighten `FileEntry._path_no_traversal` to reject:
  - any backslash `\\` anywhere in the string
  - drive-qualified paths matching `^[A-Za-z]:`
  - UNC paths starting with `\\\\`
  - rooted paths (already `/`-only check; extend to all rooted indicators)
- (2) Add a unit test verifying each rejection case.
- (3) `check_bundle_conformance` additionally resolves each `extracted_dir / entry.path` and verifies `resolved.resolve().is_relative_to(extracted_dir.resolve())` before reading — belt and suspenders against any Pydantic gap.

## §A — Final scope: 7 files modified + 9 fixture files new + 2 new modules

**1. Schema freeze + Windows-safe path validator + freeze docstring:**

| # | File | Change |
|---|---|---|
| 1 | `src/polaris_graph/audit_bundle/bundle_schema.py` | (a) Tighten `_path_no_traversal` to reject backslashes + drive-qualified + UNC + rooted. (b) Module + class docstring freeze annotation v1.0 per I-cd-012 referencing the FULL bump cascade: `bundle_schema.py` + `conformance.py` + fixture + `manifest_builder.py` + `bundle_builder.py` + `audit_bundle_route.py` + `bundle.py` + `Inspector route` + `I-B-08 emitter` + `web/lib/signed_bundle.ts`. |
| 2 | `src/polaris_graph/audit_bundle/REVIEWER_README.md` | Freeze footer + full bump cascade list. |

**2. Conformance check (with belt-and-suspenders path resolution check):**

| # | File | Change |
|---|---|---|
| 3 | `src/polaris_graph/audit_bundle/conformance.py` (NEW) | `check_bundle_conformance(extracted_dir: Path) -> ConformanceResult`. Validates: (a) manifest.yaml parses to BundleManifest; (b) BUNDLE_VERSION == "1.0"; (c) manifest.yaml.asc presence + non-empty; (d) all 6 required content types present (>=1 FileEntry each: scope_decision, evidence_pool, verified_report, metadata, source_snapshot, reasoning_trace); (e) every files[*].path resolves under extracted_dir via `is_relative_to` AND exists; (f) every actual SHA256 matches manifest; (g) sizes match; (h) scope_decision.json parses to ScopeDecision; (i) evidence_pool.json parses to EvidencePool; (j) verified_report.json parses to VerifiedReport; (k) reasoning_trace.jsonl parses as JSONL (every line valid JSON object). Returns `ConformanceResult(valid: bool, errors: list[ConformanceError])` with structured error codes. |

**3. TypeScript frontend mirror (explicit dependency declaration):**

| # | File | Change |
|---|---|---|
| 4 | `web/lib/signed_bundle.ts` (NEW) | Mirrors BundleManifest + FileEntry + ContentType enum + BundleMetadata + ReasoningTraceRecord + `parseReasoningTraceJsonl(text: string): ReasoningTraceRecord[]` + `parseManifest(yaml: string): BundleManifest` (uses js-yaml). |
| 5 | `web/package.json` | Add `js-yaml` to dependencies + `@types/js-yaml` to devDependencies. |
| 6 | `web/package-lock.json` | Lock file regenerated. |

**4. Canonical fixture directory (9 files; reasoning_trace.JSONL, not .json):**

| # | File | Change |
|---|---|---|
| 7 | `tests/fixtures/signed_bundle/v1_canonical/manifest.yaml` (NEW) | BundleManifest YAML with 6 content files; SHA256s precomputed |
| 8 | `tests/fixtures/signed_bundle/v1_canonical/manifest.yaml.asc` (NEW) | Placeholder PGP armored signature; conformance enforces presence + non-empty only |
| 9 | `tests/fixtures/signed_bundle/v1_canonical/scope_decision.json` (NEW) | Real-shape ScopeDecision |
| 10 | `tests/fixtures/signed_bundle/v1_canonical/evidence_pool.json` (NEW) | Real-shape EvidencePool |
| 11 | `tests/fixtures/signed_bundle/v1_canonical/verified_report.json` (NEW) | Real-shape VerifiedReport |
| 12 | `tests/fixtures/signed_bundle/v1_canonical/metadata.json` (NEW) | polaris_version + generator_model + evaluator_model + timestamps |
| 13 | `tests/fixtures/signed_bundle/v1_canonical/reasoning_trace.jsonl` (NEW) | JSONL (line-delimited JSON), 2+ records |
| 14 | `tests/fixtures/signed_bundle/v1_canonical/sources/<sha-id>.txt` (NEW) | One source snapshot |
| 15 | `tests/fixtures/signed_bundle/README.md` (NEW) | Fixture purpose + regen methodology + SHA256 calculation |

**5. Unit tests:**

| # | File | Change |
|---|---|---|
| 16 | `tests/polaris_graph/audit_bundle/test_conformance.py` (NEW) | Covers: (a) canonical fixture conforms (`valid=True`); (b) missing manifest.yaml.asc → fail MISSING_SIGNATURE; (c) missing scope_decision file → fail MISSING_REQUIRED_CONTENT_TYPE; (d) empty files list → fail; (e) SHA256 mismatch → fail; (f) wrong BUNDLE_VERSION → fail; (g) malformed reasoning_trace.jsonl → fail; (h) malformed scope_decision.json → fail with structured error; (i) **path-traversal: `..\\..\\evil.txt` rejected at BundleManifest parse**; (j) **drive-qualified `C:\\evil` rejected**; (k) **UNC `\\\\server\\share\\x` rejected**; (l) **resolved path outside extracted_dir → fail at conformance even if validator was bypassed** (belt-and-suspenders). |

## §B — What this PR does NOT do

- **Inspector route rebuild** — I-A-03 (Seq 13).
- **Real-run bundle emitter** — I-B-08 (Seq 20).
- **GPG signature cryptographic verification** — full `gpg --verify` belongs to the operator-side verifier, not the conformance utility (which runs at bundle emission before the operator key signs).
- **`BundleManifest` field additions / new ContentType** — forbidden post-freeze without bump cascade. The Windows-safe path validator tightening is the LAST pre-freeze hardening; it makes invalid paths invalid without breaking valid paths.
- **Raw pipeline run-data shape freeze** — `outputs/honest_sweep_r3/.../manifest.json` is the INPUT to bundle assembly, not the bundle itself.

## §C — Smoke

- `pytest tests/polaris_graph/audit_bundle/test_conformance.py` — new tests pass (including 4 path-safety negative cases).
- `pytest tests/polaris_graph/audit_bundle/` — existing test files still pass (tightened path validator does not break existing valid fixtures; if any existing test uses `\\` paths, that test was wrong + is fixed here).
- `python -c "from pathlib import Path; from src.polaris_graph.audit_bundle.conformance import check_bundle_conformance; r = check_bundle_conformance(Path('tests/fixtures/signed_bundle/v1_canonical')); assert r.valid, r.errors; print('canonical fixture conforms')"`
- `cd web && npm install && npx prettier --write lib/signed_bundle.ts && npm run lint && npm run typecheck && npm run build`

## §D — Risk surface (final)

- **Path validator tightening**: changes BundleManifest behavior to reject paths previously accepted (backslash + drive-qualified + UNC + rooted). Risk: if any pre-existing fixture or test passes such a path, it will now fail at Pydantic parse. The audit at iter 3 will identify these (none expected in tests/polaris_graph/audit_bundle/ existing fixtures, but worth verifying at smoke time).
- **Schema freeze**: binding promise post-merge; bump cascade documented in 2 places.
- **Conformance contract**: public API consumed by I-B-08.
- **js-yaml dependency**: ubiquitous, low-risk, fully typed.
- **Fixture determinism**: SHA256 calculation methodology in fixture README.

## §E — Residual question for Codex iter-3

1. Are all 4 iter-1+iter-2 P1 properly resolved?
   - manifest.yaml.asc presence-only check (no crypto) — sufficient?
   - All 6 required ContentTypes enforced — exhaustive?
   - reasoning_trace.jsonl filename — aligned with manifest_builder.py:55?
   - Windows path safety — 4 categories of rejection (backslash + drive + UNC + rooted) + belt-and-suspenders `is_relative_to` in conformance — sufficient?
2. Are the 2 iter-2 P2 properly resolved?
   - js-yaml as explicit web/package.json dependency
   - manifest_builder.py + bundle_builder.py added to the bump cascade
3. Anything else missed re: active producers/consumers OR pre-freeze hardening that needs to land in THIS issue (vs a post-freeze SemVer-bump issue)?

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
