"""Integration safety tests — reproduce EACH counterexample from Sol's integrated re-gate, then prove
it fixed:
  BLOCK A — L2 cells must be VERBATIM token-boundary spans of the row's single cited sentence
            (paraphrase / polarity / sign-flip all rejected).
  BLOCK B — a table-bearing section is fully EXEMPT from L5 (its grounding prose survives).
  BLOCK C — deterministic reader Limitations states CORRECT telemetry facts (T2 != primary; no
            working-paper inference; honors override; comparable/not-comparable partition).
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


# ============================ BLOCK A — verbatim-span grounding (Sol's 3 counterexamples) ==========
def test_A1_paraphrase_dropped(msg):
    # "randomized analysis" is NOT a verbatim span of "random-effects analysis".
    sents = ["The random-effects analysis reported a 14% gain [1]."]
    cells = _cells("—", "—", "gain", "14%", "randomized analysis", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A2_polarity_dropped(msg):
    # "no detectable change" must not match a sentence asserting a detectable change.
    sents = ["There was a detectable change of 14% [1]."]
    cells = _cells("—", "—", "change", "no detectable change 14%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A3_sign_flip_dropped(msg):
    # "-14%" must not match "+14%".
    sents = ["Output rose +14% in the trial [1]."]
    cells = _cells("—", "—", "output", "-14%", "trial", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_verbatim_row_kept(msg):
    sents = ["In a randomized trial, output rose +14% [1]."]
    cells = _cells("—", "—", "output", "+14%", "randomized trial", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is True


def test_A_multi_citation_needs_one_coherent_sentence(msg):
    # A row citing [1] and [2] must have BOTH in one sentence; split across sentences => dropped.
    sents = ["Output rose 14% [1].", "Coverage was broad [2]."]
    cells = _cells("—", "—", "output", "14%", "—", "[1][2]")
    assert msg._synthesis_row_grounded(cells, [1, 2], sents) is False


def test_A_end_to_end_fabricated_table_suppressed(msg):
    prose = (
        "The random-effects analysis reported 14% [1]. A detectable change of 34% occurred [2]. "
        "Output rose +56% [3]."
    )
    raw = "\n".join([HEADER, SEP,
                     _row("Stanford", "biotech", "gain", "14%", "randomized analysis", "[1]"),
                     _row("—", "—", "change", "no detectable change 34%", "—", "[2]"),
                     _row("—", "—", "output", "-56%", "—", "[3]")])
    # All three rows fabricate (paraphrase / polarity / sign) => all dropped => suppressed.
    assert msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=prose, min_rows=3) == ""


# --- round-3 counterexamples: token-continuation boundaries + equal-citation + Ref syntax ---
def test_A_non_randomized_dropped(msg):
    sents = ["A non-randomized analysis found 14% [1]."]
    cells = _cells("—", "—", "—", "14%", "randomized analysis", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_number_inside_signed_dropped(msg):
    # cell "14%" must not match inside "-14%".
    sents = ["The effect was -14% [1]."]
    cells = _cells("—", "—", "—", "14%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_number_inside_comparator_dropped(msg):
    # cell "5%" must not match inside "<5%".
    sents = ["The effect was <5% [1]."]
    cells = _cells("—", "—", "—", "5%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_possessive_dropped(msg):
    # cell "worker" must not match inside "worker's".
    sents = ["Each worker's output rose 3% [1]."]
    cells = _cells("worker", "—", "—", "3%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_none_content_cell_must_ground(msg):
    # "none" is content (not the em-dash), and is absent from the sentence => drop.
    sents = ["Output rose 14% [1]."]
    cells = _cells("none", "—", "—", "14%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_merged_unit_partial_citation_dropped(msg):
    # One splitter unit citing {1,9}; a row citing only [1] cannot copy "+99%" from the [9] clause.
    sents = ["Output fell -14% [1]; output rose +99% [9]."]
    cells = _cells("—", "—", "output", "+99%", "—", "[1]")
    assert msg._synthesis_row_grounded(cells, [1], sents) is False


def test_A_ref_must_be_only_markers(msg):
    prose = "Alpha rose 14% [1]. Beta rose 34% [2]. Gamma rose 56% [3]. Delta rose 78% [4]."
    raw = "\n".join([HEADER, SEP,
                     _row("alpha", "—", "—", "14%", "—", "[1]"),
                     _row("beta", "—", "—", "34%", "—", "[2]"),
                     _row("gamma", "—", "—", "56%", "—", "[3]"),
                     _row("delta", "—", "—", "78%", "—", "[4] extra")])  # Ref not pure markers
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3, 4}, verified_prose=prose, min_rows=3)
    assert out.count("\n") == 4  # header + sep + 3 kept rows; delta row dropped
    assert "delta" not in out


def test_A_stray_citation_in_content_cell_dropped(msg):
    prose = "Alpha rose 14% [1]. Beta rose 34% [2]. Gamma rose 56% [3]. Delta rose 78% [4]."
    raw = "\n".join([HEADER, SEP,
                     _row("alpha", "—", "—", "14%", "—", "[1]"),
                     _row("beta", "—", "—", "34%", "—", "[2]"),
                     _row("gamma", "—", "—", "56%", "—", "[3]"),
                     _row("delta [4]", "—", "—", "78%", "—", "[4]")])  # stray [4] in a content cell
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3, 4}, verified_prose=prose, min_rows=3)
    assert out.count("\n") == 4
    assert "delta" not in out


# ============================ BLOCK B — table-bearing section fully exempt from L5 ==================
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
    s2 = SR("Two", dup + " Extra detail [3]." + table)   # table-bearing => exempt
    s3 = SR("Three", dup + " Other framing [4].")
    guard.consolidate_cross_section_repetition([s1, s2, s3])
    # Section 2 untouched: its grounding sentence AND the table survive verbatim.
    assert dup in s2.verified_text
    assert HEADER in s2.verified_text
    assert "| exposed occupations | labor | employment | 5 pp | panel | [1] |" in s2.verified_text


# ============================ BLOCK C — correct deterministic limitations facts ====================
def test_C_t2_never_labeled_primary(msg):
    text = msg._deterministic_reader_limitations({"T1": 0.0, "T2": 1.0}, None, None, None)
    assert "evidence syntheses (systematic reviews and meta-analyses)" in text
    assert "primary studies" not in text  # 0% T1 => no primary claim; T2 is NOT primary


def test_C_no_working_paper_inference(msg):
    text = msg._deterministic_reader_limitations({"T1": 1.0, "T2": 0.0}, None, None, None)
    assert "working paper" not in text.lower()
    assert "preprint" not in text.lower()
    assert "primary studies" in text


def test_C_override_honored_verbatim(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.04, "T2": 0.01}, None, None, None,
        tier_disclosure_override="Sources comprise 4% primary and 1% synthesis studies.",
    )
    assert "Sources comprise 4% primary and 1% synthesis studies." in text
    assert "Of the retrieved corpus" not in text  # override wins => no re-derived fraction sentence


def test_C_conflict_partition_not_magnitudes(msg):
    contradictions = [
        {"predicate": "A vs B"},                       # comparable
        {"predicate": "C vs D [not_comparable]"},       # not comparable
    ]
    text = msg._deterministic_reader_limitations({"T1": 0.5}, contradictions, None, None)
    assert "differing magnitudes" not in text
    assert "conflicting findings" in text
    assert "could not be directly compared" in text


def test_C_possible_mismatch_never_conflicting(msg, monkeypatch):
    # Suppression is default-ON; a [possible_metric_mismatch] record must NOT render as a conflict.
    monkeypatch.delenv("PG_CONTRADICTION_SUPPRESS_METRIC_MISMATCH", raising=False)
    contradictions = [{"predicate": "X vs Y [possible_metric_mismatch]"}]
    text = msg._deterministic_reader_limitations({"T1": 0.5}, contradictions, None, None)
    assert "conflicting findings" not in text
    assert "possible metric mismatch" in text


def test_C_override_tier_codes_translated(msg):
    # Production caller supplies raw tier codes; they must be translated, percentages preserved.
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T1=4%, T2=1%",
    )
    assert "4% primary studies" in text
    assert "1% evidence syntheses (systematic reviews and meta-analyses)" in text
    for banned in ("T1", "T2", "tier"):
        assert banned not in text


def test_C_no_internal_vocab(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.04, "T2": 0.01}, [{"predicate": "x"}], {"start": 2015, "end": 2025}, ["policy"]
    )
    for banned in ("telemetry", "pipeline", "T1", "T2", "tier", "T6"):
        assert banned not in text
    assert "retrieved corpus" in text
    assert "2015-2025" in text


def test_C_deterministic_stable(msg):
    a = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    b = msg._deterministic_reader_limitations({"T1": 0.1, "T2": 0.0}, None, None, None)
    assert a == b
    assert "10% primary studies" in a
