# POLARIS v6.2 — Backend Modernization Plan

**Last updated:** 2026-05-01
**Owning task:** Phase 0 Task 0.5
**Plan reference:** `docs/carney_delivery_plan_v6_2.md`

This document fixes the backend modernization stack for v6.2 build, sequences the migration off legacy substrate, and defines the Dramatiq queue acceptance test that must GREEN before Phase 1 starts.

---

## 1. Stack lock (May 2026 best practice)

| Component | Pin | Status check | License |
|---|---|---|---|
| Python | 3.12.x | LTS, active support through Oct 2028 | PSF |
| FastAPI | 0.136.x | latest minor as of May 2026 | MIT |
| Pydantic | v2.11.x | v2 stable; v1 EOL Q3 2026 | MIT |
| Uvicorn | 0.36.x | ASGI server | BSD-3 |
| Dramatiq | 2.1.0 | latest stable; replaces ARQ (maintenance-only) | LGPL-3 (cleared for service-side use) |
| Redis | 7.4.x | Dramatiq broker + cache substrate | BSD-3 (pre-RSAL fork OK; using Valkey 8.0 if RSAL becomes issue) |
| OpenTelemetry SDK | 1.41.1 | verified on PyPI 2026-05-01; supports `gen_ai_latest_experimental` opt-in | Apache 2.0 |
| OpenTelemetry GenAI semconv (Python pkg) | 0.62b1 | latest pre-stable; ships GenAI semconv 1.36.0+ definitions | Apache 2.0 |
| pytest | 8.x | unit + integration | MIT |
| ruff | 0.7.x | lint + format | MIT |

**LGPL-3 note for Dramatiq:** LGPL-3 obligations attach only to modifications of Dramatiq itself, not to POLARIS service code that imports/uses it. POLARIS does not modify Dramatiq; usage is licence-compatible. Documented in `docs/blockers.md` §5 license review.

---

## 2. Migration sequence (off legacy substrate)

POLARIS currently has 3 parallel pipelines (per architecture.md):
- **A (honest-rebuild sweep)** — pipeline A is current source-of-truth, 2665 tests, scripts/run_honest_sweep_r3.py
- **B (UI web server)** — FastAPI 0.98 + Pydantic v1 (legacy versions)
- **C (frozen legacy)** — frozen 2026-03-16, do not touch

v6.2 modernization scope: **Pipeline B → modern stack**. Pipeline A invariants (two-family evaluator, strict_verify, abort gates) preserved by extending — not replacing.

### 2.1 Phase 0 (Task 0.5)
- [x] Stack pinned (this doc)
- [ ] `requirements-v6.txt` written with explicit pins
- [ ] Dramatiq queue acceptance test stub at `tests/v6/test_dramatiq_acceptance.py` — see §3
- [ ] FastAPI 0.136 router skeleton at `src/polaris_v6/api/__init__.py` — basic `/health` + SSE `/stream` endpoint that proves backpressure semantics

### 2.2 Phase 1
- [ ] Dramatiq actors for: `enqueue_research_run`, `cancel_research_run`, `audit_export`
- [ ] Pydantic v2 schemas for all v6 contracts (RunRequest, RunStatus, EvidenceContract, AuditBundle)
- [ ] OTEL GenAI semconv wired into existing `openrouter_client.py` LLM calls
- [ ] CI gate: pipeline B legacy and v6 backend run side-by-side; v6 imports nothing from legacy `src/orchestration/`

### 2.3 Phase 2A
- [ ] Cutover `scripts/live_server.py` to v6 backend behind `PG_USE_V6_BACKEND` flag (default true once Phase 1 walkthrough GREEN)
- [ ] Deprecate legacy FastAPI 0.98 router after 1-week soak

---

## 3. Dramatiq queue acceptance test (Phase 0 Task 0.5 GREEN gate)

The acceptance test is the bar that must pass before Dramatiq is committed as the queue. Coverage matrix:

| # | Scenario | Assertion |
|---|---|---|
| 1 | enqueue + complete | actor returns; result captured; status `completed` in Redis |
| 2 | enqueue + retry on transient failure | exponential backoff observed; max-retries=3 honoured; status `failed` after exhaustion |
| 3 | cancel mid-execution | `Worker.send_signal(message_id, 'abort')` raises async exception in worker thread; status `cancelled`; partial results discarded |
| 4 | worker kill mid-execution (SIGKILL) | message remains in queue; respawned worker resumes; idempotency key prevents double-execution side effect |
| 5 | resume after broker restart | actor state persisted; worker reconnects via ConnectionMiddleware sticky connection; no message loss |
| 6 | trace-id propagation | OpenTelemetry trace-id present in actor span; parent-child relationship preserved across enqueue → execute → child-actor invocation |
| 7 | high-retry-rate degradation | 100 messages with 60% transient failure rate; queue throughput stays within 30% of clean baseline (mitigation: throttle middleware) |
| 8 | broker heartbeat | `broker.heartbeat=30s` configured; broker disconnect detected within 60s; worker enters reconnect mode without crashing |

**Test fixtures:** `tests/v6/fixtures/dramatiq_acceptance/` with 100 deterministic synthetic messages (per LAW VI: fixed values for testing reside exclusively in `tests/fixtures/`).

**GREEN gate:** All 8 scenarios pass on Vast.ai US dev cluster (Task 0.3) before Phase 1 starts.

---

## 4. Repository layout (v6 modules — proposed)

Per CLAUDE.md §4 (snake_case, one-responsibility-per-file, clean structure):

```
src/polaris_v6/
├── api/                          # FastAPI 0.136 routers
│   ├── __init__.py               # router aggregation
│   ├── health.py
│   ├── runs.py                   # POST /runs, GET /runs/{id}, DELETE /runs/{id}
│   ├── stream.py                 # SSE endpoints
│   ├── upload.py                 # F3b drag-drop upload
│   └── bundle.py                 # F15 audit export
├── queue/
│   ├── __init__.py               # Dramatiq broker initialization
│   ├── actors.py                 # @dramatiq.actor functions
│   ├── middleware/
│   │   ├── connection.py         # sticky connections (cookbook pattern)
│   │   ├── throttle.py           # high-retry-rate mitigation
│   │   └── otel_propagate.py     # trace-id propagation
│   └── results.py                # result backend wrapping
├── schemas/                      # Pydantic v2
│   ├── run_request.py
│   ├── run_status.py
│   ├── evidence_contract.py
│   ├── audit_bundle.py
│   └── verifier_verdict.py
├── observability/
│   ├── otel_init.py              # OpenTelemetry SDK init (Task 0.10)
│   ├── genai_attributes.py       # gen_ai.* semconv helpers
│   └── log_redact.py             # privacy/log redaction (CAN_REAL never logged)
└── adapters/
    ├── verifier_bridge.py        # bridge to existing src/polaris_graph/agents/verifier.py
    └── retrieval_bridge.py       # bridge to existing src/polaris_graph/retrieval/

tests/v6/
├── unit/
├── integration/
├── acceptance/
│   └── test_dramatiq_acceptance.py    # the 8-scenario gate
└── fixtures/
```

---

## 5. Acceptance criteria for Task 0.5 GREEN

Per `docs/task_acceptance_matrix.yaml` task_0_5:

- [x] Stack pinned with versions verified via web research (this doc)
- [x] Migration sequence sequenced into Phase 0 → 1 → 2A
- [x] Dramatiq acceptance test matrix defined (8 scenarios)
- [x] Repository layout proposed (snake_case, modular)
- [ ] `requirements-v6.txt` written (next step)
- [ ] FastAPI 0.136 router skeleton with `/health` + SSE backpressure endpoint (next step)
- [ ] Dramatiq acceptance test stub passing scenarios 1, 2, 3 minimum (4-8 deferred to Phase 1 once Vast.ai cluster live)

**Codex review brief:** `.codex/task_0_5_review_brief.md` (next step)

**Triangle loop next:**
1. Claude self-audit at `outputs/audits/task_0_5/claude_audit.md`
2. Codex independent audit at `outputs/audits/task_0_5/codex_audit.md`
3. Cross-review at `outputs/audits/task_0_5/cross_review.md`
4. Both GREEN → merge + advance to Task 0.7 (SGLang vs vLLM bakeoff once cluster live)

## Sources

- [Dramatiq 2.1.0 user guide](https://dramatiq.io/guide.html)
- [Dramatiq advanced topics](https://dramatiq.io/advanced.html)
- [Dramatiq 2026 best practices](https://johal.in/dramatiq-python-actors-middleware-retries-throttling-2026/)
- [OpenTelemetry GenAI semconv](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
