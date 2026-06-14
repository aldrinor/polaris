"""A3 fix F13 (GH I-arch-002) — scope-gate off-list-drug false-abort fix.

The scope gate previously recognised a clinical *intervention* ONLY via the
~25-entry hard-coded `_DRUG_NAME_RE` allowlist. A clinical question about any
drug NOT in that list, whose population also could not be extracted, read BOTH
PICO anchors as None and was hard-rejected (scope_decision=reject,
clinical_pico_unscoped) — a FALSE abort on a perfectly well-scoped question.

F13 replaces the closed allowlist (for the scope-gate decision) with a
config-driven recognizer (`config/clinical_safety/intervention_recognition.yaml`)
combining WHO/USAN INN class stems (generative drug recognition) + a seed list
of stemless legacy names. LAW VI: no hard-coded per-drug allowlist gates the
decision.

These tests PROVE the fix in BOTH directions:
  - ACCEPT: an off-list drug question scopes THROUGH (no abort), even with no
    extractable population — the intervention anchor now lands.
  - REJECT: a genuinely out-of-scope / contentless clinical question STILL
    aborts (clinical_pico_unscoped), including precision collisions where a
    common English word merely ends in a stem-looking substring.

No faithfulness gate (strict_verify / NLI / 4-role / provenance / span-grounding)
is touched. This is a scope-recognition fix only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.nodes.scope_gate import (
    _build_intervention_recognizer,
    _intervention_present,
    _reset_intervention_cache,
    extract_pico_heuristic,
    run_scope_gate,
)


# Off-list drugs: NONE of these are in `_DRUG_NAME_RE` (verified by the
# canonical-fast-path assertion below). They are recognised purely by the
# config-driven INN-stem / known-name layer.
_OFFLIST_STEM_DRUGS = (
    ("rosuvastatin", "What is the efficacy of rosuvastatin for cholesterol?"),
    ("apixaban", "Does apixaban prevent stroke?"),
    ("alectinib", "alectinib in ALK-positive lung cancer outcomes"),
    ("sildenafil", "What is the efficacy of sildenafil?"),
    ("lisinopril", "How effective is lisinopril for blood pressure control?"),
    ("fluoxetine", "What are the outcomes of fluoxetine treatment?"),
    ("amlodipine", "Is amlodipine effective for hypertension?"),
    ("doxycycline", "Efficacy of doxycycline for infection."),
)

# Stemless legacy drugs seeded in known_names. These carry no INN class stem.
_OFFLIST_KNOWN_NAMES = (
    ("warfarin", "What is the bleeding risk of warfarin?"),
    ("aspirin", "Is aspirin effective for primary prevention?"),
    ("digoxin", "What are the safety outcomes of digoxin?"),
    ("methotrexate", "Efficacy of methotrexate in rheumatoid arthritis."),
)


def test_offlist_drug_is_in_neither_canonical_regex() -> None:
    """Guard: the off-list drugs genuinely are NOT in `_DRUG_NAME_RE`.

    Proves the fix exercises the NEW config layer, not the old allowlist.
    """
    from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE

    for name, _ in (*_OFFLIST_STEM_DRUGS, *_OFFLIST_KNOWN_NAMES):
        assert _DRUG_NAME_RE.search(name) is None, (
            f"{name!r} should be OFF the canonical _DRUG_NAME_RE allowlist; "
            f"if it is on-list, pick a different off-list drug for this test"
        )


@pytest.mark.parametrize("expected,query", _OFFLIST_STEM_DRUGS)
def test_inn_stem_drug_is_recognised(expected: str, query: str) -> None:
    """An off-list INN-stem drug is recognised as the intervention anchor."""
    assert _intervention_present(query) == expected
    pico = extract_pico_heuristic(query)
    assert pico["intervention"] == expected


@pytest.mark.parametrize("expected,query", _OFFLIST_KNOWN_NAMES)
def test_known_legacy_name_is_recognised(expected: str, query: str) -> None:
    """A stemless legacy drug (seed known_names) is recognised."""
    assert _intervention_present(query) == expected
    pico = extract_pico_heuristic(query)
    assert pico["intervention"] == expected


@pytest.mark.parametrize("_expected,query", _OFFLIST_STEM_DRUGS)
def test_offlist_drug_scopes_through_without_abort(
    _expected: str, query: str, tmp_path: Path
) -> None:
    """ACCEPT: an off-list drug clinical question scopes THROUGH (no abort).

    The questions carry NO population marker, so under the OLD allowlist both
    PICO anchors were None and the gate hard-rejected. With F13 the intervention
    anchor lands, so the decision is proceed OR review (one anchor still missing)
    — NEVER reject. scope_rejected must be False and the rejection code None.
    """
    result = run_scope_gate(
        research_question=query,
        run_dir=tmp_path / "offlist",
        run_id="TEST_F13_OFFLIST",
        domain="clinical",
    )
    assert result.protocol.scope_rejected is False, (
        f"off-list drug question {query!r} must NOT abort_scope_rejected"
    )
    assert result.protocol.scope_rejection_code is None
    assert result.protocol.scope_decision in {"proceed", "review"}
    assert result.protocol.intervention is not None


def test_offlist_drug_with_population_proceeds(tmp_path: Path) -> None:
    """ACCEPT: off-list drug + population marker → full proceed (both anchors)."""
    result = run_scope_gate(
        research_question=(
            "What is the efficacy of rosuvastatin for cardiovascular risk in "
            "adults with hyperlipidemia?"
        ),
        run_dir=tmp_path / "offlist_pop",
        run_id="TEST_F13_OFFLIST_POP",
        domain="clinical",
    )
    assert result.protocol.scope_decision == "proceed"
    assert result.protocol.scope_rejected is False
    assert result.protocol.population is not None
    assert result.protocol.intervention == "rosuvastatin"


# ─────────────────────────────────────────────────────────────────────────────
# DISCRIMINATORS — the gate MUST stay strict. These prove F13 did not just
# disable the gate. Each must keep rejecting with clinical_pico_unscoped.
# ─────────────────────────────────────────────────────────────────────────────

_PRECISION_COLLISION_QUERIES = (
    # common English word that merely ENDS in a stem-looking substring
    "Is April or May a better month to start a new therapy?",   # April !~ -pril
    "A walk in the pine forest may improve patient mood.",      # pine  !~ -dipine
    "How does caffeine affect sleep quality?",                  # caffeine !~ -ine
    "What is the best espresso machine for a clinic break room?",  # machine !~ -ine
    "Does the routine of a daily regimen matter?",              # routine !~ -ine
)


@pytest.mark.parametrize("query", _PRECISION_COLLISION_QUERIES)
def test_precision_collision_word_is_not_an_intervention(query: str) -> None:
    """A common English word ending in a stem-looking substring is NOT a drug."""
    assert _intervention_present(query) is None


@pytest.mark.parametrize("query", _PRECISION_COLLISION_QUERIES)
def test_precision_collision_clinical_question_still_rejects(
    query: str, tmp_path: Path
) -> None:
    """REJECT: a clinical-domain question whose only stem-looking token is an
    English collision, and which has no population marker, STILL aborts."""
    result = run_scope_gate(
        research_question=query,
        run_dir=tmp_path / "collision",
        run_id="TEST_F13_COLLISION",
        domain="clinical",
    )
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejected is True
    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"


# The `-cept` fusion-protein stem collides with these common English words.
# `exclude_words` in the config must filter them (Codex diff-gate iter-1 P1).
# NOTE: these carry NO population marker, so with intervention=None they must
# REJECT (both PICO anchors missing), not merely flag-for-review.
_CEPT_COLLISION_WORDS = (
    "I accept the proposed treatment.",
    "except in the most severe cases",
    "the concept of patient safety",
    "intercept the metabolic pathway",
    "this dose is acceptable",
    "an exception was documented",
    "contraception counseling guidance",
)

# Real `-cept` fusion-protein drugs that MUST still be recognised.
_CEPT_REAL_DRUGS = (
    ("etanercept", "etanercept for rheumatoid arthritis"),
    ("abatacept", "Is abatacept effective in RA?"),
    ("aflibercept", "aflibercept for macular degeneration"),
    ("rilonacept", "rilonacept for recurrent pericarditis"),
)


@pytest.mark.parametrize("query", _CEPT_COLLISION_WORDS)
def test_cept_english_collision_is_not_an_intervention(query: str) -> None:
    """accept/except/concept/intercept (and inflections) are NOT drugs."""
    assert _intervention_present(query) is None


@pytest.mark.parametrize("expected,query", _CEPT_REAL_DRUGS)
def test_real_cept_fusion_protein_is_recognised(expected: str, query: str) -> None:
    """Real `-cept` fusion-protein drugs are still recognised after the denylist."""
    assert _intervention_present(query) == expected


@pytest.mark.parametrize("query", _CEPT_COLLISION_WORDS)
def test_cept_collision_clinical_question_still_rejects(
    query: str, tmp_path: Path
) -> None:
    """REJECT: a clinical question whose only stem-looking token is a `-cept`
    English collision, with no population, STILL aborts (the denylist keeps the
    gate strict)."""
    result = run_scope_gate(
        research_question=query,
        run_dir=tmp_path / "cept",
        run_id="TEST_F13_CEPT",
        domain="clinical",
    )
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"


def test_exclude_words_optional_and_typed(tmp_path: Path) -> None:
    """`exclude_words` is optional (absent = no denylist) but must be a list."""
    # Absent exclude_words is valid — recognizer still compiles.
    ok = tmp_path / "ok.yaml"
    ok.write_text(
        "inn_stems:\n  stems: [mab]\nknown_names:\n  - warfarin\n",
        encoding="utf-8",
    )
    rec = _build_intervention_recognizer(ok)
    assert rec.find("pembrolizumab in NSCLC") == "pembrolizumab"
    assert rec.find("warfarin bleeding") == "warfarin"

    # Wrong-typed exclude_words fails loud.
    bad = tmp_path / "bad_exclude.yaml"
    bad.write_text(
        "inn_stems:\n  stems: [mab]\nknown_names:\n  - warfarin\n"
        "exclude_words: not-a-list\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="exclude_words"):
        _build_intervention_recognizer(bad)


def test_contentless_clinical_question_still_rejects(tmp_path: Path) -> None:
    """REJECT: the canonical contentless question keeps aborting (no regression
    of the strict gate — mirrors test_b100_scope_rejects_unscoped_clinical)."""
    result = run_scope_gate(
        research_question="Tell me about safety outcomes.",
        run_dir=tmp_path / "contentless",
        run_id="TEST_F13_CONTENTLESS",
        domain="clinical",
    )
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"


# ─────────────────────────────────────────────────────────────────────────────
# Config-loader fail-loud contract (LAW II — no silent fallback).
# ─────────────────────────────────────────────────────────────────────────────

def test_recognizer_config_is_loadable_and_fail_loud() -> None:
    """The shipped config compiles, and a missing/empty config fails loud."""
    # Real shipped config compiles.
    _reset_intervention_cache()
    rec = _intervention_present("rosuvastatin lowers LDL")
    assert rec == "rosuvastatin"

    # Missing file → RuntimeError (no silent fallback).
    with pytest.raises(RuntimeError, match="does not exist"):
        _build_intervention_recognizer(Path("/nonexistent/intervention.yaml"))


def test_recognizer_config_missing_stems_fails_loud(tmp_path: Path) -> None:
    """An otherwise-valid config with no stems fails loud, not silently empty."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "inn_stems:\n  stems: []\nknown_names:\n  - warfarin\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="stems"):
        _build_intervention_recognizer(bad)
