"""Contract tests for the Mirror (Cohere) two-pass binding + citation parse.

Properties under test:
- build_pass2_input embeds a content_hash that matches the pass-1 artifact;
- verify_pass2_binding is True on the matching artifact, False on a regenerated answer
  AND False on the SAME answer_text with swapped/missing citation bindings (the P1-a
  composite-hash regression);
- parse_cohere_citations parses the golden <co> span format and tolerates empty input.
Pure logic, no model, no network.
"""

from __future__ import annotations

from pathlib import Path

from src.polaris_graph.roles.mirror_contract import (
    CitationSpan,
    MirrorPass1,
    MirrorPass2,
    build_pass2_input,
    parse_cohere_citations,
    verify_pass2_binding,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _pass1() -> MirrorPass1:
    return MirrorPass1(
        answer_text="Tirzepatide lowered HbA1c by 2.3 points.",
        citation_spans=[
            CitationSpan(span_start=0, span_end=11, doc_ids=("doc_surmount1",)),
            CitationSpan(span_start=20, span_end=40, doc_ids=("doc_surmount1", "doc_label2")),
        ],
    )


# --- composite hash binding --------------------------------------------------------
def test_build_pass2_input_embeds_matching_hash() -> None:
    pass1 = _pass1()
    payload = build_pass2_input(pass1)
    assert "content_hash" in payload
    assert payload["answer_text"] == pass1.answer_text
    pass2 = MirrorPass2(content_hash=payload["content_hash"], classification="grounded")
    assert verify_pass2_binding(pass1, pass2) is True


def test_binding_true_on_exact_match() -> None:
    pass1 = _pass1()
    pass2 = MirrorPass2(
        content_hash=build_pass2_input(pass1)["content_hash"],
        classification="grounded",
    )
    assert verify_pass2_binding(pass1, pass2) is True


def test_binding_false_on_regenerated_answer_text() -> None:
    pass1 = _pass1()
    pass2 = MirrorPass2(
        content_hash=build_pass2_input(pass1)["content_hash"],
        classification="grounded",
    )
    regenerated = MirrorPass1(
        answer_text="Tirzepatide lowered HbA1c by 2.3 points!",  # one char changed
        citation_spans=pass1.citation_spans,
    )
    assert verify_pass2_binding(regenerated, pass2) is False


# --- P1-a regression: same answer_text but different/missing citation bindings ------
def test_binding_false_same_text_swapped_doc_ids() -> None:
    pass1 = _pass1()
    pass2 = MirrorPass2(
        content_hash=build_pass2_input(pass1)["content_hash"],
        classification="grounded",
    )
    swapped = MirrorPass1(
        answer_text=pass1.answer_text,  # IDENTICAL text
        citation_spans=[
            CitationSpan(span_start=0, span_end=11, doc_ids=("doc_DIFFERENT",)),
            CitationSpan(span_start=20, span_end=40, doc_ids=("doc_surmount1", "doc_label2")),
        ],
    )
    assert verify_pass2_binding(swapped, pass2) is False


def test_binding_false_same_text_missing_citation() -> None:
    pass1 = _pass1()
    pass2 = MirrorPass2(
        content_hash=build_pass2_input(pass1)["content_hash"],
        classification="grounded",
    )
    missing = MirrorPass1(
        answer_text=pass1.answer_text,  # IDENTICAL text
        citation_spans=[pass1.citation_spans[0]],  # second span dropped
    )
    assert verify_pass2_binding(missing, pass2) is False


def test_binding_false_same_text_moved_span_offset() -> None:
    pass1 = _pass1()
    pass2 = MirrorPass2(
        content_hash=build_pass2_input(pass1)["content_hash"],
        classification="grounded",
    )
    moved = MirrorPass1(
        answer_text=pass1.answer_text,
        citation_spans=[
            CitationSpan(span_start=1, span_end=11, doc_ids=("doc_surmount1",)),  # start moved
            CitationSpan(span_start=20, span_end=40, doc_ids=("doc_surmount1", "doc_label2")),
        ],
    )
    assert verify_pass2_binding(moved, pass2) is False


def test_anti_proof_text_only_hash_would_collide() -> None:
    """Anti-proof that the hash is COMPOSITE, not text-only: two pass-1 artifacts with
    IDENTICAL answer_text but different citation bindings must produce DIFFERENT hashes.
    A text-only sha256 would collide here; the composite hash must not."""
    base = _pass1()
    swapped = MirrorPass1(
        answer_text=base.answer_text,
        citation_spans=[
            CitationSpan(span_start=0, span_end=11, doc_ids=("doc_DIFFERENT",)),
            CitationSpan(span_start=20, span_end=40, doc_ids=("doc_surmount1", "doc_label2")),
        ],
    )
    assert build_pass2_input(base)["content_hash"] != build_pass2_input(swapped)["content_hash"]


def test_hash_injective_against_adversarial_doc_id_bytes() -> None:
    """P1-a injectivity: a doc_id carrying spaces/brackets (legal per parse_cohere_citations,
    which only forbids `>` and splits on `,`) must NOT let a crafted (answer, bindings) pair
    collide with another. A flat `answer + " " + json(bindings)` concatenation has an
    ambiguous boundary; the JSON-array canonical form does not. Distinct artifacts -> distinct
    hashes, always."""
    a = MirrorPass1(
        answer_text="X",
        citation_spans=[
            CitationSpan(0, 1, ("a",)),
            CitationSpan(2, 3, ("b",)),
        ],
    )
    # Adversarial: answer text that embeds the serialized first binding, doc_id with brackets.
    b = MirrorPass1(
        answer_text='X [[0,1,"a"',
        citation_spans=[CitationSpan(2, 3, ("b",))],
    )
    assert a.answer_text != b.answer_text or a.citation_spans != b.citation_spans
    assert build_pass2_input(a)["content_hash"] != build_pass2_input(b)["content_hash"]

    # doc_id literally containing a space and brackets is a distinct artifact, distinct hash.
    c = MirrorPass1(answer_text="claim", citation_spans=[CitationSpan(0, 5, ("doc [[x]] y",))])
    d = MirrorPass1(answer_text="claim", citation_spans=[CitationSpan(0, 5, ("doc",))])
    assert build_pass2_input(c)["content_hash"] != build_pass2_input(d)["content_hash"]


def test_binding_order_independent_for_identical_bindings() -> None:
    """Authoring order of spans must not change the hash when the binding SET is identical."""
    a = MirrorPass1(
        answer_text="x",
        citation_spans=[
            CitationSpan(0, 1, ("doc_a",)),
            CitationSpan(2, 3, ("doc_b",)),
        ],
    )
    b = MirrorPass1(
        answer_text="x",
        citation_spans=[
            CitationSpan(2, 3, ("doc_b",)),
            CitationSpan(0, 1, ("doc_a",)),
        ],
    )
    assert build_pass2_input(a)["content_hash"] == build_pass2_input(b)["content_hash"]


# --- parse_cohere_citations --------------------------------------------------------
def test_parse_cohere_citations_golden() -> None:
    spans = parse_cohere_citations(_read_fixture("cohere_citations_golden.txt"))
    assert len(spans) == 2
    # first span: single doc_id
    assert spans[0].doc_ids == ("doc_surmount1",)
    # second span: two doc_ids
    assert spans[1].doc_ids == ("doc_surmount1", "doc_label2")
    # offsets are over the cleaned (tag-stripped) text, monotonic and non-overlapping
    assert spans[0].span_start < spans[0].span_end <= spans[1].span_start < spans[1].span_end


def test_parse_cohere_citations_offsets_match_cleaned_text() -> None:
    raw = "A <co>bb</co:d1> C <co>dddd</co:d2,d3> E"
    spans = parse_cohere_citations(raw)
    # cleaned text = "A bb C dddd E"; "bb" at [2,4), "dddd" at [7,11)
    assert (spans[0].span_start, spans[0].span_end) == (2, 4)
    assert (spans[1].span_start, spans[1].span_end) == (7, 11)
    assert spans[1].doc_ids == ("d2", "d3")


def test_parse_cohere_citations_empty_returns_empty_list() -> None:
    assert parse_cohere_citations("") == []


def test_parse_cohere_citations_no_spans_returns_empty_list() -> None:
    assert parse_cohere_citations("plain answer with no co spans at all") == []


def test_parse_cohere_citations_tolerates_span_without_doc_ids() -> None:
    spans = parse_cohere_citations("text <co>covered</co:>")
    assert len(spans) == 1
    assert spans[0].doc_ids == ()
