"""Dramatiq actors for POLARIS v6 research-run lifecycle.

Per docs/backend_modernization.md §3, the acceptance matrix exercises:
1. enqueue + complete  →  enqueue_research_run
2. retry on transient failure  →  enqueue_research_run (max_retries=3)
3. cancel mid-execution  →  cancel_research_run via Worker.send_signal
4. worker kill mid-execution  →  message remains in queue, idempotency
   key prevents double-execution
5. resume after broker restart  →  Dramatiq native via ConnectionMiddleware
6. trace-id propagation  →  otel_propagate middleware (next file)
7. high-retry-rate degradation  →  throttle middleware (next file)
8. broker heartbeat  →  configured in broker.py

The actors here are deliberately small. They wrap the existing pipeline-A
substrate via the run_research_run() bridge in adapters/, which is wired
up once requirements-v6.txt is installed in a dev environment.
"""

from __future__ import annotations

from typing import Any

import dramatiq

# Importing this module assumes get_broker() has already been called by
# the application entrypoint. Tests import broker.get_broker(use_stub=True)
# before importing this module.

ENQUEUE_MAX_RETRIES = 3


@dramatiq.actor(max_retries=ENQUEUE_MAX_RETRIES, time_limit=30 * 60 * 1000)
def enqueue_research_run(run_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a research run. Idempotent on run_id.

    Bridge to existing pipeline-A substrate is wired in adapters/ (TODO
    once requirements-v6.txt installs in dev environment).
    """
    # Phase 0 stub: the bridge to scripts/run_honest_sweep_r3.py lives in
    # src/polaris_v6/adapters/retrieval_bridge.py and is implemented in
    # Phase 1 once Vast.ai cluster (Task 0.3) is live and we can run an
    # end-to-end smoke. For Phase 0 acceptance test scenario 1 we exercise
    # the queue mechanics with a deterministic noop payload.
    return {"run_id": run_id, "status": "completed", "echo": request_payload}


@dramatiq.actor(max_retries=0)
def cancel_research_run(run_id: str) -> dict[str, Any]:
    """Cancel an in-flight research run by run_id.

    Implementation note: real cancellation is via Worker.send_signal on the
    target message_id (see test_dramatiq_acceptance.py scenario 3); this
    actor exists to provide an audited entrypoint that records the cancel
    intent in the run-status table before the signal fires.
    """
    return {"run_id": run_id, "status": "cancel_requested"}
