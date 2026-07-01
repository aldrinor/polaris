"""WS-5 (I-deepfix-001 beat-both) — figure-consistency re-key of the low-confidence annotation.

Residual D1 from the drb_72 re-smoke: the confidence annotation keyed on ``claim_id``, so the
Eloundou "46%" figure was flagged low-confidence on its Key-Findings sibling (claim 02-002,
UNSUPPORTED) yet its VERIFIED span/figure twin (claim 02-010) — re-lifted VERBATIM into the
Conclusion — shipped CLEAN with the caveat stripped. These tests use the EXACT strings + span text
from the banked drb_72 artifacts.

FIX-a: a VERIFIED twin that shares a span-identity tuple AND a numeric figure with a flagged claim
inherits the flagged sibling's marker (``annotate_report_against_verdicts``).
FIX-b: ``effect_size_conditional_reason`` fires when a re-lift drops the span's governing
conditional/threshold antecedent that qualifies the number ("When accounting for ... 46%").

Both are ADD-caveat-only (§-1.3): they never change a verdict, widen a span, or remove a caveat.
Kill-switch ``PG_FIGURE_CONSISTENCY_ANNOTATE`` (default ON) reverts byte-identically.
Offline: pure string ops, no API, no GPU.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.roles.report_redactor import annotate_report_against_verdicts
from src.polaris_graph.generator.overstatement_guard import effect_size_conditional_reason

# ── EXACT banked strings (four_role_claim_audit.json) ────────────────────────────────────────────
_FLAGGED_SENT = "Headline exposure estimate: just over 46% of jobs [#ev:eloundou_gpts_are_gpts:0-800]."
_TWIN_SENT = (
    "Using this framework, they estimate that just over 46% of jobs are exposed to "
    "LLM-related technologies [#ev:eloundou_gpts_are_gpts:0-800]."
)
# Same-span (eloundou 0-800) but repeats NO flagged figure -> must NOT inherit the caveat.
_SAME_SPAN_NO_FIGURE_SENT = (
    "Eloundou et al. propose a framework for evaluating the potential impacts of large-language "
    "models [#ev:eloundou_gpts_are_gpts:0-800]."
)

# The real evidence_pool eloundou_gpts_are_gpts[0:800] span (the 46% is governed by the
# "When accounting for ... future software developments" conditional).
_ELOUNDOU_SPAN = (
    "Research is needed to estimate how jobs may be affected We propose a framework for evaluating "
    "the potential impacts of large-language models (LLMs) and associated technologies on work by "
    "considering their relevance to the tasks workers perform in their jobs. By applying this "
    "framework (with both humans and using an LLM), we estimate that roughly 1.8% of jobs could "
    "have over half their tasks affected by LLMs with simple interfaces and general training. When "
    "accounting for current and likely future software developments that complement LLM "
    "capabilities, this share jumps to just over 46% of jobs."
)

_SIBLING_MARKER = "[confidence: low — low confidence — NOT confirmed by the cited source; treat as unverified]"

# Report body mirroring the banked shape: the flagged sentence + its VERIFIED twin share a
# Key-Findings line; the twin is re-lifted VERBATIM into the Conclusion (caveat stripped today).
_REPORT = (
    "## Key Findings\n\n"
    f"{_FLAGGED_SENT[:-len(' [#ev:eloundou_gpts_are_gpts:0-800].')]}.[7] "
    f"{_TWIN_SENT[:-len(' [#ev:eloundou_gpts_are_gpts:0-800].')]}.[7] "
    f"{_SAME_SPAN_NO_FIGURE_SENT[:-len(' [#ev:eloundou_gpts_are_gpts:0-800].')]}.[7]\n\n"
    "## Conclusion\n\n"
    f"{_TWIN_SENT[:-len(' [#ev:eloundou_gpts_are_gpts:0-800].')]}.[7]\n"
)

_AUDIT = {
    "02-002-af53af14": {"sentence": _FLAGGED_SENT, "severity": "S3", "evidence_ids": ["eloundou_gpts_are_gpts"]},
    "02-010-7792e98e": {"sentence": _TWIN_SENT, "severity": "S3", "evidence_ids": ["eloundou_gpts_are_gpts"]},
    "02-009-10f90902": {"sentence": _SAME_SPAN_NO_FIGURE_SENT, "severity": "S3", "evidence_ids": ["eloundou_gpts_are_gpts"]},
}


def _conclusion_block(report_text: str) -> str:
    return report_text.split("## Conclusion", 1)[1]


# ───────────────────────────────────── FIX-a ─────────────────────────────────────────────────────
def test_fixa_conclusion_twin_inherits_flagged_sibling_marker(monkeypatch):
    """THE residual-D1 acceptance: the Conclusion "46%" twin (VERIFIED 02-010) now carries the SAME
    low-confidence marker its flagged Key-Findings sibling (02-002) has."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    verdicts = {"02-002-af53af14": "UNSUPPORTED", "02-010-7792e98e": "VERIFIED", "02-009-10f90902": "VERIFIED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"02-002-af53af14": _SIBLING_MARKER})

    concl = _conclusion_block(res.report_text)
    # The Conclusion twin sentence is present AND now carries a confidence caveat...
    assert "just over 46% of jobs are exposed to LLM-related technologies" in concl
    assert "[confidence:" in concl, f"Conclusion twin still CLEAN (leak):\n{concl}"
    # ...specifically the SAME marker the flagged sibling has.
    assert _SIBLING_MARKER in concl, f"twin did not inherit the sibling marker:\n{concl}"
    # 02-010 recorded as annotated (advisory twin), verdict untouched (still VERIFIED input).
    assert "02-010-7792e98e" in {a.claim_id for a in res.annotated}
    assert verdicts["02-010-7792e98e"] == "VERIFIED"  # the annotator NEVER flips a verdict (§-1.3)


def test_fixa_surgical_same_span_without_shared_figure_not_caveated(monkeypatch):
    """§-1.3 surgical: a same-span (0-800) VERIFIED claim that repeats NO flagged figure (02-009,
    no '46') must stay CLEAN — over-caveating unrelated verified prose is not done."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    verdicts = {"02-002-af53af14": "UNSUPPORTED", "02-010-7792e98e": "VERIFIED", "02-009-10f90902": "VERIFIED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"02-002-af53af14": _SIBLING_MARKER})
    assert "02-009-10f90902" not in {a.claim_id for a in res.annotated}
    # The 02-009 sentence renders WITHOUT a caveat appended right after it.
    seg = res.report_text.split("Eloundou et al. propose a framework", 1)[1][:120]
    assert "[confidence:" not in seg, f"02-009 wrongly caveated: {seg!r}"


def test_fixa_killswitch_off_leaves_twin_clean(monkeypatch):
    """Flag OFF -> byte-identical claim_id-only behaviour: the Conclusion twin ships CLEAN (proving
    the WS-5 re-key, not some pre-existing path, is what adds the caveat)."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "0")
    verdicts = {"02-002-af53af14": "UNSUPPORTED", "02-010-7792e98e": "VERIFIED", "02-009-10f90902": "VERIFIED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {"02-002-af53af14": _SIBLING_MARKER})
    concl = _conclusion_block(res.report_text)
    assert "[confidence:" not in concl, "flag OFF must NOT caveat the twin (regression)"
    assert "02-010-7792e98e" not in {a.claim_id for a in res.annotated}


# ───────────────────────────────────── FIX-b ─────────────────────────────────────────────────────
def test_fixb_guard_fires_on_conditional_stripped_relift(monkeypatch):
    """The effect-size guard FIRES: the bare re-lift keeps '46' but drops the span's 'When accounting
    for ... future software developments' antecedent that governs it."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    bare = "Using this framework, they estimate that just over 46% of jobs are exposed to LLM-related technologies."
    reason = effect_size_conditional_reason(bare, _ELOUNDOU_SPAN)
    assert reason is not None and "46" in reason, reason


def test_fixb_guard_inert_when_antecedent_travels(monkeypatch):
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    faithful = "When accounting for future software developments, just over 46% of jobs could be affected."
    assert effect_size_conditional_reason(faithful, _ELOUNDOU_SPAN) is None


def test_fixb_guard_inert_when_span_has_no_conditional(monkeypatch):
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    plain_span = "One more robot per thousand workers reduces the employment-to-population ratio by 46%."
    bare = "The employment-to-population ratio fell by 46%."
    assert effect_size_conditional_reason(bare, plain_span) is None


def test_fixb_guard_killswitch_off_is_inert(monkeypatch):
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "0")
    bare = "Using this framework, they estimate that just over 46% of jobs are exposed to LLM-related technologies."
    assert effect_size_conditional_reason(bare, _ELOUNDOU_SPAN) is None


def test_fixb_annotator_caveats_via_span_even_with_no_flagged_twin(monkeypatch):
    """FIX-b fires INDEPENDENTLY of FIX-a: even when EVERY verdict is VERIFIED (no flagged sibling
    for FIX-a to inherit from), supplying the cited span text makes the annotator caveat the
    conditional-stripped 46% re-lift."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    verdicts = {"02-002-af53af14": "VERIFIED", "02-010-7792e98e": "VERIFIED", "02-009-10f90902": "VERIFIED"}
    res = annotate_report_against_verdicts(
        _REPORT, verdicts, _AUDIT, {},
        span_text_by_claim={"02-010-7792e98e": _ELOUNDOU_SPAN, "02-009-10f90902": _ELOUNDOU_SPAN},
    )
    concl = _conclusion_block(res.report_text)
    assert "[confidence:" in concl, f"FIX-b did not caveat the conditional-stripped twin:\n{concl}"
    # 02-009 (no figure re-lifted) stays clean even with span text supplied.
    assert "02-009-10f90902" not in {a.claim_id for a in res.annotated}


def test_fixb_annotator_no_span_map_is_inert(monkeypatch):
    """No span_text_by_claim + all VERIFIED -> byte-identical (FIX-b needs the span text)."""
    monkeypatch.setenv("PG_FIGURE_CONSISTENCY_ANNOTATE", "1")
    verdicts = {"02-002-af53af14": "VERIFIED", "02-010-7792e98e": "VERIFIED", "02-009-10f90902": "VERIFIED"}
    res = annotate_report_against_verdicts(_REPORT, verdicts, _AUDIT, {})
    assert res.report_text == _REPORT
    assert res.annotated_count == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
