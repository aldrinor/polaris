"""Real OpenRouter-backed completion_fn for slice 003 generator.

Per `.codex/slices/slice_003/architecture_proposal.md` PR 7 row.

Implements GeneratorCompletionFn protocol with an OpenRouter chat-completion
backend. Default model from OPENROUTER_DEFAULT_MODEL env var (e.g.
'deepseek/deepseek-v4-pro'). Prompt template instructs the LLM to:

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

from polaris_graph.clinical_generator.section_blueprint import SectionPlan
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool

_LOG = logging.getLogger(__name__)

# I-sov-001: endpoint is env-configurable so the sovereign deploy can point
# the generator at the OVH H200 vLLM endpoint (set OPENROUTER_BASE_URL=
# http://<priv-ip>:8000/v1). Default keeps OpenRouter. Mirrors
# openrouter_client.py:43-45 — one env var flips the whole stack.
_OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
OPENROUTER_ENDPOINT = f"{_OPENROUTER_BASE_URL}/chat/completions"
DEFAULT_TIMEOUT_S = 60.0
DEFAULT_TEMPERATURE = 0.2
# I-arch-003 (#1253): deepseek-v4-pro is a reasoning-first model; 800 truncated mid-reasoning -> empty
# content -> RuntimeError. Un-starve to the reasoning-first floor (DeepInfra-safe deepseek cap); env-overridable.
DEFAULT_MAX_TOKENS = int(os.environ.get("PG_REAL_COMPLETION_MAX_TOKENS", "16384") or "16384")

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
    model = os.environ.get("OPENROUTER_DEFAULT_MODEL", "").strip() or "deepseek/deepseek-v4-pro"
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

    @property
    def model_label(self) -> str:
        """Returns the actual model id used for completions.

        The generator orchestrator pulls this so VerifiedReport.generator_model
        reflects the live model rather than the 'stub-generator' default.
        """
        return self.config.model

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
            # I-arch-003 (#1253): reasoning-first model needs reasoning ON at max effort so it completes
            # thinking AND emits content (the un-starved max_tokens gives it room). Env-overridable.
            "reasoning": {
                "effort": os.environ.get("PG_REAL_COMPLETION_REASONING_EFFORT", "high") or "high"
            },
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
                f"LLM backend returned empty content for section "
                f"{section_plan.section_id!r}; model={self.config.model!r}; "
                f"endpoint={OPENROUTER_ENDPOINT!r}"
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
    # I-sov-001: check BOTH `reasoning_content` (vLLM-native key, what the
    # OVH H200 sovereign deploy emits) AND `reasoning` (OpenRouter's key).
    # openrouter_client.py already does this at lines 1044-1050,1389-1393;
    # this aligns real_completion.py's fallback with the central client.
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning

    raise RuntimeError(
        "LLM response 'message.content' missing or not a string "
        f"(got type={type(content).__name__}); reasoning_present="
        f"{bool(message.get('reasoning_content') or message.get('reasoning'))}"
    )


def build_real_completion() -> RealCompletion:
    """Factory: read env, build a configured RealCompletion.

    Use this as the FastAPI Depends() injection point in production.
    """
    return RealCompletion(config=load_config_from_env())
