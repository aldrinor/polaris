"""I-rdy-018 (#514) — wiring tests for the OpenRouter rehearsal runner.

Subprocess-drives scripts/v6/run_rehearsal.py (harness style of
test_scripts_v6_handover.py) exercising `check-models` and `run --dry-run`
**without any LLM call or spend**: every subprocess runs with a clean `env`
that explicitly omits OPENROUTER_API_KEY, and with cwd set to a tmp dir so
no repo-root `.env` can be implicitly loaded.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from polaris_v6.queue.actors import TEMPLATE_TO_SCOPE_DOMAIN

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "v6" / "run_rehearsal.py"
PROMPTS = REPO_ROOT / "tests" / "v6" / "fixtures" / "rehearsal_prompts.yaml"


def _run(*args: str, cwd: Path, run_db: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the rehearsal CLI with OPENROUTER_API_KEY stripped from the env."""
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    if run_db is not None:
        env["POLARIS_V6_RUN_DB"] = str(run_db)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_models_fails_loud_without_key(tmp_path):
    result = _run("check-models", cwd=tmp_path)
    assert result.returncode != 0
    assert "OPENROUTER_API_KEY" in result.stderr


def test_run_dry_run_validates_wiring(tmp_path):
    result = _run("run", "--dry-run", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    # Every canonical template is planned.
    for template in TEMPLATE_TO_SCOPE_DOMAIN:
        assert f"- {template}:" in result.stdout, f"{template} missing from dry-run plan"
    assert "OPENROUTER_API_KEY: ABSENT" in result.stdout
    assert "DRY RUN" in result.stdout


def test_dry_run_makes_no_billed_call(tmp_path):
    # Point the run store at a path that does not exist; a dry run must not
    # create it (no insert_run, no LLM call, no spend).
    run_db = tmp_path / "state" / "v6_runs.sqlite"
    result = _run("run", "--dry-run", cwd=tmp_path, run_db=run_db)
    assert result.returncode == 0, result.stderr
    assert not run_db.exists(), "dry run wrote to the run store — it must not"


def test_rehearsal_prompts_cover_all_templates():
    data = yaml.safe_load(PROMPTS.read_text(encoding="utf-8"))
    templates = sorted(p["template"] for p in data["prompts"])
    assert templates == sorted(TEMPLATE_TO_SCOPE_DOMAIN), (
        "rehearsal_prompts.yaml must cover exactly the 8 canonical templates"
    )
    # Each question is non-empty.
    for entry in data["prompts"]:
        assert entry["question"].strip(), f"empty question for {entry['template']}"
