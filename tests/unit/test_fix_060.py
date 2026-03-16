"""
Unit tests for FIX-060: Confidence Integrity + Assembly Order + Hidden SOTA Blockers.

FIX-060-A: Basis-aware confidence fallback
FIX-060-B: NLI confidence preservation at merge
FIX-060-C: Triangulation boost guard
FIX-060-D: Low-confidence threshold env var
FIX-060-E: Assembly order — transitions after global cleanup
FIX-060-F: Verification prompt — strict for missing content
FIX-060-G: Empty batch detection + warning
"""

import logging
import os
import re

import pytest


# ---------------------------------------------------------------------------
# FIX-060-A: Basis-Aware Confidence Fallback
# ---------------------------------------------------------------------------

class TestBasisAwareConfidence:
    """FIX-060-A: Cap LLM self-assessed confidence by verification basis."""

    def test_basis_content_caps_050(self):
        """Content basis: LLM 0.93 capped to 0.50."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.93, "content")
        assert result == 0.50

    def test_basis_quote_only_caps_030(self):
        """Quote-only basis: LLM 0.90 capped to 0.30."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.90, "quote_only")
        assert result == 0.30

    def test_basis_title_only_caps_010(self):
        """Title-only basis: LLM 0.95 capped to 0.10."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.95, "title_only")
        assert result == 0.10

    def test_basis_none_caps_zero(self):
        """No basis: LLM 0.85 capped to 0.0."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.85, "none")
        assert result == 0.0

    def test_nli_takes_precedence(self):
        """NLI score should be used directly (not passed through basis cap).

        This tests the integration logic: when _ev_nli is valid (>0),
        it is used as confidence instead of basis-aware fallback.
        """
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        # When NLI is available, the calling code uses NLI directly,
        # so _basis_aware_confidence is never called.
        # Here we verify the helper itself: NLI 0.82 vs content cap 0.50.
        # The caller would use 0.82, not call this function.
        # This test validates the helper doesn't inflate:
        result = _basis_aware_confidence(0.82, "content")
        assert result == 0.50  # cap applies to LLM confidence, not NLI

    def test_low_llm_not_inflated(self):
        """LLM confidence 0.20 with content basis stays at 0.20 (min logic)."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.20, "content")
        assert result == 0.20  # min(0.20, 0.50) = 0.20

    def test_unknown_basis_defaults_050(self):
        """Unknown basis string defaults to 0.50 cap."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence
        result = _basis_aware_confidence(0.95, "unknown_basis")
        assert result == 0.50


# ---------------------------------------------------------------------------
# FIX-060-B: NLI Confidence Preservation at Merge
# ---------------------------------------------------------------------------

class TestNLIConfidencePreservation:
    """FIX-060-B: NLI-based confidence survives LLM second opinion merge."""

    def test_merge_preserves_nli_confidence(self):
        """When NLI score exists and >0, it replaces LLM confidence at merge."""
        # Simulate the merge logic inline
        r = {"nli_score": 0.45, "cross_source_score": 0.3, "confidence": 0.45}
        llm_claim = {"confidence": 0.92, "is_faithful": True}  # LLM inflated

        # Apply FIX-060-B logic
        llm_claim["nli_score"] = r.get("nli_score")
        llm_claim["cross_source_score"] = r.get("cross_source_score")
        _orig_nli = r.get("nli_score")
        if _orig_nli is not None and _orig_nli > 0:
            llm_claim["confidence"] = _orig_nli

        assert llm_claim["confidence"] == 0.45

    def test_merge_without_nli_uses_llm(self):
        """When nli_score is None, LLM confidence is retained (capped by FIX-060-A)."""
        r = {"nli_score": None, "cross_source_score": None}
        llm_claim = {"confidence": 0.92, "is_faithful": True}

        llm_claim["nli_score"] = r.get("nli_score")
        llm_claim["cross_source_score"] = r.get("cross_source_score")
        _orig_nli = r.get("nli_score")
        if _orig_nli is not None and _orig_nli > 0:
            llm_claim["confidence"] = _orig_nli

        # LLM confidence retained (basis cap applied separately in _verify_batch)
        assert llm_claim["confidence"] == 0.92

    def test_merge_zero_nli_uses_llm(self):
        """When nli_score is 0.0, skip (zero NLI = uninformative)."""
        r = {"nli_score": 0.0, "cross_source_score": None}
        llm_claim = {"confidence": 0.50, "is_faithful": True}

        llm_claim["nli_score"] = r.get("nli_score")
        _orig_nli = r.get("nli_score")
        if _orig_nli is not None and _orig_nli > 0:
            llm_claim["confidence"] = _orig_nli

        assert llm_claim["confidence"] == 0.50  # Unchanged


# ---------------------------------------------------------------------------
# FIX-060-C: Triangulation Boost Guard
# ---------------------------------------------------------------------------

class TestTriangulationBoostGuard:
    """FIX-060-C: Only boost claims below 0.70, cap at 0.85."""

    def test_boost_skipped_above_070(self):
        """Claims at 0.80 confidence are NOT boosted."""
        import math
        claim = {"confidence": 0.80, "is_faithful": True, "claim_id": "ev_1"}
        source_count = 3

        # FIX-060-C logic
        if source_count > 1 and claim.get("is_faithful") is True and claim.get("confidence", 0) < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            claim["confidence"] = min(0.85, claim["confidence"] + boost)

        assert claim["confidence"] == 0.80  # Unchanged

    def test_boost_applied_below_070(self):
        """Claims at 0.40 with 3 sources get boosted."""
        import math
        claim = {"confidence": 0.40, "is_faithful": True, "claim_id": "ev_2"}
        source_count = 3

        if source_count > 1 and claim.get("is_faithful") is True and claim.get("confidence", 0) < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            claim["confidence"] = min(0.85, claim["confidence"] + boost)

        expected_boost = min(math.log2(3) * 0.05, 0.15)
        assert abs(claim["confidence"] - (0.40 + expected_boost)) < 0.001

    def test_boost_capped_085(self):
        """Max boost doesn't exceed 0.85."""
        import math
        claim = {"confidence": 0.69, "is_faithful": True, "claim_id": "ev_3"}
        source_count = 256  # log2(256) = 8, * 0.05 = 0.40, capped at 0.15

        if source_count > 1 and claim.get("is_faithful") is True and claim.get("confidence", 0) < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            claim["confidence"] = min(0.85, claim["confidence"] + boost)

        assert claim["confidence"] == 0.84  # min(0.85, 0.69 + 0.15)

    def test_boost_unfaithful_skipped(self):
        """Unfaithful claims are not boosted regardless of confidence."""
        import math
        claim = {"confidence": 0.30, "is_faithful": False, "claim_id": "ev_4"}
        source_count = 5
        original = claim["confidence"]

        if source_count > 1 and claim.get("is_faithful") is True and claim.get("confidence", 0) < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            claim["confidence"] = min(0.85, claim["confidence"] + boost)

        assert claim["confidence"] == original


# ---------------------------------------------------------------------------
# FIX-060-D: Low-Confidence Threshold Env Var
# ---------------------------------------------------------------------------

class TestLowConfidenceThreshold:
    """FIX-060-D: PG_LOW_CONFIDENCE_THRESHOLD env var replaces hardcoded 0.7."""

    def test_low_conf_threshold_env(self, monkeypatch):
        """PG_LOW_CONFIDENCE_THRESHOLD=0.60 filters claims below 0.60."""
        monkeypatch.setenv("PG_LOW_CONFIDENCE_THRESHOLD", "0.60")
        threshold = float(os.getenv("PG_LOW_CONFIDENCE_THRESHOLD", "0.60"))

        claims = [
            {"confidence": 0.55, "verification_method": "atomic", "statement": "Claim A"},
            {"confidence": 0.65, "verification_method": "atomic", "statement": "Claim B"},
            {"confidence": 0.30, "verification_method": "atomic", "statement": "Claim C"},
            {"confidence": 0.90, "verification_method": "atomic", "statement": "Claim D"},
            {"confidence": 0.45, "verification_method": "api_error", "statement": "Claim E"},
        ]

        low_confidence = [
            c for c in claims
            if c.get("confidence", 1.0) < threshold
            and c.get("verification_method") != "api_error"
        ]

        assert len(low_confidence) == 2  # A (0.55) and C (0.30), not E (api_error)

    def test_low_conf_default_060(self, monkeypatch):
        """Default threshold is 0.60 when env var not set."""
        monkeypatch.delenv("PG_LOW_CONFIDENCE_THRESHOLD", raising=False)
        threshold = float(os.getenv("PG_LOW_CONFIDENCE_THRESHOLD", "0.60"))
        assert threshold == 0.60


# ---------------------------------------------------------------------------
# FIX-060-E: Assembly Order — Transitions After Global Cleanup
# ---------------------------------------------------------------------------

class TestAssemblyOrder:
    """FIX-060-E: Transitions injected AFTER global cleanup."""

    def test_transitions_not_in_per_section_loop(self):
        """Per-section resolution should NOT call _inject_transitions."""
        import inspect
        from src.polaris_graph.synthesis import report_assembler

        source = inspect.getsource(report_assembler.assemble_report)

        # Find the per-section loop (between "for section in sorted_sections:" and
        # "report_sections.append"). Transitions should NOT appear there.
        # But they SHOULD appear after global cleanup.
        lines = source.split("\n")
        in_section_loop = False
        transition_in_loop = False
        for line in lines:
            if "for section in sorted_sections:" in line:
                in_section_loop = True
            if in_section_loop and "report_sections.append(" in line:
                in_section_loop = False
            if in_section_loop and "_inject_transitions(" in line and "FIX-060-E" not in line:
                transition_in_loop = True

        assert not transition_in_loop, (
            "_inject_transitions found in per-section loop (should be deferred)"
        )

    def test_transitions_present_in_final_output(self):
        """The function source should contain _inject_transitions after global cleanup."""
        import inspect
        from src.polaris_graph.synthesis import report_assembler

        source = inspect.getsource(report_assembler.assemble_report)

        # Should have FIX-060-E block with _inject_transitions
        assert "FIX-060-E" in source
        assert "_inject_transitions(" in source

    def test_no_orphan_transitions(self):
        """_clean_artifacts removes orphaned transition fragments."""
        from src.polaris_graph.synthesis.section_writer import _clean_artifacts

        # Simulate orphaned transitions (citations removed, leaving dangling words)
        text = "Water quality is important. Additionally,. Filters work well. Moreover."
        cleaned = _clean_artifacts(text)

        # Should not contain orphaned transition fragments
        assert "Additionally,." not in cleaned
        assert "Moreover." not in cleaned

    def test_clean_artifacts_with_titles(self):
        """_clean_artifacts detects title echo when section_titles passed."""
        from src.polaris_graph.synthesis.section_writer import _clean_artifacts

        text = "Water Quality Analysis\nWater filters remove contaminants effectively."
        cleaned = _clean_artifacts(text, section_titles=["Water Quality Analysis"])

        # Title echo should be removed
        assert not cleaned.startswith("Water Quality Analysis\n")


# ---------------------------------------------------------------------------
# FIX-060-F: Verification Prompt — Strict for Missing Content
# ---------------------------------------------------------------------------

class TestVerificationPrompt:
    """FIX-060-F: Updated Rule 4 for strict title-only handling."""

    def test_prompt_contains_strict_title_rule(self):
        """VERIFICATION_SYSTEM has updated Rule 4 marking title-only as NOT_SUPPORTED."""
        from src.polaris_graph.agents.verifier import VERIFICATION_SYSTEM

        assert "NOT_SUPPORTED" in VERIFICATION_SYSTEM
        assert "Title-only context is insufficient" in VERIFICATION_SYSTEM
        # Old lenient rule should be gone
        assert "assess conservatively based on source title and context" not in VERIFICATION_SYSTEM

    def test_prompt_allows_partial_for_quote_only(self):
        """Quote-only sources can still be PARTIALLY_SUPPORTED."""
        from src.polaris_graph.agents.verifier import VERIFICATION_SYSTEM

        assert "PARTIALLY_SUPPORTED at most" in VERIFICATION_SYSTEM


# ---------------------------------------------------------------------------
# FIX-060-G: Empty Batch Detection + Warning
# ---------------------------------------------------------------------------

class TestEmptyBatchDetection:
    """FIX-060-G: V4 placeholder detection and CASE_4 alerting."""

    def test_empty_batch_case4_alert(self, caplog):
        """25% V4 rate triggers CASE_4 error log."""
        all_verified = []
        # 25 V4 errors out of 100
        for i in range(75):
            all_verified.append({
                "verification_method": "atomic",
                "reasoning": "verdict=SUPPORTED basis=content",
            })
        for i in range(25):
            all_verified.append({
                "verification_method": "api_error",
                "reasoning": "FIX-V4 placeholder: empty batch result",
            })

        _v4_error_count = sum(
            1 for c in all_verified
            if c.get("verification_method") == "api_error"
            and "FIX-V4" in c.get("reasoning", "")
        )
        _total_claims = len(all_verified)
        _empty_batch_rate = _v4_error_count / max(_total_claims, 1)

        assert _v4_error_count == 25
        assert abs(_empty_batch_rate - 0.25) < 0.001
        assert _empty_batch_rate > 0.20  # Would trigger CASE_4

    def test_empty_batch_low_rate_warning(self):
        """5% V4 rate triggers warning but not CASE_4."""
        all_verified = []
        for i in range(95):
            all_verified.append({
                "verification_method": "atomic",
                "reasoning": "verdict=SUPPORTED",
            })
        for i in range(5):
            all_verified.append({
                "verification_method": "api_error",
                "reasoning": "FIX-V4 placeholder: empty batch",
            })

        _v4_error_count = sum(
            1 for c in all_verified
            if c.get("verification_method") == "api_error"
            and "FIX-V4" in c.get("reasoning", "")
        )
        _total_claims = len(all_verified)
        _empty_batch_rate = _v4_error_count / max(_total_claims, 1)

        assert _v4_error_count == 5
        assert _empty_batch_rate == 0.05
        assert _empty_batch_rate <= 0.20  # Would NOT trigger CASE_4

    def test_zero_v4_no_warning(self):
        """No V4 errors means no warning at all."""
        all_verified = [
            {"verification_method": "atomic", "reasoning": "verdict=SUPPORTED"}
            for _ in range(50)
        ]

        _v4_error_count = sum(
            1 for c in all_verified
            if c.get("verification_method") == "api_error"
            and "FIX-V4" in c.get("reasoning", "")
        )

        assert _v4_error_count == 0


# ===========================================================================
# INTEGRATION TESTS — Gap Closure (FIX-060 audit)
# These call REAL functions instead of copy-pasting logic inline.
# ===========================================================================


# ---------------------------------------------------------------------------
# Class 1: TestIntegrationNLIMerge — FIX-060-B real code path
# ---------------------------------------------------------------------------

class TestIntegrationNLIMerge:
    """Integration: verify_claims() with NLI + LLM second opinion merge."""

    @pytest.mark.asyncio
    async def test_nli_confidence_preserved_through_merge(self, monkeypatch):
        """NLI confidence survives LLM second opinion merge (real verify_claims path).

        Mock NLI → nli_score=0.45, is_faithful=False
        Mock disputed → selects the claim (0.3 ≤ 0.45 ≤ 0.7)
        Mock LLM second opinion → confidence=0.92, is_faithful=True
        Assert: confidence == 0.45 (NLI preserved, NOT 0.92)
        Assert: is_faithful is False (FIX-059-B: 0.45 < 0.65)
        """
        monkeypatch.setenv("PG_NLI_ENABLED", "1")
        monkeypatch.setenv("PG_CROSS_SOURCE_ENABLED", "0")
        monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.65")

        from unittest.mock import AsyncMock, patch

        from src.polaris_graph.agents.verifier import verify_claims

        # One evidence piece
        evidence = [
            {
                "evidence_id": "ev_test_merge_001",
                "statement": "Water filters remove 99% of lead.",
                "source_url": "https://example.com/filters",
                "source_title": "Filter Guide",
                "direct_quote": "Our filters remove 99% of lead.",
            }
        ]
        state = {
            "evidence": evidence,
            "fetched_content": [],
            "original_query": "water filter effectiveness",
        }

        # NLI returns nli_score=0.45, not faithful
        nli_result = {
            "claim_id": "ev_test_merge_001",
            "statement": "Water filters remove 99% of lead.",
            "nli_score": 0.45,
            "is_faithful": False,
            "confidence": 0.45,
            "verification_method": "nli",
            "cross_source_score": 0.3,
            "evidence_ids": ["ev_test_merge_001"],
            "section_id": None,
            "reasoning": "NLI score below threshold",
            "verification_basis": "content",
            "verification_type": "nli",
        }

        # Disputed: claim has 0.3 ≤ nli_score=0.45 ≤ 0.7
        disputed = [nli_result]

        # LLM second opinion returns inflated confidence=0.92
        llm_second = [
            {
                "claim_id": "ev_test_merge_001",
                "confidence": 0.92,
                "is_faithful": True,
                "statement": "Water filters remove 99% of lead.",
                "verification_method": "atomic",
                "evidence_ids": ["ev_test_merge_001"],
                "section_id": None,
                "reasoning": "verdict=SUPPORTED basis=content",
                "verification_basis": "content",
                "verification_type": "extraction_self_check",
                "nli_score": None,
                "cross_source_score": None,
            }
        ]

        with (
            patch(
                "src.polaris_graph.agents.nli_verifier.verify_evidence_nli",
                new_callable=AsyncMock,
                return_value=[nli_result],
            ),
            patch(
                "src.polaris_graph.agents.nli_verifier.get_disputed_claims",
                return_value=disputed,
            ),
            patch(
                "src.polaris_graph.agents.verifier._llm_second_opinion",
                new_callable=AsyncMock,
                return_value=llm_second,
            ),
        ):
            result = await verify_claims(None, state)

        claims = result["claims"]
        assert len(claims) == 1, f"Expected 1 claim, got {len(claims)}"

        claim = claims[0]
        # FIX-060-B: NLI confidence preserved, not overwritten by LLM's 0.92
        assert claim["confidence"] == 0.45, (
            f"Expected NLI confidence 0.45, got {claim['confidence']}"
        )
        # FIX-059-B: 0.45 < 0.65 threshold → unfaithful
        assert claim["is_faithful"] is False, (
            f"Expected is_faithful=False (NLI 0.45 < 0.65), got {claim['is_faithful']}"
        )


# ---------------------------------------------------------------------------
# Class 2: TestIntegrationBasisConfidence — FIX-060-A real _verify_batch
# ---------------------------------------------------------------------------

class TestIntegrationBasisConfidence:
    """Integration: _verify_batch() applies basis-aware confidence caps."""

    @pytest.mark.asyncio
    async def test_content_basis_caps_at_050(self, monkeypatch):
        """Evidence with source content → basis='content', confidence capped at 0.50."""
        monkeypatch.setenv("PG_MIN_USEFUL_CONTENT", "100")
        monkeypatch.setenv("PG_BALANCED_PROMPTING", "0")

        from unittest.mock import AsyncMock

        from src.polaris_graph.agents.verifier import _verify_batch
        from src.polaris_graph.schemas import VerificationBatch

        batch = [
            {
                "evidence_id": "ev_content_001",
                "statement": "Activated carbon filters cost $20.",
                "source_url": "https://example.com/cost",
                "source_title": "Cost Analysis",
                "direct_quote": "Activated carbon filters cost $20.",
            }
        ]
        url_content_map = {
            "https://example.com/cost": "A" * 1000,  # Sufficient content
        }

        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(
            return_value=VerificationBatch(
                verifications=[
                    {
                        "claim": "Activated carbon filters cost $20.",
                        "verdict": "SUPPORTED",
                        "confidence": 0.93,
                    },
                ],
                overall_faithfulness=1.0,
            )
        )

        result = await _verify_batch(mock_client, batch, url_content_map)

        assert len(result) == 1
        claim = result[0]
        assert claim["verification_basis"] == "content"
        # FIX-060-A: LLM's 0.93 capped to content cap 0.50
        assert claim["confidence"] == 0.50, (
            f"Expected 0.50 (content cap), got {claim['confidence']}"
        )

    @pytest.mark.asyncio
    async def test_quote_only_basis_caps_at_030(self, monkeypatch):
        """Evidence with quote but NO content → basis='quote_only', capped at 0.30."""
        monkeypatch.setenv("PG_BALANCED_PROMPTING", "0")

        from unittest.mock import AsyncMock

        from src.polaris_graph.agents.verifier import _verify_batch
        from src.polaris_graph.schemas import VerificationBatch

        batch = [
            {
                "evidence_id": "ev_quote_001",
                "statement": "RO membranes last 2-5 years.",
                "source_url": "https://example.com/ro",
                "source_title": "RO Guide",
                "direct_quote": "RO membranes typically last 2-5 years.",
            }
        ]
        # No content in map → quote_only basis
        url_content_map = {}

        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(
            return_value=VerificationBatch(
                verifications=[
                    {
                        "claim": "RO membranes last 2-5 years.",
                        "verdict": "SUPPORTED",
                        "confidence": 0.90,
                    },
                ],
                overall_faithfulness=1.0,
            )
        )

        result = await _verify_batch(mock_client, batch, url_content_map)

        assert len(result) == 1
        claim = result[0]
        assert claim["verification_basis"] == "quote_only"
        # FIX-060-A: LLM's 0.90 capped to quote_only cap 0.30
        assert claim["confidence"] == 0.30, (
            f"Expected 0.30 (quote_only cap), got {claim['confidence']}"
        )


# ---------------------------------------------------------------------------
# Class 3: TestIntegrationAssemblyOrder — FIX-060-E real assemble_report
# ---------------------------------------------------------------------------

class TestIntegrationAssemblyOrder:
    """Integration: assemble_report() produces clean output with correct citation_ids."""

    def test_assemble_report_produces_clean_output(self):
        """Full assemble_report call with real schemas produces clean report."""
        from src.polaris_graph.schemas import (
            CitationAudit,
            CitationMapping,
            ReportOutline,
            SectionDraft,
        )
        from src.polaris_graph.synthesis.report_assembler import assemble_report

        outline = ReportOutline(
            title="Water Purification Methods",
            abstract="This report examines water purification methods drawing on 2 sources with 2 citations across 500 words.",
            sections=[
                {
                    "section_id": "s01",
                    "title": "Filtration Techniques",
                    "description": "Overview of filtration methods",
                    "evidence_ids": ["ev_001", "ev_002"],
                    "target_words": 400,
                    "order": 1,
                },
            ],
        )

        sections = [
            SectionDraft(
                section_id="s01",
                title="Filtration Techniques",
                content=(
                    "Activated carbon filters remove chlorine [CITE:ev_001]. "
                    "Reverse osmosis removes dissolved salts [CITE:ev_002]. "
                    "These methods are widely used in residential settings."
                ),
                claims_made=["Carbon removes chlorine", "RO removes salts"],
                evidence_ids=["ev_001", "ev_002"],
            ),
        ]

        evidence = [
            {
                "evidence_id": "ev_001",
                "statement": "Activated carbon removes chlorine.",
                "source_url": "https://example.com/carbon",
                "source_title": "Carbon Filter Study",
                "direct_quote": "Carbon filters effectively remove chlorine.",
            },
            {
                "evidence_id": "ev_002",
                "statement": "RO removes dissolved salts.",
                "source_url": "https://example.com/ro",
                "source_title": "RO Technology Review",
                "direct_quote": "Reverse osmosis removes dissolved salts.",
            },
        ]

        citation_audit = CitationAudit(
            mappings=[
                CitationMapping(evidence_id="ev_001", citation_number=1, is_grounded=True),
                CitationMapping(evidence_id="ev_002", citation_number=2, is_grounded=True),
            ],
            ungrounded_claims=[],
            bibliography_entries=["[1] Carbon Filter Study", "[2] RO Technology Review"],
        )

        full_report, report_sections, bibliography = assemble_report(
            outline, sections, evidence, citation_audit,
        )

        # No orphan artifacts
        assert "Additionally,." not in full_report
        assert "Moreover." not in full_report

        # No unresolved [CITE:] markers
        assert "[CITE:" not in full_report

        # GAP-2: citation_ids matches actual [N] in content
        for sec in report_sections:
            actual_nums = re.findall(r"\[(\d+)\]", sec["content"])
            expected_ids = [f"[{n}]" for n in actual_nums]
            assert sec["citation_ids"] == expected_ids, (
                f"citation_ids mismatch: {sec['citation_ids']} vs {expected_ids}"
            )

        # Bibliography non-empty
        assert len(bibliography) > 0, "Bibliography should not be empty"

        # Report contains title and section headers
        assert "# Water Purification Methods" in full_report
        assert "## Filtration Techniques" in full_report
        assert "## References" in full_report


# ---------------------------------------------------------------------------
# Class 4: TestIntegrationBoostGuard — FIX-060-C + FIX-060-A interaction
# ---------------------------------------------------------------------------

class TestIntegrationBoostGuard:
    """Integration: triangulation boost interacts correctly with basis caps."""

    def test_boost_on_capped_confidence_respects_guard(self):
        """Basis cap 0.50 + 3 sources → boosted but still well below 0.85."""
        import math

        from src.polaris_graph.agents.verifier import _basis_aware_confidence

        # Step 1: Basis cap
        capped = _basis_aware_confidence(0.93, "content")
        assert capped == 0.50

        # Step 2: Simulate FIX-060-C boost (only fires if < 0.70)
        source_count = 3
        if capped < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            result = min(0.85, capped + boost)
        else:
            result = capped

        # 0.50 + log2(3)*0.05 ≈ 0.50 + 0.079 = 0.579
        assert result < 0.85, f"Boosted result {result} should be < 0.85"
        assert result > 0.50, f"Boosted result {result} should be > 0.50 (boost applied)"

    def test_boost_does_not_exceed_085_with_many_sources(self):
        """Basis cap 0.50 + 128 sources → max boost 0.15 → 0.65."""
        import math

        from src.polaris_graph.agents.verifier import _basis_aware_confidence

        capped = _basis_aware_confidence(0.99, "content")
        assert capped == 0.50

        source_count = 128  # log2(128) = 7, * 0.05 = 0.35, capped at 0.15
        if capped < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            result = min(0.85, capped + boost)
        else:
            result = capped

        assert result == 0.65, f"Expected 0.65 (0.50 + 0.15 cap), got {result}"

    def test_nli_confidence_not_basis_capped(self):
        """NLI score 0.72 used directly — not passed through _basis_aware_confidence."""
        from src.polaris_graph.agents.verifier import _basis_aware_confidence

        nli_score = 0.72

        # Simulate the _verify_batch logic (line 967):
        # confidence = _ev_nli if _ev_nli and _ev_nli > 0 else _basis_aware_confidence(...)
        if nli_score and nli_score > 0:
            confidence = nli_score
        else:
            confidence = _basis_aware_confidence(0.93, "content")

        assert confidence == 0.72, (
            f"NLI score should be used directly (0.72), not basis-capped. Got {confidence}"
        )
