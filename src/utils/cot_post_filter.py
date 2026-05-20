"""
FIX-211: LLM-Based CoT Post-Filter

Replace the regex arms race (480+ patterns in cot_scrubber.py that still leak 28-40%
CoT per run) with a cheap LLM classification pass.

Architecture:
1. Regex scrubber stays as cheap pre-filter (handles ~80% at zero cost)
2. THIS module: LLM post-filter classifies remaining "suspicious" lines as KEEP/REMOVE
3. "Suspicious" = lines < 20 words, no citation, starts with pronoun/meta-pattern
4. Batch classification: ~30 lines per LLM call, structured JSON output
5. Cost: ~$0.002 per invocation

Feature flag: POLARIS_LLM_COT_FILTER (default "1")
"""

import logging
import os
import re
import json
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)

# Feature flag
LLM_COT_FILTER_ENABLED = os.environ.get("POLARIS_LLM_COT_FILTER", "1") == "1"

# Max lines per LLM batch (controls cost)
MAX_BATCH_SIZE = int(os.environ.get("POLARIS_COT_FILTER_BATCH_SIZE", "30"))

# Citation pattern for detecting cited lines (likely real content)
_CITE_PATTERN = re.compile(r'\[CITE:[^\]]+\]|\[\d+\]')

# Suspicious line patterns (cheap pre-check before LLM classification)
_SUSPICIOUS_STARTERS = re.compile(
    r'^(?:'
    r'(?:I |We |My |Our |Let |The (?:evidence|data|sources?|claim|fact|analysis))'
    r'|(?:Now|First|Next|Then|Also|However|But|So|Okay|Wait|Actually|Looking)'
    r'|(?:This (?:is|seems|appears|shows|suggests|indicates|means|requires))'
    r'|(?:Based on|According to|In (?:order|summary|conclusion|this|the))'
    r'|(?:To (?:summarize|conclude|verify|check|ensure|address))'
    r')',
    re.IGNORECASE,
)


def _is_suspicious_line(line: str) -> bool:
    """
    Cheap heuristic to identify lines that MIGHT be CoT leakage.
    Only these lines get sent to the LLM for classification.

    A line is suspicious if:
    - It's short (< 20 words)
    - It has no citations
    - It starts with a meta/reasoning pattern
    """
    stripped = line.strip()
    if not stripped:
        return False

    # Headers are never suspicious
    if stripped.startswith("#"):
        return False

    # Lines with citations are almost certainly real content
    if _CITE_PATTERN.search(stripped):
        return False

    # Long lines are usually real content (LLM reasoning is typically short)
    word_count = len(stripped.split())
    if word_count >= 20:
        return False

    # Check for suspicious starters
    if _SUSPICIOUS_STARTERS.match(stripped):
        return True

    # Very short lines (< 8 words) without citations are suspicious
    if word_count < 8:
        return True

    return False


def classify_lines_batch(
    lines: List[str],
    query: str,
    llm_invoke: Callable[[str], str],
) -> List[bool]:
    """
    Classify a batch of lines as KEEP (True) or REMOVE (False) using LLM.

    Args:
        lines: Lines to classify (max MAX_BATCH_SIZE)
        query: The research query (provides context for what's "on-topic")
        llm_invoke: Callable that takes a prompt string and returns LLM response text

    Returns:
        List of booleans, True = keep, False = remove (CoT leakage)
    """
    if not lines:
        return []

    # Build classification prompt
    numbered_lines = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))

    prompt = f"""Classify each numbered line as either KEEP or REMOVE.

RESEARCH TOPIC: {query}

KEEP = factual content about the research topic that belongs in a report
REMOVE = meta-reasoning, thinking process, self-referential commentary, or task instructions

Examples of REMOVE:
- "Let me check the evidence for this claim"
- "I need to verify this against the sources"
- "This section covers the main findings"
- "Now I will write about the health impacts"
- "Based on my analysis of the evidence"

Examples of KEEP:
- "Water filters reduce lead contamination by 99% in laboratory settings"
- "The EPA established a maximum contaminant level of 15 ppb for lead"
- "Studies conducted between 2018 and 2023 found significant variation"

LINES TO CLASSIFY:
{numbered_lines}

OUTPUT: A JSON array of objects, one per line, in order:
[{{"line": 1, "verdict": "KEEP"}}, {{"line": 2, "verdict": "REMOVE"}}, ...]

Output ONLY the JSON array. No explanation."""

    try:
        response = llm_invoke(prompt)
        if not response:
            logger.warning("[FIX-211] LLM returned empty response, keeping all lines")
            return [True] * len(lines)

        # Parse JSON from response (handle markdown code blocks)
        json_text = response.strip()
        if json_text.startswith("```"):
            # Strip markdown code fence
            json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
            json_text = re.sub(r'\s*```$', '', json_text)

        # Try to extract JSON array via bracket matching
        start = json_text.find("[")
        if start >= 0:
            depth = 0
            for i in range(start, len(json_text)):
                if json_text[i] == "[":
                    depth += 1
                elif json_text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        json_text = json_text[start:i+1]
                        break

        verdicts = json.loads(json_text)
        results = []
        for i, line in enumerate(lines):
            if i < len(verdicts):
                verdict = verdicts[i]
                if isinstance(verdict, dict):
                    v = verdict.get("verdict", "KEEP").upper()
                elif isinstance(verdict, str):
                    v = verdict.upper()
                else:
                    v = "KEEP"
                results.append(v != "REMOVE")
            else:
                results.append(True)  # Default to keep if LLM response is short

        return results

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"[FIX-211] Failed to parse LLM classification response: {e}")
        return [True] * len(lines)
    except Exception as e:
        logger.error(f"[FIX-211] LLM classification failed: {e}")
        return [True] * len(lines)


def post_filter_report(
    report: str,
    query: str,
    llm_invoke: Callable[[str], str],
    pre_scrubbed: bool = True,
) -> str:
    """
    Apply LLM-based CoT post-filter to a report.

    This should be called AFTER scrub_cot_from_report() (regex pre-filter).
    It identifies remaining suspicious lines and classifies them via LLM.

    Args:
        report: The report text (already regex-scrubbed if pre_scrubbed=True)
        query: The research query
        llm_invoke: Callable that takes a prompt string and returns LLM response text
        pre_scrubbed: Whether regex scrubber was already applied

    Returns:
        Filtered report with CoT lines removed
    """
    if not LLM_COT_FILTER_ENABLED:
        return report

    if not report or not report.strip():
        return report

    lines = report.split("\n")
    suspicious_indices = []
    suspicious_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip headers (markdown ## or ###)
        if stripped.startswith("#"):
            continue
        # Skip empty lines
        if not stripped:
            continue
        if _is_suspicious_line(stripped):
            suspicious_indices.append(i)
            suspicious_lines.append(stripped)

    if not suspicious_lines:
        logger.debug("[FIX-211] No suspicious lines found, skipping LLM filter")
        return report

    logger.info(f"[FIX-211] Found {len(suspicious_lines)} suspicious lines, classifying via LLM")

    # Process in batches
    all_verdicts = []
    for batch_start in range(0, len(suspicious_lines), MAX_BATCH_SIZE):
        batch = suspicious_lines[batch_start:batch_start + MAX_BATCH_SIZE]
        batch_verdicts = classify_lines_batch(batch, query, llm_invoke)
        all_verdicts.extend(batch_verdicts)

    # Build removal set
    lines_to_remove = set()
    removed_lines_log = []
    for idx, (line_idx, keep) in enumerate(zip(suspicious_indices, all_verdicts)):
        if not keep:
            lines_to_remove.add(line_idx)
            removed_lines_log.append(lines[line_idx].strip()[:80])

    if removed_lines_log:
        logger.info(
            f"[FIX-211] LLM post-filter removing {len(removed_lines_log)} CoT lines: "
            f"{removed_lines_log[:5]}"
        )

    # Remove lines and clean up
    filtered_lines = [
        line for i, line in enumerate(lines)
        if i not in lines_to_remove
    ]

    result = "\n".join(filtered_lines)

    # Clean up excessive blank lines from removal
    result = re.sub(r'\n{3,}', '\n\n', result)

    return result


def create_default_llm_invoke() -> Optional[Callable[[str], str]]:
    """
    Create a lightweight LLM invoke callable from the default config.
    Used by finalize_node where no agent instance is available.

    Returns None if LLM cannot be initialized (caller should skip post-filter).
    """
    try:
        from langchain_fireworks import ChatFireworks
        from langchain_core.messages import HumanMessage

        api_key = os.environ.get("FIREWORKS_API_KEY", "")
        if not api_key:
            logger.warning("[FIX-211] No FIREWORKS_API_KEY, skipping LLM post-filter in finalize")
            return None

        # Use a cheap, fast model for classification (not the expensive thinking model).
        # I-cd-010 / GH#625: pipeline-C COT classifier legacy; not under
        # Carney demo lock per CLAUDE.md §5. Override via POLARIS_COT_FILTER_MODEL.
        model = os.environ.get("POLARIS_COT_FILTER_MODEL", "accounts/fireworks/models/llama-v3p3-70b-instruct")
        llm = ChatFireworks(
            model=model,
            api_key=api_key,
            max_tokens=2048,
            temperature=0.0,
        )

        def invoke(prompt: str) -> str:
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content if hasattr(response, 'content') else str(response)

        return invoke

    except ImportError:
        logger.warning("[FIX-211] langchain_fireworks not available, skipping LLM post-filter")
        return None
    except Exception as e:
        logger.warning(f"[FIX-211] Failed to create LLM for post-filter: {e}")
        return None
