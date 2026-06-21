"""Shared HARD total-deadline force-close helper for the role-transport POST (I-beatboth-006 #1283).

Fix A lifts the PROVEN OpenRouter-side total-deadline wrapper into a self-contained, pure helper
so the SOVEREIGN `openai_compatible_transport.py` POST is bounded by the SAME force-close wall the
OpenRouter path uses — a trickle-hung sovereign socket on a D8 claim worker can no longer hang the
gate forever. The wrapper runs the blocking POST on a 1-worker executor, waits at most ``total_s``,
and on expiry FORCE-CLOSES the client so the orphaned worker's blocked C-level read errors out and
the thread exits. On exhaustion the caller raises the UNCHANGED fail-closed ``RoleTransportError``
(consumed per-claim by Fix C). FAITHFULNESS-NEUTRAL: this is transport client lifecycle + a wall-
deadline only — no verdict logic, no gate threshold.

Scope note (I-beatboth-006 #1283, design §3.1.1 + §5/§6 reconciliation): the OpenRouter transport
(`openrouter_role_transport.py`) RETAINS its proven IN-PLACE copy of ``_post_with_total_deadline`` /
``_role_transport_total_s`` / ``_default_role_http_client`` this PR — it is the battle-tested path
(F3 / #1264 / #1226 / #1173) and is listed clean/no-change in the design's §6, so it is NOT touched
here. Only the sovereign transport imports this module. Migrating OpenRouter to import from here is a
DISCLOSED follow-up (a 2-line import swap), kept out of this reliability PR so the proven path stays
byte-identical. The two copies are KEPT IN SYNC — same pattern the local convention already uses
between these two transports (cf. ``_SENTINEL_DECOMPOSITION_MIN_MAX_TOKENS`` "Kept in sync with
openrouter_role_transport...").

LAW VI: every knob is env-driven (``PG_ROLE_TRANSPORT_TOTAL_S``), read at CALL time so a slate env
override after import wins. No magic numbers.
"""

from __future__ import annotations

import concurrent.futures
import os

import httpx

# The per-call total wall-deadline default. Mirrors openrouter_role_transport._role_transport_total_s
# (kept in sync): 900s comfortably exceeds a HEALTHY seconds-to-minutes role call (so the healthy path
# is byte-identical) while bounding a trickle hang. LAW VI: env-driven, read at CALL time.
_ROLE_TRANSPORT_TOTAL_S_ENV = "PG_ROLE_TRANSPORT_TOTAL_S"
_ROLE_TRANSPORT_TOTAL_S_DEFAULT = "900"


def role_transport_total_s() -> float:
    """The per-call total wall-deadline (seconds), read at CALL time so a slate env override wins.

    Mirror of ``openrouter_role_transport._role_transport_total_s`` (kept in sync). A non-numeric /
    unparseable override falls back to the generous 900s default (never aborts every call at 0s).
    """
    try:
        return float(os.getenv(_ROLE_TRANSPORT_TOTAL_S_ENV, _ROLE_TRANSPORT_TOTAL_S_DEFAULT))
    except (TypeError, ValueError):
        return float(_ROLE_TRANSPORT_TOTAL_S_DEFAULT)


def default_role_http_client(timeout_seconds: int) -> httpx.Client:
    """Rebuild a fresh role-transport client after a total-deadline FORCE-CLOSE (prod path only).

    Only ever invoked on a genuine trickle-hang timeout — NEVER in tests, where the injected
    MockTransport returns instantly so the deadline never fires. Role headers are per-request and the
    endpoint URL is absolute, so a timeout-configured client is sufficient for ``/chat/completions``.
    Mirrors ``openrouter_role_transport._default_role_http_client`` (kept in sync).
    """
    return httpx.Client(timeout=timeout_seconds)


def post_with_total_deadline(client, url, *, json_body, headers, timeout, total_s):
    """Run the blocking role POST under a HARD total wall-deadline; force-close the client on expiry.

    Returns the ``httpx.Response`` on success; re-raises ``concurrent.futures.TimeoutError`` (after
    force-closing the hung client) so the caller's bounded retry can rebuild + retry, then fail closed.
    Byte-identical in shape to ``openrouter_role_transport._post_with_total_deadline`` (kept in sync).
    """
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(client.post, url, json=json_body, headers=headers, timeout=timeout)
    try:
        return fut.result(timeout=total_s)
    except concurrent.futures.TimeoutError:
        try:
            client.close()  # force the hung socket closed -> the worker's blocked read unblocks + exits
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        # Deterministic executor teardown on EVERY exit path; wait=False so an unsticking worker never blocks us.
        ex.shutdown(wait=False)
