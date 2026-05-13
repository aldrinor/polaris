# I-carney-005 Claude architect audit

**Issue:** GH#469 — Deploy substrate (Dockerfile / entrypoint / compose / Next / GPG)
**Branch:** `bot/I-carney-005-deploy-substrate`
**Codex brief verdict:** APPROVE iter 5 of 5
**Codex diff verdict:** APPROVE iter 3 of 5

## Surface

10 files added/modified for the v6 production stack. Legacy pipeline-B Dockerfile + docker-compose.yml untouched.

| Component | Files | Purpose |
|---|---|---|
| Backend image | `Dockerfile.v6` + `scripts/v6_entrypoint.sh` + `scripts/v6_preflight.py` | python:3.11-slim base + gnupg + WeasyPrint deps. Strips google-generativeai (pipeline-C only, conflicts with OTLP protobuf pin). PYTHONPATH=/app/src:/app. ENTRYPOINT api\|worker\|migrate\|preflight\|shell. wait_for_redis with 10s timeout via redis-py. GNUPGHOME=/app/gpg writable. |
| Compose stack | `docker-compose.v6.yml` | redis 7-alpine (AOF + healthcheck) + api + worker + webui. env_file: .env so OPENROUTER_API_KEY etc. flow in. shared_state named volume between api+worker. Writable GPG homedir bind-mount from `${POLARIS_GPG_HOMEDIR}`. |
| Webui image | `web/Dockerfile` + `web/next.config.ts` + `web/lib/api.ts` | Multi-stage Next.js 16 standalone (output: 'standalone'). INTERNAL_API_URL as BUILD ARG (Next.js bakes rewrite destinations at build time per Codex diff iter-2 P1-B). BACKEND_URL hard-coded `/api/v6` browser-relative; Next rewrite forwards `/api/v6/*` → `http://api:8000/*` server-side. |
| Broker init | `src/polaris_v6/queue/broker.py` + `src/polaris_v6/queue/actors.py` | `_INITIALIZED` sentinel makes get_broker idempotent. actors.py calls `_ensure_broker()` at module TOP before `@dramatiq.actor` decorations (P1-001 same-process init). |
| GPG bootstrap | `scripts/bootstrap_gpg_demo_key.sh` | Idempotent ed25519 signing-only subkey under UID "POLARIS Carney Demo <signing@polaris.local>". Writes fpr → state/polaris_gpg_keyid.txt, pubkey → outputs/polaris_demo_pubkey.asc. |
| Runbook | `docs/deploy_runbook.md` | Prereqs / Step1 GPG / Step2 up / Step3 smoke / Step4 rollback / troubleshooting table. |
| Tests | `tests/v6/test_broker.py` (patched) + `tests/v6/test_broker_init_order.py` (new, 3 tests) | Autouse fixture extended to save/reset/restore `_INITIALIZED` (P1-007). Sentinel-broker reload assertion catches both missing init and decoration-before-init (P1-009). |

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| brief | 1 | REQUEST_CHANGES | P1-001 broker init in subprocess didn't work; P1-002 deps; P1-003 env_file; P1-004 Next standalone; P1-005 BACKEND_URL name; P1-006 GPG writable |
| brief | 2 | REQUEST_CHANGES | P1-001 same-process via actors.py top |
| brief | 3 | REQUEST_CHANGES | P1-007 + P1-008 test fixture state restoration |
| brief | 4 | REQUEST_CHANGES | P1-009 strengthen sentinel-broker test |
| brief | 5 | **APPROVE** | zero P0/P1 |
| diff | 1 | REQUEST_CHANGES | P1-A protobuf conflict; P1-B baked client hostname; P2 GPG preflight strictness |
| diff | 2 | REQUEST_CHANGES | P1-B continued: Next.js bakes rewrite destinations at build time, INTERNAL_API_URL must be ARG not runtime |
| diff | 3 | **APPROVE** | zero P0/P1 |

## All P1 resolutions verified by passing tests

**Broker init order chain (P1-001 → P1-005 → P1-007/008/009):**
- `tests/v6/test_broker_init_order.py::test_actors_module_calls_get_broker_at_import` — pre-installs a `_SentinelBroker` marker, resets `_INITIALIZED=False`, reloads actors, asserts `dramatiq.get_broker() is not sentinel` AND `actors.enqueue_research_run.broker is dramatiq.get_broker()`. PASSES — proving actors.py calls `_ensure_broker()` BEFORE `@dramatiq.actor`.
- All 9 existing `tests/v6/test_broker.py` cases pass with the extended `_restore_session_broker` fixture.

**Dependency surface (P1-002 → P1-A):**
- `Dockerfile.v6` sed-strips `google-generativeai` + `protobuf<` from requirements.txt before install. Verified `grep -rln "from src.llm.gemini_client\|atomic_decomposer" scripts/ src/polaris_v6 src/polaris_graph` returns no consumers — only pipeline-C-frozen code imports it.

**Frontend network plumbing (P1-005 → P1-B iter1 → P1-B iter2):**
- `web/lib/api.ts:23` hard-codes `BACKEND_URL = "/api/v6"` (browser-relative, NEVER baked Docker hostname).
- `web/Dockerfile:23-25` declares `ARG INTERNAL_API_URL=http://api:8000` then sets ENV so `next build` evaluates rewrites() with the production value baked into the routes manifest.
- `docker-compose.v6.yml:108-112` passes `INTERNAL_API_URL: http://api:8000` as build arg (NOT environment), so the value lands in the routes manifest at image-build time.

**Other (P1-003 env_file, P1-004 standalone, P1-006 writable GPG):**
- `docker-compose.v6.yml` api+worker both have `env_file: .env` + container-specific overrides.
- `web/next.config.ts:7` sets `output: "standalone"`.
- `Dockerfile.v6:51-52` sets `GNUPGHOME=/app/gpg` + `mkdir -p /app/gpg && chmod 700`. Compose bind-mount NO `:ro`.

## Test evidence

```
$ python -m pytest tests/v6/test_broker.py tests/v6/test_broker_init_order.py tests/v6/test_actors.py
20 passed in 0.81s

$ python -m pytest tests/v6/
396 passed, 7 xfailed in 33.95s

$ docker compose -f docker-compose.v6.yml config --quiet
# exit 0
```

## Deferred (P3 cosmetic)

- web/Dockerfile header comment updated to match the iter-3 ARG behavior (Codex iter-3 P3 cosmetic).
- Real `docker build` smoke test not run locally; relies on the protobuf sed-strip fix verified via dependency analysis. Acceptable per Codex diff iter-3 (zero remaining_blockers).

## Verdict

READY TO MERGE. All Codex artifacts present:
- `.codex/I-carney-005/brief.md` + brief_iter_2/3/4/5.md
- `.codex/I-carney-005/codex_brief_verdict.txt` (APPROVE iter 5)
- `.codex/I-carney-005/codex_diff.patch`
- `.codex/I-carney-005/codex_diff_audit_iter_3.txt` (APPROVE iter 3)
- `outputs/audits/I-carney-005/claude_audit.md` (this file)

Next: I-carney-002 (AWS Canada Central infra) consumes this substrate to provision the Carney production environment.
