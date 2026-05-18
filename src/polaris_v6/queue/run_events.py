"""I-arch-001e — durable replayable SSE event log via Redis Streams.

Pipeline-A emits stage events via sync `emit_event()` (non-raising). The SSE
endpoint `stream.py` reads via async `read_events()` and translates to the v6
canonical event protocol. Last-Event-ID resume is honored.

Per Codex iter-1: emit MUST be non-raising — Redis observability failure cannot
become a pipeline-A `error_unexpected`. Terminal events fire at all 7 exit
paths in pipeline-A's `run_one_query`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

EVENT_STREAM_KEY = "polaris:events:{run_id}"
_LAST_EVENT_ID_RE = re.compile(r"^\d+-\d+$")
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
STREAM_MAX_LEN = 10_000


def _redis_url() -> str:
    return os.environ.get("POLARIS_V6_REDIS_URL", DEFAULT_REDIS_URL)


def _get_sync_redis():
    """Lazy redis import — keeps test-suite importable without redis installed."""
    import redis  # noqa: PLC0415 — lazy to defer ImportError to call site
    return redis.Redis.from_url(_redis_url())


def _validate_last_event_id(raw: str | None) -> str:
    """Last-Event-ID must match `<ms>-<seq>` (Redis stream-id format).

    Bad input → fall back to "0-0" (read from beginning). Caller can supply
    None or empty string to mean same thing.
    """
    if not raw:
        return "0-0"
    return raw if _LAST_EVENT_ID_RE.match(raw) else "0-0"


def emit_event(
    external_run_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    *,
    redis_client=None,
) -> None:
    """Best-effort, non-raising XADD to `polaris:events:{run_id}`.

    Per Codex iter-1 P1-2: pipeline-A's run_one_query MUST NOT raise
    error_unexpected because Redis is down. All exceptions are caught
    and logged at WARN.
    """
    if not external_run_id:
        return
    try:
        client = redis_client or _get_sync_redis()
        client.xadd(
            EVENT_STREAM_KEY.format(run_id=external_run_id),
            {
                "event_type": event_type,
                "payload": json.dumps(payload, default=str),
            },
            maxlen=STREAM_MAX_LEN,
            approximate=True,
        )
    except ImportError:
        # redis library not installed (test environment) — silent noop.
        return
    except Exception as exc:  # noqa: BLE001 — observability MUST NEVER block pipeline
        # Catch ALL exceptions, not just RedisError, per Codex iter-2 P3 cosmetic.
        logger.warning(
            "[run_events] emit failed run_id=%s event_type=%s: %s",
            external_run_id,
            event_type,
            exc,
        )


def emit_terminal_event(
    external_run_id: str | None,
    pipeline_status: str,
    error_msg: str | None = None,
    *,
    redis_client=None,
) -> None:
    """Single helper for the 7 pipeline-A exit paths.

    Emits a `run.completed` event that the translator maps to v6 `run_complete`
    with payload.status carrying the original pipeline_status (success /
    partial_* / abort_* / error_unexpected / stream_lost).
    """
    payload: dict[str, Any] = {"status": pipeline_status}
    if error_msg:
        payload["error"] = error_msg
    emit_event(external_run_id, "run.completed", payload, redis_client=redis_client)


# Translator: pipeline-A event_type → (v6_event_name, transform_fn).
# All terminal pipeline-A events (run.completed/aborted/failed) collapse to v6
# `run_complete` carrying the original status.
_TRANSLATOR: dict[str, tuple[str, Any]] = {
    "scope_gate.completed": ("scope_decision", lambda p: {
        "verdict": p.get("decision", "unknown"),
        "reason": p.get("reason", ""),
    }),
    "corpus_adequacy.completed": ("retrieval_progress", lambda p: {
        "sources_found": p.get("pool_size", 0),
        "tier_breakdown": p.get("tier_counts", {}),
    }),
    "evidence.id_assigned": ("evidence_id", lambda p: {
        "evidence_id": p.get("id", ""),
        "source_url": p.get("url", ""),
    }),
    "strict_verify.section_completed": ("verifier_verdict", lambda p: {
        "section": p.get("section", ""),
        "local_pass": p.get("local", False),
        "global_pass": p.get("global", False),
    }),
    "generator.section_completed": ("section_complete", lambda p: {
        "section": p.get("section", ""),
        "verified_sentences": p.get("verified", 0),
        "dropped": p.get("dropped", 0),
    }),
    "run.completed": ("run_complete", lambda p: dict(p)),  # passthrough
}


def translate(pipeline_event: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Translate a pipeline-A event payload to v6 (name, payload) or None."""
    event_type = pipeline_event.get("event_type")
    mapping = _TRANSLATOR.get(event_type or "")
    if mapping is None:
        return None
    v6_name, payload_fn = mapping
    try:
        payload = json.loads(pipeline_event.get("payload", "{}"))
    except json.JSONDecodeError:
        payload = {}
    return v6_name, payload_fn(payload)


# Grace period (seconds) after run_store reports lifecycle_status terminal but
# no Redis terminal event has been seen. After this elapses, emit a synthetic
# `run_complete(status=stream_lost)` so the client gets a deterministic close
# rather than hanging on keepalives forever. Per Codex iter-2 P1-3 + diff iter-1.
STREAM_LOST_GRACE_SECONDS = 10.0


def _get_lifecycle_status(external_run_id: str) -> str | None:
    """Best-effort sync run_store lookup. Returns lifecycle_status or None.

    Imported lazily so tests that don't touch run_store don't pay sqlite init.
    Any failure (missing DB, import error, schema drift) returns None so the
    reader keeps emitting keepalives rather than synthesizing a stream_lost
    terminal on transient backend hiccups.
    """
    try:
        from polaris_v6.queue import run_store  # noqa: PLC0415

        row = run_store.get_run(external_run_id)
        if row is None:
            return None
        return getattr(row, "lifecycle_status", None)
    except Exception as exc:  # noqa: BLE001 — observability lookup never blocks SSE
        logger.warning(
            "[run_events] run_store lookup failed run_id=%s: %s",
            external_run_id,
            exc,
        )
        return None


async def _check_lifecycle_terminal(external_run_id: str) -> bool:
    """Async wrapper for the sync sqlite lookup."""
    import asyncio  # noqa: PLC0415
    status = await asyncio.to_thread(_get_lifecycle_status, external_run_id)
    # I-rdy-011 (#507): `cancelled` is terminal — a queued-cancel writes no
    # Redis terminal event, so without this an SSE consumer would hang on
    # keepalives until the run is forgotten.
    return status in ("completed", "failed", "cancelled")


def _is_connection_failure(exc: BaseException) -> bool:
    """Narrow stream_unavailable to actual Redis reachability failures.

    Per Codex diff iter-1 P1: every XREAD exception was being mapped to
    stream_unavailable, masking schema bugs / corrupt entries as 'Redis down'.
    Now we treat ONLY connection/timeout/socket failures as unavailability;
    other exceptions surface as stream_lost.
    """
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    # redis.asyncio raises ConnectionError subclasses; check by class name
    # to avoid a hard import dependency.
    name = type(exc).__name__
    return name in {
        "ConnectionError",
        "TimeoutError",
        "BusyLoadingError",
        "ConnectionResetError",
        "RedisConnectionError",
    }


async def read_events(
    external_run_id: str,
    last_event_id: str = "0-0",
    *,
    block_ms: int = 5000,
    redis_client_async=None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Async generator yielding (stream_id, raw_pipeline_event_dict).

    Terminates after emitting a `run.completed` event. Per Codex iter-2 P1-3
    + diff iter-1 P1:

    - empty XREAD window → keepalive (caller emits SSE comment frame), then
      check run_store. While lifecycle_status is queued/in_progress, keep
      emitting keepalives.
    - lifecycle_status in {completed, failed} AND no terminal event seen in
      the next STREAM_LOST_GRACE_SECONDS → emit a synthetic
      run_complete(status=stream_lost) and close cleanly.
    - actual Redis connection/timeout failure → emit
      run_complete(status=stream_unavailable) and close.
    - non-reachability XREAD exception → emit stream_lost and close (treat as
      degraded stream rather than 'Redis down').
    """
    import asyncio  # noqa: PLC0415

    last_id = _validate_last_event_id(last_event_id)
    key = EVENT_STREAM_KEY.format(run_id=external_run_id)

    try:
        if redis_client_async is None:
            import redis.asyncio as aredis  # noqa: PLC0415
            client = aredis.from_url(_redis_url(), decode_responses=False)
        else:
            client = redis_client_async
    except ImportError:
        yield ("0-0", {"event_type": "run.completed", "payload": json.dumps({"status": "stream_unavailable"})})
        return

    # Tracks first-seen-at for lifecycle_status terminal so we can apply the
    # grace window before declaring stream_lost.
    lifecycle_terminal_first_seen: float | None = None
    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                events = await client.xread({key: last_id}, count=100, block=block_ms)
            except Exception as exc:  # noqa: BLE001
                if _is_connection_failure(exc):
                    logger.warning(
                        "[run_events] redis unreachable run_id=%s: %s",
                        external_run_id,
                        exc,
                    )
                    yield ("0-0", {"event_type": "run.completed", "payload": json.dumps({"status": "stream_unavailable"})})
                    return
                # Non-reachability failure — log and degrade to stream_lost.
                logger.warning(
                    "[run_events] xread error run_id=%s: %s",
                    external_run_id,
                    exc,
                )
                yield ("0-0", {"event_type": "run.completed", "payload": json.dumps({"status": "stream_lost"})})
                return

            if not events:
                # Empty XREAD window — emit keepalive then consult run_store.
                yield ("__keepalive__", {})
                if await _check_lifecycle_terminal(external_run_id):
                    now = loop.time()
                    if lifecycle_terminal_first_seen is None:
                        lifecycle_terminal_first_seen = now
                    elif now - lifecycle_terminal_first_seen >= STREAM_LOST_GRACE_SECONDS:
                        logger.warning(
                            "[run_events] lifecycle terminal without redis terminal "
                            "run_id=%s — emitting synthetic stream_lost",
                            external_run_id,
                        )
                        yield ("0-0", {"event_type": "run.completed", "payload": json.dumps({"status": "stream_lost"})})
                        return
                else:
                    # Reset the grace window if the run un-terminals (shouldn't happen,
                    # but the lifecycle is the source of truth).
                    lifecycle_terminal_first_seen = None
                continue

            # Real events arrived → reset the grace window.
            lifecycle_terminal_first_seen = None

            for _stream_name, entries in events:
                for entry_id, fields in entries:
                    stream_id = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    last_id = stream_id
                    event_type = fields.get(b"event_type") or fields.get("event_type")
                    payload = fields.get(b"payload") or fields.get("payload")
                    if isinstance(event_type, bytes):
                        event_type = event_type.decode()
                    if isinstance(payload, bytes):
                        payload = payload.decode()
                    yield (stream_id, {"event_type": event_type, "payload": payload})
                    if event_type == "run.completed":
                        return
    finally:
        # aredis client lazy-closed via context if possible
        try:
            close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        except Exception:  # noqa: BLE001 — defensive close
            pass
