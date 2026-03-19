"""ReAct analysis agent — autonomous tool selection for evidence analysis.

Supports three pipeline modes (PG_ANALYSIS_PIPELINE env var):
- "8phase" (default): Plan→Execute→Briefing→Scaffold→Write→Critique→Rewrite→Verify
- "legacy": Plan→Execute→Interpret→Verify (2 LLM calls, ReWOO pattern)
- "react": Per-step LLM decisions (up to 5+1 LLM calls)

The 8-phase pipeline fixes substance deficits (parroting, no integration,
low evidence utilization) by interposing a learnings gateway + analytical
scaffold + iterative critique between execution and writing.

The agent enforces citation provenance: every analysis result traces back
to original evidence IDs, never "POLARIS Analysis Toolkit".
"""

import asyncio
import json
import logging
import os
import re
import time

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook, AnalysisStep
from src.polaris_graph.tools.tool_registry import (
    ToolRegistry,
    ToolResult,
    build_default_registry,
)
from src.utils.embedding_service import embed_text, embed_texts

logger = logging.getLogger("polaris_graph")

_MAX_ITERATIONS = int(os.getenv("PG_REACT_MAX_ITERATIONS", "5"))
_TIMEOUT_SECONDS = int(os.getenv("PG_REACT_TIMEOUT_SECONDS", "900"))
_TOOL_TIMEOUT = int(os.getenv("PG_REACT_TOOL_TIMEOUT", "60"))
_INTERPRET_TIMEOUT = int(os.getenv("PG_REACT_INTERPRET_TIMEOUT", "240"))

# 8-phase pipeline env vars
_ANALYSIS_PIPELINE = os.getenv("PG_ANALYSIS_PIPELINE", "8phase")
_DOMAIN_RELEVANCE_THRESHOLD = float(
    os.getenv("PG_DOMAIN_RELEVANCE_THRESHOLD", "0.15"),
)
_LEARNINGS_PER_CLUSTER = int(os.getenv("PG_LEARNINGS_PER_CLUSTER", "8"))
_MAX_CLUSTERS = int(os.getenv("PG_MAX_CLUSTERS", "15"))
_MAX_INTERPRETATION_REWRITES = int(
    os.getenv("PG_MAX_INTERPRETATION_REWRITES", "1"),
)
_SCAFFOLD_TIMEOUT = int(os.getenv("PG_SCAFFOLD_TIMEOUT", "240"))
_CRITIQUE_TIMEOUT = int(os.getenv("PG_CRITIQUE_TIMEOUT", "180"))

# Learnings extraction env vars
_LLM_LEARNINGS_ENABLED = os.getenv("PG_LLM_LEARNINGS_ENABLED", "1") == "1"
_LEARNINGS_BATCH_SIZE = int(os.getenv("PG_LEARNINGS_BATCH_SIZE", "10"))
_LEARNINGS_BATCH_TIMEOUT = int(os.getenv("PG_LEARNINGS_BATCH_TIMEOUT", "180"))
_LEARNINGS_MAX_CONCURRENCY = int(
    os.getenv("PG_LEARNINGS_MAX_CONCURRENCY", "3"),
)

# Tool names Qwen is allowed to pick (for extraction from malformed JSON)
_KNOWN_TOOLS = {
    "extract_numeric_data", "query_evidence_sql", "statistical_summary",
    "comparison_table", "meta_analysis", "agreement_analysis",
    "execute_python", "rank_by_impact", "stop",
}


class ReactDecision(BaseModel):
    """LLM's decision on what to do next in the ReAct loop.

    Qwen 3.5 Plus sometimes returns simplified JSON that doesn't match
    the schema exactly (e.g. {"tool": "extract_numeric_data"} instead
    of {"reasoning": "...", "action": "..."}). The model_validator
    normalizes common deviations.
    """

    reasoning: str = Field(
        description="Your reasoning for choosing this tool",
        default="",
    )
    action: str = Field(
        description="Tool name to execute, or 'stop' to finish analysis",
    )
    action_input: dict = Field(
        description="Parameters for the tool (empty dict if none needed)",
        default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema.

        Known patterns:
        - {"tool": "xxx"} instead of {"action": "xxx"}
        - {"action": {"tool": "xxx"}} nested dict
        - {"next_step": "xxx"} alternate field name
        - Missing "reasoning" field entirely
        - {"thought": "..."} instead of {"reasoning": "..."}
        """
        if not isinstance(data, dict):
            return data

        # Normalize "tool" -> "action"
        for alt in ("tool", "tool_name", "next_step", "next_action", "name"):
            if alt in data and "action" not in data:
                data["action"] = data.pop(alt)

        # Unwrap nested {"action": {"tool": "xxx"}}
        if isinstance(data.get("action"), dict):
            nested = data["action"]
            tool_name = (
                nested.get("tool")
                or nested.get("name")
                or nested.get("tool_name")
                or ""
            )
            if tool_name:
                data["action"] = str(tool_name)
            else:
                # Last resort: find any known tool name in the dict values
                for v in nested.values():
                    if isinstance(v, str) and v in _KNOWN_TOOLS:
                        data["action"] = v
                        break
                else:
                    data["action"] = "stop"

        # Normalize "thought"/"explanation"/"reason" -> "reasoning"
        for alt in ("thought", "explanation", "reason", "thinking",
                     "rationale"):
            if alt in data and "reasoning" not in data:
                data["reasoning"] = data.pop(alt)

        # Default reasoning if missing
        if "reasoning" not in data or not data["reasoning"]:
            action = data.get("action", "unknown")
            data["reasoning"] = f"Selected {action}"

        # Normalize "params"/"parameters"/"input"/"args" -> "action_input"
        for alt in ("params", "parameters", "input", "args",
                     "tool_input", "kwargs"):
            if alt in data and "action_input" not in data:
                data["action_input"] = data.pop(alt)

        return data

    @field_validator("action", mode="before")
    @classmethod
    def coerce_action(cls, v):
        """Coerce action to string, handling unexpected types."""
        if isinstance(v, str):
            return v.strip().lower()
        if isinstance(v, dict):
            # {"tool": "xxx"} pattern
            return str(
                v.get("tool") or v.get("name") or v.get("action") or "stop"
            ).strip().lower()
        return str(v).strip().lower() if v else "stop"


class PlannedStep(BaseModel):
    """A single planned analysis step for the agentic pipeline.

    Qwen 3.5 Plus returns simplified JSON — the model_validator
    normalizes common deviations (same pattern as ReactDecision).
    """

    tool_name: str = Field(description="Tool to execute")
    reasoning: str = Field(
        description="Why this tool should run", default="",
    )
    parameters: dict = Field(
        description="Tool parameters", default_factory=dict,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema."""
        if not isinstance(data, dict):
            return data
        for alt in ("tool", "name", "action", "step", "tool_id"):
            if alt in data and "tool_name" not in data:
                data["tool_name"] = data.pop(alt)
        for alt in ("thought", "explanation", "reason", "rationale", "why"):
            if alt in data and "reasoning" not in data:
                data["reasoning"] = data.pop(alt)
        for alt in ("params", "args", "input", "kwargs", "action_input"):
            if alt in data and "parameters" not in data:
                data["parameters"] = data.pop(alt)
        if "reasoning" not in data or not data.get("reasoning"):
            data["reasoning"] = f"Run {data.get('tool_name', 'unknown')}"
        return data

    @field_validator("tool_name", mode="before")
    @classmethod
    def coerce_tool_name(cls, v):
        """Coerce tool_name to lowercase string."""
        if isinstance(v, str):
            return v.strip().lower()
        if isinstance(v, dict):
            return str(
                v.get("tool") or v.get("name") or "extract_numeric_data"
            ).strip().lower()
        return str(v).strip().lower() if v else "extract_numeric_data"


class AnalysisPlan(BaseModel):
    """LLM's analysis plan — ordered list of tools to execute.

    The agentic pipeline asks for ONE plan upfront (ReWOO pattern),
    then executes all steps deterministically without further LLM calls.
    """

    steps: list[PlannedStep] = Field(
        description="Ordered list of analysis steps",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        """Handle common Qwen deviations from the expected schema."""
        # Handle bare list: Qwen returns ["tool1", "tool2"] or [{"tool": ...}]
        if isinstance(data, list):
            data = {"steps": data}
        if not isinstance(data, dict):
            return data
        for alt in ("plan", "tools", "actions", "tool_sequence", "sequence",
                     "analysis_steps", "ordered_steps"):
            if alt in data and "steps" not in data:
                data["steps"] = data.pop(alt)
        # Handle flat tool list: ["extract_numeric_data", "statistical_summary"]
        if isinstance(data.get("steps"), list) and data["steps"]:
            if isinstance(data["steps"][0], str):
                data["steps"] = [{"tool_name": t} for t in data["steps"]]
        return data


# ---------------------------------------------------------------------------
# 8-phase pipeline schemas
# ---------------------------------------------------------------------------

class CritiqueDimension(BaseModel):
    """Single dimension of the interpretation critique."""

    dimension: str = Field(description="Dimension name")
    passed: bool = Field(
        description="Whether this dimension passes", default=False,
    )
    issues: list[str] = Field(
        description="Specific problems found", default_factory=list,
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        for alt in ("name", "dim", "category"):
            if alt in data and "dimension" not in data:
                data["dimension"] = data.pop(alt)
        for alt in ("pass", "ok", "passed", "status", "result",
                     "verdict"):
            if alt in data and "passed" not in data:
                data["passed"] = data.pop(alt)
        # Coerce string "PASS"/"FAIL" → bool
        if isinstance(data.get("passed"), str):
            data["passed"] = data["passed"].upper() in (
                "PASS", "TRUE", "YES", "OK", "PASSED",
            )
        for alt in ("problems", "findings", "errors"):
            if alt in data and "issues" not in data:
                data["issues"] = data.pop(alt)
        return data


class InterpretationCritique(BaseModel):
    """Structured critique of an interpretation across 5 dimensions."""

    dimensions: list[CritiqueDimension] = Field(
        description="Critique per dimension",
    )
    needs_rewrite: bool = Field(
        description="Whether the interpretation needs rewriting",
    )
    rewrite_instructions: str = Field(
        description="Specific fix instructions for the rewriter",
        default="",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        # Unwrap nested wrappers: Qwen sometimes wraps in
        # {"interpretation_critique": {actual_fields...}}
        for wrapper_key in list(data.keys()):
            val = data[wrapper_key]
            if (
                isinstance(val, dict)
                and len(data) == 1
                and any(
                    k in val
                    for k in ("dimensions", "needs_rewrite", "evaluation",
                              "dimension_evaluations")
                )
            ):
                data = val
                break
        # Catch-all: ANY key containing a list of dicts → dimensions
        # Qwen invents new field names every run.
        if "dimensions" not in data:
            for key, val in list(data.items()):
                if (
                    isinstance(val, list)
                    and val
                    and isinstance(val[0], dict)
                    and key not in ("needs_rewrite", "rewrite_instructions")
                ):
                    data["dimensions"] = data.pop(key)
                    break
            else:
                # Qwen returned evaluation as a single dict instead of
                # list — convert dict values to dimension list
                for key, val in list(data.items()):
                    if (
                        isinstance(val, dict)
                        and key not in (
                            "needs_rewrite", "rewrite_instructions",
                        )
                        and any(
                            isinstance(v, str)
                            for v in val.values()
                        )
                    ):
                        # {"sub_question_coverage": "PASS", ...}
                        dims = [
                            {"dimension": k, "passed": v}
                            for k, v in val.items()
                        ]
                        data["dimensions"] = dims
                        del data[key]
                        break
        for alt in ("rewrite", "needs_revision", "should_rewrite",
                     "verdict"):
            if alt in data and "needs_rewrite" not in data:
                val = data.pop(alt)
                # Coerce string verdicts like "PASS"/"FAIL" to bool
                if isinstance(val, str):
                    val = val.upper() in ("PASS", "TRUE", "YES", "OK")
                data["needs_rewrite"] = val
        for alt in ("instructions", "fix_instructions", "fixes"):
            if alt in data and "rewrite_instructions" not in data:
                data["rewrite_instructions"] = data.pop(alt)
        # Coerce None/list → "" for rewrite_instructions
        if not isinstance(data.get("rewrite_instructions"), str):
            data["rewrite_instructions"] = str(
                data.get("rewrite_instructions") or ""
            )
        return data


class ExtractedLearning(BaseModel):
    """A single distilled learning extracted from evidence."""

    fact: str = Field(description="Paraphrased concise factual learning")
    source_ids: list[str] = Field(
        description="Evidence IDs this was extracted from",
    )
    category: str = Field(
        description="Fact category", default="general",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if not isinstance(data, dict):
            return data
        for alt in ("learning", "insight", "finding", "statement",
                     "text", "content"):
            if alt in data and "fact" not in data:
                data["fact"] = data.pop(alt)
        for alt in ("sources", "evidence_ids", "ids", "evidence",
                     "source_evidence", "from_ids"):
            if alt in data and "source_ids" not in data:
                data["source_ids"] = data.pop(alt)
        for alt in ("type", "topic", "cat", "fact_category"):
            if alt in data and "category" not in data:
                data["category"] = data.pop(alt)
        if isinstance(data.get("source_ids"), str):
            data["source_ids"] = [data["source_ids"]]
        return data


class LearningsBatch(BaseModel):
    """Batch of extracted learnings from evidence statements."""

    learnings: list[ExtractedLearning] = Field(
        description="Extracted factual learnings",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_qwen_response(cls, data):
        if isinstance(data, list):
            data = {"learnings": data}
        if not isinstance(data, dict):
            return data
        for alt in ("facts", "findings", "insights", "extracted",
                     "results", "items"):
            if alt in data and "learnings" not in data:
                data["learnings"] = data.pop(alt)
        return data


class ReactAnalysisAgent:
    """ReAct loop that autonomously analyzes evidence using registered tools.

    Usage:
        agent = ReactAnalysisAgent(client, evidence_store, evidence_ids, query)
        notebook = await agent.run()
        entries = notebook.to_entries()
    """

    def __init__(
        self,
        client,
        evidence_store: dict,
        evidence_ids: list[str],
        query: str,
        registry: ToolRegistry | None = None,
        tracer=None,
        mode: str | None = None,
    ):
        self._client = client
        self._evidence_store = evidence_store
        self._evidence_ids = evidence_ids
        self._query = query
        self._registry = registry or build_default_registry()
        self._tracer = tracer
        self._notebook = AnalysisNotebook(query, evidence_ids)
        # Mode precedence: PG_REACT_MODE env (legacy compat) > constructor
        # > PG_ANALYSIS_PIPELINE env (pipeline default) > "8phase"
        react_mode = os.getenv("PG_REACT_MODE", "")
        if react_mode:
            self._mode = react_mode
        elif mode:
            self._mode = mode
        else:
            self._mode = os.getenv("PG_ANALYSIS_PIPELINE", "") or "8phase"

    async def run(self) -> AnalysisNotebook:
        """Execute analysis and return the notebook.

        Dispatches based on pipeline mode:
        - "8phase": Plan→Execute→Briefing→Scaffold→Write→Critique→Rewrite→Verify
        - "legacy"/"agentic": Plan→Execute→Interpret→Verify (2 LLM calls)
        - "react": Per-step LLM decisions
        """
        if self._mode == "react":
            return await self._run_react()
        if self._mode in ("legacy", "agentic"):
            return await self._run_agentic_analysis()
        return await self._run_8phase_analysis()

    async def _run_react(self) -> AnalysisNotebook:
        """Execute the ReAct loop (legacy mode)."""
        start_time = time.monotonic()
        max_iterations = _MAX_ITERATIONS
        timeout = _TIMEOUT_SECONDS

        logger.info(
            "[react] Starting analysis: %d evidence, max_iter=%d, timeout=%ds",
            len(self._evidence_ids), max_iterations, timeout,
        )

        for iteration in range(1, max_iterations + 1):
            elapsed = time.monotonic() - start_time

            # Budget check
            if elapsed >= timeout:
                logger.info(
                    "[react] Timeout reached after %.1fs, stopping", elapsed,
                )
                break

            # Decide next action (retry once on failure)
            decision = None
            for attempt in range(2):
                try:
                    decision = await self._decide(iteration)
                    break
                except Exception as exc:
                    logger.warning(
                        "[react] Decision attempt %d failed at iter %d: %s "
                        "(%s)",
                        attempt + 1, iteration,
                        type(exc).__name__, str(exc)[:200],
                    )
                    if attempt == 0:
                        await asyncio.sleep(1)  # Brief pause before retry

            if decision is None:
                logger.warning(
                    "[react] Decision failed after 2 attempts at iter %d, "
                    "running fallback",
                    iteration,
                )
                await self._run_fallback()
                break

            if decision.action == "stop":
                logger.info(
                    "[react] LLM chose to stop: %s", decision.reasoning[:100],
                )
                break

            # Execute the chosen tool
            step = await self._execute_tool(iteration, decision)
            self._notebook.add_step(step)

            logger.info(
                "[react] Step %d: %s [%s] %.1fs — %s",
                iteration,
                decision.action,
                "OK" if step.result.success else "FAIL",
                step.elapsed_seconds,
                decision.reasoning[:60],
            )

            # Check sufficiency
            if self._is_sufficient():
                logger.info("[react] Sufficient analysis achieved, stopping")
                break

        # If no steps succeeded, run fallback
        if self._notebook.successful_steps == 0:
            logger.warning("[react] No successful steps, running fallback")
            await self._run_fallback()

        # POST-PROCESSING: LLM interprets raw results into real insights
        # This is what separates "regex + scipy" from "analyst with reasoning"
        if self._notebook.successful_steps > 0 and self._client:
            await self._interpret_results()

        total_elapsed = time.monotonic() - start_time
        logger.info(
            "[react] Analysis complete: %d steps (%d ok), %d data points, "
            "%.1fs",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
        )

        return self._notebook

    # -------------------------------------------------------------------
    # Agentic pipeline (Plan -> Execute -> Interpret -> Verify)
    # -------------------------------------------------------------------

    async def _run_agentic_analysis(self) -> AnalysisNotebook:
        """Execute Plan -> Execute -> Interpret -> Verify pipeline.

        Phase 1: PLAN — 1 generate_structured() call produces AnalysisPlan
        Phase 2: EXECUTE — deterministic tool execution, 0 LLM calls
        Phase 3: INTERPRET — 1 generate() call produces analytical prose
        Phase 4: VERIFY — programmatic claim<->evidence check, 0 LLM calls
        """
        start_time = time.monotonic()
        timeout = _TIMEOUT_SECONDS

        logger.info(
            "[agentic] Starting analysis: %d evidence, timeout=%ds",
            len(self._evidence_ids), timeout,
        )

        # Phase 1: PLAN (1 LLM call, ~75s)
        plan = None
        try:
            plan = await self._plan_analysis()
            logger.info(
                "[agentic] Plan: %s",
                [s.tool_name for s in plan.steps],
            )
        except Exception as exc:
            logger.warning(
                "[agentic] Plan failed: %s: %s, using fallback plan",
                type(exc).__name__, str(exc)[:200],
            )

        if not plan or not plan.steps:
            plan = AnalysisPlan(steps=[
                PlannedStep(
                    tool_name="extract_numeric_data",
                    reasoning="Always extract first",
                ),
                PlannedStep(
                    tool_name="statistical_summary",
                    reasoning="Compute statistics on extracted data",
                ),
                PlannedStep(
                    tool_name="query_evidence_sql",
                    reasoning="Get tier distribution and metadata",
                ),
            ])
            logger.info(
                "[agentic] Using fallback plan: %s",
                [s.tool_name for s in plan.steps],
            )

        # Phase 2: EXECUTE (0 LLM calls, ~10s)
        for step_def in plan.steps:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info(
                    "[agentic] Timeout after %.1fs, stopping execution",
                    elapsed,
                )
                break

            tool_def = self._registry.get_tool(step_def.tool_name)
            if not tool_def or not tool_def.execute:
                logger.warning(
                    "[agentic] Skipping unknown tool: %s",
                    step_def.tool_name,
                )
                continue

            # Skip data-requiring tools if no data yet
            if tool_def.requires_data and not self._notebook.has_data:
                logger.info(
                    "[agentic] Skipping %s (requires data, none yet)",
                    step_def.tool_name,
                )
                continue

            step_start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    tool_def.execute(
                        evidence_store=self._evidence_store,
                        data_points=self._notebook.data_points,
                        client=self._client,
                        **step_def.parameters,
                    ),
                    timeout=_TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result = ToolResult(
                    success=False,
                    tool_name=step_def.tool_name,
                    markdown=f"Tool timed out after {_TOOL_TIMEOUT}s",
                    error=f"Timeout after {_TOOL_TIMEOUT}s",
                )
            except Exception as exc:
                result = ToolResult(
                    success=False,
                    tool_name=step_def.tool_name,
                    markdown=f"Tool error: {str(exc)[:200]}",
                    error=str(exc)[:500],
                )

            step_elapsed = time.monotonic() - step_start
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=step_def.reasoning or f"Planned: {step_def.tool_name}",
                tool_name=step_def.tool_name,
                result=result,
                elapsed_seconds=round(step_elapsed, 3),
            )
            self._notebook.add_step(step)

            logger.info(
                "[agentic] Step %d: %s [%s] %.1fs",
                step.step_number,
                step_def.tool_name,
                "OK" if result.success else "FAIL",
                step_elapsed,
            )

        # If no steps succeeded, run deterministic fallback
        if self._notebook.successful_steps == 0:
            logger.warning("[agentic] No successful steps, running fallback")
            await self._run_fallback()

        # Phase 3: INTERPRET (1 LLM call, ~120s)
        if self._notebook.successful_steps > 0 and self._client:
            await self._interpret_results()

        # Phase 4: VERIFY (programmatic, ~5s)
        verification = self._verify_claims()
        if verification:
            logger.info(
                "[agentic] Verification: %d/%d claims verified, "
                "%d mismatches",
                verification.get("verified", 0),
                verification.get("total_claims_checked", 0),
                verification.get("mismatches", 0),
            )

        total_elapsed = time.monotonic() - start_time
        logger.info(
            "[agentic] Complete: %d steps (%d ok), %d data points, %.1fs",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
        )

        return self._notebook

    # -------------------------------------------------------------------
    # 8-phase pipeline (Briefing→Scaffold→Write→Critique→Rewrite→Verify)
    # -------------------------------------------------------------------

    async def _run_8phase_analysis(self) -> AnalysisNotebook:
        """Execute 8-phase SOTA analysis pipeline.

        Phase 1: PLAN      — 1 generate_structured() call
        Phase 2: EXECUTE   — deterministic tool execution, 0 LLM calls
        Phase 3: BRIEFING  — cluster + distill ALL evidence, 0 LLM calls
        Phase 4: SCAFFOLD  — 1 reason() call: analytical framework
        Phase 5: WRITE     — 1 generate() call: prose from scaffold
        Phase 6: CRITIQUE  — 1 reason() call: structured quality check
        Phase 7: REWRITE   — 0-1 generate() call: fix critique issues
        Phase 8: VERIFY    — programmatic claim verification
        """
        start_time = time.monotonic()
        timeout = _TIMEOUT_SECONDS

        logger.info(
            "[8phase] Starting analysis: %d evidence, timeout=%ds",
            len(self._evidence_ids), timeout,
        )

        # Phase 1: PLAN (1 LLM call)
        plan = None
        try:
            plan = await self._plan_analysis()
            logger.info(
                "[8phase] Plan: %s",
                [s.tool_name for s in plan.steps],
            )
        except Exception as exc:
            logger.warning(
                "[8phase] Plan failed: %s: %s, using fallback",
                type(exc).__name__, str(exc)[:200],
            )

        if not plan or not plan.steps:
            plan = AnalysisPlan(steps=[
                PlannedStep(
                    tool_name="extract_numeric_data",
                    reasoning="Always extract first",
                ),
                PlannedStep(
                    tool_name="statistical_summary",
                    reasoning="Compute statistics on extracted data",
                ),
                PlannedStep(
                    tool_name="query_evidence_sql",
                    reasoning="Get tier distribution and metadata",
                ),
            ])

        # Phase 2: EXECUTE (0 LLM calls)
        for step_def in plan.steps:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                logger.info("[8phase] Timeout after %.1fs", elapsed)
                break

            tool_def = self._registry.get_tool(step_def.tool_name)
            if not tool_def or not tool_def.execute:
                continue
            if tool_def.requires_data and not self._notebook.has_data:
                continue

            step_start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    tool_def.execute(
                        evidence_store=self._evidence_store,
                        data_points=self._notebook.data_points,
                        client=self._client,
                        **step_def.parameters,
                    ),
                    timeout=_TOOL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                result = ToolResult(
                    success=False, tool_name=step_def.tool_name,
                    error=f"Timeout after {_TOOL_TIMEOUT}s",
                )
            except Exception as exc:
                result = ToolResult(
                    success=False, tool_name=step_def.tool_name,
                    error=str(exc)[:500],
                )

            step_elapsed = time.monotonic() - step_start
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=step_def.reasoning or f"Planned: {step_def.tool_name}",
                tool_name=step_def.tool_name,
                result=result,
                elapsed_seconds=round(step_elapsed, 3),
            )
            self._notebook.add_step(step)
            logger.info(
                "[8phase] Step %d: %s [%s] %.1fs",
                step.step_number, step_def.tool_name,
                "OK" if result.success else "FAIL", step_elapsed,
            )

        if self._notebook.successful_steps == 0:
            await self._run_fallback()

        # Phase 3: BRIEFING (1+ LLM calls when learnings enabled)
        # Time budget: track remaining time for graceful degradation
        elapsed_before_briefing = time.monotonic() - start_time
        remaining = timeout - elapsed_before_briefing
        briefing = await self._build_evidence_briefing()
        logger.info(
            "[8phase] Briefing: %d learnings, %d clusters, %d sub-questions "
            "(%.0fs remaining)",
            len(briefing.get("learnings", [])),
            len(briefing.get("clusters", [])),
            len(briefing.get("sub_questions", [])),
            remaining,
        )

        # Phase 4: SCAFFOLD (1 reason() call)
        scaffold = ""
        elapsed = time.monotonic() - start_time
        if (
            self._notebook.successful_steps > 0
            and self._client
            and elapsed < timeout - 60  # need >=60s for write
        ):
            scaffold = await self._generate_analytical_scaffold(briefing)
            logger.info(
                "[8phase] Scaffold: %d chars", len(scaffold),
            )

        # Phase 5: WRITE (1 generate() call)
        interpretation = ""
        elapsed = time.monotonic() - start_time
        if scaffold and self._client and elapsed < timeout - 30:
            interpretation = await self._write_interpretation(
                scaffold, briefing,
            )
            logger.info(
                "[8phase] Interpretation: %d chars", len(interpretation),
            )

        # FALLBACK: if scaffold or write failed, ALWAYS use legacy interpret.
        # No time budget check — producing zero prose is worse than overtime.
        if not interpretation and self._notebook.successful_steps > 0:
            if self._client:
                logger.info(
                    "[8phase] Scaffold/write failed, falling back to "
                    "legacy interpret (elapsed=%.0fs)",
                    time.monotonic() - start_time,
                )
                await self._interpret_results()
                for step in self._notebook.steps:
                    if (
                        step.tool_name == "interpret_results"
                        and step.result.success
                    ):
                        interpretation = step.result.markdown
                        break

        # Phase 6: CRITIQUE (1 reason() call)
        critique = None
        elapsed = time.monotonic() - start_time
        if interpretation and self._client and elapsed < timeout - 30:
            critique = await self._critique_interpretation(
                interpretation, briefing,
            )
            if critique:
                logger.info(
                    "[8phase] Critique: needs_rewrite=%s, %d/%d dims passed",
                    critique.get("needs_rewrite"),
                    sum(1 for d in critique.get("dimensions", [])
                        if d.get("passed")),
                    len(critique.get("dimensions", [])),
                )

        # Phase 7: REWRITE (conditional, 0-1 generate() call)
        elapsed = time.monotonic() - start_time
        if (
            critique
            and critique.get("needs_rewrite")
            and interpretation
            and self._client
            and elapsed < timeout - 30
        ):
            rewritten = await self._rewrite_interpretation(
                interpretation, critique, briefing,
            )
            if rewritten:
                interpretation = rewritten
                logger.info(
                    "[8phase] Rewrite: %d chars", len(interpretation),
                )

        # Phase 7.5: POST-PROCESS (programmatic cleanup)
        if interpretation:
            cleaned = self._post_process_interpretation(interpretation)
            if cleaned != interpretation:
                interpretation = cleaned
                # Update the notebook step with cleaned content
                for step in self._notebook.steps:
                    if (
                        step.tool_name == "interpret_results"
                        and step.result.success
                    ):
                        step.result = ToolResult(
                            success=True,
                            tool_name="interpret_results",
                            markdown=cleaned,
                            source_evidence_ids=(
                                step.result.source_evidence_ids
                            ),
                            insights=step.result.insights,
                        )
                        break
                logger.info(
                    "[8phase] Post-process: %d -> %d chars",
                    len(interpretation), len(cleaned),
                )

        # Phase 8: VERIFY (programmatic)
        verification = self._verify_claims(briefing=briefing)
        if verification:
            logger.info(
                "[8phase] Verification: %d/%d verified, %d mismatches",
                verification.get("verified", 0),
                verification.get("total_claims_checked", 0),
                verification.get("mismatches", 0),
            )

        total_elapsed = time.monotonic() - start_time
        logger.info(
            "[8phase] Complete: %d steps (%d ok), %d data points, %.1fs",
            self._notebook.step_count,
            self._notebook.successful_steps,
            len(self._notebook.data_points),
            total_elapsed,
        )

        return self._notebook

    # -------------------------------------------------------------------
    # Phase 3: BRIEFING — evidence distillation + clustering
    # -------------------------------------------------------------------

    @staticmethod
    def _distill_fact(statement: str) -> str:
        """Distill an evidence statement to a concise fact (~20 words).

        Strips common boilerplate prefixes and truncates to ~20 words.
        Pure regex, no LLM call.
        """
        if not statement:
            return ""

        text = statement.strip()

        # Strip boilerplate prefixes
        boilerplate_patterns = [
            r'^(?:the\s+)?(?:study|research|analysis|report|paper|'
            r'investigation|review|assessment)\s+'
            r'(?:found|showed|demonstrated|revealed|indicated|reported|'
            r'concluded|suggests?|confirms?|determined)\s+that\s+',
            r'^(?:according\s+to\s+(?:the|a|this)\s+'
            r'(?:study|research|report|analysis|data|findings)),?\s*',
            r'^(?:it\s+(?:was|is|has\s+been)\s+'
            r'(?:found|shown|demonstrated|reported|observed)\s+that\s+)',
            r'^(?:results?\s+(?:show|indicate|suggest|demonstrate)\s+that\s+)',
            r'^(?:data\s+(?:shows?|indicates?|suggests?)\s+that\s+)',
        ]
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Truncate to ~20 words
        words = text.split()
        if len(words) > 20:
            text = " ".join(words[:20]) + "..."

        return text.strip()

    # -------------------------------------------------------------------
    # Learnings extraction (LLM-based, replaces regex _distill_fact)
    # -------------------------------------------------------------------

    async def _extract_learnings_batch(
        self,
        evidence_batch: list[dict],
    ) -> list[dict]:
        """Extract learnings from a batch of evidence via free-form LLM.

        Uses generate() (NOT generate_structured) — Qwen is much faster
        without JSON schema enforcement. Parses markdown bullets with regex.
        Falls back to _distill_fact() on failure.
        """
        if not self._client or not evidence_batch:
            return self._fallback_distill_batch(evidence_batch)

        evidence_lines = []
        valid_ids = set()
        for ev_dict in evidence_batch:
            eid = ev_dict["eid"]
            # 60 chars per item keeps prompt compact for large batches
            stmt = ev_dict["statement"][:60]
            valid_ids.add(eid)
            evidence_lines.append(f"[{eid}]: {stmt}")

        evidence_text = "\n".join(evidence_lines)

        # Scale target learnings to batch size
        target_min = max(10, len(evidence_batch) // 5)
        target_max = max(20, len(evidence_batch) // 2)

        prompt = (
            f"RESEARCH: {self._query[:100]}\n\n"
            f"EVIDENCE ({len(evidence_batch)} items):\n"
            f"{evidence_text}\n\n"
            f"Distill into {target_min}-{target_max} paraphrased "
            f"learnings. Format EXACTLY:\n"
            f"- [ev_xxx] (category) Paraphrased fact with numbers\n\n"
            f"REPHRASE (never copy wording), keep numbers exact, "
            f"merge duplicates. Categories: performance, cost, "
            f"comparison, mechanism, limitation, application, general."
        )

        system = (
            "Distill evidence into paraphrased bullet points. "
            "Format: - [ev_xxx] (category) fact. Never copy wording."
        )

        # Learnings must fail fast — scaffold is what produces quality.
        # Cap at 45s so 3 concurrent batches consume ≤45s total,
        # leaving 500+ seconds for scaffold+write+critique.
        # MUST pass to generate() — otherwise DEFAULT_TIMEOUT_SECONDS=90
        # kills the httpx call internally.
        batch_timeout = _LEARNINGS_BATCH_TIMEOUT  # default 45s

        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=min(4096, len(evidence_batch) * 40),
                    temperature=0.3,
                    timeout=batch_timeout,
                ),
                timeout=batch_timeout + 30,
            )

            content = response.content.strip()
            if not content:
                return self._fallback_distill_batch(evidence_batch)

            raw_learnings = self._parse_learning_bullets(
                content, valid_ids,
            )

            if raw_learnings:
                logger.info(
                    "[8phase] LLM learnings: %d input -> %d learnings",
                    len(evidence_batch), len(raw_learnings),
                )
                return raw_learnings

            logger.warning(
                "[8phase] LLM learnings parsed 0 from %d chars, "
                "regex fallback",
                len(content),
            )
            return self._fallback_distill_batch(evidence_batch)

        except asyncio.TimeoutError:
            logger.warning(
                "[8phase] LLM learnings timed out (%ds for %d ev), "
                "regex fallback",
                batch_timeout, len(evidence_batch),
            )
            return self._fallback_distill_batch(evidence_batch)
        except Exception as exc:
            logger.warning(
                "[8phase] LLM learnings failed: %s: %s, regex fallback",
                type(exc).__name__, str(exc)[:300],
            )
            return self._fallback_distill_batch(evidence_batch)

    def _fallback_distill_batch(
        self, evidence_batch: list[dict],
    ) -> list[dict]:
        """Regex-based fallback for a failed LLM learnings batch."""
        results = []
        for ev_dict in evidence_batch:
            fact = self._distill_fact(ev_dict["statement"])
            if fact:
                results.append({
                    "fact": fact,
                    "source_ids": [ev_dict["eid"]],
                    "category": ev_dict["category"],
                })
        return results

    async def _extract_all_learnings(self) -> list[dict]:
        """Extract learnings from ALL evidence in a single LLM call.

        Uses generate() with a compact evidence summary — one call for
        all evidence instead of batched calls. Qwen's per-call overhead
        (~6s routing + thinking) makes batching unviable.

        Returns list of dicts compatible with _build_evidence_briefing.
        """
        evidence_items = []
        for eid in self._evidence_ids:
            ev = self._evidence_store.get(eid, {})
            stmt = ev.get("statement", "")
            if not stmt or len(stmt) < 10:
                continue
            evidence_items.append({
                "eid": eid,
                "statement": stmt,
                "category": ev.get("fact_category", "general"),
                "tier": ev.get("quality_tier", "BRONZE"),
                "relevance": float(ev.get("relevance_score", 0.5)),
                "perspective": ev.get("perspective", ""),
            })

        if not evidence_items:
            return []

        # Gate: LLM learnings disabled or no client
        if not _LLM_LEARNINGS_ENABLED or not self._client:
            logger.info(
                "[8phase] LLM learnings disabled, using regex (%d ev)",
                len(evidence_items),
            )
            return self._build_learnings_from_regex(evidence_items)

        # Split into ~3 large batches for concurrent extraction
        # Qwen takes ~3s/item — 3 batches of 85 items concurrently ≈ 90s
        batch_size = max(
            _LEARNINGS_BATCH_SIZE,
            (len(evidence_items) + 2) // 3,  # ~3 batches
        )
        batches = [
            evidence_items[i:i + batch_size]
            for i in range(0, len(evidence_items), batch_size)
        ]

        logger.info(
            "[8phase] LLM learnings: %d evidence -> %d batches of ~%d",
            len(evidence_items), len(batches), batch_size,
        )

        # Run batches concurrently
        sem = asyncio.Semaphore(_LEARNINGS_MAX_CONCURRENCY)

        async def _run_batch(batch):
            async with sem:
                return await self._extract_learnings_batch(batch)

        batch_results = await asyncio.gather(
            *[_run_batch(b) for b in batches],
            return_exceptions=True,
        )

        # Merge results, regex fallback per failed batch
        raw_learnings = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(
                    "[8phase] Batch %d failed (%s), regex fallback",
                    i, str(result)[:100],
                )
                raw_learnings.extend(
                    self._fallback_distill_batch(batches[i]),
                )
            elif isinstance(result, list):
                raw_learnings.extend(result)
            else:
                raw_learnings.extend(
                    self._fallback_distill_batch(batches[i]),
                )

        return self._enrich_learnings(raw_learnings, evidence_items)

    def _parse_learning_bullets(
        self,
        content: str,
        valid_ids: set[str],
    ) -> list[dict]:
        """Parse markdown bullet list into learning dicts.

        Expected format: - [ev_xxx] (category) fact text
        Also handles: - [ev_xxx, ev_yyy] (category) fact text
        Tolerant of trailing commas, truncated IDs, missing parens.
        """
        learnings = []

        # Primary pattern: - [ev_xxx] (category) fact
        bullet_pattern = re.compile(
            r'^[-*]\s*\[([^\]]+)\]\s*'      # evidence IDs in brackets
            r'(?:\((\w+)\)\s*)?'             # optional category in parens
            r'(.+)$',                         # fact text
            re.MULTILINE,
        )

        for match in bullet_pattern.finditer(content):
            ids_str = match.group(1)
            category = (match.group(2) or "general").lower()
            fact = match.group(3).strip()

            # Extract all ev_xxx patterns from the IDs string
            # (handles trailing commas, spaces, truncated hashes)
            raw_ids = re.findall(r'ev_[a-f0-9]{6,}', ids_str)
            validated_ids = [sid for sid in raw_ids if sid in valid_ids]

            if not validated_ids or not fact or len(fact) < 10:
                continue

            learnings.append({
                "fact": fact,
                "source_ids": validated_ids,
                "category": category,
            })

        return learnings

    def _build_learnings_from_regex(
        self, evidence_items: list[dict],
    ) -> list[dict]:
        """Build learnings via regex fallback for ALL evidence."""
        results = []
        for ev in evidence_items:
            fact = self._distill_fact(ev["statement"])
            if not fact:
                continue
            results.append({
                "fact": fact,
                "category": ev["category"],
                "tier": ev["tier"],
                "evidence_ids": [ev["eid"]],
                "relevance": ev["relevance"],
                "perspective": ev["perspective"],
                "original_statement": ev["statement"],
            })
        return results

    def _enrich_learnings(
        self,
        raw_learnings: list[dict],
        evidence_items: list[dict],
    ) -> list[dict]:
        """Enrich LLM-extracted learnings with metadata from sources.

        Maps source_ids back to tier/relevance/perspective, producing
        dicts compatible with downstream consumers.
        """
        ev_lookup = {ev["eid"]: ev for ev in evidence_items}
        tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

        enriched = []
        for learning in raw_learnings:
            source_ids = learning.get(
                "source_ids", learning.get("evidence_ids", []),
            )
            tier = "BRONZE"
            relevance = 0.5
            perspective = ""
            original_stmt = ""
            for sid in source_ids:
                if sid in ev_lookup:
                    src = ev_lookup[sid]
                    if tier_order.get(src["tier"], 3) < tier_order.get(
                        tier, 3,
                    ):
                        tier = src["tier"]
                    relevance = max(relevance, src["relevance"])
                    if not perspective:
                        perspective = src["perspective"]
                    if not original_stmt:
                        original_stmt = src["statement"]

            enriched.append({
                "fact": learning["fact"],
                "category": learning.get("category", "general"),
                "tier": tier,
                "evidence_ids": source_ids,
                "relevance": relevance,
                "perspective": perspective,
                "original_statement": original_stmt,
            })

        return enriched

    async def _build_evidence_briefing(self) -> dict:
        """Build structured evidence briefing from ALL evidence (Phase 3).

        Uses LLM-based learnings extraction (when enabled) to force
        paraphrasing. Falls back to regex distillation on failure.

        Returns:
            {
                "learnings": [{"fact": str, "category": str, "tier": str,
                              "evidence_ids": [str], "relevance": float}],
                "clusters": [{"theme": str, "learning_indices": [int],
                             "evidence_count": int}],
                "sub_questions": [str],
                "comparison_matrix": str,
            }
        """
        # Step 1: Extract learnings (LLM-based or regex fallback)
        raw_learnings = await self._extract_all_learnings()

        if not raw_learnings:
            return {
                "learnings": [],
                "clusters": [],
                "sub_questions": self._decompose_query(),
                "comparison_matrix": "",
            }

        # Step 2: Domain filter via embedding similarity
        try:
            query_embedding = embed_text(self._query)
            fact_texts = [l["fact"] for l in raw_learnings]
            fact_embeddings = embed_texts(fact_texts)

            query_vec = np.array(query_embedding)
            filtered_learnings = []
            filtered_embeddings = []
            for i, learning in enumerate(raw_learnings):
                fact_vec = np.array(fact_embeddings[i])
                norm_q = np.linalg.norm(query_vec)
                norm_f = np.linalg.norm(fact_vec)
                if norm_q > 0 and norm_f > 0:
                    cos_sim = float(
                        np.dot(query_vec, fact_vec) / (norm_q * norm_f)
                    )
                else:
                    cos_sim = 0.0

                if cos_sim >= _DOMAIN_RELEVANCE_THRESHOLD:
                    learning["relevance"] = max(
                        learning["relevance"], cos_sim,
                    )
                    filtered_learnings.append(learning)
                    filtered_embeddings.append(fact_embeddings[i])

            logger.info(
                "[8phase] Domain filter: %d/%d learnings passed (threshold=%.2f)",
                len(filtered_learnings), len(raw_learnings),
                _DOMAIN_RELEVANCE_THRESHOLD,
            )
        except Exception as exc:
            logger.warning(
                "[8phase] Embedding failed, skipping domain filter: %s",
                str(exc)[:200],
            )
            filtered_learnings = raw_learnings
            filtered_embeddings = []

        if not filtered_learnings:
            # If filter was too aggressive, keep top 50% by relevance
            raw_learnings.sort(key=lambda x: x["relevance"], reverse=True)
            filtered_learnings = raw_learnings[:max(5, len(raw_learnings) // 2)]
            filtered_embeddings = []

        # Step 3: Cluster by embedding similarity
        clusters = self._cluster_learnings(
            filtered_learnings, filtered_embeddings,
        )

        # Step 4: Decompose query into sub-questions
        sub_questions = self._decompose_query()

        # Step 5: Build comparison matrix
        comparison_matrix = self._build_comparison_matrix(
            filtered_learnings, sub_questions,
        )

        return {
            "learnings": filtered_learnings,
            "clusters": clusters,
            "sub_questions": sub_questions,
            "comparison_matrix": comparison_matrix,
        }

    def _cluster_learnings(
        self,
        learnings: list[dict],
        embeddings: list[list[float]],
    ) -> list[dict]:
        """Cluster learnings by embedding similarity.

        Uses scipy agglomerative clustering with cosine distance.
        Falls back to category-based grouping if embeddings unavailable.
        """
        if len(learnings) <= 1:
            if learnings:
                return [{
                    "theme": learnings[0].get("category", "general"),
                    "learning_indices": [0],
                    "evidence_count": 1,
                }]
            return []

        # Try embedding-based clustering
        if embeddings and len(embeddings) == len(learnings):
            try:
                emb_matrix = np.array(embeddings)
                # Compute pairwise cosine distances
                dists = pdist(emb_matrix, metric="cosine")
                # Replace NaN distances (zero-norm vectors) with 1.0
                dists = np.nan_to_num(dists, nan=1.0)
                linkage_matrix = linkage(dists, method="average")
                labels = fcluster(linkage_matrix, t=0.5, criterion="distance")

                cluster_map: dict[int, list[int]] = {}
                for idx, label in enumerate(labels):
                    cluster_map.setdefault(int(label), []).append(idx)

                clusters = []
                for label in sorted(cluster_map.keys()):
                    indices = cluster_map[label]
                    # Label cluster by most common category
                    cats = [
                        learnings[i].get("category", "general")
                        for i in indices
                    ]
                    theme = max(set(cats), key=cats.count)

                    # Sort: GOLD first, then by relevance desc
                    tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
                    indices.sort(key=lambda i: (
                        tier_order.get(learnings[i].get("tier", "BRONZE"), 3),
                        -learnings[i].get("relevance", 0),
                    ))

                    # Cap per cluster
                    capped = indices[:_LEARNINGS_PER_CLUSTER]
                    clusters.append({
                        "theme": theme,
                        "learning_indices": capped,
                        "evidence_count": len(capped),
                    })

                # Cap total clusters
                clusters.sort(
                    key=lambda c: c["evidence_count"], reverse=True,
                )
                return clusters[:_MAX_CLUSTERS]
            except Exception as exc:
                logger.warning(
                    "[8phase] Clustering failed: %s, using category groups",
                    str(exc)[:200],
                )

        # Fallback: group by category
        cat_map: dict[str, list[int]] = {}
        for i, learning in enumerate(learnings):
            cat = learning.get("category", "general")
            cat_map.setdefault(cat, []).append(i)

        clusters = []
        for cat, indices in cat_map.items():
            # Sort by tier + relevance
            tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
            indices.sort(key=lambda i: (
                tier_order.get(learnings[i].get("tier", "BRONZE"), 3),
                -learnings[i].get("relevance", 0),
            ))
            clusters.append({
                "theme": cat,
                "learning_indices": indices[:_LEARNINGS_PER_CLUSTER],
                "evidence_count": min(len(indices), _LEARNINGS_PER_CLUSTER),
            })

        clusters.sort(key=lambda c: c["evidence_count"], reverse=True)
        return clusters[:_MAX_CLUSTERS]

    def _decompose_query(self) -> list[str]:
        """Decompose query into sub-questions via regex.

        Detects multi-criteria patterns and generates targeted sub-questions.
        """
        query = self._query.lower()
        sub_questions = []

        # Pattern: "effective AND affordable" / "X and Y"
        and_match = re.findall(
            r'(\w+)\s+(?:and|&|as well as|plus)\s+(\w+)',
            query, re.IGNORECASE,
        )
        for w1, w2 in and_match:
            sub_questions.append(f"What is the {w1} of each option?")
            sub_questions.append(f"What is the {w2} of each option?")

        # Pattern: "compare X vs Y" / "X versus Y"
        vs_match = re.findall(
            r'compare\s+(.+?)\s+(?:vs|versus|with|against|to)\s+(.+?)(?:\s|$)',
            query, re.IGNORECASE,
        )
        for entity1, entity2 in vs_match:
            sub_questions.append(
                f"What are the strengths of {entity1.strip()}?"
            )
            sub_questions.append(
                f"What are the strengths of {entity2.strip()}?"
            )

        # Pattern: "most effective" / "best" → ranking question
        if re.search(r'\b(?:most|best|top|leading|optimal)\b', query):
            sub_questions.append(
                "What is the evidence-based ranking of options?"
            )

        # Pattern: cost-related
        if re.search(r'\b(?:cost|afford|cheap|expens|price|budget)\b', query):
            sub_questions.append(
                "What are the cost considerations for each option?"
            )

        # Pattern: effectiveness
        if re.search(
            r'\b(?:effect|efficien|remov|treat|perform|capab)\b', query,
        ):
            sub_questions.append(
                "What is the effectiveness/performance of each option?"
            )

        # Always include a gaps question
        sub_questions.append("What gaps remain in the evidence?")

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for q in sub_questions:
            q_lower = q.lower()
            if q_lower not in seen:
                seen.add(q_lower)
                unique.append(q)

        return unique

    def _build_comparison_matrix(
        self,
        learnings: list[dict],
        sub_questions: list[str],
    ) -> str:
        """Build a markdown comparison matrix for multi-criteria queries.

        Groups learnings by subject entity × criterion.
        Returns empty string if query is single-criterion.
        """
        if len(sub_questions) < 3:
            return ""

        # Extract entity mentions from learnings
        entities: dict[str, list[dict]] = {}
        for learning in learnings:
            fact = learning["fact"].lower()
            # Try to extract the subject (first capitalized noun phrase)
            subject_match = re.search(
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                learning["fact"],
            )
            if subject_match:
                entity = subject_match.group(1)
            else:
                # Use category as fallback
                entity = learning.get("category", "general")
            entities.setdefault(entity, []).append(learning)

        if len(entities) < 2:
            return ""

        # Build markdown table
        # Columns: entity | key findings
        lines = ["| Entity | Key Finding | Evidence |"]
        lines.append("|--------|-------------|----------|")

        for entity, entity_learnings in sorted(
            entities.items(), key=lambda x: -len(x[1]),
        )[:10]:
            # Pick highest-relevance learning
            best = max(entity_learnings, key=lambda l: l["relevance"])
            ev_ids = ", ".join(best["evidence_ids"][:2])
            lines.append(
                f"| {entity} | {best['fact'][:80]} | {ev_ids} |"
            )

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Phase 4: SCAFFOLD — analytical framework generation
    # -------------------------------------------------------------------

    async def _generate_analytical_scaffold(
        self, briefing: dict,
    ) -> str:
        """Generate analytical scaffold using reasoning model (Phase 4).

        Uses reason() (thinking enabled) to produce a structured framework
        that the writer will expand into prose.

        Returns: markdown scaffold (300-500 words)
        """
        # Format briefing as compact input
        cluster_text = []
        learnings = briefing.get("learnings", [])
        for cluster in briefing.get("clusters", []):
            theme = cluster["theme"]
            indices = cluster["learning_indices"]
            facts = []
            for idx in indices:
                if idx < len(learnings):
                    l = learnings[idx]
                    tier_tag = f"[{l['tier']}]" if l.get("tier") else ""
                    ev_ids = ", ".join(l.get("evidence_ids", [])[:2])
                    facts.append(
                        f"  - {tier_tag} {l['fact']} [{ev_ids}]"
                    )
            cluster_text.append(
                f"**{theme}** ({len(indices)} learnings):\n"
                + "\n".join(facts)
            )

        clustered_learnings = "\n\n".join(cluster_text)

        sub_questions = briefing.get("sub_questions", [])
        sq_text = "\n".join(
            f"  {i+1}. {q}" for i, q in enumerate(sub_questions)
        )

        matrix = briefing.get("comparison_matrix", "")
        matrix_section = (
            f"\nCOMPARISON MATRIX:\n{matrix}\n" if matrix else ""
        )

        prompt = (
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"SUB-QUESTIONS:\n{sq_text}\n\n"
            f"EVIDENCE BRIEFING ({len(learnings)} learnings across "
            f"{len(briefing.get('clusters', []))} themes):\n"
            f"{clustered_learnings}\n"
            f"{matrix_section}\n"
            f"PRODUCE AN ANALYTICAL SCAFFOLD:\n"
            f"1. For each sub-question: what does the evidence say? "
            f"(cite [CITE:ev_xxx])\n"
            f"2. Where do sources AGREE? Where do they CONTRADICT?\n"
            f"3. What TRADE-OFFS exist between the criteria?\n"
            f"4. What is the EVIDENCE-BASED ranking? (with specific numbers)\n"
            f"5. What GAPS remain in the evidence?\n"
            f"6. Do NOT rank subtypes of the same technology family as "
            f"separate entries (e.g., nanofiltration IS a high-pressure "
            f"membrane — rank the family, note subtypes within it)\n\n"
            f"This scaffold will be expanded into a full analysis. "
            f"Be specific with numbers and citations. "
            f"Think carefully about cross-source reasoning."
        )

        system = (
            "You are an analytical strategist. Think through the evidence "
            "and produce a research framework. Use [CITE:ev_xxx] citations."
        )

        try:
            response = await asyncio.wait_for(
                self._client.reason(
                    prompt=prompt,
                    system=system,
                    effort="high",
                    max_tokens=4096,
                    timeout=_SCAFFOLD_TIMEOUT,
                ),
                timeout=_SCAFFOLD_TIMEOUT + 15,
            )

            content = response.content.strip()
            if content and len(content) > 50:
                return content

            logger.warning(
                "[8phase] Scaffold too short (%d chars), using fallback",
                len(content),
            )
        except Exception as exc:
            logger.warning(
                "[8phase] Scaffold generation failed: %s: %s, using fallback",
                type(exc).__name__, str(exc)[:200],
            )

        # Fallback: programmatic scaffold from briefing
        return self._build_fallback_scaffold(briefing)

    def _build_fallback_scaffold(self, briefing: dict) -> str:
        """Build a programmatic scaffold from briefing data.

        Used when reason() times out or fails.
        """
        lines = [f"## Analytical Framework: {self._query}\n"]

        # Sub-question answers from top learnings
        for sq in briefing.get("sub_questions", []):
            lines.append(f"### {sq}")
            # Find relevant learnings
            relevant = []
            sq_words = set(sq.lower().split())
            for l in briefing.get("learnings", [])[:30]:
                fact_words = set(l["fact"].lower().split())
                if len(sq_words & fact_words) >= 2:
                    relevant.append(l)
            for r in relevant[:3]:
                ev_ids = ", ".join(
                    f"[CITE:{eid}]" for eid in r.get("evidence_ids", [])[:1]
                )
                lines.append(f"- {r['fact']} {ev_ids}")
            lines.append("")

        # Top findings from each cluster
        lines.append("### Key Evidence Clusters")
        for cluster in briefing.get("clusters", [])[:5]:
            theme = cluster["theme"]
            indices = cluster["learning_indices"][:3]
            learnings = briefing.get("learnings", [])
            facts = []
            for idx in indices:
                if idx < len(learnings):
                    l = learnings[idx]
                    ev = ", ".join(
                        f"[CITE:{eid}]"
                        for eid in l.get("evidence_ids", [])[:1]
                    )
                    facts.append(f"  - {l['fact']} {ev}")
            lines.append(f"**{theme}**:")
            lines.extend(facts)
            lines.append("")

        lines.append("### Gaps")
        lines.append("- Evidence gaps require further investigation")

        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Phase 5: WRITE — scaffold-based interpretation
    # -------------------------------------------------------------------

    async def _write_interpretation(
        self, scaffold: str, briefing: dict,
    ) -> str:
        """Write analytical prose FROM the scaffold (Phase 5).

        The LLM expands the scaffold into full prose. It never sees raw
        evidence statements, preventing verbatim parroting.
        """
        # Build cluster summary for context
        cluster_summary = ", ".join(
            f"{c['theme']} ({c['evidence_count']})"
            for c in briefing.get("clusters", [])[:10]
        )

        prompt = (
            f"You are a senior research analyst. Expand this analytical "
            f"scaffold into publication-quality prose.\n\n"
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"ANALYTICAL SCAFFOLD:\n{scaffold}\n\n"
            f"EVIDENCE THEMES: {cluster_summary}\n\n"
            f"RULES:\n"
            f"1. EXPAND the scaffold into full analytical paragraphs "
            f"(800-1500 words)\n"
            f"2. Preserve ALL citations [CITE:ev_xxx] from the scaffold\n"
            f"3. For EVERY numerical claim, include the citation\n"
            f"4. INTEGRATE criteria — discuss effectiveness AND cost in "
            f"the SAME paragraph per technology\n"
            f"5. Write CROSS-SOURCE insights "
            f"('Comparing X and Y reveals...')\n"
            f"6. Do NOT add claims not in the scaffold (no hallucination)\n"
            f"7. Include a clear ranking with evidence-backed justification\n"
            f"8. End with data gaps and limitations\n"
            f"9. ONLY cite evidence IDs starting with 'ev_'. "
            f"NEVER cite tool names\n"
            f"10. Do NOT mention 'scaffold' or 'framework' in the output\n"
        )

        system = (
            "Expand the scaffold into analytical prose. Every claim must "
            "have a [CITE:ev_xxx] citation from the scaffold. "
            "Do not invent new claims. Be concise and analytical."
        )

        interpret_timeout = int(
            os.getenv("PG_REACT_INTERPRET_TIMEOUT", "180"),
        )
        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=8192,
                    temperature=0.3,
                    timeout=interpret_timeout,
                ),
                timeout=interpret_timeout + 30,
            )

            content = response.content.strip()
            if not content or len(content) < 100:
                logger.warning(
                    "[8phase] Write produced too little: %d chars",
                    len(content),
                )
                return ""

            # Remove phantom citations
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', content)
            phantom_ids = [
                eid for eid in all_cited
                if eid not in self._evidence_store
            ]
            for pid in set(phantom_ids):
                content = content.replace(f"[CITE:{pid}]", "")

            valid_ids = [
                eid for eid in all_cited
                if eid in self._evidence_store
            ]

            # Add as notebook step
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning="8-phase scaffold-based interpretation",
                tool_name="interpret_results",
                result=ToolResult(
                    success=True,
                    tool_name="interpret_results",
                    markdown=content,
                    source_evidence_ids=list(set(valid_ids)),
                    insights=[
                        "Scaffold-based analysis with integrated criteria",
                    ],
                ),
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)

            logger.info(
                "[8phase] Write complete: %d chars, %d citations "
                "(%d valid, %d phantom)",
                len(content), len(all_cited), len(valid_ids),
                len(phantom_ids),
            )

            return content

        except Exception as exc:
            logger.warning(
                "[8phase] Write failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )
            return ""

    # -------------------------------------------------------------------
    # Phase 6: CRITIQUE — structured quality check
    # -------------------------------------------------------------------

    async def _critique_interpretation(
        self, interpretation: str, briefing: dict,
    ) -> dict | None:
        """Critique interpretation for analytical quality (Phase 6).

        Uses reason() to evaluate against 5 substance dimensions.
        Returns structured critique dict with pass/fail per dimension.
        """
        sub_questions = briefing.get("sub_questions", [])
        sq_text = "\n".join(f"  - {q}" for q in sub_questions)

        prompt = (
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"SUB-QUESTIONS THE ANALYSIS SHOULD ADDRESS:\n{sq_text}\n\n"
            f"ANALYSIS TO CRITIQUE:\n{interpretation}\n\n"
            f"Evaluate this analysis on 5 dimensions. For each, state "
            f"whether it PASSES or FAILS and list specific issues:\n\n"
            f"1. sub_question_coverage: Does it address ALL sub-questions?\n"
            f"2. cross_source_synthesis: Are there sentences combining "
            f"2+ sources? (look for multiple [CITE:] in one sentence)\n"
            f"3. integration: For multi-criteria queries, are criteria "
            f"discussed TOGETHER (not in separate sections)?\n"
            f"4. evidence_grounding: Does every numerical claim have a "
            f"[CITE:ev_xxx]?\n"
            f"5. analytical_depth: Are there trade-off identifications, "
            f"conditional recommendations, gap analyses?\n\n"
            f"Then decide: needs_rewrite = true if <=3 dimensions pass.\n"
            f"If rewrite needed, provide specific fix instructions."
        )

        system = (
            "You are a research quality auditor. Be strict but fair. "
            "Return valid JSON matching the InterpretationCritique schema."
        )

        try:
            response = await asyncio.wait_for(
                self._client.reason(
                    prompt=prompt,
                    system=system,
                    schema=InterpretationCritique,
                    effort="medium",
                    max_tokens=2048,
                    timeout=_CRITIQUE_TIMEOUT,
                ),
                timeout=_CRITIQUE_TIMEOUT + 15,
            )

            # Parse the response
            content = response.content.strip()
            if hasattr(response, "_parsed") and response._parsed:
                critique_obj = response._parsed
            else:
                # Try to parse JSON from content
                try:
                    critique_obj = InterpretationCritique.model_validate_json(
                        content,
                    )
                except Exception:
                    # Try extracting JSON from content
                    json_match = re.search(
                        r'\{[\s\S]*\}', content,
                    )
                    if json_match:
                        critique_obj = InterpretationCritique.model_validate_json(
                            json_match.group(),
                        )
                    else:
                        logger.warning(
                            "[8phase] Could not parse critique response",
                        )
                        return self._programmatic_critique(
                            interpretation, briefing,
                        )

            return critique_obj.model_dump()

        except Exception as exc:
            logger.warning(
                "[8phase] Critique failed: %s: %s, using programmatic",
                type(exc).__name__, str(exc)[:200],
            )
            return self._programmatic_critique(interpretation, briefing)

    def _programmatic_critique(
        self, interpretation: str, briefing: dict,
    ) -> dict:
        """Programmatic fallback critique when LLM critique fails.

        Checks the 5 dimensions using regex and counting.
        """
        dims = []

        # 1. Sub-question coverage
        sub_questions = briefing.get("sub_questions", [])
        covered = 0
        for sq in sub_questions:
            sq_words = set(
                w for w in sq.lower().split() if len(w) > 3
            )
            interp_lower = interpretation.lower()
            overlap = sum(1 for w in sq_words if w in interp_lower)
            if overlap >= 2:
                covered += 1
        coverage_ratio = covered / max(len(sub_questions), 1)
        dims.append({
            "dimension": "sub_question_coverage",
            "passed": coverage_ratio >= 0.6,
            "issues": (
                [f"Only {covered}/{len(sub_questions)} sub-questions addressed"]
                if coverage_ratio < 0.6 else []
            ),
        })

        # 2. Cross-source synthesis
        cross_count = 0
        for sentence in re.split(r'[.!?]\s+', interpretation):
            cites = set(re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', sentence))
            if len(cites) >= 2:
                cross_count += 1
        dims.append({
            "dimension": "cross_source_synthesis",
            "passed": cross_count >= 3,
            "issues": (
                [f"Only {cross_count} cross-source sentences (need >=3)"]
                if cross_count < 3 else []
            ),
        })

        # 3. Integration (multi-criteria in same paragraph)
        paragraphs = [
            p.strip() for p in interpretation.split("\n\n") if p.strip()
        ]
        criteria_words = {
            "cost", "price", "expensive", "affordable",
            "effective", "efficiency", "removal", "performance",
        }
        integrated_paragraphs = 0
        for para in paragraphs:
            para_lower = para.lower()
            criteria_found = sum(
                1 for w in criteria_words if w in para_lower
            )
            if criteria_found >= 3:
                integrated_paragraphs += 1
        integration_ratio = integrated_paragraphs / max(len(paragraphs), 1)
        dims.append({
            "dimension": "integration",
            "passed": integration_ratio >= 0.2 or len(sub_questions) < 3,
            "issues": (
                [f"Only {integrated_paragraphs}/{len(paragraphs)} paragraphs "
                 f"integrate multiple criteria"]
                if integration_ratio < 0.2 and len(sub_questions) >= 3 else []
            ),
        })

        # 4. Evidence grounding
        # Count numerical claims without citations
        num_claims = re.findall(
            r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$)',
            interpretation,
        )
        cited_nums = re.findall(
            r'\d+\.?\d*\s*(?:%|mg|ng|ppt|ppb|ppm|kWh|\$)[^.!?\n]*'
            r'\[CITE:ev_[a-f0-9]+\]',
            interpretation,
        )
        grounding_ratio = len(cited_nums) / max(len(num_claims), 1)
        dims.append({
            "dimension": "evidence_grounding",
            "passed": grounding_ratio >= 0.6,
            "issues": (
                [f"Only {len(cited_nums)}/{len(num_claims)} numerical "
                 f"claims have citations"]
                if grounding_ratio < 0.6 else []
            ),
        })

        # 5. Analytical depth
        depth_markers = [
            r'(?:however|although|while|whereas|despite)',
            r'(?:trade-?off|limitation|disadvantage|drawback)',
            r'(?:recommend|ranking|prefer|optimal|best suited)',
            r'(?:gap|limitation|missing|insufficient|unclear)',
        ]
        depth_count = sum(
            len(re.findall(p, interpretation, re.IGNORECASE))
            for p in depth_markers
        )
        dims.append({
            "dimension": "analytical_depth",
            "passed": depth_count >= 3,
            "issues": (
                [f"Only {depth_count} depth markers found (need >=3)"]
                if depth_count < 3 else []
            ),
        })

        passed_count = sum(1 for d in dims if d["passed"])
        needs_rewrite = passed_count <= 3

        all_issues = []
        for d in dims:
            all_issues.extend(d["issues"])

        return {
            "dimensions": dims,
            "needs_rewrite": needs_rewrite,
            "rewrite_instructions": (
                "Fix these issues: " + "; ".join(all_issues)
                if needs_rewrite else ""
            ),
        }

    # -------------------------------------------------------------------
    # Phase 7: REWRITE — fix critique issues
    # -------------------------------------------------------------------

    async def _rewrite_interpretation(
        self, interpretation: str, critique: dict, briefing: dict,
    ) -> str | None:
        """Rewrite interpretation to fix critique issues (Phase 7).

        Only called when critique.needs_rewrite == True.
        Returns rewritten text, or None if rewrite fails/is too short.
        """
        all_issues = []
        for dim in critique.get("dimensions", []):
            if not dim.get("passed", True):
                all_issues.extend(dim.get("issues", []))

        instructions = critique.get("rewrite_instructions", "")
        issue_list = "\n".join(f"- {issue}" for issue in all_issues)

        prompt = (
            f"ORIGINAL ANALYSIS:\n{interpretation}\n\n"
            f"CRITIQUE FINDINGS:\n{instructions}\n\n"
            f"REWRITE the analysis to fix these specific issues:\n"
            f"{issue_list}\n\n"
            f"RULES:\n"
            f"1. Preserve all existing CORRECT claims and citations\n"
            f"2. Fix ONLY the issues identified above\n"
            f"3. Do NOT shorten the analysis\n"
            f"4. Maintain [CITE:ev_xxx] format for all citations\n"
            f"5. Do NOT add claims without evidence\n"
            f"6. Target 800-1500 words\n"
        )

        system = (
            "Rewrite the analysis to fix the identified issues. "
            "Preserve correct claims and citations. Do not shorten."
        )

        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=8192,
                    temperature=0.3,
                    timeout=_SCAFFOLD_TIMEOUT,
                ),
                timeout=_SCAFFOLD_TIMEOUT + 30,
            )

            rewritten = response.content.strip()

            # Safety: accept only if >= 70% of original length
            if len(rewritten) < 0.7 * len(interpretation):
                logger.warning(
                    "[8phase] Rewrite too short: %d vs %d (%.0f%%), keeping original",
                    len(rewritten), len(interpretation),
                    len(rewritten) / max(len(interpretation), 1) * 100,
                )
                return None

            # Remove phantom citations
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', rewritten)
            for pid in set(all_cited):
                if pid not in self._evidence_store:
                    rewritten = rewritten.replace(f"[CITE:{pid}]", "")

            # Update the interpretation step in notebook
            for step in self._notebook.steps:
                if (
                    step.tool_name == "interpret_results"
                    and step.result.success
                ):
                    valid_ids = [
                        eid for eid in re.findall(
                            r'\[CITE:(ev_[a-f0-9]+)\]', rewritten,
                        )
                        if eid in self._evidence_store
                    ]
                    step.result = ToolResult(
                        success=True,
                        tool_name="interpret_results",
                        markdown=rewritten,
                        source_evidence_ids=list(set(valid_ids)),
                        insights=[
                            "Scaffold-based analysis (rewritten after critique)",
                        ],
                    )
                    break

            return rewritten

        except Exception as exc:
            logger.warning(
                "[8phase] Rewrite failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )
            return None

    async def _plan_analysis(self) -> AnalysisPlan:
        """Plan analysis in ONE LLM call (ReWOO pattern).

        Returns an ordered list of tools to execute. Falls back to
        a deterministic plan [extract, stats, sql] on failure.
        """
        all_tools = self._registry.available_tools(has_data=True)
        evidence_count = len(self._evidence_ids)
        has_structured = any(
            self._evidence_store.get(eid, {}).get("structured_data")
            for eid in self._evidence_ids[:50]
        )

        prompt = (
            f"Plan analysis for: {self._query[:120]}\n"
            f"Evidence: {evidence_count} | Structured: {has_structured}\n"
            f"Tools: {', '.join(all_tools)}\n\n"
            f"Rules:\n"
            f"1. Always start with extract_numeric_data\n"
            f"2. Then statistical_summary or query_evidence_sql\n"
            f"3. Then comparison_table or meta_analysis\n"
            f"4. Max {_MAX_ITERATIONS} steps\n\n"
            f"Return ordered tool steps."
        )

        plan = await asyncio.wait_for(
            self._client.generate_structured(
                prompt=prompt,
                schema=AnalysisPlan,
                system="Plan the analysis. Return an ordered list of tool steps.",
                max_tokens=512,
                timeout=60,
            ),
            timeout=75,
        )

        # Filter to known tools only, cap at max iterations
        valid_steps = [
            step for step in plan.steps
            if step.tool_name in _KNOWN_TOOLS and step.tool_name != "stop"
        ]
        plan.steps = valid_steps[:_MAX_ITERATIONS]

        return plan

    # -------------------------------------------------------------------
    # Post-processing: cleanup LLM output defects
    # -------------------------------------------------------------------

    def _post_process_interpretation(self, text: str) -> str:
        """Clean up common LLM output defects.

        1. Remove duplicate sentences (DeRep pattern: cosine > 0.95)
        2. Strip meta-commentary about prompt rules/constraints
        3. Flag fabricated numbers not in any cited evidence
        """
        lines = text.split("\n")
        cleaned_lines = []

        # --- Fix 1: Remove duplicate sentences within each paragraph ---
        seen_sentences: set[str] = set()
        for line in lines:
            if not line.strip():
                cleaned_lines.append(line)
                continue

            sentences = re.split(r'(?<=[.!?])\s+', line)
            unique_sentences = []
            for sent in sentences:
                # Normalize for comparison: lowercase, strip citations
                norm = re.sub(
                    r'\[CITE:ev_[a-f0-9]+\]', '', sent,
                ).strip().lower()
                if len(norm) < 10:
                    unique_sentences.append(sent)
                    continue
                if norm not in seen_sentences:
                    seen_sentences.add(norm)
                    unique_sentences.append(sent)
                else:
                    logger.debug(
                        "[post-process] Removed duplicate: %s",
                        sent[:60],
                    )

            if unique_sentences:
                cleaned_lines.append(" ".join(unique_sentences))

        text = "\n".join(cleaned_lines)

        # --- Fix 2: Strip meta-commentary about prompt rules ---
        meta_patterns = [
            r'[^.]*(?:to comply with|technology family constraints|'
            r'do not rank subtypes|scaffold rule|as instructed|'
            r'per the instructions|following the rules|'
            r'as specified in the prompt|per the scaffold)[^.]*\.',
        ]
        for pattern in meta_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # --- Fix 3: Fabricated number patterns ---
        fabricated_patterns = [
            (
                r'~?\s*100\s*%\s*improvement\s*(?:metric|rate|measure)',
                'near-complete improvement',
            ),
            (
                r'a\s+\d+%\s+improvement\s+metric',
                'a significant improvement',
            ),
        ]
        for pattern, replacement in fabricated_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # --- Fix 4: Number grounding check (FACTScore pattern) ---
        # For each [CITE:ev_xxx] with a nearby number, verify the number
        # exists as a standalone value in the cited evidence. If NOT,
        # remove the ungrounded numerical claim (safer than guessing
        # the correction — covers truncation, transposition, rounding,
        # and wrong-number-from-same-source errors).
        cite_num_pattern = re.compile(
            r'(\d+\.?\d*)\s'        # number followed by space
            r'(.{0,30}?)\s*'        # any text up to 30 chars (lazy)
            r'\[CITE:(ev_[a-f0-9]+)\]',
        )
        # Collect ungrounded numbers (don't modify text during iteration)
        ungrounded = []
        for match in cite_num_pattern.finditer(text):
            num_str = match.group(1)
            eid = match.group(3)
            ev = self._evidence_store.get(eid, {})
            ev_stmt = ev.get("statement", "")
            if not ev_stmt:
                continue

            # Skip small numbers likely to be ordinals/list items
            try:
                if float(num_str) < 2:
                    continue
            except ValueError:
                continue

            # Check if the number exists as a standalone value
            num_in_evidence = bool(re.search(
                r'(?<!\d)' + re.escape(num_str) + r'(?!\d)',
                ev_stmt,
            ))
            if not num_in_evidence:
                ungrounded.append({
                    "num": num_str,
                    "eid": eid,
                    "span": match.group(0),
                    "ev_numbers": re.findall(r'\d+\.?\d*', ev_stmt),
                })

        # Fix ungrounded numbers
        for item in ungrounded:
            num_str = item["num"]
            ev_numbers = item["ev_numbers"]

            # Strategy 1: If output number is a prefix of an evidence
            # number, it's truncation — fix it (7 → 70)
            fixed = False
            for ev_num in ev_numbers:
                if (
                    ev_num.startswith(num_str)
                    and len(ev_num) > len(num_str)
                    and len(ev_num) <= len(num_str) + 2
                ):
                    old_span = item["span"]
                    fixed_span = old_span.replace(num_str, ev_num, 1)
                    text = text.replace(old_span, fixed_span, 1)
                    logger.info(
                        "[post-process] Fixed truncated number: "
                        "%s -> %s (from %s)",
                        num_str, ev_num, item["eid"][:16],
                    )
                    fixed = True
                    break

            if not fixed:
                # Strategy 2: Citation correction — if the number exists
                # in a DIFFERENT evidence piece, fix the citation
                # (covers wrong-source attribution like 250µm cited to
                # the 125µm source instead of the 250µm source).
                correct_eid = None
                for eid, ev in self._evidence_store.items():
                    ev_stmt = ev.get("statement", "")
                    if re.search(
                        r'(?<!\d)' + re.escape(num_str) + r'(?!\d)',
                        ev_stmt,
                    ):
                        correct_eid = eid
                        break

                if correct_eid and correct_eid != item["eid"]:
                    old_cite = f"[CITE:{item['eid']}]"
                    new_cite = f"[CITE:{correct_eid}]"
                    old_span = item["span"]
                    if old_cite in old_span:
                        fixed_span = old_span.replace(
                            old_cite, new_cite, 1,
                        )
                        text = text.replace(old_span, fixed_span, 1)
                        logger.info(
                            "[post-process] Fixed citation: %s -> %s "
                            "for number %s",
                            item["eid"][:16], correct_eid[:16], num_str,
                        )
                    else:
                        logger.warning(
                            "[post-process] Ungrounded number: %s not "
                            "in %s (correct source: %s)",
                            num_str, item["eid"][:16],
                            correct_eid[:16],
                        )
                else:
                    # Strategy 3: Flag — number might be derived
                    logger.warning(
                        "[post-process] Ungrounded number: %s not in "
                        "%s (evidence has: %s)",
                        num_str, item["eid"][:16],
                        ", ".join(ev_numbers[:5]),
                    )

        # --- Fix 5: Remove incomplete sentences (token truncation) ---
        # Qwen sometimes hits max_tokens mid-word, producing
        # "This inconsistency distingu" without terminal punctuation.
        sentences = text.split("\n")
        cleaned = []
        for line in sentences:
            stripped = line.rstrip()
            if not stripped:
                cleaned.append(line)
                continue
            # If line ends mid-word (no punctuation, no header, no list)
            if (
                stripped
                and not stripped[-1] in '.!?:"|)'
                and not stripped.startswith('#')
                and not stripped.startswith('|')
                and not stripped.startswith('-')
                and not stripped.startswith('*')
                and len(stripped) > 50
            ):
                # Find last complete sentence
                last_period = max(
                    stripped.rfind('. '),
                    stripped.rfind('? '),
                    stripped.rfind('! '),
                    stripped.rfind('.]'),
                )
                if last_period > 0:
                    stripped = stripped[:last_period + 1]
                    logger.info(
                        "[post-process] Trimmed incomplete sentence at "
                        "end of line",
                    )
            cleaned.append(stripped)
        text = "\n".join(cleaned)

        # Clean up any double spaces or empty lines from removals
        text = re.sub(r'  +', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)

        return text.strip()

    def _verify_claims(self, briefing: dict | None = None) -> dict:
        """Programmatic post-interpretation claim verification.

        Enhanced for 8-phase pipeline with optional briefing for:
        - Evidence coverage check (what % of clusters cited)
        - Restatement detection (Jaccard overlap = parroting)
        - Sub-question coverage

        Appends a verification step to the notebook with results.
        Returns a summary dict.
        """
        # Find the interpretation step
        interp_step = None
        for step in self._notebook.steps:
            if step.tool_name == "interpret_results" and step.result.success:
                interp_step = step
                break

        if not interp_step:
            return {}

        content = interp_step.result.markdown

        # Category mismatch check (reuses existing method)
        category_mismatches = self._verify_interpretation_claims(content)

        # Numerical presence check
        all_cites = re.findall(r'\[CITE:(ev_[a-f0-9]+)\]', content)
        pattern = re.compile(
            r'([^.!?\n]{10,120})\[CITE:(ev_[a-f0-9]+)\]'
        )

        total_checked = 0
        verified = 0
        for match in pattern.finditer(content):
            claim_text = match.group(1).strip()
            ev_id = match.group(2)

            if ev_id not in self._evidence_store:
                continue

            nums_in_claim = re.findall(r'(\d+\.?\d*)', claim_text)
            if not nums_in_claim:
                continue

            total_checked += 1
            ev_stmt = self._evidence_store[ev_id].get(
                "statement", "",
            ).lower()
            key_num = nums_in_claim[-1]  # Closest to citation

            if key_num in ev_stmt:
                verified += 1

        report = {
            "total_citations": len(all_cites),
            "unique_citations": len(set(all_cites)),
            "total_claims_checked": total_checked,
            "verified": verified,
            "mismatches": len(category_mismatches),
            "mismatch_details": category_mismatches[:10],
        }

        # Enhanced metrics when briefing is available
        if briefing:
            # Evidence coverage: what % of clusters have citations
            cited_eids = set(all_cites)
            clusters = briefing.get("clusters", [])
            learnings = briefing.get("learnings", [])
            clusters_cited = 0
            for cluster in clusters:
                cluster_eids = set()
                for idx in cluster.get("learning_indices", []):
                    if idx < len(learnings):
                        cluster_eids.update(
                            learnings[idx].get("evidence_ids", []),
                        )
                if cluster_eids & cited_eids:
                    clusters_cited += 1
            report["cluster_coverage"] = round(
                clusters_cited / max(len(clusters), 1), 3,
            )

            # Category coverage
            all_categories = set(
                l.get("category", "general") for l in learnings
            )
            cited_categories = set()
            for eid in cited_eids:
                ev = self._evidence_store.get(eid, {})
                cited_categories.add(ev.get("fact_category", "general"))
            report["category_coverage"] = round(
                len(cited_categories & all_categories)
                / max(len(all_categories), 1),
                3,
            )

            # Restatement detection (parroting)
            sentences = re.split(r'[.!?]\s+', content)
            parroted = 0
            for sent in sentences:
                sent_words = set(
                    w.lower() for w in re.findall(r'[a-z]{4,}', sent.lower())
                )
                if not sent_words:
                    continue
                for eid in self._evidence_ids[:200]:
                    ev = self._evidence_store.get(eid, {})
                    ev_stmt = ev.get("statement", "")
                    ev_words = set(
                        w.lower()
                        for w in re.findall(r'[a-z]{4,}', ev_stmt.lower())
                    )
                    if not ev_words:
                        continue
                    jaccard = (
                        len(sent_words & ev_words)
                        / max(len(sent_words | ev_words), 1)
                    )
                    if jaccard > 0.5:
                        parroted += 1
                        break
            report["parroting_ratio"] = round(
                parroted / max(len(sentences), 1), 3,
            )

            # Sub-question coverage
            sub_questions = briefing.get("sub_questions", [])
            sq_covered = 0
            for sq in sub_questions:
                sq_words = set(
                    w for w in sq.lower().split() if len(w) > 3
                )
                interp_lower = content.lower()
                overlap = sum(1 for w in sq_words if w in interp_lower)
                if overlap >= 2:
                    sq_covered += 1
            report["sub_question_coverage"] = round(
                sq_covered / max(len(sub_questions), 1), 3,
            )

        # Build verification report markdown
        report_lines = [
            "**Claim Verification Report:**",
            f"- Citations: {len(all_cites)} total, "
            f"{len(set(all_cites))} unique",
            f"- Numerical claims checked: {total_checked}",
            f"- Numbers verified in source: {verified}/{total_checked}",
            f"- Category mismatches: {len(category_mismatches)}",
        ]
        if briefing:
            report_lines.extend([
                f"- Cluster coverage: "
                f"{report.get('cluster_coverage', 0):.0%}",
                f"- Parroting ratio: "
                f"{report.get('parroting_ratio', 0):.0%}",
                f"- Sub-question coverage: "
                f"{report.get('sub_question_coverage', 0):.0%}",
            ])
        if category_mismatches:
            report_lines.append("\n**Category Mismatches:**")
            for mm in category_mismatches[:5]:
                report_lines.append(
                    f"- {mm['ev_id']}: claim \"{mm['claim'][:50]}\" "
                    f"({mm['claim_category']}) vs evidence "
                    f"\"{mm['ev_statement'][:50]}\" ({mm['ev_category']})"
                )

        verify_step = AnalysisStep(
            step_number=self._notebook.step_count + 1,
            reasoning="Programmatic claim-evidence verification",
            tool_name="verify_claims",
            result=ToolResult(
                success=True,
                tool_name="verify_claims",
                markdown="\n".join(report_lines),
                source_evidence_ids=list(set(all_cites))[:20],
                insights=[
                    f"Verified {verified}/{total_checked} numerical "
                    f"claims against source evidence",
                ],
                statistics=report,
            ),
            elapsed_seconds=0.0,
        )
        self._notebook.add_step(verify_step)

        return report

    # -------------------------------------------------------------------
    # ReAct loop helpers (legacy mode)
    # -------------------------------------------------------------------

    async def _decide(self, iteration: int) -> ReactDecision:
        """Ask the LLM which tool to use next."""
        available = self._registry.available_tools(self._notebook.has_data)
        tool_descriptions = self._registry.get_tool_descriptions(
            self._notebook.has_data,
        )
        notebook_summary = self._notebook.summary_for_llm()

        evidence_count = len(self._evidence_ids)
        has_structured = any(
            self._evidence_store.get(eid, {}).get("structured_data")
            for eid in self._evidence_ids[:50]
        )

        # Compact prompt — keep under 800 tokens to avoid Qwen timeouts
        # (Qwen 3.5 Plus latency spikes on 2nd+ structured calls)
        tools_short = ", ".join(available)
        done_tools = ", ".join(
            s.tool_name for s in self._notebook.steps if s.result.success
        ) or "none"
        dp_count = len(self._notebook.data_points)

        prompt = (
            f"Topic: {self._query[:120]}\n"
            f"Evidence: {evidence_count} pieces | "
            f"Data points: {dp_count} | "
            f"Structured data: {has_structured}\n"
            f"Done: {done_tools}\n"
            f"Available: {tools_short}\n\n"
            f"Rules:\n"
            f"1. extract_numeric_data FIRST if data points = 0\n"
            f"2. Don't repeat succeeded tools\n"
            f"3. Need: stats + comparison/meta before stop\n"
            f"4. Max {_MAX_ITERATIONS} steps\n\n"
            f"Pick one tool or 'stop'. Give reasoning."
        )

        system = (
            "Pick the next analysis tool. Respond with reasoning and action."
        )

        decision = await asyncio.wait_for(
            self._client.generate_structured(
                prompt=prompt,
                schema=ReactDecision,
                system=system,
                max_tokens=512,
                timeout=60,
            ),
            timeout=75,
        )

        # Validate the action is a known tool or "stop"
        if decision.action != "stop" and decision.action not in available:
            logger.warning(
                "[react] LLM picked unavailable tool '%s', mapping to fallback",
                decision.action,
            )
            if (
                not self._notebook.has_data
                and "extract_numeric_data" in available
            ):
                decision.action = "extract_numeric_data"
                decision.reasoning = (
                    f"Falling back to extract_numeric_data "
                    f"('{decision.action}' unavailable)"
                )
            elif available:
                decision.action = available[0]
                decision.reasoning = f"Falling back to {available[0]}"
            else:
                decision.action = "stop"

        return decision

    async def _execute_tool(
        self, iteration: int, decision: ReactDecision,
    ) -> AnalysisStep:
        """Execute a tool and return an AnalysisStep."""
        tool_def = self._registry.get_tool(decision.action)
        step_start = time.monotonic()

        if not tool_def or not tool_def.execute:
            return AnalysisStep(
                step_number=iteration,
                reasoning=decision.reasoning,
                tool_name=decision.action,
                result=ToolResult(
                    success=False,
                    tool_name=decision.action,
                    markdown=f"Unknown tool: {decision.action}",
                    error=f"Tool '{decision.action}' not found in registry",
                ),
                elapsed_seconds=0.0,
            )

        try:
            result = await asyncio.wait_for(
                tool_def.execute(
                    evidence_store=self._evidence_store,
                    data_points=self._notebook.data_points,
                    client=self._client,
                    **decision.action_input,
                ),
                timeout=_TOOL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            result = ToolResult(
                success=False,
                tool_name=decision.action,
                markdown=f"Tool timed out after {_TOOL_TIMEOUT}s",
                error=f"Timeout after {_TOOL_TIMEOUT}s",
            )
        except Exception as exc:
            result = ToolResult(
                success=False,
                tool_name=decision.action,
                markdown=f"Tool execution error: {str(exc)[:200]}",
                error=str(exc)[:500],
            )

        elapsed = time.monotonic() - step_start

        return AnalysisStep(
            step_number=iteration,
            reasoning=decision.reasoning,
            tool_name=decision.action,
            result=result,
            elapsed_seconds=round(elapsed, 3),
        )

    async def _run_fallback(self) -> None:
        """Deterministic minimal analysis without LLM decisions."""
        logger.info("[react] Running deterministic fallback analysis")

        # Step 1: Extract data
        await self._run_fallback_tool(
            "extract_numeric_data",
            "Fallback: extracting numeric data from evidence",
        )

        # Step 2: Statistical summary (if data available)
        if self._notebook.has_data:
            await self._run_fallback_tool(
                "statistical_summary",
                "Fallback: computing statistical summary",
            )

        # Step 3: SQL query (always works)
        await self._run_fallback_tool(
            "query_evidence_sql",
            "Fallback: SQL tier distribution",
        )

    async def _run_fallback_tool(
        self, tool_name: str, reasoning: str,
    ) -> None:
        """Execute a single tool as part of fallback analysis."""
        tool = self._registry.get_tool(tool_name)
        if not tool or not tool.execute:
            return
        try:
            result = await asyncio.wait_for(
                tool.execute(
                    evidence_store=self._evidence_store,
                    data_points=self._notebook.data_points,
                    client=self._client,
                ),
                timeout=_TOOL_TIMEOUT,
            )
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning=reasoning,
                tool_name=tool_name,
                result=result,
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)
        except Exception as exc:
            logger.warning(
                "[react] Fallback %s failed: %s", tool_name, str(exc)[:200],
            )

    async def _interpret_results(self) -> None:
        """Use Qwen's reasoning to interpret raw tool outputs into insights.

        This is the critical step that separates "regex + scipy" from
        "analyst with reasoning." The LLM reads the raw extraction +
        statistics and produces:
        - Technology-level comparison (not URL-level)
        - Key findings with specific numbers and [CITE:ev_xxx] tokens
        - Cost-effectiveness ranking
        - Insights the section writer can directly use

        Uses generate() (prose mode) — NOT generate_structured() — because
        we want rich markdown with inline citations, not constrained JSON.
        """
        # Build evidence ID → short label mapping for the prompt
        ev_labels = {}
        for step in self._notebook.steps:
            if not step.result.success:
                continue
            for dp in step.result.data_points_produced:
                eid = dp.get("evidence_id", "")
                if eid and eid not in ev_labels:
                    # Build a useful label from the evidence
                    ev = self._evidence_store.get(eid, {})
                    title = ev.get("source_title", "")[:60]
                    ev_labels[eid] = title or eid[:16]

        # Collect data points with FULL evidence context (not truncated labels)
        # This prevents Qwen from misinterpreting "40% less expensive" as
        # "40% removal" — the full statement provides the semantic context.
        dp_lines = []
        seen_ev = set()
        for dp in self._notebook.data_points[:60]:
            eid = dp.get("evidence_id", "")
            value = dp.get("value", "")
            unit = dp.get("unit", "")

            # Pre-format large numbers for readability
            try:
                num = float(str(value).replace(",", ""))
                if abs(num) >= 1e9:
                    value = f"~${num / 1e9:.2f} billion" if unit == "USD" else f"~{num / 1e9:.2f}B"
                elif abs(num) >= 1e6:
                    value = f"~${num / 1e6:.1f} million" if unit == "USD" else f"~{num / 1e6:.1f}M"
            except (ValueError, TypeError):
                pass

            # Include the FULL evidence statement (not truncated label)
            # so Qwen can read "40% less expensive" not just "GAC was: 40%"
            ev = self._evidence_store.get(eid, {})
            stmt = ev.get("statement", "")[:150]

            if eid and eid not in seen_ev:
                dp_lines.append(
                    f"- {value} {unit} — \"{stmt}\" [{eid}]"
                )
                seen_ev.add(eid)
            elif eid:
                # Same evidence, different data point — just note the value
                dp_lines.append(f"  also: {value} {unit} [{eid}]")

        raw_data = "\n".join(dp_lines) if dp_lines else "No structured data."

        # Collect raw stats
        stats_text = ""
        for step in self._notebook.steps:
            if step.result.success and step.result.statistics:
                stats_text += (
                    f"\n{step.tool_name}: "
                    f"{json.dumps(step.result.statistics, default=str)[:300]}"
                )

        prompt = (
            f"You are a research analyst. Interpret the following raw data "
            f"to answer the research question.\n\n"
            f"RESEARCH QUESTION: {self._query}\n\n"
            f"RAW EXTRACTED DATA ({len(self._notebook.data_points)} points):\n"
            f"{raw_data}\n\n"
            f"STATISTICS:\n{stats_text}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Group findings by TECHNOLOGY or METHOD (e.g., 'Reverse "
            f"Osmosis', 'Granular Activated Carbon', 'Ion Exchange'), NOT "
            f"by source URL\n"
            f"2. For each technology, state: effectiveness (with numbers), "
            f"cost (if available), limitations\n"
            f"3. Rank technologies by effectiveness AND affordability\n"
            f"4. For EVERY claim with a number, cite the source using "
            f"[CITE:ev_xxx] format with the evidence ID from the data\n"
            f"5. Identify what the data does NOT tell us (gaps)\n"
            f"6. Be specific — never say 'several studies show' without "
            f"numbers and citations\n"
            f"7. READ THE QUOTED STATEMENT carefully before interpreting "
            f"each number. '40% less expensive' is a COST metric, NOT a "
            f"removal rate. '7.2% CAGR' is market growth, NOT removal\n"
            f"8. Do NOT create false ranges from separate sources. If one "
            f"study reports 2 kWh and another reports 313 kWh, those are "
            f"TWO separate findings, not a '2-313 kWh range'\n"
            f"9. Format large numbers readably: $2.09 billion NOT "
            f"$2,089,500,000. Use B/M suffixes for billions/millions\n"
            f"10. ONLY cite evidence IDs starting with 'ev_'. NEVER cite "
            f"tool names\n\n"
            f"Produce 300-600 words of curated analysis with inline "
            f"citations. NO raw data dumps, NO tables — just analytical "
            f"prose with specific numbers."
        )

        system = (
            "You are a senior research analyst producing publication-quality "
            "insights. Every claim must have a specific number and a "
            "[CITE:ev_xxx] citation. Be concise, analytical, and critical."
        )

        interpret_timeout = int(os.getenv("PG_REACT_INTERPRET_TIMEOUT", "180"))
        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=4096,
                    temperature=0.3,
                    timeout=interpret_timeout,
                ),
                timeout=interpret_timeout + 30,
            )

            content = response.content.strip()
            if not content or len(content) < 100:
                logger.warning(
                    "[react] Interpretation produced too little content: "
                    "%d chars", len(content),
                )
                return

            # Validate: extract ALL [CITE:xxx] tokens and check they exist
            all_cited = re.findall(r'\[CITE:([^\]]+)\]', content)
            valid_ids = [
                eid for eid in all_cited
                if eid in self._evidence_store
            ]
            phantom_ids = [
                eid for eid in all_cited
                if eid not in self._evidence_store
            ]

            if phantom_ids:
                logger.warning(
                    "[react] Interpretation has %d phantom citations: %s",
                    len(phantom_ids), phantom_ids[:5],
                )
                # Remove phantom citations from output
                for pid in set(phantom_ids):
                    content = content.replace(f"[CITE:{pid}]", "")

            # Post-interpretation claim verification: check that numbers
            # near each [CITE:ev_xxx] actually appear in that evidence.
            # This catches "40% removal" when evidence says "40% cheaper".
            mismatches = self._verify_interpretation_claims(content)
            if mismatches:
                logger.warning(
                    "[react] Interpretation has %d claim mismatches",
                    len(mismatches),
                )
                # Append warnings to the content so the section writer
                # can see which claims may be inaccurate
                warning_lines = ["\n\n**Verification Notes:**"]
                for mm in mismatches[:5]:
                    warning_lines.append(
                        f"- Claim \"{mm['claim'][:60]}\" cites {mm['ev_id'][:20]} "
                        f"which says: \"{mm['ev_statement'][:80]}\""
                    )
                content += "\n".join(warning_lines)

            # Add as the final step in the notebook
            step = AnalysisStep(
                step_number=self._notebook.step_count + 1,
                reasoning="LLM interpretation of raw analysis results",
                tool_name="interpret_results",
                result=ToolResult(
                    success=True,
                    tool_name="interpret_results",
                    markdown=content,
                    source_evidence_ids=list(set(valid_ids)),
                    insights=[
                        "LLM-synthesized analysis with per-claim citations",
                    ],
                ),
                elapsed_seconds=0.0,
            )
            self._notebook.add_step(step)

            logger.info(
                "[react] Interpretation complete: %d chars, %d citations "
                "(%d valid, %d phantom)",
                len(content), len(all_cited), len(valid_ids),
                len(phantom_ids),
            )

        except Exception as exc:
            logger.warning(
                "[react] Interpretation failed: %s: %s",
                type(exc).__name__, str(exc)[:200],
            )

    def _verify_interpretation_claims(self, content: str) -> list[dict]:
        """Lightweight post-interpretation verification.

        For each [CITE:ev_xxx] in the output, extract the number closest
        to it and check if that number appears in the cited evidence
        statement. If not, flag as a potential misinterpretation.

        This catches "GAC 40% removal" when evidence says "40% cheaper"
        because the number 40 IS in the evidence but the surrounding
        words don't match. For that we check if the claim sentence and
        evidence share a key descriptor (removal/cost/efficiency/etc).
        """
        mismatches = []

        # Find all citation contexts: text before [CITE:ev_xxx]
        pattern = re.compile(
            r'([^.!?\n]{10,120})\[CITE:(ev_[a-f0-9]+)\]'
        )

        for match in pattern.finditer(content):
            claim_text = match.group(1).strip()
            ev_id = match.group(2)

            if ev_id not in self._evidence_store:
                continue

            ev = self._evidence_store[ev_id]
            ev_stmt = ev.get("statement", "").lower()

            # Extract the key number from the claim (closest to the citation)
            nums_in_claim = re.findall(r'(\d+\.?\d*)', claim_text)
            if not nums_in_claim:
                continue

            # Check if the key number exists in the evidence
            key_num = nums_in_claim[-1]  # Closest to the citation
            if key_num not in ev_stmt:
                # Number not in evidence — might be derived (e.g. 15x)
                continue

            # Number IS in evidence — now check semantic match
            # Define category keywords
            cost_words = {"cost", "price", "expensive", "affordable",
                          "budget", "spending", "allocated", "funding",
                          "billion", "million", "usd", "$"}
            removal_words = {"removal", "removed", "efficiency", "reduction",
                             "achieved", "treatment", "filtration", "adsorption"}
            market_words = {"market", "share", "cagr", "growth", "valued",
                            "projected", "revenue"}

            claim_lower = claim_text.lower()
            claim_is_cost = any(w in claim_lower for w in cost_words)
            claim_is_removal = any(w in claim_lower for w in removal_words)
            claim_is_market = any(w in claim_lower for w in market_words)

            ev_is_cost = any(w in ev_stmt for w in cost_words)
            ev_is_removal = any(w in ev_stmt for w in removal_words)
            ev_is_market = any(w in ev_stmt for w in market_words)

            # Flag if categories don't match (cost claim citing removal ev)
            category_mismatch = False
            if claim_is_removal and ev_is_cost and not ev_is_removal:
                category_mismatch = True
            if claim_is_cost and ev_is_removal and not ev_is_cost:
                category_mismatch = True
            if claim_is_removal and ev_is_market and not ev_is_removal:
                category_mismatch = True

            if category_mismatch:
                mismatches.append({
                    "claim": claim_text,
                    "ev_id": ev_id,
                    "ev_statement": ev.get("statement", ""),
                    "claim_category": (
                        "cost" if claim_is_cost else
                        "removal" if claim_is_removal else
                        "market" if claim_is_market else "other"
                    ),
                    "ev_category": (
                        "cost" if ev_is_cost else
                        "removal" if ev_is_removal else
                        "market" if ev_is_market else "other"
                    ),
                })

        return mismatches

    def _is_sufficient(self) -> bool:
        """Check if analysis has enough results to stop.

        Requires at least 3 successful steps AND both statistics and
        a comparison/meta tool. This prevents early stopping after
        just extract + stats.
        """
        successful = [
            s for s in self._notebook.steps if s.result.success
        ]

        if len(successful) < 3:
            return False

        has_stats = any(
            s.tool_name in ("statistical_summary", "query_evidence_sql")
            for s in successful
        )
        has_comparison = any(
            s.tool_name in (
                "comparison_table", "meta_analysis", "execute_python",
                "rank_by_impact",
            )
            for s in successful
        )

        return has_stats and has_comparison
