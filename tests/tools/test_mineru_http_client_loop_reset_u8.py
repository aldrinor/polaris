"""I-deepfix-001 U8 (#1344): mineru25 vlm-http-client cross-loop Semaphore reset.

THE BUG
-------
The W4 clinical-PDF winner (MinerU 2.5) on the ``vlm-http-client`` backend drives
the THIRD-PARTY ``mineru_vl_utils`` HttpVlmClient, which caches ONE process-wide
async client whose ``asyncio.Semaphore(1)`` binds (Python ``_LoopBoundMixin``) to
the FIRST event loop that WAITS on it. ``AccessBypass._mineru25_extract`` runs on a
fetch-worker thread via ``run_in_executor`` (NO running loop), so MinerU's
``do_parse`` falls back to ``asyncio.run()`` — a FRESH loop — for EVERY extraction.
The 2nd extraction then trips
``RuntimeError: <Semaphore ...> is bound to a different event loop`` inside the
client, which the W4 circuit breaker counts as a genuine failure and, after 3,
OPENS the breaker so every clinical PDF silently degrades to Docling (observed
live: drb_78). Same class as the crawl4ai loop-keyed cache (#1227,
``test_g4_crawl4ai_blockers.py``).

THE FIX
-------
``_reset_mineru_http_client_loop_state()`` — called on the vlm-http-client path
immediately before each ``do_parse`` — swaps the cached client's loop-bound
``asyncio.Semaphore(1)`` for a fresh (unbound) one and clears its per-loop client
cache, so every extraction sees clean loop state and both calls succeed.

CONTENTION MATTERS (mirrors test_g4)
------------------------------------
``asyncio.Semaphore.acquire()`` only calls ``_get_loop()`` (the loop-binding step)
when the semaphore is already LOCKED and the caller must WAIT. An uncontended
acquire (value > 0) takes the fast path and never binds. The fake ``do_parse``
below therefore DRAINS the one slot then attempts a SECOND acquire that must wait
— that wait is what binds the loop and makes the OFF/no-reset path raise while the
ON/reset path succeeds.

FAITHFULNESS
------------
Pure reliability: nothing here touches strict_verify, the NLI judge, the 4-role
audit, or any provenance/span-grounding gate. The fix mutates only the extractor's
async plumbing inside a third-party client — never WHICH PDFs are extracted, the
verbatim text, or any faithfulness gate (all downstream and untouched).
"""

import asyncio
import sys
import types

import pytest

from src.tools import access_bypass


# Short wait so the contended 2nd acquire blocks long enough to enter the
# loop-binding wait path, then times out instead of hanging the test.
_CONTENTION_WAIT_SECONDS = 0.02


class _FakeHttpVlmClient:
    """Stand-in for mineru_vl_utils.HttpVlmClient: carries the process-wide,
    loop-bound async state the real client caches."""

    def __init__(self):
        # Created OUTSIDE any running loop -> unbound until first contended use,
        # exactly like the real module-cached client.
        self._aio_client_sem = asyncio.Semaphore(1)
        self._aio_client_cache = {}


class _FakePredictor:
    def __init__(self, client):
        self.client = client


class _FakeModelSingleton:
    """Real singleton: ``ModelSingleton()`` always returns the shared instance
    holding ``_models`` (mirrors mineru.backend.vlm.vlm_analyze.ModelSingleton)."""

    _instance = None
    _models: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class _FakeMineruState:
    """Records what each ``do_parse`` observed at entry so the test can assert the
    reset actually swapped the semaphore + cleared the cache before each call."""

    def __init__(self):
        self.entry_sem_ids: list[int] = []
        self.entry_cache_lens: list[int] = []


def _make_do_parse(state: _FakeMineruState):
    """Build a fake ``mineru.cli.common.do_parse`` that reproduces the cross-loop
    Semaphore failure: it drains + contends the cached client's semaphore inside a
    per-call ``asyncio.run`` loop (binding it), then writes a markdown file so a
    successful call returns >500 chars (the W4 success threshold)."""

    def do_parse(*_args, **kwargs):
        from pathlib import Path

        singleton = _FakeModelSingleton()
        predictor = next(iter(singleton._models.values()))
        client = predictor.client

        # Record what we saw at entry (post-reset on the fixed path).
        state.entry_sem_ids.append(id(client._aio_client_sem))
        state.entry_cache_lens.append(len(client._aio_client_cache))

        async def _use():
            sem = client._aio_client_sem
            await sem.acquire()  # value 1 -> 0, fast path, NO loop bind
            try:
                # value 0 -> must WAIT -> _get_loop() binds THIS loop (or raises
                # if the sem is bound to a prior, different loop).
                await asyncio.wait_for(sem.acquire(), _CONTENTION_WAIT_SECONDS)
            except (asyncio.TimeoutError, TimeoutError):
                pass  # expected: nobody releases the slot
            finally:
                sem.release()  # restore value to 1 for the next call
            client._aio_client_cache["used"] = True

        # Mirrors mineru_vl_utils: a fresh event loop per do_parse call.
        asyncio.run(_use())

        # Emit the markdown do_parse would have written (>500 chars -> W4 "ok").
        out_dir = kwargs.get("output_dir")
        name = kwargs.get("pdf_file_names", ["doc"])[0]
        md_dir = Path(out_dir) / name / "vlm"
        md_dir.mkdir(parents=True, exist_ok=True)
        (md_dir / f"{name}.md").write_text("X" * 600, encoding="utf-8")

    return do_parse


def _install_fake_mineru(monkeypatch, state: _FakeMineruState):
    """Inject a minimal fake ``mineru`` package tree into ``sys.modules`` so the
    production imports (``from mineru.cli.common import do_parse`` and
    ``from mineru.backend.vlm.vlm_analyze import ModelSingleton``) resolve without
    the real GPU package installed."""
    # Fresh singleton state per install.
    _FakeModelSingleton._instance = None
    client = _FakeHttpVlmClient()
    _FakeModelSingleton._models = {"winner": _FakePredictor(client)}

    mineru = types.ModuleType("mineru")
    mineru.__path__ = []  # mark as package
    cli = types.ModuleType("mineru.cli")
    cli.__path__ = []
    common = types.ModuleType("mineru.cli.common")
    common.do_parse = _make_do_parse(state)
    backend = types.ModuleType("mineru.backend")
    backend.__path__ = []
    vlm = types.ModuleType("mineru.backend.vlm")
    vlm.__path__ = []
    vlm_analyze = types.ModuleType("mineru.backend.vlm.vlm_analyze")
    vlm_analyze.ModelSingleton = _FakeModelSingleton

    mineru.cli = cli
    cli.common = common
    mineru.backend = backend
    backend.vlm = vlm
    vlm.vlm_analyze = vlm_analyze

    for name, mod in [
        ("mineru", mineru),
        ("mineru.cli", cli),
        ("mineru.cli.common", common),
        ("mineru.backend", backend),
        ("mineru.backend.vlm", vlm),
        ("mineru.backend.vlm.vlm_analyze", vlm_analyze),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    return client


@pytest.fixture
def fake_mineru(monkeypatch):
    state = _FakeMineruState()
    client = _install_fake_mineru(monkeypatch, state)
    # Route _mineru25_extract down the vlm-http-client path (U8's path).
    monkeypatch.setenv("PG_MINERU25_BACKEND", "vlm-http-client")
    monkeypatch.setenv("PG_MINERU25_SERVER_URL", "http://fake-mineru:8000")
    return types.SimpleNamespace(state=state, client=client)


def _extract_via_executor(pdf_bytes: bytes) -> str:
    """Mirror production: run the static ``_mineru25_extract`` on an executor
    thread (no running loop) from within an outer loop, so ``do_parse`` does its
    own per-call ``asyncio.run``."""

    async def _drive():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, access_bypass.AccessBypass._mineru25_extract, pdf_bytes
        )

    return asyncio.run(_drive())


# ---------------------------------------------------------------------------
# RED: with the reset DISABLED, the 2nd do_parse (fresh loop) trips the
# cross-loop RuntimeError — the exact U8 failure that opens the W4 circuit.
# ---------------------------------------------------------------------------
def test_u8_second_do_parse_raises_cross_loop_without_reset(fake_mineru, monkeypatch):
    # Disable the fix -> reproduce the broken behavior.
    monkeypatch.setattr(
        access_bypass, "_reset_mineru_http_client_loop_state", lambda: None
    )

    first = _extract_via_executor(b"pdf-1")
    assert len(first) == 600  # first extraction succeeds and binds the semaphore

    with pytest.raises(RuntimeError) as excinfo:
        _extract_via_executor(b"pdf-2")
    assert "bound to a different event loop" in str(excinfo.value)


# ---------------------------------------------------------------------------
# GREEN: with the reset ENABLED (production wiring), both extractions succeed;
# the semaphore object is swapped (fresh id) and the cache is cleared before
# EACH call.
# ---------------------------------------------------------------------------
def test_u8_reset_before_each_call_makes_both_extractions_succeed(fake_mineru):
    state = fake_mineru.state

    first = _extract_via_executor(b"pdf-1")
    second = _extract_via_executor(b"pdf-2")

    assert len(first) == 600
    assert len(second) == 600  # no cross-loop RuntimeError on the 2nd call

    # Reset ran before each do_parse: two DISTINCT semaphore objects were seen at
    # entry (the fix swapped in a fresh Semaphore(1) each time)...
    assert len(state.entry_sem_ids) == 2
    assert state.entry_sem_ids[0] != state.entry_sem_ids[1]
    # ...and the per-loop client cache was CLEARED before each call.
    assert state.entry_cache_lens == [0, 0]


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
