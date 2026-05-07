# Codex Brief Review — I-bug-082 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-bug-082 — audit-bundle health endpoint hardcoded sentinel (reissued)
**Phase:** 1 / **Feature:** F15 follow-up
**LOC budget:** 60 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: `/api/audit-bundle/health` uses `Depends(get_sign_fn)`. Acceptance: health test with `POLARIS_GPG_KEY_ID` returns `signing_backend: gpg`.

## Substrate (HONEST at HEAD — verified iter 1)

- `src/polaris_graph/api/audit_bundle_route.py:228-249` — `get_audit_bundle_health(sign_fn: SignFn | None = Depends(get_sign_fn))` returns `{"signing_backend": "gpg" if sign_fn is not None else "sentinel"}`. So when the dep override is wired (POLARIS_GPG_KEY_ID set), `sign_fn` becomes the real signer and `signing_backend` is "gpg".
- `src/polaris_v6/api/app.py:131-139` — when `POLARIS_GPG_KEY_ID` is set in env, the v6 app builds a real GPGSigner and binds via `app.dependency_overrides[slice004_get_sign_fn] = _inject_real_signer`.
- `tests/polaris_graph/api/test_audit_bundle_route.py:143` `test_health` — currently asserts only `slice` and `pipeline_stages`. Does NOT assert `signing_backend` value. Does NOT exercise the dep-override path.

## Problem

The endpoint logic is correct, but no test pins the `signing_backend: gpg` behavior when the dep override is wired. A regression that breaks the dep-override path (e.g. typo in the env-var name in app.py) would silently downgrade production to `signing_backend: sentinel` while POSTs to `/audit-bundle` still 503 — operators wouldn't notice via the health probe alone. The test gap IS the bug.

## Approach

**Part 1 — `tests/polaris_graph/api/test_audit_bundle_route.py`** (EDIT, ~25 LOC):
- Extend `test_health` to assert `signing_backend == "sentinel"` when no override is wired (tightens existing test).
- Add `test_health_with_signer_override_returns_gpg` that uses `app.dependency_overrides[get_sign_fn] = lambda: <stub>` to simulate POLARIS_GPG_KEY_ID-bound state, then asserts `signing_backend == "gpg"`.
- Add `test_health_env_var_drives_signing_backend` that builds the v6 app via `create_app()` after setting `POLARIS_GPG_KEY_ID` env var (uses `monkeypatch.setenv` + monkeypatch to avoid actually invoking gpg keyring — patches `build_gpg_signer` to return a stub). Asserts `signing_backend == "gpg"`.

**Part 2 — `src/polaris_v6/api/app.py`** (EDIT if needed):
- No production change needed; existing logic at line 131 correctly checks env var. Brief author commits to verifying via test that the env-var-bound path works end-to-end.

## Acceptance criteria (binding)

1. `tests/polaris_graph/api/test_audit_bundle_route.py` extended with 2 new tests (~50 LOC) + tighten existing test_health (~3 LOC).
2. NO production-code changes (the endpoint logic is correct at HEAD; this Issue is bug-coverage, not bug-fix).

## Planned diff shape

```
tests/polaris_graph/api/test_audit_bundle_route.py   EDIT +55
```

LOC: +55 net. Under breakdown 60 budget by 5; under CHARTER §1 200-cap by 145.

## Out of scope

- Refactoring the dep-override pattern → current pattern is canonical (Depends + dependency_overrides is the FastAPI idiom).
- Adding a `signing_backend_detail` field with key fingerprint → out of scope.

## Risks for Codex Red-Team

1. **`monkeypatch.setenv` + create_app() pattern.** Per existing v6 app.py logic, env var is read at app construction time. Test must set env BEFORE calling `create_app()`. Brief author commits to using `monkeypatch.setenv("POLARIS_GPG_KEY_ID", "test-key-id")` THEN `create_app()`.

2. **Patching `build_gpg_signer`.** To avoid invoking real gpg in tests, patch `polaris_graph.audit_bundle.gpg_signer.build_gpg_signer` to return a stub object with `.sign` callable. Per CLAUDE.md §9.4, `unittest.mock` is forbidden in `src/` but allowed in `tests/`. Brief author uses `monkeypatch.setattr` (pytest stdlib) instead of `unittest.mock` for cleanliness.

3. **`app.dependency_overrides` cleanup.** Per FastAPI docs, dependency_overrides persist across requests on the same app instance. Each test creates a fresh app via the existing `app` fixture; no cross-test pollution.

4. **§9.4 compliance.** No mocks (monkeypatch is pytest stdlib, not unittest.mock). No magic numbers. No `try: pass`. No TODO/FIXME.

5. **CHARTER §1 LOC cap.** 55 net.

6. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
