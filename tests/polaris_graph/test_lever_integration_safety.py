"""Integration safety tests — reproduce EACH counterexample from Sol's integrated re-gates (rounds 2-4),
then prove it fixed:
  BLOCK A — L2 cells must be VERBATIM token-boundary spans of the single cited CLAUSE whose canonical
            markers equal the row's Ref (Unicode boundaries; cross-clause + [01] + sign/comparator all
            rejected).
  BLOCK B — a table-bearing section is fully EXEMPT from L5 (its grounding prose survives).
  BLOCK C — deterministic reader Limitations: full-parse-or-discard override with correct taxonomy
            labels; field screening; three-way contradiction partition.
"""
import importlib

import pytest

MSG = "src.polaris_graph.generator.multi_section_generator"
GUARD = "src.polaris_graph.generator.cross_section_repetition_guard"

HEADER = "| Study | Context | Measure | Finding | Design | Ref |"
SEP = "|---|---|---|---|---|---|"


@pytest.fixture()
def msg(monkeypatch):
    monkeypatch.delenv("PG_SYNTHESIS_MATRIX", raising=False)
    monkeypatch.delenv("PG_SWEEP_TABLE_CELL_VERIFY", raising=False)
    return importlib.import_module(MSG)


def _row(study, ctx, measure, finding, design, ref):
    return f"| {study} | {ctx} | {measure} | {finding} | {design} | {ref} |"


def _cells(study, ctx, measure, finding, design, ref):
    return [study, ctx, measure, finding, design, ref]


def _grounded(msg, cells, refs, sents):
    return msg._synthesis_row_grounded(cells, frozenset(refs), sents)


# ==================== BLOCK A — token-boundary / clause / exact-marker grounding ====================
def test_A_verbatim_single_clause_kept(msg):
    sents = ["In a randomized trial output rose +14% [1]."]  # one clause, all facts present
    cells = _cells("—", "—", "output", "+14%", "randomized trial", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is True


def test_A_paraphrase_dropped(msg):
    sents = ["The random-effects analysis reported a 14% gain [1]."]
    cells = _cells("—", "—", "gain", "14%", "randomized analysis", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_non_randomized_dropped(msg):
    sents = ["A non-randomized analysis found 14% [1]."]
    cells = _cells("—", "—", "—", "14%", "randomized analysis", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_polarity_dropped(msg):
    sents = ["There was a detectable change of 14% [1]."]
    cells = _cells("—", "—", "change", "no detectable change 14%", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


@pytest.mark.parametrize("prose_num,cell_val", [
    ("-14%", "14%"), ("≤5%", "5%"), ("≥5%", "5%"), ("≈5%", "5%"),
    ("±5%", "5%"), ("$5", "5"), ("5,000", "5"),
])
def test_A_numeric_lexeme_boundaries(msg, prose_num, cell_val):
    # The bare cell must NOT match inside a larger numeric lexeme (sign/comparator/currency/grouping).
    sents = [f"The measured effect was {prose_num} [1]."]
    cells = _cells("—", "—", "effect", cell_val, "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_possessive_and_connector_dropped(msg):
    assert _grounded(msg, _cells("worker", "—", "—", "3%", "—", "[1]"),
                     {"[1]"}, ["Each worker's output rose 3% [1]."]) is False
    assert _grounded(msg, _cells("worker", "—", "—", "3%", "—", "[1]"),
                     {"[1]"}, ["The worker_id field rose 3% [1]."]) is False


def test_A_cross_clause_dropped(msg):
    # Sol's Alpha/Beta repro: Beta's 99%/revenue must not be assignable to Alpha.
    sents = ["Study Alpha in nurses measured productivity at 14%, whereas Study Beta measured "
             "revenue at 99% [1]."]
    cells = _cells("Study Alpha", "nurses", "revenue", "99%", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_merged_unit_partial_citation_dropped(msg):
    sents = ["Output fell -14% [1]; output rose +99% [9]."]
    cells = _cells("—", "—", "output", "+99%", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_none_content_cell_must_ground(msg):
    sents = ["Output rose 14% [1]."]
    cells = _cells("none", "—", "—", "14%", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A_leading_zero_marker_dropped(msg):
    prose = "Alpha rose 14% [1]. Beta rose 34% [2]. Gamma rose 56% [3]."
    raw = "\n".join([HEADER, SEP,
                     _row("alpha", "—", "—", "14%", "—", "[01]"),   # non-canonical Ref
                     _row("beta", "—", "—", "34%", "—", "[2]"),
                     _row("gamma", "—", "—", "56%", "—", "[3]")])
    assert msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3) == ""


def test_A_ref_extra_text_and_stray_content_citation_dropped(msg):
    prose = "Alpha rose 14% [1]. Beta rose 34% [2]. Gamma rose 56% [3]. Delta rose 78% [4]."
    raw = "\n".join([HEADER, SEP,
                     _row("alpha", "—", "—", "14%", "—", "[1]"),
                     _row("beta", "—", "—", "34%", "—", "[2]"),
                     _row("gamma", "—", "—", "56%", "—", "[3]"),
                     _row("delta [4]", "—", "—", "78%", "—", "[4] see")])  # stray + non-pure Ref
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3, 4}, verified_prose=prose, min_rows=3)
    assert out.count("\n") == 4  # 3 kept rows; delta dropped
    assert "delta" not in out


def test_A_end_to_end_single_clause_kept(msg):
    prose = ("A randomized trial in writing raised output 34% [1]. "
             "A randomized trial in coding raised output 56% [2]. "
             "A randomized trial in support raised output 14% [3].")
    raw = "\n".join([HEADER, SEP,
                     _row("writing", "writing", "output", "34%", "randomized trial", "[1]"),
                     _row("coding", "coding", "output", "56%", "randomized trial", "[2]"),
                     _row("support", "support", "output", "14%", "randomized trial", "[3]")])
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3)
    assert out.startswith(HEADER)
    assert out.count("\n") == 4


# ==================== BLOCK B — table-bearing section fully exempt from L5 ==========================
def test_B_table_section_and_its_grounding_prose_survive(monkeypatch):
    guard = importlib.import_module(GUARD)
    monkeypatch.setenv("PG_CROSS_SECTION_REPETITION_GUARD", "1")

    class SR:
        def __init__(self, title, text):
            self.title = title
            self.verified_text = text
            self.dropped_due_to_failure = False
            self.is_gap_stub = False

    dup = "Employment fell by 5 percentage points in exposed occupations [1]."
    table = "\n\n" + "\n".join(
        [HEADER, SEP, "| exposed occupations | labor | employment | 5 pp | panel | [1] |"]
    )
    s1 = SR("One", dup + " Additional context here [2].")
    s2 = SR("Two", dup + " Extra detail [3]." + table)
    s3 = SR("Three", dup + " Other framing [4].")
    guard.consolidate_cross_section_repetition([s1, s2, s3])
    assert dup in s2.verified_text
    assert HEADER in s2.verified_text
    assert "| exposed occupations | labor | employment | 5 pp | panel | [1] |" in s2.verified_text


# ==================== BLOCK C — correct deterministic limitations facts ============================
def test_C_t2_never_labeled_primary(msg):
    text = msg._deterministic_reader_limitations({"T1": 0.0, "T2": 1.0}, None, None, None)
    assert "evidence syntheses (systematic reviews and meta-analyses)" in text
    assert "primary studies" not in text


def test_C_no_working_paper_inference(msg):
    text = msg._deterministic_reader_limitations({"T1": 1.0, "T2": 0.0}, None, None, None)
    assert "working paper" not in text.lower()
    assert "preprint" not in text.lower()
    assert "primary studies" in text


def test_C_override_codes_translated(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T1=4%, T2=1%",
    )
    assert "4% primary studies" in text
    assert "1% evidence syntheses (systematic reviews and meta-analyses)" in text
    for banned in ("T1", "T2", "tier"):
        assert banned not in text


def test_C_override_unknown_supported(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T1=4%, UNKNOWN=96%",
    )
    assert "4% primary studies" in text
    assert "96% unclassified sources" in text
    assert "UNKNOWN" not in text


def test_C_override_t7_label(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T7=10%",
    )
    assert "10% abstract-only or stub sources" in text
    assert "T7" not in text


def test_C_override_partial_discarded(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T1=4%, T2=oops",
    )
    assert "4%" not in text
    assert "primary studies" not in text


def test_C_override_exponent_discarded(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T1=4e1%, T2=1%",
    )
    assert "primary studies" not in text
    assert "40" not in text


def test_C_override_missing_percent_discarded(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.5}, None, None, None, tier_disclosure_override="T1=4, T2=1%",
    )
    assert "50% primary studies" in text   # discarded => falls back to tier_fractions
    assert "4%" not in text


def test_C_field_screen_date_and_topic(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.5},
        None,
        {"start": "T1", "end": "T7"},                 # unsafe date => screened out
        ["[not_comparable] effects", "wage growth"],  # first topic unsafe => dropped
    )
    for banned in ("T1", "T7", "[not_comparable]"):
        assert banned not in text
    assert "wage growth" in text


def test_C_possible_mismatch_never_conflicting(msg, monkeypatch):
    monkeypatch.delenv("PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH", raising=False)
    contradictions = [{"predicate": "X vs Y [possible_metric_mismatch]"}]
    text = msg._deterministic_reader_limitations({"T1": 0.5}, contradictions, None, None)
    assert "conflicting findings" not in text
    assert "possible metric mismatch" in text


def test_C_deterministic_stable(msg):
    a = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    b = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    assert a == b
    assert "10% primary studies" in a
