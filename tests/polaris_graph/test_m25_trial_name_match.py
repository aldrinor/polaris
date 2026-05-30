"""M-25a tests: trial-name match in strict_verify.

Reproduces the FABRICATED #20 defect from DR audit pass 4:
  - Sentence: "SURMOUNT-1 ... tirzepatide 15 mg ... 20.9% at 72 weeks
    versus 3.1% placebo." [ev:ev_015]
  - ev_015 statement: "Tirzepatide after intensive lifestyle intervention
    in adults with overweight or obesity: the SURMOUNT-3 phase 3 trial"

The old strict_verify passed this sentence because:
  (a) content words {tirzepatide, surmount} overlap between sentence
      and evidence span, satisfying MIN_CONTENT_WORD_OVERLAP
  (b) the numeric check ran against the span text — if the span
      happened to contain 20.9 or 3.1 or 72 it would pass

The new guard rejects the binding: sentence names SURMOUNT-1 as an
atomic token, evidence title names SURMOUNT-3 atomically, and the
two do not match.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    extract_trial_names,
    verify_sentence_provenance,
)


class TestExtractTrialNames:
    """Unit tests for the trial-name extractor itself."""

    def test_extracts_surpass_n(self) -> None:
        assert extract_trial_names("SURPASS-1 reported HbA1c reduction") == {"SURPASS-1"}

    def test_extracts_surmount_n(self) -> None:
        assert extract_trial_names("SURMOUNT-4 at week 88 [data]") == {"SURMOUNT-4"}

    def test_extracts_multiple_trials(self) -> None:
        text = "SURPASS-1 and SURPASS-2 both showed efficacy, while SURMOUNT-3 focused on obesity."
        assert extract_trial_names(text) == {"SURPASS-1", "SURPASS-2", "SURMOUNT-3"}

    def test_extracts_named_acronyms(self) -> None:
        """SELECT, LEADER, SUSTAIN, PIONEER, STEP, REWIND, AWARD, GRADE are
        named trial programs. When named as ALLCAPS words in a sentence,
        treat them as trial tokens.
        """
        assert extract_trial_names("The SELECT trial showed CV benefit") == {"SELECT"}
        assert extract_trial_names("LEADER established CV safety") == {"LEADER"}
        assert extract_trial_names("STEP-1 trial with semaglutide") == {"STEP-1"}

    def test_no_false_positive_on_surmount_without_number(self) -> None:
        """A generic phrase 'SURMOUNT program' without a number should
        not be extracted as a specific trial token — it refers to the
        whole program, which doesn't require sub-trial matching."""
        # Per spec: SURMOUNT alone (no dash-number) is NOT a specific
        # trial ID and doesn't trigger the gate.
        result = extract_trial_names("Across the SURMOUNT program outcomes varied")
        # Should not contain a bare "SURMOUNT" token (because that would
        # incorrectly match SURMOUNT-1/2/3/4 evidence).
        assert "SURMOUNT" not in result

    def test_case_insensitive_matching(self) -> None:
        """Evidence titles often use mixed case (Surmount, SURMOUNT).
        Normalize to uppercase for comparison."""
        assert extract_trial_names("Surmount-3 is a phase 3 trial") == {"SURMOUNT-3"}
        assert extract_trial_names("surpass-1 randomized trial") == {"SURPASS-1"}

    def test_extracts_surmount_program_dash_variants(self) -> None:
        """SURMOUNT-CN, SURMOUNT-OSA are legitimate sub-trials."""
        assert "SURMOUNT-CN" in extract_trial_names("SURMOUNT-CN Chinese cohort")
        assert "SURMOUNT-OSA" in extract_trial_names("SURMOUNT-OSA sleep apnea trial")

    def test_empty_for_generic_prose(self) -> None:
        assert extract_trial_names("Tirzepatide is effective for weight loss") == set()


class TestTrialNameMismatchRejection:
    """Integration tests: strict_verify rejects a sentence whose named
    trial does not appear in the cited evidence.
    """

    def test_fabricated_surmount1_cited_to_surmount3_is_rejected(self) -> None:
        """The exact FABRICATED #20 defect from DR audit pass 4."""
        sentence = (
            "In SURMOUNT-1, tirzepatide 15 mg achieved >=20% body-weight "
            "reduction in 20.9% of participants at 72 weeks versus 3.1% "
            "with placebo. [#ev:ev_015:0-200]  # span within direct_quote length below"
        )
        # ev_015 is genuinely the SURMOUNT-3 paper — correct tier/label.
        # But the generator bound it to a SURMOUNT-1 sentence. Reject.
        pool = {
            "ev_015": {
                "direct_quote": (
                    "Tirzepatide after intensive lifestyle intervention in "
                    "adults with overweight or obesity: the SURMOUNT-3 phase "
                    "3 trial. The MTD of tirzepatide achieved weight reduction "
                    "of 20.9% at 72 weeks versus placebo."
                ),
                "statement": (
                    "Tirzepatide after intensive lifestyle intervention: the "
                    "SURMOUNT-3 phase 3 trial"
                ),
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert not result.is_verified
        assert any(
            "trial_name_mismatch" in r for r in result.failure_reasons
        ), f"expected trial_name_mismatch; got {result.failure_reasons}"

    def test_matching_trial_name_passes(self) -> None:
        """A SURMOUNT-3 sentence cited to a SURMOUNT-3 paper passes.

        Pass-7 hardening: trial-name gate uses statement/title ONLY
        (not direct_quote). Fixture must populate statement with the
        authoritative trial identity.
        """
        quote = (
            "Tirzepatide in SURMOUNT-3: MTD tirzepatide achieved 18.4% "
            "weight reduction at 72 weeks."
        )
        sentence = (
            f"In SURMOUNT-3, MTD tirzepatide achieved 18.4% weight reduction. "
            f"[#ev:ev_015:0-{len(quote)}]"
        )
        pool = {
            "ev_015": {
                "direct_quote": quote,
                "statement": "SURMOUNT-3 phase 3 obesity trial with lifestyle intervention",
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert result.is_verified, f"expected pass; failures={result.failure_reasons}"

    def test_sentence_without_trial_name_not_gated(self) -> None:
        """A generic sentence with no trial name is not subject to the
        trial-name gate (only numeric + content-overlap checks apply)."""
        sentence = (
            "Tirzepatide significantly reduced HbA1c compared to placebo. "
            "[#ev:ev_015:0-95]"
        )
        pool = {
            "ev_015": {
                "direct_quote": (
                    "Tirzepatide significantly reduced HbA1c compared to "
                    "placebo across doses in the SURMOUNT-3 trial."
                ),
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert result.is_verified, f"expected pass; failures={result.failure_reasons}"

    def test_mismatched_trial_in_multi_citation_one_matching_passes(self) -> None:
        """If the sentence names trial T and cites multiple evidence rows,
        at least one cited row must mention T for the sentence to pass."""
        sentence = (
            "SURPASS-2 demonstrated superior efficacy versus semaglutide. "
            "[#ev:ev_a:0-50][#ev:ev_b:0-50]"
        )
        pool = {
            "ev_a": {
                "direct_quote": (
                    "Some other trial context mentioning semaglutide and "
                    "tirzepatide comparison."
                ),
                "statement": "GLP-1/GIP co-agonist comparative review",
            },
            "ev_b": {
                "direct_quote": (
                    "SURPASS-2 was a phase 3 trial comparing tirzepatide "
                    "to semaglutide in people with T2D."
                ),
                "statement": "SURPASS-2 primary RCT: tirzepatide vs semaglutide",
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert result.is_verified, (
            f"expected pass (ev_b matches trial); failures={result.failure_reasons}"
        )

    def test_pass7_regression_direct_quote_mention_insufficient(self) -> None:
        """DR pass-7 regression: the SURMOUNT-3 Nature paper's
        direct_quote mentions SURMOUNT-1 as a prior reference. Pre-
        hardening, M-25a saw SURMOUNT-1 in evidence text and passed a
        fabricated 'In SURMOUNT-1, ...' sentence. Post-hardening, the
        gate uses only statement/title — so the SURMOUNT-3 paper
        correctly rejects a SURMOUNT-1 binding even though direct_quote
        mentions both."""
        # SURMOUNT-3 paper's direct_quote spans both trials (prior-ref
        # style), but its title/statement is only SURMOUNT-3.
        direct_quote = (
            "Prior work in SURMOUNT-1 established the weight-reduction "
            "efficacy of tirzepatide in obesity without diabetes. Here "
            "we present SURMOUNT-3, an intensive-lifestyle-intervention "
            "trial demonstrating MTD of tirzepatide produced a mean "
            "weight reduction of 18.4% at 72 weeks."
        )
        sentence = (
            f"In SURMOUNT-1, the MTD of tirzepatide led to a mean weight "
            f"reduction of 20.9% at 72 weeks versus 3.1% with placebo. "
            f"[#ev:ev_015:0-{len(direct_quote)}]"
        )
        pool = {
            "ev_015": {
                "direct_quote": direct_quote,
                "statement": (
                    "Tirzepatide after intensive lifestyle intervention: the "
                    "SURMOUNT-3 phase 3 trial"
                ),
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert not result.is_verified, (
            f"pass-7 hardening regressed: expected trial_name_mismatch "
            f"drop because statement is only SURMOUNT-3; got kept "
            f"(failures={result.failure_reasons})"
        )
        assert any(
            "trial_name_mismatch" in r for r in result.failure_reasons
        ), f"expected trial_name_mismatch; got {result.failure_reasons}"

    def test_mismatched_trial_in_multi_citation_none_matching_rejected(self) -> None:
        """If none of the cited rows mention the named trial, reject."""
        quote_a = (
            "SURPASS-1 was the first pivotal tirzepatide trial demonstrating "
            "sustained glycemic control vs placebo."
        )
        quote_b = (
            "SURPASS-2 compared tirzepatide to semaglutide and showed "
            "sustained glycemic control superiority."
        )
        sentence = (
            f"SURPASS-6 demonstrated sustained glycemic control in tirzepatide "
            f"patients. [#ev:ev_a:0-{len(quote_a)}][#ev:ev_b:0-{len(quote_b)}]"
        )
        pool = {
            "ev_a": {"direct_quote": quote_a},
            "ev_b": {"direct_quote": quote_b},
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert not result.is_verified
        assert any("trial_name_mismatch" in r for r in result.failure_reasons), (
            f"expected trial_name_mismatch; got {result.failure_reasons}"
        )


class TestTrialNameSpanFallback:
    """I-meta-002-q1d (#949): title-authority + CITED-SPAN fallback. The fallback rescues a correct
    sentence when the row's title names NO trial AND the CITED span names the trial — without re-opening
    FABRICATED-#20 (title authority) and without the one-reference laundering hole (span scope, not body)."""

    def test_span_fallback_rescues_surpass2_when_title_lacks_token(self) -> None:
        """RESCUE: a SURPASS-2 paper whose TITLE lacks the token and whose body INTRO references SURPASS-1
        and SURPASS-3 (≥2 trials in body), but whose CITED RESULTS span names SURPASS-2 → a SURPASS-2
        sentence PASSES. (A whole-body count heuristic would still drop this; cited-span is required.)"""
        intro = (
            "Building on SURPASS-1 and contrasting with SURPASS-3 obesity outcomes, this analysis "
        )
        results = (
            "reports that tirzepatide in SURPASS-2 produced a mean HbA1c reduction of 2.3 percent "
            "versus semaglutide at 40 weeks."
        )
        direct_quote = intro + results
        span_start = len(intro)
        span_end = len(direct_quote)
        sentence = (
            f"In SURPASS-2, tirzepatide produced a mean HbA1c reduction of 2.3 percent versus "
            f"semaglutide. [#ev:ev_s2:{span_start}-{span_end}]"
        )
        pool = {
            "ev_s2": {
                "direct_quote": direct_quote,
                # AUTHORITATIVE title names NO trial token (the real SURPASS-2 paper title shape).
                "statement": "Tirzepatide versus semaglutide once weekly in type 2 diabetes",
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert result.is_verified, (
            f"span fallback should rescue the SURPASS-2 sentence (title lacks token, cited span names "
            f"SURPASS-2); got failures={result.failure_reasons}"
        )

    def test_locked_fail_one_reference_outside_cited_span_rejected(self) -> None:
        """MANDATORY locked-FAIL #2 (the one-reference hole): title names NO trial; the body mentions
        SURMOUNT-1 ONCE as a prior reference in the INTRO; the CITED span is the SURMOUNT-3 result and does
        NOT contain SURMOUNT-1 → a fabricated SURMOUNT-1 sentence is REJECTED. Span scope (not body scope)
        is what closes this — a body mention outside the cited span never matches."""
        intro = "Prior work in SURMOUNT-1 motivated this study. "
        results = (
            "Here SURMOUNT-3 with intensive lifestyle intervention produced a mean weight reduction "
            "of 18.4 percent at 72 weeks."
        )
        direct_quote = intro + results
        # Cite ONLY the results span (starts after the SURMOUNT-1 intro mention).
        span_start = len(intro)
        span_end = len(direct_quote)
        sentence = (
            f"In SURMOUNT-1, tirzepatide produced a mean weight reduction of 18.4 percent at 72 weeks. "
            f"[#ev:ev_015:{span_start}-{span_end}]"
        )
        pool = {
            "ev_015": {
                "direct_quote": direct_quote,
                "statement": "Tirzepatide with intensive lifestyle intervention in obesity",  # NO trial token
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert not result.is_verified, (
            "one-reference hole: a SURMOUNT-1 reference OUTSIDE the cited span must NOT launder a "
            f"fabricated SURMOUNT-1 sentence; got kept (failures={result.failure_reasons})"
        )
        assert any("trial_name_mismatch" in r for r in result.failure_reasons), (
            f"expected trial_name_mismatch; got {result.failure_reasons}"
        )

    def test_kill_switch_off_restores_title_only_behavior(self, monkeypatch) -> None:
        """Kill-switch OFF → exact pass-7 title/statement-only behavior: the SURPASS-2 rescue case (title
        lacks the token) drops again, byte-identical to pre-#949."""
        monkeypatch.setenv("PG_VERIFY_TRIAL_NAME_SPAN_FALLBACK", "0")
        results = (
            "tirzepatide in SURPASS-2 produced a mean HbA1c reduction of 2.3 percent versus semaglutide."
        )
        sentence = (
            f"In SURPASS-2, tirzepatide produced a mean HbA1c reduction of 2.3 percent versus "
            f"semaglutide. [#ev:ev_s2:0-{len(results)}]"
        )
        pool = {
            "ev_s2": {
                "direct_quote": results,
                "statement": "Tirzepatide versus semaglutide once weekly in type 2 diabetes",  # no token
            },
        }
        result = verify_sentence_provenance(sentence, pool, require_number_match=True)
        assert not result.is_verified, (
            "with the span fallback OFF, a title-token-less SURPASS-2 row must drop the sentence "
            f"(exact pre-#949 behavior); got kept (failures={result.failure_reasons})"
        )
        assert any("trial_name_mismatch" in r for r in result.failure_reasons)
