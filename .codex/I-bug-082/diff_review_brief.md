# Codex Diff Review — I-bug-082 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-bug-082 — audit-bundle health endpoint hardcoded sentinel
**Brief:** APPROVED iter 1 (0/0/0P1, 1 P2 hygiene)
**Canonical-diff-sha256:** `26da844abf3e69e01d5f34409473879878ba9a1d1673a4acd0f2a093cb1fab22`
**LOC:** 28 net (under CHARTER §1 200-cap by 172, under breakdown 60 budget by 32)
**Tests:** 3/3 health tests PASS

## Files

```
tests/polaris_graph/api/test_audit_bundle_route.py   EDIT +28
```

## What changed

Three additive changes to existing `test_health`:

1. **`test_health` tightened** (1 line): asserts `signing_backend == "sentinel"` (default state, no override).
2. **`test_health_with_signer_override_returns_gpg` (NEW)**: uses existing `_override_sign(app)` helper to bind a stub sign_fn via `app.dependency_overrides`; asserts `signing_backend == "gpg"`.
3. **`test_health_env_var_drives_signing_backend_via_create_app` (NEW)**: `monkeypatch.setattr(gpg_mod, "build_gpg_signer", lambda: _StubSigner())` THEN `monkeypatch.setenv("POLARIS_GPG_KEY_ID", "test-key-id")` THEN `from polaris_v6.api.app import create_app; v6_app = create_app()`. Asserts `signing_backend == "gpg"`. The patch order is critical: build_gpg_signer must be patched BEFORE create_app() reads the env var (Codex iter-1 P2 #1 hygiene addressed).

## Risks for Codex Red-Team

1. **Patch order.** `build_gpg_signer` patched on module BEFORE `create_app()` import-and-call. Per Codex iter-1 P2: `src/polaris_v6/api/app.py:166` constructs a module-level app at import time, so patching after import would be too late. Brief author commits to patching first, then importing.

2. **Env-var cleanup.** `monkeypatch` automatically reverts on test teardown. `POLARIS_BENCHMARK_RESULTS_DIR` explicitly delenv'd to avoid wiring an unrelated benchmark router that would change response shape.

3. **`_StubSigner.sign` returns valid bytes.** Real signer is dependency-injected via the existing `_inject_real_signer = lambda: _real_signer.sign`. Stub provides a `.sign` method matching that interface.

4. **§9.4 compliance.** `monkeypatch` is pytest stdlib (not unittest.mock — which is forbidden in src/ but allowed in tests/ anyway). No magic numbers.

5. **No production-code change.** The endpoint logic at `audit_bundle_route.py:228-249` was already correct. This Issue is bug-coverage, not bug-fix.

6. **CHARTER §1 LOC cap.** 28 net.

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
