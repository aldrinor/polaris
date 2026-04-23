"""V30 sweep integration tests.

Exercises `run_v30_post_generation` — the glue module that wires
M-54..M-61 into run_honest_sweep_r3.py. Pure tests (no network;
M-56 httpx calls stubbed via MockTransport injected through
environment patches + module-level shims).

Covers:
1. PG_V30_ENABLED=0 → no-op (backward-compat with pre-V30 sweeps).
2. PG_V30_ENABLED=1 + slug with no contract → no-op with log.
3. PG_V30_ENABLED=1 + clinical slug → compiled frame +
   coverage report emitted. Network is NOT invoked in this test;
   we pre-inject a monkeypatched `fetch_compiled_frame` that
   returns stub rows.
4. PG_V30_ENABLED=1 + gap row → human_gap_tasks.json has a
   curator-actionable task with required_fields.
5. PG_V30_ENABLED=1 + operator human_gap_completions.json
   present → completions merged, rejected completions logged as
   warnings.
6. Exception inside chain → V30SweepResult.error populated,
   does NOT propagate up.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def log_capture() -> list[str]:
    return []


@pytest.fixture
def _log(log_capture: list[str]):
    def _write(msg: str) -> None:
        log_capture.append(msg)
    return _write


@pytest.fixture(scope="module")
def clinical_template() -> dict:
    path = Path("config/scope_templates/clinical.yaml")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def policy_template() -> dict:
    path = Path("config/scope_templates/policy.yaml")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    """Replace M-56 fetch with stub rows — one ABSTRACT_ONLY row per
    binding. Used to test V30 integration without live network."""
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow, ProvenanceClass,
    )
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=f"stub content for {b.entity_id}",
            quote_source="crossref_abstract",
            doi="10.1/stub",
            pmid=None,
            oa_pdf_url=None,
            url=None,
            title=f"Stub title {b.entity_id}",
            authors=(),
            journal=None,
            year=2024,
            failure_reason=None,
            retrieval_attempts=(),
            retrieval_timings=(),
        )
        for b in compiled.evidence_bindings
    )


def _stub_fetch_with_gap(compiled, gap_entity_id: str):
    """Stub fetch where one specific entity returns
    FRAME_GAP_UNRECOVERABLE."""
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow, ProvenanceClass,
    )
    rows = []
    for b in compiled.evidence_bindings:
        if b.entity_id == gap_entity_id:
            rows.append(FrameRow(
                entity_id=b.entity_id,
                entity_type=b.entity_type,
                rendering_slot=b.rendering_slot,
                provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
                direct_quote="",
                quote_source="none",
                doi=None,
                pmid=None,
                oa_pdf_url=None,
                url=None,
                title=None,
                authors=(),
                journal=None,
                year=None,
                failure_reason="paywalled, no OA, no abstract",
                retrieval_attempts=(),
                retrieval_timings=(),
            ))
        else:
            rows.append(FrameRow(
                entity_id=b.entity_id,
                entity_type=b.entity_type,
                rendering_slot=b.rendering_slot,
                provenance_class=ProvenanceClass.ABSTRACT_ONLY,
                direct_quote=f"stub content for {b.entity_id}",
                quote_source="crossref_abstract",
                doi="10.1/stub",
                pmid=None,
                oa_pdf_url=None,
                url=None,
                title=f"Stub title {b.entity_id}",
                authors=(),
                journal=None,
                year=2024,
                failure_reason=None,
                retrieval_attempts=(),
                retrieval_timings=(),
            ))
    return tuple(rows)


# ─────────────────────────────────────────────────────────────────────
# (1) Opt-in gating
# ─────────────────────────────────────────────────────────────────────
class TestOptInGating:
    def test_disabled_is_noop(
        self, tmp_path: Path, clinical_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PG_V30_ENABLED", raising=False)
        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )
        assert result.enabled is False
        assert result.frame_coverage_report is None
        assert result.methods_disclosure_text is None
        # No file written
        assert not (tmp_path / "human_gap_tasks.json").exists()

    def test_enabled_explicitly(
        self, tmp_path: Path, clinical_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        # Stub M-56 so the test is network-free
        import src.polaris_graph.v30_sweep_integration as mod
        import src.polaris_graph.retrieval.frame_fetcher as ff
        orig = ff.fetch_compiled_frame
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_rows(
                _FakeCompiled(bindings)
            ),
        )
        try:
            from src.polaris_graph.v30_sweep_integration import (
                run_v30_post_generation,
            )
            result = run_v30_post_generation(
                research_question="tirzepatide T2D evidence",
                scope_template=clinical_template,
                slug="clinical_tirzepatide_t2dm",
                run_dir=tmp_path,
                log=_log,
            )
        finally:
            monkeypatch.setattr(ff, "fetch_compiled_frame", orig)

        assert result.enabled is True
        assert result.frame_coverage_report is not None
        assert result.error is None


class _FakeCompiled:
    """Duck-typed stub so `_stub_fetch_rows(compiled)` can be
    called with `compiled.evidence_bindings` when monkeypatching
    takes only bindings."""
    def __init__(self, bindings):
        self.evidence_bindings = bindings


# ─────────────────────────────────────────────────────────────────────
# (2) No-contract slug graceful skip
# ─────────────────────────────────────────────────────────────────────
class TestNoContractSkip:
    def test_slug_without_contract_returns_none_coverage(
        self, tmp_path: Path, clinical_template: dict,
        _log, log_capture: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="slug_that_does_not_exist_in_contract",
            run_dir=tmp_path,
            log=_log,
        )
        assert result.enabled is True
        assert result.frame_coverage_report is None
        assert result.error is None
        # Log message mentions missing contract
        assert any(
            "no per_query_report_contract" in m
            for m in log_capture
        )


# ─────────────────────────────────────────────────────────────────────
# (3) Clinical slug full chain
# ─────────────────────────────────────────────────────────────────────
class TestClinicalChain:
    def test_clinical_tirzepatide_produces_coverage(
        self, tmp_path: Path, clinical_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        import src.polaris_graph.retrieval.frame_fetcher as ff
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_rows(
                _FakeCompiled(bindings)
            ),
        )
        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question=(
                "What is the evidence for tirzepatide in T2D?"
            ),
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )

        assert result.enabled is True
        assert result.frame_coverage_report is not None
        cov = result.frame_coverage_report
        # Clinical contract has 15 entities
        assert cov["total_entities"] == 15
        assert cov["pipeline_fault_count"] == 0
        # All stub rows are ABSTRACT_ONLY → synth PASS → pass_count=15
        assert cov["pass_count"] == 15

        # Methods disclosure produced
        assert "Frame coverage" in result.methods_disclosure_text

        # human_gap_tasks.json written (all PASS → zero tasks)
        tasks_path = tmp_path / "human_gap_tasks.json"
        assert tasks_path.exists()
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
        assert tasks == []


# ─────────────────────────────────────────────────────────────────────
# (4) Gap row → curator task
# ─────────────────────────────────────────────────────────────────────
class TestGapRowToTask:
    def test_gap_entity_yields_human_completion_task(
        self, tmp_path: Path, clinical_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        import src.polaris_graph.retrieval.frame_fetcher as ff
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_with_gap(
                _FakeCompiled(bindings),
                gap_entity_id="surpass_cvot_primary",
            ),
        )
        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )

        cov = result.frame_coverage_report
        assert cov["frame_gap_count"] == 1
        # Tasks file has exactly one curator-actionable entry
        tasks = result.human_gap_tasks_json
        assert len(tasks) == 1
        task = tasks[0]
        assert task["entity_id"] == "surpass_cvot_primary"
        # Codex M-60 audit Blocker: required_fields must be present
        assert "required_fields" in task
        assert len(task["required_fields"]) > 0
        assert "RETRIEVAL gap" in task["needs"]


# ─────────────────────────────────────────────────────────────────────
# (5) Operator completions merge
# ─────────────────────────────────────────────────────────────────────
class TestOperatorCompletionsMerge:
    def test_completions_file_substitutes_gap_row(
        self, tmp_path: Path, clinical_template: dict,
        _log, log_capture: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        import src.polaris_graph.retrieval.frame_fetcher as ff
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_with_gap(
                _FakeCompiled(bindings),
                gap_entity_id="surpass_4_primary",
            ),
        )

        # Write a well-formed completion for surpass_4_primary
        completions = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.1016/S0140-6736(21)01997-1",
            "direct_quote": (
                "In SURPASS-4 (Del Prato, Lancet 2021), 1995 T2D "
                "adults received tirzepatide."
            ),
            "provenance": {
                "curator_id": "operator@inst",
                "source_type": "licensed_institutional_access",
                "source_locator": "10.1016/S0140-6736(21)01997-1 pp.1811-1824",
                "acquired_at": "2026-04-23T18:00:00+00:00",
                "artifact_sha256": "a" * 64,
                "artifact_retention_path": "/audit/surpass4.pdf",
                "quote_page_range": "pp.1811-1824",
                "attestation": "I hereby certify licensed access.",
            },
        }]
        (tmp_path / "human_gap_completions.json").write_text(
            json.dumps(completions), encoding="utf-8",
        )

        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )

        # After merge, SURPASS-4 is no longer a gap
        cov = result.frame_coverage_report
        surpass_4 = next(
            e for e in cov["entries"]
            if e["entity_id"] == "surpass_4_primary"
        )
        assert surpass_4["provenance_class"] == "human_curated"
        # Structured provenance survives the FrameRow boundary
        assert surpass_4["human_curated_provenance"] is not None
        assert (
            surpass_4["human_curated_provenance"]["curator_id"]
            == "operator@inst"
        )
        # Log mentions the merge
        assert any("merged 1 human-curated" in m for m in log_capture)

    def test_doi_mismatch_completion_rejected_with_warning(
        self, tmp_path: Path, clinical_template: dict,
        _log, log_capture: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        import src.polaris_graph.retrieval.frame_fetcher as ff
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_with_gap(
                _FakeCompiled(bindings),
                gap_entity_id="surpass_4_primary",
            ),
        )

        # Operator submits wrong DOI
        completions = [{
            "entity_id": "surpass_4_primary",
            "doi": "10.9999/wrong_paper.2020",
            "direct_quote": "operator-supplied but from wrong paper",
            "provenance": {
                "curator_id": "operator@inst",
                "source_type": "licensed_institutional_access",
                "source_locator": "10.9999/wrong_paper.2020 pp.1-2",
                "acquired_at": "2026-04-23T18:00:00+00:00",
                "artifact_sha256": "a" * 64,
                "artifact_retention_path": "/audit/wrong.pdf",
                "quote_page_range": "pp.1-2",
                "attestation": "I hereby certify licensed access.",
            },
        }]
        (tmp_path / "human_gap_completions.json").write_text(
            json.dumps(completions), encoding="utf-8",
        )

        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )

        # Warning emitted
        rejected_msgs = [
            w for w in result.warnings
            if "human_completion_rejected" in w
        ]
        assert len(rejected_msgs) == 1
        assert "surpass_4_primary" in rejected_msgs[0]


# ─────────────────────────────────────────────────────────────────────
# (6) Chain exception caught
# ─────────────────────────────────────────────────────────────────────
class TestExceptionSafety:
    def test_compile_frame_exception_does_not_propagate(
        self, tmp_path: Path, clinical_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        # Patch compile_frame to raise
        import src.polaris_graph.nodes.frame_compiler as fc

        def _raise(*args, **kwargs):
            raise RuntimeError("synthetic failure for test")

        monkeypatch.setattr(fc, "compile_frame", _raise)

        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question="q",
            scope_template=clinical_template,
            slug="clinical_tirzepatide_t2dm",
            run_dir=tmp_path,
            log=_log,
        )
        # Exception caught; sweep continues
        assert result.enabled is True
        assert result.error is not None
        assert "RuntimeError" in result.error


# ─────────────────────────────────────────────────────────────────────
# (7) Policy slug non-clinical end-to-end
# ─────────────────────────────────────────────────────────────────────
class TestPolicySweepIntegration:
    def test_policy_medicare_drug_price_integration(
        self, tmp_path: Path, policy_template: dict,
        _log, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Integration smoke: policy slug with url_pattern-primary
        entities flows end-to-end. M-56 is stubbed to avoid
        network; coverage report has 5 entries."""
        monkeypatch.setenv("PG_V30_ENABLED", "1")
        import src.polaris_graph.retrieval.frame_fetcher as ff
        # Policy entities are url-primary → M-56 returns
        # METADATA_ONLY rows directly. For test clarity we just
        # stub them as ABSTRACT_ONLY with non-empty content so
        # synth validator marks them PASS.
        monkeypatch.setattr(
            ff, "fetch_compiled_frame",
            lambda bindings, **_: _stub_fetch_rows(
                _FakeCompiled(bindings)
            ),
        )

        from src.polaris_graph.v30_sweep_integration import (
            run_v30_post_generation,
        )
        result = run_v30_post_generation(
            research_question=(
                "What does the IRA drug price negotiation statute do?"
            ),
            scope_template=policy_template,
            slug="policy_medicare_drug_price",
            run_dir=tmp_path,
            log=_log,
        )

        cov = result.frame_coverage_report
        assert cov is not None
        assert cov["total_entities"] == 5
        assert cov["pass_count"] == 5
        # Non-clinical entity types present in coverage
        types = {e["entity_type"] for e in cov["entries"]}
        assert "statute" in types
        assert "court_decision" in types
        assert "regulatory_ruling" in types
        assert "cbo_report" in types
