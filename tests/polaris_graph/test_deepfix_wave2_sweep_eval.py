"""I-deepfix-001 WAVE-2 behavioral fail-loud tests for WIRER-SWEEP-EVAL (#1344).

These assert each seam's effect APPEARS in real output / behavior (§-1.4), flipping the seam's flag
ON and checking the change actually fires. They cover the OFFLINE-provable seams:

  B6(b)  — claim-shape gate suppresses a non-assertional corroboration HEADER (no source dropped).
  B4     — PT03 honest two-family check + the run-script disclosure clause shared-literal contract +
           the UI family-segregation badges (no longer hardcoded True).
  B11 C1 — apply_provider_routing injects per-role provider SLO prefs from config.
  B11 C2 — the min-tok/s SLO arming + pure tok/s predicate (the live adjudicated-flip needs a paid run).
  P2b    — (covered by an existence assert on the constraints serialization in the source).

The run-script functions are loaded via importlib (the script has an ``if __name__ == '__main__'``
guard and no heavy import-time work) so this test does NOT depend on the heavy registry conftest.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_run_script():
    path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    spec = importlib.util.spec_from_file_location("_rhs_wave2_test", path)
    assert spec and spec.loader, f"cannot load spec for {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# B6(b) — claim-shape gate (run_honest_sweep_r3)
# ---------------------------------------------------------------------------


def test_b6b_gate_enabled_by_default(monkeypatch):
    monkeypatch.delenv("PG_CLAIM_SHAPE_GATE", raising=False)
    rhs = _load_run_script()
    assert rhs.claim_shape_gate_enabled() is True


def test_b6b_assertional_claim_is_renderable(monkeypatch):
    monkeypatch.setenv("PG_CLAIM_SHAPE_GATE", "1")
    rhs = _load_run_script()
    # A real assertional claim — with OR without a terminal period — must PASS (no regression of the
    # 154/155 trimmed-summary header recovery).
    assert rhs.claim_is_renderable_claim_shape(
        "Tirzepatide reduced HbA1c by 2.1 percent in adults with type 2 diabetes"
    )
    assert rhs.claim_is_renderable_claim_shape(
        "Semaglutide is associated with weight loss in obese patients."
    )


def test_b6b_nonassertional_fragments_suppressed(monkeypatch):
    monkeypatch.setenv("PG_CLAIM_SHAPE_GATE", "1")
    rhs = _load_run_script()
    # ccid hash stub, web chrome, and an empty string are NOT renderable assertional claims.
    assert not rhs.claim_is_renderable_claim_shape("clm_a1b2c3d4")
    assert not rhs.claim_is_renderable_claim_shape(
        "URL Source: https://x.com Published Time: 2020 Markdown Content:"
    )
    assert not rhs.claim_is_renderable_claim_shape("")
    # A bare noun phrase with too few content words is suppressed.
    assert not rhs.claim_is_renderable_claim_shape("Diabetes care")


def test_b6b_corroboration_block_drops_chrome_header_keeps_real_claim(monkeypatch):
    """END-TO-END behavioral (§-1.3 no-source-dropped): a bibliography carrying TWO baskets — one a
    real claim, one a chrome stub — renders BOTH baskets, but the chrome basket's garbled claim HEADER
    is replaced by a NEUTRAL count-only header while its SUPPORT source line is STILL emitted (the
    corroborating source + count are never dropped — only the cosmetic claim text is withheld).
    FAIL-LOUD on the garbled chrome header text leaking in AS a verified claim."""
    monkeypatch.setenv("PG_CLAIM_SHAPE_GATE", "1")
    rhs = _load_run_script()
    real_member = {
        "member_tier": "ENTAILMENT_VERIFIED",
        "source_url": "https://example.org/rct",
        "source_tier": "T1",
        "credibility_weight": 0.9,
    }
    chrome_member = {
        "member_tier": "ENTAILMENT_VERIFIED",
        "source_url": "https://chrome.example/x",
        "source_tier": "T5",
        "credibility_weight": 0.2,
    }
    bibliography = [
        {
            "statement": "A real source",
            "baskets": [
                {
                    "claim_cluster_id": "c_real",
                    # terminal period so the EXISTING fallback chain keeps it as a sentence (an
                    # un-terminated trimmed summary is mangled to its ccid by the pre-existing
                    # _claim_header_is_unrenderable path, independent of this gate).
                    "claim_text": "Tirzepatide reduced HbA1c by 2.1 percent versus placebo.",
                    "verified_support_origin_count": 1,
                    "supporting_members": [real_member],
                },
                {
                    "claim_cluster_id": "c_chrome",
                    # pure chrome / non-assertional — no fallback can rescue a real claim
                    "claim_text": "URL Source: https://x.com Published Time: 2020 Markdown Content:",
                    "subject": "",
                    "predicate": "",
                    "verified_support_origin_count": 1,
                    "supporting_members": [chrome_member],
                },
            ],
        }
    ]
    block = rhs._basket_corroboration_block(bibliography)
    # The real claim's header + its SUPPORT line appear (the block is non-empty -> a real claim
    # survived, proving the gate did not over-suppress everything).
    assert block.strip(), "the whole corroboration block was suppressed (over-suppression bug)"
    assert "Tirzepatide reduced HbA1c by 2.1 percent" in block
    assert "https://example.org/rct" in block
    # The chrome basket's garbled claim HEADER is suppressed — neither the chrome text nor its hash id
    # appears as a "verified claim" header.
    assert "Markdown Content" not in block
    assert "c_chrome" not in block
    # §-1.3 no-source-dropped: the chrome basket's SUPPORT source line IS STILL emitted (under a
    # neutral count-only header) — only the cosmetic claim header text was withheld, never the source.
    assert "https://chrome.example/x" in block
    assert "verified independent source(s)" in block


def test_b6b_off_renders_chrome_header(monkeypatch):
    """Kill-switch proof: with the gate OFF, the chrome basket is NOT suppressed (legacy behavior)."""
    monkeypatch.setenv("PG_CLAIM_SHAPE_GATE", "0")
    rhs = _load_run_script()
    bibliography = [
        {
            "statement": "src",
            "baskets": [
                {
                    "claim_cluster_id": "c_chrome",
                    "claim_text": "URL Source: https://x.com Published Time: 2020 Markdown Content:",
                    "subject": "topic",
                    "predicate": "label",
                    "verified_support_origin_count": 1,
                    "supporting_members": [
                        {
                            "member_tier": "ENTAILMENT_VERIFIED",
                            "source_url": "https://chrome.example/x",
                            "source_tier": "T5",
                            "credibility_weight": 0.2,
                        }
                    ],
                }
            ],
        }
    ]
    block = rhs._basket_corroboration_block(bibliography)
    # Gate OFF -> the basket renders (the source line is present), proving the gate is what suppresses.
    assert "https://chrome.example/x" in block


# ---------------------------------------------------------------------------
# B4 — run-script disclosure clause shared-literal contract (sweep leg) + PT03
# ---------------------------------------------------------------------------

_PT03_SHARED_LITERAL_TOKENS = (
    "not family-segregated",
    "same family",
    "self-bias safeguard disabled",
)


def test_b4_disclosure_clause_shared_literals_present():
    rhs = _load_run_script()
    clause = rhs.eval_family_disclosure_clause("glm", "glm", permit_same_family=True)
    lowered = clause.lower()
    for tok in _PT03_SHARED_LITERAL_TOKENS:
        assert tok in lowered, f"missing shared-literal token {tok!r}"


def test_b4_pt03_distinct_families_pass():
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks

    report = "Methods: evaluator model qwen/qwen3.6-35b-a3b; distinct training families."
    res, _, _ = run_rule_checks(
        report_text=report, protocol={}, tier_distribution_report=None, contradictions=[],
        evidence_pool={}, generator_model="deepseek/deepseek-v4-pro",
        evaluator_model="qwen/qwen3.6-35b-a3b", generator_family="deepseek", evaluator_family="qwen",
    )
    pt03 = next(r for r in res if r.item_id == "PT03")
    assert pt03.passed is True


def test_b4_pt03_same_family_no_override_fails(monkeypatch):
    monkeypatch.delenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", raising=False)
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks

    # Even with the disclosure tokens in the report, NO override -> FAIL (no silent self-verify pass).
    report = (
        "evaluator glm/glm-5.2; NOT family-segregated; same family; self-bias safeguard disabled."
    )
    res, _, _ = run_rule_checks(
        report_text=report, protocol={}, tier_distribution_report=None, contradictions=[],
        evidence_pool={}, generator_model="z-ai/glm-5.2", evaluator_model="glm/glm-5.2",
        generator_family="glm", evaluator_family="glm",
    )
    pt03 = next(r for r in res if r.item_id == "PT03")
    assert pt03.passed is False


def test_b4_pt03_same_family_override_with_disclosure_passes(monkeypatch):
    monkeypatch.setenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", "1")
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks

    report = (
        "evaluator glm/glm-5.2; NOT family-segregated; same family; self-bias safeguard disabled."
    )
    res, _, _ = run_rule_checks(
        report_text=report, protocol={}, tier_distribution_report=None, contradictions=[],
        evidence_pool={}, generator_model="z-ai/glm-5.2", evaluator_model="glm/glm-5.2",
        generator_family="glm", evaluator_family="glm",
    )
    pt03 = next(r for r in res if r.item_id == "PT03")
    assert pt03.passed is True


def test_b4_pt03_same_family_override_without_disclosure_fails(monkeypatch):
    monkeypatch.setenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", "1")
    from src.polaris_graph.evaluator.external_evaluator import run_rule_checks

    # Override set but the report does NOT honestly disclose -> still FAIL.
    report = "evaluator glm/glm-5.2 mentioned in passing."
    res, _, _ = run_rule_checks(
        report_text=report, protocol={}, tier_distribution_report=None, contradictions=[],
        evidence_pool={}, generator_model="z-ai/glm-5.2", evaluator_model="glm/glm-5.2",
        generator_family="glm", evaluator_family="glm",
    )
    pt03 = next(r for r in res if r.item_id == "PT03")
    assert pt03.passed is False


# ---------------------------------------------------------------------------
# B11 C1 — provider SLO preferences merged into the routing block
# ---------------------------------------------------------------------------


def test_b11_c1_slo_injected_when_enabled(monkeypatch):
    from src.polaris_graph.roles import provider_routing as pr

    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_SLO", "1")
    pr.reset_cache()
    block = pr.apply_provider_routing({"require_parameters": True}, "sentinel")
    assert block.get("min_throughput") == 5.0
    assert block.get("max_latency") == 30.0


def test_b11_c1_slo_off_is_noop(monkeypatch):
    from src.polaris_graph.roles import provider_routing as pr

    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_SLO", "0")
    pr.reset_cache()
    block = pr.apply_provider_routing({"require_parameters": True}, "sentinel")
    assert "min_throughput" not in block
    assert "max_latency" not in block


def test_b11_c1_role_without_slo_keys_noop(monkeypatch):
    from src.polaris_graph.roles import provider_routing as pr

    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_SLO", "1")
    pr.reset_cache()
    # judge config carries NO preferred_* keys -> no SLO injected.
    assert pr.role_provider_slo("judge") is None


# ---------------------------------------------------------------------------
# B11 C2 — min-tok/s SLO arming + pure throughput predicate
# ---------------------------------------------------------------------------


def test_b11_c2_off_by_default(monkeypatch):
    from src.polaris_graph.roles import openrouter_role_transport as T

    monkeypatch.delenv("PG_ROLE_MIN_TPS", raising=False)
    assert T.role_min_tps() == 0.0
    assert T.role_min_tps_rotation_enabled() is False


def test_b11_c2_armed_requires_floor_and_rotation(monkeypatch):
    from src.polaris_graph.roles import openrouter_role_transport as T

    monkeypatch.setenv("PG_ROLE_MIN_TPS", "8")
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    assert T.role_min_tps() == 8.0
    assert T.role_min_tps_rotation_enabled() is True
    # rotation OFF -> not armed even with a floor set
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "0")
    assert T.role_min_tps_rotation_enabled() is False


def test_b11_c2_tps_predicate_pure():
    from src.polaris_graph.roles import openrouter_role_transport as T

    assert T._observed_tokens_per_second({"completion_tokens": 100}, 10.0) == 10.0
    # unknown throughput -> None (fail-open: never rotated)
    assert T._observed_tokens_per_second(None, 10.0) is None
    assert T._observed_tokens_per_second({"completion_tokens": 100}, 0.0) is None
    assert T._observed_tokens_per_second({"completion_tokens": 0}, 5.0) is None


# ---------------------------------------------------------------------------
# P2b — constraints serialized into summary + manifest (source-level assert)
# ---------------------------------------------------------------------------


def test_p2b_constraints_serialized_in_source():
    path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    src = path.read_text(encoding="utf-8")
    # Both the summary AND the manifest intent_frame block now serialize constraints.
    assert src.count('"constraints": list(intent_frame_advisory.constraints)') == 2


# ---------------------------------------------------------------------------
# B4 — UI family-segregation badges are DERIVED, not hardcoded True
# ---------------------------------------------------------------------------


def test_b4_ui_badges_not_hardcoded_true():
    for rel in (
        "src/polaris_v6/api/artifact_to_slice_chain.py",
        "src/polaris_graph/clinical_generator/generator.py",
    ):
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "family_segregation_passed=True" not in src, (
            f"{rel} still hardcodes the family-segregation badge True"
        )


def test_b4_ui_badge_derivation_is_honest():
    from src.polaris_graph.llm.openrouter_client import family_from_model

    # The deterministic verifier maps to a DIFFERENT family than any real generator -> honestly True.
    assert family_from_model("deepseek/deepseek-v4-pro") != family_from_model("strict_verify_v1")
    assert family_from_model("z-ai/glm-5.2") != family_from_model("strict_verify_v1")
    # A genuine same-family LLM pair (both z-ai/glm lineage) correctly reads False (badge flags the
    # breach instead of a benign green lie).
    assert not (family_from_model("z-ai/glm-5.2") != family_from_model("z-ai/glm-5.1"))


# ---------------------------------------------------------------------------
# B3 — clean-question substitution wired at the decompose/retrieval/planner sites
# ---------------------------------------------------------------------------


def test_b3_clean_question_substituted_at_backend_sites():
    src = (_REPO_ROOT / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8")
    # init to raw (byte-identical OFF-mode) then overridden inside the frame block.
    assert "_clean_question = q[\"question\"]" in src
    assert "_clean_question = \" \".join(_frame_questions)" in src
    # the backend query sites now fire the clean question.
    assert "plan_research(\n                _clean_question" in src
    assert "decompose_question(_clean_question)" in src
    assert "expand_regulatory_queries(_clean_question" in src
    assert "research_question=_clean_question," in src


def test_b3_clean_question_threaded_to_backend_retrieval_seeds():
    """P1-B: the clean question reaches the FS-Researcher/IterResearch seeds, the CRAG gap-retrieval
    loop-back, and the R6 expansion — not only the planner/decompose/primary-retrieval sites. The raw
    q["question"] (which may carry an injected directive appendix) must no longer seed those paths."""
    src = (_REPO_ROOT / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8")
    # FS-Researcher AND IterResearch generators now derive queries from the CLEAN question (both seeds).
    assert "_clean_question, _iter_llm, _iter_per_query_retrieve, _IterLRR" in src
    assert 'q["question"], _iter_llm, _iter_per_query_retrieve, _IterLRR' not in src
    # CRAG gap-derivation + CRAG loop-back retrieval + R6 expansion + primary retrieval all fire clean.
    # (primary 1 + FS/Iter scope-context 1 + CRAG derive 1 + CRAG loop-back 1 + R6 expansion 1 = 5)
    assert src.count("research_question=_clean_question,") >= 5
    # the CRAG no-gap fallback re-issues the CLEAN question, never the raw one.
    assert "_gap_queries = [_clean_question]" in src
    assert '_gap_queries = [q["question"]]' not in src


# ---------------------------------------------------------------------------
# B11 C2 P2-A — fail-open: a slow-but-valid response is KEPT when no other provider remains
# ---------------------------------------------------------------------------


def test_b11_c2_p2a_nonignored_provider_remains():
    from src.polaris_graph.roles import openrouter_role_transport as T

    # Two providers, none ignored -> ignoring the slow head still leaves one -> rotate is allowed.
    body_two = {"provider": {"order": ["alpha", "beta"], "ignore": []}}
    assert T._nonignored_provider_remains(body_two, also_ignore="alpha") is True
    # Single provider -> ignoring it leaves NONE -> fail-open (keep the valid slow verdict).
    body_one = {"provider": {"order": ["alpha"], "ignore": []}}
    assert T._nonignored_provider_remains(body_one, also_ignore="alpha") is False
    # Last remaining provider when the other is already ignored -> also fail-open.
    body_one_ignored = {"provider": {"order": ["alpha", "beta"], "ignore": ["beta"]}}
    assert T._nonignored_provider_remains(body_one_ignored, also_ignore="alpha") is False
    # No routing block / no order -> never rotate (fail-open).
    assert T._nonignored_provider_remains({}, also_ignore="alpha") is False
    assert T._nonignored_provider_remains({"provider": {}}, also_ignore="alpha") is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
