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
    sentinel_groundedness_mode,
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


# The guardian-mode tests pin mode="guardian" explicitly (I-run11-002 L1): the SOVEREIGN
# self-host granite-Guardian path is the inverted `<score>yes|no</score>` contract. With
# mode unset the adapter now DEFAULTS to "noninverted" (the benchmark general-granite path),
# which these `<score>`-fixture tests are NOT exercising — so they pin guardian explicitly.
def test_request_has_guardian_block_documents_and_no_structured_output() -> None:
    request = build_sentinel_request(_CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
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
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    assert len(records) == 1
    assert records[0].role == "sentinel"
    assert records[0].served_model == _MODEL
    assert records[0].parsed == result


def test_yes_score_is_ungrounded() -> None:
    transport = _CannedTransport("<score>yes</score>")
    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


def test_malformed_output_fails_closed() -> None:
    # Surrounding prose makes the strict envelope fail -> UNGROUNDED, parsed_ok False.
    transport = _CannedTransport("The claim looks fine <score>no</score> overall.")
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    assert len(records) == 1


def test_empty_output_fails_closed() -> None:
    transport = _CannedTransport("")
    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_transport_error_fails_closed() -> None:
    transport = _RaisingTransport()
    result, records = run_sentinel(transport, _CLAIM, _DOCS, model_slug=_MODEL, mode="guardian")
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    # One record per attempted completion; served_model unknown on the error path.
    assert len(records) == 1
    assert records[0].served_model is None
    assert "transport_error" in records[0].raw_text


# === NON-INVERTED (benchmark) mode tests (I-run11-002 L1) ============================
_BENCHMARK_MODEL = "ibm-granite/granite-4.1-8b"


def test_benchmark_mode_request_emits_noninverted_block_not_guardian() -> None:
    """build_sentinel_request(mode="noninverted") emits the DIRECT one-word block — NOT the
    inverted `<guardian>` block. Same assistant=claim + documents layout; only the final
    instruction differs."""
    request = build_sentinel_request(
        _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    final = request.messages[-1]["content"]
    assert "<guardian>" not in final
    assert "GROUNDED or UNGROUNDED" in final
    # Layout invariants identical to the guardian path.
    assert [m["role"] for m in request.messages] == ["assistant", "user"]
    assert request.messages[0]["content"] == _CLAIM
    assert request.params["documents"][0]["doc_id"] == "doc_surmount1"
    assert "structured_outputs" not in request.params
    assert "response_format" not in request.params


def test_benchmark_grounded_word_parses_grounded() -> None:
    transport = _CannedTransport("GROUNDED", served_model=_BENCHMARK_MODEL)
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    assert len(records) == 1
    assert records[0].parsed == result


def test_benchmark_ungrounded_word_parses_ungrounded() -> None:
    transport = _CannedTransport("UNGROUNDED", served_model=_BENCHMARK_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


def test_benchmark_garbage_fails_closed() -> None:
    transport = _CannedTransport("I think it might be ok", served_model=_BENCHMARK_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_benchmark_both_tokens_fails_closed() -> None:
    transport = _CannedTransport("GROUNDED ... UNGROUNDED", served_model=_BENCHMARK_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_benchmark_score_tag_output_fails_closed() -> None:
    """A model that emits the inverted `<score>` format under the non-inverted prompt must NOT be
    trusted — `<score>no</score>` must fail closed (never a silent GROUNDED)."""
    transport = _CannedTransport("<score>no</score>", served_model=_BENCHMARK_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_benchmark_transport_error_fails_closed() -> None:
    transport = _RaisingTransport()
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL, mode="noninverted"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    assert len(records) == 1
    assert "transport_error" in records[0].raw_text


# === mode resolver (PG_SENTINEL_GROUNDEDNESS_MODE / PG_FOUR_ROLE_TRANSPORT) ==========
def test_mode_defaults_to_noninverted_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    assert sentinel_groundedness_mode() == "noninverted"


def test_mode_defaults_to_noninverted_on_openrouter_transport(monkeypatch) -> None:
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    assert sentinel_groundedness_mode() == "noninverted"


def test_mode_defaults_to_guardian_on_self_host_transport(monkeypatch) -> None:
    """The runtime-desync guard: the sovereign self_host route DEFAULTS to guardian so the
    granite-Guardian model gets the inverted prompt it is trained on — without any extra env."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    assert sentinel_groundedness_mode() == "guardian"


def test_explicit_mode_env_overrides_transport_default(monkeypatch) -> None:
    # Explicit override wins over the transport-derived default, both directions.
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "noninverted")
    assert sentinel_groundedness_mode() == "noninverted"
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardian")
    assert sentinel_groundedness_mode() == "guardian"


def test_unrecognized_mode_falls_back_to_transport_default(monkeypatch) -> None:
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "bogus")
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    assert sentinel_groundedness_mode() == "guardian"
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    assert sentinel_groundedness_mode() == "noninverted"


def test_run_sentinel_uses_env_mode_when_mode_arg_none(monkeypatch) -> None:
    """When run_sentinel is called WITHOUT a mode (the role_pipeline call site), it resolves the
    mode from the env. Default (unset) -> noninverted: a `GROUNDED` word parses GROUNDED."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    transport = _CannedTransport("GROUNDED", served_model=_BENCHMARK_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_BENCHMARK_MODEL
    )
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    # And a self_host env makes the SAME call site use guardian -> a `<score>no</score>` parses.
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    transport2 = _CannedTransport("<score>no</score>", served_model=_MODEL)
    result2, _r2 = run_sentinel(transport2, _CLAIM, _DOCS, model_slug=_MODEL)
    assert result2.verdict is SentinelVerdict.GROUNDED
    assert result2.parsed_ok is True
