# Claude architect audit — I-rdy-008

**Issue:** #504 / I-rdy-008 — wire live runs into the rich UI (Phase 3.5)
**Branch:** `bot/I-rdy-008-live-run-rich-ui` @ `7b4c441b` (off `polaris` @ `9185035e`)
**Brief:** APPROVE iter-2 (`pattern-a-only-correct`, `fallback-ok`, `single-pr-exemption-ok`, `clamp`)
**Canonical diff:** 6 files, 707 insertions / 18 deletions, sha256 `7f3087cfa7177df6c3b99b7ba94b2dd981885a0f7e2e4c05684432c2711ae61f`

## 1. Deliverable

Implements the I-rdy-007 contract (`docs/live_run_artifact_contract.md`): the rich
UI endpoints now accept a real completed run ID.

- **NEW `src/polaris_v6/api/live_run_adapter.py`** — `resolve_run` (run_id →
  artifact_dir, error matrix), `artifact_dir_to_evidence_contract` (the adapter),
  `live_run_evidence_contract` (endpoint entry; `None` ⇒ no run_store row ⇒ caller
  falls back to the golden index).
- **`bundle.py` / `charts.py` / `followup.py` / `compare.py`** — rewired live-first
  with `_GOLDEN_RUN_INDEX` as fallback.
- **NEW `tests/v6/test_live_run_adapter.py`** — 9 adapter unit tests + 5 endpoint
  live-path tests.

## 2. The 6 adapter decisions — implemented as the APPROVED brief §3.2

- dec-1 model identity: `AuditIR.model_provenance` → raw `manifest.json` `models` →
  422 (`_model_identity`). Verified by `test_adapter_dec1_model_identity_422`.
- dec-2 verifier split: both `verifier_local_pass`/`verifier_global_pass` ←
  `is_verified` (`_build_verified_sentences`).
- dec-3 frame rollup: group by `(section, slot_id)`, `coverage = pass/total*100`
  (`_build_frame_coverage`).
- dec-4 contradiction projection: `cluster → ContradictionRecord`, >2 claims fold
  into `evidence_b` (`_build_contradictions`). Verified by
  `test_adapter_dec4_contradiction_projection`.
- dec-5 tier normalization: non-T1/2/3 → T3 via `artifact_to_slice_chain._normalize_tier`
  (`_build_evidence_pool`). Verified by `test_adapter_dec5_tier_normalization`.
- dec-6 evidence_pool span clamp: clamp to body, 422 on no non-empty overlap
  (`_build_evidence_pool`). Verified by `test_adapter_dec6_span_clamp`.

## 3. Error matrix + fallback

`resolve_run` raises typed `HTTPException` per I-rdy-007 §6 (404 not-found /
not-completed / artifact_dir-missing; 422 abort_* / release-blocked). Verified by
`test_resolve_run_404_not_found / _404_not_completed / _422_aborted`.
`_GOLDEN_RUN_INDEX` retained as a fallback — `live_run_evidence_contract` returns
`None` when no `run_store` row exists, so golden ids resolve through the existing
path unchanged; verified by `test_endpoint_bundle_golden_fallback_intact`.

## 4. Test evidence

`pytest tests/v6/test_live_run_adapter.py` → **9 passed, 5 skipped**.

- The 9 adapter unit tests (resolver matrix + all 6 decisions) pass unconditionally.
- The 5 endpoint live-path tests **skip on this dev box**: `create_app()` eagerly
  builds the GPG signer (`app.py` module-level `app = create_app()`), and the `gpg`
  binary is not installed here. The pre-existing `tests/v6/test_api_bundle.py`
  errors identically — the whole v6 endpoint suite is gpg-gated. The `client`
  fixture catches the `OSError` and `pytest.skip`s (clean signal, not a masked
  failure). In CI (gpg present) all 14 run. `winget install GnuPG.GnuPG` was
  attempted and UAC-cancelled in the non-interactive session.
- Import smoke (`live_run_adapter`, `bundle`, `charts`, `followup`, `compare`) — OK.

## 5. Judgement calls / honest notes

- **707-LOC diff** — over the 200-LOC cap; Codex brief review explicitly ruled
  `single-pr-exemption-ok` (adapter + rewiring are one inseparable reviewable unit).
  ~290 of the 707 is the new test file.
- **Endpoint tests gpg-gated** — see §4. Not a #504 regression; the gpg fragility in
  `app.py` is pre-existing. A follow-up to make `create_app()` tolerate a missing
  signer is out of #504 scope.
- **#503 residual P2s carried in:** dec-1 reads raw `manifest.json` (P2-1 closed);
  `FrameCoverageEntry.status` treated as a free `str`, exact-`"pass"` match (P2-2
  closed).
- **pin-replay (F13)** — Pattern C, no v6 route; carved to a new follow-up issue
  filed alongside this PR.

## 6. Verdict

Implementation matches the APPROVED brief; the 6 adapter decisions + the error
matrix are each test-verified. Ready for Codex diff review.
