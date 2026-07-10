"""S7 RENDER thin checkpoint runner -- offline unit battery.

Drives ``scripts/sec_s7_render_runner.render_cp6_to_report`` on a minimal, made-up cp6
FIXTURE (a DIFFERENT research question than any live corpus) to prove the runner is
question-agnostic and honors the binding render contracts:

  * NO ``[#ev:...]`` / ``[CITE:...]`` audit tokens leak into the reader-facing report;
  * NO orphan citations -- an evidence_id absent from the bibliography is dropped, a
    valid one maps to its numbered ``[N]`` marker;
  * S6 LABEL+REPAIR -- a sentence the checkpoint marks weak is KEPT with a disclosed
    confidence label (never silent-drop);
  * the readable shape renders (H1 title carrying the question, ## Abstract, ## Methods,
    ## Bibliography);
  * the Methods block discloses every deletion (drop counts + reasons) and the RunConfig knobs;
  * cp6 is loaded fail-loud (a smuggled release-verdict key raises).

Fixture data is synthetic STRUCTURE only (tests/fixtures discipline), never used as a
research source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.sec_s7_render_runner import render_cp6_to_report  # noqa: E402


def _write_fixture_cp6(run_dir: Path) -> None:
    """A minimal, made-up cp6 for a cardiology question (distinct from any live corpus)."""
    cp6 = {
        "stage": "post_verification",
        "schema_version": 1,
        "run_id": "s7_unit_fixture",
        "question": "What are the cardiovascular effects of SGLT2 inhibitors in heart failure?",
        "evidence_id_hash": "fixture",
        "verification_details": {
            "totals": {"sentences_verified": 3, "sentences_dropped": 1},
            "drop_reason_counts": {"no_provenance_token": 1},
            "dedup_redundant_count": 0,
            "sections": [
                {
                    "title": "Cardiac_Outcomes",
                    "dropped_due_to_failure": False,
                    "total_dropped": 0,
                    "kept": [
                        {
                            "sentence": "Empagliflozin reduced cardiovascular death by 38 percent. [#ev:empa_trial_2015:10-60]",
                            "tokens": [],
                        },
                        {
                            "sentence": "A marker with no bibliography row must vanish. [#ev:not_in_bib:0-5]",
                            "tokens": [],
                        },
                    ],
                },
                {
                    "title": "Renal_Effects",
                    "dropped_due_to_failure": False,
                    "total_dropped": 0,
                    "kept": [
                        {
                            "sentence": "eGFR decline slowed with treatment. [#ev:renal_study_2019:5-40]",
                            "label": "weak",
                            "tokens": [],
                        }
                    ],
                },
            ],
        },
    }
    (run_dir / "cp6_postverify_checkpoint.json").write_text(
        json.dumps(cp6), encoding="utf-8"
    )
    bib = [
        {"num": 1, "evidence_id": "empa_trial_2015", "statement": "EMPA-REG OUTCOME trial",
         "url": "https://example.org/empa", "tier": "T1", "year": 2015},
        {"num": 2, "evidence_id": "renal_study_2019", "statement": "Renal outcomes study",
         "url": "https://example.org/renal", "tier": "T1", "year": 2019},
    ]
    (run_dir / "bibliography.json").write_text(json.dumps(bib), encoding="utf-8")


@pytest.fixture()
def rendered_report(tmp_path: Path) -> str:
    _write_fixture_cp6(tmp_path)
    out = tmp_path / "report.md"
    render_cp6_to_report(str(tmp_path), str(out), None)
    return out.read_text(encoding="utf-8")


def test_no_audit_token_leak(rendered_report: str) -> None:
    assert "[#ev:" not in rendered_report
    assert "[CITE:" not in rendered_report


def test_orphan_citation_dropped(rendered_report: str) -> None:
    # The evidence_id with no bibliography row is removed entirely (no dangling marker/text).
    assert "not_in_bib" not in rendered_report


def test_valid_citation_mapped_to_number(rendered_report: str) -> None:
    # empa_trial_2015 is bibliography row 1 -> its sentence carries [1].
    assert "Empagliflozin reduced cardiovascular death by 38 percent. [1]" in rendered_report


def test_weak_label_surfaced_not_dropped(rendered_report: str) -> None:
    # S6 LABEL+REPAIR: the weak sentence is KEPT and carries a disclosed confidence label.
    assert "eGFR decline slowed with treatment." in rendered_report
    assert "confidence: weak" in rendered_report


def test_readable_shape_and_title(rendered_report: str) -> None:
    assert rendered_report.startswith("# Research report:")
    assert "SGLT2 inhibitors" in rendered_report  # question carried into the title
    assert "## Abstract" in rendered_report
    assert "## Methods" in rendered_report
    assert "## Bibliography" in rendered_report


def test_methods_discloses_deletions_and_knobs(rendered_report: str) -> None:
    methods = rendered_report[rendered_report.find("## Methods"):]
    assert "Deletions and drops" in methods
    assert "no_provenance_token=1" in methods  # the drop reason is disclosed verbatim
    assert "Run configuration" in methods       # knob disclosure block present
    assert "Reference style requested" in methods


def test_missing_checkpoint_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        render_cp6_to_report(str(tmp_path / "does_not_exist"), str(tmp_path / "r.md"), None)


def test_smuggled_verdict_key_rejected(tmp_path: Path) -> None:
    # A checkpoint that smuggled a release verdict at the top level must fail loud (never render).
    bad = {
        "stage": "post_verification",
        "question": "q",
        "release_outcome": "released",  # forbidden verdict key
        "verification_details": {"sections": []},
    }
    (tmp_path / "postverify_checkpoint.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        render_cp6_to_report(str(tmp_path), str(tmp_path / "r.md"), None)
