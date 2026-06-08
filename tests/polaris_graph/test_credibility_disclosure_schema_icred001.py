"""I-cred-001 (Phase 1) — per-claim disclosure schema: 4 inert, default-OFF fields on
SentenceVerification. No population, no render change in this phase. Proves backward-compat and that
the new fields are side-outputs only (never verdict inputs)."""

from __future__ import annotations

import dataclasses

from src.polaris_graph.generator.provenance_generator import (
    SentenceVerification,
    resolve_provenance_to_citations,
    verify_sentence_provenance,
)


def test_new_fields_have_safe_defaults():
    sv = SentenceVerification(sentence="x", tokens=[], is_verified=True)
    assert sv.span_verdict == ""
    assert sv.credibility_weight is None
    assert sv.independent_origin_count is None
    assert sv.certainty_label == ""


def test_backward_compat_existing_callers():
    # Old-style construction (existing fields only) still works — new fields default.
    sv = SentenceVerification(sentence="s", tokens=[], is_verified=False, failure_reasons=["r"])
    assert sv.is_verified is False
    assert sv.failure_reasons == ["r"]
    assert sv.span_verdict == "" and sv.credibility_weight is None


def test_new_fields_are_side_outputs_not_verdict_inputs():
    # Populating the disclosure fields does NOT change is_verified — they are never verdict inputs.
    bare = SentenceVerification(sentence="s", tokens=[], is_verified=True)
    populated = SentenceVerification(
        sentence="s", tokens=[], is_verified=True,
        span_verdict="SUPPORTS", credibility_weight=0.9,
        independent_origin_count=3, certainty_label="high",
    )
    assert bare.is_verified is True
    assert populated.is_verified is True


# ── Real verifier + render paths (Codex iter-1 P1): prove strict_verify is unchanged
#    and the render is byte-identical whether the disclosure fields are default or populated ──


def test_real_verifier_path_unchanged_and_new_fields_default(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    span = (
        "The randomized cohort study measured the adverse event rate at "
        "42.5 percent among the treated participants."
    )
    pool = {"e1": {"direct_quote": span}}
    sentence = f"The cohort study adverse event rate was 42.5 percent [#ev:e1:0-{len(span)}]."
    sv = verify_sentence_provenance(sentence, pool)
    # The real strict_verify path still verifies a genuinely-grounded number...
    assert sv.is_verified is True
    # ...and the disclosure fields are present + default (the verifier never sets them).
    assert sv.span_verdict == "" and sv.credibility_weight is None
    assert sv.independent_origin_count is None and sv.certainty_label == ""


def test_real_verifier_failure_path_unchanged(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    span = "The report discusses unrelated qualitative themes with no matching figure."
    pool = {"e1": {"direct_quote": span}}
    sentence = f"The measured rate was 88.8 percent [#ev:e1:0-{len(span)}]."
    sv = verify_sentence_provenance(sentence, pool)
    # An ungrounded number still FAILS (strict_verify behaviour is unchanged)...
    assert sv.is_verified is False
    # ...and the new fields are still default (not consulted on the failure path either).
    assert sv.span_verdict == "" and sv.credibility_weight is None


def test_render_byte_identical_with_default_vs_populated_disclosure_fields(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    span = (
        "The randomized cohort study measured the adverse event rate at "
        "42.5 percent among the treated participants."
    )
    pool = {"e1": {"source_url": "https://j.example/x", "tier": "T1",
                   "statement": span, "direct_quote": span}}
    sentence = f"The cohort study adverse event rate was 42.5 percent [#ev:e1:0-{len(span)}]."
    sv = verify_sentence_provenance(sentence, pool)
    assert sv.is_verified is True

    # The SAME verification with all four disclosure fields populated.
    sv_populated = dataclasses.replace(
        sv, span_verdict="SUPPORTS", credibility_weight=0.9,
        independent_origin_count=3, certainty_label="high",
    )
    text_default, biblio_default = resolve_provenance_to_citations([sv], pool)
    text_populated, biblio_populated = resolve_provenance_to_citations([sv_populated], pool)
    # The render reads sentence + tokens only; the disclosure fields are NOT rendered in
    # Phase 1 -> the rendered text AND the bibliography are byte-identical.
    assert text_default == text_populated
    assert biblio_default == biblio_populated
