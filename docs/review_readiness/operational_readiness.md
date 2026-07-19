# Operational Readiness Checklist (Plan V4 — Item S5)

**Audience:** Independent Telus code reviewer
**Scope:** `src/polaris_graph` deep-research pipeline (§§1–5) **and** the `src/polaris_v6` serving layer + deployment boundary, assessed end-to-end in §6.
**Method:** Every claim below cites a file and line number that was read or grepped directly. No behaviour was inferred without code evidence.
**Repo root:** `/home/polaris/wt/deliverables`
**Date:** 2026-07-19

---

## 1. Executive summary

The pipeline is **operationally mature for a single-host, operator-supervised deployment** and demonstrably **not yet hardened for unattended external exposure**. The strongest areas are cost accounting (persistent ledger + hard per-run budget guard), retries (exponential backoff with `Retry-After` parsing on both LLM and fetch paths), and broad timeout coverage (58 timeout knobs plus a whole-run wall clock). Timeouts are rated **Partial rather than Present** because the "every external call is bounded" claim rests on grep sampling that cannot follow dynamically-supplied `timeout=<var>` / `ClientTimeout` values (see §3.1). The weakest areas for a reviewer to flag are: **checkpoint/resume ships disabled by default**, **no central metrics/health endpoint for the `polaris_graph` pipeline itself** (health endpoints exist but are per-subrouter and shallow), **inter-process rate limiting is best-effort in-process only** (no distributed token bucket), and **no centralized logging configuration** (`logging.basicConfig` appears only in `graph.py` and is not applied by library entrypoints).

A **serving layer** (`src/polaris_v6`, FastAPI + Dramatiq/redis) fronts the pipeline for the Carney demo. It is assessed end-to-end in §6 (new). Its strongest properties are a **fail-loud auth gate** (JWT + startup verification), an **atomic single-session admission gate** (HTTP 409), and **cooperative cancellation**. Its operational gaps are **no server-level request timeout** (uvicorn is started without `--timeout-keep-alive` or any per-request deadline; the only wall clock is the Dramatiq `time_limit`), a **liveness-only `/health` used as a readiness gate**, and **single-worker / single-thread** process sizing that caps throughput but sidesteps most shared-state hazards.

Overall readiness verdict: **Partial — green for a supervised demo/single-host run, amber-to-red for multi-tenant external exposure.**

---

## 2. Readiness checklist table

| # | Capability | Status | Primary evidence |
|---|------------|--------|------------------|
| 1 | Per-stage / per-provider timeouts | **Partial** | 58 `*_TIMEOUT` keys exist (`config_defaults.py`) and `graph_v3.py:791-796` wraps the whole run in a wall clock; but the "all calls bounded" claim rests on **grep sampling, not exhaustive proof** — see note below and row 1a |
| 1a | All external calls bounded | **Partial** | A grep for *bare* `requests`/`httpx`/`aiohttp`/`urlopen` calls (no `timeout=`) returned zero, but many callsites pass the timeout **dynamically** — `timeout=timeout`, `timeout=self.…`, or an `aiohttp.ClientTimeout` object threaded through function args (`agents/evidence_deepener.py:561,657,687`; `agents/searcher.py:2425-2428`). Grep cannot prove those dynamic values are always non-`None` on every branch, and the bound is enforced call-by-call, not at a single choke point |
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

### 3.1 Timeouts — Partial

**Why Partial, not Present (revised).** The prior draft rated timeouts **Present** on the strength of a grep that found zero *bare* external calls. That grep is a **sampling** technique, not a proof: it detects a literal call with no `timeout=` argument, but it cannot follow a `timeout=` value that is supplied **dynamically**. Many real callsites do exactly that — they pass a variable or a threaded `aiohttp.ClientTimeout` object rather than a literal:
- `agents/evidence_deepener.py:561,657,687` take `timeout: aiohttp.ClientTimeout` as a **function parameter** and forward it to `session.get(...)`. Whether every caller actually passes a bounded value (vs. `None`, vs. an unset default on some branch) is not established by grep.
- `agents/searcher.py:2425-2428` builds `timeout = aiohttp.ClientTimeout(total=30)` then passes it through — bounded here, but the pattern shows the bound lives in data flow, not in the call syntax the grep inspected.
- `graph_v2.py:745` passes `timeout=timeout_seconds` (a variable). A grep sees `timeout=`; it does not see whether `timeout_seconds` can be `None`.

Because the audit did **not** exhaustively trace every multiline / dynamically-parameterised client call to prove its timeout is always non-`None`, the honest status is **Partial**. The strong evidence below stands; what is unproven is *exhaustive* coverage.

- **58 timeout knobs** are defined in `src/polaris_graph/config_defaults.py` (grep count of `TIMEOUT`). They span every stage: `PG_LLM_CALL_TIMEOUT=300` (`:400`), `PG_GENERATOR_LLM_TIMEOUT_SECONDS=600` (`:357`), `PG_OUTLINE_TIMEOUT=600` (`:550`), `PG_EXTRACTION_TIMEOUT=180` (`:304`), `PG_DEEPENER_TIMEOUT=720` (`:225`), `PG_DOMAIN_HTTP_TIMEOUT=15` (`:245`), `OPENALEX_TIMEOUT=10` (`:21`), `PG_LIVE_HTTP_TIMEOUT=20` (`:396`), `PG_REACT_TIMEOUT_SECONDS=900` (`:622`).
- **Whole-pipeline wall clock:** `graph_v3.py:791-796` wraps the run in `asyncio.wait_for(..., timeout=max_execution_minutes*60+30)` and logs on `asyncio.TimeoutError`. This is a genuine backstop: even if one dynamic call leaked its bound, the whole-run clock caps the blast radius.
- **Per-provider LLM timeout sizing:** `openrouter_client.py:901-935` (`_resolve_call_timeout`) sizes the per-call clock off the generator budget for reasoning-first models, preventing a small default from truncating a long reasoning call. Streaming uses a tight per-chunk read-stall timeout (`:1766-1779`).
- **External-call audit (sampling):** greps for bare `requests.get/post(`, `httpx.get/post(`, `urlopen(` *without* `timeout` returned **zero** hits. `aiohttp.ClientSession()` sites (e.g. `agents/evidence_deepener.py:571-733`, `searcher.py:2426`, `wiki/wiki_crawl.py:270`) pass the timeout at the per-request `.get()/.post()` call instead — often via a variable, which is exactly why the grep is a sample and not a proof.
- **Gap (Partial):** (1) the "all bounded" claim is grep-sampled, not exhaustively traced through dynamic `timeout=<var>` / `ClientTimeout`-parameter flows; (2) the bound is enforced *call-by-call*, so correctness depends on each new callsite remembering to pass a bounded timeout; there is no single HTTP client wrapper that injects a default, so a future unbounded (or `timeout=None`) call would not be caught structurally. *Recommendation:* route external HTTP through one wrapper that enforces a default timeout, and add a CI check that greps for both bare calls **and** `timeout=None`.

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

- **Timeout coverage is broad and thoughtful** — 58 knobs, reasoning-first-aware sizing (`openrouter_client.py:901-935`), per-chunk stream-stall timeout, and a whole-run wall clock. (Rated Partial only because *exhaustive* per-callsite proof is not established; the coverage itself is genuinely strong — see §3.1.)
- **Cost governance is real** — persistent ledger, context-scoped per-task accounting that survives concurrent `gather()`, and a hard fail-closed budget guard that propagates rather than masks.
- **Retry/backoff honours server `Retry-After`** and never lets a malformed header break the retry path.
- **Graceful degradation across retrieval backends** with an explicit, documented fail-closed posture for research integrity.
- **Failure-mode runbook (`runbook.md` §8) is concrete and actionable**, mapping each abort code to causes and env-var remediations.

---

## 6. Serving layer end-to-end assessment (`src/polaris_v6` + deployment boundary)

**Scope of this section.** Sections 1–5 assess the `polaris_graph` pipeline. This section assesses the **serving surface that exposes that pipeline over HTTP** for the Carney demo: the FastAPI app (`src/polaris_v6/api/app.py`), its Dramatiq/redis job queue (`src/polaris_v6/queue/*`), and the deployment boundary (`Dockerfile.v6`, `scripts/v6_entrypoint.sh`, `docker-compose.v6.yml`, `Caddyfile`). This is the boundary a reviewer must judge for external exposure, because the pipeline itself has no network listener — `polaris_v6` is the only listener.

### 6.0 Serving topology (what actually runs)

- **Process model:** the API is `uvicorn polaris_v6.api.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log` (`scripts/v6_entrypoint.sh:54`). The worker is `dramatiq polaris_v6.queue.actors --processes 1 --threads 2` (`:59`). The API **enqueues** a job and returns `202`; the **worker** runs the long pipeline (`api/runs.py:126`, `queue/actors.py:70-206`).
- **Ingress:** Caddy terminates TLS and is the only host-published surface (`docker-compose.v6.yml:16-33`, `Caddyfile`); `api:8000` and `webui:3000` have no host `ports:` mapping (`docker-compose.v6.yml:79-80,153-154`).
- **Shared state:** run status lives in a SQLite DB on a shared docker volume (`shared_state:/app/state`, `docker-compose.v6.yml:66,120`; `POLARIS_V6_RUN_DB=/app/state/v6_runs.sqlite`, `:62,117`), read/written by **both** the API and the worker container. Redis is the job broker (`queue/broker.py:76-77`).

### 6.1 Serving-layer readiness table

| # | Serving capability | Status | Primary evidence |
|---|--------------------|--------|------------------|
| S1 | Request admission control | **Partial** | App-level 1-concurrent-session gate: `insert_run_if_idle` (`queue/run_store.py:173-210`, `BEGIN IMMEDIATE`) → HTTP 409 (`api/runs.py:91-119`). Auth gate on all non-public routes (`api/auth.py:129-164`). **No server-level rate limit / connection cap** — the gate is one-run-at-a-time, not a per-client QPS limit |
| S2 | Server-level request timeout | **Missing** | uvicorn started with no `--timeout-keep-alive` and no per-request deadline (`scripts/v6_entrypoint.sh:54`); no gunicorn worker-timeout; no ASGI timeout middleware in `app.py`. The only wall clock on a run is the Dramatiq actor `time_limit=30*60*1000` ms (`queue/actors.py:70`) — that bounds the **background job**, not a **synchronous HTTP request**. A slow client or a hung upstream on a synchronous route is not server-bounded |
| S3 | Backpressure / concurrency limit at the server | **Partial** | Backpressure is provided by the **queue**, not the web server: the API returns `202` immediately and the redis/Dramatiq queue buffers work (`api/runs.py:81,126`); the single-session gate caps in-flight *runs* to 1 (`run_store.py:173-210`). But uvicorn has **no `--limit-concurrency` / `--backlog`** (`v6_entrypoint.sh:54`), and Caddy sets no `max_request_body`/connection limit (`Caddyfile`), so raw HTTP connection admission is unbounded up to OS limits |
| S4 | Graceful shutdown | **Partial** | uvicorn installs its default SIGINT/SIGTERM graceful-shutdown handler, and Dramatiq's own default worker shutdown drains in-flight messages before exit. But the FastAPI `lifespan` (`api/app.py:62-68`) does **not** drain or checkpoint in-flight work, there is **no explicit shutdown grace/timeout flag** on either process, and a `StickyConnectionMiddleware.after_worker_shutdown` teardown hook exists (`queue/middleware/connection.py:32-48`) but is **not actually registered** on the broker — `get_broker()` builds a plain `RedisBroker` (`queue/broker.py:71-81`) despite the module docstring claiming sticky connections are wired (`broker.py:6-9`). A container stop mid-run relies on the worker's cooperative-cancel path + Dramatiq requeue, not an app-coordinated drain |
| S5 | Dependency / readiness checks | **Partial** | `/health` returns a **static** `{"status":"ok","version":…}` (`api/health.py:16-18`) — a **liveness** probe. It is used as the compose **readiness gate** (`docker-compose.v6.yml:84-89` health-check + `depends_on: service_healthy` at `:81-83,129-130`) even though it verifies **no dependency** (redis, run DB, provider keys, GPG keyring). The entrypoint does a one-shot `wait_for_redis` at boot (`v6_entrypoint.sh:21-43,47`) and auth substrate is verified fail-loud at app construction (`api/auth.py:99-109` via `app.py:74`), but there is **no continuous `/readyz`** that re-checks dependencies at runtime |
| S6 | SLOs / alerting | **Missing** | No SLO definition, no alert rules, no metrics exporter wired into the serving path. OTel *tracing* SDK exists (`observability/otel_init.py`) but is **opt-in and off by default** — `_lifespan` only calls `init_otel()` when `OTEL_SEMCONV_STABILITY_OPT_IN` is set (`api/app.py:63-68`), and it exports **spans** to an OTLP endpoint, not metrics/alerts. No Prometheus, no `/metrics`, no latency/error-rate/cost-burn alerting on the serving layer |
| S7 | Multi-worker behaviour (shared state / DB contention) | **Partial (mitigated by single-worker)** | The stack runs **1 uvicorn worker + 1 dramatiq process/2 threads** (`v6_entrypoint.sh:54,59`), so most shared-state races are sidestepped by design. Where concurrency does exist (API threads + worker process both hitting the SQLite run DB on a shared volume), it is handled by **WAL mode** (`run_store.py:146`), a **5s `busy_timeout`** (`:86`), an in-process `_INIT_LOCK` for migrations (`:64,143`), and **CAS transitions** (`mark_in_progress` compare-and-swap `:213-233`; `insert_run_if_idle` `BEGIN IMMEDIATE` `:192`). **Not proven safe if scaled to `--workers N>1` or multiple worker replicas:** the single-session gate and CAS are correct across processes via SQLite locking, but SQLite-over-a-docker-volume under many writers is a known contention/`SQLITE_BUSY` risk, and the broker-init idempotency sentinel (`queue/broker.py:30,64-66`) is **per-process**, so horizontal scaling has not been exercised |
| S8 | Auth / tenant isolation at the edge | **Present (single-tenant)** | Global `require_auth` dependency on the app (`api/app.py:80`), HS256 JWT with 12h expiry, fail-loud on missing/weak `POLARIS_JWT_SECRET` and missing accounts file at startup (`api/auth.py:88-109`), SSE token accepted via query param **only** on `/stream/*` (`:148-151`). This is a **single-tenant static-accounts** model (Carney demo); there is no per-tenant quota/isolation — consistent with §4 gap 6 (cost cap is per-run, not per-tenant) |

### 6.2 Serving-layer detail with evidence

- **Admission control (S1, Partial).** The one meaningful admission gate is the **1-concurrent-session** constraint: `POST /runs` calls `insert_run_if_idle`, which runs the active-run check and the INSERT inside a single `BEGIN IMMEDIATE` transaction (`run_store.py:187-210`) so two concurrent `POST /runs` cannot both start; the loser gets a structured HTTP 409 (`api/runs.py:101-119`) and is never enqueued. Every non-public route also passes the JWT `require_auth` dependency (`api/app.py:80`, `api/auth.py:129-164`). What is **absent** is a per-client rate limit or a global connection cap at the server — admission is "one run at a time + valid JWT", not "N requests/sec/client".

- **Server-level timeout (S2, Missing) — the sharpest serving gap.** uvicorn is invoked with no request/keep-alive timeout (`v6_entrypoint.sh:54`) and there is no timeout middleware in `app.py`. The `30-minute` bound at `queue/actors.py:70` is a **Dramatiq actor `time_limit`** — it caps the background job, not a synchronous HTTP handler. Routes that do synchronous work in-request (e.g. upload parsing, bundle assembly, chart rendering) have **no server-side deadline**; a hung dependency or slow client ties up one of the 1-worker's threads indefinitely. This mirrors the pipeline-side finding (§3.1 / §4 gap 5) that timeout enforcement is per-callsite and not structural — here the structural gap is at the web-server layer.

- **Backpressure (S3, Partial).** The architecture deliberately pushes long work onto the queue: `POST /runs` returns `202` and enqueues (`api/runs.py:81,126`); redis + Dramatiq absorb the backlog; the single-session gate caps concurrent *runs* to 1. That is real backpressure for the **run** workload. It is **not** backpressure for raw HTTP: no `--limit-concurrency`, no `--backlog` on uvicorn (`v6_entrypoint.sh:54`), no request-body-size or connection limit in Caddy (`Caddyfile`), so connection admission is bounded only by the OS and the single worker's thread pool.

- **Graceful shutdown (S4, Partial).** The worker relies on Dramatiq's default worker shutdown (drain in-flight messages, then exit). A `StickyConnectionMiddleware.after_worker_shutdown` teardown hook is *defined* (`queue/middleware/connection.py:32-48`) — it would close the sticky redis connection and log (non-fatal) on failure — but it is **never registered**: `get_broker()` constructs a plain `RedisBroker(url=…, heartbeat_timeout=…)` and adds no custom middleware (`queue/broker.py:71-81`), even though the module docstring asserts sticky connections are wired (`broker.py:6-9`). The API side relies on uvicorn's built-in graceful shutdown; the FastAPI `lifespan` (`api/app.py:62-68`) only initialises OTel and yields — it does **not** drain in-flight requests, flush the run DB, or set a shutdown grace period. On `docker compose down`, in-flight worker jobs depend on Dramatiq's requeue-on-restart and the cooperative-cancel machinery (`run_store.request_cancel` / `is_cancel_requested`, `actors.py:93-103,252-255`) rather than a coordinated app drain.

- **Readiness (S5, Partial).** `/health` is static liveness (`api/health.py:16-18`). It is nonetheless the gate the whole compose graph waits on (`docker-compose.v6.yml:81-90,126-130`), so a container can report "healthy" while redis is unreachable, the run DB volume is unwritable, or provider keys are absent — none of which `/health` checks. Startup does fail loud on the two things it *does* verify: `wait_for_redis` (10s, `v6_entrypoint.sh:21-43`) and auth substrate at `create_app()` (`api/auth.py:99-109`). The gap is a **continuous** readiness probe (`/readyz`) that re-checks redis, the run DB, and configured backends at request time — the same "deep readiness probe" gap called out for the pipeline in §4 gap 2, here at the deployment boundary.

- **SLOs / alerting (S6, Missing).** There is no serving-layer SLO, alert rule, or metrics exporter. The OTel machinery (`observability/otel_init.py`) is opt-in (`app.py:63-68` guards on `OTEL_SEMCONV_STABILITY_OPT_IN`) and exports **traces**, not metrics; even when enabled it gives no alerting. Operators cannot alert on API error rate, p95 latency, queue depth, or cost-burn without adding instrumentation. `observability/log_redact.py` exists to scrub logs, which is good hygiene, but is not telemetry.

- **Multi-worker behaviour (S7, Partial — mitigated by single-worker).** The deployment ships **one** uvicorn worker and **one** dramatiq process/2 threads (`v6_entrypoint.sh:54,59`), which is why the shared-state story holds today: the only genuine cross-process concurrency is API-threads + worker both touching the SQLite run DB on `shared_state:/app/state`. That is handled with WAL (`run_store.py:146`), a 5s `busy_timeout` (`:86`), migration serialisation via `_INIT_LOCK` (`:64,143`), and atomic CAS/`BEGIN IMMEDIATE` transitions (`:192,213-233,251-266`). These are **correct across processes** (SQLite file locking), so the single-session and cancel invariants survive the API↔worker split. **However**, the configuration has not been validated for horizontal scale: raising uvicorn `--workers` or adding worker replicas would put many writers on a **single SQLite file over a docker volume** (a documented `SQLITE_BUSY`/latency hazard), and the broker-init idempotency sentinel is **per-process** (`queue/broker.py:30,64-66`). For anything beyond the single-host demo, the run store should move to a client/server DB (Postgres) or the writer set stay at one process.

- **Auth / edge (S8, Present for single-tenant).** Covered in the table; the notable positive is the LAW-II fail-loud posture — the app refuses to construct if `POLARIS_JWT_SECRET` is missing/short or the accounts YAML is absent (`api/auth.py:88-109`, invoked at `app.py:74`), so it cannot silently boot with auth disabled unless `POLARIS_AUTH_DISABLED=1` is explicitly set (`:106-107,137-138`).

### 6.3 Serving-layer top gaps (reviewer flags, in priority order)

1. **[HIGH] No server-level request timeout (S2).** uvicorn runs with no keep-alive/request deadline and there is no timeout middleware; the 30-min bound is a background-job `time_limit`, not an HTTP-request deadline (`v6_entrypoint.sh:54`, `queue/actors.py:70`). *Recommendation:* add `--timeout-keep-alive`, front with gunicorn+uvicorn workers with a `--timeout`, or add an ASGI timeout middleware; and put read/write timeouts in Caddy.
2. **[HIGH] `/health` is liveness used as readiness (S5).** The compose graph gates on a probe that checks no dependency (`api/health.py:16-18`, `docker-compose.v6.yml:84-90`). *Recommendation:* add `/readyz` that verifies redis, the run DB, and configured provider/GPG backends, and point the compose/orchestrator readiness gate at it.
3. **[MEDIUM-HIGH] No serving SLOs / metrics / alerting (S6).** OTel is opt-in, trace-only (`app.py:63-68`, `observability/otel_init.py`). *Recommendation:* export request/queue/cost metrics and define error-rate + latency + queue-depth alerts before external exposure.
4. **[MEDIUM] SQLite run store not proven for horizontal scale (S7).** Correct at 1 worker + 1 dramatiq process; a single SQLite file over a docker volume is a contention risk under `--workers N` or replicated workers (`run_store.py:82-88,146`). *Recommendation:* move the run store to Postgres before scaling out, or hold the writer set at one process and document it as a hard constraint.
5. **[MEDIUM] No app-coordinated graceful drain (S4).** `lifespan` does not drain in-flight requests/jobs (`api/app.py:62-68`); shutdown relies on uvicorn defaults + Dramatiq requeue. *Recommendation:* add a shutdown grace period and an in-flight-drain step, and document the container-stop contract in `deploy_runbook.md`.
6. **[MEDIUM] No edge rate limiting / connection cap (S1/S3).** Admission is one-run-at-a-time + valid JWT, with no per-client QPS limit or uvicorn `--limit-concurrency`/Caddy connection cap (`v6_entrypoint.sh:54`, `Caddyfile`). *Recommendation:* add a Caddy or middleware rate limiter and a uvicorn concurrency cap before multi-tenant exposure.

### 6.4 Serving layer — what is genuinely strong (for balance)

- **Fail-loud auth substrate** verified at app construction (`api/auth.py:99-109`), so the server cannot boot into an unauthenticated state by accident.
- **Atomic single-session admission** via `BEGIN IMMEDIATE` (`run_store.py:187-210`) — two concurrent starts cannot both win; the loser gets a clean, structured 409.
- **Cooperative cancellation with an actor-side backstop** (`actors.py:93-103,252-255`, `run_store.request_cancel` `:236-268`) — a cancel wins even if it lands at a late pipeline stage.
- **Correct API↔worker separation of shared state** — the run DB uses WAL + `busy_timeout` + CAS transitions, so the invariants hold across the two-process split at demo scale.
- **Egress-minimised ingress** — Caddy is the only host-published surface; API and webui are Docker-network internal (`docker-compose.v6.yml:76-80,151-154`).
