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
    # Default the entailment gate OFF for the STRUCTURAL/verbatim tests so they exercise the
    # deterministic lexical fallback (no live judge). The entailment tests below opt back IN with a
    # mocked judge. (Production default is 'on'; see config_defaults.)
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX_ENTAILMENT", "off")
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


# ==================== ROUND 5 — polarity / coordination / unicode / screening ======================
# --- Sol's round-5 A counterexamples ---
def test_A5_polarity_negation_dropped(msg):
    assert _grounded(msg, _cells("—", "—", "—", "detectable increase", "—", "[1]"),
                     {"[1]"}, ["There was no detectable increase [1]."]) is False
    assert _grounded(msg, _cells("—", "—", "—", "increase", "—", "[1]"),
                     {"[1]"}, ["There was no increase [1]."]) is False


def test_A5_coordination_and_dropped(msg):
    # Alpha coordinated with Beta's 91% across an "and"; Alpha must not borrow Beta's value.
    sents = ["Study Alpha measured productivity at 14% and Study Beta measured revenue at 91% [1]."]
    cells = _cells("Study Alpha", "—", "revenue", "91%", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


@pytest.mark.parametrize("sep", [" ", " ", " ", "٬"])
def test_A5_whitespace_and_unicode_thousands_dropped(msg, sep):
    # "5" must not ground inside "5 000" for ASCII space, NBSP, narrow-NBSP, Arabic thousands sep.
    sents = [f"The count was 5{sep}000 units [1]."]
    cells = _cells("—", "—", "count", "5", "—", "[1]")
    assert _grounded(msg, cells, {"[1]"}, sents) is False


def test_A5_fullwidth_matches_consistently(msg):
    # NFKC folds full-width "１４％" to "14%"; the ASCII cell "14%" grounds it (consistent), and "14"
    # alone does NOT (cross-unit) because "%" is token-internal.
    sents = ["Output rose １４％ [1]."]
    assert _grounded(msg, _cells("—", "—", "output", "14%", "—", "[1]"), {"[1]"}, sents) is True
    assert _grounded(msg, _cells("—", "—", "output", "14", "—", "[1]"), {"[1]"}, sents) is False


def test_A5_full_atom_with_modifier_kept(msg):
    # A cell that copies the FULL atom including its governing modifier grounds.
    assert _grounded(msg, _cells("—", "—", "—", "no detectable increase", "—", "[1]"),
                     {"[1]"}, ["There was no detectable increase [1]."]) is True
    assert _grounded(msg, _cells("—", "—", "—", "up to 14%", "—", "[1]"),
                     {"[1]"}, ["Gains reached up to 14% [1]."]) is True


# --- my own adversarial A cases (5+) ---
@pytest.mark.parametrize("clause,cell", [
    ("Gains were up to 14% [1].", "14%"),               # up to
    ("Gains were more than 14% [1].", "14%"),           # more than
    ("The effect was only 14% [1].", "14%"),            # only
    ("At least 5 trials were run [1].", "5 trials"),    # at least
    ("Output rose approximately 14% [1].", "14%"),      # approximately
    ("Effects were less than 5% [1].", "5%"),           # less than
    ("Output fell under 3% [1].", "3%"),                # under
])
def test_A5_adversarial_modifiers_dropped(msg, clause, cell):
    assert _grounded(msg, _cells("—", "—", "—", cell, "—", "[1]"), {"[1]"}, [clause]) is False


@pytest.mark.parametrize("clause,cell", [
    ("Output rose to 14% [1].", "14%"),                 # "to" is NOT a modifier (reached 14%)
    ("A randomized trial reported 5 000 cases [1].", "5 000 cases"),  # full grouped number
    ("Output rose 14% overall [1].", "14%"),            # trailing word, not governing
    ("The 14% gain was real [1].", "14%"),              # bare article before value is fine
])
def test_A5_adversarial_legit_kept(msg, clause, cell):
    assert _grounded(msg, _cells("—", "—", "—", cell, "—", "[1]"), {"[1]"}, [clause]) is True


@pytest.mark.parametrize("clause", [
    "Output rose roughly a 14% gain [1].",              # modifier through article "a"
    "It was less than the 14% baseline [1].",           # phrase modifier through article "the"
])
def test_A5_modifier_through_article_dropped(msg, clause):
    assert _grounded(msg, _cells("—", "—", "—", "14%", "—", "[1]"), {"[1]"}, [clause]) is False


# ==================== BLOCK A — ENTAILMENT gate (closes verb-scoped negation; admits paraphrase) ==========
class _FakeJudge:
    """Deterministic stand-in for the frozen entailment judge (no live LLM in unit tests)."""
    def __init__(self, verdict, reason=""):
        self._v, self._r = verdict, reason
        self.calls = []

    def judge(self, hypothesis, premise):
        self.calls.append((hypothesis, premise))
        return (self._v, self._r)


def _patch_judge(monkeypatch, verdict, reason=""):
    fj = _FakeJudge(verdict, reason)
    sv = importlib.import_module("src.polaris_graph.clinical_generator.strict_verify")
    monkeypatch.setattr(sv, "_get_judge", lambda: fj)
    return fj


def _entail_matrix(msg, monkeypatch, rows, prose, nums, verdict="ENTAILED", reason=""):
    """Run _extract_synthesis_matrix with entailment ON and a mocked judge; return (out, fake_judge)."""
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX_ENTAILMENT", "on")
    fj = _patch_judge(monkeypatch, verdict, reason)
    raw = "\n".join([HEADER, SEP, *rows])
    out = msg._extract_synthesis_matrix(raw, nums, verified_prose=prose, min_rows=3)
    return out, fj


# 3 comparable rows, each citing a distinct [N], each with a one-[N] prose sentence.
_ENTAIL_ROWS = [
    _row("Alpha", "nurses", "productivity", "14%", "trial", "[1]"),
    _row("Beta", "clerks", "productivity", "22%", "trial", "[2]"),
    _row("Gamma", "agents", "productivity", "31%", "trial", "[3]"),
]
_ENTAIL_PROSE = (
    "Alpha reported a 14% productivity gain among nurses [1]. "
    "Beta reported a 22% productivity gain among clerks [2]. "
    "Gamma reported a 31% productivity gain among agents [3]."
)


def test_entail_verb_scoped_negation_dropped(msg, monkeypatch):
    # The class the LEXICAL rule could never close: negation governs the value through a verb.
    prose = ("Alpha output did not rise 14% [1]. Beta output did not rise 22% [2]. "
             "Gamma output did not rise 31% [3].")
    out, fj = _entail_matrix(msg, monkeypatch, _ENTAIL_ROWS, prose, {1, 2, 3},
                             verdict="CONTRADICTED")
    assert out == ""                         # every row dropped => table suppressed
    assert len(fj.calls) >= 1                # the judge WAS consulted


def test_entail_faithful_paraphrase_kept(msg, monkeypatch):
    # Benefit restored: a faithful paraphrase the over-strict verbatim rule would have dropped.
    out, fj = _entail_matrix(msg, monkeypatch, _ENTAIL_ROWS, _ENTAIL_PROSE, {1, 2, 3},
                             verdict="ENTAILED")
    assert out != "" and out.count("\n") >= 4  # header+sep+3 rows survive
    assert len(fj.calls) == 3


@pytest.mark.parametrize("verdict,reason", [
    ("NEUTRAL", ""), ("CONTRADICTED", ""), ("ENTAILED", "judge_error: timeout"),
])
def test_entail_fail_closed(msg, monkeypatch, verdict, reason):
    out, _ = _entail_matrix(msg, monkeypatch, _ENTAIL_ROWS, _ENTAIL_PROSE, {1, 2, 3},
                            verdict=verdict, reason=reason)
    assert out == ""                         # NEUTRAL / CONTRADICTED / judge_error all drop the row


def test_entail_structural_prefilter_runs_before_judge(msg, monkeypatch):
    # A number absent from the grounding clause must drop the row BEFORE the judge is called.
    rows = [
        _row("Alpha", "nurses", "productivity", "99%", "trial", "[1]"),  # 99% not in prose
        _row("Beta", "clerks", "productivity", "22%", "trial", "[2]"),
        _row("Gamma", "agents", "productivity", "31%", "trial", "[3]"),
    ]
    out, fj = _entail_matrix(msg, monkeypatch, rows, _ENTAIL_PROSE, {1, 2, 3}, verdict="ENTAILED")
    # Row 1 dropped by the numeric pre-check => <3 survive => suppressed; judge called only for 2/3.
    assert out == ""
    assert all("99%" not in h for h, _ in fj.calls)   # the fabricated-number row never reached the judge


def test_entail_off_falls_back_to_verbatim(msg, monkeypatch):
    # Entailment OFF => strict verbatim lexical grounding (safe, stricter) — never less safe.
    monkeypatch.setenv("PG_SYNTHESIS_MATRIX_ENTAILMENT", "off")
    fj = _patch_judge(monkeypatch, "ENTAILED")
    raw = "\n".join([HEADER, SEP, *_ENTAIL_ROWS])
    # paraphrase prose => verbatim rule drops all => suppressed, and the judge is NEVER consulted
    out = msg._extract_synthesis_matrix(raw, {1, 2, 3}, verified_prose=_ENTAIL_PROSE, min_rows=3)
    assert out == ""
    assert fj.calls == []


# --- Sol's round-5 C counterexample + my adversarial screening cases ---
@pytest.mark.parametrize("field", [
    "T1_topic", "pipeline_internal", "tier_3_source", "ev_12345", "basket_7",
    "possible_metric_mismatch note", "UNKNOWN_bucket", "T7.subtype",
])
def test_C5_field_screen_rejects_internal(msg, field):
    assert msg._reader_field_safe(field) is False


@pytest.mark.parametrize("field", ["wage growth", "healthcare automation", "regional effects 2024"])
def test_C5_field_screen_allows_clean(msg, field):
    assert msg._reader_field_safe(field) is True


def test_C5_screened_topic_dropped_from_prose(msg):
    text = msg._deterministic_reader_limitations(
        {"T1": 0.5}, None, None, ["pipeline_internal", "labor market"]
    )
    assert "pipeline" not in text
    assert "labor market" in text


def test_C5_override_t3_t6_labels(msg):
    text = msg._deterministic_reader_limitations(
        None, None, None, None, tier_disclosure_override="T3=50%, T6=50%",
    )
    assert "50% government and regulatory sources" in text
    assert "50% news and non-peer-reviewed web content" in text
    for banned in ("T3", "T6", "tier"):
        assert banned not in text
