"""B6 (I-deepfix-001 #1370) — D8 Judge transport parse-hardening + off-enum provider rotation.

FABLE_SPEC_D8JUDGE.md build spec, THREE sub-fixes, all faithfulness-NEUTRAL:
  FIX 1 — strip a leaked `<think>` opener off message.content when a SEPARATE reasoning channel is
          populated (a subset of kimi endpoints garble the reasoning channel). Default-ON kill-switch
          PG_OPENROUTER_THINK_LEAK_STRIP; OFF => byte-identical pre-fix (`bare = content` verbatim).
  FIX 2 — RoleResponse.served_provider + off-enum re-ask rotation: the garbling provider slug is
          threaded into request.params['provider_ignore_extra'] and merged into the next body's
          provider ignore-list. Default-ON kill-switch PG_JUDGE_OFFENUM_PROVIDER_ROTATE; OFF => no
          added ignore entry (byte-identical).
  FIX 3 — observability only: the two WS-1(b) re-ask warnings carry str(exc)[:120] + served_provider.

OFFLINE: httpx.MockTransport injected into OpenRouterRoleTransport (the meta007 no-network pattern).
NO socket, NO real LLM, NO spend. The exact-enum `parse_judge_verdict`, the enum, and the fail-closed
UNSUPPORTED degrade are UNCHANGED — this only removes transport-noise convictions.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.polaris_graph.benchmark import pathB_capture as pc
from src.polaris_graph.roles import openrouter_role_transport as ort
from src.polaris_graph.roles.judge_adapter import (
    _extract_verdict_token,
    reset_judge_verdict_cache,
    run_judge,
)
from src.polaris_graph.roles.judge_contract import JudgeEnumError, parse_judge_verdict
from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    _parse_openrouter_response,
)

_MODEL = "moonshotai/kimi-k2.6"
_CLAIM = "Tirzepatide lowered HbA1c by 2.3 points."
_EVIDENCE = "SURMOUNT-1: HbA1c fell 2.3 points across arms."
_MIRROR = "grounded"
_SENTINEL = "grounded"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """OpenRouter key (LAW VI) + a clean slate: clear every B6/WS-1 flag so each test controls the
    default-ON behaviors explicitly, and reset the process-wide idempotency cache + pathB capture."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    for _k in (
        "PG_FOUR_ROLE_TRANSPORT",
        "OPENROUTER_BASE_URL",
        "PG_JUDGE_MODEL",
        "PG_BENCHMARK_JUDGE_MODEL",
        "PG_JUDGE_RETRY_MAX_ATTEMPTS",
        "PG_JUDGE_RETRY_BEFORE_DEGRADE",
        "PG_ROLE_TRANSPORT_DEGRADE",
        "PG_SENTINEL_TRANSPORT_DEGRADE",
        "PG_JUDGE_OFFENUM_PROVIDER_ROTATE",
        "PG_OPENROUTER_THINK_LEAK_STRIP",
        "PG_JUDGE_VERDICT_IDEMPOTENCY",
        "PG_JUDGE_ENUM_RESPONSE_FORMAT",
        "PG_PROVIDER_BLANK_RETRIES",
        "PG_ROLE_TRANSPORT_RETRIES",
    ):
        monkeypatch.delenv(_k, raising=False)
    reset_judge_verdict_cache()
    pc.clear_pathB_capture()
    yield
    reset_judge_verdict_cache()
    pc.clear_pathB_capture()


@pytest.fixture(autouse=True)
def _pin_effort_ladder(monkeypatch):
    """Deterministic seam attempt count regardless of ambient PG_FOUR_ROLE_EFFORT_LADDER (read at
    import). A non-blank response returns on the FIRST rung, so this only bounds a blank ladder."""
    monkeypatch.setattr(ort, "_VERIFIER_EFFORT_LADDER", ("xhigh", "low", None))
    yield


def _payload(message: dict, *, provider: str = "DeepInfra", model: str = _MODEL) -> dict:
    """A canned OpenRouter-shaped 200 body (top-level served provider/model + assistant message)."""
    return {
        "model": model,
        "provider": provider,
        "choices": [{"message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5},
    }


def _seq_transport(steps):
    """Build an OpenRouterRoleTransport whose injected MockTransport walks `steps` in order.

    Each step is either a payload dict (returned as a 200) or an Exception instance (raised, to
    exercise the transport's own bounded retries). Records every request body for assertions."""
    state = {"n": 0, "bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        state["bodies"].append(json.loads(request.content.decode("utf-8")))
        step = steps[state["n"]]
        state["n"] += 1
        if isinstance(step, Exception):
            raise step
        return httpx.Response(200, json=step)

    transport = OpenRouterRoleTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    return transport, state


# ------------------------------------------------------------------------------------ FIX 1 (parse)
def test_parse_strips_think_opener_and_merges_reasoning():
    """FIX 1 at the parser: with a SEPARATE reasoning channel present, an UNCLOSED leaked `<think>`
    opener is stripped off content, and a CLOSED block's inner think text is merged into reasoning."""
    bare, _served_model, _usage, reasoning = _parse_openrouter_response(
        _payload({"content": "<think>\nVERIFIED", "reasoning": "chain of thought"})
    )
    assert bare == "VERIFIED"
    assert reasoning == "chain of thought"  # separate channel preserved

    bare2, _sm2, _u2, reasoning2 = _parse_openrouter_response(
        _payload({"content": "<think>span A entails B</think>PARTIAL", "reasoning": "chain"})
    )
    assert bare2 == "PARTIAL"
    assert "chain" in reasoning2 and "span A entails B" in reasoning2  # both channels preserved


def test_think_leak_stripped_when_separate_reasoning():
    """FIX 1 end-to-end: a `<think>\\nVERIFIED` leak with a populated reasoning field parses clean to
    VERIFIED in exactly ONE POST — no wasted re-ask (the pre-fix grind)."""
    transport, state = _seq_transport(
        [_payload({"content": "<think>\nVERIFIED", "reasoning": "chain of thought"})]
    )
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "VERIFIED"
    assert state["n"] == 1  # exactly one POST, no re-ask
    assert len(records) == 1
    assert records[0].parsed == "VERIFIED"


# --------------------------------------------------------------------------- FIX 2 (rotate/converge)
def test_garbled_token_still_off_enum_then_rotates_and_converges():
    """FIX 2: a doubled-token garble ('VERIFIEDVERIFIED' after the opener strip) is STILL off-enum
    (enum bar intact), the re-ask rotates OFF the garbling provider (deepinfra in the 2nd body's
    ignore), and the clean second response converges to PARTIAL in exactly 2 POSTs."""
    transport, state = _seq_transport(
        [
            _payload({"content": "<think>\nVERIFIEDVERIFIED", "reasoning": "cot"}, provider="DeepInfra"),
            _payload({"content": '{"verdict": "PARTIAL"}', "reasoning": "cot"}, provider="Novita"),
        ]
    )
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "PARTIAL"
    assert state["n"] == 2  # one re-ask
    second_provider_block = state["bodies"][1].get("provider", {})
    assert "deepinfra" in second_provider_block.get("ignore", [])
    # the doubled token was NEVER accepted as a verdict (exact-enum bar unchanged).
    with pytest.raises(JudgeEnumError):
        parse_judge_verdict("VERIFIEDVERIFIED")


def test_unclosed_think_with_no_separate_reasoning_still_fails_loud():
    """band_aids_to_avoid (2): an unclosed `<think>` with NO separate reasoning field is genuine
    truncation and MUST stay fail-loud (RoleTransportError) — the strip never runs on this path."""
    with pytest.raises(RoleTransportError):
        _parse_openrouter_response(
            _payload({"content": "<think>\nhalf-emitted reasoning with no close"})
        )


def test_exhausted_reasks_degrade_fail_closed(monkeypatch):
    """FIX 2 exhaustion: 3 consecutive garbled off-enum responses (max_retries=2) degrade THIS claim
    to a fail-closed UNSUPPORTED with a <judge_offenum> record — never a synthesized PASS, never None."""
    monkeypatch.setenv("PG_JUDGE_RETRY_MAX_ATTEMPTS", "2")
    steps = [
        _payload({"content": "<think>\nVERIFIEDVERIFIED", "reasoning": "cot"}, provider=f"Host{i}")
        for i in range(3)
    ]
    transport, state = _seq_transport(steps)
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "UNSUPPORTED"
    assert state["n"] == 3  # initial + 2 re-asks
    assert len(records) == 1
    assert "<judge_offenum>" in records[0].raw_text
    assert records[0].parsed == "UNSUPPORTED"


def test_disconnect_then_converges(monkeypatch):
    """Regression (#1053): the transport's OWN bounded retry recovers 2 transient disconnects then
    serves a clean UNSUPPORTED — one run_judge attempt, verdict returned, not propagated."""
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "2")
    steps = [
        httpx.RemoteProtocolError("server disconnected without sending a response"),
        httpx.RemoteProtocolError("server disconnected without sending a response"),
        _payload({"content": '{"verdict": "UNSUPPORTED"}'}),
    ]
    transport, state = _seq_transport(steps)
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "UNSUPPORTED"
    assert state["n"] == 3  # 2 disconnects retried inside ONE complete(), then success


# ------------------------------------------------------------------------- kill-switch byte-identity
def test_kill_switch_think_leak_strip_off_byte_identical(monkeypatch):
    """PG_OPENROUTER_THINK_LEAK_STRIP=0 => the leaked opener is NOT stripped; content is the bare
    verdict VERBATIM, and parse raises JudgeEnumError exactly as pre-fix."""
    monkeypatch.setenv("PG_OPENROUTER_THINK_LEAK_STRIP", "0")
    bare, _sm, _u, reasoning = _parse_openrouter_response(
        _payload({"content": "<think>\nVERIFIED", "reasoning": "chain"})
    )
    assert bare == "<think>\nVERIFIED"  # verbatim (byte-identical pre-fix)
    assert reasoning == "chain"
    with pytest.raises(JudgeEnumError):
        parse_judge_verdict(bare)


def test_kill_switch_offenum_rotate_off_no_added_ignore(monkeypatch):
    """PG_JUDGE_OFFENUM_PROVIDER_ROTATE=0 => the re-ask still fires (retry is a SEPARATE switch) and
    still converges, but the re-ask body carries NO added provider ignore entry (byte-identical)."""
    monkeypatch.setenv("PG_JUDGE_OFFENUM_PROVIDER_ROTATE", "0")
    transport, state = _seq_transport(
        [
            _payload({"content": "<think>\nVERIFIEDVERIFIED", "reasoning": "cot"}, provider="DeepInfra"),
            _payload({"content": '{"verdict": "PARTIAL"}'}, provider="Novita"),
        ]
    )
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "PARTIAL"
    assert state["n"] == 2  # re-ask unchanged
    second_provider_block = state["bodies"][1].get("provider", {})
    assert "deepinfra" not in second_provider_block.get("ignore", [])


def test_enum_bar_unchanged():
    """band_aids_to_avoid (1): NO fuzzy/substring/case-fold. Off-enum tokens (incl. a doubled or
    prose-wrapped token, and a {"verdict": "MAYBE"} envelope) all raise; a clean JSON-enveloped
    UNSUPPORTED parses and HOLDS with NO re-ask (a genuine non-support is never re-asked)."""
    for bad in ("verified", "VERIFIED.", "the verdict is verified", '{"verdict": "MAYBE"}'):
        token = _extract_verdict_token(bad)
        with pytest.raises(JudgeEnumError):
            parse_judge_verdict(token)

    transport, state = _seq_transport([_payload({"content": '{"verdict": "UNSUPPORTED"}'})])
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == "UNSUPPORTED"
    assert state["n"] == 1  # HELD on the first clean parse — a real non-support is never re-asked
