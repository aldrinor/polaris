"""Behavioral/static checks for the Step 1 and Step 7 run recipes."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def _text(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def test_measurement_recipe_generates_before_each_of_three_scores():
    text = _text("baseline_triple.sh")
    assert "for draw in 1 2 3" in text
    assert 'DRAW_DIR="$RUN_ROOT/draw_$draw"' in text
    assert text.index('"$RUNNER"') < text.index("scripts/score_report_race.py")
    assert "independent_draws=" in text


def test_isolation_recipe_has_all_authoritative_arms():
    text = _text("run_generator_isolation.sh")
    for arm in ("current", "k3_prompt", "artifacts", "scope_weighting", "full"):
        assert f"run_arm {arm}" in text
    assert "PG_FACET_EVIDENCE_PACKS=1" in text
    assert "PG_BASKET_SYNTHESIS=1" in text


def test_generality_recipe_requires_all_constraint_classes_and_audits_no_drop():
    text = _text("run_scope_generality.sh")
    assert "hard|soft|mixed|none" in text
    assert "input_count" in text and "output_count" in text
    assert "unconstrained prompt was over-weighted" in text
    assert "expected 3 independent compose summaries" in text


def test_all_recipes_are_valid_bash():
    paths = [
        ROOT / "scripts" / "baseline_triple.sh",
        ROOT / "scripts" / "run_generator_isolation.sh",
        ROOT / "scripts" / "run_scope_generality.sh",
        ROOT / "scripts" / "run_race_7phase.sh",
    ]
    subprocess.run(["bash", "-n", *map(str, paths)], check=True)


def test_race_recipe_enables_retained_coverage_fix_only_in_full_arm():
    text = _text("run_race_7phase.sh")
    full, current = text.split("# BEFORE:", 1)
    assert "PG_COVERAGE_OBLIGATIONS=1" in full
    assert "PG_COVERAGE_OBLIGATIONS=0" in current
