"""I-bug-094 — env-gated live OpenRouter entailment canary.

Skipped by default. Opt-in via:

    PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=... \
    pytest tests/polaris_graph/generator2/test_strict_verify_entailment_live.py

Or, with the registered `live` marker:

    PG_ENTAILMENT_LIVE=1 OPENROUTER_API_KEY=... pytest -m live

Purpose: catch model-behavior drift that the FakeJudge unit tests
cannot detect. Mocked tests bind the gate WIRING (FakeJudge returns
NEUTRAL → gate drops). They do NOT verify that Gemma 4 31B given the
audit-derived M2/C2/C1 sentence/span pairs actually returns NEUTRAL.

If Gemma 4 31B's recall on M2-style fabrications regresses, OR
OpenRouter's response format changes such that the judge silently
fails open, this canary fails — at which point operator looks at the
prompt + judge output and recalibrates (likely an I-bug-093 demo
sample is also warranted at that point).

Cost: ~4 OpenRouter calls × ~$0.0005 = ~$0.002 per run. Per CLAUDE.md
`feedback_no_cost_mentions.md` cost is not the gating concern; this
is a deliberate opt-in canary, not a per-CI-run cost.

Per Codex iter-1 brief verdict (`.codex/I-bug-094/codex_brief_verdict.txt`):
- skip mechanism: skipif at collect-time (clean CI logs)
- failure on model drift: hard_fail (catch drift early)
- pytest marker: yes (`live`)
"""

from __future__ import annotations

import os

import pytest

from polaris_graph.generator2 import strict_verify

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("PG_ENTAILMENT_LIVE"),
        reason=(
            "PG_ENTAILMENT_LIVE not set — opt-in only. "
            "Set PG_ENTAILMENT_LIVE=1 + OPENROUTER_API_KEY to run."
        ),
    ),
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY required for live entailment canary",
    ),
]


# ---------- Audit-derived fixtures (verbatim from CROSS_REVIEW.md) ----------

_M2_SPAN = (
    "tirzepatide demonstrates synergistic actions on insulin secretion, "
    "glucagon suppression, appetite regulation, and adipocyte metabolism."
)
_M2_SENTENCE = (
    "GIP receptor agonism independently potentiates insulin secretion "
    "from pancreatic beta-cells and acts on adipocytes to influence "
    "lipid metabolism and energy storage."
)

_C2_SPAN = (
    "tirzepatide produced HbA1c reductions up to 2.4% compared to "
    "GLP-1 RAs across SURPASS clinical trial program."
)
_C2_SENTENCE = (
    "tirzepatide HbA1c reductions up to 2.4%, exceeding semaglutide "
    "at the highest studied doses."
)

_C1_SPAN = (
    "tirzepatide patients achieved HbA1c targets in clinical trials "
    "across SURPASS program. Across endpoints the studies report a "
    "spread of values including 6.5, 19, 27, 46, 64, 69, 80 in "
    "different efficacy contexts and subgroup analyses."
)
_C1_SENTENCE = (
    "Among tirzepatide patients, 69-80% reached HbA1c <=6.5% versus "
    "64% with semaglutide."
)

_PARAPHRASE_SPAN = (
    "Tirzepatide demonstrated significant HbA1c reduction of 2.4% "
    "in adult patients with type 2 diabetes across SURPASS trials."
)
_PARAPHRASE_SENTENCE = (
    "Tirzepatide showed significant HbA1c reduction of 2.4% in "
    "type 2 diabetes patients."
)


# ---------- Tests ----------

@pytest.fixture(scope="module")
def _judge() -> strict_verify._EntailmentJudge:
    """Real judge instance — Codex APPROVE'd on the construction path
    in I-bug-092 + family-segregation enforcement at __init__.
    """
    return strict_verify._EntailmentJudge()


def test_live_m2_fabrication_returns_neutral_or_contradicted(_judge):
    """M2 audit case: span talks about adipocyte metabolism in general;
    sentence inserts pancreatic β-cells, lipid metabolism, energy storage.
    Real Gemma 4 31B should mark this NEUTRAL (or CONTRADICTED).
    """
    verdict, reason = _judge.judge(_M2_SENTENCE, _M2_SPAN)
    assert verdict in ("NEUTRAL", "CONTRADICTED"), (
        f"M2 fabrication should not entail; got {verdict!r} reason={reason!r}"
    )


def test_live_c2_specificity_inflation_returns_neutral_or_contradicted(_judge):
    """C2: span supports GLP-1 RA class comparison; sentence upgrades to
    semaglutide-specific claim with 'highest studied doses' framing.
    """
    verdict, reason = _judge.judge(_C2_SENTENCE, _C2_SPAN)
    assert verdict in ("NEUTRAL", "CONTRADICTED"), (
        f"C2 specificity inflation should not entail; "
        f"got {verdict!r} reason={reason!r}"
    )


def test_live_c1_unentailed_numbers_returns_neutral_or_contradicted(_judge):
    """C1: span has the constituent numbers nearby but does NOT state
    the specific 69-80% reach <=6.5% vs 64% semaglutide claim.
    """
    verdict, reason = _judge.judge(_C1_SENTENCE, _C1_SPAN)
    assert verdict in ("NEUTRAL", "CONTRADICTED"), (
        f"C1 unentailed-numbers should not entail; "
        f"got {verdict!r} reason={reason!r}"
    )


def test_live_paraphrase_positive_control_returns_entailed(_judge):
    """Positive control: a conservative paraphrase of the span.
    Both sentence and span carry HbA1c 2.4% reduction in T2D adults.
    Should ENTAIL (no model-drift toward over-strictness).
    """
    verdict, reason = _judge.judge(_PARAPHRASE_SENTENCE, _PARAPHRASE_SPAN)
    assert verdict == "ENTAILED", (
        f"conservative paraphrase should entail; "
        f"got {verdict!r} reason={reason!r}"
    )
