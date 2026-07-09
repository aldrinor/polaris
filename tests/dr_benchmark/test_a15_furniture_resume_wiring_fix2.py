"""I-deepfix-001 FIX-2 (B1 RESUME WIRING) — furniture-density degraded detection on the A15 resume path.

On ``--resume`` the A15 degraded-detector in ``scripts/run_honest_sweep_r3.py`` decides which banked
rows get re-fetched. Wave-2 B1 built the furniture-density screen but only on the fresh extraction
path, so a banked furniture-dominant row (a degraded big-PDF extraction: masthead / nav / DOI /
license welded together) survived the resume untouched (B1 was blind on banked rows). FIX-2 extends
the A15 degraded predicate: when ``PG_FURNITURE_DENSITY_SCREEN=1`` a row whose banked grounding is
furniture-DOMINANT is ALSO flagged degraded so the A15 cascade re-fetches it with the fixed mineru
(B2) and recovers real content. Gated STRICTLY on the default-OFF flag => OFF => no extra rows
flagged => byte-identical.

This tests the ACTUAL module-level helper ``_a15_row_furniture_degraded`` that the A15 predicate
calls. ``run_honest_sweep_r3.py`` cannot be imported offline (its top pulls the live evaluator /
judge stack), so the pure, self-contained helper is ast-extracted from source and exec'd in
isolation — the identical function object, tested against the REAL ``shell_detector`` B1 predicate
and REAL furniture / prose bodies (no GPU / LLM / network).

GREEN = ``python -m pytest tests/polaris_graph/test_a15_furniture_resume_wiring_fix2.py -q``.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.polaris_graph.retrieval import shell_detector as sd

_ROOT = Path(__file__).resolve().parents[2]
_SWEEP = _ROOT / "scripts" / "run_honest_sweep_r3.py"
_HELPER_NAME = "_a15_row_furniture_degraded"


def _load_real_helper():
    """ast-extract the module-level ``_a15_row_furniture_degraded`` from the sweep script and exec
    its verbatim source in an isolated namespace. It is pure + self-contained (params + builtins
    only), so the exec'd object is behaviourally identical to the one the A15 predicate calls —
    without triggering the script's heavy top-level imports."""
    text = _SWEEP.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == _HELPER_NAME:
            segment = ast.get_source_segment(text, node)
            assert segment, "could not extract helper source segment"
            ns: dict = {}
            exec(compile(segment, str(_SWEEP), "exec"), ns)  # noqa: S102 — trusted first-party source
            return ns[_HELPER_NAME]
    raise AssertionError(f"{_HELPER_NAME} not found at module level in {_SWEEP}")


_helper = _load_real_helper()


# ── real furniture / prose bodies (long enough to clear the min-body guard) ───────────────────
def _furniture_body() -> str:
    lines = [
        "## Abstract", "10.1093/qje/qjae044", "## Author Listed", "ISSN 0033-5533",
        "doi:10.1000/xyz", "## References", "## Acknowledgements", "## Introduction",
        "## Methods", "## Results", "## Discussion", "## Conclusion",
        "Terms of Use", "Privacy Policy", "## Supplementary Material", "## Funding",
    ]
    return "\n\n".join(lines * 6)


def _clean_body() -> str:
    unit = (
        "One more robot per thousand workers in the United States reduces the "
        "employment-to-population ratio by 0.2 percentage points and wages by 0.42 "
        "percent, according to the study of local labor markets across many regions."
    )
    return "\n\n".join(unit for _ in range(8))


# ── sanity: the reused B1 predicate really discriminates furniture vs prose (offline) ─────────
def test_reused_b1_predicate_discriminates():
    assert sd.is_furniture_dominant(_furniture_body()) is True
    assert sd.is_furniture_dominant(_clean_body()) is False


# ── the flag the wiring surfaces as screen_on defaults OFF ────────────────────────────────────
def test_furniture_screen_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PG_FURNITURE_DENSITY_SCREEN", raising=False)
    assert sd.furniture_density_screen_enabled() is False


def test_furniture_screen_flag_on_via_env(monkeypatch):
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    assert sd.furniture_density_screen_enabled() is True


# ── the real helper: screen ON => furniture row flagged, clean row not ────────────────────────
def test_furniture_row_flagged_when_screen_on():
    # a banked furniture-dominant row => degraded => would be re-fetched.
    assert _helper(_furniture_body(), screen_on=True, is_dominant_fn=sd.is_furniture_dominant) is True


def test_clean_row_not_flagged_when_screen_on():
    # a real-content banked row => NOT degraded by the furniture term.
    assert _helper(_clean_body(), screen_on=True, is_dominant_fn=sd.is_furniture_dominant) is False


# ── OFF => byte-identical: the furniture term never contributes, for ANY body ─────────────────
def test_screen_off_never_flags_furniture_row():
    assert _helper(_furniture_body(), screen_on=False, is_dominant_fn=sd.is_furniture_dominant) is False


def test_screen_off_never_flags_clean_row():
    assert _helper(_clean_body(), screen_on=False, is_dominant_fn=sd.is_furniture_dominant) is False


def test_none_predicate_is_false():
    # import failed upstream (fail-open) => screen contributes nothing even if flag is on.
    assert _helper(_furniture_body(), screen_on=True, is_dominant_fn=None) is False


def test_predicate_error_is_fail_open_false():
    def _boom(_body):  # noqa: ANN001
        raise RuntimeError("predicate blew up")

    assert _helper(_furniture_body(), screen_on=True, is_dominant_fn=_boom) is False


# ── the composed A15 _is_degraded OR is byte-identical OFF and additive ON ─────────────────────
def _is_degraded(row: dict, *, screen_on: bool) -> bool:
    """Mirror of the A15 predicate composition in run_honest_sweep_r3.py, using the REAL helper for
    the new furniture term (base flags unchanged). Base flags all False + non-starved grounding =>
    the ONLY thing that can flip degraded is the furniture term."""
    grounding = row.get("direct_quote") or row.get("statement") or ""
    return (
        bool(row.get("content_starved"))
        or bool(row.get("fetch_failed"))
        or bool(row.get("landing_page"))
        # base is_content_starved on a long body is False; the furniture term is the new signal.
        or _helper(grounding, screen_on=screen_on, is_dominant_fn=sd.is_furniture_dominant)
    )


def test_composed_predicate_flags_furniture_row_only_when_on():
    furniture_row = {"direct_quote": _furniture_body()}
    clean_row = {"direct_quote": _clean_body()}
    # OFF: neither row gains a degraded flag (byte-identical to the pre-FIX-2 base OR).
    assert _is_degraded(furniture_row, screen_on=False) is False
    assert _is_degraded(clean_row, screen_on=False) is False
    # ON: the furniture row is flagged (would be re-fetched); the clean row is not.
    assert _is_degraded(furniture_row, screen_on=True) is True
    assert _is_degraded(clean_row, screen_on=True) is False
