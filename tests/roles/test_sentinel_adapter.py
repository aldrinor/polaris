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


# === DECOMPOSITION (certified MiniMax-M2) mode tests (I-run11-004) ===================
_MINIMAX_MODEL = "minimax/minimax-m2"
# Full decomposition contract (I-run11-004 brief-gate P1): a "supported" verdict needs a non-empty
# atoms list + unsupported_atoms or the parser fails closed (a bare/non-atomized supported did no work).
_SUPPORTED_JSON = ('{"verdict": "supported", "unsupported_atoms": 0, '
                   '"atoms": [{"atom": "x", "type": "mechanism", "status": "supported"}]}')
_UNSUPPORTED_JSON = ('{"verdict": "unsupported", "unsupported_atoms": 1, '
                     '"atoms": [{"atom": "x", "type": "mechanism", "status": "unsupported"}]}')
_MULTI_DOCS = [
    EvidenceDocument(doc_id="doc_a", text="HbA1c fell 2.3 points across arms."),
    EvidenceDocument(doc_id="doc_b", text="The reduction was sustained at 52 weeks."),
]


def test_decomposition_request_is_single_user_message_with_span_and_claim() -> None:
    """build_sentinel_request(mode="decomposition") REPLICATES the certified call: ONE user message
    carrying the certified decomposition prompt with span (all evidence .text joined) + claim
    inline (NOT the guardian documents-channel layout), and a JSON response_format param."""
    request = build_sentinel_request(
        _CLAIM, _MULTI_DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert request.role == "sentinel"
    assert request.model_slug == _MINIMAX_MODEL
    # SINGLE user message (not assistant+user guardian layout).
    assert request.messages is not None
    assert [m["role"] for m in request.messages] == ["user"]
    user_content = request.messages[0]["content"]
    # The certified decomposition prompt scaffolding is present.
    assert "Decompose the CLAIM into atomic sub-assertions" in user_content
    assert "STRICT JSON only" in user_content
    # Both spans are inlined into the prompt (the SPAN), and the claim too.
    assert "HbA1c fell 2.3 points across arms." in user_content
    assert "The reduction was sustained at 52 weeks." in user_content
    assert _CLAIM in user_content
    # No guardian block / no one-word block in this layout.
    assert "<guardian>" not in user_content
    assert "GROUNDED or UNGROUNDED" not in user_content
    # JSON response_format requested; NO documents — the span is inlined into the single message, so
    # the transport prepends no separate evidence message and the live body is the certified ONE
    # user message (Codex diff-gate iter-2 P1-2).
    assert request.params["response_format"] == {"type": "json_object"}
    assert request.params["documents"] == []


def test_decomposition_supported_json_parses_grounded() -> None:
    transport = _CannedTransport(_SUPPORTED_JSON, served_model=_MINIMAX_MODEL)
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    assert len(records) == 1
    assert records[0].parsed == result
    # The transport saw the single-user-message decomposition layout.
    assert transport.last_request is not None
    assert [m["role"] for m in transport.last_request.messages] == ["user"]


def test_decomposition_unsupported_json_parses_ungrounded() -> None:
    transport = _CannedTransport(_UNSUPPORTED_JSON, served_model=_MINIMAX_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is True


def test_decomposition_fenced_json_parses() -> None:
    fenced = "```json\n" + _SUPPORTED_JSON + "\n```"
    transport = _CannedTransport(fenced, served_model=_MINIMAX_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True


def test_decomposition_garbage_fails_closed() -> None:
    # Non-JSON, no verdict -> fail closed UNGROUNDED parsed_ok False (never a silent GROUNDED).
    transport = _CannedTransport("I think the claim is fine", served_model=_MINIMAX_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_decomposition_empty_fails_closed() -> None:
    transport = _CannedTransport("", served_model=_MINIMAX_MODEL)
    result, _records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False


def test_decomposition_transport_error_fails_closed() -> None:
    transport = _RaisingTransport()
    result, records = run_sentinel(
        transport, _CLAIM, _DOCS, model_slug=_MINIMAX_MODEL, mode="decomposition"
    )
    assert result.verdict is SentinelVerdict.UNGROUNDED
    assert result.parsed_ok is False
    assert len(records) == 1
    assert "transport_error" in records[0].raw_text


# === mode resolver (PG_SENTINEL_GROUNDEDNESS_MODE / PG_SENTINEL_MODEL / PG_FOUR_ROLE_TRANSPORT) ==
# I-run11-004: the UNSET default is MODEL-AWARE first. A granite slug whose name is NOT a
# minimax/granite-guardian model falls through to the transport-derived default; these tests pin
# PG_SENTINEL_MODEL to a NON-minimax/non-guardian general slug to exercise that fall-through path.
_GENERAL_GRANITE_SLUG = "ibm-granite/granite-4.1-8b"


def test_mode_defaults_to_noninverted_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    # A general (non-minimax, non-guardian) slug -> transport-derived default (here: noninverted).
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
    assert sentinel_groundedness_mode() == "noninverted"


def test_mode_defaults_to_noninverted_on_openrouter_transport(monkeypatch) -> None:
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
    assert sentinel_groundedness_mode() == "noninverted"


def test_mode_defaults_to_guardian_on_self_host_transport(monkeypatch) -> None:
    """The runtime-desync guard: a non-minimax/non-guardian slug on the sovereign self_host route
    DEFAULTS to guardian (the transport-derived fall-through), without any extra env."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
    assert sentinel_groundedness_mode() == "guardian"


# === I-run11-004: model-aware default mode (granite-guardian / minimax) =============
def test_mode_defaults_to_decomposition_for_minimax_slug(monkeypatch) -> None:
    """The MiniMax-M2 lock Sentinel: an UNSET PG_SENTINEL_GROUNDEDNESS_MODE with a minimax slug
    DEFAULTS to decomposition (model-aware), regardless of transport."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    assert sentinel_groundedness_mode() == "decomposition"
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    assert sentinel_groundedness_mode() == "decomposition"


def test_mode_defaults_to_guardian_for_granite_guardian_slug(monkeypatch) -> None:
    """A granite-guardian slug DEFAULTS to guardian (model-aware), even on the openrouter route —
    the inverted contract pairs with the task-trained Guardian model it is served against."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_SENTINEL_MODEL", "ibm-granite/granite-guardian-4.1-8b")
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    assert sentinel_groundedness_mode() == "guardian"


def test_default_minimax_code_default_resolves_decomposition(monkeypatch) -> None:
    """With NO PG_SENTINEL_MODEL env (falls back to the openrouter_client code default
    minimax/minimax-m2) the UNSET-mode default is decomposition — the shipping default."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.delenv("PG_SENTINEL_MODEL", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    assert sentinel_groundedness_mode() == "decomposition"


def test_explicit_mode_env_overrides_model_and_transport_default(monkeypatch) -> None:
    # Explicit override wins over BOTH the model-aware AND transport-derived default, all directions.
    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "noninverted")
    assert sentinel_groundedness_mode() == "noninverted"
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "guardian")
    assert sentinel_groundedness_mode() == "guardian"
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "decomposition")
    assert sentinel_groundedness_mode() == "decomposition"


def test_unrecognized_mode_raises_loud(monkeypatch) -> None:
    # Codex diff-gate P2 (no-silent-fallback): an EXPLICIT but unrecognized
    # PG_SENTINEL_GROUNDEDNESS_MODE must FAIL LOUD, not silently derive from the model/transport
    # (a mode typo must never desync the prompt+parser from the served model).
    import pytest
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "bogus")
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "self_host")
    with pytest.raises(ValueError):
        sentinel_groundedness_mode()
    # When the env is UNSET (not a typo), the model-aware default still applies.
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
    assert sentinel_groundedness_mode() == "decomposition"
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
    monkeypatch.setenv("PG_FOUR_ROLE_TRANSPORT", "openrouter")
    assert sentinel_groundedness_mode() == "noninverted"


def test_run_sentinel_uses_env_mode_when_mode_arg_none(monkeypatch) -> None:
    """When run_sentinel is called WITHOUT a mode (the role_pipeline call site), it resolves the
    mode from the env. A general granite slug on openrouter -> noninverted: `GROUNDED` parses."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_TRANSPORT", raising=False)
    monkeypatch.setenv("PG_SENTINEL_MODEL", _GENERAL_GRANITE_SLUG)
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


def test_run_sentinel_minimax_default_uses_decomposition(monkeypatch) -> None:
    """The shipping default: with a minimax slug and no mode env, run_sentinel uses decomposition —
    a `{"verdict": "supported"}` JSON parses GROUNDED, and a `{"verdict": "unsupported"}` parses
    UNGROUNDED (the certified mapping)."""
    monkeypatch.delenv("PG_SENTINEL_GROUNDEDNESS_MODE", raising=False)
    monkeypatch.setenv("PG_SENTINEL_MODEL", "minimax/minimax-m2")
    transport = _CannedTransport(
        _SUPPORTED_JSON,
        served_model="minimax/minimax-m2",
    )
    result, _records = run_sentinel(transport, _CLAIM, _DOCS, model_slug="minimax/minimax-m2")
    assert result.verdict is SentinelVerdict.GROUNDED
    assert result.parsed_ok is True
    transport2 = _CannedTransport(
        '{"verdict": "unsupported", "unsupported_atoms": 1, "atoms": []}',
        served_model="minimax/minimax-m2",
    )
    result2, _r2 = run_sentinel(transport2, _CLAIM, _DOCS, model_slug="minimax/minimax-m2")
    assert result2.verdict is SentinelVerdict.UNGROUNDED
    assert result2.parsed_ok is True
