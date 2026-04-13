"""Smoke test for FIX-GLM5-STRUCTURED.

Validates that generate_structured() with GLM 5.1 and a 5+ field schema
returns non-empty content (vs. dumping prose into reasoning_content).

The existing pg_smoke_test.py uses a 2-field TestSchema which is too simple
to reproduce the bug. The bug only manifests with complex schemas (5+ fields)
where GLM 5.1 burns reasoning budget on planning before emitting JSON.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Add project root to path so `from src.polaris_graph...` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

from src.polaris_graph.llm.openrouter_client import OpenRouterClient


# 5-field schema mimicking StormOutlinePlan complexity
class ComplexPlan(BaseModel):
    """5-field plan to reproduce the GLM5 structured-output bug."""

    topic: str = Field(..., description="The main research topic")
    rationale: str = Field(..., description="Why this topic matters")
    perspectives: List[str] = Field(..., description="3-5 viewpoints to explore")
    questions: List[str] = Field(..., description="3-5 research questions")
    success_criteria: List[str] = Field(..., description="2-3 success metrics")


async def main() -> int:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[FAIL] OPENROUTER_API_KEY not set in .env")
        return 1

    model = "z-ai/glm-5.1"
    print(f"[smoke] Model: {model}")
    print(f"[smoke] Schema: ComplexPlan (5 fields)")

    client = OpenRouterClient(
        api_key=api_key,
        model=model,
    )

    prompt = (
        "Plan a research investigation into intermittent fasting and metabolic health. "
        "Provide 3 perspectives, 3 research questions, and 2 success criteria."
    )

    try:
        plan = await client.generate_structured(
            prompt=prompt,
            schema=ComplexPlan,
            max_tokens=4096,
        )
    except Exception as exc:
        print(f"[FAIL] generate_structured raised: {type(exc).__name__}: {exc}")
        return 1

    if plan is None:
        print("[FAIL] generate_structured returned None")
        return 1

    print("[smoke] Got ComplexPlan instance")
    print(f"  topic: {plan.topic[:100]}")
    print(f"  rationale: {plan.rationale[:100]}")
    print(f"  perspectives ({len(plan.perspectives)}): {plan.perspectives[:2]}")
    print(f"  questions ({len(plan.questions)}): {plan.questions[:2]}")
    print(f"  success_criteria ({len(plan.success_criteria)}): {plan.success_criteria[:2]}")

    # Validate substance
    issues = []
    if not plan.topic or len(plan.topic.strip()) < 5:
        issues.append("topic empty or too short")
    if not plan.rationale or len(plan.rationale.strip()) < 10:
        issues.append("rationale empty or too short")
    if len(plan.perspectives) < 2:
        issues.append(f"perspectives count {len(plan.perspectives)} < 2")
    if len(plan.questions) < 2:
        issues.append(f"questions count {len(plan.questions)} < 2")
    if len(plan.success_criteria) < 1:
        issues.append(f"success_criteria count {len(plan.success_criteria)} < 1")

    if issues:
        print(f"[FAIL] Substance issues: {issues}")
        return 1

    print("[PASS] FIX-GLM5-STRUCTURED smoke test")
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
