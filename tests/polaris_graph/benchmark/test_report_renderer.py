"""Tests for report_renderer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.benchmark.beat_both_scorer import (
    AggregateScoreboard,
    QuestionScores,
    Scoreboard,
    SystemScores,
)
from polaris_graph.benchmark.dimension_scorers import ALL_DIMENSIONS
from polaris_graph.benchmark.report_renderer import (
    render_report,
    render_report_html,
    render_scoreboard_json,
    render_summary_md,
)


def _system_scores(
    system: str, base_score: float = 0.5
) -> SystemScores:
    return SystemScores(
        system=system,
        by_dimension={dim: base_score for dim in ALL_DIMENSIONS},
        evidence={dim: [f"{system}_evidence"] for dim in ALL_DIMENSIONS},
    )


def _question_scores(qid: str = "Q1", refusal_bait: bool = False) -> QuestionScores:
    return QuestionScores(
        question_id=qid,
        question_text=f"text for {qid}",
        is_refusal_bait=refusal_bait,
        polaris=_system_scores("polaris", 0.8),
        chatgpt=_system_scores("chatgpt", 0.5),
        gemini=_system_scores("gemini", 0.6),
    )


def _scoreboard(n_questions: int = 1) -> Scoreboard:
    questions = [_question_scores(f"Q{i+1}") for i in range(n_questions)]
    return Scoreboard(
        benchmark_id="test_run",
        ran_at_utc=datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc),
        per_question=questions,
        aggregate=AggregateScoreboard(
            polaris_mean={dim: 0.8 for dim in ALL_DIMENSIONS},
            chatgpt_mean={dim: 0.5 for dim in ALL_DIMENSIONS},
            gemini_mean={dim: 0.6 for dim in ALL_DIMENSIONS},
            n_questions=n_questions,
        ),
        polaris_wins=n_questions * len(ALL_DIMENSIONS),
        external_wins=0,
        ties=0,
    )


# ---------- scoreboard.json ----------

def test_render_json_is_valid_json():
    sb = _scoreboard()
    data = render_scoreboard_json(sb)
    parsed = json.loads(data.decode("utf-8"))
    assert parsed["benchmark_id"] == "test_run"


def test_render_json_canonical_ordering():
    """sort_keys=True ensures deterministic output."""
    sb = _scoreboard()
    a = render_scoreboard_json(sb)
    b = render_scoreboard_json(sb)
    assert a == b


def test_render_json_includes_all_per_question():
    sb = _scoreboard(n_questions=3)
    data = json.loads(render_scoreboard_json(sb).decode("utf-8"))
    assert len(data["per_question"]) == 3


# ---------- summary.md ----------

def test_render_summary_md_has_title():
    sb = _scoreboard()
    md = render_summary_md(sb)
    assert "POLARIS BEAT-BOTH" in md
    assert sb.benchmark_id in md


def test_render_summary_md_includes_win_counts():
    sb = _scoreboard(n_questions=2)
    md = render_summary_md(sb)
    assert "POLARIS won" in md
    assert str(sb.polaris_wins) in md
    assert str(sb.external_wins) in md


def test_render_summary_md_aggregate_table():
    sb = _scoreboard()
    md = render_summary_md(sb)
    assert "| Dimension | POLARIS | ChatGPT DR | Gemini DR |" in md
    # All 7 dimensions must appear
    for dim_label in ("Sourcing tier mix", "Auditability", "Latency"):
        assert dim_label in md


def test_render_summary_md_top3_dimensions():
    sb = _scoreboard()
    md = render_summary_md(sb)
    # POLARIS dominates by 0.8 - 0.6 = 0.2 across all dims
    assert "+0.20" in md or "+0.2" in md


def test_render_summary_md_handles_no_external_data():
    sb = _scoreboard()
    sb.aggregate.chatgpt_mean = {dim: None for dim in ALL_DIMENSIONS}
    sb.aggregate.gemini_mean = {dim: None for dim in ALL_DIMENSIONS}
    md = render_summary_md(sb)
    assert "no head-to-head dimension data" in md


# ---------- report.html ----------

def test_render_html_well_formed():
    sb = _scoreboard()
    html_str = render_report_html(sb)
    assert html_str.startswith("<!DOCTYPE html>")
    assert "</html>" in html_str
    assert sb.benchmark_id in html_str


def test_render_html_includes_aggregate_and_per_question():
    sb = _scoreboard(n_questions=2)
    html_str = render_report_html(sb)
    assert "Aggregate means" in html_str
    assert "Per-question scores" in html_str
    assert "Q1" in html_str
    assert "Q2" in html_str


def test_render_html_marks_refusal_bait():
    questions = [_question_scores("Q1", refusal_bait=True)]
    sb = Scoreboard(
        benchmark_id="test",
        per_question=questions,
        aggregate=AggregateScoreboard(
            polaris_mean={dim: None for dim in ALL_DIMENSIONS},
            chatgpt_mean={dim: None for dim in ALL_DIMENSIONS},
            gemini_mean={dim: None for dim in ALL_DIMENSIONS},
            n_questions=1,
        ),
        polaris_wins=0,
        external_wins=0,
        ties=0,
    )
    html_str = render_report_html(sb)
    assert "refusal bait" in html_str


def test_render_html_escapes_special_chars():
    """HTML-escape question text + ids."""
    questions = [
        QuestionScores(
            question_id="Q1",
            question_text="Question with <script>alert('xss')</script> & more",
            is_refusal_bait=False,
            polaris=_system_scores("polaris"),
            chatgpt=_system_scores("chatgpt"),
            gemini=_system_scores("gemini"),
        )
    ]
    sb = Scoreboard(
        benchmark_id="test",
        per_question=questions,
        aggregate=AggregateScoreboard(
            polaris_mean={dim: 0.5 for dim in ALL_DIMENSIONS},
            chatgpt_mean={dim: 0.5 for dim in ALL_DIMENSIONS},
            gemini_mean={dim: 0.5 for dim in ALL_DIMENSIONS},
            n_questions=1,
        ),
        polaris_wins=0,
        external_wins=0,
        ties=len(ALL_DIMENSIONS),
    )
    html_str = render_report_html(sb)
    assert "<script>" not in html_str
    assert "&lt;script&gt;" in html_str


# ---------- render_report (combined) ----------

def test_render_report_writes_all_three_files(tmp_path: Path):
    sb = _scoreboard()
    files = render_report(sb, tmp_path)
    assert (tmp_path / "scoreboard.json").exists()
    assert (tmp_path / "summary.md").exists()
    assert (tmp_path / "report.html").exists()
    assert "scoreboard.json" in files
    assert "summary.md" in files
    assert "report.html" in files


def test_render_report_creates_output_dir(tmp_path: Path):
    sb = _scoreboard()
    target = tmp_path / "nonexistent" / "subdir"
    files = render_report(sb, target)
    assert target.is_dir()
    assert (target / "scoreboard.json").exists()


def test_render_report_files_round_trip():
    """Written JSON is reparseable to the same Scoreboard."""
    import tempfile
    sb = _scoreboard()
    with tempfile.TemporaryDirectory() as tmp:
        files = render_report(sb, Path(tmp))
        loaded = json.loads(files["scoreboard.json"].read_text(encoding="utf-8"))
    assert loaded["benchmark_id"] == sb.benchmark_id
    assert loaded["polaris_wins"] == sb.polaris_wins
