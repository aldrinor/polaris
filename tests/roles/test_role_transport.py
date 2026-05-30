"""Shape tests for the shared role transport data contracts (I-meta-002 sub-PR-4).

Pure data-contract checks: RoleRequest / RoleResponse (incl. the citations field) /
RoleCallRecord / EvidenceDocument shapes and the RoleTransport Protocol. No network.
"""

from __future__ import annotations

from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)


def test_role_request_carries_role_model_and_params() -> None:
    request = RoleRequest(
        role="judge",
        model_slug="qwen/qwen3.6-35b-a3b",
        prompt="decide",
        params={"max_tokens": 16},
    )
    assert request.role == "judge"
    assert request.model_slug == "qwen/qwen3.6-35b-a3b"
    assert request.prompt == "decide"
    assert request.messages is None
    assert request.params["max_tokens"] == 16


def test_role_response_defaults_and_citations_field() -> None:
    # Minimal response: only raw_text required, citations defaults to None.
    minimal = RoleResponse(raw_text="<score>no</score>")
    assert minimal.raw_text == "<score>no</score>"
    assert minimal.served_model is None
    assert minimal.usage is None
    assert minimal.citations is None

    # Structured-citation path: citations carries CitationSpan objects.
    spans = [CitationSpan(span_start=0, span_end=5, doc_ids=("doc_a",))]
    rich = RoleResponse(
        raw_text="answer",
        served_model="cohere/command-a-plus",
        usage={"total_tokens": 12},
        citations=spans,
    )
    assert rich.served_model == "cohere/command-a-plus"
    assert rich.usage == {"total_tokens": 12}
    assert rich.citations == spans
    assert rich.citations[0].doc_ids == ("doc_a",)


def test_role_call_record_shape() -> None:
    record = RoleCallRecord(
        role="sentinel",
        model_slug="ibm-granite/granite-guardian-4.1-8b",
        served_model="ibm-granite/granite-guardian-4.1-8b",
        raw_text="<score>no</score>",
        parsed="grounded",
    )
    assert record.role == "sentinel"
    assert record.model_slug == "ibm-granite/granite-guardian-4.1-8b"
    assert record.served_model == record.model_slug
    assert record.raw_text == "<score>no</score>"
    assert record.parsed == "grounded"


def test_evidence_document_shape() -> None:
    doc = EvidenceDocument(doc_id="doc_surmount1", text="HbA1c fell 2.3 points.")
    assert doc.doc_id == "doc_surmount1"
    assert doc.text == "HbA1c fell 2.3 points."


def test_mock_transport_satisfies_protocol() -> None:
    class _MockTransport:
        def complete(self, request: RoleRequest) -> RoleResponse:
            return RoleResponse(raw_text="ok", served_model=request.model_slug)

    transport = _MockTransport()
    assert isinstance(transport, RoleTransport)
    response = transport.complete(RoleRequest(role="judge", model_slug="m"))
    assert response.raw_text == "ok"
    assert response.served_model == "m"
