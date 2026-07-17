"""FIX 1 — scoring-cache purge + scored-artifact assertion in score_report_race.

VERIFIED bug: deepresearch_bench_race.py scores cleaned_data/{model}.jsonl; --force only
bypasses the eval-results cache, never the clean cache; clean_article.py dedups by task-id, so
an aborted stub under a task id permanently shadows the real report. The wrapper must purge the
stale cleaned file BEFORE invoking the harness, and assert the produced cleaned artifact matches
the raw report afterward.

These are offline unit tests: the RACE harness (subprocess.run) is monkeypatched — no network,
no spend.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.score_report_race as srr  # noqa: E402

TASK_ID = "72"
REPORT_TEXT = "This is the real composed report. " * 40  # long enough article


def _write_query_jsonl(drb: Path) -> None:
    (drb / "data/prompt_data").mkdir(parents=True, exist_ok=True)
    task = {"id": int(TASK_ID), "prompt": "the exact benchmark prompt", "language": "en"}
    (drb / "data/prompt_data/query.jsonl").write_text(
        json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")


def _setup(tmp_path: Path, monkeypatch, report_text: str = REPORT_TEXT) -> tuple[Path, Path]:
    """Point the wrapper at a throwaway DRB tree, provide an API key, return (drb, report)."""
    drb = tmp_path / "deep_research_bench"
    monkeypatch.setattr(srr, "DRB", drb)
    _write_query_jsonl(drb)
    (drb / "data/test_data/raw_data").mkdir(parents=True, exist_ok=True)
    (drb / "data/test_data/cleaned_data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    report = tmp_path / "report.md"
    report.write_text(report_text, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "score_report_race.py", "--report", str(report),
        "--task-id", TASK_ID, "--model-name", "polaris_task72",
    ])
    return drb, report


def test_stale_cleaned_file_is_purged_before_scoring(tmp_path, monkeypatch):
    """A pre-existing stale cleaned file must be unlinked before the harness runs."""
    drb, report = _setup(tmp_path, monkeypatch)
    cleaned = drb / "data/test_data/cleaned_data/polaris_task72.jsonl"

    # Poison the cleaned cache with a 1090-char stub under the SAME task id (the shadowing bug).
    cleaned.write_text(
        json.dumps({"id": int(TASK_ID), "prompt": "x", "article": "stale stub " * 100}) + "\n",
        encoding="utf-8")

    observed = {}

    def fake_run(cmd, cwd=None, env=None):
        # At harness-invocation time the stale cache MUST already be gone.
        observed["stale_purged_before_run"] = not cleaned.exists()
        # Simulate the harness re-cleaning: write the correct record.
        cleaned.write_text(
            json.dumps({"id": int(TASK_ID), "prompt": "the exact benchmark prompt",
                        "article": REPORT_TEXT}) + "\n", encoding="utf-8")

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(srr.subprocess, "run", fake_run)

    rc = srr.main()

    assert observed.get("stale_purged_before_run") is True, "stale cleaned cache not purged before harness"
    assert rc == 0


def test_missing_cleaned_artifact_blocks(tmp_path, monkeypatch):
    """If the harness produces no cleaned file, the wrapper must BLOCK (return 3)."""
    drb, report = _setup(tmp_path, monkeypatch)

    def fake_run(cmd, cwd=None, env=None):
        class _R:
            returncode = 0
        return _R()  # produces nothing

    monkeypatch.setattr(srr.subprocess, "run", fake_run)
    assert srr.main() == 3


def test_error_record_poisoning_blocks(tmp_path, monkeypatch):
    """A {'id','error'} failure record (no long article) must BLOCK (return 3)."""
    drb, report = _setup(tmp_path, monkeypatch)
    cleaned = drb / "data/test_data/cleaned_data/polaris_task72.jsonl"

    def fake_run(cmd, cwd=None, env=None):
        cleaned.write_text(
            json.dumps({"id": int(TASK_ID), "error": "clean failed"}) + "\n", encoding="utf-8")

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(srr.subprocess, "run", fake_run)
    assert srr.main() == 3


def test_short_article_blocks(tmp_path, monkeypatch):
    """A cleaned article under 0.5x the report length must BLOCK (return 3)."""
    drb, report = _setup(tmp_path, monkeypatch)
    cleaned = drb / "data/test_data/cleaned_data/polaris_task72.jsonl"

    def fake_run(cmd, cwd=None, env=None):
        cleaned.write_text(
            json.dumps({"id": int(TASK_ID), "prompt": "p", "article": "tiny"}) + "\n",
            encoding="utf-8")

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(srr.subprocess, "run", fake_run)
    assert srr.main() == 3


def test_wrong_id_blocks(tmp_path, monkeypatch):
    """A cleaned record for a different task id must BLOCK (return 3)."""
    drb, report = _setup(tmp_path, monkeypatch)
    cleaned = drb / "data/test_data/cleaned_data/polaris_task72.jsonl"

    def fake_run(cmd, cwd=None, env=None):
        cleaned.write_text(
            json.dumps({"id": 999, "prompt": "p", "article": REPORT_TEXT}) + "\n",
            encoding="utf-8")

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(srr.subprocess, "run", fake_run)
    assert srr.main() == 3


def test_valid_cleaned_artifact_passes(tmp_path, monkeypatch):
    """Exactly-one matching record with a long-enough article returns the harness code (0)."""
    drb, report = _setup(tmp_path, monkeypatch)
    cleaned = drb / "data/test_data/cleaned_data/polaris_task72.jsonl"

    def fake_run(cmd, cwd=None, env=None):
        cleaned.write_text(
            json.dumps({"id": int(TASK_ID), "prompt": "the exact benchmark prompt",
                        "article": REPORT_TEXT}) + "\n", encoding="utf-8")

        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(srr.subprocess, "run", fake_run)
    assert srr.main() == 0
