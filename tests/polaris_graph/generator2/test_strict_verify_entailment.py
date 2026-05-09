"""Tests for strict_verify check (f) — entailment judge (I-bug-092).

The entailment judge is the 6th strict_verify check, gated by
PG_STRICT_VERIFY_ENTAILMENT. It runs an LLM-as-judge content check
on top of the existing 5 mechanical checks. The tests below pin the
audit-derived failure patterns (M2, C2, C1) plus a positive-control
paraphrase and the synthesis-with-tokens edge case, so the new gate
cannot regress on the architectural fix while leaving the off-mode
behavior identical to pre-I-bug-092.

The judge is monkeypatched with a deterministic fake — these tests
verify the GATE WIRING, not the production model's semantic accuracy
(that is verified at the integration layer with a live OpenRouter
call once the env is configured).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from polaris_graph.generator2 import strict_verify
from polaris_graph.generator2.strict_verify import (
    verify_sentence,
    verify_sentence_to_record,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Helpers ----------

def _src(
    source_id: str = "src-1",
    full_text: str | None = None,
    snippet: str = "snippet text",
) -> Source:
    return Source(
        url="https://www.urncst.org/article",
        domain="urncst.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=snippet,
        full_text=full_text,
        full_text_available=full_text is not None,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-entail",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


class _FakeJudge:
    """Deterministic judge driven by an explicit (sentence_substring -> verdict) map.

    Tests construct a FakeJudge with the expected verdicts pre-loaded, so we
    don't hit OpenRouter at all. The substring match keeps the table small
    while allowing one fixture to cover many sentences.
    """

    def __init__(self, verdicts: list[tuple[str, str]]) -> None:
        # list of (sentence_substring, verdict) — first match wins
        self._verdicts = verdicts
        self.calls: list[tuple[str, str]] = []  # (sentence, span) for assertions

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        for needle, verdict in self._verdicts:
            if needle in sentence:
                return verdict, f"fake: matched {needle!r}"
        return "ENTAILED", "fake: default"


def _install_fake_judge(
    monkeypatch: pytest.MonkeyPatch,
    verdicts: list[tuple[str, str]],
) -> _FakeJudge:
    fake = _FakeJudge(verdicts)
    # Reset singleton + install replacement so _get_judge() returns the fake.
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)
    return fake


# ---------- Off mode (default) — gate is invisible ----------

def test_off_mode_skips_judge_even_when_set_explicitly(monkeypatch):
    """PG_STRICT_VERIFY_ENTAILMENT='off' must not invoke the judge."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    # Install a judge that would mark every sentence NEUTRAL — if the
    # gate were running, the sentence would be dropped.
    fake = _install_fake_judge(monkeypatch, [("", "NEUTRAL")])
    full_text = "Adults with chronic pain showed clinical benefit from treatment."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults with chronic pain showed clinical benefit from treatment [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True, f"off-mode must not drop, got reason={reason}"
    assert fake.calls == [], "off-mode must not call the judge"


def test_unknown_mode_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "verbose-strict")
    fake = _install_fake_judge(monkeypatch, [("", "NEUTRAL")])
    full_text = "Adults with chronic pain showed clinical benefit from treatment."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, _ = verify_sentence(
        f"Adults with chronic pain showed clinical benefit from treatment [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is True
    assert fake.calls == []


# ---------- Warn mode — log but do not drop ----------

def test_warn_mode_does_not_drop_on_neutral(monkeypatch, caplog):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    _install_fake_judge(monkeypatch, [("β-cells", "NEUTRAL")])
    full_text = (
        "tirzepatide demonstrates synergistic actions on insulin secretion, "
        "glucagon suppression, appetite regulation, and adipocyte metabolism."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic β-cells and acts on adipocytes to influence lipid "
        f"metabolism and energy storage [#ev:src-1:0-{len(full_text)}]."
    )
    with caplog.at_level("WARNING"):
        passed, reason = verify_sentence(sentence, pool)
    # warn mode still returns pass because reason chain is unchanged
    assert passed is True
    assert reason is None
    # but a warning was logged
    assert any("entailment NEUTRAL" in rec.message for rec in caplog.records), (
        "warn mode must log on NEUTRAL verdict"
    )


# ---------- Enforce mode — M2 fabricated mechanistic granularity ----------

def test_enforce_mode_drops_m2_fabricated_granularity(monkeypatch):
    """M2 audit case: span says 'adipocyte metabolism', sentence adds
    'pancreatic β-cells', 'lipid metabolism', 'energy storage' — strict_verify
    checks (a)-(e) all pass, but the entailment judge must reject.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("β-cells", "NEUTRAL")])
    full_text = (
        "tirzepatide demonstrates synergistic actions on insulin secretion, "
        "glucagon suppression, appetite regulation, and adipocyte metabolism."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic β-cells and acts on adipocytes to influence lipid "
        f"metabolism and energy storage [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False
    assert reason == "entailment_failed"


# ---------- Enforce mode — C2 specificity inflation ----------

def test_enforce_mode_drops_c2_specificity_inflation(monkeypatch):
    """C2 audit case: span says 'GLP-1 RAs' (class-level), sentence
    upgrades to 'semaglutide at the highest studied doses' — that
    specificity is generator-invented and the judge must reject.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("semaglutide", "NEUTRAL")])
    full_text = (
        "tirzepatide produced HbA1c reductions up to 2.4% compared to "
        "GLP-1 RAs across SURPASS clinical trial program."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "tirzepatide HbA1c reductions up to 2.4%, exceeding semaglutide "
        f"at the highest studied doses [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False
    assert reason == "entailment_failed"


# ---------- Enforce mode — C1 numbers nearby but not entailed ----------

def test_enforce_mode_drops_c1_unentailed_numbers(monkeypatch):
    """C1 audit case: span contains decimals 27, 46, 19, 64, 69, 80 (so
    decimal-subset check passes), and shares topical content words. But
    the SPECIFIC claim '69-80% reach <=6.5%' is not stated by the span.
    Mechanical checks pass; entailment judge must reject.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("69-80", "NEUTRAL")])
    # Span contains every decimal the sentence cites (so check (d) passes)
    # AND shares topical content words (so check (e) passes), but does
    # NOT actually state the specific claim "69-80% reach <=6.5%".
    full_text = (
        "tirzepatide patients achieved HbA1c targets in clinical trials "
        "across SURPASS program. Across endpoints the studies report a "
        "spread of values including 6.5, 19, 27, 46, 64, 69, 80 in "
        "different efficacy contexts and subgroup analyses."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "Among tirzepatide patients, 69-80% reached HbA1c <=6.5% versus "
        f"64% with semaglutide [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False
    assert reason == "entailment_failed"


# ---------- Enforce mode — CONTRADICTED also drops ----------

def test_enforce_mode_drops_on_contradicted_verdict(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("decreased", "CONTRADICTED")])
    full_text = "Treatment increased HbA1c reduction by 2.4% in clinical trials."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        f"Treatment decreased HbA1c reduction by 2.4% [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is False
    assert reason == "entailment_failed"


# ---------- Enforce mode — positive control passes ----------

def test_enforce_mode_keeps_legit_paraphrase(monkeypatch):
    """Positive control: a conservative paraphrase fully entailed by the
    span must keep passing under enforce mode. This is the false-positive
    regression guard called out in Codex's `false_positive_risk`.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_fake_judge(monkeypatch, [("HbA1c reduction", "ENTAILED")])
    full_text = (
        "Tirzepatide demonstrated significant HbA1c reduction of 2.4% "
        "in adult patients with type 2 diabetes across SURPASS trials."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "Tirzepatide showed significant HbA1c reduction of 2.4% in "
        f"type 2 diabetes patients [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(sentence, pool)
    assert passed is True, f"legit paraphrase must pass, got reason={reason}"
    assert reason is None
    assert len(fake.calls) == 1, "judge should have been called exactly once"


# ---------- Synthesis claim with tokens — still gated ----------

def test_synthesis_claim_with_tokens_still_runs_entailment(monkeypatch):
    """A synthesis-flagged claim that DOES carry tokens must clear the
    same content-correctness bar as any other cited sentence — the
    is_synthesis_claim exemption only short-circuits the no-token path.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("invented mechanism", "NEUTRAL")])
    full_text = (
        "Across the trials, tirzepatide produced consistent HbA1c reductions "
        "and weight loss in adults with type 2 diabetes."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "These trials suggest an invented mechanism explains tirzepatide "
        f"effects [#ev:src-1:0-{len(full_text)}]."
    )
    passed, reason = verify_sentence(
        sentence, pool, is_synthesis_claim=True
    )
    assert passed is False
    assert reason == "entailment_failed"


def test_synthesis_claim_without_tokens_skips_entailment(monkeypatch):
    """The pure synthesis path (no tokens, is_synthesis_claim=True) MUST
    NOT call the judge — that path was always exempt and stays exempt.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_fake_judge(monkeypatch, [("", "NEUTRAL")])
    pool = _pool(_src(full_text="Aspirin reduced cardiovascular events."))
    passed, reason = verify_sentence(
        "These trials together suggest a moderate effect.",
        pool,
        is_synthesis_claim=True,
    )
    assert passed is True
    assert reason is None
    assert fake.calls == [], "synthesis-no-token path must not invoke the judge"


# ---------- Drop reason propagates through verify_sentence_to_record ----------

def test_record_carries_entailment_failed_reason(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install_fake_judge(monkeypatch, [("β-cells", "NEUTRAL")])
    full_text = (
        "tirzepatide demonstrates synergistic actions on insulin secretion, "
        "glucagon suppression, appetite regulation, and adipocyte metabolism."
    )
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic β-cells and acts on adipocytes to influence lipid "
        f"metabolism and energy storage [#ev:src-1:0-{len(full_text)}]."
    )
    record = verify_sentence_to_record(sentence, "sec_m", pool)
    assert record.verifier_pass is False
    assert record.drop_reason == "entailment_failed"
    assert record.evaluator_agrees is False


# ---------- Mode helper — env interpretation ----------

@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("off", "off"),
        ("OFF", "off"),
        (" off ", "off"),
        ("warn", "warn"),
        ("WARN", "warn"),
        ("enforce", "enforce"),
        ("Enforce", "enforce"),
        ("", "off"),
        ("strict", "off"),  # unknown -> off
        ("1", "off"),        # truthy but not a valid mode -> off
    ],
)
def test_entailment_mode_env_parsing(monkeypatch, env_value, expected):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", env_value)
    assert strict_verify._entailment_mode() == expected


def test_entailment_mode_unset_defaults_off(monkeypatch):
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    assert strict_verify._entailment_mode() == "off"


# ---------- Two-family invariant on judge model (§9.1.1) ----------

def test_judge_construction_fails_when_judge_same_family_as_generator(
    monkeypatch,
):
    """If an operator sets PG_ENTAILMENT_MODEL to the same family as
    PG_GENERATOR_MODEL, _EntailmentJudge.__init__ must raise so the
    misconfiguration is visible at construction (§9.1.1, mirroring
    OpenRouterClient.check_family_segregation).
    """
    # Force an obvious same-family collision: generator AND judge both
    # set to the deepseek family.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v3.2-exp")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "deepseek/deepseek-v3.2-exp")
    # Reset module-level singleton + the cached model constants on
    # openrouter_client so the env-var read sees the new values.
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", None, raising=False)
    from polaris_graph.llm import openrouter_client as _orc
    monkeypatch.setattr(_orc, "PG_GENERATOR_MODEL", "deepseek/deepseek-v3.2-exp")
    with pytest.raises(RuntimeError, match="(?i)same training-lineage family"):
        strict_verify._EntailmentJudge()


def test_judge_construction_requires_api_key(monkeypatch):
    """No API key -> immediate RuntimeError. Misconfiguration must be
    surfaced at __init__, not at first .judge() call.
    """
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", None, raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        strict_verify._EntailmentJudge()


# ---------- Mechanical checks still fire BEFORE entailment ----------

def test_numeric_mismatch_short_circuits_before_judge(monkeypatch):
    """If decimal-subset fails, the gate returns numeric_mismatch and
    the judge must not be called — keeps the cheap gates in front of
    the expensive one (cost-and-latency invariant).
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_fake_judge(monkeypatch, [("", "NEUTRAL")])
    full_text = "Trial showed event rate of 18% in treatment arm."
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Trial showed event rate of 23.5% [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is False
    assert reason == "numeric_mismatch"
    assert fake.calls == [], "judge must not run after a mechanical failure"


def test_overlap_too_low_short_circuits_before_judge(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_fake_judge(monkeypatch, [("", "NEUTRAL")])
    full_text = "Tomato basil mozzarella pizza dough recipe pasta"
    pool = _pool(_src(source_id="src-1", full_text=full_text))
    passed, reason = verify_sentence(
        f"Adults with chronic pain experienced relief [#ev:src-1:0-{len(full_text)}].",
        pool,
    )
    assert passed is False
    assert reason == "overlap_too_low"
    assert fake.calls == []
