"""
HONEST-REBUILD Phase 1b stub — DO NOT IMPLEMENT ANYTHING HERE.

This module previously ran post-synthesis NLI hallucination detection
(MiniCheck flan-t5-large) and triggered a REMEDIATE-LOOP in
wiki_composer.py that rewrote flagged sections to pass the NLI score.

The REMEDIATE-LOOP was documented NLI-gaming: iter-2 rewrites compressed
sections by ~60% on average in PG_LB_SA_02, deleting evidence-synthesis
content to beat the metric. See loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md
Section B for the quantified information-loss audit.

The detector itself used same-family self-grading (MiniCheck +
generator-family LLM) which the field has documented as unreliable:
"Play Favorites" (arXiv:2508.06709, Aug 2025) and DeepHalluBench
(arXiv:2601.22984, Jan 2026).

This stub preserves the import surface so call-sites in synthesizer.py
and wiki_composer.py and forensic scripts in scripts/ do not break at
import time. All calls return empty audit results (no flagging).

Phase 5 of the honest-rebuild plan replaces this with
src/polaris_graph/evaluator/external_evaluator.py — non-same-family
LLM (Qwen 3 32B evaluator while generator is DeepSeek V3.2) plus
rule-based PRISMA-trAIce compliance checks. No self-grading, no
rewrite-to-pass-metric loop. See
C:/Users/msn/.claude/plans/lovely-finding-firefly.md Phase 5.

The pre-rebuild 356-line implementation is preserved in git history
(commit d638446 and earlier). Rollback with git show d638446:<path>
if needed for forensic inspection.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)

# Preserved so downstream env-reads don't KeyError. Both default to disabled
# and the stub ignores them.
PG_HALLUCINATION_DETECT_ENABLED = False
PG_HALLUCINATION_REWRITE_THRESHOLD = 0.25
PG_POST_SYNTH_NLI_THRESHOLD = 0.5
PG_POST_SYNTH_MAX_CLAIMS = 50


_WARNED = False


def _warn_once() -> None:
    global _WARNED
    if _WARNED:
        return
    _WARNED = True
    msg = (
        "hallucination_detector is a stub per HONEST-REBUILD Phase 1b "
        "(plan: C:/Users/msn/.claude/plans/lovely-finding-firefly.md). "
        "Returning empty audit results. External non-same-family evaluator "
        "wiring is Phase 5 scope."
    )
    logger.warning("[hallucination_detector STUB] %s", msg)
    warnings.warn(msg, DeprecationWarning, stacklevel=3)


def _is_enabled() -> bool:
    """Always disabled in the stub."""
    _warn_once()
    return False


def _get_detector() -> Any:
    """Stub — returns None. Callers should check _is_enabled() first."""
    _warn_once()
    return None


def audit_sections_for_hallucination(
    sections: list[dict] | None = None,
    evidence: list[dict] | None = None,
    research_query: str | None = None,
    **kwargs: Any,
) -> list[dict]:
    """Stub — always returns empty list. No audit performed.

    The replacement is the external non-same-family evaluator built in
    Phase 5 (src/polaris_graph/evaluator/external_evaluator.py). That
    evaluator runs on a different model family than the generator,
    grades via rule-based structured checks primarily (PRISMA-trAIce
    compliance, citation-span exact match, tier-distribution arithmetic)
    and LLM judgment only for ambiguous cases.
    """
    _warn_once()
    return []
