# POLARIS v6.2 — OpenTelemetry GenAI Semconv Pinning

**Last updated:** 2026-05-01
**Owning task:** Phase 0 Task 0.10
**Plan reference:** `docs/carney_delivery_plan_v6_2.md`

This document fixes the OpenTelemetry GenAI semantic conventions pin for v6.2, **with a material correction vs the v6.2 plan**.

---

## 1. Material correction vs v6.2 plan

**v6.2 plan stated:**
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_dev`
- "semconv 1.30.0-dev pinned"

**ACTUAL** (verified at https://opentelemetry.io/docs/specs/semconv/gen-ai/ on 2026-05-01):
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` (verbatim — NOT `gen_ai_dev`)
- Baseline is **1.36.0+** (NOT 1.30.0-dev)
- Status: **Development** (still experimental, not yet stable)

**Why the plan was wrong:** `gen_ai_dev` was a draft proposal name; the spec landed on `gen_ai_latest_experimental` after WG review. The 1.30.0 reference predated the GenAI conventions reaching the current 1.36.0 baseline.

**Plan amendment required:** Update `docs/carney_delivery_plan_v6_2.md` env var string + version pin.

---

## 2. Pinned configuration

### 2.1 Environment variable (POLARIS deployment)

```bash
# Required for all POLARIS v6 services emitting GenAI telemetry
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

**Effect:** Instrumentations emit the latest experimental GenAI conventions; do NOT emit prior 1.36.0-baseline conventions in parallel.

**Rationale for opting into experimental:**
- The "Development" stability tag means the spec may change before stable. POLARIS accepts that risk in exchange for richer attributes (gen_ai.agent.*, gen_ai.tool.*, gen_ai.evaluation.*) that POLARIS uses for Inspector view + audit bundle.
- Carney handover bundle declares the exact OTEL semconv version captured (per F15 Evidence Contract Gate, Phase 1 Task 1.4).
- If the spec breaks compatibility before Phase 5 handover (2026-09-06), POLARIS pins the version that shipped and documents the lock.

### 2.2 Version pin (`requirements-v6.txt`)

```
opentelemetry-api==1.41.1
opentelemetry-sdk==1.41.1
opentelemetry-semantic-conventions==0.62b1
opentelemetry-exporter-otlp==1.41.1
opentelemetry-instrumentation-fastapi==0.62b1
opentelemetry-instrumentation-httpx==0.62b1
```

**Verified via PyPI on 2026-05-01.** `opentelemetry-instrumentation-dramatiq` is **NOT** a published package — Dramatiq instrumentation must be provided by POLARIS middleware (see `docs/backend_modernization.md` §4 — `src/polaris_v6/queue/middleware/otel_propagate.py`). `opentelemetry-semantic-conventions==0.62b1` ships the latest GenAI semconv definitions including the `gen_ai_latest_experimental` opt-in.

### 2.3 Code-side instrumentation pattern

```python
# src/polaris_v6/observability/otel_init.py

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Verify required env var
required_optin = "gen_ai_latest_experimental"
actual_optin = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN", "")
if required_optin not in actual_optin.split(","):
    raise RuntimeError(
        f"POLARIS v6 requires OTEL_SEMCONV_STABILITY_OPT_IN to include "
        f"'{required_optin}'. Got: '{actual_optin}'"
    )

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
```

**Why fail-loudly here:** Per CLAUDE.md LAW II (No Fake Working / No Silent Fallbacks). If OTEL is misconfigured, POLARIS aborts at startup rather than ship a build with broken telemetry.

---

## 3. Attribute coverage POLARIS will emit

| Span / Metric | Attributes |
|---|---|
| LLM call (generator) | `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.response.id`, `gen_ai.request.temperature`, custom: `polaris.evidence_pool_size`, `polaris.section_id` |
| LLM call (verifier) | same + `polaris.verifier_role`, `polaris.verifier_local_pass`, `polaris.verifier_global_pass` |
| Tool call | `gen_ai.tool.name`, `gen_ai.tool.call.id`, `gen_ai.tool.type` |
| Agent loop | `gen_ai.agent.id`, `gen_ai.agent.name`, custom: `polaris.template_id`, `polaris.run_id` |
| Evaluation event | `gen_ai.evaluation.name`, `gen_ai.evaluation.score.value`, custom: `polaris.dimension`, `polaris.benchmark_id` |
| Cost metric | `gen_ai.client.token.usage` (counter), custom: `polaris.cost_usd` |

---

## 4. Privacy / data classification cross-check

Per CLAUDE.md security posture and `docs/blockers.md` §9: data classification `PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN` is enforced in code.

**Mandatory log-redact rules** (enforced in `src/polaris_v6/observability/log_redact.py`):
- `gen_ai.prompt` content for `CAN_REAL` data: redacted (hash only)
- `gen_ai.completion` content for `CAN_REAL` data: redacted (hash only)
- Token counts, latencies, model IDs: ALWAYS emitted (no PII)
- Tool-call arguments containing `CAN_REAL` payload: redacted

**CI gate:** Phase 1 test `tests/v6/test_otel_redaction.py` ensures `CAN_REAL` content never appears in OTEL span attributes.

---

## 5. Acceptance criteria for Task 0.10 GREEN

Per `docs/task_acceptance_matrix.yaml` task_0_10:

- [x] Material correction surfaced (env var name + version baseline)
- [x] Pinned env var: `gen_ai_latest_experimental` (verbatim)
- [x] Pinned semconv baseline: 1.36.0+ via `opentelemetry-semantic-conventions==0.51b0`
- [x] Fail-loudly init pattern documented
- [x] Attribute coverage matrix defined
- [x] Privacy / log-redact rules cross-checked vs CLAUDE.md security posture
- [ ] `requirements-v6.txt` adds OTEL pins (Task 0.5 deliverable)
- [ ] `src/polaris_v6/observability/otel_init.py` written (Task 0.5 deliverable)
- [ ] Plan amendment to `docs/carney_delivery_plan_v6_2.md` env var + version (immediate next step)

**Triangle loop next:**
1. Claude self-audit at `outputs/audits/task_0_10/claude_audit.md`
2. Codex independent audit at `outputs/audits/task_0_10/codex_audit.md`
3. Cross-review at `outputs/audits/task_0_10/cross_review.md`
4. Both GREEN → merge

## Sources

- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [GenAI client AI spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [GenAI events](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-events/)
- [GenAI metrics](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)
- [GenAI agent + framework spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
