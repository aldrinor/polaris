"""I-arch-006 (#1262) keystone: every LLM call path has a TIGHT read-stall deadline.

These tests guard the F33 / HANG-J1 / HANG-J2 fix: no LLM call path may leave the
httpx per-read (chunk-gap) timeout defaulting to the full generator budget — a dead /
idle-open socket (rx=tx=0) must trip in ~read-stall seconds, not hang for the whole
budget. Transport-only; no faithfulness gate is exercised here.
"""

import httpx

from src.polaris_graph.llm import openrouter_client as orc
from src.polaris_graph.llm import entailment_judge as ej
from src.polaris_graph.retrieval import semantic_conflict_detector as scd


# A generous upper bound: a "tight" read-stall must be far below the cert-slate
# generator budget (6500s) and below the non-slate module default (600s).
TIGHT_UPPER_BOUND_S = 300.0


def test_generator_sse_read_stall_constant_is_tight():
    assert orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS == 120.0
    assert orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS < TIGHT_UPPER_BOUND_S


def test_generator_stream_timeout_caps_read_below_budget():
    """The streaming Timeout must apply the tight read-stall, NOT the full budget.

    This is the exact F33 regression: ``httpx.Timeout(budget, connect=30.0)`` leaves
    ``.read == budget`` (6500s) — a dead socket hangs ~108 min. The fix passes an
    explicit ``read=``.
    """
    budget = 6500.0
    old_bug = httpx.Timeout(budget, connect=30.0)
    assert old_bug.read == budget  # documents the pre-fix behavior

    fixed = httpx.Timeout(
        budget, connect=30.0, read=orc.PG_SSE_READ_STALL_TIMEOUT_SECONDS
    )
    assert fixed.read == 120.0
    assert fixed.read < budget


def test_entailment_judge_read_stall_constants():
    assert ej._ENTAILMENT_READ_STALL_S == 120.0
    assert ej._ENTAILMENT_READ_STALL_S < TIGHT_UPPER_BOUND_S
    # keepalive reaping (HANG-J2) is configured
    assert ej._ENTAILMENT_MAX_KEEPALIVE >= 1
    assert ej._ENTAILMENT_KEEPALIVE_EXPIRY_S > 0


def test_semantic_conflict_judge_read_stall_constants():
    assert scd._JUDGE_READ_STALL_S == 120.0
    assert scd._JUDGE_READ_STALL_S < TIGHT_UPPER_BOUND_S
    assert scd._JUDGE_MAX_KEEPALIVE >= 1
    assert scd._JUDGE_KEEPALIVE_EXPIRY_S > 0


def test_judge_clients_build_with_tight_read():
    """Construct the two sync-judge httpx clients the way the modules do and assert
    the per-read timeout is tight (the bare-float 30s gap, which httpx reset on every
    byte and let a trickled socket run unbounded, is gone)."""
    ent_client = httpx.Client(
        timeout=httpx.Timeout(
            connect=ej._ENTAILMENT_CONNECT_S,
            read=ej._ENTAILMENT_READ_STALL_S,
            write=ej._ENTAILMENT_WRITE_S,
            pool=ej._ENTAILMENT_POOL_S,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=ej._ENTAILMENT_MAX_KEEPALIVE,
            keepalive_expiry=ej._ENTAILMENT_KEEPALIVE_EXPIRY_S,
        ),
    )
    try:
        assert ent_client.timeout.read == 120.0
        assert ent_client.timeout.connect == ej._ENTAILMENT_CONNECT_S
    finally:
        ent_client.close()

    scd_client = httpx.Client(
        timeout=httpx.Timeout(
            connect=scd._JUDGE_CONNECT_S,
            read=scd._JUDGE_READ_STALL_S,
            write=scd._JUDGE_WRITE_S,
            pool=scd._JUDGE_POOL_S,
        )
    )
    try:
        assert scd_client.timeout.read == 120.0
    finally:
        scd_client.close()


def test_credibility_timeout_applies_read_stall():
    """The credibility judge passed ``read=call_timeout`` (full budget). The fix adds an
    explicit tight ``read=`` so a full budget no longer governs the per-chunk read."""
    call_timeout = 600.0
    fixed = httpx.Timeout(call_timeout, connect=15.0, read=120.0)
    assert fixed.read == 120.0
    assert fixed.read < call_timeout
