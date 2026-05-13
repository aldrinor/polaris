HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 iter 3 — P1-001 resolution (same-process broker init)

## P1-001 — broker init MUST be same-process, before actor decoration

Codex iter-2 caught: subprocess `python -m scripts.v6_init_broker` doesn't survive into `exec uvicorn` / `exec dramatiq` (separate interpreter). API lifespan hook also too late because router imports bind actors before lifespan starts.

### Resolution: idempotent same-process init at the broker module + actors module top

**Patch 1: `src/polaris_v6/queue/broker.py`** — add module-level `_INITIALIZED` sentinel so `get_broker()` is idempotent:

```python
_INITIALIZED = False

def get_broker(*, use_stub=None, redis_url=None, heartbeat_seconds=DEFAULT_HEARTBEAT_SECONDS):
    global _INITIALIZED
    if _INITIALIZED:
        return dramatiq.get_broker()
    # ... existing construction logic ...
    dramatiq.set_broker(broker)
    _INITIALIZED = True
    return broker
```

This preserves conftest behavior (first call sets StubBroker, subsequent calls return it) AND lets actors.py call `get_broker()` at module top without double-init.

**Patch 2: `src/polaris_v6/queue/actors.py`** — add a top-of-module guard so importing actors ALWAYS sets the broker first:

```python
# At very top, BEFORE `import dramatiq` and BEFORE any @dramatiq.actor
from polaris_v6.queue.broker import get_broker as _ensure_broker
_ensure_broker()  # idempotent; reads POLARIS_V6_REDIS_URL or POLARIS_V6_QUEUE_USE_STUB

import dramatiq  # noqa: E402 — must come after broker init
# ... rest of imports + actor declarations unchanged
```

Now both `uvicorn polaris_v6.api.app:app` and `dramatiq polaris_v6.queue.actors` paths bind actors against the correct broker:

- `uvicorn ... app:app` → imports `polaris_v6.api.runs` → imports `polaris_v6.queue.actors` → top of actors.py calls `get_broker()` → reads env → sets Redis broker → THEN `@dramatiq.actor` decorations bind correctly.
- `dramatiq polaris_v6.queue.actors` → imports the module → same sequence.
- `tests/v6/conftest.py` sets `POLARIS_V6_QUEUE_USE_STUB=1` then calls `get_broker(use_stub=True)` → `_INITIALIZED=True`. Test imports actors → actors.py calls `get_broker()` → returns the already-set stub. Same broker object. Conftest's `_SHARED_TEST_BROKER` reference stays valid.

**No subprocess init needed.** `scripts/v6_init_broker.py` from iter 2 is DROPPED. Entrypoint just exec's uvicorn / dramatiq directly; the module-level guard in actors.py is the single source of truth.

### Test impact

Existing `tests/v6/test_actors.py` passes unchanged (same broker continues to be the stub). New test added:

```python
# tests/v6/test_broker_init_order.py
def test_get_broker_is_idempotent(monkeypatch):
    """Regression for I-carney-005 P1-001: repeated get_broker calls don't
    overwrite an already-set broker."""
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    # Reset the sentinel so we get a fresh first-call from this test.
    from polaris_v6.queue import broker as br
    br._INITIALIZED = False
    b1 = br.get_broker()
    b2 = br.get_broker()
    assert b1 is b2
```

## Scope (final, after iter 1+2+3 P1 resolutions)

Files:
- NEW `Dockerfile.v6` (~50 LOC) — installs requirements.txt + requirements-v6.txt + gnupg
- NEW `scripts/v6_entrypoint.sh` — `api|worker|migrate|preflight|shell` subcommands; no broker init helper (P1-001 handled in actors.py)
- NEW `web/Dockerfile` (~30 LOC) — multi-stage Next.js 16 build, NEXT_PUBLIC_BACKEND_URL arg
- NEW `docker-compose.v6.yml` — redis + api + worker + webui; env_file: .env; writable GPG homedir
- NEW `scripts/bootstrap_gpg_demo_key.sh` — idempotent ed25519 signing-only subkey
- NEW `docs/deploy_runbook.md` — single-page operator runbook
- NEW `scripts/v6_preflight.py` — redis-py ping + GPG keyring check + env-var diag
- PATCH `src/polaris_v6/queue/broker.py` — `_INITIALIZED` idempotence
- PATCH `src/polaris_v6/queue/actors.py` — `_ensure_broker()` at module top
- PATCH `web/next.config.ts` — `output: 'standalone'` + `/api/v6/*` rewrite
- PATCH `web/lib/api.ts` — fetch URLs go through `/api/v6` prefix (browser-relative)
- NEW `tests/v6/test_broker_init_order.py` — P1-001 regression

## P2 resolutions (all accepted iter 2)

- Webui healthcheck: `wget --spider http://localhost:3000 || exit 1` (busybox built-in on alpine)
- Preflight uses redis-py
- bootstrap_gpg_demo_key.sh checks `gpg --list-keys "POLARIS Carney Demo"` for idempotence

## Acceptance criteria (unchanged from iter 1, +1 from iter 3)

1. `docker compose -f docker-compose.v6.yml config` parses clean
2. `Dockerfile.v6` builds in CI without private-registry access
3. `scripts/v6_entrypoint.sh` shellcheck-clean
4. `wait-for-redis` polling loop ≤10s timeout
5. `bootstrap_gpg_demo_key.sh` idempotent
6. `docs/deploy_runbook.md` has prereqs / start / smoke / rollback / troubleshoot sections
7. No secrets committed
8. Pipeline-B `Dockerfile` + `docker-compose.yml` untouched
9. **NEW (iter 3):** `tests/v6/test_broker_init_order.py` passes; existing `tests/v6/test_actors.py` passes unchanged

## Direct questions iter 3

1. P1-001 fix via module-level `_INITIALIZED` sentinel in broker.py + top-of-module `_ensure_broker()` in actors.py — APPROVE'd?
2. Dropping `scripts/v6_init_broker.py` subprocess helper from iter-2 (since same-process init via module guard is sufficient) — APPROVE'd?
3. Anything else blocking iter-3 APPROVE?

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
