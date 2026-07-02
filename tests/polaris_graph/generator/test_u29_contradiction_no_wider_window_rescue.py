"""I-deepfix-001 U29 — verify span-imprecision leniency (faithfulness-adjacent).

Autopsy U29 (CONSOLIDATED_ISSUES.md): "a CONTRADICTED narrow-span passed
because the WIDER window ENTAILED (clinical-frame risk)."

The entailment gate in ``verify_sentence_provenance`` first judges the claim
against its NARROW cited byte-range (``combined_span``). When that verdict is
NEUTRAL or CONTRADICTED and the caller allows the local-window fallback, the
gate searches the FULL ``direct_quote`` for a bounded (<=400-char) window that
holds the claim's content words and RE-JUDGES against that WIDER window. Before
this fix a CONTRADICTED narrow span could be RESCUED (masked) by a wider window
that ENTAILS — the clinical-frame risk.

The fix TIGHTENS the gate: a CONTRADICTED narrow-span verdict now ALWAYS fails
closed (no wider-window rescue). Only NEUTRAL (imprecise/incomplete, NOT
refuting) remains eligible for the bounded-window rescue. This never relaxes any
existing gate — it only removes a rescue path for active contradictions.

Offline + deterministic: a fake judge stands in for the NLI judge (no GPU / no
network / no paid LLM), exactly like test_provenance_generator_entailment.py.
"""

from __future__ import annotations

import pytest

# Import the SAME module object the lazy import inside provenance_generator
# uses (``from src.polaris_graph.clinical_generator.strict_verify import ...``),
# so monkeypatching ``_get_judge`` here is picked up by the verifier.
from src.polaris_graph.clinical_generator import strict_verify as _gen2
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)


# A marker that appears ONLY in the wider window region of the evidence, never
# in the narrow cited byte-range. The fake judge keys on it to distinguish the
# first (narrow-span) judge call from the rescue (wider-window) re-judge.
_WIDE_MARKER = "WIDE_ENTAIL_MARKER"


class _WindowKeyedJudge:
    """Fake NLI judge that returns different verdicts for the narrow cited span
    versus the wider rescue window.

    - Wider window (contains ``_WIDE_MARKER``)  -> ENTAILED
    - Narrow cited span (no marker)             -> ``narrow_verdict``
    """

    def __init__(self, narrow_verdict: str) -> None:
        self.narrow_verdict = narrow_verdict
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        if _WIDE_MARKER in span:
            return "ENTAILED", "wide-window entails"
        return self.narrow_verdict, f"narrow-span {self.narrow_verdict.lower()}"


def _install(monkeypatch, fake: _WindowKeyedJudge) -> None:
    monkeypatch.setattr(_gen2, "_JUDGE_SINGLETON", fake, raising=False)
    monkeypatch.setattr(_gen2, "_get_judge", lambda: fake)


@pytest.fixture(autouse=True)
def _reset_telemetry():
    _gen2.reset_judge_telemetry()


# The NARROW cited span (bytes 0..len(_NARROW)) actively REFUTES the claim
# ("reduced" vs the claim's "improved") yet shares >=2 content words so it
# clears the content-word floor and reaches the entailment judge.
_NARROW = "The therapy reduced patient survival outcomes markedly."

# The remainder of the evidence body holds a WIDER window that (per the fake
# judge) ENTAILS the claim. The whole direct_quote is < 400 chars, so the
# rescue's bounded content-window spans it and therefore contains the marker.
_WIDE_EXTRA = (
    f" In the extended cohort analysis {_WIDE_MARKER} the therapy improved "
    "patient survival outcomes in the cohort over the study period."
)
_DIRECT_QUOTE = _NARROW + _WIDE_EXTRA

# Non-numeric claim; content words overlap the narrow span (therapy, patient,
# survival, outcomes) so it clears the content-word floor.
_SENTENCE = (
    "The therapy improved patient survival outcomes in the cohort "
    f"[#ev:ev_u29:0-{len(_NARROW)}]."
)


def _pool() -> dict:
    return {
        "ev_u29": {
            "evidence_id": "ev_u29",
            "direct_quote": _DIRECT_QUOTE,
            "url": "https://example.org/clinical-study",
            "tier": "T1",
        },
    }


def _enforce_env(monkeypatch) -> None:
    # enforce both the entailment gate AND the Phase-0b verification mode, so the
    # non-numeric bounded-window rescue path is live (the branch that could mask
    # the contradiction on the pre-fix code).
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "enforce")


def test_contradicted_narrow_span_not_rescued_by_wider_window(monkeypatch):
    """U29 core: a CONTRADICTED narrow cited span MUST fail closed even when a
    wider in-row window would ENTAIL. The wider window may NOT mask the
    narrow-span contradiction, and the rescue re-judge must never even run.
    """
    _enforce_env(monkeypatch)
    fake = _WindowKeyedJudge("CONTRADICTED")
    _install(monkeypatch, fake)

    result = verify_sentence_provenance(_SENTENCE, _pool())

    assert result.is_verified is False, (
        "a CONTRADICTED narrow span must fail closed; a wider entailing window "
        f"must NOT rescue it, but got is_verified=True (failures={result.failure_reasons})"
    )
    assert any(
        r.startswith("entailment_failed:") and "verdict=CONTRADICTED" in r
        for r in result.failure_reasons
    ), f"expected entailment_failed:verdict=CONTRADICTED, got {result.failure_reasons}"
    # The rescue re-judge (wider window) must NOT have been invoked — a
    # contradiction short-circuits to fail-closed with a single judge call.
    assert len(fake.calls) == 1, (
        "wider-window rescue judge must not run on a CONTRADICTED narrow span; "
        f"judge was called {len(fake.calls)} times"
    )
    assert all(
        _WIDE_MARKER not in span for _, span in fake.calls
    ), "the wider (marker) window must never be judged for a contradiction"


def test_neutral_narrow_span_still_rescued_by_wider_window(monkeypatch):
    """Regression guard: the legitimate NEUTRAL rescue is PRESERVED. A NEUTRAL
    (imprecise, NOT refuting) narrow span is still allowed to be rescued by a
    bounded in-row window that ENTAILS. The fix must not over-reach.
    """
    _enforce_env(monkeypatch)
    fake = _WindowKeyedJudge("NEUTRAL")
    _install(monkeypatch, fake)

    result = verify_sentence_provenance(_SENTENCE, _pool())

    assert result.is_verified is True, (
        "a NEUTRAL narrow span with a genuinely-entailing bounded window must "
        f"still pass (rescue preserved); failures={result.failure_reasons}"
    )
    # Two judge calls: first on the narrow span (NEUTRAL), then the rescue on
    # the wider entailing window (ENTAILED).
    assert len(fake.calls) == 2, (
        f"expected narrow judge + rescue re-judge (2 calls), got {len(fake.calls)}"
    )
    assert _WIDE_MARKER in fake.calls[1][1], (
        "the second (rescue) judge call must be against the wider window"
    )
