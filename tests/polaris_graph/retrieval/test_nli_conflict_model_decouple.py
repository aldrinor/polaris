"""I-deepfix-001 FIX-1 (judge-429 relief) — side-judge model decouple + conditional pin.

Proves:
  1. PG_NLI_CONFLICT_MODEL OVERRIDES the nli/semantic-conflict SIDE judge's model.
  2. The CORE strict_verify entailment judge STILL reads PG_ENTAILMENT_MODEL and IGNORES
     PG_NLI_CONFLICT_MODEL (faithfulness engine untouched — the decouple).
  3. With PG_NLI_CONFLICT_MODEL unset, the side judge falls back to PG_ENTAILMENT_MODEL
     (OFF path byte-identical).
  4. When the side judge is OFFLOADED to a NON-glm model, it FREE-ROUTES (no glm-only mirror
     provider pin) so it does not 404 under allow_fallbacks:false.
  5. When the side-judge model still MATCHES the glm mirror, the mirror provider pin is applied
     UNCHANGED.

All offline: constructing a judge makes NO network call; test 4/5 intercept the transport POST
to inspect the outbound request body without hitting OpenRouter.
"""

from __future__ import annotations

import copy


def _common_env(monkeypatch):
    # No real key needed (no network); construction only requires the var to be present.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-offline")
    # generator + these glm judges are the same family under the all-GLM run; permit it so the
    # two-family guard does not raise at construction (matches production PG_PERMIT flag).
    monkeypatch.setenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", "1")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")


def test_side_judge_reads_nli_conflict_model_override(monkeypatch):
    _common_env(monkeypatch)
    monkeypatch.setenv("PG_NLI_CONFLICT_MODEL", "moonshotai/kimi-k2.6")
    from src.polaris_graph.retrieval.semantic_conflict_detector import (
        _SemanticContradictionJudge,
    )

    judge = _SemanticContradictionJudge()
    assert judge._model == "moonshotai/kimi-k2.6"


def test_entailment_judge_ignores_nli_conflict_model(monkeypatch):
    _common_env(monkeypatch)
    monkeypatch.setenv("PG_NLI_CONFLICT_MODEL", "moonshotai/kimi-k2.6")
    from src.polaris_graph.llm.entailment_judge import _EntailmentJudge

    ej = _EntailmentJudge()
    # The faithfulness-critical entailment judge stays governed by PG_ENTAILMENT_MODEL and is
    # NOT moved by the side-judge offload env.
    assert ej._model == "z-ai/glm-5.2"


def test_side_judge_falls_back_to_entailment_model_when_unset(monkeypatch):
    _common_env(monkeypatch)
    monkeypatch.delenv("PG_NLI_CONFLICT_MODEL", raising=False)
    from src.polaris_graph.retrieval.semantic_conflict_detector import (
        _SemanticContradictionJudge,
    )

    judge = _SemanticContradictionJudge()
    # OFF path: identical to the pre-fix expression (PG_ENTAILMENT_MODEL else glm-5.2 default).
    assert judge._model == "z-ai/glm-5.2"


def _capture_post_body(monkeypatch, scd):
    captured: list[dict] = []

    def _fake_post(client, endpoint, headers, json_body, total_s):  # noqa: ANN001
        captured.append(copy.deepcopy(json_body))
        raise RuntimeError("stop-after-capture")

    monkeypatch.setattr(scd, "_post_with_total_deadline", _fake_post)
    return captured


def test_offloaded_non_glm_model_free_routes_off_mirror_pin(monkeypatch):
    _common_env(monkeypatch)
    # rotation ON makes the glm mirror pin deterministic when the model MATCHES the mirror;
    # the offload must still bypass it.
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    monkeypatch.setenv("PG_NLI_CONFLICT_MODEL", "moonshotai/kimi-k2.6")
    import src.polaris_graph.retrieval.semantic_conflict_detector as scd
    from src.polaris_graph.roles import provider_routing

    provider_routing.reset_cache()
    captured = _capture_post_body(monkeypatch, scd)
    judge = scd._SemanticContradictionJudge()
    # The side-judge guard SWALLOWS the transport error (labels the pair conflict_unscored, never
    # holds) and returns normally, so we do NOT expect a raise — we inspect the captured body.
    judge.judge("The dose is 5 mg once daily.", "The dose is 10 mg twice daily.")
    assert captured, "judge never issued a POST"
    # OFFLOADED to a non-glm model -> NO provider pin (free-route across the model's own hosts),
    # so it does not 404 on the glm-only friendli/novita/z-ai/phala chain.
    assert "provider" not in captured[0], captured[0].get("provider")


def test_default_glm_model_keeps_mirror_pin(monkeypatch):
    _common_env(monkeypatch)
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    monkeypatch.delenv("PG_NLI_CONFLICT_MODEL", raising=False)
    import src.polaris_graph.retrieval.semantic_conflict_detector as scd
    from src.polaris_graph.roles import provider_routing

    provider_routing.reset_cache()
    captured = _capture_post_body(monkeypatch, scd)
    judge = scd._SemanticContradictionJudge()
    judge.judge("The dose is 5 mg once daily.", "The dose is 10 mg twice daily.")
    assert captured, "judge never issued a POST"
    # model MATCHES the glm mirror -> the mirror provider pin is applied UNCHANGED (byte-identical).
    # captured[0] is the FIRST attempt (before any provider-rotation mutates the order).
    provider = captured[0].get("provider")
    assert provider is not None and provider.get("order") == ["friendli"], provider
