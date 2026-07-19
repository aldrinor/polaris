# Operational Readiness Checklist (Plan V4 — Item S5)

**Audience:** Independent Telus code reviewer
**Scope:** `src/polaris_graph` deep-research pipeline (plus the serving surface in `src/polaris_v6` where it bounds the same runtime).
**Method:** Every claim below cites a file and line number that was read or grepped directly. No behaviour was inferred without code evidence.
**Repo root:** `/home/polaris/wt/deliverables`
**Date:** 2026-07-19

---

## 1. Executive summary

The pipeline is **operationally mature for a single-host, operator-supervised deployment** and demonstrably **not yet hardened for unattended external exposure**. The strongest areas are timeouts (58 timeout knobs, every sampled external call bounded), cost accounting (persistent ledger + hard per-run budget guard), and retries (exponential backoff with `Retry-After` parsing on both LLM and fetch paths). The weakest areas for a reviewer to flag are: **checkpoint/resume ships disabled by default**, **no central metrics/health endpoint for the `polaris_graph` pipeline itself** (health endpoints exist but are per-subrouter and shallow), **inter-process rate limiting is best-effort in-process only** (no distributed token bucket), and **no centralized logging configuration** (`logging.basicConfig` appears only in `graph.py` and is not applied by library entrypoints).

Overall readiness verdict: **Partial — green for a supervised demo/single-host run, amber-to-red for multi-tenant external exposure.**

---

## 2. Readiness checklist table

| # | Capability | Status | Primary evidence |
|---|------------|--------|------------------|
| 1 | Per-stage / per-provider timeouts | **Present** | `config_defaults.py` (58 `*_TIMEOUT` keys); `graph_v3.py:791-796` (whole-pipeline wall clock); `llm/openrouter_client.py:901-935` (`_resolve_call_timeout`) |
| 1a | All external calls bounded | **Partial** | Every sampled `requests`/`httpx`/`aiohttp`/`urlopen` call carries a timeout (audit grep for bare calls returned zero); but bound is enforced call-by-call, not by a single choke point |
| 2 | Retries + backoff on LLM calls | **Present** | `openrouter_client.py:936-938` (`MAX_RETRIES`, `RETRY_BACKOFF_BASE`), `:2161-2420` (retry loop, 429 backoff), `:1018-1049` (`_parse_retry_after`) |
| 2a | Retries + backoff on fetch calls | **Present** | `retrieval/fetch_limiter.py:74-130` (exponential backoff + jitter); `retrieval/frame_fetcher.py:686-702` (429/5xx retry); `agents/searcher.py:1063-1067` (Exa `Retry-After`) |
| 2b | Retries on planner/verifier stages | **Present** | `agents/planner.py:425-462` (3x backoff `[1,3,9]`); `agents/verifier.py:491-579` (retry cap `PG_VERIFY_RETRY_CAP`) |
| 3 | Concurrency caps | **Present** | 19 `*_CONCURRENCY` keys in `config_defaults.py`; `retrieval/llm_throttle.py:35-54` (shared semaphore); `retrieval/fetch_limiter.py:39-47` |
| 3a | Rate limiting (per-provider) | **Partial** | In-process only: `openrouter_client.py:2414-2420` (429 floor), `live_retriever.py:6948` (S2 <=1rps via `time.sleep`), `searcher.py:786` — **no shared/distributed limiter across workers** |
| 3b | Token / cost accounting | **Present** | `openrouter_client.py:57-58` (persistent ledger), `:325-397` (`append_cost_ledger_row`, `cumulative_cost_usd`), `:481-490` (`check_run_budget`) |
| 3c | Hard cost cap enforcement | **Present** | `openrouter_client.py:84,246-247,481-490` (`PG_MAX_COST_PER_RUN` default `10.00`, `BudgetExceededError`); enforced at callsites e.g. `authority/credibility_skill.py:436,465` |
| 4 | Structured tracing | **Present** | `tracing.py` (JSONL tracer, `PG_TRACING_ENABLED` default **1**, `config_defaults.py:784`) |
| 4a | Logging | **Partial** | Loggers used throughout, but `logging.basicConfig` only in `graph.py:2223`; no central `dictConfig`/JSON logger — library callers get no handler config |
| 4b | Metrics / aggregation | **Missing** | No Prometheus/OpenTelemetry/statsd. Grep for `prometheus|opentelemetry|otel|statsd` in `src/polaris_graph` returns 0 hits. Only ad-hoc `time.perf_counter()` latency in `api/intake.py` |
| 4c | Health checks | **Partial** | `src/polaris_v6/api/health.py:16-18` (`/health`, static `status:ok`); per-subrouter health in `api/*.py` (e.g. `retrieval_route.py:140`); Docker `HEALTHCHECK` in `Dockerfile:38`, `Dockerfile.v6:79`, `docker-compose.v6.yml`. **No deep readiness probe** (does not check provider keys / DB / downstream) |
| 5 | Runbooks | **Present** | `docs/runbook.md` (433 lines, incl. §8 failure modes); `docs/deploy_runbook.md` (139 lines); `docs/carney_demo_runbook.md`; `docs/serving/verifier_serving_runbook.md` |
| 6 | Checkpoint / resume | **Partial** | `checkpoint_manager.py` (langgraph sqlite saver, rewind API) — but `PG_CHECKPOINT_ENABLED` default **`0`** (`config_defaults.py:97`) — **ships OFF** |
| 6a | Resume idempotency / re-fetch | **Present (default OFF)** | `retrieval/resume_refetch.py` (A15 shell re-fetch, `PG_RESUME_REFETCH_DEGRADED` default OFF) |
| 6b | Graceful degradation on provider failure | **Present** | `agents/searcher.py:407-408,659-662` (OpenAlex→S2→DDG fallbacks); `openrouter_client.py` provider exclusion on stall (`:2342-2369`) |
| 6c | Fail-loud vs fail-silent posture | **Present (by design)** | Deliberate fail-closed on core retrieval: `searcher.py:373,1278`; `domain_backends.py:876-879` (rate-limited backend must not be masked as empty) |

---

## 3. Category detail with evidence

### 3.1 Timeouts — Present

- **58 timeout knobs** are defined in `src/polaris_graph/config_defaults.py` (grep count of `TIMEOUT`). They span every stage: `PG_LLM_CALL_TIMEOUT=300` (`:400`), `PG_GENERATOR_LLM_TIMEOUT_SECONDS=600` (`:357`), `PG_OUTLINE_TIMEOUT=600` (`:550`), `PG_EXTRACTION_TIMEOUT=180` (`:304`), `PG_DEEPENER_TIMEOUT=720` (`:225`), `PG_DOMAIN_HTTP_TIMEOUT=15` (`:245`), `OPENALEX_TIMEOUT=10` (`:21`), `PG_LIVE_HTTP_TIMEOUT=20` (`:396`), `PG_REACT_TIMEOUT_SECONDS=900` (`:622`).
- **Whole-pipeline wall clock:** `graph_v3.py:791-796` wraps the run in `asyncio.wait_for(..., timeout=max_execution_minutes*60+30)` and logs on `asyncio.TimeoutError`.
- **Per-provider LLM timeout sizing:** `openrouter_client.py:901-935` (`_resolve_call_timeout`) sizes the per-call clock off the generator budget for reasoning-first models, preventing a small default from truncating a long reasoning call. Streaming uses a tight per-chunk read-stall timeout (`:1766-1779`).
- **External-call audit:** greps for bare `requests.get/post(`, `httpx.get/post(`, `urlopen(` *without* `timeout` returned **zero** hits. `aiohttp.ClientSession()` sites (e.g. `agents/evidence_deepener.py:571-733`, `searcher.py:2426`, `wiki/wiki_crawl.py:270`) pass the timeout at the per-request `.get()/.post()` call instead.
- **Gap (Partial on 1a):** the bound is enforced *call-by-call*, so correctness depends on each new callsite remembering to pass a timeout. There is no single HTTP client wrapper that enforces a default timeout, so a future unbounded call would not be caught structurally.

### 3.2 Retries — Present

- **LLM:** `openrouter_client.py:936-938` (`MAX_RETRIES=2`, `RETRY_BACKOFF_BASE=2.0`); the retry loop at `:2161` sleeps `RETRY_BACKOFF_BASE ** attempt` (`:2389`); 429 handling bumps the backoff floor to 15/30/60s (`:2415-2420`, `PG_RATE_LIMIT_FLOOR_S=15.0`); `_parse_retry_after` (`:1018-1049`) honours the server `Retry-After` header and never raises on a malformed value.
- **Fetch:** `retrieval/fetch_limiter.py:74-130` retries 429/5xx with exponential backoff + jitter (`PG_FETCH_MAX_RETRIES=3`, `PG_FETCH_RETRY_BASE=2.0`, `PG_FETCH_RETRY_MAX=30.0` — `config_defaults.py:325-329`). `frame_fetcher.py:686-702` retries `{429,500,502,503,504}`. `searcher.py:1063-1067` reads Exa's `Retry-After`.
- **Stage-level:** planner seed retry with backoff `[1,3,9]` (`planner.py:425-462`); verifier retry with a consecutive-timeout cap (`verifier.py:491-579`, `PG_VERIFY_RETRY_CAP=3`).
- No `tenacity` dependency — retries are hand-rolled but consistent.

### 3.3 Rate / cost limits

- **Concurrency (Present):** 19 `*_CONCURRENCY` knobs (`PG_LLM_CONCURRENCY=4`, `PG_WEB_CONCURRENCY=20`, `PG_VERIFY_CONCURRENCY=20`, etc.). `retrieval/llm_throttle.py:35-54` provides a shared module-level `asyncio.Semaphore(PG_LLM_CONCURRENCY)` with a retry wrapper; `fetch_limiter.py` a shared fetch semaphore. Many agents also self-bound with `asyncio.Semaphore` (18 direct usages).
- **Cost accounting (Present):** persistent JSONL cost ledger at `PG_COST_LEDGER_PATH=logs/pg_cost_ledger.jsonl` (`config_defaults.py:165`). `append_cost_ledger_row` (`openrouter_client.py:325-397`) records `cumulative_cost_usd` per session under a reentrant lock; per-task cost uses a `contextvars.ContextVar` (`:103-104`) so concurrent `gather()` workers don't cross-contaminate.
- **Hard cost cap (Present):** `PG_MAX_COST_PER_RUN` (default `10.00`, `config_defaults.py:435`) enforced by `check_run_budget()` (`openrouter_client.py:481-490`), which raises `BudgetExceededError` and propagates (not masked) at real callsites (`authority/credibility_skill.py:436,465`; `authority/credibility_judge_caller.py:495`). This is documented as a runaway-loop guard, not an economic limit (`:69-84`).
- **Rate limiting (Partial):** per-provider throttling is **in-process best-effort**: S2 gentle sleep `<=1rps` (`live_retriever.py:6948`), 429 backoff floors, Exa `Retry-After`. There is **no shared/distributed rate limiter** — under `docker-compose.v6.yml` (multiple `worker` replicas) each process rate-limits itself independently, so aggregate provider QPS can exceed per-provider limits. `PG_S2_RPS=1.0` exists (`config_defaults.py:657`) but was not observed wired into a cross-worker limiter.

### 3.4 Monitoring / observability

- **Tracing (Present):** `tracing.py` emits structured JSONL trace events (`node_start`, `llm_call`, `fetch`, `quality_gate`) to `logs/pg_trace_{vector_id}.jsonl`, stdlib-only, `PG_TRACING_ENABLED` default **1** (`config_defaults.py:784`). Thread-safe `vector_id` propagation via `ContextVar`.
- **Live dashboard (Present, dev-facing):** `dashboard.py` renders a Rich terminal dashboard; `graph_v3.py:721` `enable_dashboard: bool = True`. This is a human-in-the-loop TUI, not machine-scrapable telemetry.
- **Logging (Partial):** loggers are used everywhere (`logging.getLogger("polaris_graph")`), but `logging.basicConfig(...)` appears **only** in `graph.py:2223` (a CLI entrypoint). A library caller (e.g. the API/worker importing pipeline functions) gets no handler/format configuration and no structured/JSON logging. There is no `logging.config.dictConfig` in the package.
- **Metrics (Missing):** no Prometheus / OpenTelemetry / statsd instrumentation anywhere in `src/polaris_graph` (grep returns 0). Latency is captured ad-hoc via `time.perf_counter()` in a few routes (`api/intake.py:110-202`) but not exported.
- **Health checks (Partial):** `src/polaris_v6/api/health.py:16-18` returns a static `{"status":"ok","version":...}` — a **liveness** probe with no dependency (provider key, redis, DB) check, i.e. not a true readiness probe. Per-subrouter `/…/health` endpoints exist across `api/*.py`. Docker `HEALTHCHECK` hits `:8000/health` (`Dockerfile:38`, `Dockerfile.v6:79`); `docker-compose.v6.yml` gives redis a `redis-cli ping` and the worker a redis-reachability check. **The `polaris_graph` pipeline library itself exposes no health/self-test endpoint.**

### 3.5 Runbooks — Present

- `docs/runbook.md` (433 lines): prerequisites, sanity checks, output interpretation, and **§8 Common failure modes** covering `material_deviation=true`, `abort_corpus_approval_denied`, `abort_no_verified_sections`, budget-cap hits (with concrete env-var remediations), and empty-content-from-provider. This is genuinely operational, not aspirational.
- `docs/deploy_runbook.md` (139 lines): single-host `docker compose` deploy, GPG bootstrap, smoke test, service dependency ordering.
- Additional: `docs/carney_demo_runbook.md`, `docs/serving/verifier_serving_runbook.md`, `docs/carney_handover/runbook.md`.
- **Gap:** runbooks are demo/single-host oriented ("Production AWS Canada Central infrastructure is tracked separately"). No incident/on-call runbook for the multi-tenant/production surface (alerting thresholds, escalation, provider-outage playbook beyond the pipeline's own fallbacks).

### 3.6 Recovery — Partial

- **Checkpoint/resume (Partial — ships OFF):** `checkpoint_manager.py` wraps langgraph's `AsyncSqliteSaver` and adds `list_checkpoints`/`get_checkpoint_state`/`rewind_to_checkpoint`. But `PG_CHECKPOINT_ENABLED` default is **`0`** (`config_defaults.py:97`) — crash-resume is opt-in and off by default, so an unconfigured production deployment has **no automatic resume** after a crash.
- **Resume re-fetch idempotency (Present, default OFF):** `retrieval/resume_refetch.py` re-fetches shell/degraded rows on resume, documented as faithfulness-safe (touches input only); master flag `PG_RESUME_REFETCH_DEGRADED` defaults OFF.
- **Graceful degradation (Present):** retrieval fallback chain OpenAlex → S2 → DuckDuckGo (`searcher.py:407-408,659-662`); provider exclusion on a stalled stream forces the retry onto the next provider (`openrouter_client.py:2342-2369`); `TokenBudgetError` triggers a bounded regen loop (`:261-290`).
- **Fail-closed core (Present, by design):** the system deliberately fails loud rather than silently degrading on core retrieval (`searcher.py:373,1278`; `domain_backends.py:876-879`), which is the correct posture for a research-integrity product but means a provider outage can **abort** a run rather than return a partial — acceptable given checkpoint/resume, but that resume is off by default (see above).

---

## 4. Prioritized top operational gaps (reviewer flags before external exposure)

1. **[HIGH] Checkpoint/resume ships disabled (`PG_CHECKPOINT_ENABLED=0`).** A crash or provider outage mid-run loses the run with no automatic recovery. Combined with the fail-closed retrieval posture (`domain_backends.py:876-879`), a transient outage can abort a paid, long-running job. *Recommendation:* default-on checkpointing in the deployed profile, or document it as a required deploy step in `deploy_runbook.md`. Evidence: `config_defaults.py:97`, `checkpoint_manager.py:26`.

2. **[HIGH] No machine-scrapable metrics or deep readiness probe.** `/health` is a static liveness string (`polaris_v6/api/health.py:16-18`) that does not verify provider keys, redis, DB, or model reachability; there is no Prometheus/OTel export (grep = 0 hits). Operators cannot alert on cost-burn rate, 429 rate, latency, or failure rate without parsing JSONL by hand. *Recommendation:* add a `/readyz` that checks dependencies and export the trace counters (spend, retries, provider errors) as metrics.

3. **[MEDIUM-HIGH] Rate limiting is in-process only — no cross-worker coordination.** With multiple `worker` replicas (`docker-compose.v6.yml`), aggregate provider QPS can exceed per-provider limits because each process throttles itself independently (`llm_throttle.py:53`, `live_retriever.py:6948`). Under external load this invites provider-side 429 storms / key suspension. *Recommendation:* a shared (redis-backed) token bucket for provider calls.

4. **[MEDIUM] No centralized logging configuration.** `logging.basicConfig` exists only in the `graph.py` CLI entrypoint (`graph.py:2223`); library/API/worker callers get unconfigured loggers and no structured/JSON logs, which undermines log aggregation and incident triage in a container platform. *Recommendation:* a `dictConfig`/JSON logger applied at every service entrypoint.

5. **[MEDIUM] Timeout enforcement is per-callsite, not structural.** Every sampled external call is bounded, but there is no single HTTP-client choke point enforcing a default timeout, so a future unbounded call would silently pass review. *Recommendation:* route external HTTP through one wrapper that injects a default timeout; add a lint/CI check for bare `requests`/`httpx`/`aiohttp` calls.

6. **[MEDIUM] Cost cap is per-run, not per-tenant/per-window.** `check_run_budget` bounds a single run (default $10, `config_defaults.py:435`), but nothing caps aggregate spend across concurrent runs / a tenant / a time window. Under external exposure this is a cost-DoS vector. *Recommendation:* add a per-tenant/per-window ceiling on top of the existing per-run guard (the ledger at `openrouter_client.py:325-397` already has the primitives).

7. **[LOW-MEDIUM] Runbooks are single-host/demo-scoped.** No production incident/on-call playbook (alert thresholds, escalation, provider-outage response beyond the pipeline's own fallbacks). *Recommendation:* extend `deploy_runbook.md` with a production incident section before external exposure.

---

## 5. What is genuinely strong (for balance)

- **Timeout coverage is thorough and thoughtful** — 58 knobs, reasoning-first-aware sizing (`openrouter_client.py:901-935`), per-chunk stream-stall timeout, and a whole-run wall clock.
- **Cost governance is real** — persistent ledger, context-scoped per-task accounting that survives concurrent `gather()`, and a hard fail-closed budget guard that propagates rather than masks.
- **Retry/backoff honours server `Retry-After`** and never lets a malformed header break the retry path.
- **Graceful degradation across retrieval backends** with an explicit, documented fail-closed posture for research integrity.
- **Failure-mode runbook (`runbook.md` §8) is concrete and actionable**, mapping each abort code to causes and env-var remediations.
