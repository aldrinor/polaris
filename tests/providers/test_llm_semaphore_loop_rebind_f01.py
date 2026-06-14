"""F01 (A3) regression: the global LLM concurrency semaphore must REBIND to the
running event loop, so the Gate-B ``--all`` cert run (one ``asyncio.run`` per
question = a fresh loop per query) does not raise
``RuntimeError: ... bound to a different event loop`` on Q2..Q5.

Pre-fix: ``get_semaphore()`` cached a single ``asyncio.Semaphore`` created in the
first loop that touched it. Query 1 ran fine; query 2's ``asyncio.run`` created a
NEW loop, and ``async with semaphore`` against the query-1-loop semaphore raised
RuntimeError, killing every remaining cert question.

Post-fix: the semaphore is keyed to the loop it was created in and recreated when
the running loop differs. Also covers F16 (PG_MAX_CONCURRENT_LLM read at call time).
"""
from __future__ import annotations

import asyncio
import importlib

import pytest


@pytest.fixture()
def provider_mod():
    mod = importlib.import_module("src.providers.llm_provider")
    mod.reset_semaphore()
    yield mod
    mod.reset_semaphore()


# Forensic NEW-1: the bug fires on the CONTENDED acquire (>cap calls in flight),
# which binds _LoopBoundMixin._loop. A fanout above the cap forces that contention,
# matching the generation fan-out on the real run. cap default = 5, so 12 contends.
_FANOUT = 12


def _query_with_fanout(mod) -> int:
    """Mirror the Gate-B per-query pattern: one fresh asyncio.run() that drives a
    CONTENDED fanout through the module-global semaphore (forces the loop binding
    that the bug trips over). Returns the semaphore id() so a rebind is observable."""

    async def _worker(sem) -> None:
        async with sem:
            await asyncio.sleep(0)

    async def _inner() -> int:
        sem = mod.get_semaphore()
        await asyncio.gather(*[_worker(sem) for _ in range(_FANOUT)])
        return id(sem)

    return asyncio.run(_inner())


def test_module_global_semaphore_genuinely_poisons_across_loops() -> None:
    """Ground-truth (control): a NON-rebinding module-global Semaphore — the exact
    pre-fix shape — DOES raise 'bound to a different event loop' on the second query.
    This proves the fix is load-bearing, and the repro is faithful (cap=5 fanout=12)."""
    stale = {"sem": None}

    async def _q() -> None:
        if stale["sem"] is None:
            stale["sem"] = asyncio.Semaphore(5)  # pre-fix: no per-loop rebind

        async def _w() -> None:
            async with stale["sem"]:
                await asyncio.sleep(0.001)

        await asyncio.gather(*[_w() for _ in range(_FANOUT)])

    asyncio.run(_q())  # query 1 binds the loop
    with pytest.raises(RuntimeError, match="different event loop"):
        asyncio.run(_q())  # query 2 fresh loop -> contended acquire RAISES


def test_get_semaphore_rebind_survives_two_queries(provider_mod) -> None:
    """The fix: the SAME contended 2-query repro through get_semaphore() must NOT
    raise — each query gets a semaphore bound to its own loop. This is the
    'Codex 2-query repro RAISE -> pass' acceptance for F01."""
    id1 = _query_with_fanout(provider_mod)
    id2 = _query_with_fanout(provider_mod)  # pre-fix: RuntimeError here
    assert id1 != id2  # rebound for the second loop


def test_acquire_within_same_loop_reuses_one_semaphore(provider_mod) -> None:
    """Within ONE loop the semaphore is reused (not recreated each call), so the
    concurrency cap is honored across all calls in a query."""

    async def _inner() -> None:
        a = provider_mod.get_semaphore()
        b = provider_mod.get_semaphore()
        assert a is b  # same loop => same semaphore object
        # Two concurrent acquisitions within the cap succeed without deadlock.
        async with a:
            async with b:
                await asyncio.sleep(0)

    asyncio.run(_inner())


def test_get_semaphore_rebinds_loop_reference(provider_mod) -> None:
    """The rebind is load-bearing: get_semaphore() records the loop it created the
    semaphore in and recreates it whenever the running loop differs. We assert the
    recorded loop reference tracks each fresh asyncio.run() loop, which is exactly
    what prevents the 'bound to a different event loop' RuntimeError.

    (Note: a stale Semaphore does not raise on an UNCONTENDED acquire under some
    CPython versions — the loop binding is lazy/contention-dependent — so we assert
    the rebind mechanism directly rather than relying on the stale object raising.)"""
    captured = {}

    async def _capture(key: str) -> None:
        provider_mod.get_semaphore()
        captured[key] = provider_mod._LLM_SEMAPHORE_LOOP

    asyncio.run(_capture("loop1"))
    loop1_ref = captured["loop1"]
    asyncio.run(_capture("loop2"))
    loop2_ref = captured["loop2"]

    # Each query's get_semaphore() bound to that query's OWN loop (different objects).
    assert loop1_ref is not None
    assert loop2_ref is not None
    assert loop1_ref is not loop2_ref

    # And a real acquire in a fresh loop never raises (the end-user guarantee).
    async def _fresh() -> None:
        async with provider_mod.get_semaphore():
            await asyncio.sleep(0)

    asyncio.run(_fresh())  # must not raise


def test_max_concurrent_llm_read_at_call_time_f16(provider_mod, monkeypatch) -> None:
    """F16: PG_MAX_CONCURRENT_LLM is read when the semaphore is CREATED, not frozen
    at import — so the Gate-B slate (which mutates os.environ after import) lands."""
    monkeypatch.setenv("PG_MAX_CONCURRENT_LLM", "9")
    provider_mod.reset_semaphore()

    async def _inner() -> int:
        sem = provider_mod.get_semaphore()
        return sem._value  # initial permits == the configured cap

    assert asyncio.run(_inner()) == 9
    assert provider_mod._max_concurrent_llm() == 9


def test_max_concurrent_llm_malformed_falls_back(provider_mod, monkeypatch) -> None:
    """A malformed cap must fall back to the default, never crash the run."""
    monkeypatch.setenv("PG_MAX_CONCURRENT_LLM", "not-an-int")
    assert provider_mod._max_concurrent_llm() == provider_mod._MAX_CONCURRENT_LLM
    monkeypatch.setenv("PG_MAX_CONCURRENT_LLM", "0")
    assert provider_mod._max_concurrent_llm() == provider_mod._MAX_CONCURRENT_LLM


def test_max_concurrent_llm_unset_is_default(provider_mod, monkeypatch) -> None:
    """Byte-identical when unset: the default cap is preserved."""
    monkeypatch.delenv("PG_MAX_CONCURRENT_LLM", raising=False)
    assert provider_mod._max_concurrent_llm() == provider_mod._MAX_CONCURRENT_LLM
