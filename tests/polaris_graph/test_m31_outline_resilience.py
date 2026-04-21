"""M-31 tests: outline JSON decode resilience.

V19 / V20 both hit `Expecting ',' delimiter` JSON parse failures from
DeepSeek V3.2 outline responses. Two root causes:

1. Truncation at max_tokens=800: the sweep caller was passing 800,
   but a 5-section outline with 12-20 ev_ids per section needs
   ~2000+ tokens to emit valid JSON. Primary fix: raise
   `outline_max_tokens` to 2500 in `scripts/run_honest_sweep_r3.py`
   (matches the in-module default).

2. Trailing commas: DeepSeek V3.2 occasionally emits JSON with
   trailing commas before `]` / `}`. Belt-and-suspenders fix:
   `_parse_outline` now attempts a lenient re-parse that strips
   trailing commas if strict parsing fails.

Generalizable design: the lenient cleanup is a safe transformation
on JSON syntax (well-formed JSON never has trailing commas; stripping
them cannot change meaning). The max_tokens bump is domain-agnostic.
"""
from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import _parse_outline


class TestLenientTrailingCommaRecovery:
    """M-31: lenient re-parse rescues JSON with trailing commas."""

    def test_trailing_comma_in_ev_ids_list(self) -> None:
        """DeepSeek sometimes emits `[\"ev_1\", \"ev_2\",]` — trailing
        comma. Strict json.loads fails; lenient cleanup succeeds."""
        raw = (
            '{"sections": ['
            '{"title": "Efficacy", "focus": "test", '
            '"ev_ids": ["ev_1", "ev_2",]},'
            '{"title": "Safety", "focus": "test", '
            '"ev_ids": ["ev_3", "ev_4",]},'
            '{"title": "Comparative", "focus": "test", '
            '"ev_ids": ["ev_5", "ev_6",]}'
            ']}'
        )
        allowed = {f"ev_{i}" for i in range(1, 7)}
        result = _parse_outline(raw, allowed_ev_ids=allowed)
        # Lenient parse must succeed (not "json_decode_error").
        assert "json_decode_error" not in result.reason_codes, (
            f"lenient trailing-comma recovery failed: {result.reason_codes}"
        )
        assert len(result.plans) == 3

    def test_trailing_comma_in_sections_list(self) -> None:
        """Trailing comma in the outermost `sections` array."""
        raw = (
            '{"sections": ['
            '{"title": "Efficacy", "focus": "t", "ev_ids": ["ev_1", "ev_2"]},'
            '{"title": "Safety", "focus": "t", "ev_ids": ["ev_3", "ev_4"]},'
            ']}'
        )
        allowed = {f"ev_{i}" for i in range(1, 5)}
        result = _parse_outline(raw, allowed_ev_ids=allowed)
        assert "json_decode_error" not in result.reason_codes
        assert len(result.plans) == 2

    def test_well_formed_json_still_parses(self) -> None:
        """Non-regression: valid JSON (no trailing comma) still parses
        without going through the lenient path."""
        raw = (
            '{"sections": ['
            '{"title": "Efficacy", "focus": "t", "ev_ids": ["ev_1", "ev_2"]},'
            '{"title": "Safety", "focus": "t", "ev_ids": ["ev_3", "ev_4"]},'
            '{"title": "Comparative", "focus": "t", "ev_ids": ["ev_5", "ev_6"]}'
            ']}'
        )
        allowed = {f"ev_{i}" for i in range(1, 7)}
        result = _parse_outline(raw, allowed_ev_ids=allowed)
        assert result.ok, f"valid JSON failed: {result.reason_codes}"
        assert len(result.plans) == 3

    def test_truncation_error_still_fails(self) -> None:
        """Truncation (missing comma between two objects) is NOT a
        trailing-comma case and the lenient pass correctly does NOT
        rescue it — this is what the max_tokens bump in the sweep
        caller is supposed to fix, not the parser."""
        raw = (
            '{"sections": ['
            '{"title": "Efficacy", "focus": "t", "ev_ids": ["ev_1"]}'
            '{"title": "Safety", "focus": "t", "ev_ids": ["ev_2"]}'  # missing comma
            ']}'
        )
        allowed = {"ev_1", "ev_2"}
        result = _parse_outline(raw, allowed_ev_ids=allowed)
        assert "json_decode_error" in result.reason_codes

    def test_lenient_pass_preserves_semantics_on_valid_input(self) -> None:
        """Sanity: lenient cleanup must not change the meaning of
        already-valid JSON. Verified by comparing parsed plans."""
        raw = (
            '{"sections": ['
            '{"title": "Efficacy", "focus": "focus A", '
            '"ev_ids": ["ev_1", "ev_2", "ev_3"]},'
            '{"title": "Safety", "focus": "focus B", '
            '"ev_ids": ["ev_4", "ev_5"]},'
            '{"title": "Comparative", "focus": "focus C", '
            '"ev_ids": ["ev_6", "ev_7"]}'
            ']}'
        )
        allowed = {f"ev_{i}" for i in range(1, 8)}
        result = _parse_outline(raw, allowed_ev_ids=allowed)
        titles = [p.title for p in result.plans]
        assert titles == ["Efficacy", "Safety", "Comparative"]
        ev_counts = [len(p.ev_ids) for p in result.plans]
        assert ev_counts == [3, 2, 2]


class TestSweepOutlineMaxTokens:
    """M-31 primary fix: the sweep caller must pass at least the
    in-module default outline_max_tokens. This test is a guard against
    future regressions of the form run_honest_sweep_r3.py used to have
    (passing 800, causing truncation)."""

    def test_sweep_script_uses_adequate_outline_max_tokens(self) -> None:
        """Static check: the sweep script must not pass a too-small
        outline_max_tokens value. 2500+ is the minimum (M-24 default)."""
        import re
        import pathlib

        path = pathlib.Path("scripts/run_honest_sweep_r3.py")
        text = path.read_text(encoding="utf-8")
        matches = re.findall(r"outline_max_tokens\s*=\s*(\d+)", text)
        assert matches, "no outline_max_tokens= found in sweep script"
        for value in matches:
            assert int(value) >= 2500, (
                f"sweep script passes outline_max_tokens={value}, below "
                f"the 2500 minimum required to avoid JSON truncation "
                f"with 5-section outlines and 12-20 ev_ids per section. "
                f"This is the V19/V20 failure mode documented in M-31."
            )
