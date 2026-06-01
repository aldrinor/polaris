"""I-meta-006 (#1006) smoke — cash-free FACT benchmark scorer.

SPEND-FREE: the atomizer, span_fetcher, and judge are deterministic FAKES (no
LLM, no network). Verifies the §-1.1 guarantees Codex design-gate APPROVE'd:
system-agnostic atomic extraction, evidence-locked judge (substring-validated
span_quote), most-specific span, UNREACHABLE-in-denominator, uncited→UNSUPPORTED,
lane2_pending (no false fail), clinical-3 / overall-5 split. Plain assertions.
"""
from __future__ import annotations

from src.polaris_graph.benchmark.benchmark_scorecard import (
    build_scorecard,
    normalize_qid,
    score_system_question,
)
from src.polaris_graph.benchmark.claim_audit_scorer import ClaimRow
from src.polaris_graph.benchmark.fact_scorer import (
    JudgeVerdict,
    SpanResult,
    score_atoms,
)
from src.polaris_graph.benchmark.report_claim_extractor import (
    CitationRef,
    extract_atoms,
)


# ── extraction: 3 citation formats + uncited + compound ──────────────────────
def test_extract_polaris_ev_span_tokens():
    txt = "Semaglutide achieved 14.9% weight loss [#ev:ev_017:0-40]."
    atoms = extract_atoms(txt, "polaris")
    assert len(atoms) == 1
    refs = atoms[0].citation_refs
    assert refs[0].kind == "ev_span" and refs[0].resolved == "ev_017"
    assert refs[0].ev_start == 0 and refs[0].ev_end == 40
    assert "[#ev:" not in atoms[0].text                      # marker stripped


def test_extract_chatgpt_author_year():
    txt = "AI restructures labor markets through task reallocation (Acemoglu & Restrepo, 2018)."
    refs_map = {"Acemoglu & Restrepo, 2018": "https://nber.org/w24196"}
    atoms = extract_atoms(txt, "chatgpt", refs_map)
    assert len(atoms) == 1
    c = atoms[0].citation_refs[0]
    assert c.kind == "author_year" and c.resolved == "https://nber.org/w24196"
    assert "(Acemoglu" not in atoms[0].text


def test_extract_gemini_numbered_superscript():
    txt = "Generative AI accelerates occupational churn [12]."
    refs_map = {"12": "https://example.org/gemini-ref-12"}
    atoms = extract_atoms(txt, "gemini", refs_map)
    c = atoms[0].citation_refs[0]
    assert c.kind == "numbered" and c.resolved == "https://example.org/gemini-ref-12"


def test_extract_uncited_atom_kept():
    atoms = extract_atoms("This is an unsupported assertion with no citation.", "chatgpt")
    assert len(atoms) == 1
    assert atoms[0].citation_refs[0].kind == "uncited"
    assert atoms[0].is_cited is False


def test_extract_compound_sentence_atomizes():
    # default atomizer splits the obvious compound case on a semicolon
    txt = "Employment rose in exposed sectors; wages fell for routine tasks."
    atoms = extract_atoms(txt, "chatgpt")
    assert len(atoms) == 2
    # injected atomizer can split further
    def fake_atomizer(s):
        return [p.strip() for p in s.replace(";", " AND ").split(" AND ") if p.strip()]
    atoms2 = extract_atoms(txt, "chatgpt", atomizer=fake_atomizer)
    assert len(atoms2) == 2


# ── fact_scorer: evidence-locked judge + fail-closed substring validation ────
def _atom(text, refs):
    from src.polaris_graph.benchmark.report_claim_extractor import ExtractedAtom
    return ExtractedAtom(atom_id="s:0:0", text=text, citation_refs=refs)


def _ev_ref(ev_id="ev_1"):
    return CitationRef(system="polaris", kind="ev_span", raw_key=f"[#ev:{ev_id}:0-10]",
                       resolved=ev_id, ev_start=0, ev_end=10)


def test_fact_verified_requires_real_substring_quote():
    atom = _atom("The drug cut events by 20%.", [_ev_ref()])
    span = "In the trial the drug cut cardiovascular events by 20% versus placebo."

    def fetcher(ref):
        return SpanResult(text=span)

    def good_judge(text, span_text, ref):
        return JudgeVerdict(verdict="VERIFIED", severity="S1",
                            span_quote="cut cardiovascular events by 20%")
    rows = score_atoms([atom], span_fetcher=fetcher, judge=good_judge)
    assert rows[0].verdict == "VERIFIED" and rows[0].span_quote in span


def test_fact_fabricated_quote_fails_closed_to_unsupported():
    atom = _atom("The drug cut events by 90%.", [_ev_ref()])
    span = "The drug cut events by 20% versus placebo."

    def fetcher(ref):
        return SpanResult(text=span)

    def lying_judge(text, span_text, ref):
        # claims VERIFIED but the quote is NOT in the fetched span
        return JudgeVerdict(verdict="VERIFIED", severity="S0",
                            span_quote="cut events by 90%")
    rows = score_atoms([atom], span_fetcher=fetcher, judge=lying_judge)
    assert rows[0].verdict == "UNSUPPORTED"                  # fail-closed
    assert "not found in fetched source" in (rows[0].audit_note or "")


def test_fact_uncited_material_is_unsupported_null_with_audit_severity():
    atom = _atom("Bold uncited claim.", [CitationRef(system="chatgpt", kind="uncited", raw_key="")])

    def fetcher(ref):  # never called for uncited
        raise AssertionError("fetcher must not be called for uncited atoms")

    def judge(text, span_text, ref):
        assert span_text is None and ref is None
        return JudgeVerdict(verdict="UNSUPPORTED", severity="S1")
    rows = score_atoms([atom], span_fetcher=fetcher, judge=judge)
    assert rows[0].verdict == "UNSUPPORTED" and rows[0].citation_id is None
    assert rows[0].severity == "S1"


def test_fact_unresolved_citation_is_unreachable_source_missing():
    # author-year citation that resolves to NO source
    ref = CitationRef(system="gemini", kind="author_year", raw_key="(Doe, 2099)", resolved=None)
    atom = _atom("Claim with an unresolvable citation.", [ref])

    def fetcher(r):
        raise AssertionError("fetcher must not run on an unresolved citation")

    def judge(text, span_text, r):
        return JudgeVerdict(verdict="UNSUPPORTED", severity="S2")
    rows = score_atoms([atom], span_fetcher=fetcher, judge=judge)
    assert rows[0].verdict == "UNREACHABLE"
    assert rows[0].unreachable_subtype == "source_missing"


def test_fact_metadata_only_is_unreachable_not_verified():
    ref = CitationRef(system="chatgpt", kind="author_year", raw_key="(Smith, 2020)",
                      resolved="https://paywalled.example/abs")
    atom = _atom("Claim citing a paywalled abstract.", [ref])

    def fetcher(r):
        return SpanResult(text=None, unreachable_subtype="metadata_only")

    def judge(text, span_text, r):
        return JudgeVerdict(verdict="VERIFIED", severity="S1")  # must NOT win
    rows = score_atoms([atom], span_fetcher=fetcher, judge=judge)
    assert rows[0].verdict == "UNREACHABLE"
    assert rows[0].unreachable_subtype == "metadata_only"


def test_fact_unreachable_stays_in_denominator():
    # one VERIFIED + one UNREACHABLE -> material denominator counts BOTH
    from src.polaris_graph.benchmark.claim_audit_scorer import lane1_faithfulness
    rows = [
        ClaimRow("a", "S1", "VERIFIED", "ev_1", "x"),
        ClaimRow("b", "S1", "UNREACHABLE", "ev_2", None, unreachable_subtype="source_missing"),
    ]
    l1 = lane1_faithfulness(rows)
    assert l1["material_atoms"] == 2
    assert l1["unsupported_or_worse_rate"] == 0.5            # UNREACHABLE counts against


# ── scorecard: lane2_pending (no false fail) + clinical-3 / overall-5 ─────────
def test_scorecard_lane2_pending_no_false_fail():
    rows = [ClaimRow("a", "S1", "VERIFIED", "ev_1", "x")]
    res = score_system_question(rows, rubric=None)
    assert res["lane2_pending"] is True and res["pass"] is None
    assert res["lane1"]["material_atoms"] == 1


def test_scorecard_clinical_and_overall_split():
    def clean(qid):
        return [ClaimRow(f"{qid}:0", "S1", "VERIFIED", "ev_1", "x")]
    def bad(qid):
        return [ClaimRow(f"{qid}:0", "S1", "FABRICATED", "ev_1", "refuting span")]
    rows_by_sys_qid = {
        ("polaris", "Q75"): clean("75"), ("polaris", "Q76"): clean("76"),
        ("polaris", "Q78"): clean("78"), ("polaris", "Q72"): clean("72"),
        ("polaris", "Q90"): clean("90"),
        ("chatgpt", "Q75"): bad("75"), ("chatgpt", "Q76"): clean("76"),
        ("chatgpt", "Q78"): clean("78"), ("chatgpt", "Q72"): clean("72"),
        ("chatgpt", "Q90"): clean("90"),
    }
    card = build_scorecard(rows_by_sys_qid)
    assert card["lane2_pending"] is True
    assert card["systems"]["polaris"]["overall_5"]["n_questions"] == 5
    assert card["systems"]["polaris"]["clinical_3"]["n_questions"] == 3
    assert card["systems"]["polaris"]["overall_5"]["hard_fail_count"] == 0
    # chatgpt has 1 FABRICATED in a clinical question -> clinical hard-fail surfaces
    assert card["systems"]["chatgpt"]["clinical_3"]["hard_fail_count"] == 1
    assert card["systems"]["chatgpt"]["source_critical_2"]["hard_fail_count"] == 0


def test_normalize_qid():
    assert normalize_qid("Q75") == "75"
    assert normalize_qid("DRB-EN#90") == "90"
    assert normalize_qid("72") == "72"


# ── run-wiring orchestrator (cash-free, injected fakes) ──────────────────────
def test_parse_references_numbered_and_author_year():
    from scripts.dr_benchmark.run_scorecard import parse_references
    report = (
        "Body text.\n\n## References\n\n"
        "1. Acemoglu, 2018. Title. https://nber.org/w24196\n"
        "[12] Autor, 2015. Other. https://example.org/autor2015\n"
    )
    refs = parse_references(report)
    assert refs["1"] == "https://nber.org/w24196"
    assert refs["12"] == "https://example.org/autor2015"
    assert refs.get("acemoglu, 2018") == "https://nber.org/w24196"


def test_gemini_unicode_superscript_citation():
    # Codex diff-gate P2-2: unicode superscripts resolve to numbered citations.
    txt = "Generative AI accelerates occupational churn²⁷."
    atoms = extract_atoms(txt, "gemini", {"27": "https://example.org/ref27"})
    kinds = {(c.kind, c.resolved) for c in atoms[0].citation_refs}
    assert ("numbered", "https://example.org/ref27") in kinds
    assert "²⁷" not in atoms[0].text                       # superscript stripped


def test_split_body_keeps_prose_after_nonterminal_header(tmp_path):
    # Codex diff-gate P1: a "## Sources" header followed by ANSWER PROSE must NOT be
    # stripped — those claims must stay in the denominator.
    from scripts.dr_benchmark.run_scorecard import split_body_and_references
    report = (
        "## Sources of evidence\n\n"
        "The strongest causal study finds a 12% local employment decline. "
        "A second cohort shows wage compression in routine tasks.\n"
    )
    body, refs = split_body_and_references(report)
    assert "12% local employment decline" in body          # prose NOT excluded
    assert refs == ""


def test_split_body_strips_terminal_reference_list():
    from scripts.dr_benchmark.run_scorecard import split_body_and_references
    report = (
        "Main finding: the drug cut events by 20%.\n\n"
        "References\n\n"
        "1. Smith J. 2020. https://example.org/smith\n"
        "2. Doe A. 2019. https://example.org/doe\n"
    )
    body, refs = split_body_and_references(report)
    assert "cut events by 20%" in body
    assert "Smith" not in body and "Smith" in refs          # terminal list stripped


def test_split_body_keeps_numbered_prose_under_references_header():
    # Codex diff-gate iter2 P1: numbered PROSE claims under a "References" header
    # must NOT be stripped (they are claims, not citations).
    from scripts.dr_benchmark.run_scorecard import split_body_and_references
    report = (
        "Summary paragraph.\n\n"
        "References\n\n"
        "1. The drug reduced cardiovascular events by 20% in the 2020 cohort.\n"
        "2. A second study confirmed wage compression in 2019.\n"
    )
    body, refs = split_body_and_references(report)
    assert "reduced cardiovascular events by 20%" in body   # prose NOT excluded
    assert refs == ""


def test_split_body_sources_header_not_a_strip_trigger():
    from scripts.dr_benchmark.run_scorecard import split_body_and_references
    report = (
        "Body.\n\n## Sources\n\n"
        "Smith J. 2020. https://example.org/smith\n"   # looks reference-like...
    )
    # "Sources" is NOT a strong strip header -> not stripped (fail-safe inclusion).
    body, refs = split_body_and_references(report)
    assert "Smith J. 2020" in body and refs == ""


def test_run_scorecard_end_to_end_cash_free(tmp_path):
    from scripts.dr_benchmark.run_scorecard import run_scorecard
    ext = tmp_path / "external_outputs"
    (ext / "gpt_5_5_pro").mkdir(parents=True)
    (ext / "gemini_3_1_pro").mkdir(parents=True)
    (ext / "gpt_5_5_pro" / "Q75_metal.md").write_text(
        "Metal ions reduce CVD risk by 10% (Smith, 2020).\n\n"
        "## References\n\n1. Smith, 2020. https://example.org/smith\n",
        encoding="utf-8",
    )
    (ext / "gemini_3_1_pro" / "Q75_metal.md").write_text(
        "An uncited claim about metal ions and the heart.\n",
        encoding="utf-8",
    )

    def fetcher(ref):
        from src.polaris_graph.benchmark.fact_scorer import SpanResult
        return SpanResult(text="Metal ions reduce CVD risk by 10% in the cohort.")

    def judge(text, span_text, ref):
        from src.polaris_graph.benchmark.fact_scorer import JudgeVerdict
        if span_text is None:
            return JudgeVerdict(verdict="UNSUPPORTED", severity="S1")
        return JudgeVerdict(verdict="VERIFIED", severity="S1",
                            span_quote="Metal ions reduce CVD risk by 10%")

    card = run_scorecard(
        polaris_run_dir=None, external_root=ext,
        span_fetcher=fetcher, judge=judge,
    )
    assert card["lane2_pending"] is True
    assert "chatgpt" in card["systems"] and "gemini" in card["systems"]
    # chatgpt Q75 claim VERIFIED (0 hard fails); gemini Q75 uncited -> UNSUPPORTED hard fail
    assert card["systems"]["chatgpt"]["clinical_3"]["hard_fail_count"] == 0
    assert card["systems"]["gemini"]["clinical_3"]["hard_fail_count"] == 1
