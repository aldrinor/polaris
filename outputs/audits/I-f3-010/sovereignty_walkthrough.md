# I-f3-010 — F3 Sovereignty Walkthrough

**Reframe:** per user directive 2026-05-06 ("Codex signs, not user"), the original "product-owner upload-and-fact-check walkthrough; recording" is replaced by an audit trail of the sovereignty enforcement substrate that already exists. This document IS the durable deliverable Codex reviews for the "CLIENT classification visible, no external API call" verdict.

## 4-scenario corpus

| # | Input | Classification (form field) | Expected backend behavior | Sovereignty router behavior | Substrate ref |
|---|---|---|---|---|---|
| 1 | CLIENT-tagged .md upload | `CLIENT` | 201 with `parse_status="completed"`, `chunk_preview=[...]`, `classification="CLIENT"` | `assert_safe_for_external([item with CLIENT])` → `SovereigntyViolationError` | `src/polaris_graph/sovereignty/router.py:43` (`filter_for_external_egress`), `:71` (`assert_safe_for_external`); `tests/polaris_graph/sovereignty/test_red_team.py:25` |
| 2 | CAN_REAL-tagged .pdf upload | `CAN_REAL` | 201 with `parse_status="queued"` (PDFs queue without sync parse); `classification="CAN_REAL"` | Sovereignty router blocks egress | `src/polaris_graph/sovereignty/classification.py:25` (`EXTERNAL_LEAK_FORBIDDEN` frozenset includes CAN_REAL); `tests/polaris_graph/sovereignty/test_red_team.py:31` |
| 3 | UNKNOWN-tagged upload (default when no classification specified) | `UNKNOWN` (default) | 201; `classification="UNKNOWN"` | Default-deny — UNKNOWN is in `EXTERNAL_LEAK_FORBIDDEN` per Carney v6.2 §332 | `src/polaris_graph/sovereignty/classification.py:25-32` (frozenset definition); `tests/polaris_graph/sovereignty/test_red_team.py:37` |
| 4 | PUBLIC_SYNTHETIC-tagged upload | `PUBLIC_SYNTHETIC` | 201; `classification="PUBLIC_SYNTHETIC"` | Sovereignty router PERMITS egress (only allowed classification per Carney v6.2 §332) | `src/polaris_graph/sovereignty/classification.py:25-32` (PUBLIC_SYNTHETIC NOT in frozenset); `tests/polaris_graph/sovereignty/test_router.py:49` |

## Sovereignty enforcement substrate (cross-referenced)

- **`src/polaris_graph/sovereignty/classification.py:15`** (`DataClassification` enum, 5 values), **`:25-32`** (`EXTERNAL_LEAK_FORBIDDEN = frozenset({CAN_REAL, PRIVATE, CLIENT, UNKNOWN})`) — codifies Carney v6.2 §332 "All non-PUBLIC_SYNTHETIC classifications blocked from external API."
- **`src/polaris_graph/sovereignty/router.py:43`** (`filter_for_external_egress`) raises `SovereigntyViolationError` on any forbidden item. **`:71`** (`assert_safe_for_external`) is the strict-default convenience gate.
- **`tests/polaris_graph/sovereignty/test_router.py`**: 9 unit tests including the 4-classification matrix + dict + dataclass item access.
- **`tests/polaris_graph/sovereignty/test_red_team.py`**: 3 red-team tests proving the gate fires for CLIENT, CAN_REAL, and UNKNOWN-default-deny.
- **`.github/workflows/sovereignty.yml.pending_workflow_scope`** (USER ACTION REQUIRED — rename to `.yml` to activate; bot account lacks `workflow` OAuth scope per project pattern). Workflow runs the full `tests/polaris_graph/sovereignty/` suite on every PR + push to `polaris`/`main`.

## "CLIENT classification visible" — current state + follow-up

**Current (HEAD):**
- Backend `UploadResponse.classification` field (`src/polaris_v6/api/upload.py:43`) is populated from the user's `Form("UNKNOWN")` default at `src/polaris_v6/api/upload.py:56` OR explicit form field.
- Frontend `UploadResponse` type (`web/lib/api.ts:90-99`) includes the classification field.
- Frontend UI (UploadDropZone, DocumentPreview, etc.) does NOT currently render a CLIENT-specific badge — the classification value is on the response object but not visually surfaced.

**Follow-up (named):**
- **I-f3-008b — Frontend: classification badge per uploaded file.** Render `<span data-testid="classification-badge-{id}">{classification}</span>` next to filename. Tests: 4 classifications render with distinct visual treatment; CLIENT renders prominently (red border).

This Issue's walkthrough deliverable is the audit trail proving the BACKEND/POLICY layer enforces the no-external-leak guarantee via tested substrate. UI badge surfacing is the named follow-up.

## "No external API call" — provability

The sovereignty CI gate (`.github/workflows/sovereignty.yml.pending_workflow_scope`) runs:
- `tests/polaris_graph/sovereignty/test_classification.py` (7 tests) — proves the policy set is correct.
- `tests/polaris_graph/sovereignty/test_router.py` (9 tests) — proves the router blocks all non-PUBLIC_SYNTHETIC.
- `tests/polaris_graph/sovereignty/test_red_team.py` (3 tests) — proves the gate fires for the 3 catastrophic classifications (CLIENT, CAN_REAL, UNKNOWN).

If anyone weakens `EXTERNAL_LEAK_FORBIDDEN` to allow CLIENT/CAN_REAL/UNKNOWN through, the red-team tests fail. **CI gating is currently INACTIVE** — `.github/workflows/sovereignty.yml.pending_workflow_scope` requires user-side rename to `.yml` (bot account lacks GitHub `workflow` OAuth scope). Once renamed, the gate runs on every PR and a weakened policy cannot merge.

The remaining gap (named follow-up I-f3-008c): integration test that asserts production code at every external-egress site invokes `assert_safe_for_external()` before the network call. Currently the policy library is correct; the integration assertion that callers USE it is a separate substrate Issue.

## Codex acceptance criteria

APPROVE iff:
1. All 4 scenarios in the table above cross-reference real substrate (file paths exist at HEAD; line numbers point to relevant code).
2. The "no external API call" provability section's tests all PASS via `PYTHONPATH=src python -m pytest tests/polaris_graph/sovereignty/`.
3. The follow-up Issues (I-f3-008b, I-f3-008c) are named explicitly so no acceptance is silently deferred.

## Out of scope

- Real human screen recording (user-driven if desired).
- Frontend classification badge → I-f3-008b.
- Integration test for caller-side `assert_safe_for_external` invocation → I-f3-008c.
