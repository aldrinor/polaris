"""I-beatboth-011 KEYSTONE (#1289) — behavioral test for the rollup span-quality screen wiring.

Offline (no LLM, no network): stubs ``screen_finding_units`` via the injectable ``screen_fn`` to flag a
known chrome unit, and asserts the §-1.3 FLAG-NOT-DROP withhold semantics at the render seam:

  (a) a flagged FAQ/masthead chrome unit is WITHHELD from the rendered Key-Findings rollup while a clean
      finding is KEPT,
  (b) when EVERY finding unit is flagged, the whole block is dropped (no empty heading),
  (c) ``normalize_citations_and_truncation`` collapses orphan-citation glue (``...world.[8].[9]`` ->
      ``...world.[8][9]``, attribution preserved) and flags mid-word truncation.

Run WITHOUT pytest:
    python tests/polaris_graph/test_keystone_rollup_span_quality_screen.py
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _load_sweep_module():
    """Import run_honest_sweep_r3.py (main-guarded, import-safe) and return the module object."""
    spec = importlib.util.spec_from_file_location(
        "rhs_keystone_test", str(ROOT / "scripts" / "run_honest_sweep_r3.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class _FakeVerdict:
    """Mirrors span_quality_gate.SpanQualityVerdict's consumed surface (is_junk / source)."""

    unit_index: int
    is_junk: bool
    junk_class: str
    confidence: float
    offending_span: str
    source: str


def _make_stub_screen(junk_substrings):
    """A stub screen_finding_units: flags a unit is_junk=True iff its text contains any of
    ``junk_substrings`` (simulating the LLM judge flagging a chrome/masthead/FAQ unit). Returns
    a 1:1-aligned verdict list (the real module's contract)."""

    def _stub(units):
        out = []
        for i, unit in enumerate(units):
            is_junk = any(sub in unit for sub in junk_substrings)
            out.append(
                _FakeVerdict(
                    unit_index=i,
                    is_junk=is_junk,
                    junk_class="scraped_heading" if is_junk else "clean",
                    confidence=0.95,
                    offending_span=unit if is_junk else "",
                    source="primary",
                )
            )
        return out

    return _stub


def test_chrome_unit_withheld_clean_kept(mod):
    """(a) a flagged chrome bullet is WITHHELD from the rollup; a clean bullet is KEPT; header +
    italic preamble are untouched."""
    block = (
        "## Key Findings\n\n"
        "_Each finding below is verbatim text carried up from a cited body span._\n\n"
        "- **Background.** Frequently Asked Questions. How does machine learning work.[7]\n"
        "- **Efficacy.** Tirzepatide reduced HbA1c by 2.1 percentage points at 40 weeks.[12]\n"
    )
    stub = _make_stub_screen(["Frequently Asked Questions"])
    out = mod._screen_rollup_finding_units(block, screen_fn=stub)
    assert "Frequently Asked Questions" not in out, "chrome bullet must be WITHHELD from the rollup"
    assert "Tirzepatide reduced HbA1c" in out, "clean finding bullet must be KEPT"
    assert "## Key Findings" in out, "the heading must survive (a clean finding remains)"
    assert "verbatim text carried up" in out, "the italic preamble must survive"
    print("PASS (a) chrome withheld, clean kept, header+preamble untouched")


def test_all_flagged_drops_block(mod):
    """(b) when EVERY finding unit is flagged, the whole block is dropped (no empty heading)."""
    block = (
        "## Key Findings\n\n"
        "_preamble._\n\n"
        "- **A.** Frequently Asked Questions. How does it work.[1]\n"
        "- **B.** Creative Commons license applies to this masthead fragment.[2]\n"
    )
    stub = _make_stub_screen(["Frequently Asked Questions", "Creative Commons"])
    out = mod._screen_rollup_finding_units(block, screen_fn=stub)
    assert out == "", "all-flagged block must be dropped entirely (no empty heading)"
    print("PASS (b) all-flagged block dropped (no empty heading)")


def test_depth_layer_finding_lines_screened(mod):
    """The depth-layer ``**Key Findings|Challenges|Tension** <sentence>`` lines are finding units too;
    a flagged one is withheld while ``### Title`` headers are preserved."""
    block = (
        "## Analytical synthesis\n\n"
        "_preamble._\n\n"
        "### Efficacy\n"
        "\n"
        "**Key Findings** Frequently Asked Questions. About dosing.[3]\n"
        "**Challenges** Evidence on long-term safety remains uncertain.[4]\n"
    )
    stub = _make_stub_screen(["Frequently Asked Questions"])
    out = mod._screen_rollup_finding_units(block, screen_fn=stub)
    assert "Frequently Asked Questions" not in out, "flagged depth finding line must be withheld"
    assert "long-term safety remains uncertain" in out, "clean Challenges line must be kept"
    assert "### Efficacy" in out, "the ### section header must survive"
    print("PASS depth-layer finding lines screened; headers preserved")


def test_disabled_gate_is_no_op(mod):
    """When the stub returns every unit is_junk=False (the flag-OFF / fail-safe shape), the block is
    byte-identical — withhold nothing (§-1.3: never flag on uncertainty)."""
    block = (
        "## Key Findings\n\n"
        "_preamble._\n\n"
        "- **A.** A real finding.[1]\n"
    )
    stub = _make_stub_screen([])  # nothing flagged
    out = mod._screen_rollup_finding_units(block, screen_fn=stub)
    assert out == block, "no flag -> byte-identical (suppress-only no-op)"
    print("PASS disabled/no-flag -> byte-identical no-op")


def test_orphan_glue_collapsed():
    """(c) normalize_citations_and_truncation collapses the inline orphan-citation glue and flags
    mid-word truncation — the deterministic post-render leg of the keystone."""
    from src.polaris_graph.generator.citation_truncation_normalizer import (
        normalize_citations_and_truncation,
    )
    text = (
        "- **Adoption.** AI is deployed across the world.[8].[9][10] The rollout continued.[11]\n"
        "- **Cut.** The aggregate statis.; bstitution rate fell.[5]\n"
    )
    result = normalize_citations_and_truncation(text)
    assert "[8][9][10]" in result.text, "orphan glue '].[' must collapse to '][' (attribution preserved)"
    assert ".[9]" not in result.text or "[8][9]" in result.text, "spurious period between clusters removed"
    assert result.inline_collapsed >= 1, "at least one inline collapse recorded"
    assert result.truncation_flagged >= 1, "mid-word '.;' truncation flagged"
    print(
        f"PASS (c) orphan glue collapsed (inline_collapsed={result.inline_collapsed}) + "
        f"truncation flagged ({result.truncation_flagged})"
    )


def test_abstract_unit_screen_withholds_chrome():
    """The Abstract (front sandwich) rides the SAME authoritative screen via the injectable
    ``unit_screen``: a flagged chrome headline is WITHHELD from the joined Abstract prose while a clean
    headline is KEPT. Uses a real verified-section stub so build_abstract harvests it."""
    import os

    os.environ["PG_SYNTHESIS_ABSTRACT_CONCLUSION"] = "1"  # enable the abstract block for this test
    from src.polaris_graph.generator import abstract_conclusion as ac

    @dataclass
    class _Sec:
        title: str
        verified_text: str
        sentences_verified: int = 2
        is_gap_stub: bool = False
        dropped_due_to_failure: bool = False

    # A clean headline sentence + a chrome FAQ headline, each cited so the harvester lifts it.
    sections = [
        _Sec("Efficacy", "Tirzepatide reduced HbA1c by 2.1 percentage points at 40 weeks.[1] It was well tolerated.[2]"),
        _Sec("Background", "Frequently Asked Questions about the drug class.[3] The class is widely studied.[4]"),
    ]

    def _unit_screen(sentences):
        # withhold any sentence containing the chrome marker (simulating the LLM judge flag)
        return [s for s in sentences if "Frequently Asked Questions" not in s]

    out = ac.build_abstract(sections, unit_screen=_unit_screen)
    assert "Tirzepatide reduced HbA1c" in out, "clean headline must remain in the Abstract"
    assert "Frequently Asked Questions" not in out, "chrome headline must be WITHHELD from the Abstract"
    # Legacy (no screen) keeps the chrome (proves the screen is what removes it, not the harvest filter).
    out_legacy = ac.build_abstract(sections, unit_screen=None)
    assert "Frequently Asked Questions" in out_legacy, "without the screen the blind harvest keeps the chrome (proves the gate fires)"
    print("PASS abstract unit_screen withholds chrome headline (front sandwich rides the authoritative gate)")


def test_real_caller_exists(mod):
    """Confirm screen_finding_units + normalize_citations_and_truncation now have a real caller:
    _screen_rollup_finding_units defaults screen_fn to the production span gate, and the run path
    imports normalize_citations_and_truncation."""
    import inspect

    src = inspect.getsource(mod._screen_rollup_finding_units)
    assert "screen_finding_units" in src, "the helper must call the production span gate by default"
    run_src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "_screen_rollup_finding_units(_key_findings)" in run_src, "KF rollup must be screened on the run path"
    assert "_screen_rollup_finding_units(_depth_layer)" in run_src, "depth rollup must be screened on the run path"
    assert "normalize_citations_and_truncation" in run_src, "the normalizer must be called on the run path"
    assert "unit_screen=_abstract_unit_screen" in run_src, "the abstract/conclusion must receive the span-gate unit_screen"
    assert "screen_finding_units as _sfu" in run_src, "the abstract unit_screen must call the production span gate"
    print("PASS real caller exists for screen_finding_units + normalize_citations_and_truncation (KF + depth + abstract/conclusion)")


if __name__ == "__main__":
    _mod = _load_sweep_module()
    test_chrome_unit_withheld_clean_kept(_mod)
    test_all_flagged_drops_block(_mod)
    test_depth_layer_finding_lines_screened(_mod)
    test_disabled_gate_is_no_op(_mod)
    test_orphan_glue_collapsed()
    test_abstract_unit_screen_withholds_chrome()
    test_real_caller_exists(_mod)
    print("\nALL KEYSTONE ROLLUP SCREEN TESTS PASSED")
