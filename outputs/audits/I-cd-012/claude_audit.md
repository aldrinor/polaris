# I-cd-012 — Claude architect audit

**Issue:** GH#608 — freeze run-data + signed-bundle fixture schema. Acceptance: "fixture schema locked; I-B-08 (#630) carries a conformance check against this schema."
**Deliverable:** 16 files / +1216 / -2 LOC. Schema freeze + Windows-safe path validator + 12-layer conformance check + canonical fixture (8 files) + 17 unit tests + TypeScript mirror + npm deps + deterministic regen script.
**Deps:** I-A-02 / I-cd-004 (PR #607 merged — app shell + route map locked).

## What this PR ships

### Schema freeze + pre-freeze Windows path hardening
- `src/polaris_graph/audit_bundle/bundle_schema.py` — module + class docstring freeze annotation; bump cascade documented in 8 steps (schema → conformance → fixture → manifest_builder → bundle_builder → audit_bundle_route → bundle.py → Inspector + I-B-08 + web mirror). Path validator tightened to reject backslashes + drive-qualified + UNC + rooted paths (pre-freeze security hardening; the new conformance check runs on the bundle-receiver filesystem and would inherit the gap on Windows).
- `src/polaris_graph/audit_bundle/REVIEWER_README.md` — schema-freeze footer with the bump cascade.

### Conformance check (the I-B-08 public-API contract)
- `src/polaris_graph/audit_bundle/conformance.py` NEW — `check_bundle_conformance(extracted_dir: Path) → ConformanceResult` validates 12 layers: (1) manifest.yaml → BundleManifest parse; (2) bundle_version == "1.0"; (3) manifest.yaml.asc present + non-empty; (4) all 6 required ContentTypes present (>=1 FileEntry each); (5) every path resolves under extracted_dir via `is_relative_to` (belt-and-suspenders against Pydantic-validator bypass); (6) every path exists; (7) actual SHA256 matches; (8) actual size matches; (9-11) typed JSON payloads parse to ScopeDecision / EvidencePool / VerifiedReport; (12) reasoning_trace.jsonl every non-empty line is a valid JSON object.

### Canonical fixture
- `tests/fixtures/signed_bundle/v1_canonical/` (8 files): manifest.yaml + manifest.yaml.asc + scope_decision.json + evidence_pool.json + verified_report.json + metadata.json + reasoning_trace.jsonl + sources/src_v1_canonical_0001.txt.
- `tests/fixtures/signed_bundle/README.md` — fixture purpose + regen methodology + SHA256 calculation.
- `scripts/regen_signed_bundle_canonical_fixture.py` — deterministic regenerator (no clocks, no uuid4 — frozen IDs + timestamp; same run produces byte-identical output).
- `.gitignore` updated with `!tests/fixtures/signed_bundle/**` exemption (default `*.jsonl` ignore would have masked the trace fixture).

### Unit tests (17 cases)
- `tests/polaris_graph/audit_bundle/test_conformance.py` NEW — covers canonical fixture conformance + 6 path-safety negatives (backslash, drive, UNC, rooted, dot-dot, POSIX-absolute) + 9 conformance-layer failures (missing manifest / missing signature / empty signature / missing required content type / empty files list / SHA mismatch / wrong bundle_version / malformed reasoning_trace.jsonl / malformed scope_decision.json) + 1 valid-path positive.

### Frontend mirror (consumed by Inspector route I-A-03 + offline fallback I-B-09)
- `web/lib/signed_bundle.ts` NEW — mirrors BundleManifest + FileEntry + ContentType enum + BundleMetadata + ReasoningTraceRecord + `parseManifest(yamlText)` + `parseReasoningTraceJsonl(text)` + `filesByContentType(manifest, contentType)` helpers.
- `web/package.json` — explicit declaration of `js-yaml ^4.1.0` (deps) + `@types/js-yaml ^4.0.9` (devDeps) per Codex iter-2 P2.
- `web/package-lock.json` regenerated via `npm install`.

## #608 acceptance check

| Criterion | Status |
|---|---|
| "fixture schema locked" | YES — BundleManifest pinned to `Literal["1.0"]`; module + class docstring freeze annotation + REVIEWER_README footer + 8-step bump cascade documented; canonical fixture under `tests/fixtures/signed_bundle/v1_canonical/` |
| "I-B-08 carries a conformance check against this schema" | YES — `check_bundle_conformance` is the public-API contract function I-B-08 will consume; signature, return type, error codes, layers all locked at this issue |

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | 3 P1 (manifest.yaml.asc presence + required-content-type validation + reasoning_trace.jsonl filename mismatch with `manifest_builder.py:55 FILE_REASONING_TRACE`) + 2 P2 (TS JSONL handling + cross-ref audit_bundle_route.py + bundle.py) |
| 2 | RC | 1 NEW P1 (BundleManifest `_path_no_traversal` validator only rejects `/` + `..`; accepted Windows backslash + drive-qualified + UNC → conformance check would follow these unsafe paths on Windows) + 2 P2 (js-yaml dep explicit + manifest_builder.py + bundle_builder.py added to bump cascade) |
| 3 | **APPROVE** | novel_p0=0 / continuing_p0=0 / p1=0 / p2=0 / convergence_call: accept_remaining |

## Why the iter-1 + iter-2 P1 catches mattered

- **iter-1 P1 (manifest.yaml.asc)**: I had treated signature as "out of scope until operator signs" — but the bundle CONTRACT includes the signature file as a presence requirement. An unsigned bundle is not a valid v1 bundle. Without the presence check, I-B-08 could ship unsigned bundles that pass conformance. Real bug.
- **iter-1 P1 (reasoning_trace.jsonl)**: `manifest_builder.py:55` defines `FILE_REASONING_TRACE = "reasoning_trace.jsonl"`. My iter-1 brief said `.json` (singular). Without the catch, the conformance check would have looked for `.json` while real bundles ship `.jsonl` → Inspector + I-B-08 + conformance all diverge from the actual emitted filename.
- **iter-2 P1 (Windows path safety)**: the existing `_path_no_traversal` validator only checks `/` (forward slash) + `..`. On Windows, backslash is the path separator. A manifest with `path: "..\\..\\evil.txt"` would pass the validator AND the conformance check would resolve it as `extracted_dir / "..\\..\\evil.txt"` — Path.resolve() on Windows follows backslash-traversal. Combined with `pathlib.Path.is_relative_to`, this could either give false positives (path looks under bundle but actually escaped) or miss real escapes. Pre-freeze tightening was the right call: post-freeze it would have been a SemVer-breaking change.

## Risk surface

- **Schema freeze**: binding promise post-merge. Bump cascade documented in 2 places (bundle_schema.py docstring + REVIEWER_README footer).
- **Conformance contract**: function signature, return type, error codes become public API consumed by I-B-08.
- **Path validator tightening**: existing valid fixtures unaffected (verified — 108 passed + 4 skipped in full audit_bundle suite). Pre-existing tests/fixtures used only forward-slash paths.
- **js-yaml dependency**: ubiquitous, well-typed (@types/js-yaml exists), low-risk.
- **Fixture determinism**: regen script uses frozen IDs + timestamp; same run → byte-identical output → SHA256s never drift.

## Smoke

| Check | Result |
|---|---|
| `pytest tests/polaris_graph/audit_bundle/test_conformance.py` | **17 passed** |
| `pytest tests/polaris_graph/audit_bundle/` (full audit_bundle regression) | **108 passed + 4 skipped (zero regression from path validator tightening)** |
| `pytest tests/crown_jewels/test_cj_001_two_family_segregation.py` | **5 passed** |
| Canonical fixture round-trip via `check_bundle_conformance` | **valid=True** |
| `cd web && npm install` | **clean (js-yaml + @types/js-yaml installed)** |
| `cd web && npx prettier --write lib/signed_bundle.ts` | clean (formatter touched lines 142-143, no semantic change) |
| `cd web && npm run typecheck` | **clean (0 errors)** |
| `cd web && npm run lint` | clean (3 pre-existing warnings unrelated to signed_bundle.ts) |
| `cd web && npm run format:check` | pre-existing 192-file format debt (NOT from signed_bundle.ts) |

## Scope discipline

Out of scope per breakdown + Codex iter-3 explicit accept_remaining:
- Inspector route rebuild → I-A-03 (Seq 13).
- Real-run bundle emitter → I-B-08 (Seq 20). I-cd-012 ships the schema + conformance; I-B-08 produces conforming bundles.
- GPG cryptographic verification (`gpg --verify`) → operator/reviewer tooling, NOT the pre-sign emitter check.
- Field additions / new ContentTypes → forbidden post-freeze without bump cascade.
- bundle_builder.py / manifest_builder.py / audit_bundle_route.py / bundle.py modifications → read-only references; their docstrings could back-reference the freeze but widening the PR is unnecessary.
