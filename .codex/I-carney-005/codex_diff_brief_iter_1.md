HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 diff iter 1 — deploy substrate (Dockerfile.v6 + compose + GPG + broker init)

Brief APPROVE iter 5 of 5 (zero P0/P1; one P2 about reload teardown noted as non-blocking).

## Diff `.codex/I-carney-005/codex_diff.patch` (~930 LOC across 13 files)

## File-by-file

| File | Status | Purpose |
|---|---|---|
| `Dockerfile.v6` | NEW | Single image for api + worker. Installs requirements.txt + requirements-v6.txt + gnupg + WeasyPrint deps. PYTHONPATH=/app/src:/app. GNUPGHOME=/app/gpg. EXPOSE 8000. ENTRYPOINT /entrypoint.sh / CMD ["api"]. |
| `docker-compose.v6.yml` | NEW | redis (AOF persistence + healthcheck) + api + worker + webui. env_file: .env so api+worker get OPENROUTER_API_KEY etc. shared_state named volume between api+worker. ${POLARIS_GPG_HOMEDIR}:/app/gpg writable bind-mount. |
| `scripts/v6_entrypoint.sh` | NEW | api\|worker\|migrate\|preflight\|shell. wait_for_redis polls 10s timeout via redis-py; fails loud per LAW II. No subprocess broker init helper — P1-001 is handled IN-PROCESS at top of actors.py. |
| `scripts/v6_preflight.py` | NEW | Checks env vars + redis ping + GPG keyring + run_db write perms. Exits non-zero with failure list. |
| `scripts/bootstrap_gpg_demo_key.sh` | NEW | Idempotent ed25519 signing-only subkey under UID "POLARIS Carney Demo <signing@polaris.local>". Writes fingerprint to state/polaris_gpg_keyid.txt + pubkey to outputs/polaris_demo_pubkey.asc. |
| `docs/deploy_runbook.md` | NEW | Prereqs / Step1 GPG / Step2 up / Step3 smoke / Step4 rollback / troubleshooting table. |
| `web/Dockerfile` | NEW | Multi-stage Next.js 16: deps → builder (ARG NEXT_PUBLIC_BACKEND_URL=http://api:8000) → runner using `.next/standalone`. wget --spider healthcheck (busybox alpine). |
| `web/next.config.ts` | PATCH | `output: 'standalone'` (P1-004) + `/api/v6/:path*` rewrite to `${INTERNAL_API_URL}/:path*` (P1-005). |
| `web/lib/api.ts` | PATCH | BACKEND_URL defaults to `/api/v6` (relative) so browser fetch goes through Next.js server-side rewrite to api container. Falls back to env var when absolute http URL set. |
| `src/polaris_v6/queue/broker.py` | PATCH | `_INITIALIZED` sentinel + `_reset_for_testing()` helper (P1-001 idempotent). Production callers never see `_reset_for_testing`; tests only. |
| `src/polaris_v6/queue/actors.py` | PATCH | `from polaris_v6.queue.broker import get_broker as _ensure_broker` + `_ensure_broker()` BEFORE `import dramatiq` and `@dramatiq.actor`. P1-001 same-process init. |
| `tests/v6/test_broker.py` | PATCH | Extend autouse fixture to save/reset/restore `_INITIALIZED`. P1-007. |
| `tests/v6/test_broker_init_order.py` | NEW | 3 tests: idempotence, `_reset_for_testing`, P1-009 sentinel-broker reload assertion ensuring actors.py calls `_ensure_broker()` BEFORE `@dramatiq.actor` and that `actors.enqueue_research_run.broker is dramatiq.get_broker()` post-reload. |

## P1 resolutions verified

- **P1-001 (broker init in same process):** actors.py line 14-19 imports and calls `_ensure_broker()` BEFORE `import dramatiq` and any `@dramatiq.actor`. Test `test_actors_module_calls_get_broker_at_import` (sentinel-broker pre-install + reload assertion) confirms.
- **P1-002 (dependency surface):** Dockerfile.v6 line 32 installs both requirements.txt + requirements-v6.txt.
- **P1-003 (compose env passthrough):** docker-compose.v6.yml api+worker services both have `env_file: .env` plus container-specific overrides for POLARIS_V6_REDIS_URL, POLARIS_V6_RUN_DB, GNUPGHOME.
- **P1-004 (Next.js standalone):** web/next.config.ts line 7 sets `output: "standalone"`.
- **P1-005 (frontend env var + rewrite):** web/next.config.ts adds rewrite `/api/v6/:path*` → `${INTERNAL_API_URL || NEXT_PUBLIC_BACKEND_URL || localhost:8000}/:path*`. web/lib/api.ts BACKEND_URL defaults to `/api/v6`. web/Dockerfile uses NEXT_PUBLIC_BACKEND_URL (matches the existing api.ts read).
- **P1-006 (writable GNUPGHOME):** Dockerfile.v6 line 49 `ENV GNUPGHOME=/app/gpg` + `mkdir -p /app/gpg && chmod 700`. docker-compose.v6.yml bind-mounts host `${POLARIS_GPG_HOMEDIR}` to `/app/gpg` WRITABLE (no :ro).
- **P1-007 (test_broker.py fixture):** save+reset+restore `_INITIALIZED` extends existing `_restore_session_broker`. 9 existing test cases pass.
- **P1-008 (test_broker_init_order state restore):** new autouse fixture matches the pattern.
- **P1-009 (strengthen assertion):** sentinel `_SentinelBroker` subclass + non-identity check + `actor.broker is current` assertion. Test PASSES.

## Test results

```
tests/v6/test_broker.py: 9 passed
tests/v6/test_broker_init_order.py: 3 passed
tests/v6/test_actors.py: 8 passed
tests/v6/ full suite: 396 passed, 7 xfailed in 33.95s
```

Compose config validation:
```
docker compose -f docker-compose.v6.yml config --quiet  # exit 0
```

## Acceptance criteria verification

1. ✅ Compose config parses clean
2. ⚠️ Dockerfile.v6 build verification: deferred to CI (local Docker build not run in this iter; configured-only)
3. ⚠️ Shellcheck v6_entrypoint.sh: not run locally; brief P2 noted
4. ✅ wait_for_redis 10s timeout (line 19-37 in v6_entrypoint.sh)
5. ✅ bootstrap_gpg_demo_key.sh idempotent (lines 27-30 check existing fingerprint)
6. ✅ deploy_runbook.md has all 5 sections
7. ✅ No secrets committed (.env stays gitignored)
8. ✅ Pipeline-B Dockerfile + docker-compose.yml untouched (no diff)
9. ✅ test_broker_init_order.py + test_actors.py + test_broker.py all pass

## Direct questions iter 1

1. P1-001..P1-009 resolutions verified by passing tests — APPROVE'd?
2. Dockerfile.v6 local-build NOT run in this iter (acceptance crit 2 deferred to CI). Acceptable, or want a local build smoke?
3. shellcheck on v6_entrypoint.sh + bootstrap_gpg_demo_key.sh deferred. Acceptable, or want it in this iter?
4. Anything else blocking iter-1 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
