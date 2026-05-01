# Per-commit Codex brief — `466b662`

**Commit:** `466b662 PL: v6.2 F-9 root_cause — pin dramatiq + opentelemetry deps in requirements.txt`
**Format:** v2 minimal
**Files changed (1):** `requirements.txt` (+12 lines, new "POLARIS v6 — Dramatiq queue + OpenTelemetry GenAI semconv" section)

## What this commit does

Closes cycle-3 audit P1.2 — the only **root_cause** finding in the cycle. Subagent caught that 4 new test files (`test_otel_propagate_middleware.py`, `test_sticky_connection_middleware.py`, `test_throttle_middleware.py`, `test_otel_init.py`) used `pytest.importorskip` against `dramatiq` + `opentelemetry`, but those packages weren't pinned in `requirements.txt`. On a fresh CI runner, tests would silently SKIP — exactly the LAW II "no silent fallback" violation.

Pins added (verified via `pip index versions <pkg>`):
- `dramatiq>=2.1.0` — actors, brokers, middleware base class. INSTALLED locally as 2.1.0.
- `opentelemetry-api>=1.36.0` — tracer + propagate APIs. Matches Phase 0 Task 0.10 errata E-2 baseline.
- `opentelemetry-sdk>=1.36.0` — TracerProvider + BatchSpanProcessor.
- `opentelemetry-exporter-otlp-proto-grpc>=1.36.0` — needed by `src/polaris_v6/observability/otel_init.py` OTLP exporter.

## Acceptance criteria

1. **All 4 deps actually exist on PyPI at the pinned versions** — verified via `pip index versions <pkg>` (each returned the pinned version in the available list).
2. **No version downgrade** — pins are `>=` from the version installed locally; CI can use newer if available.
3. **Comment block explains WHY** — per cycle-3 brief discipline, future engineers see the "this fixes a CI silent-skip" reasoning.
4. **No accidental dep removal** — diff is purely additive (+12, -0).
5. **No transitive duplication** — verify these aren't already pulled in via `langchain-community` or similar (they aren't; cycle-3 audit verified `grep -iE "dramatiq|opentelemetry" requirements.txt` returned nothing pre-fix).

## Codex focus

- **P0:** Have I verified that `pip install -r requirements.txt` on a fresh ubuntu-latest actually installs all 4? `opentelemetry-exporter-otlp-proto-grpc` may have system-level grpc deps that fail without `apt-get install build-essential`. Test by spinning up a fresh container.
- **P1:** The `>=` pins allow newer versions. opentelemetry has a track record of breaking-change minor bumps (e.g., 1.36 → 1.37 dropped some experimental APIs). Should we pin `==1.36.x` instead? Trade-off: stability vs security patches.
- **P2:** No `requirements-api.txt` minimal subset created (cycle-1 P2.2 deferred). Adding 4 deps here grows the install surface; consider splitting api-only requirements when CI install-time becomes a bottleneck.

## Cross-review

Lands at `outputs/audits/continuous/466b662/cross_review.md`.
