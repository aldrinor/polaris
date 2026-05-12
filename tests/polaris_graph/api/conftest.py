"""Test fixtures for graph_route tests (I-snowball-002).

Builds minimal AuditIR-shaped duck-typed objects via SimpleNamespace.
The build_graph_payload function walks attributes; it doesn't enforce
dataclass instance types, so a SimpleNamespace with matching attribute
names is sufficient and avoids the dataclass-field-completeness burden
of constructing a real frozen AuditIR.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _bib(num: int, evidence_id: str, tier: str = "T1", url: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        num=num, evidence_id=evidence_id, statement=f"Source {evidence_id}",
        tier=tier, url=url or f"https://example.com/{evidence_id}",
    )


def _tok(evidence_id: str, start: int = 0, end: int = 10) -> SimpleNamespace:
    return SimpleNamespace(evidence_id=evidence_id, start=start, end=end)


def _sent(claim_id: str, section: str, text: str,
          tokens: list[SimpleNamespace] | None = None,
          is_verified: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        claim_id=claim_id, section=section, text=text,
        tokens=tuple(tokens or []), is_verified=is_verified,
        failure_reasons=tuple() if is_verified else ("missing_evidence",),
    )


def _section(title: str, sentences: list[SimpleNamespace]) -> SimpleNamespace:
    kept = sum(1 for s in sentences if s.is_verified)
    return SimpleNamespace(
        title=title, kept_count=kept, dropped_count=len(sentences) - kept,
        total_in=len(sentences), dropped_due_to_failure=0,
        sentences=tuple(sentences),
    )


def _contradiction_claim(evidence_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        evidence_id=evidence_id, subject="s", predicate="p", arm="",
        dose="", value=0.0, unit="", source_tier="T1",
        source_url=f"https://example.com/{evidence_id}",
        context_snippet="", endpoint_phrase="",
    )


def _frame_entry(entity_id: str, status: str = "pass") -> SimpleNamespace:
    return SimpleNamespace(
        entity_id=entity_id, entity_type="drug", section="safety",
        slot_id=f"slot_{entity_id}", subsection_title="Safety",
        status=status, doi=None, pmid=None, failure_reason=None,
        available_artifacts=tuple(), required_fields=tuple(),
        min_fields_for_completion=1, provenance_class="",
        human_completion_eligible=False, human_curated_provenance=None,
        is_pipeline_fault=False, retrieval_attempt_log=tuple(),
    )


@pytest.fixture
def small_ir() -> SimpleNamespace:
    """Minimal AuditIR: 2 bib sources, 1 referenced-missing, 1 section, 2 sentences, 1 contradiction, 2 frames."""
    return SimpleNamespace(
        ir_schema_version="1.0", run_id="test_run_001",
        bibliography=(_bib(1, "ev_001"), _bib(2, "ev_002", tier="T2")),
        verified_report=SimpleNamespace(
            sections=(
                _section("Safety", [
                    _sent("Safety:verified:0", "Safety", "Sentence A cites ev_001.",
                          tokens=[_tok("ev_001")]),
                    _sent("Safety:verified:1", "Safety", "Sentence B cites ev_002 and ev_missing.",
                          tokens=[_tok("ev_002"), _tok("ev_missing")]),
                    _sent("Safety:dropped:0", "Safety", "Dropped sentence.",
                          tokens=[_tok("ev_001")], is_verified=False),
                ]),
            ),
            sentences_verified=2, sentences_dropped=1, drop_reason_counts={},
        ),
        contradictions=(
            SimpleNamespace(
                cluster_id=1, subject="efficacy", predicate="vs",
                severity="high", absolute_difference=1.0, relative_difference=0.1,
                recommended_action="review",
                claims=(_contradiction_claim("ev_001"), _contradiction_claim("ev_002")),
            ),
        ),
        frame_coverage=SimpleNamespace(
            pass_count=1, partial_count=0,
            entries=(_frame_entry("efficacy_endpoint", "pass"),
                     _frame_entry("safety_endpoint", "fail_min_fields")),
        ),
    )
