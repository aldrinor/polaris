"""Unit tests for _reduce_filler and _compute_density_metrics from report_assembler."""

import pytest

from src.polaris_graph.synthesis.report_assembler import (
    _compute_density_metrics,
    _reduce_filler,
)


# ---------------------------------------------------------------------------
# _reduce_filler tests
# ---------------------------------------------------------------------------


class TestReduceFiller:
    """Tests for _reduce_filler: caps each filler phrase to 2 occurrences."""

    def test_reduce_filler_keeps_two(self):
        """Text with exactly 2 'Furthermore, ' sentences is unchanged."""
        text = (
            "Furthermore, the results are clear. "
            "Furthermore, the data supports this. "
            "The conclusion is sound."
        )
        result = _reduce_filler(text)
        assert result == text

    def test_reduce_filler_strips_third(self):
        """Third 'Furthermore, ' is stripped and the next word capitalised."""
        text = (
            "Furthermore, alpha. "
            "Furthermore, beta. "
            "Furthermore, gamma is important."
        )
        result = _reduce_filler(text)
        # First two kept, third stripped: "gamma" → "Gamma"
        assert result.count("Furthermore, ") == 2
        assert "Gamma is important" in result
        assert "Furthermore, gamma" not in result

    def test_reduce_filler_strips_multiple_types(self):
        """Mix of 'Moreover, ' (3x) and 'Additionally, ' (3x) — strips 3rd of each."""
        text = (
            "Moreover, one. "
            "Moreover, two. "
            "Moreover, three. "
            "Additionally, four. "
            "Additionally, five. "
            "Additionally, six."
        )
        result = _reduce_filler(text)
        assert result.count("Moreover, ") == 2
        assert result.count("Additionally, ") == 2
        # Third occurrences should be capitalised stripped versions
        assert "Three" in result
        assert "Six" in result

    def test_reduce_filler_empty_string(self):
        """Empty input returns empty output."""
        assert _reduce_filler("") == ""

    def test_reduce_filler_no_fillers(self):
        """Text without any filler phrases is returned unchanged."""
        text = "The sky is blue. Water flows downhill. Plants need sunlight."
        assert _reduce_filler(text) == text

    def test_reduce_filler_preserves_mid_sentence(self):
        """'furthermore' mid-sentence is NOT stripped (only sentence-start matches)."""
        text = "The study furthermore shows growth. Another point furthermore holds."
        result = _reduce_filler(text)
        # Neither occurrence starts with the filler (case-sensitive, sentence start)
        assert result == text


# ---------------------------------------------------------------------------
# _compute_density_metrics tests
# ---------------------------------------------------------------------------


class TestComputeDensityMetrics:
    """Tests for _compute_density_metrics: pure computation, no I/O."""

    def test_density_basic_citations(self):
        """Count citations, sentences, and facts_per_100w correctly."""
        report = "The sky is blue [1]. Water is wet [2]. Fire is hot."
        metrics = _compute_density_metrics(report)

        assert metrics["cited_sentences"] == 2
        assert metrics["total_sentences"] == 3
        # 12 words, 2 citations → 2/12*100 ≈ 16.67
        expected_f100 = (2 / 12) * 100
        assert abs(metrics["facts_per_100w"] - expected_f100) < 0.01
        assert metrics["total_words"] == 12
        # uncited = (3-2)/3
        assert abs(metrics["uncited_sentence_ratio"] - 1 / 3) < 0.01

    def test_density_with_table(self):
        """Markdown table rows are counted."""
        report = (
            "Summary.\n"
            "| Header A | Header B |\n"
            "| --- | --- |\n"
            "| val1 | val2 |\n"
            "| val3 | val4 |\n"
        )
        metrics = _compute_density_metrics(report)
        # 4 lines matching ^\|.+\|$ (header, separator, two data rows)
        assert metrics["table_row_count"] == 4

    def test_density_with_chart(self):
        """Embedded base64 chart image is counted."""
        report = "Results below. ![chart](data:image/png;base64,iVBOR) End."
        metrics = _compute_density_metrics(report)
        assert metrics["chart_count"] == 1

    def test_density_with_key_findings(self):
        """'Key Findings' mention (case-insensitive) is counted."""
        report = "This section covers **Key Findings:** of the study."
        metrics = _compute_density_metrics(report)
        assert metrics["key_findings_count"] == 1

    def test_density_with_fillers(self):
        """Filler phrases are tallied (case-sensitive match on phrase text)."""
        report = "Furthermore, A is true. Moreover, B follows. Plain sentence."
        metrics = _compute_density_metrics(report)
        assert metrics["filler_count"] == 2

    def test_density_empty_report(self):
        """Empty string produces all zeros without divide-by-zero."""
        metrics = _compute_density_metrics("")
        assert metrics["facts_per_100w"] == 0.0
        assert metrics["filler_ratio"] == 0.0
        assert metrics["filler_count"] == 0
        assert metrics["table_row_count"] == 0
        assert metrics["chart_count"] == 0
        assert metrics["key_findings_count"] == 0
        assert metrics["total_words"] == 0
        assert metrics["total_sentences"] == 0
        assert metrics["cited_sentences"] == 0
        # uncited_sentence_ratio: (0-0)/max(0,1) = 0
        assert metrics["uncited_sentence_ratio"] == 0.0
