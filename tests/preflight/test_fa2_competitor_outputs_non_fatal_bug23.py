"""BUG-23 (#1262) regression lock — FA2 competitor-output presence must be NON-FATAL on the live run path.

The original ``check_fa2_competitor_outputs_present`` hard-``assert``-ed that every ChatGPT/Gemini
competitor markdown existed, and ``super_heavy_preflight`` normalizes that AssertionError into a fatal
GateError. drb_72's first attempt therefore CRASHED a $4+ in-flight research run the instant
``gpt_5_5_pro/Q72_ai_labor.md`` was missing in the run shape — a scoring-harness file unrelated to
research quality.

These tests prove the fix:
  * default / ``require=None`` / env OFF  -> a MISSING competitor file does NOT raise (returns the
    missing list); the OLD crash is gone.
  * ``require=True`` (explicit scoring/comparison) OR env ``PG_FA2_REQUIRE_COMPETITOR_OUTPUTS=1`` -> a
    MISSING competitor file STILL raises ``AssertionError`` (strict scoring path preserved).
  * all-present -> empty list, no raise, in BOTH modes.

Offline, deterministic, no spend, no network. We monkeypatch the module ``ROOT`` to a tmp dir so the
real (committed) competitor outputs do not mask the missing-file path.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dr_benchmark import false_alarm_checks as fac  # noqa: E402  (sys.path bootstrap above)

_SYSTEMS = ("gpt_5_5_pro", "gemini_3_1_pro")
_QUESTIONS = (
    "Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
    "Q78_parkinsons_dbs", "Q90_adas_liability",
)


def _materialize_competitor_tree(root: pathlib.Path, *, drop: set[str] | None = None) -> None:
    """Write the 10 competitor markdown files under ``root``, optionally omitting any in ``drop``
    (keyed by ``f'{system}/{question}'``)."""
    drop = drop or set()
    base = root / "outputs" / "dr_benchmark" / "external_outputs"
    for system in _SYSTEMS:
        for q in _QUESTIONS:
            if f"{system}/{q}" in drop:
                continue
            path = base / system / f"{q}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {system} {q}\nnon-empty competitor output\n", encoding="utf-8")


def test_fa2_missing_competitor_is_non_fatal_by_default(tmp_path, monkeypatch):
    """REGRESSION (BUG-23): a missing competitor markdown must NOT raise on the default/live run path.

    This is the exact drb_72 crash condition (``gpt_5_5_pro/Q72_ai_labor.md`` absent). Pre-fix this
    raised AssertionError -> fatal GateError -> aborted paid run. Post-fix it returns the missing list."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.delenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, raising=False)
    _materialize_competitor_tree(tmp_path, drop={"gpt_5_5_pro/Q72_ai_labor"})

    # Must NOT raise — the old AssertionError crash is gone.
    missing = fac.check_fa2_competitor_outputs_present()

    expected = str(tmp_path / "outputs" / "dr_benchmark" / "external_outputs" / "gpt_5_5_pro" / "Q72_ai_labor.md")
    assert missing == [expected], "the single missing competitor file should be reported, not crashed on"


def test_fa2_all_present_returns_empty_and_does_not_raise(tmp_path, monkeypatch):
    """All 10 competitor outputs present -> empty missing-list, no raise, regardless of require mode."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.delenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, raising=False)
    _materialize_competitor_tree(tmp_path)

    assert fac.check_fa2_competitor_outputs_present() == []
    assert fac.check_fa2_competitor_outputs_present(require=True) == []


def test_fa2_empty_file_is_treated_as_missing_but_non_fatal(tmp_path, monkeypatch):
    """A zero-byte competitor output is still 'missing/empty' (the original ``st_size > 0`` semantics),
    and is non-fatal by default."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.delenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, raising=False)
    _materialize_competitor_tree(tmp_path, drop={"gemini_3_1_pro/Q90_adas_liability"})
    empty = tmp_path / "outputs" / "dr_benchmark" / "external_outputs" / "gemini_3_1_pro" / "Q90_adas_liability.md"
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("", encoding="utf-8")  # zero-byte -> counts as missing

    missing = fac.check_fa2_competitor_outputs_present()
    assert missing == [str(empty)]


def test_fa2_require_true_still_raises_on_missing(tmp_path, monkeypatch):
    """Strict scoring/comparison path: ``require=True`` re-arms the original AssertionError so a real
    head-to-head cannot silently proceed without the competitor outputs."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.delenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, raising=False)
    _materialize_competitor_tree(tmp_path, drop={"gpt_5_5_pro/Q72_ai_labor"})

    with pytest.raises(AssertionError, match="competitor output"):
        fac.check_fa2_competitor_outputs_present(require=True)


def test_fa2_env_flag_re_arms_strict_assertion(tmp_path, monkeypatch):
    """The env flag ``PG_FA2_REQUIRE_COMPETITOR_OUTPUTS=1`` re-arms the strict assertion for the no-arg
    call shape (the shape used by ALL_CHECKS / the CI regression lock)."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.setenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, "1")
    _materialize_competitor_tree(tmp_path, drop={"gemini_3_1_pro/Q76_gut_microbiota"})

    with pytest.raises(AssertionError, match="competitor output"):
        fac.check_fa2_competitor_outputs_present()  # no-arg -> consults env flag


@pytest.mark.parametrize("value", ["0", "", "false", "off", "no"])
def test_fa2_env_flag_off_values_stay_non_fatal(tmp_path, monkeypatch, value):
    """Falsey env values keep FA2 non-fatal (default-OFF semantics, LAW VI sane default)."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.setenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, value)
    _materialize_competitor_tree(tmp_path, drop={"gpt_5_5_pro/Q78_parkinsons_dbs"})

    # Must not raise for any falsey value.
    missing = fac.check_fa2_competitor_outputs_present()
    assert len(missing) == 1


def test_fa2_in_all_checks_no_arg_call_does_not_crash_when_missing(tmp_path, monkeypatch):
    """End-to-end wiring: invoking FA2 exactly as ``ALL_CHECKS`` does (no-arg) with a missing file and
    env OFF must NOT raise — this is what stops ``super_heavy_preflight`` from aborting the paid run."""
    monkeypatch.setattr(fac, "ROOT", tmp_path)
    monkeypatch.delenv(fac._FA2_REQUIRE_COMPETITOR_OUTPUTS_ENV, raising=False)
    _materialize_competitor_tree(tmp_path, drop={"gpt_5_5_pro/Q72_ai_labor"})

    fa2 = dict((c.__name__, c) for c in fac.ALL_CHECKS)["check_fa2_competitor_outputs_present"]
    # Mirror the preflight loop body: call the check; it must not raise.
    result = fa2()
    assert isinstance(result, list) and len(result) == 1
