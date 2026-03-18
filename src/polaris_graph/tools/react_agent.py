"""ReAct analysis agent — autonomous tool selection for evidence analysis.

Instead of a fixed 7-tool pipeline, the LLM autonomously decides which
tools to run based on data availability and what's been analyzed so far.
Inspired by OpenAI Deep Research's ReAct (Plan-Act-Observe) pattern.

The agent enforces citation provenance: every analysis result traces back
to original evidence IDs, never "POLARIS Analysis Toolkit".
"""

import asyncio
import json
import logging
import os
import time

from pydantic import BaseModel, Field, field_validator, model_validator

from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook, AnalysisStep
from src.polaris_graph.tools.tool_registry import (
    ToolRegistry,
    ToolResult,
    build_default_registry,
)

logger = logging.getLogger("polaris_graph")

_MAX_ITERATIONS = int(os.getenv("PG_REACT_MAX_ITERATIONS", "5"))
_TIMEOUT_SECONDS = int(os.getenv("PG_REACT_TIMEOUT_SECONDS", "300"))
_TOOL_TIMEOUT = int(os.getenv("PG_REACT_TOOL_TIMEOUT", "60"))

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
    ):
        self._client = client
        self._evidence_store = evidence_store
        self._evidence_ids = evidence_ids
        self._query = query
        self._registry = registry or build_default_registry()
        self._tracer = tracer
        self._notebook = AnalysisNotebook(query, evidence_ids)

    async def run(self) -> AnalysisNotebook:
        """Execute the ReAct loop and return the analysis notebook."""
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
        import re as _re

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

        interpret_timeout = int(os.getenv("PG_REACT_INTERPRET_TIMEOUT", "120"))
        try:
            response = await asyncio.wait_for(
                self._client.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=4096,
                    temperature=0.3,
                ),
                timeout=interpret_timeout,
            )

            content = response.content.strip()
            if not content or len(content) < 100:
                logger.warning(
                    "[react] Interpretation produced too little content: "
                    "%d chars", len(content),
                )
                return

            # Validate: extract ALL [CITE:xxx] tokens and check they exist
            all_cited = _re.findall(r'\[CITE:([^\]]+)\]', content)
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
        import re as _re

        mismatches = []

        # Find all citation contexts: text before [CITE:ev_xxx]
        pattern = _re.compile(
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
            nums_in_claim = _re.findall(r'(\d+\.?\d*)', claim_text)
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
