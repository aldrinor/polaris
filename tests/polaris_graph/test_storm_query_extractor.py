"""I-cap-002 feature 1/4 (#1060): tests for the STORM benchmark question extractor."""

from __future__ import annotations

from src.polaris_graph.retrieval.storm_query_extractor import extract_storm_questions


def _conv(questions: list[str]) -> dict:
    return {"perspective": "p", "rounds": [{"question": q, "answer": "a"} for q in questions]}


def test_extracts_questions_across_conversations_in_order():
    convs = [_conv(["What is the labor displacement rate?", "Which sectors are most exposed?"]),
             _conv(["How does reskilling affect outcomes?"])]
    out = extract_storm_questions(convs)
    assert out == [
        "What is the labor displacement rate?",
        "Which sectors are most exposed?",
        "How does reskilling affect outcomes?",
    ]


def test_case_insensitive_dedup_preserves_first_order():
    convs = [_conv(["AI and jobs", "ai AND jobs", "Distinct question"])]
    out = extract_storm_questions(convs)
    assert out == ["AI and jobs", "Distinct question"]


def test_cap_is_respected():
    convs = [_conv([f"question number {i}" for i in range(50)])]
    out = extract_storm_questions(convs, cap=10)
    assert len(out) == 10
    assert out[0] == "question number 0"


def test_empty_blank_and_malformed_are_safe():
    assert extract_storm_questions(None) == []
    assert extract_storm_questions([]) == []
    assert extract_storm_questions([{"rounds": [{"question": ""}, {"question": "   "}]}]) == []
    # malformed entries (non-dict conversation / round) are skipped, not raised
    assert extract_storm_questions(["not a dict", {"rounds": ["bad", {"question": "ok"}]}]) == ["ok"]
    # a conversation with no rounds key
    assert extract_storm_questions([{"perspective": "p"}]) == []
