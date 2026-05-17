"""Crown Jewel I-cj-008 — Entailment-correctness invariant.

Per CLAUDE.md §9.1.3 + I-bug-092 (PR #343, commit 58b91362):

`strict_verify.verify_sentence` enforces a 6th content-correctness check
beyond the 5 mechanical checks pinned by I-cj-003 (token presence, token
validity, span bounds, decimal subset, content-word overlap). The 6th
check asks an LLM-as-judge whether the cited span semantically ENTAILS
the sentence. It is gated by `PG_STRICT_VERIFY_ENTAILMENT={off,warn,
enforce}` and defaults to `off`.

This Crown Jewel pins the architectural invariant:
  Under enforce mode, a sentence whose cited span does NOT entail it
  (judge returns NEUTRAL or CONTRADICTED) MUST be dropped with
  drop_reason='entailment_failed'.

The 2026-05-09 audit found that 1 fabricated mechanistic claim and
2 specificity-inflation claims passed the 5 mechanical checks because
they shared topical content words and decimals with their cited spans.
The entailment gate is what closes that hole. If a future edit silently
disables this gate (e.g. removes the enforce branch, drops the
'entailment_failed' literal from DropReason, or makes synthesis-claims
exempt at the wrong layer), the audit-revealed fabrications will start
passing strict_verify again. This Crown Jewel locks the gate teeth.

Notes:
- The fake judge is acceptable per Codex APPROVE iter 1 (`.codex/I-cj-008/codex_brief_verdict.txt`):
  Crown Jewel binds wiring + policy semantics, not model quality or
  provider availability. Model semantic accuracy is I-bug-093's surface.
- Two-family segregation at judge construction is pinned by I-cj-001
  via the underlying `check_family_segregation` function — not duplicated
  here per Codex's `extra_invariants_to_pin` guidance.
- Mechanical-check short-circuit (cheap gates before expensive judge)
  is covered by regular regression in
  `tests/polaris_graph/clinical_generator/test_strict_verify_entailment.py`;
  not promoted here per Codex's guidance.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.polaris_graph.clinical_generator import strict_verify
from src.polaris_graph.clinical_generator.strict_verify import (
    verify_sentence,
    verify_sentence_to_record,
)
from src.polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Fixtures (mirror I-cj-003 patterns) ----------

# Realistic M2-pattern: span talks about adipocyte metabolism in general,
# sentence claims pancreatic β-cells / lipid metabolism / energy storage —
# specifics not in the span. This is the actual fabrication the audit
# surfaced; locking it in as the canonical Crown Jewel scenario.
_M2_SPAN_TEXT = (
    "tirzepatide demonstrates synergistic actions on insulin secretion, "
    "glucagon suppression, appetite regulation, and adipocyte metabolism."
)
_M2_SENTENCE = (
    "GIP receptor agonism independently potentiates insulin secretion "
    "from pancreatic beta-cells and acts on adipocytes to influence "
    f"lipid metabolism and energy storage [#ev:src-m2:0-{len(_M2_SPAN_TEXT)}]."
)


def _m2_pool() -> EvidencePool:
    src = Source(
        url="https://www.urncst.org/article",
        domain="urncst.org",
        tier=SourceTier.T1,
        title="t",
        snippet="s",
        full_text=_M2_SPAN_TEXT,
        full_text_available=True,
        source_id="src-m2",
    )
    return EvidencePool(
        pool_id="cj008",
        decision_id="cj008",
        sources=[src],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0,
            },
            min_required_per_tier={
                SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0,
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


class _FakeJudge:
    """Deterministic judge for Crown Jewel wiring tests.

    Returns the configured verdict on every call and counts invocations
    so off-mode tests can assert the judge is never reached.
    """

    def __init__(self, verdict: str, reason: str = "fake") -> None:
        self.verdict = verdict
        self.reason = reason
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return self.verdict, self.reason


def _install(monkeypatch, fake: _FakeJudge) -> None:
    monkeypatch.setattr(strict_verify, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(strict_verify, "_get_judge", lambda: fake)


# ---------- Core invariant: enforce mode + NEUTRAL -> entailment_failed ----------

def test_cj_008_enforce_neutral_drops_with_entailment_failed(monkeypatch) -> None:
    """The audit-revealed M2 fabrication MUST be dropped under enforce
    mode when the judge returns NEUTRAL.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    ok, reason = verify_sentence(_M2_SENTENCE, _m2_pool(), min_content_overlap=2)
    assert ok is False
    assert reason == "entailment_failed"


def test_cj_008_enforce_contradicted_drops_with_entailment_failed(
    monkeypatch,
) -> None:
    """CONTRADICTED is also a hard drop under enforce mode."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("CONTRADICTED"))
    ok, reason = verify_sentence(_M2_SENTENCE, _m2_pool(), min_content_overlap=2)
    assert ok is False
    assert reason == "entailment_failed"


# ---------- Positive control: enforce mode + ENTAILED keeps sentence ----------

def test_cj_008_enforce_entailed_keeps_sentence(monkeypatch) -> None:
    """Conservative paraphrase fully entailed by span must KEEP passing.
    Without this control, the gate could pin a false-positive (drops
    legit content) and still satisfy the negative tests above.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_and_return(monkeypatch, _FakeJudge("ENTAILED"))
    ok, reason = verify_sentence(_M2_SENTENCE, _m2_pool(), min_content_overlap=2)
    assert ok is True
    assert reason is None
    assert len(fake.calls) == 1, "judge must be called exactly once on enforce"


def _install_and_return(monkeypatch, fake: _FakeJudge) -> _FakeJudge:
    _install(monkeypatch, fake)
    return fake


# ---------- Mode gating: off mode never invokes judge ----------

def test_cj_008_off_mode_never_invokes_judge(monkeypatch) -> None:
    """Default mode (off) MUST NOT call the judge even if a singleton
    is present. This pins the cost-discipline guarantee that off-mode
    pays zero per-sentence latency.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _install_and_return(monkeypatch, _FakeJudge("NEUTRAL"))
    # Off mode keeps the sentence even when judge would have rejected.
    ok, reason = verify_sentence(_M2_SENTENCE, _m2_pool(), min_content_overlap=2)
    assert ok is True
    assert reason is None
    assert fake.calls == [], "off-mode must not invoke the judge"


def test_cj_008_unset_mode_defaults_enforce(monkeypatch) -> None:
    """I-bug-095: production default is enforce. No PG_STRICT_VERIFY_ENTAILMENT
    set -> gate runs + drops on NEUTRAL/CONTRADICTED. The operator escape
    hatch is `PG_STRICT_VERIFY_ENTAILMENT=off` (asserted in the next test).
    """
    monkeypatch.delenv("PG_STRICT_VERIFY_ENTAILMENT", raising=False)
    fake = _install_and_return(monkeypatch, _FakeJudge("NEUTRAL"))
    ok, reason = verify_sentence(
        _M2_SENTENCE, _m2_pool(), min_content_overlap=2,
    )
    assert ok is False, "default-enforce must drop NEUTRAL"
    assert reason == "entailment_failed"
    assert len(fake.calls) == 1, "default-enforce must invoke the judge"


def test_cj_008_explicit_off_disables_gate(monkeypatch) -> None:
    """I-bug-095: operator escape hatch — `PG_STRICT_VERIFY_ENTAILMENT=off`
    bypasses the entailment check, returning the pre-graduation behavior.
    Pinning this so a future edit cannot remove the operator override.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _install_and_return(monkeypatch, _FakeJudge("NEUTRAL"))
    ok, reason = verify_sentence(
        _M2_SENTENCE, _m2_pool(), min_content_overlap=2,
    )
    assert ok is True, "explicit off must keep the sentence"
    assert reason is None
    assert fake.calls == [], "explicit off must not invoke the judge"


# ---------- Warn mode: judge runs but does not drop ----------

def test_cj_008_warn_mode_runs_judge_but_does_not_drop(
    monkeypatch, caplog,
) -> None:
    """Warn is the operator-facing telemetry-only mode. The judge MUST
    be invoked AND the violation MUST be logged, but the sentence is
    still kept (verifier_pass=True). Pinning this so a future edit
    cannot collapse warn into off (silently disabling telemetry) or
    into enforce (silently turning warn into a hard drop).
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    fake = _install_and_return(monkeypatch, _FakeJudge("NEUTRAL", "fake-warn"))
    with caplog.at_level("WARNING"):
        ok, reason = verify_sentence(
            _M2_SENTENCE, _m2_pool(), min_content_overlap=2,
        )
    assert ok is True, "warn mode MUST keep the sentence"
    assert reason is None
    assert len(fake.calls) == 1, "warn mode MUST invoke the judge"
    assert any(
        "entailment NEUTRAL" in record.message for record in caplog.records
    ), "warn mode MUST log a NEUTRAL telemetry line"


# ---------- Synthesis-claim semantics ----------

def test_cj_008_synthesis_with_tokens_still_runs_entailment(monkeypatch) -> None:
    """A synthesis-flagged claim that DOES carry tokens must still clear
    the entailment bar. The is_synthesis_claim exemption only short-
    circuits the no-token path (mirrors I-cj-003's synthesis pass-
    without-token semantics).
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    ok, reason = verify_sentence(
        _M2_SENTENCE,
        _m2_pool(),
        min_content_overlap=2,
        is_synthesis_claim=True,
    )
    assert ok is False
    assert reason == "entailment_failed"


def test_cj_008_synthesis_without_tokens_skips_entailment(monkeypatch) -> None:
    """Pure synthesis (no tokens, is_synthesis_claim=True) MUST NOT
    invoke the judge. Mirrors I-cj-003's synthesis pass-without-token.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _install_and_return(monkeypatch, _FakeJudge("NEUTRAL"))
    ok, reason = verify_sentence(
        "These trials together suggest a moderate effect.",
        _m2_pool(),
        min_content_overlap=2,
        is_synthesis_claim=True,
    )
    assert ok is True
    assert reason is None
    assert fake.calls == [], (
        "synthesis-no-token path must remain exempt from the judge"
    )


# ---------- Drop reason propagation through VerifiedSentence record ----------

def test_cj_008_record_carries_entailment_failed_drop_reason(
    monkeypatch,
) -> None:
    """The orchestrator-level record (VerifiedSentence) MUST faithfully
    carry drop_reason='entailment_failed' so downstream section gates
    + the audit bundle can attribute the drop. Without this, the gate
    drops would be invisible to the operator-facing surface.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    record = verify_sentence_to_record(
        _M2_SENTENCE,
        section_id="cj008",
        pool=_m2_pool(),
        min_content_overlap=2,
    )
    assert record.verifier_pass is False
    assert record.drop_reason == "entailment_failed"
    assert record.evaluator_agrees is False
