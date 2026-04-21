"""M-33 tests: section_max_tokens ceiling.

V22 diagnostic showed one of six sections output exactly 1200 tokens,
capped at the `section_max_tokens=1200` override passed by the sweep
caller. The in-module default is 2400 (M-24 fix), so the override was
actively clobbering the upstream ceiling.

Narrative-depth gap vs competitors: V22 total = 1964 words, ChatGPT DR
= 4830 words, Gemini DR = 6054 words. A 1200-token cap limits each
section to roughly ~800-900 words before the generator is forced to
stop, which in turn blocks per-primary-study framing (N + baseline +
comparator + endpoint + timepoint, per M-32 rule #12).

This is the exact same regression class as M-31 (`outline_max_tokens`
override of 800 clobbering module default 2500, causing JSON
truncation). The test is a static guard on the sweep script so a
future edit cannot silently re-introduce the cap.

Generalizable design: the cap is a tokens-per-section ceiling, not a
domain-specific length bound. Nothing in this test references clinical
content.
"""
from __future__ import annotations


class TestSweepSectionMaxTokens:
    """M-33: the sweep caller must not pass a too-small
    section_max_tokens value. 2400 is the in-module default set by
    M-24 for 10-18 sentence targets per section."""

    def test_sweep_script_uses_adequate_section_max_tokens(self) -> None:
        """Static check: the sweep script must not pass a
        section_max_tokens value below the 2400 in-module default.
        V22 diagnostic confirmed hitting exactly 1200 on a SURPASS
        framing section; with 2400 the generator has headroom to emit
        per-trial framing sentences required by M-32 rule #12."""
        import pathlib
        import re

        path = pathlib.Path("scripts/run_honest_sweep_r3.py")
        text = path.read_text(encoding="utf-8")
        matches = re.findall(r"section_max_tokens\s*=\s*(\d+)", text)
        assert matches, "no section_max_tokens= found in sweep script"
        for value in matches:
            assert int(value) >= 2400, (
                f"sweep script passes section_max_tokens={value}, below "
                f"the 2400 in-module default (M-24). V22 hit exactly 1200 "
                f"on one section, capping narrative depth. This is the "
                f"M-33 regression class: script override clobbers upstream "
                f"default."
            )


class TestModuleDefaultUnchanged:
    """Non-regression: the in-module default in
    `multi_section_generator.py` must stay at the M-24 value of 2400.
    If someone lowers the default, the sweep override is no longer
    protective — this test catches that drift."""

    def test_module_default_is_at_least_2400(self) -> None:
        import inspect

        from src.polaris_graph.generator import multi_section_generator

        sig = inspect.signature(
            multi_section_generator.generate_multi_section_report
        )
        param = sig.parameters.get("section_max_tokens")
        assert param is not None, (
            "generate_multi_section_report must accept section_max_tokens"
        )
        default = param.default
        assert isinstance(default, int), (
            f"section_max_tokens default must be an int, got {default!r}"
        )
        assert default >= 2400, (
            f"module default section_max_tokens={default}, below the M-24 "
            f"target of 2400. Lowering this silently defeats the M-33 "
            f"sweep-script guard."
        )
