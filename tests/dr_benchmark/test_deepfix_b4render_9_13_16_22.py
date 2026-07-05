"""I-deepfix-001 B4-render tail batch (#1344) — RED/GREEN for findings #9, #13, #16, #22.

All four are HONESTY / render fixes. None relaxes the faithfulness engine (strict_verify / NLI /
4-role D8 / provenance / span-grounding) and none drops a real source: #9 escalates an over-claim to
a faithfulness-TIGHTENING drop, #13/#22 suppress non-content chrome from the rendered surfaces, #16
emits an honest WAIVER instead of a silent PASS. Each fix is a default-ON LAW VI kill-switch that
reverts byte-identically when disabled. Offline: pure string ops, no API, no GPU.

  #9  — a tasks-vs-jobs UNIT-CONFLATION guard drops a claim that binds a percentage to a JOB unit
        ("46% of jobs") that the cited span binds to a TASK unit ("46% of tasks") — the units
        misstatement the numeric leg passes. (The companion conditional/threshold-STRIP class is
        already dropped by the existing S5 leg; this closes the orthogonal unit-swap gap.)
  #13 — the block-page chrome scrub reuses the shared render-chrome detector at SENTENCE granularity,
        catching glued mid-prose chrome (editor/affiliation/masthead) the whole-unit render seam is
        blind to — in the body AND the §8 basket labels.
  #16 — PT03 emits an honest WAIVER (waived=True) on an operator-permitted same-family (all-GLM)
        run rather than a silent "(separate family)" PASS.
  #22 — the contradiction panel no longer renders a semantic record as "0.0 VS 0.0" and no longer
        quotes a chrome-only span as one side of a conflict.
"""

from __future__ import annotations

import json

import pytest

# ── #9 tasks-vs-jobs unit conflation. The claim binds 46% to JOBS; the span binds it to TASKS. ────
_TASK_SPAN = (
    "By applying this framework we estimate that just over 46% of tasks could be affected by "
    "large language models across the surveyed occupations."
)
_JOB_CLAIM = "They estimate that just over 46% of jobs are exposed to LLM-related technologies."
# A span that DOES support the claim's unit (46% of jobs) — the guard must stay inert (no false drop).
_JOB_SPAN = "We estimate that just over 46% of jobs are exposed to language-model technologies."


# ═══════════════════════════════ FINDING #9 — tasks-vs-jobs unit conflation ═══════════════════════
def test_9_green_unit_conflation_drops_tasks_stated_as_jobs(monkeypatch):
    """GREEN: the default-ON guard returns a strict_verify failure reason when the claim binds 46%
    to JOBS but the cited span binds the same 46% to TASKS (and never to jobs) — a units
    misstatement the numeric leg passes."""
    monkeypatch.delenv("PG_UNIT_CONFLATION_GUARD", raising=False)
    from src.polaris_graph.generator.overstatement_guard import unit_conflation_reason
    reason = unit_conflation_reason(_JOB_CLAIM, _TASK_SPAN)
    assert reason is not None and "46" in reason
    assert reason.startswith("unit_conflation_tasks_as_jobs")


def test_9_red_killswitch_off_reverts_to_no_drop(monkeypatch):
    """RED: with PG_UNIT_CONFLATION_GUARD=0 the guard is inert (None) — byte-identical revert."""
    monkeypatch.setenv("PG_UNIT_CONFLATION_GUARD", "0")
    from src.polaris_graph.generator.overstatement_guard import unit_conflation_reason
    assert unit_conflation_reason(_JOB_CLAIM, _TASK_SPAN) is None


def test_9_inert_when_span_supports_the_claims_unit(monkeypatch):
    """Precision: when the span DOES bind 46% to JOBS (the claim's own unit), the guard never fires."""
    monkeypatch.delenv("PG_UNIT_CONFLATION_GUARD", raising=False)
    from src.polaris_graph.generator.overstatement_guard import unit_conflation_reason
    assert unit_conflation_reason(_JOB_CLAIM, _JOB_SPAN) is None


def test_9_inert_when_claim_has_no_job_percentage(monkeypatch):
    """Precision: a claim with no 'N% of jobs' binding is inert (nothing to conflate)."""
    monkeypatch.delenv("PG_UNIT_CONFLATION_GUARD", raising=False)
    from src.polaris_graph.generator.overstatement_guard import unit_conflation_reason
    assert unit_conflation_reason("Adoption of language models is accelerating.", _TASK_SPAN) is None


def test_9_guard_is_wired_into_the_strict_verify_path():
    """The provenance_generator B16 block imports AND references the #9 unit-conflation guard."""
    import inspect
    from src.polaris_graph.generator import provenance_generator as pg
    src = inspect.getsource(pg)
    assert "_unit_conflation_guard_enabled" in src
    assert "_unit_conflation_reason(_b16_claim, _b16_span)" in src


# ═══════════════════════════════ FINDING #13 — shared chrome scrub per sentence ═══════════════════
# A single chrome SENTENCE (author/ORCID/affiliation byline) that the OLD block_page predicate
# (hard bot-challenge markers + copyright footer) does NOT catch, but the shared render-chrome
# detector DOES — the glued-mid-prose class the whole-unit render seam is blind to.
_CHROME_SENTENCE = "John Smith 1 ORCID 0000-0002-1825-0097 Department of Economics, MIT, Cambridge, MA."
_REAL_FINDING = "Automation could displace many workers across affected sectors within the decade."


def test_13_red_shared_leg_off_is_blind_to_glued_chrome(monkeypatch):
    """RED: with PG_BLOCK_PAGE_CHROME_SCRUB_SHARED=0 the sentence predicate is blind to the
    author/affiliation chrome (the pre-#13 behaviour) — hard-marker + copyright only."""
    monkeypatch.setenv("PG_BLOCK_PAGE_CHROME_SCRUB_SHARED", "0")
    from src.polaris_graph.generator.block_page_chrome_scrub import is_block_page_chrome_sentence
    assert is_block_page_chrome_sentence(_CHROME_SENTENCE) is False


def test_13_green_shared_leg_catches_glued_chrome_and_keeps_findings(monkeypatch):
    """GREEN: default-ON, the shared leg flags the chrome sentence while a real finding is kept."""
    monkeypatch.delenv("PG_BLOCK_PAGE_CHROME_SCRUB_SHARED", raising=False)
    from src.polaris_graph.generator.block_page_chrome_scrub import is_block_page_chrome_sentence
    assert is_block_page_chrome_sentence(_CHROME_SENTENCE) is True
    assert is_block_page_chrome_sentence(_REAL_FINDING) is False


def test_13_green_scrub_drops_only_the_glued_chrome_sentence(monkeypatch):
    """GREEN: a body/§8 line with a real finding welded to a chrome sentence renders the finding and
    drops ONLY the chrome (line-scoped partition; real content preserved)."""
    monkeypatch.delenv("PG_BLOCK_PAGE_CHROME_SCRUB_SHARED", raising=False)
    monkeypatch.delenv("PG_BLOCK_PAGE_CHROME_SCRUB", raising=False)
    from src.polaris_graph.generator.block_page_chrome_scrub import scrub_block_page_chrome
    line = f"{_REAL_FINDING} {_CHROME_SENTENCE}"
    out, dropped = scrub_block_page_chrome(line)
    assert dropped == 1
    assert "Automation could displace many workers" in out
    assert "ORCID" not in out


def test_13_red_scrub_killswitch_off_is_byte_identical(monkeypatch):
    """RED: the whole scrub OFF => byte-identical (chrome leaks, proving the scrub is what removes it)."""
    monkeypatch.setenv("PG_BLOCK_PAGE_CHROME_SCRUB", "0")
    from src.polaris_graph.generator.block_page_chrome_scrub import scrub_block_page_chrome
    line = f"{_REAL_FINDING} {_CHROME_SENTENCE}"
    out, dropped = scrub_block_page_chrome(line)
    assert dropped == 0 and out == line


# ═══════════════════════════════ FINDING #16 — PT03 honest WAIVER ═════════════════════════════════
# A Methods clause that discloses the voided two-family safeguard via the shared-literal tokens the
# same-family override run emits, plus the evaluator model name.
_ALLGLM_REPORT = (
    "Methods. Generator model z-ai/glm-5.2. Evaluator model z-ai/glm-5.2. This run is "
    "not family-segregated: generator and evaluator are the same family, so the "
    "self-bias safeguard disabled. protocol.json pre-registered. Retrieved 2026-04-17. "
    "Inclusion and exclusion criteria. Tier T1-T7."
)


def _pt03(**kw):
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks
    results, _n, _m = run_rule_checks(
        report_text=_ALLGLM_REPORT, protocol={}, tier_distribution_report=None,
        contradictions=[], evidence_pool={}, generator_model="z-ai/glm-5.2",
        evaluator_model="z-ai/glm-5.2", generator_family="glm", evaluator_family="glm", **kw,
    )
    return next(r for r in results if r.item_id == "PT03")


def test_16_green_same_family_override_emits_honest_waiver(monkeypatch):
    """GREEN: an all-GLM (same-family) operator-permitted run emits PT03 as an HONEST WAIVER —
    passed stays True (override authorised the run) BUT waived=True + a WAIVED detail, so the
    artifact never claims a silent genuine '(separate family)' pass."""
    monkeypatch.setenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", "1")
    monkeypatch.delenv("PG_PT03_WAIVED_HONEST", raising=False)
    p = _pt03()
    assert p.passed is True
    assert p.waived is True
    assert "WAIVED" in p.details and "same family" in p.details.lower()


def test_16_red_honest_off_reverts_to_silent_pass(monkeypatch):
    """RED: PG_PT03_WAIVED_HONEST=0 reverts to the pre-#16 silent pass (passed True, waived False,
    no WAIVED detail) — byte-identical to the old behaviour the finding flagged."""
    monkeypatch.setenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", "1")
    monkeypatch.setenv("PG_PT03_WAIVED_HONEST", "0")
    p = _pt03()
    assert p.passed is True
    assert p.waived is False
    assert "WAIVED" not in p.details


def test_16_distinct_families_never_waived(monkeypatch):
    """A genuinely distinct-family pair is a real pass, never a waiver (no waived flag/detail)."""
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks
    results, _n, _m = run_rule_checks(
        report_text="Evaluator model qwen/qwen3. protocol.json Retrieved 2026-04-17. inclusion exclusion T1",
        protocol={}, tier_distribution_report=None, contradictions=[], evidence_pool={},
        generator_model="deepseek/deepseek-v4-pro", evaluator_model="qwen/qwen3",
        generator_family="deepseek", evaluator_family="qwen",
    )
    p = next(r for r in results if r.item_id == "PT03")
    assert p.passed is True and p.waived is False


def test_16_json_strips_waived_key_when_no_waiver(monkeypatch):
    """Byte-identity: evaluator_rule_checks.json emits the ``waived`` key ONLY on a waived rule; a
    run with no waiver drops the key entirely (legacy JSON unchanged)."""
    from src.polaris_graph.evaluator.external_evaluator import (
        EvaluatorOutput, RuleCheckResult,
    )
    plain = EvaluatorOutput(
        "z-ai/glm-5.2", "qwen/qwen3", "glm", "qwen",
        rule_checks=[RuleCheckResult("PT03", "x", True, "")],
    )
    waived = EvaluatorOutput(
        "z-ai/glm-5.2", "z-ai/glm-5.2", "glm", "glm",
        rule_checks=[RuleCheckResult("PT03", "x", True, "WAIVED …", waived=True)],
    )
    assert "waived" not in plain.to_json_dict()["rule_checks"][0]
    assert waived.to_json_dict()["rule_checks"][0]["waived"] is True


# ═══════════════════════════════ FINDING #22 — honest contradiction render ════════════════════════
_SEM_A = {"evidence_id": "ev_042", "tier": "T2", "value": 0.0,
          "text": "Automation could displace between 14 and 41 percent of workers in affected sectors."}
_SEM_B = {"evidence_id": "ev_051", "tier": "T1", "value": 0.0,
          "text": "The empirical findings are inconclusive on employment and productivity effects."}
_CHROME_SIDE = {"evidence_id": "ev_051", "tier": "T1", "value": None,
                "text": "(c) 2008-2026 ResearchGate GmbH. All rights reserved."}
_NUMERIC = {"evidence_id": "ev_09", "tier": "T1", "value": 14.0, "unit": "%"}


def test_22_green_semantic_side_renders_prose_not_zero_vs_zero(monkeypatch):
    """GREEN: a semantic record (0.0 value sentinel) renders its substantive prose, never '0.0'."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import _contradict_side
    side = _contradict_side(_SEM_A, is_semantic=True)
    assert side.startswith('"Automation could displace')
    assert not side.startswith("0.0")


def test_22_red_semantic_side_off_reverts_to_zero(monkeypatch):
    """RED: with PG_CONTRADICTION_RENDER_HONEST=0 the semantic side reverts to the meaningless
    '0.0 [ev=…]' the finding flagged (byte-identical revert)."""
    monkeypatch.setenv("PG_CONTRADICTION_RENDER_HONEST", "0")
    from scripts.run_honest_sweep_r3 import _contradict_side
    assert _contradict_side(_SEM_A, is_semantic=True).startswith("0.0 [ev=ev_042")


def test_22_green_chrome_only_side_is_dropped(monkeypatch):
    """GREEN: a chrome-only span (copyright footer) is NOT surfaced as a contradiction side ('')."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import _contradict_side
    assert _contradict_side(_CHROME_SIDE) == ""


def test_22_red_chrome_only_side_off_renders_chrome(monkeypatch):
    """RED: OFF => the chrome quote leaks as a contradiction side (the behaviour the finding flagged)."""
    monkeypatch.setenv("PG_CONTRADICTION_RENDER_HONEST", "0")
    from scripts.run_honest_sweep_r3 import _contradict_side
    assert "ResearchGate" in _contradict_side(_CHROME_SIDE)


def test_22_numeric_contradiction_side_is_unaffected(monkeypatch):
    """A genuine numeric contradiction still renders its value+unit (no regression)."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import _contradict_side
    assert _contradict_side(_NUMERIC, is_semantic=False) == "14.0% [ev=ev_09, tier=T1]"


def test_22_green_semantic_block_replaces_chrome_quote_with_placeholder(monkeypatch):
    """GREEN: the §5 semantic disclosure block never renders a chrome quote as a claim — it shows a
    neutral pointer while keeping the substantive side, subject/predicate (PT08) and ev/tier."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import render_semantic_disclosure

    class _Rec:
        def __init__(self, subject, predicate, claims, nli_confidence):
            self.subject = subject
            self.predicate = predicate
            self.claims = claims
            self.nli_confidence = nli_confidence

    out = render_semantic_disclosure([_Rec("automation", "employment effect", [_SEM_A, _CHROME_SIDE], 0.82)])
    assert "ResearchGate" not in out              # chrome quote suppressed
    assert "source furniture" in out              # neutral placeholder rendered
    assert "Automation could displace" in out     # the substantive side kept
    assert "automation / employment effect" in out  # PT08 subject/predicate intact


# ── #22 iter-2 P1 regression: a REAL substantive quote LONGER than the cap must render its trimmed
# "…" form, NEVER collapse to the furniture pointer / the generic sidecar fallback. The pre-iter-2
# chrome check ran on the already-quote-trimmed text, whose renderer-appended trailing "…" tripped the
# shared detector's TRUNCATION leg and mislabeled real evidence as "source furniture". ──────────────
_LONG_SEM_PROSE = (  # 218 chars — exceeds both the 200-char §5 cap and the 120-char _contradict_side cap
    "Automation could displace between fourteen and forty-one percent of workers across the affected "
    "manufacturing, clerical, and logistics sectors within the coming decade, according to the panel "
    "central-scenario analysis."
)
_LONG_SEM_A = {"evidence_id": "ev_042", "tier": "T2", "value": 0.0, "text": _LONG_SEM_PROSE}
_SHORT_SEM_B = {"evidence_id": "ev_051", "tier": "T1", "value": 0.0,
                "text": "The empirical findings are inconclusive on employment effects."}


def test_22_green_long_semantic_side_renders_trimmed_quote_not_furniture(monkeypatch):
    """GREEN (iter-2 P1): a semantic side whose substantive prose EXCEEDS the quote cap renders the
    trimmed quote ending in '…' — NOT the '(no substantive quote — source furniture)' pointer. The
    chrome check now keys on the untrimmed text, so our own trim '…' can no longer masquerade as a
    truncation-fragment chrome hit on real evidence."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import render_semantic_disclosure

    class _Rec:
        def __init__(self, subject, predicate, claims, nli_confidence):
            self.subject = subject
            self.predicate = predicate
            self.claims = claims
            self.nli_confidence = nli_confidence

    out = render_semantic_disclosure(
        [_Rec("automation", "employment effect", [_LONG_SEM_A, _SHORT_SEM_B], 0.82)],
        quote_trim=120,
    )
    assert "source furniture" not in out          # a real long quote is NOT mislabeled as furniture
    assert "…" in out                         # the trimmed quote carries the ellipsis
    assert "Automation could displace" in out      # the substantive prose is quoted (trimmed)
    assert "automation / employment effect" in out  # PT08 subject/predicate intact


def test_22_green_long_semantic_side_in_contradict_side_no_sidecar_fallback(tmp_path, monkeypatch):
    """GREEN (iter-2 P1): a >120-char semantic side does NOT return '' from _contradict_side (so the
    caller does not collapse to the generic 'see sidecar' fallback). Verified BOTH at the unit level
    and end-to-end through _render_contradicts_block, whose CONTRADICTS line must quote the real
    trimmed prose rather than the fallback text."""
    monkeypatch.delenv("PG_CONTRADICTION_RENDER_HONEST", raising=False)
    from scripts.run_honest_sweep_r3 import _contradict_side, _render_contradicts_block

    side = _contradict_side(_LONG_SEM_A, is_semantic=True)
    assert side != ""                                     # NOT dropped as chrome
    assert side.startswith('"Automation could displace')  # renders the real trimmed prose
    assert side.rstrip().endswith(']')                    # ev/tier locator intact
    assert "…" in side                               # trimmed with the ellipsis

    # End-to-end: a 2-claim SEMANTIC record whose sides are BOTH real prose (one > cap) renders the
    # both-sides CONTRADICTS line, NOT the "same-subject claims disagree; see the … sidecar" fallback.
    contradictions = [{
        "type": "semantic", "subject": "automation", "predicate": "employment effect",
        "claims": [_LONG_SEM_A, _SHORT_SEM_B],
    }]
    path = tmp_path / "contradictions.json"
    path.write_text(json.dumps(contradictions), encoding="utf-8")
    block = _render_contradicts_block(str(path))
    assert "- CONTRADICTS: automation / employment effect —" in block
    assert "Automation could displace" in block          # the real long side is quoted
    assert "…" in block                              # trimmed with the ellipsis
    assert "same-subject claims disagree" not in block    # did NOT collapse to the sidecar fallback


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
