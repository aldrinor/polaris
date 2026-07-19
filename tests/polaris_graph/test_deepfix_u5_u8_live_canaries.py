"""I-deepfix-001 (#1344) — offline RED->GREEN tests for the two LIVE-CANARY guards.

CANARY 1 (U5 synthesis-fires, fail-loud ABORT): at the run status-decision seam, a run whose
consolidation produced >=1 multi-source basket (verified_support_origin_count>=2) but whose
composition rendered ZERO multi-cited sentences (a pure span-dump) must ABORT
``abort_synthesis_did_not_fire`` instead of shipping the deficient report as ``success``. A
single-source corpus (0 multi-source baskets) must NEVER abort (synthesis is never FORCED, §-1.3).

CANARY 2 (U8 mineru-fires, fail-loud DISCLOSE): when mineru25 (the W4 GPU-VLM clinical-PDF winner)
was REQUESTED but recorded ZERO real GPU-VLM extractions (all clinical PDFs silently degraded to a
CPU fallback), the belt check surfaces a disclosed ``silent_degrade`` flag + disclosure string.

All pure-logic (no models, no network). Frozen faithfulness engine untouched; the banned
PG_SWEEP_ANALYST_SYNTHESIS path is NOT referenced.
"""

import ast
import pathlib
import types
import typing

import scripts.run_honest_sweep_r3 as sweep
from src.polaris_v6.schemas.run_status import PipelineStatus
from src.tools import access_bypass


def _regression_lab_status_tier_keys():
    """Read the ``_STATUS_TIERS`` dict KEYS (== KNOWN_STATUS_VALUES) from regression_lab.py via AST,
    WITHOUT importing the module — its import runs an artifact-registry build that needs gitignored
    ``outputs/`` dirs absent from a fresh worktree. Mirrors how
    tests/architecture/test_status_schema_parity_b23.py extracts KNOWN_STATUS_VALUES."""
    repo_root = pathlib.Path(sweep.__file__).resolve().parents[1]
    src = repo_root / "src" / "polaris_graph" / "audit_ir" / "regression_lab.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        # ``_STATUS_TIERS: dict[str, int] = {...}`` is an annotated assignment (ast.AnnAssign).
        is_tiers = (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_STATUS_TIERS"
        ) or (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_STATUS_TIERS" for t in node.targets)
        )
        if is_tiers and isinstance(node.value, ast.Dict):
            keys = {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
    return keys


# ── helpers to build fake COMPOSED-report / CONSOLIDATION shapes ──────────────────────────────────
def _tok(evidence_id):
    return types.SimpleNamespace(evidence_id=evidence_id, start=0, end=10)


def _sentence(evidence_ids):
    return types.SimpleNamespace(
        sentence="a verified declarative sentence.",
        tokens=[_tok(e) for e in evidence_ids],
    )


def _section(sentence_evidence_id_lists, *, dropped=False):
    return types.SimpleNamespace(
        title="Section",
        dropped_due_to_failure=dropped,
        kept_sentences_pre_resolve=[_sentence(ids) for ids in sentence_evidence_id_lists],
    )


def _basket(origin_count):
    return types.SimpleNamespace(verified_support_origin_count=origin_count)


def _credibility_analysis(origin_counts):
    return types.SimpleNamespace(baskets=[_basket(c) for c in origin_counts])


# ── CANARY 1 — U5 synthesis-fires ─────────────────────────────────────────────────────────────────
def test_status_abort_synthesis_did_not_fire_registered():
    """The new manifest verdict-status is registered in every taxonomy mirror (parity gate)."""
    assert "abort_synthesis_did_not_fire" in sweep.UNIFIED_STATUS_VALUES
    assert sweep.to_unified_status("abort_synthesis_did_not_fire") == "abort_synthesis_did_not_fire"
    assert sweep.to_unified_status("abort_synthesis_did_not_fire").startswith("abort_")
    assert "abort_synthesis_did_not_fire" in _regression_lab_status_tier_keys()
    assert "abort_synthesis_did_not_fire" in typing.get_args(PipelineStatus)


def test_span_dump_with_multi_source_baskets_aborts():
    """Baskets>0 (multi-source) but every rendered sentence single-cite => span-dump => ABORT."""
    sections = [
        _section([["ev1"], ["ev2"], ["ev3"]]),   # all single-cite
        _section([["ev4"]]),
    ]
    cred = _credibility_analysis([2, 3, 2])       # 3 multi-source baskets
    ms = sweep.count_multi_source_baskets(cred)
    mc = sweep.count_multi_cited_sentences(sections)
    assert ms == 3
    assert mc == 0
    assert sweep.synthesis_did_not_fire(
        multi_source_basket_count=ms, multi_cited_sentence_count=mc,
    ) is True
    manifest = {"status": "success", "release_allowed": True}
    summary_status, unified_status = sweep._apply_synthesis_fire_hold(
        manifest, multi_source_basket_count=ms, multi_cited_sentence_count=mc,
    )
    assert summary_status == "abort_synthesis_did_not_fire"
    assert unified_status == "abort_synthesis_did_not_fire"
    assert manifest["status"] == "abort_synthesis_did_not_fire"
    assert manifest["release_allowed"] is False
    assert manifest["synthesis_fire_canary"]["multi_source_baskets"] == 3
    assert manifest["synthesis_fire_canary"]["multi_cited_sentences"] == 0
    assert manifest["synthesis_fire_canary"]["aborted"] is True


def test_multi_cited_sentence_passes():
    """>=1 rendered sentence citing >=2 distinct evidence ids => synthesis fired => NO abort."""
    sections = [
        _section([["ev1", "ev2"], ["ev3"]]),      # first sentence is multi-cited (ev1+ev2)
        _section([["ev4"]]),
    ]
    cred = _credibility_analysis([2, 2])
    ms = sweep.count_multi_source_baskets(cred)
    mc = sweep.count_multi_cited_sentences(sections)
    assert ms == 2
    assert mc == 1
    assert sweep.synthesis_did_not_fire(
        multi_source_basket_count=ms, multi_cited_sentence_count=mc,
    ) is False


def test_single_source_corpus_does_not_abort():
    """0 multi-source baskets (single-source corpus) => NEVER abort, even with 0 multi-cited."""
    sections = [_section([["ev1"], ["ev2"]])]     # all single-cite
    cred = _credibility_analysis([1, 1, 1])       # every basket single-origin => 0 multi-source
    ms = sweep.count_multi_source_baskets(cred)
    mc = sweep.count_multi_cited_sentences(sections)
    assert ms == 0
    assert mc == 0
    assert sweep.synthesis_did_not_fire(
        multi_source_basket_count=ms, multi_cited_sentence_count=mc,
    ) is False


def test_dropped_section_multicite_not_counted():
    """A dropped-due-to-failure section's sentences never count toward the multi-cited total."""
    sections = [_section([["ev1", "ev2"]], dropped=True)]
    assert sweep.count_multi_cited_sentences(sections) == 0


def test_none_credibility_analysis_yields_zero_baskets():
    """No credibility pass (None) => 0 multi-source baskets => fail-open, never aborts."""
    assert sweep.count_multi_source_baskets(None) == 0


def test_synthesis_fire_canary_enabled_default_on(monkeypatch):
    monkeypatch.delenv("PG_SYNTHESIS_FIRE_CANARY", raising=False)
    assert sweep.synthesis_fire_canary_enabled() is True
    monkeypatch.setenv("PG_SYNTHESIS_FIRE_CANARY", "0")
    assert sweep.synthesis_fire_canary_enabled() is False


def test_multicited_compose_gate_default_off(monkeypatch):
    """The canary self-skips when the multi-cite compose path is OFF (single-cite expected)."""
    monkeypatch.delenv("PG_VERIFIED_COMPOSE_MULTICITED", raising=False)
    assert sweep._multicited_compose_on() is False
    monkeypatch.setenv("PG_VERIFIED_COMPOSE_MULTICITED", "1")
    assert sweep._multicited_compose_on() is True


# ── CANARY 2 — U8 mineru-fires ──────────────────────────────────────────────────────────────────
def test_mineru_silent_degrade_flagged():
    """mineru25 requested, ZERO GPU-VLM wins, >=1 degrade => silent_degrade True + disclosure set."""
    winner_status = {
        "requested": True,
        "degraded": True,
        "fallback_count": 3,
        "win_count": 0,
        "reasons": {"no_gpu": 3},
        "selected_extractors": ["docling"],
        "source": "tool_trace.pdf_extract",
    }
    out = access_bypass.mineru_silent_degrade_disclosure(winner_status)
    assert out["mineru_expected"] is True
    assert out["gpu_vlm_extractions"] == 0
    assert out["clinical_pdf_degrades"] == 3
    assert out["silent_degrade"] is True
    assert out["disclosure"] and "clinical_pdf_extractor_all_degraded" in out["disclosure"]


def test_mineru_win_not_flagged():
    """>=1 real GPU-VLM extraction => not a silent degrade (winner genuinely fired at least once)."""
    winner_status = {
        "requested": True, "degraded": True, "fallback_count": 1, "win_count": 2,
        "reasons": {"mineru25_timeout": 1}, "selected_extractors": ["docling"],
    }
    out = access_bypass.mineru_silent_degrade_disclosure(winner_status)
    assert out["gpu_vlm_extractions"] == 2
    assert out["silent_degrade"] is False
    assert out["disclosure"] is None


def test_mineru_docling_baseline_not_flagged():
    """mineru25 never requested (docling baseline) => not a degrade."""
    winner_status = {
        "requested": False, "degraded": False, "fallback_count": 0, "win_count": 0,
        "reasons": {}, "selected_extractors": [],
    }
    out = access_bypass.mineru_silent_degrade_disclosure(winner_status)
    assert out["mineru_expected"] is False
    assert out["silent_degrade"] is False
    assert out["disclosure"] is None


def test_mineru_empty_status_safe():
    """A None / empty winner-status never raises and never falsely flags a degrade."""
    out = access_bypass.mineru_silent_degrade_disclosure(None)
    assert out["silent_degrade"] is False
    assert out["disclosure"] is None


def test_mineru_fire_canary_enabled_default_on(monkeypatch):
    monkeypatch.delenv("PG_MINERU_FIRE_CANARY", raising=False)
    assert access_bypass.mineru_degrade_canary_enabled() is True
    monkeypatch.setenv("PG_MINERU_FIRE_CANARY", "0")
    assert access_bypass.mineru_degrade_canary_enabled() is False
