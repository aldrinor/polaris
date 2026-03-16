"""
Prompt-level token accounting for observability.

Tracks input token breakdown per LLM call and emits tracer events.
Warns when evidence or total tokens approach context window limits.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration (LAW VI)
PG_TOKEN_ACCOUNTING_ENABLED = os.getenv("PG_TOKEN_ACCOUNTING_ENABLED", "1") == "1"
PG_TOKEN_ACCOUNTING_WARN_THRESHOLD = float(
    os.getenv("PG_TOKEN_ACCOUNTING_WARN_THRESHOLD", "0.85")
)

# Kimi K2.5 context window (128K tokens input)
_CONTEXT_WINDOW = int(os.getenv("PG_CONTEXT_WINDOW_TOKENS", "128000"))


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length (chars/3.5)."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


class PromptTokenAccounting:
    """Token breakdown for a single LLM prompt.

    Attributes:
        system_tokens: Tokens in the system prompt.
        evidence_tokens: Tokens in the evidence block.
        context_tokens: Tokens in context/template (non-evidence user prompt).
        instruction_tokens: Tokens in instructions appended to the prompt.
        total_tokens: Sum of all components.
        utilization_pct: Percentage of context window used.
        warnings: List of warning strings if thresholds exceeded.
    """

    def __init__(
        self,
        system_prompt: str = "",
        evidence_block: str = "",
        context_block: str = "",
        instruction_block: str = "",
        evidence_count: int = 0,
        section_title: str = "",
    ):
        self.system_tokens = _estimate_tokens(system_prompt)
        self.evidence_tokens = _estimate_tokens(evidence_block)
        self.context_tokens = _estimate_tokens(context_block)
        self.instruction_tokens = _estimate_tokens(instruction_block)
        self.evidence_count = evidence_count
        self.section_title = section_title

        self.total_tokens = (
            self.system_tokens
            + self.evidence_tokens
            + self.context_tokens
            + self.instruction_tokens
        )

        self.utilization_pct = (
            self.total_tokens / max(_CONTEXT_WINDOW, 1)
        ) * 100

        self.warnings: list[str] = []
        self._check_thresholds()

    def _check_thresholds(self) -> None:
        """Generate warnings for threshold violations."""
        total_budget = self.system_tokens + self.evidence_tokens + self.context_tokens + self.instruction_tokens

        if total_budget > 0:
            evidence_pct = self.evidence_tokens / total_budget
            if evidence_pct > 0.80:
                self.warnings.append(
                    f"Evidence dominates prompt ({evidence_pct:.0%} of input tokens)"
                )

        if self.utilization_pct > PG_TOKEN_ACCOUNTING_WARN_THRESHOLD * 100:
            self.warnings.append(
                f"Prompt uses {self.utilization_pct:.1f}% of context window "
                f"({self.total_tokens}/{_CONTEXT_WINDOW} tokens)"
            )

    def to_dict(self) -> dict:
        """Serialize to dict for tracer events / logging."""
        return {
            "system_tokens": self.system_tokens,
            "evidence_tokens": self.evidence_tokens,
            "context_tokens": self.context_tokens,
            "instruction_tokens": self.instruction_tokens,
            "total_tokens": self.total_tokens,
            "evidence_count": self.evidence_count,
            "utilization_pct": round(self.utilization_pct, 1),
            "tokens_per_evidence": round(
                self.evidence_tokens / max(self.evidence_count, 1)
            ),
            "section_title": self.section_title,
            "warnings": self.warnings,
        }

    def log(self) -> None:
        """Log token accounting at appropriate level."""
        if not PG_TOKEN_ACCOUNTING_ENABLED:
            return

        if self.warnings:
            for w in self.warnings:
                logger.warning("[token_accounting] %s", w)

        logger.info(
            "[token_accounting] Section '%s': %d total tokens "
            "(system=%d, evidence=%d [%d pieces], context=%d, instructions=%d) "
            "%.1f%% context window",
            self.section_title[:50],
            self.total_tokens,
            self.system_tokens,
            self.evidence_tokens,
            self.evidence_count,
            self.context_tokens,
            self.instruction_tokens,
            self.utilization_pct,
        )

    def emit_tracer_event(self) -> None:
        """Emit a tracer event with token accounting data."""
        if not PG_TOKEN_ACCOUNTING_ENABLED:
            return

        try:
            from src.polaris_graph.tracing import get_tracer
            tracer = get_tracer()
            if tracer:
                tracer.evidence(
                    "synthesize",
                    "prompt_token_accounting",
                    self.evidence_count,
                    **self.to_dict(),
                )
        except Exception:
            pass  # Non-critical observability
