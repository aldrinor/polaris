"""I-arch-008 (#1265) FIX K — verified-span render for the enrichment section.

Locks the behavior the §-1.4 behavioral harness surfaced:
  * per-sentence-unit ``[ev_id]`` tagging (a single trailing marker silently
    collapses to ~0 — the 590->0 symptom);
  * a boilerplate/junk screen (strict_verify's content checks are idle on a
    self-quote, so fetch-shell spans must be screened on input);
  * default-OFF flag => byte-identical (empty draft, never called);
  * the draft survives the UNCHANGED _rewrite_draft_with_spans -> strict_verify
    path (entailment off = deterministic floor) and cites the source.

Faithfulness is NEVER relaxed here: K only surfaces a source's OWN verbatim span
for the unchanged gate to validate.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import weighted_enrichment as we


class _Plan:
    def __init__(self, title: str) -> None:
        self.title = title


def test_flag_default_off_and_truthy_values(monkeypatch):
    monkeypatch.delenv(we._ENV_RENDER_VERIFIED_SPANS, raising=False)
    assert we.render_verified_spans_enabled() is False
    for val in ("1", "true", "on", "yes", "enabled", "TRUE"):
        monkeypatch.setenv(we._ENV_RENDER_VERIFIED_SPANS, val)
        assert we.render_verified_spans_enabled() is True
    for val in ("0", "off", "no", ""):
        monkeypatch.setenv(we._ENV_RENDER_VERIFIED_SPANS, val)
        assert we.render_verified_spans_enabled() is False


def test_is_enrichment_section_matches_only_the_title():
    assert we.is_enrichment_section(_Plan(we._ENRICHMENT_TITLE)) is True
    assert we.is_enrichment_section(_Plan("Efficacy")) is False
    assert we.is_enrichment_section(None) is False


def test_spans_per_source_default_override_and_fail_loud(monkeypatch):
    monkeypatch.delenv(we._ENV_SPANS_PER_SOURCE, raising=False)
    assert we.spans_per_source() == we._DEFAULT_SPANS_PER_SOURCE
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "5")
    assert we.spans_per_source() == 5
    # floored at 1 — a 0/negative can never silently zero the render
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "0")
    assert we.spans_per_source() == 1
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "-3")
    assert we.spans_per_source() == 1
    # fail loud on garbage (LAW II — no silent fallback)
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "lots")
    with pytest.raises(ValueError):
        we.spans_per_source()


def test_draft_tags_every_sentence_unit_not_just_the_last(monkeypatch):
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "9")  # don't budget-clip the test
    quote = (
        "Magnesium supplementation reduced systolic blood pressure by 2.0 mmHg. "
        "Diastolic blood pressure fell by 1.8 mmHg in the pooled analysis. "
        "The effect was consistent across 34 randomized trials."
    )
    pool = {"mag_meta": {"direct_quote": quote}}
    draft = we.build_verified_span_draft(["mag_meta"], pool)
    # EVERY unit carries its own [ev_id] marker (the per-unit tagging rule).
    assert draft.count("[mag_meta]") == 3, draft
    # The naive-collapse anti-pattern (one trailing marker) is NOT what we emit.
    assert not draft.strip().endswith(quote.strip() + " [mag_meta]")


def test_budget_limits_units_per_source_but_not_sources(monkeypatch):
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "1")
    quote = (
        "First substantive finding about the intervention and its measured effect. "
        "Second substantive finding about a different measured outcome entirely. "
        "Third substantive finding describing the safety profile across the cohort."
    )
    pool = {
        "src_a": {"direct_quote": quote},
        "src_b": {"direct_quote": quote},
    }
    draft = we.build_verified_span_draft(["src_a", "src_b"], pool)
    # budget=1 unit per source, but BOTH sources are present (breadth uncapped).
    assert draft.count("[src_a]") == 1
    assert draft.count("[src_b]") == 1


def test_junk_quote_and_pool_absent_contribute_nothing():
    pool = {
        "junk": {"direct_quote": "Enable basic functions like page navigation."},
        "empty": {"direct_quote": ""},
        "good": {
            "direct_quote": "Disodium EDTA chelation reduced cardiovascular events "
            "with a hazard ratio of 0.82 in the randomized trial."
        },
    }
    # offer junk, an absent id, and one good source
    draft = we.build_verified_span_draft(["junk", "empty", "absent_id", "good"], pool)
    assert "[good]" in draft
    assert "[junk]" not in draft
    assert "[empty]" not in draft
    assert "[absent_id]" not in draft


def test_draft_survives_real_rewrite_and_strict_verify(monkeypatch):
    """End-to-end deterministic floor: draft -> rewrite -> strict_verify cites the source."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # deterministic floor, no LLM
    monkeypatch.setenv(we._ENV_SPANS_PER_SOURCE, "3")
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )
    from src.polaris_graph.generator.provenance_generator import (
        parse_provenance_tokens,
        strict_verify,
    )

    quote = (
        "Disodium EDTA chelation therapy reduced the primary cardiovascular endpoint "
        "with a hazard ratio of 0.82 in the randomized controlled trial."
    )
    pool = {"tact": {"direct_quote": quote}}
    draft = we.build_verified_span_draft(["tact"], pool)
    assert draft  # non-empty
    rewritten, converted, _unver = _rewrite_draft_with_spans(draft, pool)
    assert converted >= 1  # at least one [ev_id] bound to a real [#ev:...] span
    report = strict_verify(rewritten, pool)
    assert report.total_kept >= 1, "K draft produced no verified sentence"
    cited = set()
    for sv in report.kept_sentences:
        for tok in (getattr(sv, "tokens", None)
                    or parse_provenance_tokens(getattr(sv, "sentence", "") or "")):
            cited.add(getattr(tok, "evidence_id", None))
    assert "tact" in cited
