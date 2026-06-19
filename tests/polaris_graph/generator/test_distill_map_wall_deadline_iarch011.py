"""I-arch-011 B19 (KEYSTONE — root cause of the B15 generator hang).

Two BEHAVIORAL assertions, both offline / no network / no spend, run against the
REAL public ``distill_section_evidence`` entry point (not a flag/env check):

  (a) EXPLICIT per-call wall is passed as ``timeout=`` to the live ``distill_map``
      LLM call. Without it, ``openrouter_client._call_impl`` resolves a
      reasoning-first model (deepseek-v4-pro) to ~6530s
      (``GENERATOR_TIMEOUT_SECONDS`` + 30); a half-open SSE socket then hangs the
      asyncio loop for ~1.8h. The fix passes ``PG_DISTILL_MAP_CALL_WALL_S``
      (default 1800) so the explicit branch (``actual_timeout = timeout or
      default``) wins and the call is bounded. PRE-FIX the call had NO ``timeout``
      kwarg -> ``None != 1800.0`` -> this test fails first.

  (b) ONE source's MAP batch raising past the inner guard (a per-call wall timeout
      that escapes ``_map_microbatch``'s ``except``, surfaced here by patching
      ``_map_microbatch`` itself) must NOT cancel the whole ``asyncio.gather`` and
      silently drop EVERY other source. PRE-FIX the gather had no
      ``return_exceptions=True`` so the escaped exception propagated and
      ``distill_section_evidence`` raised, dropping the ENTIRE section (a
      breadth/faithfulness loss). POST-FIX the siblings still return their
      findings/rows and the timed-out source surfaces a LOUD fail-closed coverage
      row (``unaccounted_after_dispatch``) — never a silent drop, never an
      unverified-as-verified claim.

These exercise the ``_map_microbatch`` / line-1486 site (the default
``PG_DISTILL_MICROBATCH_SIZE`` is 1, so every cache-miss source is its own
batch-of-1 that flows through ``_map_microbatch`` and the gather).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import tempfile
from dataclasses import dataclass

import pytest

import src.polaris_graph.llm.openrouter_client as orc
from src.polaris_graph.generator import evidence_distiller as ed
from src.polaris_graph.generator.evidence_distiller import (
    SectionDistillate,
    distill_section_evidence,
)


@dataclass
class _Section:
    title: str
    focus: str


_SECTION = _Section(title="Safety", focus="adverse events of the intervention")
_RQ = "What are the cardiovascular safety risks of tirzepatide in T2D adults?"

_EV_A = {
    "evidence_id": "ev_a", "tier": "T1",
    "statement": "Tirzepatide safety summary",
    "direct_quote": (
        "Serious adverse events occurred in 7.0 percent of tirzepatide patients. "
        "Discontinuation due to adverse events was 5.1 percent."
    ),
    "source_url": "https://example.org/a",
}
_EV_B = {
    "evidence_id": "ev_b", "tier": "T1",
    "statement": "Tirzepatide adverse events",
    "direct_quote": (
        "Pancreatitis was reported in 0.2 percent of participants in the trial. "
        "Gallbladder disease occurred in 1.5 percent of the treated group."
    ),
    "source_url": "https://example.org/b",
}
_POOL = {"ev_a": _EV_A, "ev_b": _EV_B}

# The locked reasoning-first generator (so _resolve_call_timeout / _call_impl would
# otherwise stretch to ~6530s without our explicit wall).
_MODEL = "deepseek/deepseek-v4-pro"


def _tmp_cache(monkeypatch) -> None:
    d = tempfile.mkdtemp()
    monkeypatch.setattr(ed, "_default_cache_dir", lambda: pathlib.Path(d))


class _Resp:
    def __init__(self, body):
        self.content = body
        self.reasoning = None
        self.input_tokens = 13
        self.output_tokens = 9


# ---------------------------------------------------------------------------
# (a) the explicit per-call wall is passed as timeout= to the distill_map call.
# ---------------------------------------------------------------------------

def test_distill_map_passes_explicit_call_wall_as_timeout(monkeypatch):
    _tmp_cache(monkeypatch)
    monkeypatch.delenv("PG_DISTILL_MICROBATCH_SIZE", raising=False)
    # Leave PG_DISTILL_MAP_CALL_WALL_S UNSET so we assert the SHIPPED default 1800,
    # not a value the test smuggled in via the env (that would test the env, not
    # the behavior the fix guarantees).
    monkeypatch.delenv("PG_DISTILL_MAP_CALL_WALL_S", raising=False)

    seen_timeouts: list = []

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *a, **k):
            # Record what the distiller actually passed for `timeout` (PRE-FIX this
            # kwarg is absent -> defaults to None and the assert below fails).
            seen_timeouts.append(k.get("timeout"))
            return _Resp(json.dumps(
                {"no_relevant_findings": True, "no_relevant_reason": "x",
                 "findings": []}
            ))

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient, raising=True)

    result = asyncio.run(
        distill_section_evidence(
            _SECTION, [_EV_A, _EV_B], _POOL, model=_MODEL,
            research_question=_RQ,
        )
    )
    assert isinstance(result, SectionDistillate)

    # Both cache-miss sources issued a live distill_map call (default microbatch=1).
    assert len(seen_timeouts) == 2, (
        f"expected one distill_map call per source, saw {len(seen_timeouts)}"
    )
    # BEHAVIOR: every call carried the EXPLICIT default wall (1800.0s), so the
    # reasoning-first ~6530s default can no longer govern a half-open socket.
    assert all(t == 1800.0 for t in seen_timeouts), (
        "distill_map must pass the explicit PG_DISTILL_MAP_CALL_WALL_S "
        f"(default 1800.0) as timeout= to every call; saw {seen_timeouts!r}"
    )


# ---------------------------------------------------------------------------
# (b) one batch timing out does not cancel the gather / drop the other sources.
# ---------------------------------------------------------------------------

def test_distill_map_timeout_isolated_other_sources_survive(monkeypatch):
    _tmp_cache(monkeypatch)
    monkeypatch.delenv("PG_DISTILL_MICROBATCH_SIZE", raising=False)

    # Healthy MAP responder for the batch(es) that do NOT time out.
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def _call(self, *a, **k):
            return _Resp(json.dumps(
                {"no_relevant_findings": True, "no_relevant_reason": "x",
                 "findings": []}
            ))

        async def close(self):
            return None

    monkeypatch.setattr(orc, "OpenRouterClient", _FakeClient, raising=True)

    # Make exactly ONE batch raise PAST the inner except (a wall timeout escaping
    # _map_microbatch — the real hang signature), and let every other batch run the
    # genuine code path. Patching _map_microbatch is the only injection point that
    # actually reaches the gather: the per-site `except Exception` inside
    # _map_microbatch would otherwise swallow a timeout before gather ever sees it.
    real_microbatch = ed._map_microbatch
    raised = {"done": False}

    async def _flaky_microbatch(evs, **kwargs):
        first_eid = (evs[0].get("evidence_id", "") if evs else "")
        if first_eid == "ev_a" and not raised["done"]:
            raised["done"] = True
            raise asyncio.TimeoutError("simulated distill_map per-call wall fired")
        return await real_microbatch(evs, **kwargs)

    monkeypatch.setattr(ed, "_map_microbatch", _flaky_microbatch, raising=True)

    # PRE-FIX (gather without return_exceptions): the escaped TimeoutError
    # propagates here and distill_section_evidence raises -> this call blows up and
    # the test FAILS. POST-FIX: it returns, ev_b survives, ev_a is disclosed.
    result = asyncio.run(
        distill_section_evidence(
            _SECTION, [_EV_A, _EV_B], _POOL, model=_MODEL,
            research_question=_RQ,
        )
    )
    assert isinstance(result, SectionDistillate)

    cov_by_id = {c.evidence_id: c for c in result.coverage}

    # The sibling that did NOT time out still produced its coverage row (BREADTH
    # preserved — it was not cancelled out by the failing batch).
    assert "ev_b" in cov_by_id, (
        "the non-timed-out source must still be accounted for "
        f"(coverage ids={sorted(cov_by_id)})"
    )

    # The timed-out source is NOT silently dropped: it surfaces a LOUD fail-closed
    # coverage row via the None-net (status map_failed / unaccounted_after_dispatch).
    assert "ev_a" in cov_by_id, (
        "the timed-out source must surface a LOUD fail-closed coverage row, "
        f"never disappear (coverage ids={sorted(cov_by_id)})"
    )
    assert cov_by_id["ev_a"].status == "map_failed", (
        "a timed-out source must be disclosed as map_failed, "
        f"got status={cov_by_id['ev_a'].status!r}"
    )
    assert cov_by_id["ev_a"].reason == "unaccounted_after_dispatch", (
        "the fail-closed None-net must label the dropped batch's source, "
        f"got reason={cov_by_id['ev_a'].reason!r}"
    )

    # Faithfulness: a timeout NEVER yields a verified/accepted finding for that
    # source — it is a disclosed gap, not an unverified-as-verified claim.
    assert all(f.evidence_id != "ev_a" for f in result.findings), (
        "a timed-out source must not produce any accepted finding"
    )


# ---------------------------------------------------------------------------
# (c) the wall bounds the WHOLE distill_map call END-TO-END, not per-retry-attempt.
# ---------------------------------------------------------------------------

def test_distill_map_wall_bounds_call_end_to_end(monkeypatch):
    """Codex P1 (iter 2): ``openrouter_client._call`` applies ``timeout=`` PER retry attempt
    and retries up to MAX_RETRIES, so a half-open socket could occupy the fan-out for
    ~3*(wall+grace)s — enough to blow the 10800s run-wall and lose the render. The fix wraps
    the call in an OUTER ``asyncio.wait_for(wall)`` so the TOTAL is bounded at ~wall. This test
    drives a ``_call`` that would run 30s (far past the wall) and asserts the helper cuts it at
    ~wall, NOWHERE near 3*wall or the 30s sleep.
    """
    import time

    monkeypatch.setenv("PG_DISTILL_MAP_CALL_WALL_S", "1")  # tiny wall for a fast test

    class _SlowClient:
        async def _call(self, *a, **k):
            # A call that runs FAR past the wall — the per-attempt timeout would retry this
            # forever; the outer wait_for must cancel it at ~wall.
            await asyncio.sleep(30)
            return _Resp("{}")

    async def _run() -> float:
        t0 = time.monotonic()
        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await ed._call_distill_map_with_wall(
                _SlowClient(), messages=[], reasoning_enabled=False,
            )
        return time.monotonic() - t0

    elapsed = asyncio.run(_run())
    assert elapsed < 5.0, (
        f"the distill_map wall must bound the call END-TO-END at ~1s; took {elapsed:.1f}s "
        "(the outer asyncio.wait_for did not cut the call across retries)"
    )
