"""STEP 3: construction-by-validity comparison tables."""

import re

import src.polaris_graph.generator.multi_section_generator as m


def _sv(sentence: str, evidence_id: str) -> dict:
    return {
        "sentence": sentence,
        "tokens": [{"evidence_id": evidence_id}],
        "is_verified": True,
        "span_verdict": "kept",
    }


def _build(sentences, resolved, numbers):
    kept = [_sv(sentence, evidence_id) for evidence_id, sentence in sentences]
    bibliography = [
        {"evidence_id": evidence_id, "num": number}
        for evidence_id, number in numbers.items()
    ]
    return m._construct_synthesis_table(
        resolved, kept_sentences=kept, bibliography=bibliography,
    )


def test_off_by_default_no_regression(monkeypatch):
    monkeypatch.delenv("PG_SYNTHESIS_TABLE_CONSTRUCT", raising=False)
    assert m._construct_table_enabled() is False


def test_comparison_requires_shared_unit_and_measure_token():
    table = _build(
        [
            ("ev_a", "Productivity rose 14% [#ev:ev_a:0-20]."),
            ("ev_b", "Productivity rose 22% [#ev:ev_b:0-20]."),
        ],
        "Productivity rose 14% [7]. Productivity rose 22% [9].",
        {"ev_a": 7, "ev_b": 9},
    )
    assert "| Productivity rose 14%. | 14% | [7] |" in table
    assert "| Productivity rose 22%. | 22% | [9] |" in table


def test_same_unit_different_constructs_do_not_form_false_comparison():
    table = _build(
        [
            ("ev_a", "Productivity rose 14% [#ev:ev_a:0-20]."),
            ("ev_b", "Inflation reached 22% [#ev:ev_b:0-20]."),
        ],
        "Productivity rose 14% [1]. Inflation reached 22% [2].",
        {"ev_a": 1, "ev_b": 2},
    )
    assert table == ""


def test_every_factual_cell_is_a_literal_span_of_its_verified_sentence():
    sources = {
        "[1]": "Output per worker was 11 kg [#ev:ev_a:0-20].",
        "[2]": "Output per worker was 13 kg [#ev:ev_b:0-20].",
    }
    table = _build(
        [("ev_a", sources["[1]"]), ("ev_b", sources["[2]"])],
        "Output per worker was 11 kg [1]. Output per worker was 13 kg [2].",
        {"ev_a": 1, "ev_b": 2},
    )
    for line in table.splitlines()[2:]:
        finding, value, source = [cell.strip().replace(r"\|", "|") for cell in line.strip("|").split("|")]
        marker_free = re.sub(r"\s*\[#ev:[^\]]+\]", "", sources[source])
        marker_free = re.sub(r"\s+([.,;:])", r"\1", marker_free)
        assert finding in marker_free
        assert value in marker_free


def test_real_evidence_to_citation_map_is_used_not_marker_guessing():
    table = _build(
        [
            ("source_alpha", "Throughput was 4 units [#ev:source_alpha:0-10]."),
            ("source_beta", "Throughput was 6 units [#ev:source_beta:0-10]."),
        ],
        "Throughput was 4 units [41]. Throughput was 6 units [73].",
        {"source_alpha": 41, "source_beta": 73},
    )
    assert "[41]" in table and "[73]" in table
    assert "[1]" not in table and "[2]" not in table


def test_render_withheld_verified_sentence_cannot_reenter_via_table():
    table = _build(
        [
            ("ev_a", "Output was 4 units [#ev:ev_a:0-10]."),
            ("ev_b", "Output was 6 units [#ev:ev_b:0-10]."),
        ],
        # ev_b was withheld by a render screen and is absent from final prose.
        "Output was 4 units [1].",
        {"ev_a": 1, "ev_b": 2},
    )
    assert table == ""


def test_clause_and_source_must_cooccur_in_same_resolved_sentence():
    table = _build(
        [
            ("ev_a", "Output was 4 units [#ev:ev_a:0-10]."),
            ("ev_b", "Output was 4 units [#ev:ev_b:0-10]."),
        ],
        # The duplicate clause survives only under ev_a; [2] belongs to a
        # different sentence and cannot lend its marker to ev_b's kept SV.
        "Output was 4 units [1]. A separate qualitative finding remained [2].",
        {"ev_a": 1, "ev_b": 2},
    )
    assert table == ""


def test_non_comparable_findings_remain_in_untouched_prose():
    prose = "Output was 4 units [1]. A qualitative boundary remained [2]."
    table = m._construct_synthesis_table(prose)
    assert table == ""
    assert m._attach_synthesis_matrix(prose, table) == prose


def test_appended_markdown_survives_flatten_safe_seam():
    prose = "Output was 4 units [1]. Output was 6 units [2]."
    table = m._construct_synthesis_table(prose)
    rendered = m._attach_synthesis_matrix(prose, table)
    assert rendered.startswith(prose)
    assert "\n\n| Finding | Value | Source |\n|---|---|---|" in rendered
    assert rendered.count("\n| Output") == 2


def test_bare_numbers_have_no_value_unit_span():
    assert m._construct_synthesis_table("Output was 4 [1]. Output was 6 [2].") == ""


def test_currency_scale_is_part_of_comparability_key():
    table = _build(
        [
            ("ev_a", "Program cost was $4 million [#ev:ev_a:0-10]."),
            ("ev_b", "Program cost was $6 billion [#ev:ev_b:0-10]."),
        ],
        "Program cost was $4 million [1]. Program cost was $6 billion [2].",
        {"ev_a": 1, "ev_b": 2},
    )
    assert table == ""


def test_all_independent_comparable_groups_are_rendered_without_largest_group_cap():
    table = _build(
        [
            ("ev_a", "Output was 4 units [#ev:ev_a:0-10]."),
            ("ev_b", "Output was 6 units [#ev:ev_b:0-10]."),
            ("ev_c", "Latency was 8 ms [#ev:ev_c:0-10]."),
            ("ev_d", "Latency was 9 ms [#ev:ev_d:0-10]."),
        ],
        (
            "Output was 4 units [1]. Output was 6 units [2]. "
            "Latency was 8 ms [3]. Latency was 9 ms [4]."
        ),
        {"ev_a": 1, "ev_b": 2, "ev_c": 3, "ev_d": 4},
    )
    assert table.count("| Finding | Value | Source |") == 2
    assert all(f"[{number}]" in table for number in range(1, 5))
