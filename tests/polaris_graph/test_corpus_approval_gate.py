"""
Tests for Phase 2g corpus-approval gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.nodes.corpus_approval_gate import (
    AuthorizedSweep,
    CorpusApprovalDecision,
    CorpusSource,
    authorization_from_env,
    check_auto_approve_allowed,
    compute_tier_distribution,
    render_approval_html,
    save_approval_decision,
)


def _on_protocol_corpus() -> list[CorpusSource]:
    return [
        CorpusSource(url="https://example.com/1", tier="T1", domain="journals.lww.com"),
        CorpusSource(url="https://example.com/2", tier="T1", domain="doi.org"),
        CorpusSource(url="https://example.com/3", tier="T1", domain="pmc"),
        CorpusSource(url="https://example.com/4", tier="T2", domain="frontiersin.org"),
        CorpusSource(url="https://example.com/5", tier="T2", domain="cochrane.org"),
        CorpusSource(url="https://example.com/6", tier="T3", domain="fda.gov"),
        CorpusSource(url="https://example.com/7", tier="T3", domain="ema.europa.eu"),
        CorpusSource(url="https://example.com/8", tier="T4", domain="postgraduate"),
        CorpusSource(url="https://example.com/9", tier="T5", domain="novomedlink.com"),
        CorpusSource(url="https://example.com/10", tier="T6", domain="news"),
    ]


def _clinical_protocol() -> dict:
    return {
        "research_question": "Semaglutide for weight loss",
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.30, "max_fraction": 0.60},
            {"tier": "T2", "min_fraction": 0.15, "max_fraction": 0.40},
            {"tier": "T3", "min_fraction": 0.05, "max_fraction": 0.25},
            {"tier": "T5", "min_fraction": 0.00, "max_fraction": 0.15},
            {"tier": "T6", "min_fraction": 0.00, "max_fraction": 0.10},
        ],
    }


def test_on_protocol_corpus_is_within_bounds() -> None:
    sources = _on_protocol_corpus()  # 10 sources: 3 T1, 2 T2, 2 T3, 1 T4, 1 T5, 1 T6
    report = compute_tier_distribution(sources, _clinical_protocol())
    assert report.total_sources == 10
    assert report.tier_counts["T1"] == 3
    # T1 fraction = 0.30 -> within [0.30, 0.60]
    assert report.tier_fractions["T1"] == 0.30
    # Except T2 = 0.20, T3 = 0.20, T5 = 0.10, T6 = 0.10 (all within bounds)
    assert report.has_material_deviation is False
    assert report.auto_approve_allowed is True


def test_industry_dominated_corpus_triggers_material_deviation() -> None:
    # Bad corpus: 80% T5 industry marketing, no T1/T2
    sources = [
        CorpusSource(url=f"https://novomedlink.com/{i}", tier="T5", domain="novomedlink.com")
        for i in range(8)
    ] + [
        CorpusSource(url="https://pmc/r1", tier="T1", domain="pmc"),
        CorpusSource(url="https://pmc/r2", tier="T1", domain="pmc"),
    ]
    report = compute_tier_distribution(sources, _clinical_protocol())
    assert report.tier_fractions["T5"] == 0.80  # above max 0.15
    assert report.tier_fractions["T1"] == 0.20  # below min 0.30
    assert report.has_material_deviation is True
    assert report.auto_approve_allowed is False
    # Find the T5 deviation
    t5_dev = next(d for d in report.deviations if d.tier == "T5")
    assert t5_dev.is_material is True
    assert t5_dev.deviation_pp > 0.15


def test_minor_deviation_not_material() -> None:
    # 10% T1 (below min 0.30 by 20pp — material),
    # but test with smaller deviation
    sources = [
        CorpusSource(url=f"https://pmc/{i}", tier="T1", domain="pmc")
        for i in range(3)  # 30%
    ] + [
        CorpusSource(url=f"https://f/{i}", tier="T2", domain="frontiers")
        for i in range(3)  # 30%
    ] + [
        CorpusSource(url=f"https://fda/{i}", tier="T3", domain="fda.gov")
        for i in range(3)  # 30% — above max 0.25 by 5pp, not material
    ] + [
        CorpusSource(url=f"https://mk/{i}", tier="T5", domain="novo")
        for i in range(1)  # 10%
    ]
    report = compute_tier_distribution(sources, _clinical_protocol())
    # T3 at 30% is above max 25% — deviation 5pp (below 15pp threshold)
    t3_dev = next(d for d in report.deviations if d.tier == "T3")
    assert t3_dev.actual_fraction == 0.30
    assert abs(t3_dev.deviation_pp - 0.05) < 0.001
    assert t3_dev.is_material is False


def test_html_render_basic() -> None:
    sources = _on_protocol_corpus()
    report = compute_tier_distribution(sources, _clinical_protocol())
    html_doc = render_approval_html(
        report, sources,
        "Semaglutide for weight loss in adults with obesity",
    )
    assert "<title>POLARIS" in html_doc
    assert "Semaglutide for weight loss" in html_doc
    assert "T1" in html_doc
    assert "fda.gov" in html_doc


def test_html_shows_material_banner_when_deviation() -> None:
    sources = [
        CorpusSource(url=f"https://novomedlink.com/{i}", tier="T5", domain="novomedlink.com")
        for i in range(10)
    ]
    report = compute_tier_distribution(sources, _clinical_protocol())
    html_doc = render_approval_html(report, sources, "question")
    assert "Material deviation" in html_doc


def _material_deviation_report():
    """A corpus that is 100% T5 → way over the clinical T5 cap → material."""
    sources = [
        CorpusSource(url=f"https://x/{i}", tier="T5", domain="x")
        for i in range(10)
    ]
    report = compute_tier_distribution(sources, _clinical_protocol())
    assert report.has_material_deviation is True
    return report


def test_check_auto_approve_allowed_without_deviation() -> None:
    report = compute_tier_distribution(
        _on_protocol_corpus(), _clinical_protocol(),
    )
    # FX-05: no material deviation → auto-approve regardless of authorization.
    ok, err = check_auto_approve_allowed(report, None)
    assert ok is True
    assert err == ""


def test_material_deviation_denies_without_authorization() -> None:
    """FX-05: material deviation + no structured authorization → DENY."""
    report = _material_deviation_report()
    ok, err = check_auto_approve_allowed(report, None)
    assert ok is False
    assert "authoriz" in err.lower()


def test_material_deviation_denies_free_text_note() -> None:
    """FX-05: a free-text note alone NEVER auto-approves (closes the loophole
    where the R-3 sweep's own 48-char canned note slipped through)."""
    report = _material_deviation_report()
    substantive = (
        "Corpus is dominated by manufacturer HCP content because the "
        "research question is specifically about the labelled dosing "
        "regimen. Will flag in methods."
    )
    ok, err = check_auto_approve_allowed(report, substantive)  # legacy free text
    assert ok is False
    assert "note" in err.lower() or "authoriz" in err.lower()


def test_material_deviation_approves_with_structured_authorization() -> None:
    """FX-05: a COMPLETE AuthorizedSweep is the one sanctioned auto-approve."""
    report = _material_deviation_report()
    auth = AuthorizedSweep(
        authorized_by="env:PG_AUTHORIZED_SWEEP_APPROVAL",
        authorized_at="2026-06-06T00:00:00Z",
        flag_source="env",
    )
    ok, err = check_auto_approve_allowed(report, auth)
    assert ok is True
    assert err == ""


def test_material_deviation_denies_incomplete_authorization() -> None:
    """FX-05: an AuthorizedSweep missing required fields → DENY (fail-closed)."""
    report = _material_deviation_report()
    auth = AuthorizedSweep(authorized_by="", authorized_at="", flag_source="")
    ok, err = check_auto_approve_allowed(report, auth)
    assert ok is False


def test_authorization_from_env_requires_flag(monkeypatch) -> None:
    """FX-05: authorization_from_env() returns None unless the flag is truthy,
    and a complete AuthorizedSweep when it is (LAW VI: from config only)."""
    monkeypatch.delenv("PG_AUTHORIZED_SWEEP_APPROVAL", raising=False)
    assert authorization_from_env() is None
    monkeypatch.setenv("PG_AUTHORIZED_SWEEP_APPROVAL", "0")
    assert authorization_from_env() is None
    monkeypatch.setenv("PG_AUTHORIZED_SWEEP_APPROVAL", "1")
    auth = authorization_from_env()
    assert auth is not None
    assert auth.authorized_by and auth.authorized_at and auth.flag_source == "env"


def test_save_approval_decision_writes_json(tmp_path: Path) -> None:
    sources = _on_protocol_corpus()
    report = compute_tier_distribution(sources, _clinical_protocol())
    decision = CorpusApprovalDecision(
        run_id="TEST_APPROVE",
        decision_at_unix=1700000000.0,
        decision_at_iso="2023-11-14T22:13:20Z",
        approved=True,
        user_note="Looks good.",
        approved_source_urls=[s.url for s in sources],
        rejected_source_urls=[],
        report=report,
        protocol_sha256="deadbeef" * 8,
    )
    path = save_approval_decision(decision, tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["approved"] is True
    assert data["run_id"] == "TEST_APPROVE"
    assert data["report"]["total_sources"] == 10
