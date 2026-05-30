"""Tests for the Sentinel (Granite Guardian) adapter — request shape + FAIL-CLOSED.

Properties:
- request has the assistant claim turn, the final user <guardian> groundedness block, and
  the documents in params["documents"]; NO structured-output spec;
- a clean <score>no</score> -> GROUNDED, parsed_ok; <score>yes</score> -> UNGROUNDED;
- a malformed transport output FAILS CLOSED (UNGROUNDED, parsed_ok=False), never GROUNDED;
- a transport that raises FAILS CLOSED too;
- run_sentinel returns a 1-element RoleCallRecord list (one record per completion).
All with a mock transport. No network.
"""

from __future__ import annotations

from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sentinel_adapter import (
    build_sentinel_request,
    run_sentinel,
)
from src.polaris_graph.roles.sentinel_contract import SentinelVerdict

_MODEL = "ibm-granite/granite-guardian-4.1-8b"
_CLAIM = "Tirzepatide lowered HbA1c by 2.3 points."
_DOCS = [
    EvidenceDocument(doc_id="doc_surmount1", text="HbA1c fell 2.3 points across arms."),
]


class _CannedTransport:
    """Mock transport returning a fixed RoleResponse and recording the last request."""

    def __init__(self, raw_text: str, served_model: str | None = _MODEL) -> None:
        self._raw_text = raw_text
        self._served_model = served_model
        self.last_request: RoleRequest | None = None

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.last_request = request
        return RoleResponse(raw_text=self._raw_text, served_model=self._served_model)


class _RaisingTransport:
    """Mock transport that raises to exercise the fail-closed path."""

    def complete(self, request: RoleRequest) -> RoleResponse:
        raise RuntimeError("transport down")


def test_request_has_guardian_block_documents_and_no_structured_output() -> None:
    request = build_sentinel_request(_CLAIM, _DOCS, model_slug=_MODEL)
    assert request.role == "sentinel"
    assert request.model_slug == _MODEL

    # assistant turn carries the claim; final user turn is the <guardian> block.
    assert request.messages is not None
    roles = [m["role"] for m in request.messages]
    assert roles == ["assistant", "user"]
    assert request.messages[0]["content"] == _CLAIM
    assert "<guardian>" in request.messages[-1]["content"]

    # documents present in params; NO structured-output spec (Granite emits <score>).
    assert request.params["documents"][0]["doc_id"] == "doc_surmount1"
    assert "structured_outputs" not in request.params
    assert "response_format" not in request.params


def test_grounded_score_parses_ok() -> None:
    transport = _CannedTransport("<score>no</score>")
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    assert len(records) == 1
    assert records[0].role == "sentinel"
    assert records[0].served_model == _MODEL
    assert records[0].parsed == result


def test_yes_score_is_ungrounded() -> None:
    transport = _CannedTransport("<score>yes</score>")
    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


def test_malformed_output_fails_closed() -> None:
    # Surrounding prose makes the strict envelope fail -> UNGROUNDED, parsed_ok False.
    transport = _CannedTransport("The claim looks fine <score>no</score> overall.")
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    assert len(records) == 1


def test_empty_output_fails_closed() -> None:
    transport = _CannedTransport("")
    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_transport_error_fails_closed() -> None:
    transport = _RaisingTransport()
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    # One record per attempted completion; served_model unknown on the error path.
    assert len(records) == 1
    assert records[0].served_model is None
    assert "transport_error" in records[0].raw_text
