"""M-45 tests: refetch diagnostics with strict contract preservation.

Codex V28 plan pass-2 APPROVED. Instead of assuming the AccessBypass
cascade is missing, M-45 instruments the existing refetch path with
per-URL diagnostics (attempted backend, char count, body type,
eligibility, failure mode). Sweep audits can then tell whether the
cascade actually ran, whether backends returned thin content, or
whether the row was cleanly paywalled.

Strict contract preserved:
- Direct quote ≥100 chars → eligible
- Refetch <100 chars → skip (no statement fallback, no prose fallback)
- Exception → skip with exception_type recorded
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.polaris_graph.retrieval.live_retriever import (
    refetch_for_extraction,
    refetch_for_extraction_with_diagnostics,
)


class TestM45DiagnosticSchema:
    """Every call must return a dict with the 8-key schema."""

    _EXPECTED_KEYS = {
        "url", "attempted", "method", "raw_char_count", "body_type",
        "eligible", "failure_mode", "exception_type",
    }

    def test_empty_url_returns_diagnostic_schema(self) -> None:
        quote, diag = refetch_for_extraction_with_diagnostics("")
        assert quote == ""
        assert set(diag.keys()) == self._EXPECTED_KEYS
        assert diag["attempted"] is False
        assert diag["failure_mode"] == "empty_url"

    def test_fetch_exception_records_exception_type(self) -> None:
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            side_effect=RuntimeError("boom"),
        ):
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://example.com/a"
            )
        assert quote == ""
        assert diag["attempted"] is True
        assert diag["failure_mode"] == "exception"
        assert diag["exception_type"] == "RuntimeError"

    def test_fetch_returns_thin_content_records_thin(self) -> None:
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=("abc", True, "title", "full_text"),  # 3 chars
        ):
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://example.com/a"
            )
        assert quote == ""
        assert diag["failure_mode"] == "thin_content"
        assert diag["raw_char_count"] == 3

    def test_fetch_not_ok_records_fetch_failed(self) -> None:
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=("", False, "", ""),
        ):
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://example.com/a"
            )
        assert quote == ""
        assert diag["failure_mode"] == "fetch_failed"

    def test_fetch_succeeds_returns_eligible(self) -> None:
        fat_content = (
            "SURPASS-2 enrolled 1879 patients with baseline HbA1c 8.28%. "
            "Tirzepatide 15 mg reduced HbA1c by 2.30 pp versus semaglutide "
            "1 mg at week 40. Weight loss was 11.2 kg. Primary endpoint met. "
        ) * 3  # ~500 chars
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=(fat_content, True, "SURPASS-2", "full_text"),
        ):
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://nejm.org/surpass2"
            )
        assert len(quote) >= 100
        assert diag["eligible"] is True
        assert diag["failure_mode"] == ""
        assert diag["body_type"] == "full_text"
        assert diag["raw_char_count"] > 100

    def test_paywall_shell_tagged(self) -> None:
        """Paywall-shell content still gets extracted if ≥100 chars, but
        body_type carries the shell marker. Diagnostic failure_mode
        cleared when eligibility reached."""
        shell_content = (
            "This is a subscription page. Please log in to view the full "
            "text. Abstract: tirzepatide reduced HbA1c by 2.3 pp."
        ) * 3  # ≥100 chars
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=(shell_content, True, "t", "paywall_shell"),
        ):
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://paywalled.example/x"
            )
        # Eligible because content ≥100 chars
        assert diag["eligible"] is True
        # But body_type preserved so downstream audits can filter
        assert diag["body_type"] == "paywall_shell"
        # Failure mode cleared once eligibility reached
        assert diag["failure_mode"] == ""


class TestM45Pass2MethodReporting:
    """M-45 pass-2 (Codex audit HIGH): method reporting via module-
    level telemetry recorder. Pre-pass-2 the method was always "none"
    because _fetch_content discarded result.access_method."""

    def test_method_surfaces_from_fetch_telemetry(self) -> None:
        from src.polaris_graph.retrieval.live_retriever import (
            _m45_record_fetch_telemetry,
            _m45_pop_fetch_telemetry,
        )
        _m45_record_fetch_telemetry(
            "https://nejm.org/x", "crawl4ai", ""
        )
        got = _m45_pop_fetch_telemetry("https://nejm.org/x")
        assert got["method"] == "crawl4ai"

    def test_diag_reads_method_from_fetch_telemetry(self) -> None:
        """When _fetch_content records 'jina', the diagnostic variant
        reads that method instead of leaving it as 'none'."""
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
        ) as mock_fetch:
            # Simulate _fetch_content recording 'jina' telemetry and
            # returning fat content.
            def _fake(url, mc):
                from src.polaris_graph.retrieval.live_retriever import (
                    _m45_record_fetch_telemetry,
                )
                _m45_record_fetch_telemetry(url, "jina", "")
                fat = "X " * 200  # 400 chars
                return fat, True, "t", "full_text"
            mock_fetch.side_effect = _fake
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://nejm.org/x"
            )
        assert diag["method"] == "jina"
        assert diag["eligible"] is True

    def test_diag_reads_timeout_from_fetch_telemetry(self) -> None:
        """When AccessBypass times out, _fetch_content records
        failure_reason containing 'timeout'. Diagnostic variant
        surfaces that as failure_mode='timeout'."""
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
        ) as mock_fetch:
            def _fake(url, mc):
                from src.polaris_graph.retrieval.live_retriever import (
                    _m45_record_fetch_telemetry,
                )
                _m45_record_fetch_telemetry(
                    url, "httpx_naive",
                    "access_bypass_timeout_90s",
                )
                return "", False, "", ""
            mock_fetch.side_effect = _fake
            quote, diag = refetch_for_extraction_with_diagnostics(
                "https://paywalled.example/x"
            )
        # failure_mode upgraded from fetch_failed to timeout
        assert diag["failure_mode"] == "timeout"
        assert diag["method"] == "httpx_naive"


class TestM45Pass2MissingUrlDiagnostic:
    """M-45 pass-2 (Codex audit medium #2): primary rows with thin
    direct_quote and no refetchable URL must still appear in the
    sink with failure_mode='missing_url'."""

    def test_missing_url_creates_diagnostic_entry(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )
        selected_rows = [
            {
                "evidence_id": "ev_s2",
                "title": "SURPASS-2 primary publication",
                "direct_quote": "thin",  # <100 chars
                # No source_url, no url → unrefetchable
            },
        ]
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        sink: list[dict] = []
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected_rows,
            primary_trial_anchors=["SURPASS-2"],
            bibliography=biblio,
            refetch_fn=lambda u, mc: "",
            refetch_diagnostics_sink=sink,
        )
        assert len(sink) == 1
        assert sink[0]["failure_mode"] == "missing_url"
        assert sink[0]["anchor"] == "SURPASS-2"
        assert sink[0]["evidence_id"] == "ev_s2"
        assert sink[0]["attempted"] is False


class TestM45BackwardsCompat:
    """`refetch_for_extraction` (1-value variant) must continue to work."""

    def test_legacy_variant_returns_string_only(self) -> None:
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=("short", True, "t", ""),
        ):
            result = refetch_for_extraction("https://example.com/a")
        # Thin → empty string
        assert result == ""

    def test_legacy_variant_eligible_returns_quote(self) -> None:
        fat = "SURPASS-2 enrolled 1879 patients at baseline HbA1c 8.28%. " * 5
        with patch(
            "src.polaris_graph.retrieval.live_retriever._fetch_content",
            return_value=(fat, True, "t", "full_text"),
        ):
            result = refetch_for_extraction("https://nejm.org/x")
        assert len(result) >= 100


class TestM45BuilderDiagnosticsSink:
    """The M-42b trial-table builder now accepts
    `refetch_diagnostics_sink: list` and appends one entry per URL
    it attempts to refetch."""

    def test_sink_receives_entry_per_refetch(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )

        # Two primary-trial rows with thin direct_quotes; builder will
        # call refetch for each. Mock refetch to return (quote, diag).
        selected_rows = [
            {
                "evidence_id": "ev_s2",
                "source_url": "https://nejm.org/surpass2",
                "title": "SURPASS-2: Tirzepatide vs semaglutide",
                "direct_quote": "thin",  # <100 chars → triggers refetch
            },
            {
                "evidence_id": "ev_s1",
                "source_url": "https://lancet.com/surpass1",
                "title": "SURPASS-1: Tirzepatide monotherapy",
                "direct_quote": "tiny",  # <100 chars → triggers refetch
            },
        ]
        biblio = [
            {"num": 1, "evidence_id": "ev_s2"},
            {"num": 2, "evidence_id": "ev_s1"},
        ]

        # Patch the diagnostic variant import target (imported inside
        # the builder when sink is provided). Use a mock that returns
        # thin content so both rows are extraction-ineligible but the
        # sink still receives entries.
        def _mock_diag(url: str, max_chars: int = 2000):
            return "", {
                "url": url[:200],
                "attempted": True,
                "method": "crawl4ai",
                "raw_char_count": 50,
                "body_type": "paywall_shell",
                "eligible": False,
                "failure_mode": "thin_content",
                "exception_type": "",
            }

        sink: list[dict] = []
        with patch(
            "src.polaris_graph.retrieval.live_retriever."
            "refetch_for_extraction_with_diagnostics",
            side_effect=_mock_diag,
        ):
            table, timeline = build_trial_summary_and_timeline_from_evidence(
                selected_rows=selected_rows,
                primary_trial_anchors=["SURPASS-2", "SURPASS-1"],
                bibliography=biblio,
                refetch_fn=lambda url, mc: "",  # legacy path unused
                refetch_diagnostics_sink=sink,
            )
        # Sink received one entry per anchor refetch attempt
        assert len(sink) == 2, f"sink should have 2 entries: {sink}"
        # Each entry carries anchor + evidence_id
        anchors_in_sink = {e.get("anchor") for e in sink}
        assert anchors_in_sink == {"SURPASS-2", "SURPASS-1"}
        ev_ids_in_sink = {e.get("evidence_id") for e in sink}
        assert ev_ids_in_sink == {"ev_s2", "ev_s1"}
        # All entries have the diagnostic schema
        for entry in sink:
            assert "failure_mode" in entry
            assert "raw_char_count" in entry

    def test_sink_none_means_no_diagnostic_route(self) -> None:
        """When sink is None (legacy caller), builder uses the non-
        diagnostic refetch_fn path — no diagnostic imports, no sink
        entries."""
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )

        call_count = [0]

        def _legacy_refetch(url: str, max_chars: int = 2000) -> str:
            call_count[0] += 1
            return ""  # thin → skip

        selected_rows = [
            {
                "evidence_id": "ev_s2",
                "source_url": "https://nejm.org/s2",
                "title": "SURPASS-2 primary",
                "direct_quote": "thin",
            },
        ]
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        table, timeline = build_trial_summary_and_timeline_from_evidence(
            selected_rows=selected_rows,
            primary_trial_anchors=["SURPASS-2"],
            bibliography=biblio,
            refetch_fn=_legacy_refetch,
            refetch_diagnostics_sink=None,
        )
        # Legacy path was used
        assert call_count[0] == 1

    def test_exception_in_refetch_still_recorded_in_sink(self) -> None:
        from src.polaris_graph.generator.multi_section_generator import (
            build_trial_summary_and_timeline_from_evidence,
        )

        def _broken_refetch(url: str, max_chars: int = 2000):
            raise ValueError("simulated")

        selected_rows = [
            {
                "evidence_id": "ev_s2",
                "source_url": "https://x/y",
                "title": "SURPASS-2 primary",
                "direct_quote": "short",
            },
        ]
        biblio = [{"num": 1, "evidence_id": "ev_s2"}]
        sink: list[dict] = []
        with patch(
            "src.polaris_graph.retrieval.live_retriever."
            "refetch_for_extraction_with_diagnostics",
            side_effect=_broken_refetch,
        ):
            table, timeline = build_trial_summary_and_timeline_from_evidence(
                selected_rows=selected_rows,
                primary_trial_anchors=["SURPASS-2"],
                bibliography=biblio,
                refetch_fn=lambda u, mc: "",
                refetch_diagnostics_sink=sink,
            )
        assert len(sink) == 1
        assert sink[0]["failure_mode"] == "builder_exception"
        assert sink[0]["exception_type"] == "ValueError"
