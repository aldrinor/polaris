"""I-deepfix-001 U8 (#1344): mineru vlm-http-client cross-loop Semaphore reset —
helper units (RETAINED as defensive utilities after the Box-C rewrite).

HISTORY: on the old in-process ``vlm-http-client`` backend, MinerU's THIRD-PARTY
``mineru_vl_utils`` HttpVlmClient cached ONE process-wide async client whose
``asyncio.Semaphore(1)`` bound to the FIRST event loop, so the 2nd extraction on a
fresh fetch-worker loop tripped ``RuntimeError: <Semaphore ...> is bound to a
different event loop`` and opened the W4 circuit (drb_78).
``_reset_mineru_http_client_loop_state()`` de-wedged that client before each
in-process ``do_parse``.

Box-C RETIRED the in-process path entirely: ``AccessBypass._mineru25_extract``
now shells out to the isolated-venv ``mineru`` CLI in ``vlm-http-client`` mode (a
subprocess) talking to the resident ``mineru-vllm-server``, and never touches
MinerU's in-process HttpVlmClient — so the cross-loop-Semaphore failure class
cannot occur in the pipeline process. The two former INTEGRATION tests (which
drove ``_mineru25_extract`` through a fake in-process ``do_parse``) are removed
because that path no longer exists; see
``tests/tools/test_mineru25_http_client_boxc.py`` for the CLI-subprocess transport
behavior and ``tests/polaris_graph/test_mineru25_gpu_lock_serialization.py`` for
the retirement regression guard.

The ``_reset_loop_bound_client`` / ``_reset_mineru_http_client_loop_state``
helpers remain in the module as defensive, side-effect-free utilities; these unit
tests keep them honest (pure / fully guarded / loud-not-fatal).

FAITHFULNESS: pure reliability plumbing — nothing here touches strict_verify, the
NLI judge, the 4-role audit, or any provenance / span-grounding gate.
"""

import asyncio
import sys

from src.tools import access_bypass


class _FakeHttpVlmClient:
    """Stand-in for mineru_vl_utils.HttpVlmClient: carries the process-wide,
    loop-bound async state the real client caches."""

    def __init__(self):
        # Created OUTSIDE any running loop -> unbound until first contended use,
        # exactly like the real module-cached client.
        self._aio_client_sem = asyncio.Semaphore(1)
        self._aio_client_cache = {}


# ---------------------------------------------------------------------------
# Defensive path: absent package (import fails) => quiet no-op, never raises.
# ---------------------------------------------------------------------------
def test_reset_absent_package_is_quiet_noop(monkeypatch):
    # Ensure no fake mineru is installed, then block any real import of `mineru`.
    for name in list(sys.modules):
        if name == "mineru" or name.startswith("mineru."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    # A None entry in sys.modules makes `import mineru...` raise ImportError.
    monkeypatch.setitem(sys.modules, "mineru", None)

    # Must return without raising (the caller's Docling fallback still runs).
    access_bypass._reset_mineru_http_client_loop_state()


# ---------------------------------------------------------------------------
# Defensive path: missing-attribute / None holders => False, never raises.
# ---------------------------------------------------------------------------
def test_reset_loop_bound_client_defensive_shapes():
    assert access_bypass._reset_loop_bound_client(None) is False
    assert access_bypass._reset_loop_bound_client(object()) is False

    class _NoAttrs:
        pass

    assert access_bypass._reset_loop_bound_client(_NoAttrs()) is False


def test_reset_loop_bound_client_swaps_sem_and_clears_cache():
    client = _FakeHttpVlmClient()
    client._aio_client_cache["stale"] = "x"
    old_sem = client._aio_client_sem

    assert access_bypass._reset_loop_bound_client(client) is True
    assert client._aio_client_sem is not old_sem  # fresh Semaphore
    assert isinstance(client._aio_client_sem, asyncio.Semaphore)
    assert client._aio_client_cache == {}  # cleared


def test_reset_loop_bound_client_readonly_attr_is_loud_not_fatal(caplog):
    """A present-but-unsettable ``_aio_client_sem`` (read-only property) must be
    logged LOUDLY (W4-CANARY) and swallowed, never raised."""

    class _ReadOnlySem:
        @property
        def _aio_client_sem(self):  # present -> hasattr True
            return asyncio.Semaphore(1)
        # no setter -> setattr raises AttributeError

    with caplog.at_level("WARNING"):
        # Must not raise; returns False (nothing successfully reset).
        assert access_bypass._reset_loop_bound_client(_ReadOnlySem()) is False
    assert any("W4-CANARY" in rec.message for rec in caplog.records)
