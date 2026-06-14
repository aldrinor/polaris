"""I-ready-012 (#1079) — semantic/NLI cross-document contradiction detector.

Closes the F12 recall hole: a prose-only directional contradiction with NO shared number and NO
NegEx cue ("adjuvant chemotherapy improved overall survival" vs "...provided no overall survival
benefit") passes both the numeric and qualitative rule detectors silently. This detector adds an
LLM-NLI pass (default OFF, fail-open, additive) that catches it and routes the conflict into the
existing report disclosure + PT08 release gate.

All offline: the judge is INJECTED (a fake), so no network / no model. Verifies recall, precision,
flag-OFF inertness, every fail-open path (per-pair error + BudgetExceededError keep-partial), the
pair cap, the audit_ir.loader compatibility (Codex iter-1 P2), and the real PT08 routing (Codex
iter-1 P1: semantic records must actually reach the PT08 evaluator gate).
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.llm.openrouter_client import BudgetExceededError
from src.polaris_graph.retrieval import semantic_conflict_detector as scd

# The reproduced recall-hole pair: prose-only, no shared number, no NegEx cue.
_ROW_A = {
    "evidence_id": "ev_a", "tier": "T1", "source_url": "u1",
    "direct_quote": "Adjuvant chemotherapy improved overall survival in stage II colon cancer.",
}
_ROW_B = {
    "evidence_id": "ev_b", "tier": "T1", "source_url": "u2",
    "direct_quote": "Adjuvant chemotherapy provided no overall survival benefit in stage II colon cancer.",
}


def _contradict_judge(a, b):
    return "contradict", 0.95


def _neutral_judge(a, b):
    return "neutral", 0.9


# ───────────────────────────── recall: the hole closes ──────────────────────────────

def test_cluster_groups_the_reproduced_rows_before_any_judge():
    """The recall-oriented clustering (independent of the rule extractors) must put the two
    prose-only rows in ONE candidate cluster — BEFORE the judge is ever invoked."""
    clusters = scd.cluster_candidate_rows([_ROW_A, _ROW_B])
    assert len(clusters) == 1
    assert {r["evidence_id"] for r in clusters[0]} == {"ev_a", "ev_b"}


def test_detect_emits_one_semantic_record_on_contradict():
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    records = scd.detect_semantic_conflicts(pairs, _contradict_judge)
    assert len(records) == 1
    rec = records[0]
    assert rec.type == "semantic"
    assert rec.severity == "review"
    assert rec.subject  # non-empty (PT08 substring source)
    assert rec.predicate
    assert {c["evidence_id"] for c in rec.claims} == {"ev_a", "ev_b"}
    assert rec.nli_confidence == pytest.approx(0.95)


def test_end_to_end_for_rows_with_injected_judge():
    records = scd.detect_semantic_conflicts_for_rows([_ROW_A, _ROW_B], judge=_contradict_judge)
    assert len(records) == 1
    assert "survival" in records[0].subject


# ───────────────────────────── precision ──────────────────────────────

def test_neutral_or_entail_pair_yields_no_record():
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    assert scd.detect_semantic_conflicts(pairs, _neutral_judge) == []
    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("entail", 0.99)) == []


def test_low_confidence_contradict_is_filtered():
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    # below the 0.7 default threshold → dropped
    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("contradict", 0.4)) == []


@pytest.mark.parametrize("bad_conf", [float("nan"), float("inf"), -0.1, 1.5])
def test_non_finite_or_out_of_range_confidence_never_fabricates(bad_conf):
    """Codex diff-gate P2: a NaN/inf/out-of-range confidence from a malformed judge must NOT pass
    the threshold and create a phantom contradiction (which would falsely abort a run via PT08)."""
    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    assert scd.detect_semantic_conflicts(pairs, lambda a, b: ("contradict", bad_conf)) == []


# ───────────────────────────── flag-OFF inertness ──────────────────────────────

def test_enabled_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_NLI_CONFLICT", raising=False)
    assert scd.semantic_conflict_enabled() is False
    for off in ("0", "false", "off", "no", ""):
        monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", off)
        assert scd.semantic_conflict_enabled() is False
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT", "1")
    assert scd.semantic_conflict_enabled() is True


def test_for_rows_never_constructs_a_judge_when_no_pairs(monkeypatch):
    """Unrelated rows (no shared salient words) → no cluster → no pairs → the default judge
    factory is NEVER called (no network even if somehow ON)."""
    def _boom():
        raise AssertionError("default judge must not be constructed when there are no pairs")
    monkeypatch.setattr(scd, "get_default_judge", _boom)
    rows = [
        {"evidence_id": "x", "tier": "T1", "direct_quote": "Quantum entanglement decoheres rapidly."},
        {"evidence_id": "y", "tier": "T1", "direct_quote": "Maple syrup grades reflect color."},
    ]
    assert scd.detect_semantic_conflicts_for_rows(rows) == []


# ───────────────────────────── fail-open ──────────────────────────────

def test_per_pair_judge_error_is_skipped_not_fatal():
    rows = [_ROW_A, _ROW_B,
            {"evidence_id": "ev_c", "tier": "T2",
             "direct_quote": "Adjuvant chemotherapy overall survival benefit was confirmed in colon cancer."}]
    pairs = scd.extract_pairs(scd.cluster_candidate_rows(rows))
    calls = {"n": 0}

    def _flaky(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient judge error")
        return "contradict", 0.9

    records = scd.detect_semantic_conflicts(pairs, _flaky)
    # first pair errored (skipped), remaining pairs still judged → at least one record
    assert len(records) >= 1


def test_budget_exceeded_keeps_partial_and_stops():
    rows = [_ROW_A, _ROW_B,
            {"evidence_id": "ev_c", "tier": "T2",
             "direct_quote": "Adjuvant chemotherapy overall survival in stage II colon cancer was worse."}]
    pairs = scd.extract_pairs(scd.cluster_candidate_rows(rows))
    assert len(pairs) >= 2
    calls = {"n": 0}

    def _budget_then_more(a, b):
        calls["n"] += 1
        if calls["n"] == 1:
            return "contradict", 0.9
        raise BudgetExceededError("run budget cap reached")

    records = scd.detect_semantic_conflicts(pairs, _budget_then_more)
    assert len(records) == 1            # pair-1 kept
    assert calls["n"] == 2              # stopped at the breach (did not judge pair 3+)


# ───────────────────────────── cost bound ──────────────────────────────

def test_pair_cap_is_honored(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_NLI_CONFLICT_MAX_PAIRS", "3")
    # 6 same-cluster rows → 15 raw pairs, capped to 3.
    rows = [
        {"evidence_id": f"e{i}", "tier": "T1",
         "direct_quote": f"Adjuvant chemotherapy overall survival colon cancer finding number {i}."}
        for i in range(6)
    ]
    clusters = scd.cluster_candidate_rows(rows)
    pairs = scd.extract_pairs(clusters, max_pairs=3)
    assert len(pairs) == 3


# ───────────────────────────── routing (Codex iter-1 P1-2) ──────────────────────────────

def test_pt08_gate_counts_a_semantic_record_real_evaluator():
    """The REAL PT08 check must treat a semantic record like a numeric one: disclosed
    (subject+predicate in report text) → pass; not disclosed → fail. Proves the record reaches
    and is gated by the evaluator, not just written to contradictions.json."""
    from src.polaris_graph.evaluator.external_evaluator import run_external_evaluation
    from dataclasses import asdict

    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    rec = scd.detect_semantic_conflicts(pairs, _contradict_judge)[0]
    contra = [asdict(rec)]
    protocol = {"research_question": "q", "date_range": {}}

    disclosed = (
        f"## Semantic contradiction disclosures\n- [SEMANTIC] {rec.subject} / {rec.predicate}: "
        f"claim A VS claim B\n"
    )
    out_ok = run_external_evaluation(
        report_text=disclosed, protocol=protocol, tier_distribution_report={},
        contradictions=contra, evidence_pool={}, enable_llm_judge=False,
    )
    out_missing = run_external_evaluation(
        report_text="A report with no contradiction disclosure at all.",
        protocol=protocol, tier_distribution_report={},
        contradictions=contra, evidence_pool={}, enable_llm_judge=False,
    )
    pt08_ok = next(r for r in out_ok.rule_checks if r.item_id == "PT08")
    pt08_missing = next(r for r in out_missing.rule_checks if r.item_id == "PT08")
    assert pt08_ok.passed is True
    assert pt08_missing.passed is False


# ───────────────────────────── audit_ir.loader compat (Codex iter-1 P2) ──────────────────────────────

def test_semantic_record_is_audit_ir_loader_compatible():
    """A contradictions.json holding a semantic record must parse — _parse_contradiction_claim
    REQUIRES evidence_id + predicate + finite value on every claim."""
    from dataclasses import asdict
    from src.polaris_graph.audit_ir import loader

    pairs = scd.extract_pairs(scd.cluster_candidate_rows([_ROW_A, _ROW_B]))
    rec = scd.detect_semantic_conflicts(pairs, _contradict_judge)[0]
    raw = json.loads(json.dumps([asdict(rec)]))  # round-trip exactly like the on-disk file
    clusters = loader._parse_contradictions(raw)
    assert len(clusters) == 1
    assert len(clusters[0].claims) == 2
    for c in clusters[0].claims:
        assert c.evidence_id
        assert c.predicate
        assert c.value == pytest.approx(0.0)  # finite sentinel (prose has no numeric value)


# ───────────────────── F09: NLI conflict judge pins the MIRROR provider chain ─────────────────────


class _CaptureClient:
    """Mock httpx.Client capturing the posted request body; returns a valid CONTRADICT verdict."""

    def __init__(self):
        self.body = None

    def post(self, url, headers=None, json=None):
        self.body = json

        class _Resp:
            def raise_for_status(self_inner):
                return None

            def json(self_inner):
                return {
                    "choices": [{"message": {"content": '{"verdict": "NEUTRAL", "confidence": 0.0}'}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0.001},
                }

        return _Resp()


def test_conflict_judge_pins_mirror_chain_when_gate_active(monkeypatch):
    # I-arch-004 F09: the NLI conflict side-judge must pin to the MIRROR role's resolved provider
    # (the locked GLM-5.1 chain), NOT the RETIRED "evaluator" role. role_provider_map only carries
    # generator/mirror/sentinel/judge; "evaluator" is absent -> get_role_provider("evaluator") == None
    # -> NO pin -> free-route. Assert the judge looks up "mirror" and pins it singleton-no-fallback.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")  # glm != deepseek => family ok
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)
    judge._client = _CaptureClient()
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    looked_up = []

    def _fake_get_role_provider(role):
        looked_up.append(role)
        return "novita" if role == "mirror" else None

    monkeypatch.setattr(_pathb, "get_role_provider", _fake_get_role_provider)
    judge.judge("claim a", "claim b")
    assert judge._client.body["provider"] == {
        "order": ["novita"], "allow_fallbacks": False, "require_parameters": True}
    assert "mirror" in looked_up
    assert "evaluator" not in looked_up


def test_conflict_judge_retired_evaluator_key_does_not_free_route(monkeypatch):
    # I-arch-004 F09 regression guard: BEFORE the fix the judge looked up "evaluator", which the locked
    # 4-role role_provider_map never carries -> None -> NO provider pin -> free-route. Mimic the real
    # map shape (only the 4 locked roles populated) and prove the judge now PINS the mirror chain.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)
    judge._client = _CaptureClient()
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    role_map = {"generator": "fireworks", "mirror": "novita",
                "sentinel": "deepinfra", "judge": "together"}
    monkeypatch.setattr(_pathb, "get_role_provider", lambda role: role_map.get(role))
    judge.judge("claim a", "claim b")
    assert judge._client.body["provider"]["order"] == ["novita"]
    assert judge._client.body["provider"]["allow_fallbacks"] is False
    assert judge._client.body["provider"]["require_parameters"] is True


# ───────────────── I-arch-004 F19 (§9.1.8): token cap == the GLM-5.1 mirror-chain model max ────────


def test_conflict_judge_max_tokens_defaults_to_mirror_chain_model_max(monkeypatch):
    # F19: the posted body MUST carry the model REAL max (the pinned mirror-chain MIN
    # max_completion_tokens = 131072, live OpenRouter read 2026-06-14), NOT the old small 2000 hardcode.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.delenv("PG_SEMANTIC_CONFLICT_MAX_TOKENS", raising=False)
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)
    judge._client = _CaptureClient()
    judge.judge("claim a", "claim b")
    assert judge._client.body["max_tokens"] == scd._CONFLICT_MAX_TOKENS_CHAIN_MIN == 131072
    # Reasoning effort stays "high" (NOT xhigh — the GLM bake-off proved xhigh blanks). Never starved.
    assert judge._client.body["reasoning"] == {"effort": "high"}


def test_conflict_judge_max_tokens_env_override_clamped_to_chain_ceiling(monkeypatch):
    # F19: an env override ABOVE the chain MIN is CLAMPED DOWN (would otherwise hard-400 under
    # allow_fallbacks=False); a value BELOW is honored verbatim.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)
    judge._client = _CaptureClient()
    monkeypatch.setenv("PG_SEMANTIC_CONFLICT_MAX_TOKENS", "999999")
    judge.judge("claim a", "claim b")
    assert judge._client.body["max_tokens"] == 131072  # clamped to the chain ceiling

    monkeypatch.setenv("PG_SEMANTIC_CONFLICT_MAX_TOKENS", "4096")
    judge.judge("claim a", "claim b")
    assert judge._client.body["max_tokens"] == 4096  # below ceiling -> honored
