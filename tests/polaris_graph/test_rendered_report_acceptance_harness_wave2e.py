"""I-deepfix-001 Wave 2e (#1344): tests for the rendered-report ACCEPTANCE HARNESS.

Proves the harness READS the actual rendered paragraphs and distinguishes a GOOD report (connected
multi-sentence prose, >=2-distinct-citation cross-source analytical units, low labeled-fallback rate,
supported pro + con, no chrome) from a FALSE-FIRED report (mostly labeled-fallback disclosure blocks,
a raw ``[#ev:`` token leaked into the body, one-sided, single-source lookups). Also proves it NEVER
raises on empty / malformed input. Fully offline; the harness imports NO production predicate.
"""

from __future__ import annotations

import json

import pytest

from scripts.rendered_report_acceptance_harness import (
    Thresholds,
    analyze_report,
    body_chrome_flags,
    classify_section,
    count_analytical_units,
    facet_coverage,
    format_summary,
    is_disclosure_block,
    main,
    split_sections,
    two_sided_analysis,
)

# ---------------------------------------------------------------------------
# Synthetic rendered reports
# ---------------------------------------------------------------------------
_GOOD_REPORT = """## Reliability header

_Per-claim corroboration strength (a disclosure signal, not a gate)._

- Evidence-pool claim clusters (total): 120

# Research report: What is the debate on AI's displacement versus creation of jobs?

## Abstract

_Each sentence below is verbatim text carried up from a cited body span._

Automation displaces some tasks previously performed by labor, reducing labor demand in exposed
occupations.[1] In contrast to that displacement channel, the reinstatement effect creates new
tasks and raises labor demand, offsetting the losses.[2][3] Because these two forces operate in
opposite directions, the net employment effect depends on which channel dominates in a given
sector.[2][4]

## Key Findings

- **Displacement.** One more robot per thousand workers reduces the employment-to-population ratio
  by 0.2 percentage points.[1]
- **Creation.** Generative AI raised the productivity of customer-support agents, increasing
  output per worker.[3]

### Task-based automation framework

The task-based framework begins from the thesis that production requires tasks allocated to capital
or labor.[1] Whereas the displacement effect reduces the labor share by eliminating tasks, the
reinstatement effect increases labor demand, and therefore the two channels counterbalance each
other.[1][2] Compared with a pure-substitution account, this framework predicts a smaller net
decline because automation also complements labor and raises output.[2][3]

### Generative-AI productivity evidence

A field study of 5,172 customer-support agents introduced a generative AI assistant in a staggered
rollout.[3] As a result of that intervention, worker productivity increased, and the largest gains
accrued to less-experienced workers.[3][4] However, relative to experienced workers, the measured
benefit was smaller, indicating skill compression rather than uniform improvement.[3][4]

## Conclusion

Taken together, the evidence shows that AI both displaces and creates jobs, and because the balance
varies across industries, aggregate employment effects remain ambiguous.[1][2] Therefore, policy
should target the exposed sectors where displacement outweighs reinstatement.[2][4]
"""

_FALSE_FIRED_REPORT = """## Reliability header

_Per-claim corroboration strength (a disclosure signal, not a gate)._

# Research report: What is the debate on AI's displacement versus creation of jobs?

## Abstract

_Each sentence below is verbatim text carried up from a cited body span._

[verification incomplete: 2 source(s) deterministically ground this claim but entailment
verification was unavailable this run — not counted as verified support: automation and labor]

## Key Findings

- **Displacement.** [uncovered supporting evidence for: robot exposure reduces employment]

### Task-based automation framework

[uncovered supporting evidence for: task-based automation framework of Acemoglu and Restrepo]

[verification incomplete: 1 source(s) deterministically ground this claim but entailment
verification was unavailable this run — not counted as verified support: reinstatement effect]

### Empirical displacement

Robots reduce employment in exposed local labor markets.[4] Received: 31 May 2023 / Accepted: 1
June 2023 / Published online: 5 June 2023 ORCID 0000-0002-1825-0097 [#ev:e12:0-40] job losses were
concentrated in manufacturing.[5]

### Fourth Industrial Revolution framing

Contract-bound content for fourth_industrial_revolution_framing did not survive strict verification
against retrieved primary source text; this slot is a curator-actionable gap.[3]

## Conclusion

[insufficient verified evidence to compose a sentence for: net employment effect of AI]
"""

_GOOD_MANIFEST = {
    "question": "What is the debate on AI's displacement versus creation of jobs?",
    "frame_coverage_report": {
        "entries": [
            {"entity_id": "task_based_automation_framework"},
            {"entity_id": "generative_ai_productivity_evidence"},
            {"entity_id": "quantum_supremacy_unrelated_topic"},
        ]
    },
}


# ---------------------------------------------------------------------------
# GOOD report — accepted (not false-fired), high analytical count, two-sided
# ---------------------------------------------------------------------------
def test_good_report_not_false_fired():
    res = analyze_report(_GOOD_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    assert res["input_present"] is True
    assert res["looks_false_fired"] is False, res["reasons"]
    assert res["reasons"] == []


def test_good_report_has_analytical_cross_source_units():
    res = analyze_report(_GOOD_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c3 = res["check3_analytical_units"]
    assert c3["cross_source_analytical_units"] >= 3, c3


def test_good_report_low_fallback_rate_and_prose_shipped():
    res = analyze_report(_GOOD_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c1 = res["check1_writer_prose_shipped"]
    c2 = res["check2_labeled_fallback_rate"]
    assert c2["fallback_block_rate_by_unit"] == 0.0
    assert c1["prose_shipped_fraction"] >= 0.5
    assert c1["prose_shipped_sections"] >= 2


def test_good_report_two_sided_and_clean_body():
    res = analyze_report(_GOOD_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c4 = res["check4_two_sided"]
    c5 = res["check5_chrome_junk"]
    assert c4["debate_detected"] is True
    assert c4["two_sided"] is True
    assert c4["supported_pro_count"] >= 1 and c4["supported_con_count"] >= 1
    assert c5["chrome_units"] == 0
    assert c5["raw_ev_tokens"] == 0


def test_good_report_facet_presence():
    res = analyze_report(_GOOD_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c6 = res["check6_facet_coverage"]
    assert c6["facet_list_available"] is True
    # the two on-topic facets appear in the body; the unrelated one does not
    assert "task_based_automation_framework" in c6["present_facets"]
    assert "quantum_supremacy_unrelated_topic" in c6["absent_facets"]


# ---------------------------------------------------------------------------
# FALSE-FIRED report — flagged, each defect surfaced
# ---------------------------------------------------------------------------
def test_false_fired_report_is_flagged():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    assert res["looks_false_fired"] is True
    assert res["reasons"], "expected at least one reason for the false-fired flag"


def test_false_fired_high_fallback_rate():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c2 = res["check2_labeled_fallback_rate"]
    assert c2["fallback_block_rate_by_unit"] > 0.5
    assert c2["disclosure_heavy_sections"], "expected disclosure-heavy sections to be named"


def test_false_fired_zero_analytical_units():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    assert res["check3_analytical_units"]["cross_source_analytical_units"] == 0


def test_false_fired_body_chrome_and_raw_ev_token():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c5 = res["check5_chrome_junk"]
    assert c5["raw_ev_tokens"] >= 1
    assert c5["chrome_units"] >= 1
    flags_seen = {f for hit in c5["chrome_examples"] for f in hit["flags"]}
    assert "raw_ev_token" in flags_seen
    assert "author_meta" in flags_seen


def test_false_fired_one_sided_treatment():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    c4 = res["check4_two_sided"]
    assert c4["debate_detected"] is True
    # con-only body (displacement / job loss), no supported pro
    assert c4["two_sided"] is False
    assert c4["missing_side"] in ("pro", "both")


def test_false_fired_reasons_name_each_defect():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    joined = " ; ".join(res["reasons"])
    assert "fallback_block_rate" in joined
    assert "cross_source_analytical_units" in joined


# ---------------------------------------------------------------------------
# Never-raises on empty / malformed input
# ---------------------------------------------------------------------------
def test_empty_report_never_raises():
    res = analyze_report("", manifest=None, thresholds=Thresholds())
    assert res["input_present"] is False
    assert "analysis_error" not in res
    # empty content => no analytical units => advisory flag may trip, but it never raised
    assert "looks_false_fired" in res


def test_malformed_manifest_never_raises():
    # a non-dict manifest is tolerated (treated as absent facet list)
    res = analyze_report(_GOOD_REPORT, manifest=["not", "a", "dict"], thresholds=Thresholds())
    assert res["check6_facet_coverage"]["facet_list_available"] is False
    assert "analysis_error" not in res


def test_whitespace_and_headers_only_never_raises():
    res = analyze_report("#\n\n   \n\n##\n", manifest=None, thresholds=Thresholds())
    assert "looks_false_fired" in res


# ---------------------------------------------------------------------------
# Function-level unit tests (independent detector primitives)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "[verification incomplete: 2 source(s) deterministically ground this claim ...]",
    "[uncovered supporting evidence for: robot exposure reduces employment]",
    "[insufficient verified evidence to compose a sentence for: net effect]",
    "Contract-bound content did not survive strict verification; this slot is a curator-actionable gap.[3]",
])
def test_is_disclosure_block_fires(text):
    assert is_disclosure_block(text) is True


def test_is_disclosure_block_leaves_real_prose_alone():
    assert is_disclosure_block(
        "Automation displaces some tasks and reduces labor demand in exposed occupations.[1]"
    ) is False


@pytest.mark.parametrize("text, expected", [
    ("Received: 31 May 2023 / Accepted: 1 June 2023 / Published online: 5 June 2023.", "author_meta"),
    ("This is an open access article distributed under the Creative Commons license.", "license"),
    ("ORCID 0000-0002-1825-0097 for the corresponding author.", "author_meta"),
    ("residual claim [#ev:e12:0-40] glued into prose.", "raw_ev_token"),
    ("please refresh the page or clear your browser cache and try again.", "browser_ui"),
])
def test_body_chrome_flags_fire(text, expected):
    assert expected in body_chrome_flags(text)


def test_body_chrome_flags_clean_prose():
    assert body_chrome_flags(
        "Automation complements labor and raises productivity in many occupations.[1]"
    ) == []


def test_split_sections_marks_scaffolding():
    secs = split_sections(_GOOD_REPORT)
    titles = {s.title: s.is_scaffolding for s in secs}
    assert titles.get("Reliability header") is True
    assert titles.get("Abstract") is False


def test_classify_section_prose_vs_disclosure():
    secs = {s.title: s for s in split_sections(_FALSE_FIRED_REPORT)}
    concl = classify_section(secs["Conclusion"])
    assert concl["verdict"] == "disclosure_only"
    good_secs = {s.title: s for s in split_sections(_GOOD_REPORT)}
    abstract = classify_section(good_secs["Abstract"])
    assert abstract["verdict"] == "prose_shipped"


# ---------------------------------------------------------------------------
# CLI smoke — main never raises, returns 0, writes JSON
# ---------------------------------------------------------------------------
def test_main_on_good_report_returns_zero(tmp_path, capsys):
    rp = tmp_path / "report.md"
    rp.write_text(_GOOD_REPORT, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps(_GOOD_MANIFEST), encoding="utf-8")
    out = tmp_path / "result.json"
    rc = main(["--report", str(rp), "--json-out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["looks_false_fired"] is False
    printed = capsys.readouterr().out
    assert "acceptance harness" in printed


def test_main_on_missing_report_returns_zero(tmp_path):
    rc = main(["--report", str(tmp_path / "does_not_exist.md")])
    assert rc == 0  # never a gate: missing input still exits 0


def test_format_summary_renders_for_false_fired():
    res = analyze_report(_FALSE_FIRED_REPORT, manifest=_GOOD_MANIFEST, thresholds=Thresholds())
    text = format_summary(res, Thresholds())
    assert "looks_false_fired: True" in text
    assert "ADVISORY" in text
