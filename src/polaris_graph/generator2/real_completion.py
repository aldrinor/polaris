"""Real OpenRouter-backed completion_fn for slice 003 generator.

Per `.codex/slices/slice_003/architecture_proposal.md` PR 7 row.

Implements GeneratorCompletionFn protocol with an OpenRouter chat-completion
backend. Default model from OPENROUTER_DEFAULT_MODEL env var (e.g.
'z-ai/glm-5.1'). Prompt template instructs the LLM to:

  - write 4-8 sentences for the requested section
  - cite EVERY claim with a [#ev:<source_id>:<start>-<end>] token
  - never invent decimal numbers — only cite numbers that appear in
    the cited span
  - use only the supplied evidence; do not invoke external knowledge

Strict-verify (slice 003 PR 4) drops sentences that violate these rules
post-generation, so the LLM occasionally producing bad output is OK —
the gate enforces the contract regardless.

Fail-loud per LAW II:
  - OPENROUTER_API_KEY missing → RuntimeError at construction
  - OpenRouter returns malformed JSON → propagate exception
  - HTTP errors → propagate (orchestrator catches, returns
    GenerationError(completion_backend_unavailable))
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from polaris_graph.generator2.section_blueprint import SectionPlan
from polaris_graph.retrieval2.evidence_pool import EvidencePool

_LOG = logging.getLogger(__name__)

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 800

# Cap evidence excerpts in the prompt to keep total tokens manageable.
# Each source contributes its first MAX_EVIDENCE_CHARS_PER_SOURCE chars.
MAX_EVIDENCE_CHARS_PER_SOURCE = 800
MAX_SOURCES_IN_PROMPT = 8


@dataclass
class RealCompletionConfig:
    api_key: str
    model: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS


def load_config_from_env() -> RealCompletionConfig:
    """Build a RealCompletionConfig from environment variables.

    Raises RuntimeError if OPENROUTER_API_KEY is unset (fail loud).
    """
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for slice 003 real_completion. "
            "Set it in .env before mounting the generation route. Per "
            "CLAUDE.md LAW II, this MUST fail loudly rather than silently "
            "skipping the generator."
        )
    model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip() or "z-ai/glm-5.1"
    return RealCompletionConfig(api_key=key, model=model)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _format_evidence_block(pool: EvidencePool) -> str:
    """Build the evidence block of the prompt.

    Lists each source with its source_id, tier, title, and a bounded
    excerpt of its full_text (or snippet). The LLM uses these to cite.
    """
    lines: list[str] = []
    sources_used = pool.sources[:MAX_SOURCES_IN_PROMPT]
    for source in sources_used:
        text = source.full_text if source.full_text is not None else source.snippet
        excerpt = text[:MAX_EVIDENCE_CHARS_PER_SOURCE]
        lines.append(
            f"--- source_id: {source.source_id} | tier: {source.tier.value} | "
            f"title: {source.title}\n{excerpt}"
        )
    return "\n\n".join(lines)


SYSTEM_PROMPT = """You are a clinical research synthesis engine. Your output is the section text ONLY — no preamble, no meta-commentary, no markdown, no thinking-aloud.

RULES (mandatory):

1. Write 4-8 well-formed declarative sentences for the requested section.
2. EVERY sentence ends with at least one provenance token of the form
   [#ev:<source_id>:<start>-<end>]. source_id MUST be one of the sources
   provided. start/end are character offsets into that source's text.
3. NEVER invent numbers. Only cite numeric claims (percentages, sample
   sizes, hazard ratios, etc.) that literally appear in the cited span.
4. NEVER use external knowledge. Use ONLY the supplied evidence excerpts.
5. NEVER write meta-commentary like "We need to write...", "The
   evidence shows...", "Let me examine...", "I need to...". Skip directly
   to the section content.
6. If the evidence does not support a claim, say so explicitly with a
   citation to the source that demonstrates the gap.

EXAMPLE (for a 'Population' section about aspirin in migraine):

INPUT EVIDENCE:
--- source_id: src-A | tier: T1 | title: Cochrane review on aspirin for migraine
The review included 13 trials enrolling 4222 adults aged 18 to 65 years with episodic migraine. Mean age was 38.7 years; 73% were female.

OUTPUT (this is the EXACT format expected — note: starts with content,
no preamble, every sentence has a token):
The review included 13 trials enrolling 4222 adults aged 18 to 65 years with episodic migraine [#ev:src-A:0-99]. The cohort had a mean age of 38.7 years and was 73% female [#ev:src-A:101-148].

END EXAMPLE.

Now produce the section. Output the prose directly with no preamble."""


def _build_user_prompt(section_plan: SectionPlan, pool: EvidencePool) -> str:
    evidence_block = _format_evidence_block(pool)
    return (
        f"Section to write: {section_plan.section_title}\n\n"
        f"Section guidance: {section_plan.section_brief}\n\n"
        f"Available evidence:\n{evidence_block}\n\n"
        f"Write the section now. Remember: every sentence ends with at "
        f"least one [#ev:source_id:start-end] token; never invent numbers."
    )


# ---------------------------------------------------------------------------
# Completion function
# ---------------------------------------------------------------------------

@dataclass
class RealCompletion:
    """Stateful GeneratorCompletionFn impl backed by OpenRouter chat API."""

    config: RealCompletionConfig

    def __call__(
        self,
        prompt: str,
        section_plan: SectionPlan,
        pool: EvidencePool,
    ) -> str:
        # `prompt` is the section_brief; we re-build a richer user prompt
        # with the actual evidence block. Section_plan + pool are the
        # authoritative inputs.
        user_prompt = _build_user_prompt(section_plan, pool)

        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            # OpenRouter recommends these for routing analytics:
            "HTTP-Referer": "https://polaris-canada.local",
            "X-Title": "POLARIS Slice 003 Generator",
        }

        with httpx.Client() as client:
            response = client.post(
                OPENROUTER_ENDPOINT,
                json=body,
                headers=headers,
                timeout=self.config.timeout_s,
            )
            response.raise_for_status()
            data = response.json()

        text = _extract_text(data)
        if not text.strip():
            raise RuntimeError(
                f"OpenRouter returned empty content for section "
                f"{section_plan.section_id!r}; model={self.config.model!r}"
            )
        return text


def _extract_text(response_json: dict[str, Any]) -> str:
    """Parse OpenRouter chat-completion response to plain text.

    Handles both shapes seen in the wild:
        # Standard string content (most models)
        {"choices": [{"message": {"content": "Generated text..."}}]}

        # Multipart content (some Anthropic, Google, etc.)
        {"choices": [{"message": {"content": [
            {"type": "text", "text": "Generated text..."}
        ]}}]}

    Falls back to `message.reasoning` when `content` is empty/None and
    reasoning is populated (some routes return reasoning + empty content
    when the model hits a refusal-like state but still produced thought).
    Last-resort: raises RuntimeError so the orchestrator surfaces a
    structured GenerationError.
    """
    choices = response_json.get("choices") or []
    if not choices:
        raise RuntimeError(
            f"OpenRouter response missing 'choices': {response_json}"
        )
    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        joined = "\n".join(parts).strip()
        if joined:
            return joined

    # Fallback: some routes return reasoning when content is suppressed.
    reasoning = message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning

    raise RuntimeError(
        "OpenRouter response 'message.content' missing or not a string "
        f"(got type={type(content).__name__}); reasoning_present="
        f"{bool(message.get('reasoning'))}"
    )


def build_real_completion() -> RealCompletion:
    """Factory: read env, build a configured RealCompletion.

    Use this as the FastAPI Depends() injection point in production.
    """
    return RealCompletion(config=load_config_from_env())
