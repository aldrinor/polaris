"""Pure question decomposition for the live retrieval path (I-meta-002-q1d #951 q1d-a).

NO network, NO LLM — pure string ops. Tests the Codex brief-gate iter-1 contract: conservative
splitting (no bare commas; conjunction/`versus` splits require >=4 content words each side, which
protects compounds by construction), dedup, cap, determinism, and the pure list-builder helper.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.query_decomposer import (
    build_amplified_query_list,
    decompose_question,
)

# A golden-style ~50-word multi-clause clinical question (5 distinct sub-topics), structurally like
# the benchmark questions (not the sealed gold rubric — the question shape only).
_MULTI = (
    "What is the role of probiotic supplementation in colorectal cancer prevention; "
    "how do prebiotics alter the gut microbiota composition; "
    "which pathogenic bacteria are implicated in tumorigenesis; "
    "what toxic microbial metabolites drive carcinogenesis; "
    "and how do dietary fiber choices modulate the colonic microbiome?"
)


def test_multiclause_question_yields_multiple_subqueries():
    out = decompose_question(_MULTI)
    assert len(out) >= 4, out
    blob = " ".join(out).lower()
    # Each distinct sub-topic survives as its own focused query.
    assert "probiotic" in blob and "prebiotic" in blob
    assert "pathogenic bacteria" in blob
    assert "toxic" in blob or "metabolite" in blob
    assert "dietary fiber" in blob or "colonic" in blob


def test_safety_and_efficacy_compound_not_split():
    # "safety and efficacy" — each side has < 4 content words → conjunction split is NOT taken.
    out = decompose_question(
        "Evaluate the safety and efficacy of tirzepatide in adults with type 2 diabetes."
    )
    # Single-clause after the guard → falls back to [] (caller seeds the full question anyway).
    assert out == []


def test_type_2_diabetes_and_compounds_preserved():
    out = decompose_question(
        "Assess cardiovascular outcomes in non-small cell lung cancer; "
        "and review renal safety in chronic kidney disease patients on metformin therapy."
    )
    blob = " ".join(out).lower()
    assert "non-small cell lung cancer" in blob
    assert "chronic kidney disease" in blob


def test_safety_and_efficacy_protected_in_long_clause():
    # Codex diff-gate iter-1 P1: even when BOTH sides around `and` have >=4 content words, a protected
    # clinical compound ("safety and efficacy") is a single concept and must NOT be split.
    out = decompose_question(
        "Assess long-term cardiovascular safety and efficacy clinical endpoints in adults "
        "with type 2 diabetes; and review hepatic adverse events in cirrhotic patients on therapy."
    )
    blob = " ".join(out).lower()
    assert "safety and efficacy" in blob, out
    # The semicolon boundary still produces two sub-queries.
    assert len(out) == 2, out


def test_vs_dot_comparator_not_split_by_terminator():
    # Codex diff-gate iter-1 P1: "vs." must NOT be split at its period before the >=4 connective guard.
    short = decompose_question("Compare tirzepatide vs. semaglutide for weight loss.")
    assert short == [], short
    # Long "vs." comparator: both sides query-like → connective split allowed (handled as "vs").
    long = decompose_question(
        "Long-term cardiovascular mortality reduction with intensive statin therapy "
        "vs. moderate-intensity statin therapy in elderly diabetic patients."
    )
    assert len(long) == 2, long


def test_abbreviation_periods_not_treated_as_terminators():
    # "e.g." / "i.e." internal periods must not shred a clause into fragments.
    out = decompose_question(
        "Evaluate glycemic agents (e.g. metformin, sulfonylureas) for renal safety in elderly adults; "
        "and assess hepatic clearance pathways in patients with cirrhosis and portal hypertension."
    )
    blob = " ".join(out).lower()
    assert "e.g." in blob  # abbreviation restored intact
    assert len(out) == 2, out


def test_capitalized_abbreviations_protected():
    # Codex diff-gate iter-2 P1: case-insensitive abbreviation masking (E.g./Fig./No. at clause start).
    out = decompose_question(
        "E.g. metformin and sulfonylureas affect renal clearance in elderly diabetic patients; "
        "Fig. 2 shows hepatic enzyme elevation in cirrhotic patients on long-term statin therapy."
    )
    blob = " ".join(out)
    assert "E.g." in blob and "Fig." in blob, out  # capitalized abbreviations restored intact
    # No fragment shred from the abbreviation periods.
    assert not any(s.lower().endswith(("e.g", "(e.g", "fig")) for s in out), out


def test_long_safety_versus_efficacy_comparator_is_split():
    # Codex diff-gate iter-2 P2: the protected-pair guard applies to ADDITIVE connectives only —
    # a long "safety versus efficacy" COMPARATOR with both sides >=4 content words IS a valid split.
    out = decompose_question(
        "Long-term cardiovascular safety outcomes in elderly diabetic patients "
        "versus efficacy endpoints measured across the pivotal phase 3 trial program."
    )
    assert len(out) == 2, out


def test_versus_split_requires_four_content_words_each_side():
    # Compact comparator: "drug A versus drug B" — sides too short → NOT split.
    short = decompose_question("Compare tirzepatide versus semaglutide.")
    assert short == []
    # Long comparator: both sides query-like (>=4 content words) → split allowed.
    long = decompose_question(
        "Long-term cardiovascular mortality reduction with intensive statin therapy "
        "versus moderate-intensity statin therapy in elderly diabetic patients."
    )
    assert len(long) == 2, long


def test_no_bare_comma_split():
    # Bare commas must NOT create sub-queries (would shred a single clause into noise).
    out = decompose_question(
        "Describe the pharmacokinetics, pharmacodynamics, and metabolism of the drug."
    )
    # One clause (commas ignored; "and metabolism of the drug" side < 4 content words) → [].
    assert out == []


def test_short_single_clause_returns_empty():
    assert decompose_question("What is the efficacy of aspirin?") == []
    assert decompose_question("") == []
    assert decompose_question("   ") == []


def test_dedup_and_cap_and_determinism():
    q = (
        "How does exercise improve glycemic control in diabetes; "
        "how does exercise improve glycemic control in diabetes; "
        "what is the effect of diet on insulin sensitivity in obese adults; "
        "what is the role of sleep duration on metabolic health outcomes; "
        "how does stress influence cortisol and blood glucose regulation; "
        "what is the impact of smoking cessation on cardiovascular risk reduction?"
    )
    out = decompose_question(q, max_subqueries=3)
    assert len(out) == 3  # cap respected
    assert len(out) == len({s.lower() for s in out})  # dedup (the duplicate clause collapsed)
    assert decompose_question(q, max_subqueries=3) == out  # determinism


# --- build_amplified_query_list: prepend order + dedup + anchor never added -------------------
def test_build_amplified_list_order_and_dedup():
    out = build_amplified_query_list(
        hand_authored=["hand one", "shared"],
        decomposed=["decomp one", "shared"],  # "shared" duplicates hand_authored → dropped
        regulatory=["reg one"],
        trial=["trial one"],
    )
    assert out == ["hand one", "shared", "decomp one", "reg one", "trial one"]


def test_build_amplified_list_case_insensitive_dedup_and_blank_filter():
    out = build_amplified_query_list(
        hand_authored=["Tirzepatide HbA1c"],
        decomposed=["tirzepatide hba1c", "  ", ""],  # case-dup + blanks dropped
        regulatory=[],
        trial=["trial"],
    )
    assert out == ["Tirzepatide HbA1c", "trial"]
