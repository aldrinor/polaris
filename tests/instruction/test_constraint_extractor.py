"""Acceptance tests for the instruction constraint extractor.

The live LLM call is gated (PG_CONSTRAINT_EXTRACT_LIVE); by default these tests
run fully offline. The task-72 acceptance is exercised two ways:

  1. ``parse_constraints_json`` on a realistic model output (pure parser shape).
  2. ``extract_constraints`` end-to-end with a STUB client that returns that
     output — proving the async/sync plumbing + normalization deliver the
     required fields (journal-only source_types, English language,
     literature_review format).

A live smoke test is included but skipped unless PG_CONSTRAINT_EXTRACT_LIVE=1.
"""

import os

import pytest

from src.polaris_graph.instruction import (
    Constraints,
    extract_constraints,
    parse_constraints_json,
)
from src.polaris_graph.instruction.constraint_extractor import (
    extract_constraints_async,
)

# The task-72 prompt (verbatim intent from the brief).
TASK_72_PROMPT = (
    "Please write a literature review on the restructuring impact of "
    "Artificial Intelligence (AI) on the labor market. Ensure the review only "
    "cites high-quality, English-language journal articles."
)

# A realistic strict-JSON model reply for the task-72 prompt (code-fenced on
# purpose, to exercise the fence-stripping path).
TASK_72_MODEL_OUTPUT = """```json
{
  "source_types": ["journal article"],
  "languages": ["English"],
  "recency": null,
  "required_coverage": [
    "restructuring impact of AI on the labor market"
  ],
  "exclusions": ["low-quality sources", "non-English sources"],
  "format": "literature review",
  "length": null,
  "tone": "academic"
}
```"""


class _StubResponse:
    def __init__(self, content: str):
        self.content = content


class _StubClient:
    """Minimal stand-in for OpenRouterClient — records the call, returns canned."""

    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def generate(self, prompt, system="", max_tokens=0, temperature=0.0, **kw):
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        return _StubResponse(self._content)


# ---------------------------------------------------------------------------
# Pure-parser shape tests (no network, no stub)
# ---------------------------------------------------------------------------

def test_all_keys_present_on_empty_result():
    c = parse_constraints_json("{}").to_dict()
    assert set(c.keys()) == {
        "source_types",
        "languages",
        "recency",
        "required_coverage",
        "exclusions",
        "format",
        "length",
        "tone",
    }
    assert c["source_types"] == []
    assert c["languages"] == []
    assert c["recency"] is None
    assert c["required_coverage"] == []
    assert c["exclusions"] == []
    assert c["format"] is None
    assert c["length"] is None
    assert c["tone"] is None


def test_parse_task72_shape_and_canonicalization():
    c = parse_constraints_json(TASK_72_MODEL_OUTPUT)
    assert isinstance(c, Constraints)
    # journal-only source type, canonicalized
    assert c.source_types == ["journal_article"]
    # English -> ISO-639-1 'en'
    assert c.languages == ["en"]
    # literature review -> canonical format token
    assert c.format == "literature_review"
    assert c.tone == "academic"
    assert c.recency is None
    assert c.required_coverage  # non-empty coverage slot(s)


def test_parser_tolerates_scalar_where_list_expected():
    # Model returns a bare string for a list field, and 'none' text for scalars.
    raw = (
        '{"source_types": "journal article", "languages": "en", '
        '"recency": "none", "format": "None", "tone": ""}'
    )
    c = parse_constraints_json(raw)
    assert c.source_types == ["journal_article"]
    assert c.languages == ["en"]
    assert c.recency is None
    assert c.format is None
    assert c.tone is None


def test_parser_strips_surrounding_prose():
    raw = (
        "Here are the constraints I found:\n"
        '{"source_types": ["peer-reviewed"], "languages": ["English"], '
        '"format": "systematic review"}\n'
        "Hope that helps!"
    )
    c = parse_constraints_json(raw)
    assert c.source_types == ["peer_reviewed"]
    assert c.languages == ["en"]
    assert c.format == "systematic_review"


def test_parser_raises_on_non_json():
    with pytest.raises(ValueError):
        parse_constraints_json("no json here at all")


def test_parser_dedups_case_insensitively():
    raw = '{"languages": ["English", "english", "EN"], "source_types": ["Journal Article", "journal articles"]}'
    c = parse_constraints_json(raw)
    assert c.languages == ["en"]
    assert c.source_types == ["journal_article"]


# ---------------------------------------------------------------------------
# End-to-end via stub client (async + sync)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_task72_async_with_stub_client():
    stub = _StubClient(TASK_72_MODEL_OUTPUT)
    result = await extract_constraints_async(TASK_72_PROMPT, client=stub)

    # ACCEPTANCE (brief): journal-only sources, English, literature_review.
    assert result["source_types"] == ["journal_article"]
    assert "en" in result["languages"]
    assert result["format"] == "literature_review"

    # The prompt actually reached the model, with the adversarial system prompt.
    assert len(stub.calls) == 1
    assert TASK_72_PROMPT in stub.calls[0]["prompt"]
    assert "buried" in stub.calls[0]["system"].lower()
    # Deterministic default temperature for extraction.
    assert stub.calls[0]["temperature"] == 0.0


def test_extract_task72_sync_with_stub_client():
    stub = _StubClient(TASK_72_MODEL_OUTPUT)
    result = extract_constraints(TASK_72_PROMPT, client=stub)
    assert result["source_types"] == ["journal_article"]
    assert "en" in result["languages"]
    assert result["format"] == "literature_review"


@pytest.mark.asyncio
async def test_empty_prompt_returns_empty_without_calling_model():
    stub = _StubClient(TASK_72_MODEL_OUTPUT)
    result = await extract_constraints_async("   ", client=stub)
    assert result["source_types"] == []
    assert result["format"] is None
    assert stub.calls == []  # no model call for an empty prompt


@pytest.mark.asyncio
async def test_live_disabled_and_no_client_raises():
    # With the live gate OFF (default) and no injected client, the extractor
    # must refuse to hit the network rather than silently constructing a real
    # client.
    prev = os.environ.pop("PG_CONSTRAINT_EXTRACT_LIVE", None)
    try:
        with pytest.raises(RuntimeError):
            await extract_constraints_async(TASK_72_PROMPT)
    finally:
        if prev is not None:
            os.environ["PG_CONSTRAINT_EXTRACT_LIVE"] = prev


# ---------------------------------------------------------------------------
# Live smoke (opt-in only)
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("PG_CONSTRAINT_EXTRACT_LIVE", "0").strip().lower()
    not in ("1", "true", "yes", "on"),
    reason="live LLM extraction disabled (set PG_CONSTRAINT_EXTRACT_LIVE=1)",
)
async def test_extract_task72_live():
    result = await extract_constraints_async(TASK_72_PROMPT)
    assert any(
        "journal" in s.lower() for s in result["source_types"]
    ), result["source_types"]
    assert "en" in result["languages"], result["languages"]
    assert result["format"] == "literature_review", result["format"]
