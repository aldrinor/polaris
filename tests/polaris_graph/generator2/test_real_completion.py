"""Tests for the real OpenRouter-backed completion_fn (network-mocked)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from polaris_graph.generator2.real_completion import (
    OPENROUTER_ENDPOINT,
    RealCompletion,
    RealCompletionConfig,
    SYSTEM_PROMPT,
    _build_user_prompt,
    _extract_text,
    _format_evidence_block,
    build_real_completion,
    load_config_from_env,
)
from polaris_graph.generator2.section_blueprint import (
    CLINICAL_EFFICACY,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Config / env handling ----------

def test_load_config_requires_openrouter_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
        load_config_from_env()


def test_load_config_blank_key_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
        load_config_from_env()


def test_load_config_default_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL", raising=False)
    cfg = load_config_from_env()
    assert cfg.api_key == "test-key"
    assert cfg.model == "z-ai/glm-5.1"


def test_load_config_custom_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "anthropic/claude-3-5-sonnet")
    cfg = load_config_from_env()
    assert cfg.model == "anthropic/claude-3-5-sonnet"


def test_build_real_completion_uses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    rc = build_real_completion()
    assert isinstance(rc, RealCompletion)
    assert rc.config.api_key == "test-key"


# ---------- Prompt construction ----------

def _src(source_id: str = "src-1", text: str = "x" * 100) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title=f"Source {source_id}",
        snippet=text[:100],
        full_text=text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(sources: list[Source]) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=sources,
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: len(sources), SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def test_format_evidence_block_includes_source_metadata():
    pool = _pool([_src("src-A", "Aspirin reduced events"), _src("src-B", "Trial enrolled adults")])
    block = _format_evidence_block(pool)
    assert "src-A" in block
    assert "src-B" in block
    assert "T1" in block
    assert "Aspirin" in block
    assert "Trial enrolled" in block


def test_format_evidence_block_caps_at_8_sources():
    sources = [_src(f"src-{i}", f"text-{i}") for i in range(20)]
    pool = _pool(sources)
    block = _format_evidence_block(pool)
    # Only first 8 should appear
    assert "src-7" in block
    assert "src-8" not in block
    assert "src-19" not in block


def test_format_evidence_block_caps_excerpt_length():
    long_text = "X" * 5000
    pool = _pool([_src("src-1", long_text)])
    block = _format_evidence_block(pool)
    # Each excerpt is bounded; 5000 chars must NOT all appear
    assert len(block) < 2000


def test_build_user_prompt_includes_section_title_and_brief():
    pool = _pool([_src()])
    prompt = _build_user_prompt(CLINICAL_EFFICACY.sections[0], pool)
    assert "Population" in prompt  # section title
    assert "demographics" in prompt.lower() or "eligibility" in prompt.lower()  # brief
    assert "src-1" in prompt


def test_system_prompt_specifies_token_format():
    assert "[#ev:" in SYSTEM_PROMPT
    assert "<source_id>" in SYSTEM_PROMPT


def test_system_prompt_forbids_inventing_numbers():
    assert "Do NOT invent numbers" in SYSTEM_PROMPT or "do not invent numbers" in SYSTEM_PROMPT.lower()


# ---------- _extract_text ----------

def test_extract_text_canonical_response():
    response = {
        "choices": [
            {"message": {"role": "assistant", "content": "Generated prose."}}
        ]
    }
    assert _extract_text(response) == "Generated prose."


def test_extract_text_missing_choices_raises():
    with pytest.raises(RuntimeError, match="missing 'choices'"):
        _extract_text({})


def test_extract_text_empty_choices_raises():
    with pytest.raises(RuntimeError, match="missing 'choices'"):
        _extract_text({"choices": []})


def test_extract_text_missing_content_raises():
    with pytest.raises(RuntimeError, match="content"):
        _extract_text({"choices": [{"message": {}}]})


def test_extract_text_non_string_content_raises():
    with pytest.raises(RuntimeError, match="content"):
        _extract_text(
            {"choices": [{"message": {"content": [{"type": "text"}]}}]}
        )


# ---------- RealCompletion call (network mocked) ----------

def _success_handler(content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        body = request.read()
        # Verify body shape
        import json

        parsed = json.loads(body)
        assert "model" in parsed
        assert isinstance(parsed["messages"], list)
        assert len(parsed["messages"]) == 2
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": content,
                        }
                    }
                ]
            },
        )

    return handler


def test_real_completion_returns_text(monkeypatch: pytest.MonkeyPatch):
    cfg = RealCompletionConfig(api_key="test", model="z-ai/glm-5.1")
    rc = RealCompletion(config=cfg)
    transport = httpx.MockTransport(
        _success_handler(
            "Adults benefited from aspirin therapy [#ev:src-1:0-50]."
        )
    )

    real_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    pool = _pool([_src()])
    text = rc(
        prompt="ignored",
        section_plan=CLINICAL_EFFICACY.sections[0],
        pool=pool,
    )
    assert "[#ev:src-1:0-50]" in text


def test_real_completion_raises_on_http_error(monkeypatch: pytest.MonkeyPatch):
    cfg = RealCompletionConfig(api_key="test", model="z-ai/glm-5.1")
    rc = RealCompletion(config=cfg)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = httpx.MockTransport(handler)
    real_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    pool = _pool([_src()])
    with pytest.raises(httpx.HTTPStatusError):
        rc(prompt="x", section_plan=CLINICAL_EFFICACY.sections[0], pool=pool)


def test_real_completion_raises_on_empty_response(monkeypatch: pytest.MonkeyPatch):
    cfg = RealCompletionConfig(api_key="test", model="z-ai/glm-5.1")
    rc = RealCompletion(config=cfg)
    transport = httpx.MockTransport(_success_handler(""))

    real_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    pool = _pool([_src()])
    with pytest.raises(RuntimeError, match="empty content"):
        rc(
            prompt="x",
            section_plan=CLINICAL_EFFICACY.sections[0],
            pool=pool,
        )


def test_real_completion_includes_referer_and_title_headers(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = RealCompletionConfig(api_key="test", model="z-ai/glm-5.1")
    rc = RealCompletion(config=cfg)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    transport = httpx.MockTransport(handler)
    real_init = httpx.Client.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)

    pool = _pool([_src()])
    rc(prompt="x", section_plan=CLINICAL_EFFICACY.sections[0], pool=pool)
    assert seen.get("http-referer", "").startswith("https://polaris-canada")
    assert "POLARIS" in seen.get("x-title", "")
