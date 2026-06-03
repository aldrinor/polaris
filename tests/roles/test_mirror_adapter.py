"""Tests for the Mirror (Cohere) two-pass adapter — citation normalization + binding.

Properties:
- run_mirror makes TWO transport calls and returns a 2-element RoleCallRecord list with
  BOTH pass-1 and pass-2 asserted;
- the pass-2 request embeds the pass-1 composite content_hash;
- a pass-2 whose hash does not bind -> MirrorBindingError (fail closed);
- citation normalization: the structured RoleResponse.citations path is parsed, the <co>
  raw_text path is parsed, and the empty-both case raises MirrorCitationError (no silent
  empty MirrorPass1 that trivially passes the binding);
- citation-binding (iter-4): an empty-doc_id span is rejected, a span citing a doc_id NOT
  in evidence_documents is rejected, a MIXED real+hallucinated span is rejected whole, a
  claim left with no valid grounded citation raises MirrorCitationError, and a span citing a
  real supplied doc_id is accepted.
All with a mock transport. No network.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.roles.mirror_adapter import (
    MirrorBindingError,
    MirrorCitationError,
    MirrorParseError,
    build_mirror_pass2_request,
    run_mirror,
)
from src.polaris_graph.roles.mirror_contract import (
    CitationSpan,
    MirrorPass1,
    build_pass2_input,
)
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)

_MODEL = "cohere/command-a-plus"
_CLAIM = "Summarize the HbA1c effect."
_DOCS = [
    EvidenceDocument(doc_id="doc_surmount1", text="HbA1c fell 2.3 points."),
    EvidenceDocument(doc_id="doc_label2", text="Indicated for T2DM."),
]
_VALID_IDS = {d.doc_id for d in _DOCS}


class _SequencedTransport:
    """Mock transport returning queued RoleResponses in order, recording each request."""

    def __init__(self, responses: list[RoleResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[RoleRequest] = []

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def _pass2_hash_for(pass1: MirrorPass1) -> str:
    """The composite content_hash the adapter will compute for `pass1`."""
    return build_pass2_input(pass1)["content_hash"]


def _pass2_response_for(pass1: MirrorPass1, classification: str = "grounded") -> RoleResponse:
    """A canned pass-2 JSON response that binds to `pass1`."""
    payload = {
        "content_hash": _pass2_hash_for(pass1),
        "classification": classification,
        "rationale": "ok",
    }
    return RoleResponse(raw_text=json.dumps(payload), served_model=_MODEL)


# --- structured-citation path ------------------------------------------------------
def test_structured_citations_two_calls_two_records_and_binding() -> None:
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.",
        served_model=_MODEL,
        citations=spans,
    )
    # On the structured path answer_text is the raw_text verbatim.
    expected_pass1 = MirrorPass1(answer_text="HbA1c fell 2.3 points.", citation_spans=spans)
    transport = _SequencedTransport(
        [pass1_response, _pass2_response_for(expected_pass1)]
    )

    pass2, records = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)

    # TWO transport calls.
    assert len(transport.requests) == 2
    # 2-element record list, BOTH passes asserted.
    assert len(records) == 2
    assert records[0].role == "mirror"
    assert records[0].parsed.answer_text == "HbA1c fell 2.3 points."
    assert records[0].parsed.citation_spans == spans
    assert records[1].parsed is pass2
    assert pass2.classification == "grounded"

    # pass-2 request embeds the pass-1 composite hash.
    pass2_request = transport.requests[1]
    assert pass2_request.params["pass2_input"]["content_hash"] == _pass2_hash_for(
        expected_pass1
    )


# --- self-host <co> path -----------------------------------------------------------
def test_co_span_path_parsed_and_answer_text_stripped() -> None:
    # raw_text carries a <co> span; offsets index the TAG-STRIPPED text.
    pass1_raw = "<co>HbA1c fell 2.3</co:doc_surmount1> overall."
    cleaned = "HbA1c fell 2.3 overall."
    expected_spans = [CitationSpan(span_start=0, span_end=14, doc_ids=("doc_surmount1",))]
    expected_pass1 = MirrorPass1(answer_text=cleaned, citation_spans=expected_spans)

    pass1_response = RoleResponse(raw_text=pass1_raw, served_model=_MODEL)
    transport = _SequencedTransport(
        [pass1_response, _pass2_response_for(expected_pass1)]
    )

    pass2, records = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)

    # answer_text is the cleaned (tag-stripped) text so span offsets align.
    assert records[0].parsed.answer_text == cleaned
    assert records[0].parsed.citation_spans == expected_spans
    assert pass2.classification == "grounded"


# --- binding mismatch --------------------------------------------------------------
def test_binding_mismatch_raises_mirror_binding_error() -> None:
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    # pass-2 carries a hash that does NOT bind to pass-1.
    bad_pass2 = RoleResponse(
        raw_text=json.dumps(
            {"content_hash": "deadbeef", "classification": "grounded"}
        ),
        served_model=_MODEL,
    )
    transport = _SequencedTransport([pass1_response, bad_pass2])
    with pytest.raises(MirrorBindingError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


# --- #1028: pass-2 robustness (omitted hash salvaged; missing/non-JSON verdict fail-closed) ----
def test_pass2_omitted_content_hash_is_salvaged_via_expected_hash() -> None:
    # A reasoning-first verifier (GLM-5.1) returns valid JSON with the classification but OMITS
    # the redundant content_hash echo. The caller knows the expected hash, so the real verdict is
    # salvaged (NOT fail-closed) and the binding holds.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    expected_pass1 = MirrorPass1(answer_text="HbA1c fell 2.3 points.", citation_spans=spans)
    no_hash_pass2 = RoleResponse(
        raw_text=json.dumps({"classification": "grounded", "rationale": "ok"}),
        served_model=_MODEL,
    )
    transport = _SequencedTransport([pass1_response, no_hash_pass2])
    pass2, records = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert pass2.classification == "grounded"
    assert pass2.content_hash == _pass2_hash_for(expected_pass1)  # caller-bound expected hash
    assert len(records) == 2


def test_pass2_missing_classification_raises_mirror_parse_error() -> None:
    # JSON present but NO classification -> unrecoverable -> MirrorParseError (a verdict-level
    # failure that drives fail-closed -> UNSUPPORTED, never a whole-run crash).
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    expected_pass1 = MirrorPass1(answer_text="HbA1c fell 2.3 points.", citation_spans=spans)
    no_class_pass2 = RoleResponse(
        raw_text=json.dumps({"content_hash": _pass2_hash_for(expected_pass1)}),
        served_model=_MODEL,
    )
    transport = _SequencedTransport([pass1_response, no_class_pass2])
    with pytest.raises(MirrorParseError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_pass2_non_json_body_raises_mirror_parse_error() -> None:
    # A non-JSON pass-2 body is a verdict-level parse failure, NOT a transport fault -> fail-closed.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    junk_pass2 = RoleResponse(raw_text="not json at all {{{", served_model=_MODEL)
    transport = _SequencedTransport([pass1_response, junk_pass2])
    with pytest.raises(MirrorParseError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_pass2_present_but_wrong_hash_still_fails_binding() -> None:
    # A present-but-MISMATCHED hash is kept (not overwritten by the expected) so a genuine mixup
    # still trips verify_pass2_binding -> MirrorBindingError. Salvage applies ONLY to an omitted hash.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    wrong_hash_pass2 = RoleResponse(
        raw_text=json.dumps({"content_hash": "deadbeef", "classification": "grounded"}),
        served_model=_MODEL,
    )
    transport = _SequencedTransport([pass1_response, wrong_hash_pass2])
    with pytest.raises(MirrorBindingError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_pass2_present_but_empty_hash_is_not_salvaged_fails_binding() -> None:
    # Codex diff-gate P1: salvage is KEY-ABSENCE only. A present-but-EMPTY content_hash is a
    # present-but-wrong hash; it must be kept verbatim (NOT overwritten with the expected) so the
    # binding guard still trips. Truthiness salvage would have laundered "" past verify_pass2_binding.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    empty_hash_pass2 = RoleResponse(
        raw_text=json.dumps({"content_hash": "", "classification": "grounded"}),
        served_model=_MODEL,
    )
    transport = _SequencedTransport([pass1_response, empty_hash_pass2])
    with pytest.raises(MirrorBindingError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


# --- empty-both: no silent empty MirrorPass1 ---------------------------------------
def test_empty_both_citation_sources_raises_mirror_citation_error() -> None:
    # No structured citations AND no <co> spans -> no grounded citation -> fail closed.
    pass1_response = RoleResponse(raw_text="A bare answer with no citations.", served_model=_MODEL)
    # Only pass-1 should be consumed; pass-2 should never be reached.
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert len(transport.requests) == 1  # pass-2 never called


# --- iter-4 citation-binding guard -------------------------------------------------
def test_empty_doc_id_span_is_rejected() -> None:
    # <co>covered</co:> -> a span with empty doc_ids; rejected -> no grounded citation.
    pass1_response = RoleResponse(raw_text="<co>covered</co:>", served_model=_MODEL)
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_unknown_doc_id_span_is_rejected() -> None:
    # span cites a doc_id never supplied -> hallucinated identity -> rejected.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_phantom",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_mixed_real_and_hallucinated_doc_ids_rejected_whole() -> None:
    # One real + one hallucinated doc_id in the SAME span -> reject the whole span.
    spans = [
        CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1", "doc_phantom")),
    ]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_real_doc_id_span_is_accepted() -> None:
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    transport = _SequencedTransport(
        [pass1_response, _pass2_response_for(expected_pass1)]
    )
    pass2, records = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert len(records) == 2
    assert records[0].parsed.citation_spans == spans
    assert pass2.classification == "grounded"


def test_empty_doc_id_in_evidence_set_does_not_launder_empty_citation_codex_diff_p1() -> None:
    """Codex diff iter-1 P1: if the supplied evidence set itself contains an
    EvidenceDocument with an empty doc_id, a citation span with doc_ids=("",) must STILL be
    rejected. valid_doc_ids excludes empty ids AND the validator rejects empty-doc_id spans,
    so an empty doc_id can never bind — leaving no grounded citation -> MirrorCitationError."""
    docs_with_empty = [
        EvidenceDocument(doc_id="", text="a document that was given an empty id"),
        EvidenceDocument(doc_id="doc_real", text="HbA1c fell."),
    ]
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, docs_with_empty, model_slug=_MODEL)
    assert len(transport.requests) == 1  # pass-2 never reached


def test_whitespace_doc_id_span_is_rejected() -> None:
    # A whitespace-only doc_id is not a real identity even if echoed in the evidence set.
    docs = [EvidenceDocument(doc_id="   ", text="whitespace id"), *_DOCS]
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("   ",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, docs, model_slug=_MODEL)


# --- I-run11-002 L2: robust pass-2 classification extraction (format-noise tolerance) -----
def _pass2_raw(pass1: MirrorPass1, body_inner: str) -> RoleResponse:
    """A pass-2 RoleResponse whose raw_text is exactly `body_inner` (so a test can hand-craft
    fenced / alternate-key / nested JSON). Binds to `pass1` via the embedded expected hash so the
    test isolates the CLASSIFICATION extraction, not the binding guard (which has its own tests).
    """
    return RoleResponse(raw_text=body_inner, served_model=_MODEL)


def test_pass2_code_fenced_json_classification_recovered() -> None:
    # ```json\n{...}\n``` wrapper (run-11: 5/70 fenced) -> fence stripped, classification recovered.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(
        raw_text="HbA1c fell 2.3 points.", served_model=_MODEL, citations=spans
    )
    expected_pass1 = MirrorPass1(answer_text="HbA1c fell 2.3 points.", citation_spans=spans)
    h = _pass2_hash_for(expected_pass1)
    fenced = (
        "```json\n"
        + json.dumps({"content_hash": h, "classification": "Reinstatement Effect"})
        + "\n```"
    )
    transport = _SequencedTransport([pass1_response, _pass2_raw(expected_pass1, fenced)])
    pass2, records = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert pass2.classification == "Reinstatement Effect"
    assert len(records) == 2


def test_pass2_code_fenced_no_newline_and_bare_fence_recovered() -> None:
    # Both the ```json{...``` no-newline-after-tag form (run-11 sample 9) and the bare ``` ... ```
    # no-language-tag form must unwrap and recover the verdict.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    h = _pass2_hash_for(expected_pass1)

    # no-newline-after-language-tag form
    p1a = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    body_no_nl = "```json{" + json.dumps({"content_hash": h, "classification": "Claim"})[1:] + "```"
    t_a = _SequencedTransport([p1a, _pass2_raw(expected_pass1, body_no_nl)])
    pass2_a, _ = run_mirror(t_a, _CLAIM, _DOCS, model_slug=_MODEL)
    assert pass2_a.classification == "Claim"

    # bare ``` fence with no language tag
    p1b = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    body_bare = "```\n" + json.dumps({"content_hash": h, "classification": "Polarization"}) + "\n```"
    t_b = _SequencedTransport([p1b, _pass2_raw(expected_pass1, body_bare)])
    pass2_b, _ = run_mirror(t_b, _CLAIM, _DOCS, model_slug=_MODEL)
    assert pass2_b.classification == "Polarization"


def test_pass2_alternate_classification_keys_recovered() -> None:
    # Canonical `classification` absent but a common alternate present (answer/category/label/class).
    # Run-11 evidence: answer x3, category x2, label x1. Each must recover the verdict.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    h = _pass2_hash_for(expected_pass1)
    for alt_key, value in (
        ("answer", "Claim"),
        ("category", "Economics"),
        ("label", "AI"),
        ("class", "Method"),
    ):
        p1 = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
        body = json.dumps({"content_hash": h, alt_key: value})
        transport = _SequencedTransport([p1, _pass2_raw(expected_pass1, body)])
        pass2, _ = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
        assert pass2.classification == value, f"alt key {alt_key!r} not recovered"


def test_pass2_nested_classification_dict_recovered_as_string() -> None:
    # Run-11: 17/70 bodies put a NESTED dict under `classification` (heterogeneous sub-keys). The
    # field is typed str, so the dict is deterministically serialized to a stable, non-empty string
    # (NOT a Python repr, NOT fail-closed). The recovered string must contain a sub-value.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    h = _pass2_hash_for(expected_pass1)
    nested = {"domain": "Economics", "subdomain": "Labor Economics"}
    body = json.dumps({"content_hash": h, "classification": nested})
    transport = _SequencedTransport([pass1_response, _pass2_raw(expected_pass1, body)])
    pass2, _ = run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert isinstance(pass2.classification, str)
    assert "Economics" in pass2.classification  # sub-value preserved, not lost
    assert pass2.classification.startswith("{")  # serialized, deterministic


def test_pass2_pure_garbage_raises_mirror_parse_error_fail_closed() -> None:
    # A non-JSON body that is NOT a fenced wrapper of valid JSON stays unrecoverable -> fail-closed.
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    transport = _SequencedTransport(
        [pass1_response, _pass2_raw(expected_pass1, "I think the classification is probably a Claim.")]
    )
    with pytest.raises(MirrorParseError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_pass2_fenced_garbage_raises_mirror_parse_error_fail_closed() -> None:
    # A fenced wrapper whose BODY is still not JSON must remain fail-closed (the fence strip is not
    # an escape hatch that fabricates a verdict).
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    transport = _SequencedTransport(
        [pass1_response, _pass2_raw(expected_pass1, "```json\nnot json at all\n```")]
    )
    with pytest.raises(MirrorParseError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_pass2_answer_text_only_is_not_a_verdict_fail_closed() -> None:
    # NO-FALSE-ACCEPT regression guard: a body carrying ONLY the echoed pass-1 `answer_text` key
    # (no classification, no alternate) must NOT be laundered into a verdict. Exact key matching
    # means "answer" != "answer_text", so nothing recovers -> MirrorParseError (fail-closed).
    spans = [CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))]
    pass1_response = RoleResponse(raw_text="answer", served_model=_MODEL, citations=spans)
    expected_pass1 = MirrorPass1(answer_text="answer", citation_spans=spans)
    h = _pass2_hash_for(expected_pass1)
    body = json.dumps({"content_hash": h, "answer_text": "Automation enables capital to..."})
    transport = _SequencedTransport([pass1_response, _pass2_raw(expected_pass1, body)])
    with pytest.raises(MirrorParseError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)


def test_no_co_span_claim_still_unsupported_pass1_grounding_untouched() -> None:
    # HARD CONSTRAINT proof: a claim with NO valid <co> span (and no structured citations) still
    # fails closed at pass-1 grounding (MirrorCitationError) REGARDLESS of how lenient pass-2 is.
    # pass-2 is never reached -> len(requests)==1 proves the pass-1 grounding gate is untouched.
    pass1_response = RoleResponse(
        raw_text="A bare grounded-sounding answer with no citation spans.", served_model=_MODEL
    )
    transport = _SequencedTransport([pass1_response])
    with pytest.raises(MirrorCitationError):
        run_mirror(transport, _CLAIM, _DOCS, model_slug=_MODEL)
    assert len(transport.requests) == 1  # pass-2 never reached; grounding gate fired first


# --- build_mirror_pass2_request shape ----------------------------------------------
def test_pass2_request_has_response_format_and_no_documents() -> None:
    pass1 = MirrorPass1(
        answer_text="answer",
        citation_spans=[CitationSpan(span_start=0, span_end=6, doc_ids=("doc_surmount1",))],
    )
    request = build_mirror_pass2_request(pass1, model_slug=_MODEL)
    assert request.role == "mirror"
    assert request.params["response_format"]["type"] == "json_object"
    assert "documents" not in request.params
    assert request.params["pass2_input"]["content_hash"] == _pass2_hash_for(pass1)
