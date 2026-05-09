"""I-bug-098 — entailment judge wired into PRODUCTION verifier.

Mirrors tests/polaris_graph/generator2/test_strict_verify_entailment.py
patterns but exercises the production verifier (generator/
provenance_generator.py:verify_sentence_provenance) directly. This is
the verifier the production sweep at scripts/run_honest_sweep_r3.py
actually uses; the I-bug-092..097 generator2/ tests cover the slice-003
demo path which is a different code branch.

Tests use a fake judge to keep CI network-free + deterministic. Live
canary lives at tests/polaris_graph/generator2/
test_strict_verify_entailment_live.py (env-gated).
"""

from __future__ import annotations

import pytest

from polaris_graph.generator2 import strict_verify as _gen2
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)


# ---------- Fake-judge fixture (shared with generator2 telemetry) ----------

class _FakeJudge:
    def __init__(self, verdict: str, reason: str = "fake") -> None:
        self.verdict = verdict
        self.reason = reason
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return self.verdict, self.reason


def _install(monkeypatch, fake: _FakeJudge) -> None:
    """Replace both the judge singleton and the _get_judge factory so
    verify_sentence_provenance picks up our fake.
    """
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    """Ensure each test starts with zero counters."""
    _gen2.reset_judge_telemetry()


# ---------- Helpers — build evidence pool dicts the production way ----------

def _pool(direct_quote: str, evidence_id: str = "ev_x") -> dict:
    return {
        evidence_id: {
            "evidence_id": evidence_id,
            "direct_quote": direct_quote,
            "url": "https://example.org/article",
            "tier": "T1",
        },
    }


# ---------- M2 audit case ----------

_M2_SPAN = (
    "tirzepatide demonstrates synergistic actions on insulin secretion, "
    "glucagon suppression, appetite regulation, and adipocyte metabolism."
)


def test_enforce_drops_m2_fabrication(monkeypatch):
    """The audit-revealed M2 fabrication MUST be dropped under enforce
    by the PRODUCTION verifier (not just generator2/).
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL"))
    pool = _pool(_M2_SPAN, "ev_m2")
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic beta-cells and acts on adipocytes to influence "
        f"lipid metabolism and energy storage [#ev:ev_m2:0-{len(_M2_SPAN)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is False
    assert any(
        r.startswith("entailment_failed:") for r in result.failure_reasons
    ), f"expected entailment_failed reason, got {result.failure_reasons}"


def test_enforce_drops_contradicted_verdict(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("CONTRADICTED"))
    full = "Treatment increased HbA1c by 1 percent in adults."
    pool = _pool(full, "ev_c")
    sentence = (
        f"Treatment increased HbA1c by 1 percent in adults [#ev:ev_c:0-{len(full)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is False
    assert any(
        r.startswith("entailment_failed:") for r in result.failure_reasons
    )


# ---------- Positive control — paraphrase passes ----------

def test_enforce_keeps_legit_paraphrase(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _FakeJudge("ENTAILED")
    _install(monkeypatch, fake)
    full = (
        "Tirzepatide demonstrated significant HbA1c reduction in adults "
        "with type 2 diabetes across SURPASS trials in clinical practice."
    )
    pool = _pool(full, "ev_p")
    sentence = (
        "Tirzepatide showed significant HbA1c reduction in type 2 diabetes "
        f"adults during SURPASS clinical practice trials [#ev:ev_p:0-{len(full)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is True, (
        f"legit paraphrase must pass, got failures={result.failure_reasons}"
    )
    assert len(fake.calls) == 1, "judge invoked exactly once"


# ---------- Off mode — judge never invoked ----------

def test_off_mode_never_invokes_judge(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    fake = _FakeJudge("NEUTRAL")
    _install(monkeypatch, fake)
    pool = _pool(_M2_SPAN, "ev_m2")
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic beta-cells and acts on adipocytes to influence "
        f"lipid metabolism and energy storage [#ev:ev_m2:0-{len(_M2_SPAN)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is True, "off mode must keep the sentence"
    assert fake.calls == [], "off mode must not invoke the judge"


# ---------- Warn mode — judge runs, sentence kept ----------

def test_warn_mode_runs_judge_but_does_not_drop(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "warn")
    fake = _FakeJudge("NEUTRAL")
    _install(monkeypatch, fake)
    pool = _pool(_M2_SPAN, "ev_m2")
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic beta-cells and acts on adipocytes to influence "
        f"lipid metabolism and energy storage [#ev:ev_m2:0-{len(_M2_SPAN)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is True, "warn mode must keep the sentence"
    assert len(fake.calls) == 1, "warn mode must invoke the judge"


# ---------- Mechanical-check short-circuit (cost discipline) ----------

def test_number_mismatch_short_circuits_before_entailment(monkeypatch):
    """If the number-match mechanical check fails, the entailment judge
    MUST NOT run — keeps the cheap gates in front of the expensive one.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _FakeJudge("NEUTRAL")
    _install(monkeypatch, fake)
    full = "Trial showed HbA1c reduction of 1.5 percent in adults."
    pool = _pool(full, "ev_n")
    # Sentence claims 9.9% which is NOT in the span (1.5 only).
    sentence = (
        f"Trial showed HbA1c reduction of 9.9 percent in adults "
        f"[#ev:ev_n:0-{len(full)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    assert result.is_verified is False
    assert any(
        "number_not_in_any_cited_span" in r for r in result.failure_reasons
    )
    assert fake.calls == [], (
        "judge must not run after mechanical failure (cost discipline)"
    )


def test_no_provenance_short_circuits_before_entailment(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    fake = _FakeJudge("NEUTRAL")
    _install(monkeypatch, fake)
    pool = _pool("Some text.", "ev_n")
    result = verify_sentence_provenance("Sentence with no token.", pool)
    assert result.is_verified is False
    assert "no_provenance_token" in result.failure_reasons
    assert fake.calls == []


# ---------- Telemetry counters tick on production path ----------

def test_telemetry_counters_tick_on_production_path(monkeypatch):
    """Critical I-bug-098 invariant: judge_telemetry counters from
    generator2.strict_verify ALSO tick when the production verifier
    invokes the judge. A single get_judge_telemetry() snapshot must
    cover both code paths (per Codex iter-1 brief acceptance proof).
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("ENTAILED"))
    full = (
        "Adults with chronic pain reported clinical benefit "
        "from regular treatment over the trial period."
    )
    pool = _pool(full, "ev_t")
    sentence = (
        f"Adults with chronic pain reported clinical benefit "
        f"[#ev:ev_t:0-{len(full)}]."
    )
    # Snapshot before
    before = _gen2.get_judge_telemetry()
    assert before["calls"] == 0
    # Invoke
    verify_sentence_provenance(sentence, pool)
    # Snapshot after
    after = _gen2.get_judge_telemetry()
    assert after["calls"] == 1, (
        "production-path call MUST tick the shared counter"
    )
    assert after["entailed"] == 1


def test_telemetry_judge_error_routes_to_judge_error_counter(monkeypatch):
    """Fail-open ('ENTAILED', 'judge_error: ...') ticks judge_error,
    NOT entailed — distinguishes accepted from failed-open. Same
    invariant as I-bug-096 but on the production code path.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(
        monkeypatch,
        _FakeJudge("ENTAILED", "judge_error: TimeoutError"),
    )
    full = "Adults with chronic pain reported clinical benefit."
    pool = _pool(full, "ev_e")
    sentence = (
        f"Adults with chronic pain reported clinical benefit "
        f"[#ev:ev_e:0-{len(full)}]."
    )
    verify_sentence_provenance(sentence, pool)
    snap = _gen2.get_judge_telemetry()
    assert snap["judge_error"] == 1, "fail-open MUST count as judge_error"
    assert snap["entailed"] == 0, "fail-open MUST NOT count as entailed"


# ---------- Drop reason flows through to manifest histogram ----------

def test_entailment_failed_reason_includes_evidence_ids(monkeypatch):
    """The failure_reason string MUST start with 'entailment_failed:'
    so the manifest builder's `r.split(':', 1)[0]` collapses it to
    'entailment_failed' in drop_reason_counts. Pinning the prefix
    contract here.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    _install(monkeypatch, _FakeJudge("NEUTRAL", "fake-reason"))
    pool = _pool(_M2_SPAN, "ev_m2")
    sentence = (
        "GIP receptor agonism independently potentiates insulin secretion "
        "from pancreatic beta-cells and acts on adipocytes to influence "
        f"lipid metabolism and energy storage [#ev:ev_m2:0-{len(_M2_SPAN)}]."
    )
    result = verify_sentence_provenance(sentence, pool)
    matching = [
        r for r in result.failure_reasons
        if r.startswith("entailment_failed:")
    ]
    assert len(matching) == 1
    # Manifest builder split: r.split(":", 1)[0] -> "entailment_failed"
    key = matching[0].split(":", 1)[0]
    assert key == "entailment_failed"
    # Evidence id should be present in the reason payload
    assert "ev_m2" in matching[0]
