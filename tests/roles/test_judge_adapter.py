"""Tests for the Judge (Qwen3.6) adapter — hard-enum request + LOUD-FAIL parse.

Properties:
- request carries params["structured_outputs"]["choice"] == JUDGE_CHOICES (current vLLM
  spelling, NOT guided_choice) and a bounded max_tokens;
- the prompt includes the Mirror + Sentinel signals;
- every canonical enum token parses to itself;
- a non-enum token raises JudgeEnumError (NO silent default — fail loud);
- run_judge returns a 1-element RoleCallRecord list.
All with a mock transport. No network.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.roles.judge_contract import JUDGE_CHOICES, JudgeEnumError
from src.polaris_graph.roles.judge_adapter import build_judge_request, run_judge
from src.polaris_graph.roles.role_transport import RoleRequest, RoleResponse

_MODEL = "qwen/qwen3.6-35b-a3b"
_CLAIM = "Tirzepatide lowered HbA1c by 2.3 points."
_EVIDENCE = "SURMOUNT-1: HbA1c fell 2.3 points across arms."
_MIRROR = "grounded"
_SENTINEL = "grounded"


class _CannedTransport:
    def __init__(self, raw_text: str, served_model: str | None = _MODEL) -> None:
        self._raw_text = raw_text
        self._served_model = served_model
        self.last_request: RoleRequest | None = None

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.last_request = request
        return RoleResponse(raw_text=self._raw_text, served_model=self._served_model)


def test_request_carries_choice_enum_and_bounded_max_tokens() -> None:
    request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert request.role == "judge"
    assert request.model_slug == _MODEL

    # hard-enum spec: structured_outputs.choice == JUDGE_CHOICES (NOT guided_choice).
    assert request.params["structured_outputs"]["choice"] == JUDGE_CHOICES
    assert "guided_choice" not in request.params

    # bounded context.
    assert isinstance(request.params["max_tokens"], int)
    assert request.params["max_tokens"] > 0

    # the arbiter prompt carries the Mirror + Sentinel signals.
    assert "MIRROR_SIGNAL" in request.prompt
    assert "SENTINEL_SIGNAL" in request.prompt


def test_custom_max_tokens_is_bounded_and_passed_through() -> None:
    request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL, max_tokens=8
    )
    assert request.params["max_tokens"] == 8


@pytest.mark.parametrize("verdict_token", JUDGE_CHOICES)
def test_every_enum_token_parses(verdict_token: str) -> None:
    transport = _CannedTransport(verdict_token)
    verdict, records = run_judge(
        transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL
    )
    assert verdict == verdict_token
    assert len(records) == 1
    assert records[0].role == "judge"
    assert records[0].served_model == _MODEL
    assert records[0].parsed == verdict_token


def test_non_enum_token_raises_judge_enum_error() -> None:
    transport = _CannedTransport("MAYBE")
    with pytest.raises(JudgeEnumError):
        run_judge(transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL)


def test_empty_output_raises_judge_enum_error() -> None:
    transport = _CannedTransport("")
    with pytest.raises(JudgeEnumError):
        run_judge(transport, _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL)
