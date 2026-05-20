# I-cd-016a — Phase-N-PARTIAL-honest manifest

**Issue:** GH#626 — live-run journey backend core (verify + harness).
**Scope of this PR:** harness only. Does NOT close #626.
**Closes #626:** I-cd-016b (#674), operator-supervised live OpenRouter run.

## What's intact (verified pre-PR)

The end-to-end backend journey is built. Pre-PR verification:
- `pytest tests/v6/test_end_to_end_arch_001f.py` PASSES on HEAD `0241ed418386` (capstone hermetic e2e exercises POST /runs → Dramatiq actor → run_store → SSE /stream → /bundle.tar.gz → extract + cross-validate manifest + verified_report).

Backend modules already wired:
- `src/polaris_v6/api/runs.py` (POST /runs, GET /runs/{id}, /cancel) — I-phase0-005, I-rdy-010..013.
- `src/polaris_v6/api/stream.py` (SSE via Redis Streams, Last-Event-ID resume) — I-arch-001e.
- `src/polaris_v6/queue/actors.py` (Dramatiq actor → pipeline-A run_one_query) — I-arch-001a.
- `src/polaris_v6/queue/run_events.py` (v6 event protocol translator).
- `src/polaris_v6/api/bundle.py` (GET /bundle.tar.gz via build_audit_bundle_response).
- `src/polaris_graph/audit_bundle/` (v1.0 schema frozen at I-cd-012; conformance check at I-cd-012).

## What this PR ships (I-cd-016a)

- `scripts/live_run_smoke.py` — operator-runs harness with 9-layer flow (transparency preflight → auth → POST /runs → SSE wait → lifecycle poll → bundle fetch → conformance check → verified-content assert → wallclock report). 9 structured exit codes for diagnosis.
- `docs/runbook.md` — "Live-run smoke (I-cd-016a harness)" section documenting backend + client env requirements, invocation, output, known limitations, and the deferral path to I-cd-016b.

## What's deferred (carved as new bug issues)

| Issue | Status | Blocker for |
|---|---|---|
| **I-cd-016b (#674)** | NEW; operator-supervised live OpenRouter run | Closes #626 |
| **I-cd-016c (#675)** | NEW; bug — `build_slice_chain()` falls back to `generator_model='unknown'` | Blocks lock-verification assertions in I-cd-016b |
| **I-cd-016d (#676)** | NEW; gap — `/transparency.signing_key_fingerprint` is a shallow GPG preflight | Real preflight needed before I-cd-016b real OpenRouter spend |

The harness intentionally does NOT yet assert lock-verification (`generator_model == "deepseek/deepseek-v4-pro"` etc.) because of the bridge bug I-cd-016c. Once that lands, I-cd-016b will re-enable the assertion.

## Codex iter trajectory

- **Brief**: iter 1 RC (4 P1: close-#626 framing, success-only, auth, GPG preflight) → iter 2 RC (3 P1: lock-verification bridge bug, GPG preflight is shallow, SSE-completion race) → iter 3 APPROVE (5 P2 non-blocking, mostly confirmations).
- **Scope split confirmed via Codex consult 2026-05-20** (Path A — highest quality impact): split into harness (this PR) + operator-run (I-cd-016b) per "reducing correctness and security risk late in a long session."

## Risk surface

- No real OpenRouter spend in this PR.
- Smoke is opt-in by operator.
- Two carved bug issues (I-cd-016c + I-cd-016d) capture real production gaps that operator-time-discovery would otherwise hit at I-cd-016b spend cost.

## Acceptance for THIS PR (I-cd-016a)

- `python -m py_compile scripts/live_run_smoke.py`: PASS.
- `python scripts/live_run_smoke.py --help`: argparse usable.
- Codex brief APPROVE (iter 3). Codex diff review next.
