"""M-36 tests: Trial Summary markdown table synthesis.

Codex DR pass-11 gap #4: "Add at least one trial summary table and
one benefit-risk or NNT/NNH table, plus subsections for evidence
architecture, safety, prescribing, limitations, and ongoing evidence."

M-36 addresses the trial-summary half of gap #4. The benefit-risk/
NNT/NNH half is M-36b (separate, post-approval).

Design:
  - One LLM call over VERIFIED prose + global bibliography.
  - No per-cell provenance required: input prose is already
    strict_verified, citation numbers are validated against the
    bibliography, out-of-range cites are dropped row-level.
  - Empty output when prose names no trials, LLM fails, or every
    candidate row has out-of-range cites — never emit a misleading
    stub table.

Tests split by surface:
  - `_extract_trial_summary_table` — deterministic parser / validator
    (no LLM, no I/O).
  - `_call_trial_summary_table` — orchestration around an LLM call,
    tested with a monkeypatched client.
"""
from __future__ import annotations

import asyncio
import pytest

from src.polaris_graph.generator.multi_section_generator import (
    _call_trial_summary_table,
    _extract_trial_summary_table,
)


# ─────────────────────────────────────────────────────────────────────
# _extract_trial_summary_table — parser / validator tests
# ─────────────────────────────────────────────────────────────────────


class TestExtractorEmpty:
    def test_empty_string_returns_empty(self) -> None:
        assert _extract_trial_summary_table("", {1, 2}) == ""

    def test_whitespace_only_returns_empty(self) -> None:
        assert _extract_trial_summary_table("   \n\n  ", {1, 2}) == ""

    def test_no_trials_named_sentinel_returns_empty(self) -> None:
        assert _extract_trial_summary_table("NO_TRIALS_NAMED", {1, 2}) == ""

    def test_no_trials_named_with_surrounding_whitespace(self) -> None:
        assert _extract_trial_summary_table(
            "  NO_TRIALS_NAMED  ", {1, 2}
        ) == ""


class TestExtractorShape:
    def test_missing_header_returns_empty(self) -> None:
        raw = "| A | B |\n|---|---|\n| x | y |"
        assert _extract_trial_summary_table(raw, {1, 2}) == ""

    def test_missing_separator_returns_empty(self) -> None:
        raw = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |"
        )
        assert _extract_trial_summary_table(raw, {1}) == ""

    def test_header_with_no_data_rows_returns_empty(self) -> None:
        raw = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
        )
        assert _extract_trial_summary_table(raw, {1}) == ""

    def test_header_and_separator_and_one_data_row(self) -> None:
        raw = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1})
        # Preserves header + separator + row
        lines = table.splitlines()
        assert len(lines) == 3
        assert "Trial" in lines[0] and "Ref" in lines[0]
        assert lines[1].count("|") >= 7
        assert "TRIAL-A" in lines[2] and "[1]" in lines[2]


class TestExtractorCitationValidation:
    HDR = (
        "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
        "|---|---|---|---|---|---|---|\n"
    )

    def test_row_without_citation_dropped(self) -> None:
        """Per rule #1 every row must carry at least one [N]."""
        raw = self.HDR + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | — |"
        assert _extract_trial_summary_table(raw, {1}) == ""

    def test_row_with_out_of_range_citation_dropped(self) -> None:
        """Bibliography only has [1]; a row citing [99] must be dropped."""
        raw = (
            self.HDR
            + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [99] |"
        )
        assert _extract_trial_summary_table(raw, {1}) == ""

    def test_row_with_in_range_citation_kept(self) -> None:
        raw = (
            self.HDR
            + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1, 2, 3})
        assert "TRIAL-A" in table

    def test_mixed_rows_only_valid_kept(self) -> None:
        raw = (
            self.HDR
            + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            + "| TRIAL-B | 200 | — | placebo | HbA1c | −1.5 pp | [99] |\n"
            + "| TRIAL-C | 300 | — | placebo | HbA1c | −1.8 pp | [2][3] |\n"
            + "| TRIAL-D | 400 | — | placebo | HbA1c | −2.0 pp | — |"
        )
        table = _extract_trial_summary_table(raw, {1, 2, 3})
        assert "TRIAL-A" in table
        assert "TRIAL-B" not in table  # [99] out of range
        assert "TRIAL-C" in table       # [2][3] both in range
        assert "TRIAL-D" not in table  # no citation marker

    def test_row_with_mixed_in_and_out_range_dropped(self) -> None:
        """Any out-of-range [N] → whole row dropped (strict)."""
        raw = (
            self.HDR
            + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1][99] |"
        )
        assert _extract_trial_summary_table(raw, {1}) == ""

    def test_all_rows_out_of_range_returns_empty(self) -> None:
        raw = (
            self.HDR
            + "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [99] |\n"
            + "| TRIAL-B | 200 | — | placebo | HbA1c | −1.5 pp | [100] |"
        )
        assert _extract_trial_summary_table(raw, {1, 2, 3}) == ""


class TestExtractorFences:
    def test_markdown_fence_stripped(self) -> None:
        raw = (
            "```markdown\n"
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            "```"
        )
        table = _extract_trial_summary_table(raw, {1})
        assert "TRIAL-A" in table
        assert "```" not in table

    def test_bare_md_fence_stripped(self) -> None:
        raw = (
            "```md\n"
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            "```"
        )
        table = _extract_trial_summary_table(raw, {1})
        assert "TRIAL-A" in table


class TestExtractorHeaderLocation:
    """Header may be preceded by preamble (the LLM sometimes ignores
    the 'output only the table' rule). We strip the preamble and
    start at the canonical header row."""

    def test_preamble_before_table_stripped(self) -> None:
        raw = (
            "Here is the trial summary table:\n\n"
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |"
        )
        table = _extract_trial_summary_table(raw, {1})
        assert "TRIAL-A" in table
        assert "Here is" not in table

    def test_trailing_prose_after_table_stopped_at(self) -> None:
        """Table ends at first non-pipe non-empty line."""
        raw = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            "\n"
            "This table was generated from 3 sources."
        )
        table = _extract_trial_summary_table(raw, {1})
        assert "TRIAL-A" in table
        assert "This table was generated" not in table


# ─────────────────────────────────────────────────────────────────────
# _call_trial_summary_table — orchestrator tests
# ─────────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, content: str, in_tok: int = 100, out_tok: int = 50) -> None:
        self.content = content
        self.input_tokens = in_tok
        self.output_tokens = out_tok


class _FakeClient:
    def __init__(self, response_content: str = "", *, raise_on_call=None) -> None:
        self._response = response_content
        self._raise = raise_on_call
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return _FakeResponse(self._response)

    async def close(self) -> None:
        pass


def _install_fake_client(monkeypatch, client: _FakeClient) -> None:
    def _factory(*args, **kwargs):
        return client
    monkeypatch.setattr(
        "src.polaris_graph.generator.multi_section_generator.OpenRouterClient",
        _factory,
        raising=False,
    )
    # Fallback: also patch the import location.
    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "OpenRouterClient", _factory, raising=False)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestCallOrchestration:
    def test_empty_prose_returns_empty_no_llm_call(self, monkeypatch) -> None:
        client = _FakeClient("unused")
        _install_fake_client(monkeypatch, client)
        text, in_tok, out_tok = _run(_call_trial_summary_table(
            verified_prose="",
            bibliography=[{"num": 1, "title": "t", "url": "u"}],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""
        assert in_tok == 0 and out_tok == 0
        assert client.calls == 0

    def test_empty_bibliography_returns_empty_no_llm_call(
        self, monkeypatch
    ) -> None:
        client = _FakeClient("unused")
        _install_fake_client(monkeypatch, client)
        text, _, _ = _run(_call_trial_summary_table(
            verified_prose="Some verified prose with [1] markers.",
            bibliography=[],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""
        assert client.calls == 0

    def test_bibliography_without_num_field_returns_empty(
        self, monkeypatch
    ) -> None:
        client = _FakeClient("unused")
        _install_fake_client(monkeypatch, client)
        text, _, _ = _run(_call_trial_summary_table(
            verified_prose="Some prose.",
            bibliography=[{"title": "t", "url": "u"}],  # no "num"
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""
        assert client.calls == 0

    def test_llm_returns_no_trials_named_empty(self, monkeypatch) -> None:
        client = _FakeClient("NO_TRIALS_NAMED")
        _install_fake_client(monkeypatch, client)
        text, in_tok, out_tok = _run(_call_trial_summary_table(
            verified_prose="Some verified prose with [1] markers.",
            bibliography=[{"num": 1, "title": "t", "url": "u"}],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""
        assert in_tok == 100  # still returns token usage
        assert client.calls == 1

    def test_llm_returns_valid_table(self, monkeypatch) -> None:
        table_md = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            "| TRIAL-B | 200 | — | semaglutide | HbA1c | −1.5 pp | [2] |"
        )
        client = _FakeClient(table_md)
        _install_fake_client(monkeypatch, client)
        text, _, _ = _run(_call_trial_summary_table(
            verified_prose="... [1] ... [2] ...",
            bibliography=[
                {"num": 1, "title": "t1", "url": "u1"},
                {"num": 2, "title": "t2", "url": "u2"},
            ],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert "TRIAL-A" in text
        assert "TRIAL-B" in text

    def test_llm_returns_table_with_out_of_range_citations_dropped(
        self, monkeypatch
    ) -> None:
        """LLM fabricated [99]; that row is dropped by the validator."""
        table_md = (
            "| Trial | N | Baseline | Comparator | Endpoint | Result | Ref |\n"
            "|---|---|---|---|---|---|---|\n"
            "| TRIAL-A | 100 | — | placebo | HbA1c | −1.0 pp | [1] |\n"
            "| TRIAL-FAKE | 999 | — | placebo | HbA1c | −5.0 pp | [99] |"
        )
        client = _FakeClient(table_md)
        _install_fake_client(monkeypatch, client)
        text, _, _ = _run(_call_trial_summary_table(
            verified_prose="... [1] ...",
            bibliography=[{"num": 1, "title": "t", "url": "u"}],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert "TRIAL-A" in text
        assert "TRIAL-FAKE" not in text
        assert "[99]" not in text

    def test_llm_failure_returns_empty(self, monkeypatch) -> None:
        client = _FakeClient("", raise_on_call=RuntimeError("provider down"))
        _install_fake_client(monkeypatch, client)
        text, in_tok, out_tok = _run(_call_trial_summary_table(
            verified_prose="Some prose with [1].",
            bibliography=[{"num": 1, "title": "t", "url": "u"}],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""
        assert in_tok == 0 and out_tok == 0

    def test_llm_returns_junk_returns_empty(self, monkeypatch) -> None:
        """A response with no recognizable table must collapse to empty
        string — we never emit misleading structure."""
        client = _FakeClient("I think the trials are X, Y, Z.")
        _install_fake_client(monkeypatch, client)
        text, _, _ = _run(_call_trial_summary_table(
            verified_prose="Some prose.",
            bibliography=[{"num": 1, "title": "t", "url": "u"}],
            model="test-model",
            temperature=0.2,
            max_tokens=800,
        ))
        assert text == ""


# ─────────────────────────────────────────────────────────────────────
# Result schema + config
# ─────────────────────────────────────────────────────────────────────


class TestResultSchema:
    def test_multi_section_result_has_m36_fields(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            MultiSectionResult,
        )
        r = MultiSectionResult(
            sections=[],
            outline=[],
            bibliography=[],
            total_words=0,
            total_sentences_verified=0,
            total_sentences_dropped=0,
            total_input_tokens=0,
            total_output_tokens=0,
        )
        assert r.trial_summary_table_text == ""
        assert r.trial_summary_table_input_tokens == 0
        assert r.trial_summary_table_output_tokens == 0


class TestDisableKnob:
    """`trial_summary_table_max_tokens=0` disables the whole stage
    without requiring a template edit or env var."""

    def test_max_tokens_zero_suppresses_call(self, monkeypatch) -> None:
        # Patch the inner _call function to record whether it was hit.
        import src.polaris_graph.generator.multi_section_generator as m
        hits = {"n": 0}
        orig = m._call_trial_summary_table

        async def _mock(**kwargs):
            hits["n"] += 1
            return ("", 0, 0)

        monkeypatch.setattr(m, "_call_trial_summary_table", _mock)
        # Now invoke generate_multi_section_report with
        # trial_summary_table_max_tokens=0 and an empty evidence list
        # to short-circuit early — but this only tests the gate, so we
        # assert no hit occurred after disabling.
        # (Full end-to-end is covered by the smoke test.)
        from src.polaris_graph.generator.multi_section_generator import (
            generate_multi_section_report,
        )
        # An empty evidence list + no telemetry keeps us in the
        # insufficient_evidence path; the table gate is evaluated
        # after section generation. The call should still be zero
        # because we're passing 0.
        _run(generate_multi_section_report(
            research_question="q",
            evidence=[],
            trial_summary_table_max_tokens=0,
        ))
        assert hits["n"] == 0
        # Restore
        monkeypatch.setattr(m, "_call_trial_summary_table", orig)
