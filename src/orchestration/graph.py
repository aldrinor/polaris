"""
POLARIS v3 LangGraph State Machine

Defines the research workflow as a directed graph with:
- Nodes: Agent invocations
- Edges: State transitions
- Conditional routing based on state
- Iteration management with saturation detection
- Error handling and recovery

FIX 70: Memory Integration
- retrieve_memories node at start (loads LTM-Stage/Global context)
- consolidate_memory logic in finalize_node (promotes to LTM after CASE_1)

This is the main orchestration layer that coordinates all agents.
"""

import logging
import math
import os
import re
import traceback
from typing import Literal, Annotated, Optional, Callable
from datetime import UTC, datetime, timezone
from functools import wraps

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from .state import ResearchState
from .persistence import save_state

# FIX 70: Memory integration imports
from src.memory.chroma_client import get_chroma_manager

# FIX 80: Citation binding imports
from src.utils.citation_registry import CitationRegistry, normalize_cite_tokens

# SOTA Integration: New module imports (Task #21)
# FIX-052C: Guard import — src.formatters is legacy Track A, may not exist
try:
    from src.formatters import OutputFormatter, OutputFormat, FormatConfig
except ImportError:
    OutputFormatter = None
    OutputFormat = None
    FormatConfig = None
from src.tools.visual_generator import VisualGenerator, ChartData, VisualConfig
from src.utils.content_deduplicator import ContentDeduplicator, DeduplicationConfig
from src.quality import BiasDetector, BiasConfig
from src.quality.output_quality_gate import check_output_quality, repair_output_quality
from src.utils.cot_scrubber import scrub_cot_from_report
from src.utils.cot_post_filter import post_filter_report as cot_post_filter_report
from .iteration_manager import (
    IterationManager,
    IterationConfig,
    ConvergenceReason,
    create_iteration_manager,
    analyze_gaps,
    check_evidence_sufficiency,
    calculate_overall_progress,
)

# =============================================================================
# OpenAI o3 Parity Imports
# =============================================================================
from .dynamic_replanner import DynamicReplanner, ReplanTrigger, ReplanDecision
from .stopping_mechanism import SophisticatedStopper, StopReason, should_stop_research
# FIX-052C: Guard legacy import
try:
    from src.reasoning import ReasoningContext, ReasoningStep
except ImportError:
    ReasoningContext = None
    ReasoningStep = None

# Global o3 parity instances (initialized lazily)
_dynamic_replanner = None
_sophisticated_stopper = None
_reasoning_context = None


def get_dynamic_replanner() -> DynamicReplanner:
    """Get or initialize the dynamic replanner."""
    global _dynamic_replanner
    if _dynamic_replanner is None:
        _dynamic_replanner = DynamicReplanner.from_config()
    return _dynamic_replanner


def get_sophisticated_stopper() -> SophisticatedStopper:
    """Get or initialize the sophisticated stopper."""
    global _sophisticated_stopper
    if _sophisticated_stopper is None:
        _sophisticated_stopper = SophisticatedStopper.from_config()
        _sophisticated_stopper.start_timing()
    return _sophisticated_stopper


def get_reasoning_context():
    """Get or initialize the reasoning context."""
    global _reasoning_context
    if ReasoningContext is None:
        return None
    if _reasoning_context is None:
        import yaml
        try:
            with open("config/settings/thresholds.yaml", "r") as f:
                config = yaml.safe_load(f)
            reasoning_config = config.get("reasoning", {})
            _reasoning_context = ReasoningContext(
                max_backtrack=reasoning_config.get("max_backtrack", 5),
                backtrack_confidence_threshold=reasoning_config.get("backtrack_confidence_threshold", 0.4),
                consecutive_low_confidence=reasoning_config.get("consecutive_low_confidence", 3),
            )
        except Exception:
            _reasoning_context = ReasoningContext()
    return _reasoning_context


def reset_reasoning_state():
    """Reset reasoning state for new research run."""
    global _dynamic_replanner, _sophisticated_stopper, _reasoning_context
    _dynamic_replanner = None
    _sophisticated_stopper = None
    _reasoning_context = None


# Backward compatibility alias
reset_o3_parity_state = reset_reasoning_state


def _balance_evidence_chain(evidence_chain: list, max_per_perspective: int = 50) -> list:
    """
    FIX-129 + FIX-146: Stratified Noah's Ark evidence filter.

    Replaces the old per-perspective cap with a stratified approach that:
    1. GUARANTEES minimum representation per perspective (prevents "Perspective Suicide")
    2. Fills remaining capacity with top-scoring items globally (meritocratic)
    3. Caps total evidence to prevent context flooding

    FIX-146 rationale: Pure meritocratic filtering purges minority perspectives
    (Economic, Regulatory) because Scientific Tier 1 evidence dominates. The
    Noah's Ark guarantee ensures diversity while still favoring quality.

    Args:
        evidence_chain: List of Evidence objects (Pydantic or dict).
        max_per_perspective: Maximum evidence items per perspective (FIX-129 legacy).

    Returns:
        Balanced evidence chain with perspective diversity guaranteed.
    """
    if not evidence_chain:
        return evidence_chain

    # FIX-146: Configurable parameters
    min_per_perspective = int(os.environ.get("POLARIS_MIN_PER_PERSPECTIVE", "5"))
    total_cap = int(os.environ.get("POLARIS_EVIDENCE_TOTAL_CAP", "150"))
    # Floor cannot exceed ceiling
    min_per_perspective = min(min_per_perspective, max_per_perspective)

    def _get_relevance(ev):
        if hasattr(ev, 'relevance_score'):
            return getattr(ev, 'relevance_score', 0)
        elif isinstance(ev, dict):
            return ev.get('relevance_score', 0)
        return 0

    # Group evidence by perspective
    perspective_buckets = {}
    no_perspective = []

    for ev in evidence_chain:
        ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
        perspectives = ev_dict.get("perspective_origins", [])

        if not perspectives:
            no_perspective.append(ev)
            continue

        # Evidence can belong to multiple perspectives; put in primary (first)
        primary = perspectives[0]
        if primary not in perspective_buckets:
            perspective_buckets[primary] = []
        perspective_buckets[primary].append(ev)

    # Sort each bucket by relevance_score (descending)
    for perspective, items in perspective_buckets.items():
        items.sort(key=_get_relevance, reverse=True)

    # FIX-146 Phase 1: Guarantee minimum per perspective (Noah's Ark)
    selected = set()  # Track by id() to avoid duplicates
    selected_list = []

    for perspective, items in perspective_buckets.items():
        take_count = min(min_per_perspective, len(items))
        for item in items[:take_count]:
            item_id = id(item)
            if item_id not in selected:
                selected.add(item_id)
                selected_list.append(item)

    guaranteed_count = len(selected_list)
    perspective_counts = {p: min(min_per_perspective, len(items)) for p, items in perspective_buckets.items()}

    logger.info(
        f"[FIX-146] Noah's Ark guaranteed: {guaranteed_count} items across "
        f"{len(perspective_buckets)} perspectives "
        f"(min {min_per_perspective}/perspective)"
    )

    # FIX-146 Phase 2: Global meritocratic fill to total_cap
    remaining_capacity = total_cap - len(selected_list)

    if remaining_capacity > 0:
        # Pool all remaining items (not yet selected) from all buckets + no_perspective
        candidates = []
        for perspective, items in perspective_buckets.items():
            for item in items:
                if id(item) not in selected:
                    candidates.append(item)

        # Also include untagged evidence in the global pool
        for item in no_perspective:
            if id(item) not in selected:
                candidates.append(item)

        # Sort globally by relevance (meritocratic fill)
        candidates.sort(key=_get_relevance, reverse=True)

        # Fill remaining capacity, respecting max_per_perspective cap
        for item in candidates:
            if len(selected_list) >= total_cap:
                break

            # Check if adding this item would exceed max_per_perspective
            ev_dict = item.model_dump() if hasattr(item, "model_dump") else item if isinstance(item, dict) else {}
            perspectives = ev_dict.get("perspective_origins", [])
            primary = perspectives[0] if perspectives else "_untagged"

            current_count = perspective_counts.get(primary, 0)
            # Untagged evidence is not subject to per-perspective cap
            cap = total_cap if primary == "_untagged" else max_per_perspective
            if current_count < cap:
                item_id = id(item)
                if item_id not in selected:
                    selected.add(item_id)
                    selected_list.append(item)
                    perspective_counts[primary] = current_count + 1

    # Log results
    if len(selected_list) < len(evidence_chain):
        logger.info(
            f"[FIX-146] Stratified filter: {len(evidence_chain)} -> {len(selected_list)} evidence "
            f"(guaranteed={guaranteed_count}, cap={total_cap}, perspectives={len(perspective_buckets)})"
        )
        for p, count in sorted(perspective_counts.items(), key=lambda x: x[1], reverse=True):
            logger.debug(f"  {p}: {count} items")

    return selected_list


def check_backtrack_needed(state: ResearchState, agent_name: str, confidence: float) -> ResearchState:
    """
    Check if backtracking is needed after an agent step.

    Called by routing functions to evaluate if the reasoning path should be revised.
    Triggers backtrack if:
    - Confidence is below threshold
    - Consecutive low confidence steps detected
    - Dead end detected (no progress)

    Args:
        state: Current research state
        agent_name: Name of the agent that just completed
        confidence: Confidence score of the step (0-1)

    Returns:
        Updated state (potentially with backtracked reasoning)
    """
    try:
        reasoning_ctx = get_reasoning_context()
        if reasoning_ctx is None or ReasoningStep is None:
            return state

        # Record the current step - create proper ReasoningStep object
        import uuid
        outcome = "success" if confidence >= 0.6 else ("partial" if confidence >= 0.4 else "failure")
        step = ReasoningStep(
            step_id=str(uuid.uuid4())[:8],
            agent=agent_name,
            action=f"completed_{agent_name}_analysis",
            confidence=confidence,
            outcome=outcome,
            parent_step_id=reasoning_ctx.get_current_step().step_id if reasoning_ctx.steps else None,
            evidence_count=len(state.get("evidence_chain", [])),
            gaps_identified=len(state.get("identified_gaps", [])),
        )
        reasoning_ctx.add_step(step)
        logger.info(f"[BACKTRACK] Recorded step: {agent_name} confidence={confidence:.2f} outcome={outcome}")

        # Check if backtracking is needed - returns BacktrackDecision object
        backtrack_decision = reasoning_ctx.should_backtrack(state)

        if backtrack_decision.should_backtrack:
            logger.warning(f"[BACKTRACK] Triggering backtrack: {backtrack_decision.reason}")

            # Use target from decision or find one
            backtrack_point = backtrack_decision.target_step_id or reasoning_ctx.find_backtrack_point()

            if backtrack_point:
                # Execute backtrack
                backtracked_step = reasoning_ctx.execute_backtrack(backtrack_point)
                logger.info(f"[BACKTRACK] Backtracked to step: {backtrack_point}")

                # Update state with backtrack information
                state["reasoning_backtrack_count"] = state.get("reasoning_backtrack_count", 0) + 1
                state["reasoning_current_branch"] = reasoning_ctx.current_branch

                # Add to dead ends if this path failed
                dead_ends = state.get("reasoning_dead_ends", [])
                if step.step_id not in dead_ends:
                    dead_ends.append(step.step_id)
                state["reasoning_dead_ends"] = dead_ends

                logger.info(
                    f"[BACKTRACK] State updated: backtracks={state['reasoning_backtrack_count']}, "
                    f"dead_ends={len(dead_ends)}"
                )
            else:
                logger.warning("[BACKTRACK] No valid backtrack point found")

        # Serialize reasoning context to state
        state["reasoning_context"] = reasoning_ctx.to_dict()

    except Exception as e:
        logger.error(f"[BACKTRACK] Error in backtrack check: {e}")

    return state


def record_agent_reasoning_step(
    state: ResearchState,
    agent_name: str,
    action: str,
    confidence: float,
    outcome: str = "success",
    metadata: dict = None
) -> ResearchState:
    """
    O3 Parity: Record a reasoning step from an agent execution.

    This should be called at the end of each agent node to maintain
    the continuous reasoning trace.

    Args:
        state: Current research state
        agent_name: Name of the agent
        action: Description of the action taken
        confidence: Confidence score (0-1)
        outcome: Step outcome (success/partial/failure)
        metadata: Additional step metadata

    Returns:
        Updated state with reasoning step recorded
    """
    try:
        import uuid
        reasoning_ctx = get_reasoning_context()
        if reasoning_ctx is None or ReasoningStep is None:
            return state

        # Create proper ReasoningStep object
        meta = metadata or {}
        step = ReasoningStep(
            step_id=str(uuid.uuid4())[:8],
            agent=agent_name,
            action=action,
            confidence=confidence,
            outcome=outcome,
            parent_step_id=reasoning_ctx.get_current_step().step_id if reasoning_ctx.steps else None,
            evidence_count=meta.get("evidence_count", 0),
            quality_score=meta.get("faithfulness", 0.0),
            gaps_identified=meta.get("gaps_identified", 0),
            queries_generated=meta.get("query_count", 0),
        )
        reasoning_ctx.add_step(step)
        state["reasoning_context"] = reasoning_ctx.to_dict()
        logger.debug(f"[REASONING] Recorded step: {agent_name}/{action} (conf={confidence:.2f})")
    except Exception as e:
        logger.error(f"[REASONING] Failed to record step: {e}")
    return state


# =============================================================================
# KIMI K2.5 Parity Tool Integration (Parts 20-28)
# =============================================================================
# These tools are available to agents during research execution.
# Import lazily to avoid circular dependencies and heavy startup costs.

_tool_registry = None


def get_tool_registry():
    """
    Get or initialize the tool registry.

    Returns a dict of tool name -> tool class/function mappings.
    Tools are imported lazily to avoid circular dependencies.
    """
    global _tool_registry

    if _tool_registry is not None:
        return _tool_registry

    _tool_registry = {}

    try:
        from src.tools import (
            # Vision and File Processing
            VisionProcessor,
            FileAnalyzer,
            ChartGenerator,
            # Long-Form Generation
            LongFormGenerator,
            CoherenceValidator,
            # Streaming
            StreamingReasoner,
            # User Interaction
            UserFeedbackManager,
            # Browser
            BrowserAutomation,
            # Research Access
            AccessBypass,
            # Agent Swarm
            FullScaleSwarmOrchestrator,
        )

        _tool_registry = {
            # Vision Tools
            "vision_processor": VisionProcessor,
            # File Analysis
            "file_analyzer": FileAnalyzer,
            "chart_generator": ChartGenerator,
            # Long-Form Generation
            "long_form_generator": LongFormGenerator,
            "coherence_validator": CoherenceValidator,
            # Streaming
            "streaming_reasoner": StreamingReasoner,
            # User Feedback
            "user_feedback": UserFeedbackManager,
            # Browser
            "browser_automation": BrowserAutomation,
            # Research Access
            "access_bypass": AccessBypass,
            # Agent Swarm
            "agent_swarm": FullScaleSwarmOrchestrator,
        }

        logger.info(f"[TOOLS] Registered {len(_tool_registry)} tools")

    except ImportError as e:
        logger.warning(f"[TOOLS] Some tools not available: {e}")

    return _tool_registry


def get_tool(tool_name: str):
    """Get a specific tool by name."""
    registry = get_tool_registry()
    return registry.get(tool_name)


# Tool instance cache (singleton pattern for stateful tools)
_tool_instances = {}


def get_tool_instance(tool_name: str, **kwargs):
    """
    Get or create a tool instance.

    For stateful tools that should be reused across calls.
    """
    cache_key = f"{tool_name}_{hash(frozenset(kwargs.items()))}"

    if cache_key not in _tool_instances:
        tool_class = get_tool(tool_name)
        if tool_class is None:
            return None
        _tool_instances[cache_key] = tool_class(**kwargs)

    return _tool_instances[cache_key]


logger = logging.getLogger(__name__)


# =============================================================================
# Tool Integration Nodes (KIMI K2.5 Parity)
# =============================================================================

def process_file_attachments_node(state: ResearchState) -> ResearchState:
    """
    Process any file attachments using FileAnalyzer.

    Automatically analyzes attached files and adds insights to state.
    File attachments can be provided via agent_trace metadata.
    """
    # Check for file attachments in agent_trace (user-provided files)
    agent_trace = state.get("agent_trace", [])
    attachments = []
    for trace in agent_trace:
        if trace.get("action") == "file_upload":
            attachments.extend(trace.get("files", []))

    if not attachments:
        return state

    logger.info(f"[TOOLS] Processing {len(attachments)} file attachments")

    try:
        analyzer = get_tool_instance(
            "file_analyzer",
            auto_generate_charts=True,
            chart_output_dir="outputs/charts"
        )

        if analyzer is None:
            logger.warning("[TOOLS] FileAnalyzer not available")
            return state

        file_insights = []

        for attachment in attachments:
            file_path = attachment.get("path", attachment) if isinstance(attachment, dict) else attachment

            try:
                result = analyzer.analyze_file(file_path, generate_charts=True)

                file_insights.append({
                    "file": result.file_name,
                    "type": result.file_type,
                    "summary": result.summary,
                    "insights": result.insights,
                    "statistics": result.statistics,
                    "charts": result.charts,
                })

                logger.info(f"[TOOLS] Analyzed {result.file_name}: {result.summary}")

            except Exception as e:
                logger.error(f"[TOOLS] Failed to analyze {file_path}: {e}")

        # Store file insights as facts for synthesizer to use
        if file_insights:
            file_context = "\n".join(
                f"- {fi['file']}: {fi['summary']}. Insights: {', '.join(fi['insights'][:3])}"
                for fi in file_insights
            )

            # Add to agent_trace for synthesizer context
            if "agent_trace" not in state:
                state["agent_trace"] = []
            state["agent_trace"].append({
                "agent": "file_analyzer",
                "action": "analyze_files",
                "file_count": len(file_insights),
                "results": file_insights,
                "context": file_context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Also add to facts_extracted for evidence chain
            if "facts_extracted" not in state:
                state["facts_extracted"] = []
            for fi in file_insights:
                state["facts_extracted"].append({
                    "source": f"file:{fi['file']}",
                    "fact": fi["summary"],
                    "insights": fi["insights"],
                })

    except Exception as e:
        logger.error(f"[TOOLS] File processing failed: {e}")
        state = record_error(state, "process_file_attachments", e)

    return state


def check_user_feedback_node(state: ResearchState) -> ResearchState:
    """
    Check for user feedback at progress milestones.

    Creates checkpoints at 25%, 50%, 75% of iteration progress.
    Feedback checkpoints are stored in agent_trace for tracking.
    """
    # Calculate progress based on iteration count
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 5)
    progress = iteration_count / max_iterations if max_iterations > 0 else 0

    feedback_checkpoints = [0.25, 0.50, 0.75]  # 25%, 50%, 75%

    # Track last checkpoint in agent_trace
    agent_trace = state.get("agent_trace", [])
    last_checkpoint = 0
    for trace in agent_trace:
        if trace.get("action") == "feedback_checkpoint":
            last_checkpoint = max(last_checkpoint, trace.get("checkpoint_pct", 0))

    # Find next checkpoint we've passed
    current_checkpoint = None
    for cp in feedback_checkpoints:
        if progress >= cp and cp > last_checkpoint:
            current_checkpoint = cp
            break

    if current_checkpoint is None:
        return state

    logger.info(f"[TOOLS] User feedback checkpoint at {current_checkpoint:.0%}")

    try:
        feedback_manager = get_tool_instance("user_feedback")

        if feedback_manager is None:
            logger.warning("[TOOLS] UserFeedbackManager not available")
            return state

        # Get current research summary
        draft_report = state.get("draft_report", "")
        evidence_count = len(state.get("evidence_chain", []))
        summary = f"Research progress: {iteration_count}/{max_iterations} iterations, {evidence_count} evidence pieces collected."
        if draft_report:
            summary += f" Draft report: {len(draft_report)} characters."

        # Create checkpoint with correct signature: create_checkpoint(state, stage, summary, questions)
        checkpoint = feedback_manager.create_checkpoint(
            state=dict(state),  # Pass state dict
            stage=f"progress_{int(current_checkpoint * 100)}",
            summary=summary,
            questions=[
                "Is the research direction correct?",
                "Should any topics be added or removed?",
                "Are there specific sources to prioritize?",
            ],
        )

        # Record checkpoint in agent_trace
        if "agent_trace" not in state:
            state["agent_trace"] = []
        state["agent_trace"].append({
            "agent": "user_feedback",
            "action": "feedback_checkpoint",
            "checkpoint_id": checkpoint.checkpoint_id,
            "checkpoint_pct": current_checkpoint,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Check for any pending feedback by looking at checkpoint status
        # Note: Actual feedback would be applied asynchronously via CLI
        if checkpoint.status == "responded":
            # Feedback was provided - apply it with correct signature: apply_feedback(feedback, state)
            if checkpoint.response:
                updated_state = feedback_manager.apply_feedback(checkpoint.response, dict(state))
                # Merge updated state back
                for key, value in updated_state.items():
                    if key in state:
                        state[key] = value
                logger.info(f"[TOOLS] Applied user feedback from checkpoint {checkpoint.checkpoint_id}")

    except Exception as e:
        logger.error(f"[TOOLS] Feedback checkpoint failed: {e}")

    return state


def enhanced_fetch_with_bypass_node(state: ResearchState) -> ResearchState:
    """
    Retry failed URL fetches using AccessBypass.

    Uses Unpaywall, Archive.org, institutional proxy for paywalled content.
    Identifies failed URLs from search_results with fetch_status='failed'.
    """
    # Find failed URLs from search_results (using existing ResearchState keys)
    search_results = state.get("search_results", [])
    failed_urls = []
    for result in search_results:
        if isinstance(result, dict):
            # Check fetch_status field (from SearchResult model)
            if result.get("fetch_status") == "failed":
                failed_urls.append(result.get("url"))
        elif hasattr(result, "fetch_status") and result.fetch_status == "failed":
            failed_urls.append(result.url)

    # Also check urls_failed count - if we have failed attempts but no explicit failed URLs
    if not failed_urls and state.get("urls_failed", 0) > 0:
        # Try to find URLs that were attempted but not in successful results
        logger.debug("[TOOLS] No explicit failed URLs found, skipping bypass")
        return state

    if not failed_urls:
        return state

    logger.info(f"[TOOLS] Attempting bypass for {len(failed_urls)} failed URLs")

    try:
        bypass = get_tool_instance("access_bypass")

        if bypass is None:
            logger.warning("[TOOLS] AccessBypass not available")
            return state

        recovered_content = []

        for url in failed_urls[:10]:  # Limit to 10 retries
            try:
                # Correct method name: fetch_with_bypass (not fetch_with_fallback)
                result = bypass.fetch_with_bypass(url)

                # AccessResult fields: url, content, access_method, legal_alternative, success, metadata
                if result.success:
                    recovered_content.append({
                        "url": url,
                        "content": result.content,
                        "access_method": result.access_method,  # Correct field name
                        "legal_alternative": result.legal_alternative,
                    })
                    logger.info(f"[TOOLS] Recovered content via {result.access_method}: {url[:50]}...")

            except Exception as e:
                logger.debug(f"[TOOLS] Bypass failed for {url}: {e}")

        if recovered_content:
            # Add recovered content to search results
            existing_results = list(state.get("search_results", []))

            # Convert recovered content to SearchResult-compatible dicts
            for content in recovered_content:
                existing_results.append({
                    "result_id": f"bypass_{hash(content['url']) % 10000}",
                    "url": content["url"],
                    "title": f"Recovered via {content['access_method']}",
                    "snippet": content["content"][:200] if content["content"] else "",
                    "source_type": "web",
                    "domain": content["url"].split("/")[2] if "/" in content["url"] else "",
                    "fetch_status": "success",
                    "content": content["content"],
                    "metadata": {"access_method": content["access_method"]},
                })

            state["search_results"] = existing_results
            # Update success count
            state["urls_success"] = state.get("urls_success", 0) + len(recovered_content)

            logger.info(f"[TOOLS] Recovered {len(recovered_content)} documents via bypass")

    except Exception as e:
        logger.error(f"[TOOLS] Access bypass failed: {e}")

    return state


def process_images_node(state: ResearchState) -> ResearchState:
    """
    Process images in search results using VisionProcessor.

    Extracts text, charts, and data from images.
    Image insights are added to facts_extracted for evidence chain.
    """
    search_results = state.get("search_results", [])

    # Find results with images
    image_urls = []
    for result in search_results:
        if isinstance(result, dict):
            images = result.get("images", [])
            image_urls.extend(images)
            # Also check metadata for image URLs
            metadata = result.get("metadata", {})
            if metadata and metadata.get("images"):
                image_urls.extend(metadata.get("images", []))

    if not image_urls:
        return state

    logger.info(f"[TOOLS] Processing {len(image_urls)} images")

    try:
        vision = get_tool_instance("vision_processor")

        if vision is None:
            logger.warning("[TOOLS] VisionProcessor not available")
            return state

        image_insights = []

        for img_url in image_urls[:20]:  # Limit to 20 images
            try:
                # process_image(image_path, context) returns VisionResult
                result = vision.process_image(img_url, context=state.get("original_query", ""))

                # VisionResult fields: image_type, extracted_text, description, data_points, confidence, metadata
                # No .success field - use confidence > 0 as success indicator
                if result.confidence > 0:
                    image_insights.append({
                        "url": img_url,
                        "type": result.image_type.value,
                        "extracted_text": result.extracted_text,
                        "description": result.description,
                        "data_points": result.data_points,  # Correct field name (not extracted_data)
                        "confidence": result.confidence,
                    })

            except Exception as e:
                logger.debug(f"[TOOLS] Image processing failed for {img_url}: {e}")

        if image_insights:
            # Store image insights in facts_extracted (existing ResearchState key)
            if "facts_extracted" not in state:
                state["facts_extracted"] = []

            for insight in image_insights:
                state["facts_extracted"].append({
                    "source": f"image:{insight['url']}",
                    "fact": insight["description"],
                    "extracted_text": insight["extracted_text"],
                    "data_points": insight["data_points"],
                    "confidence": insight["confidence"],
                })

            # Also add to agent_trace for tracking
            if "agent_trace" not in state:
                state["agent_trace"] = []
            state["agent_trace"].append({
                "agent": "vision_processor",
                "action": "process_images",
                "image_count": len(image_insights),
                "insights": image_insights,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            logger.info(f"[TOOLS] Extracted insights from {len(image_insights)} images")

    except Exception as e:
        logger.error(f"[TOOLS] Image processing failed: {e}")

    return state


# =============================================================================
# Error Handling Utilities
# =============================================================================

class NodeExecutionError(Exception):
    """Exception raised when a node fails to execute."""
    def __init__(self, node_name: str, original_error: Exception, state: ResearchState):
        self.node_name = node_name
        self.original_error = original_error
        self.state = state
        super().__init__(f"Node '{node_name}' failed: {str(original_error)}")


def record_error(state: ResearchState, node_name: str, error: Exception) -> ResearchState:
    """Record an error in the state for tracking and recovery."""
    if "errors" not in state:
        state["errors"] = []

    error_record = {
        "node": node_name,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": traceback.format_exc(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iteration": state.get("iteration_count", 0),
    }

    state["errors"].append(error_record)
    logger.error(f"[{node_name.upper()}] Error recorded: {error}")

    return state


def with_error_handling(node_name: str, max_retries: int = 2, fallback_fn: Callable = None):
    """
    Decorator for node functions that adds error handling and retry logic.

    Args:
        node_name: Name of the node for logging
        max_retries: Maximum retry attempts
        fallback_fn: Optional fallback function if all retries fail
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state: ResearchState) -> ResearchState:
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    return func(state)
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"[{node_name.upper()}] Attempt {attempt + 1}/{max_retries + 1} failed: {e}"
                    )

                    if attempt < max_retries:
                        logger.info(f"[{node_name.upper()}] Retrying...")
                        continue

                    # All retries failed
                    logger.error(f"[{node_name.upper()}] All retries exhausted")
                    state = record_error(state, node_name, last_error)

                    # Try fallback if provided
                    if fallback_fn:
                        logger.info(f"[{node_name.upper()}] Executing fallback")
                        try:
                            return fallback_fn(state)
                        except Exception as fallback_error:
                            logger.error(f"[{node_name.upper()}] Fallback also failed: {fallback_error}")
                            state = record_error(state, f"{node_name}_fallback", fallback_error)

                    # Return state with error recorded (workflow can continue)
                    return state

            return state

        return wrapper
    return decorator


def create_fallback_state_update(node_name: str) -> Callable:
    """Create a fallback function that updates state minimally."""
    def fallback(state: ResearchState) -> ResearchState:
        logger.warning(f"[{node_name.upper()}] Using fallback - minimal state update")

        # Add trace entry for fallback
        if "agent_trace" not in state:
            state["agent_trace"] = []

        state["agent_trace"].append({
            "agent": node_name,
            "action": "fallback",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Agent failed, using fallback state",
        })

        return state

    return fallback

# Global iteration manager (set per workflow)
_iteration_manager: Optional[IterationManager] = None


def get_iteration_manager() -> IterationManager:
    """Get or create the iteration manager."""
    global _iteration_manager
    if _iteration_manager is None:
        _iteration_manager = create_iteration_manager()
    return _iteration_manager


def set_iteration_manager(manager: IterationManager):
    """Set the iteration manager for this workflow."""
    global _iteration_manager
    _iteration_manager = manager


# =============================================================================
# Node Functions
# =============================================================================

@with_error_handling("retrieve_memories", max_retries=1, fallback_fn=create_fallback_state_update("retrieve_memories"))
def retrieve_memories_node(state: ResearchState) -> ResearchState:
    """
    FIX 70: Retrieve prior knowledge from LTM before research begins.

    This node runs FIRST in the graph, enabling the "snowball effect":
    - Queries LTM-Stage for same stage+region prior research
    - Queries LTM-Global for cross-stage context
    - Registers VWM for this vector's working memory

    The retrieved context informs the planner and synthesizer agents.
    """
    vector_id = state.get("vector_id", "unknown")
    stage = state.get("stage", 1)
    region = state.get("region", "NORTH_AMERICA")
    query = state.get("original_query", "")

    logger.info(f"[MEMORY] Retrieving prior knowledge for {vector_id}")

    try:
        chroma = get_chroma_manager()

        # Register VWM for this vector (clean slate)
        chroma.register_vwm(vector_id)
        logger.debug(f"[MEMORY] VWM registered: {vector_id}")

        # Query LTM-Stage for same stage+region prior research
        ltm_stage_context = []
        if query:
            ltm_stage_context = chroma.query_ltm_stage(
                query=query,
                stage=stage,
                region=region,
                n_results=20,
            )
            logger.info(
                f"[MEMORY] LTM-Stage ({stage}, {region}): "
                f"Retrieved {len(ltm_stage_context)} prior documents"
            )

        # Query LTM-Global for cross-stage context
        ltm_global_context = []
        if query:
            ltm_global_context = chroma.get_cross_session_context(
                query=query,
                n_results=10,
            )
            logger.info(
                f"[MEMORY] LTM-Global: Retrieved {len(ltm_global_context)} documents"
            )

        # Update state with memory context
        state["ltm_stage_context"] = ltm_stage_context
        state["ltm_global_context"] = ltm_global_context
        state["prior_knowledge_count"] = len(ltm_stage_context) + len(ltm_global_context)
        state["memory_initialized"] = True

        # Log the snowball effect metric
        if state["prior_knowledge_count"] > 0:
            logger.info(
                f"[MEMORY] SNOWBALL EFFECT: Vector {vector_id} starting with "
                f"{state['prior_knowledge_count']} prior documents "
                f"(Stage: {len(ltm_stage_context)}, Global: {len(ltm_global_context)})"
            )
        else:
            logger.info(f"[MEMORY] No prior knowledge for {vector_id} (baseline vector)")

        # Add trace entry
        if "agent_trace" not in state:
            state["agent_trace"] = []
        state["agent_trace"].append({
            "agent": "retrieve_memories",
            "action": "retrieve",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ltm_stage_count": len(ltm_stage_context),
            "ltm_global_count": len(ltm_global_context),
        })

        save_state(state, "after_memory_retrieval")

    except Exception as e:
        logger.error(f"[MEMORY] Failed to retrieve memories: {e}")
        # Non-fatal - continue without memory context
        state["ltm_stage_context"] = []
        state["ltm_global_context"] = []
        state["prior_knowledge_count"] = 0
        state["memory_initialized"] = False
        state = record_error(state, "retrieve_memories", e)

    return state


@with_error_handling("triage", max_retries=2, fallback_fn=create_fallback_state_update("triage"))
def triage_node(state: ResearchState) -> ResearchState:
    """Triage agent node - classifies the query."""
    from src.agents.triage_agent import TriageAgent

    logger.info(f"[TRIAGE] Processing {state.get('vector_id')}")

    agent = TriageAgent()
    state = agent.invoke(state)

    # Save checkpoint
    save_state(state, "after_triage")

    return state


@with_error_handling("planner", max_retries=2, fallback_fn=create_fallback_state_update("planner"))
def planner_node(state: ResearchState) -> ResearchState:
    """Planner agent node - creates research plan."""
    from src.agents.planner_agent import PlannerAgent

    logger.info(f"[PLANNER] Processing {state.get('vector_id')}")

    # Increment iteration if re-planning
    if state.get("sub_queries"):
        state["iteration_count"] = state.get("iteration_count", 0) + 1
        logger.info(f"[PLANNER] Iteration {state['iteration_count']}")

    agent = PlannerAgent()
    state = agent.invoke(state)

    # O3 PARITY: Record reasoning step for planner
    sub_queries = state.get("sub_queries", [])
    query_count = len(sub_queries)
    confidence = min(1.0, query_count / 20) if query_count > 0 else 0.3
    state = record_agent_reasoning_step(
        state, "planner", "generated_research_plan",
        confidence=confidence,
        outcome="success" if query_count >= 15 else ("partial" if query_count >= 5 else "failure"),
        metadata={"query_count": query_count, "iteration": state.get("iteration_count", 0)}
    )

    # Save checkpoint
    save_state(state, f"after_planner_iter{state.get('iteration_count', 0)}")

    return state


@with_error_handling("supervisor", max_retries=1)
def supervisor_node(state: ResearchState) -> ResearchState:
    """Supervisor agent node - decides next action."""
    from src.agents.supervisor_agent import SupervisorAgent

    logger.info(f"[SUPERVISOR] Evaluating {state.get('vector_id')}")

    agent = SupervisorAgent()
    state = agent.invoke(state)

    return state


@with_error_handling("search", max_retries=3, fallback_fn=create_fallback_state_update("search"))
def search_node(state: ResearchState) -> ResearchState:
    """Search agent node - executes searches.

    SPRINT 2 FIX 2.3 (Gemini "Cross-Encoder Gate"):
    After search, filter chunks by semantic relevance BEFORE analyst.
    This prevents BRONZE/UNVERIFIED evidence from ever being created.
    """
    from src.agents.search_agent import SearchAgent
    from src.functions.relevance_filter import cross_encoder_filter_dynamic_with_metadata

    logger.info(f"[SEARCH] Processing {state.get('vector_id')}")

    agent = SearchAgent()
    state = agent.invoke(state)

    # CROSS-ENCODER GATE: Filter chunks by semantic relevance
    search_results = state.get("search_results", [])
    # FIX: Variable name bug - was "query" but ResearchState uses "original_query"
    # This caused the cross-encoder gate to be skipped entirely (empty string)
    query = state.get("original_query", "")

    if search_results and query:
        original_count = len(search_results)

        # Convert search results to format expected by cross-encoder filter
        # SearchResult has: snippet (short), content (full text, may be None)
        items_to_filter = []
        for result in search_results:
            # Use content if available, otherwise snippet
            if hasattr(result, 'content') and result.content:
                text = result.content
            elif hasattr(result, 'snippet'):
                text = result.snippet
            elif isinstance(result, dict):
                text = result.get("content") or result.get("snippet", str(result))
            else:
                text = str(result)

            items_to_filter.append({
                "text": text,
                "_original": result
            })

        # FIX 84 (Operation Unshackle): Replace static threshold with dynamic filter
        # PROBLEM: Static threshold 0.15 rejected 99.6% of content (471 -> 2 results)
        # SOLUTION: Dynamic filter guarantees minimum evidence floor
        # FIX 107G (Gemini Audit): Increased min_keep from 50 to 200
        # - min_keep=200: Must exceed target citation count (130) + buffer
        # - max_keep=350: Cap to prevent memory issues
        # - percentile=0.25: Keep top 25% by relevance score
        # - floor_threshold=0.10: Only reject truly garbage content

        try:
            filtered_items = cross_encoder_filter_dynamic_with_metadata(
                query=query,
                items=items_to_filter,
                text_key="text",
                min_keep=200,   # FIX 107G: Increased from 50 to 200
                max_keep=350,   # FIX 107G: Increased from 250 to 350
                percentile=0.25,
                floor_threshold=0.10
            )

            # Extract original results that passed
            filtered_results = [item["_original"] for item in filtered_items]
            filtered_count = len(filtered_results)

            logger.info(
                f"[SEARCH] CROSS-ENCODER GATE (FIX 84/107G): {original_count} -> {filtered_count} "
                f"(dynamic filter, min_keep=200, max_keep=350)"
            )

        except Exception as e:
            logger.error(f"[FIX 40] Cross-encoder filter failed: {e}, passing all results")
            filtered_results = search_results
            filtered_count = len(filtered_results)

        # Update state with filtered results
        state["search_results"] = filtered_results
        state["cross_encoder_gate_applied"] = True
        state["cross_encoder_gate_stats"] = {
            "original_count": original_count,
            "filtered_count": filtered_count,
            "removed_count": original_count - filtered_count,
            "removal_rate": 1 - (filtered_count / max(original_count, 1))
        }

    # O3 PARITY: Record reasoning step for search
    search_count = len(state.get("search_results", []))
    confidence = min(1.0, search_count / 50) if search_count > 0 else 0.2  # Scale by results
    state = record_agent_reasoning_step(
        state, "search", "executed_search_queries",
        confidence=confidence,
        outcome="success" if search_count >= 10 else "partial",
        metadata={"result_count": search_count}
    )

    save_state(state, "after_search")
    return state


@with_error_handling("analyst", max_retries=2, fallback_fn=create_fallback_state_update("analyst"))
def analyst_node(state: ResearchState) -> ResearchState:
    """Analyst agent node - extracts evidence."""
    from src.agents.analyst_agent import AnalystAgent

    logger.info(f"[ANALYST] Processing {state.get('vector_id')}")

    # FIX-124I-D: Pre-analyst perspective health check
    # Use stats already calculated by SearchAgent (stored in state)
    perspective_stats = state.get("search_perspective_stats", {})

    if perspective_stats:
        perspective_count = perspective_stats.get("perspectives_covered", 0)
        balance = perspective_stats.get("balance", 0)
        is_healthy = perspective_stats.get("is_healthy", True)
        perspective_coverage = perspective_stats.get("perspective_distribution", {})

        if not is_healthy:
            logger.warning(
                f"[FIX-124I-D] Pre-analyst perspective health WARNING: "
                f"{perspective_count} perspectives, balance={balance:.2f}"
            )
            state["perspective_health_warning"] = {
                "count": perspective_count,
                "balance": round(balance, 3) if isinstance(balance, float) else balance,
                "coverage": perspective_coverage,
            }
            # Note: Could trigger early replan here if coverage is catastrophic
    else:
        # Fallback: Calculate from search_results if stats not available
        search_results = state.get("search_results", [])
        if search_results:
            perspective_coverage = {}
            for r in search_results:
                r_dict = r.model_dump() if hasattr(r, "model_dump") else r if isinstance(r, dict) else {}
                origins = r_dict.get("perspective_origins", []) or []
                if not origins:
                    origin = r_dict.get("perspective_origin")
                    if origin:
                        origins = [origin]
                for origin in origins:
                    perspective_coverage[origin] = perspective_coverage.get(origin, 0) + 1

            if perspective_coverage:
                perspective_count = len(perspective_coverage)
                values = list(perspective_coverage.values())
                balance = min(values) / max(values) if max(values) > 0 else 0

                if perspective_count < 5 or balance < 0.15:
                    logger.warning(
                        f"[FIX-124I-D] Pre-analyst perspective health WARNING (fallback calc): "
                        f"{perspective_count} perspectives, balance={balance:.2f}"
                    )
                    state["perspective_health_warning"] = {
                        "count": perspective_count,
                        "balance": round(balance, 3),
                        "coverage": perspective_coverage,
                    }

    agent = AnalystAgent()
    state = agent.invoke(state)

    # O3 PARITY: Record reasoning step for analyst
    evidence_count = len(state.get("evidence_chain", []))
    confidence = min(1.0, evidence_count / 30) if evidence_count > 0 else 0.2
    state = record_agent_reasoning_step(
        state, "analyst", "extracted_evidence",
        confidence=confidence,
        outcome="success" if evidence_count >= 10 else "partial",
        metadata={"evidence_count": evidence_count}
    )

    save_state(state, "after_analyst")
    return state


@with_error_handling("verifier", max_retries=2, fallback_fn=create_fallback_state_update("verifier"))
def verifier_node(state: ResearchState) -> ResearchState:
    """Verifier agent node - verifies claims."""
    from src.agents.verifier_agent import VerifierAgent

    logger.info(f"[VERIFIER] Processing {state.get('vector_id')}")

    agent = VerifierAgent()
    state = agent.invoke(state)

    # O3 PARITY: Record reasoning step for verifier
    verification_score = state.get("verification_score", 0.5)
    state = record_agent_reasoning_step(
        state, "verifier", "verified_claims",
        confidence=verification_score,
        outcome="success" if verification_score >= 0.7 else "partial",
        metadata={"verification_score": verification_score}
    )

    save_state(state, "after_verifier")
    return state


@with_error_handling("critic", max_retries=2, fallback_fn=create_fallback_state_update("critic"))
def critic_node(state: ResearchState) -> ResearchState:
    """Critic agent node - evaluates quality."""
    from src.agents.critic_agent import CriticAgent

    logger.info(f"[CRITIC] Processing {state.get('vector_id')}")

    agent = CriticAgent()
    state = agent.invoke(state)

    # O3 PARITY: Record reasoning step for critic
    quality_metrics = state.get("quality_metrics", {})
    if isinstance(quality_metrics, dict):
        faithfulness = quality_metrics.get("faithfulness", 0.5)
    else:
        faithfulness = getattr(quality_metrics, "faithfulness", 0.5)
    state = record_agent_reasoning_step(
        state, "critic", "evaluated_quality",
        confidence=faithfulness,
        outcome="success" if faithfulness >= 0.7 else ("partial" if faithfulness >= 0.5 else "failure"),
        metadata={"faithfulness": faithfulness}
    )

    save_state(state, "after_critic")
    return state


@with_error_handling("synthesizer", max_retries=2, fallback_fn=create_fallback_state_update("synthesizer"))
def synthesizer_node(state: ResearchState) -> ResearchState:
    """Synthesizer agent node - generates report.

    SPRINT 1 FIX 1.1 (Gemini "Trash Compactor"):
    Filter evidence to GOLD/SILVER BEFORE synthesis.
    This removes 61% noise that caused "Lost in the Middle" syndrome.

    SPRINT 2 FIX 2.4 (Iterative Synthesis):
    Option to generate section-by-section with per-section verification.
    Enable via state["use_iterative_synthesis"] = True.

    FIX 117 (Path B - Cite-First Architecture):
    Enable cite-first synthesis via POLARIS_CITEFIRST_ENABLED=1.
    This inverts the synthesis order: claim → evidence → verify → write.
    Target: 90%+ faithfulness (vs 75% ceiling with write-then-cite).
    """
    import os
    from src.agents.synthesizer_agent import SynthesizerAgent, IterativeSynthesizer

    logger.info(f"[SYNTHESIZER] Processing {state.get('vector_id')}")

    # FIX 117: Check for cite-first mode
    citefirst_enabled = os.environ.get("POLARIS_CITEFIRST_ENABLED", "0") == "1"

    if citefirst_enabled:
        logger.info("[FIX 117] Using CITE-FIRST synthesis (Path B for 90%+ faithfulness)")
        try:
            from src.agents.citefirst_synthesizer import CitefirstSynthesizer

            # FIX 117 Phase 3.1: Check if this is a revision pass
            revision_count = state.get("auditor_revision_count", 0)
            sentences_to_revise = state.get("sentences_to_revise", [])
            is_revision_pass = revision_count > 0 and sentences_to_revise

            if is_revision_pass:
                # REVISION MODE: Use dynamic re-retrieval for failed sentences
                logger.info(
                    f"[FIX 117] REVISION MODE: revision #{revision_count} with {len(sentences_to_revise)} sentences to revise"
                )

                agent = CitefirstSynthesizer()
                state = agent.process_revision(state, sentences_to_revise)

                # FIX-230: Track KimiClient fallback count for FIX-229 gate
                state["kimi_fallback_count"] = state.get("kimi_fallback_count", 0) + getattr(agent, '_kimi_fallback_count', 0)

                # Record revision stats
                revision_stats = state.get("revision_stats", {})
                logger.info(
                    f"[FIX 117] Revision complete: "
                    f"{revision_stats.get('sentences_rephrased', 0)} rephrased, "
                    f"{revision_stats.get('new_evidence_retrieved', 0)} new evidence"
                )

                state = record_agent_reasoning_step(
                    state, "citefirst_synthesizer", "revision_with_reretrieval",
                    confidence=0.7,
                    outcome="success" if revision_stats.get("sentences_rephrased", 0) > 0 else "partial",
                    metadata=revision_stats
                )

                save_state(state, f"after_citefirst_revision_{revision_count}")
                return state

            # INITIAL SYNTHESIS MODE
            # Apply trash compactor to evidence before cite-first synthesis
            evidence_chain = state.get("evidence_chain", [])
            original_count = len(evidence_chain)

            if evidence_chain:
                filtered_evidence = [
                    e for e in evidence_chain
                    if getattr(e, 'quality_tier', 'UNVERIFIED') in ('GOLD', 'SILVER')
                    and getattr(e, 'relevance_score', 0) > 0.0
                ]
                logger.info(
                    f"[SYNTHESIZER] TRASH COMPACTOR (cite-first): {original_count} -> {len(filtered_evidence)} evidence"
                )

                # FIX-129: Balance evidence chain to prevent perspective flooding
                filtered_evidence = _balance_evidence_chain(filtered_evidence, max_per_perspective=50)

                state["evidence_chain"] = filtered_evidence

            # =================================================================
            # FIX-210: Pre-synthesis evidence relevance gate
            # If evidence pool is off-topic, refuse to synthesize (CASE_3).
            # =================================================================
            gate_evidence = state.get("evidence_chain", [])
            if gate_evidence:
                relevance_scores = [getattr(e, 'relevance_score', 0.0) for e in gate_evidence]
                sorted_scores = sorted(relevance_scores)
                median_relevance = sorted_scores[len(sorted_scores) // 2]
                high_relevance_count = sum(1 for s in relevance_scores if s >= 0.60)
                high_relevance_pct = high_relevance_count / len(relevance_scores)

                min_median = float(os.environ.get("POLARIS_MIN_MEDIAN_RELEVANCE", "0.50"))
                min_high_pct = float(os.environ.get("POLARIS_MIN_HIGH_RELEVANCE_PCT", "0.30"))

                logger.info(
                    f"[FIX-210] Evidence relevance gate: median={median_relevance:.3f} "
                    f"(min={min_median}), high_pct={high_relevance_pct:.1%} (min={min_high_pct:.0%})"
                )

                if median_relevance < min_median or high_relevance_pct < min_high_pct:
                    state["gating_case"] = "CASE_3"
                    state["draft_report"] = (
                        f"CASE_3: Evidence pool off-topic. "
                        f"Median relevance: {median_relevance:.3f} (threshold: {min_median}), "
                        f"High-relevance evidence: {high_relevance_pct:.1%} (threshold: {min_high_pct:.0%}). "
                        f"Synthesis refused to prevent wasting API costs on garbage evidence."
                    )
                    logger.error(
                        f"[FIX-210] EVIDENCE GATE FAILED — returning CASE_3. "
                        f"Median relevance {median_relevance:.3f} < {min_median} or "
                        f"high-relevance {high_relevance_pct:.1%} < {min_high_pct:.0%}"
                    )
                    save_state(state, "after_evidence_relevance_gate_fail")
                    return state

            # Use cite-first synthesizer
            agent = CitefirstSynthesizer()
            state = agent.invoke(state)

            # FIX-230: Track KimiClient fallback count for FIX-229 gate
            state["kimi_fallback_count"] = getattr(agent, '_kimi_fallback_count', 0)
            if state["kimi_fallback_count"] > 0:
                logger.warning(
                    f"[FIX-230] KimiClient had {state['kimi_fallback_count']} fallbacks during synthesis. "
                    f"FIX-211 LLM post-filter will run in finalize_node."
                )

            # Record cite-first specific stats
            citefirst_stats = state.get("citefirst_stats", {})
            logger.info(
                f"[FIX 117] Cite-first synthesis complete: "
                f"{citefirst_stats.get('claims_grounded', 0)}/{citefirst_stats.get('claims_generated', 0)} claims grounded, "
                f"avg confidence: {citefirst_stats.get('average_confidence', 0):.2f}"
            )

            # Record reasoning step
            draft_report = state.get("draft_report", "")
            word_count = len(draft_report.split()) if draft_report else 0
            state = record_agent_reasoning_step(
                state, "citefirst_synthesizer", "generated_citefirst_report",
                confidence=citefirst_stats.get("average_confidence", 0.5),
                outcome="success" if citefirst_stats.get("claims_grounded", 0) > 10 else "partial",
                metadata={
                    "word_count": word_count,
                    "claims_grounded": citefirst_stats.get("claims_grounded", 0),
                    "claims_ungroundable": citefirst_stats.get("claims_ungroundable", 0),
                }
            )

            save_state(state, "after_citefirst_synthesizer")
            return state

        except ImportError as e:
            # FIX-212 P0: If citefirst is enabled but not importable, this is CASE_4 (hard fail)
            logger.error(f"[FIX-212] CitefirstSynthesizer IMPORT FAILED: {e}")
            state["gating_case"] = "CASE_4"
            state["draft_report"] = f"CASE_4: CitefirstSynthesizer import failed: {e}"
            save_state(state, "after_citefirst_import_fail")
            raise RuntimeError(
                f"[FIX-212] POLARIS_CITEFIRST_ENABLED=1 but CitefirstSynthesizer "
                f"cannot be imported: {e}. Run preflight.py to diagnose."
            )
        except Exception as e:
            # FIX-212 P0: Cite-first synthesis failure is CASE_4, not a silent fallback
            logger.error(f"[FIX-212] Cite-first synthesis CRASHED: {e}")
            state["gating_case"] = "CASE_4"
            state["draft_report"] = f"CASE_4: Cite-first synthesis crashed: {e}"
            save_state(state, "after_citefirst_crash")
            raise RuntimeError(
                f"[FIX-212] Cite-first synthesis crashed: {e}. "
                f"User states: 'Fallback is considered a major failure'."
            )

    # TRASH COMPACTOR: Filter evidence at orchestration level (as Gemini specified)
    evidence_chain = state.get("evidence_chain", [])
    original_count = len(evidence_chain)

    if evidence_chain:
        # Filter to GOLD and SILVER tiers only
        filtered_evidence = [
            e for e in evidence_chain
            if getattr(e, 'quality_tier', 'UNVERIFIED') in ('GOLD', 'SILVER')
        ]

        # Also filter out relevance_score=0.0 (confirmed bug from File 07)
        filtered_evidence = [
            e for e in filtered_evidence
            if getattr(e, 'relevance_score', 0) > 0.0
        ]

        filtered_count = len(filtered_evidence)
        logger.info(
            f"[SYNTHESIZER] TRASH COMPACTOR: {original_count} -> {filtered_count} evidence "
            f"({100 * (1 - filtered_count / max(original_count, 1)):.1f}% noise removed)"
        )

        # Update state with filtered evidence
        state["evidence_chain"] = filtered_evidence
        state["trash_compactor_applied"] = True
        state["trash_compactor_stats"] = {
            "original_count": original_count,
            "filtered_count": filtered_count,
            "removed_count": original_count - filtered_count,
            "removal_rate": 1 - (filtered_count / max(original_count, 1))
        }

    # ==========================================================================
    # FIX-210: Pre-synthesis evidence relevance gate (standard path)
    # ==========================================================================
    gate_evidence_std = state.get("evidence_chain", [])
    if gate_evidence_std:
        relevance_scores_std = [getattr(e, 'relevance_score', 0.0) for e in gate_evidence_std]
        sorted_scores_std = sorted(relevance_scores_std)
        median_relevance_std = sorted_scores_std[len(sorted_scores_std) // 2]
        high_relevance_count_std = sum(1 for s in relevance_scores_std if s >= 0.60)
        high_relevance_pct_std = high_relevance_count_std / len(relevance_scores_std)

        min_median_std = float(os.environ.get("POLARIS_MIN_MEDIAN_RELEVANCE", "0.50"))
        min_high_pct_std = float(os.environ.get("POLARIS_MIN_HIGH_RELEVANCE_PCT", "0.30"))

        logger.info(
            f"[FIX-210] Evidence relevance gate (std): median={median_relevance_std:.3f} "
            f"(min={min_median_std}), high_pct={high_relevance_pct_std:.1%} (min={min_high_pct_std:.0%})"
        )

        if median_relevance_std < min_median_std or high_relevance_pct_std < min_high_pct_std:
            state["gating_case"] = "CASE_3"
            state["draft_report"] = (
                f"CASE_3: Evidence pool off-topic. "
                f"Median relevance: {median_relevance_std:.3f} (threshold: {min_median_std}), "
                f"High-relevance evidence: {high_relevance_pct_std:.1%} (threshold: {min_high_pct_std:.0%}). "
                f"Synthesis refused to prevent wasting API costs on garbage evidence."
            )
            logger.error(
                f"[FIX-210] EVIDENCE GATE FAILED (std) — returning CASE_3. "
                f"Median relevance {median_relevance_std:.3f} < {min_median_std} or "
                f"high-relevance {high_relevance_pct_std:.1%} < {min_high_pct_std:.0%}"
            )
            save_state(state, "after_evidence_relevance_gate_fail_std")
            return state

    # FIX-202: Preserve original report for word count comparison
    original_draft = state.get("draft_report", "")
    original_word_count = len(original_draft.split()) if original_draft else 0

    agent = SynthesizerAgent()

    # SPRINT 2 FIX 2.4: Use iterative synthesis if enabled
    use_iterative = state.get("use_iterative_synthesis", False)

    if use_iterative:
        logger.info("[SYNTHESIZER] Using ITERATIVE section-by-section synthesis")
        iterative_synth = IterativeSynthesizer(agent)
        state = iterative_synth.synthesize_iteratively(state)
    else:
        state = agent.invoke(state)

    # FIX-202: Word count floor — reject fallback synthesis if > 30% word loss
    draft_report = state.get("draft_report", "")
    word_count = len(draft_report.split()) if draft_report else 0
    if original_word_count > 500 and word_count > 0:
        loss_pct = (original_word_count - word_count) / original_word_count
        if loss_pct > 0.30:
            logger.warning(
                f"[FIX-202] Standard synthesizer fallback lost {loss_pct:.0%} words "
                f"({original_word_count} -> {word_count}). Restoring original report."
            )
            state["draft_report"] = original_draft
            word_count = original_word_count

    # O3 PARITY: Record reasoning step for synthesizer
    confidence = min(1.0, word_count / 2000)  # Scale by expected word count
    state = record_agent_reasoning_step(
        state, "synthesizer", "generated_report",
        confidence=confidence,
        outcome="success" if word_count >= 1500 else ("partial" if word_count >= 500 else "failure"),
        metadata={"word_count": word_count}
    )

    save_state(state, "after_synthesizer")
    return state


# =============================================================================
# FIX 107: Citation Enrichment Node
# =============================================================================

@with_error_handling("citation_enrichment", max_retries=1, fallback_fn=create_fallback_state_update("citation_enrichment"))
def citation_enrichment_node(state: ResearchState) -> ResearchState:
    """
    FIX 107 + FIX 107J: Post-verification citation enrichment node.

    This node runs AFTER the Router has authorized enrichment. Its job is to
    increase citation density without modifying the verified text content.

    FIX 107J "AUDITOR TRUST" UPDATE:
    - The Router now handles ALL authorization logic (auditor approval, faithfulness, hail mary)
    - This node TRUSTS the Router's decision - if we're routed here, we enrich
    - Removed the redundant "double gate" faithfulness check that blocked RUN11
    - Only safety check: catastrophic faithfulness (<50%) which Router should already block

    Key Design:
    - Uses semantic matching to find relevant evidence for under-cited sentences
    - Soft verification (MiniCheck at 0.25 threshold, NO atomic decomposition)
    - Injects citations without modifying text content
    - Tracks enrichment_citations for FIX 107B auditor bypass
    """
    import os
    from src.agents.citation_enricher_agent import CitationEnricherAgent

    # Check if enrichment is enabled
    if os.environ.get("POLARIS_ENRICHMENT_ENABLED", "1") != "1":
        logger.info("[FIX 107] Citation enrichment disabled, skipping")
        return state

    faithfulness = state.get("post_hoc_faithfulness", 0.0)
    revision_count = state.get("auditor_revision_count", 0)

    # ==========================================================================
    # FIX 107J: TRUST THE ROUTER
    # ==========================================================================
    # The Router (route_after_auditor) has ALREADY decided we should enrich.
    # We don't second-guess that decision. The "double gate" problem in RUN11
    # was caused by this node re-checking faithfulness after Router approved.
    #
    # REMOVED: The old faithfulness < min_faithfulness check that blocked RUN11
    #
    # Only safety check: catastrophic faithfulness (<50%) - this should already
    # be caught by Router, but we double-check as a safety net.
    # ==========================================================================

    if faithfulness < 0.50:
        logger.warning(
            f"[FIX 107J] SAFETY NET: Faithfulness {faithfulness:.1%} < 50% is catastrophic. "
            f"This should have been caught by Router. Skipping enrichment."
        )
        return state

    logger.info(
        f"[FIX 107J] Executing citation enrichment (Router authorized, "
        f"faithfulness={faithfulness:.1%}, revision_count={revision_count})"
    )

    # ==========================================================================
    # FIX 107J-B: Pass router authorization flag to the agent
    # ==========================================================================
    # The CitationEnricherAgent has its own faithfulness check (legacy from pre-107J).
    # We set this flag to tell the agent "the Router has already authorized you,
    # bypass your own faithfulness check."
    state["router_authorized_enrichment"] = True

    agent = CitationEnricherAgent()
    state = agent.invoke(state)

    # Log enrichment summary
    summary = state.get("enrichment_summary", {})
    if summary:
        logger.info(
            f"[FIX 107] Enrichment complete: "
            f"{summary.get('citations_added', 0)} citations added "
            f"({summary.get('original_citation_count', 0)} -> {summary.get('final_citation_count', 0)})"
        )

    save_state(state, "after_citation_enrichment")
    return state


@with_error_handling("auditor", max_retries=2, fallback_fn=create_fallback_state_update("auditor"))
def auditor_node(state: ResearchState) -> ResearchState:
    """Auditor agent node - post-hoc verification of generated report.

    SPRINT 2 FIX 2.1 (Gemini Recommendation):
    Verify the OUTPUT (generated report), not the inputs.
    Check that each sentence with [CITE:id] is actually supported by that evidence.
    Return unfaithful sentences for revision.

    FIX 21 (Gemini Audit FIX 1):
    Increment auditor_revision_count HERE (inside the node), not in
    route_after_auditor(). LangGraph conditional edge functions should be
    read-only; state mutations in routing functions are discarded by the
    graph runtime.
    """
    from src.agents.auditor_agent import AuditorAgent

    logger.info(f"[AUDITOR] Processing {state.get('vector_id')}")

    # Only run auditor if there's a draft report
    draft_report = state.get("draft_report", "")
    if not draft_report:
        logger.warning("[AUDITOR] No draft report to audit, skipping")
        return state

    agent = AuditorAgent()
    # FIX 85: Use invoke() instead of process() for proper tracing
    state = agent.invoke(state)

    # Log audit results
    audit_result = state.get("audit_result", {})
    faithfulness = state.get("post_hoc_faithfulness", 0)
    revision_required = audit_result.get("revision_required", False)

    # FIX 21: Increment revision counter inside the node (not in routing function)
    # This ensures the counter is properly persisted in the graph state.
    revision_count = state.get("auditor_revision_count", 0)
    if revision_required:
        state["auditor_revision_count"] = revision_count + 1
        logger.info(
            f"[AUDITOR] Revision count incremented: {revision_count} -> {revision_count + 1}"
        )

    # =========================================================================
    # FIX 117/126B: Track faithfulness history for convergence detection
    # MUST be in node function (not routing function) for state persistence.
    # See FIX 21 comment: LangGraph routing functions are read-only.
    # FIX-126B: Removed citefirst gate - convergence detection must work for
    # ALL synthesis paths, not just citefirst. Without this, the non-citefirst
    # path has no convergence escape and loops until max_revisions.
    # =========================================================================
    import os
    if faithfulness >= 0:
        faithfulness_history = state.get("faithfulness_history", [])
        faithfulness_history.append(faithfulness)
        state["faithfulness_history"] = faithfulness_history

        convergence_threshold = float(os.environ.get("POLARIS_CONVERGENCE_THRESHOLD", "0.01"))
        target_faithfulness = float(os.environ.get("POLARIS_TARGET_FAITHFULNESS", "0.90"))
        current_revision_count = state.get("auditor_revision_count", 0)

        if len(faithfulness_history) >= 2:
            previous_faithfulness = faithfulness_history[-2]
            improvement = faithfulness - previous_faithfulness

            if faithfulness >= target_faithfulness:
                state["convergence_detected"] = True
                state["convergence_reason"] = f"Target faithfulness achieved: {faithfulness:.1%} >= {target_faithfulness:.0%}"
            elif improvement < convergence_threshold and current_revision_count >= 2:
                state["convergence_detected"] = True
                state["convergence_reason"] = f"Convergence detected: improvement {improvement:.2%} < {convergence_threshold:.0%}"
            elif improvement < 0 and current_revision_count >= 2:
                state["convergence_detected"] = True
                state["convergence_reason"] = f"Regression detected: {previous_faithfulness:.1%} -> {faithfulness:.1%}"

            if state.get("convergence_detected"):
                logger.info(f"[FIX 126B] {state['convergence_reason']}")

        # FIX-126C: Detect revision deadlock from consecutive revision rejections.
        # When FIX 54 rejects revisions (word count drop), the same report gets
        # re-audited. Score oscillation due to LLM non-determinism can prevent
        # convergence detection. Track rejections explicitly.
        revision_rejected_count = state.get("revision_rejected_count", 0)
        if revision_rejected_count >= 2 and current_revision_count >= 2:
            if not state.get("convergence_detected"):
                state["convergence_detected"] = True
                state["convergence_reason"] = (
                    f"Revision deadlock: {revision_rejected_count} consecutive revisions "
                    f"rejected by word count/citation safeguards"
                )
                logger.warning(f"[FIX-126C] {state['convergence_reason']}")

    logger.info(
        f"[AUDITOR] Post-hoc faithfulness: {faithfulness:.1%}, "
        f"revision_required: {revision_required}"
    )

    # If revision is required, log the unfaithful sentences
    if revision_required:
        sentences_to_revise = state.get("sentences_to_revise", [])
        logger.warning(
            f"[AUDITOR] {len(sentences_to_revise)} sentences flagged for revision"
        )
        for i, item in enumerate(sentences_to_revise[:3]):  # Log first 3
            logger.warning(f"[AUDITOR] Unfaithful #{i+1}: {item.get('sentence', '')[:100]}...")

    # O3 PARITY: Record reasoning step for auditor
    state = record_agent_reasoning_step(
        state, "auditor", "verified_report_faithfulness",
        confidence=faithfulness,
        outcome="success" if faithfulness >= 0.7 else ("partial" if faithfulness >= 0.5 else "failure"),
        metadata={"faithfulness": faithfulness, "revision_required": revision_required}
    )

    save_state(state, "after_auditor")
    return state


# =============================================================================
# OpenAI o3 Parity: Dynamic Re-Planning Node
# =============================================================================

def dynamic_replan_node(state: ResearchState) -> ResearchState:
    """
    OpenAI o3 Parity: Dynamic re-planning node.

    Evaluates whether the research direction should be changed based on:
    - Contradictions in evidence
    - Unexpected findings requiring investigation
    - Critical knowledge gaps
    - Evidence saturation

    If a replan is triggered, generates adaptive queries and marks state
    for routing back to planner.
    """
    logger.info(f"[REPLAN] Evaluating research direction for {state.get('vector_id')}")

    replanner = get_dynamic_replanner()
    reasoning_ctx = get_reasoning_context()

    # Check if replan is needed
    decision = replanner.should_replan(state)

    # Record reasoning step (guarded — src.reasoning may not exist)
    if reasoning_ctx is not None and ReasoningStep is not None:
        try:
            step = ReasoningStep.create(
                agent="dynamic_replanner",
                action=f"Evaluated replan: trigger={decision.trigger.value}, should_replan={decision.should_replan}",
                confidence=decision.confidence,
                outcome="success" if not decision.should_replan else "partial",
                evidence_count=len(state.get("evidence_chain", [])),
                quality_score=state.get("post_hoc_faithfulness", 0.0),
                gaps_identified=len(state.get("gaps", [])),
            )
            reasoning_ctx.add_step(step)

            # Update state with reasoning context
            state["reasoning_context"] = reasoning_ctx.to_dict()
            state["reasoning_backtrack_count"] = reasoning_ctx.backtrack_count
            state["reasoning_current_branch"] = reasoning_ctx.current_branch
            state["reasoning_dead_ends"] = reasoning_ctx.dead_ends
        except Exception as e:
            logger.error(f"[REPLAN] Failed to record reasoning step: {e}")

    if decision.should_replan:
        logger.info(
            f"[REPLAN] Triggering replan: {decision.trigger.value} - {decision.reason}"
        )
        # Execute replan (adds adaptive queries to state)
        state = replanner.execute_replan(decision, state)

        # Store replan decision for routing
        state["_replan_triggered"] = True
        state["_replan_reason"] = decision.reason
        state["_replan_focus"] = decision.suggested_focus
    else:
        logger.info(f"[REPLAN] No replan needed: {decision.reason}")
        state["_replan_triggered"] = False

    save_state(state, "after_replan")
    return state


def route_after_dynamic_replan(state: ResearchState) -> str:
    """
    Route after dynamic replan evaluation.

    If replan was triggered, route back to planner.
    Otherwise, proceed to finalize.
    """
    replan_triggered = state.get("_replan_triggered", False)

    if replan_triggered:
        logger.info("[ROUTE] Replan triggered, routing back to planner")
        return "planner"
    else:
        logger.info("[ROUTE] No replan needed, proceeding to finalize")
        return "finalize"


def finalize_node(state: ResearchState) -> ResearchState:
    """Finalize node - packages final report and consolidates memory."""
    logger.info(f"[FINALIZE] Completing {state.get('vector_id')}")

    # ==========================================================================
    # FIX 80: Citation Binding & Counting
    # ==========================================================================
    # The bug: previously counted state["citations"] which was empty.
    # Now we: 1) Extract [CITE:xxx] tokens, 2) Bind to [1], [2], 3) Save bound text

    draft_report = state.get("draft_report", "")
    vector_id = state.get("vector_id", "unknown")

    # ==========================================================================
    # FIX-133B: Defense-in-depth stripping of internal markers
    # ==========================================================================
    # Even though FIX-133A removes the source of [REVISION_HEDGED], we strip
    # all internal markers here as a safety net before citation binding.
    if draft_report:
        _internal_markers = [
            r"\[REVISION_HEDGED\]",
            r"\[PARTIAL_SUPPORT:[^\]]*\]",
            r"\[UNGROUNDED\]",
        ]
        markers_found = 0
        for marker_pat in _internal_markers:
            matches = re.findall(marker_pat, draft_report)
            if matches:
                markers_found += len(matches)
                draft_report = re.sub(marker_pat, "", draft_report)
        if markers_found > 0:
            # Clean up double spaces left by marker removal
            draft_report = re.sub(r"  +", " ", draft_report)
            state["draft_report"] = draft_report
            logger.warning(
                f"[FIX-133B] Stripped {markers_found} internal markers from report"
            )

    # ==========================================================================
    # FIX-139: Final-pass report cleanup — strip pipeline artifacts
    # ==========================================================================
    # Catches evidence IDs, source quotes, prompt echoes, and procedural
    # language that survived upstream sanitization.
    if draft_report:
        # FIX-149E: Warn about empty cite tokens before stripping
        empty_cite_count = len(re.findall(r'\[CITE:\s*\]', draft_report))
        if empty_cite_count > 0:
            logger.warning(
                f"[FIX-149E] Detected {empty_cite_count} empty [CITE:] "
                f"token(s) in draft report before final cleanup"
            )

        _fix139_patterns = [
            # FIX-149D: Empty cite tokens (e.g., [CITE:], [CITE: ])
            (r'\[CITE:\s*\]', ''),
            # Evidence ID artifacts (e.g., ev_atomic_abc123, chunk_atomic_xyz)
            # FIX-162F: Negative lookbehind (?<!CITE:) preserves IDs inside
            # [CITE:ev_xxx] tokens — those are the citation system, not artifacts.
            (r"(?<!CITE:)\bev_atomic_[a-f0-9]+\b", ""),
            (r"(?<!CITE:)\bev_\w{3,40}\b", ""),
            (r"(?<!CITE:)\bchunk_atomic_\w+\b", ""),
            # FIX-169: Double-double quote patterns (MUST come BEFORE single-double)
            (r'Source quote:\s*""[^"]*""', ''),
            (r'""[^"]{0,500}""', ''),
            # Source quote artifacts from evidence enrichment (FIX-113)
            (r'\.\s*Source quote:\s*"[^"]{0,500}"', "."),
            (r'Source quote:\s*"[^"]{0,500}"\.?\s*', ""),
            # Prompt template echoes
            (r"Attempt\s+\d+\s*[-—:]\s*", ""),
            (r"\bthe claim to express\b", ""),
            (r"\bthe original sentence\b", ""),
            (r"\bmore faithful\b", ""),
            (r"\bthe rewrite\b", ""),
            (r"\bevidence descriptions?\b", ""),
        ]
        fix139_total = 0
        for pattern, replacement in _fix139_patterns:
            matches = re.findall(pattern, draft_report, re.IGNORECASE)
            if matches:
                fix139_total += len(matches)
                draft_report = re.sub(
                    pattern, replacement, draft_report, flags=re.IGNORECASE
                )
        if fix139_total > 0:
            # Clean up artifacts from removal: double spaces, empty parentheses
            draft_report = re.sub(r"  +", " ", draft_report)
            draft_report = re.sub(r"\(\s*\)", "", draft_report)
            draft_report = re.sub(r"\s+\.", ".", draft_report)
            draft_report = re.sub(r"\s+,", ",", draft_report)
            state["draft_report"] = draft_report
            logger.warning(
                f"[FIX-139] Final-pass cleanup stripped {fix139_total} "
                f"pipeline artifacts from report"
            )

    # Build citation registry from evidence chain
    evidence_chain = state.get("evidence_chain", [])
    registry = CitationRegistry(vector_id=vector_id)

    # Populate registry with evidence metadata
    for evidence in evidence_chain:
        if hasattr(evidence, "model_dump"):
            ev_dict = evidence.model_dump()
        elif isinstance(evidence, dict):
            ev_dict = evidence
        else:
            continue

        evidence_id = ev_dict.get("evidence_id", ev_dict.get("chunk_id", ""))
        if evidence_id:
            from src.utils.citation_registry import CitationSource
            # FIX-180C: Title fallback — use evidence title, or extract from text
            ev_title = ev_dict.get("title", "")
            if not ev_title:
                ev_text = ev_dict.get("text", "") or ""
                if ev_text:
                    # Extract first sentence as title, capped at 100 chars
                    first_sentence_match = re.match(r'[^.!?]+[.!?]', ev_text)
                    if first_sentence_match:
                        ev_title = first_sentence_match.group(0).strip()[:100]
                    else:
                        ev_title = ev_text[:100].strip()
            # FIX-227: Pipe author metadata from Evidence to CitationSource
            ev_authors = ev_dict.get("authors", [])
            # FIX-227A: Defensive type check — Serper Scholar may return string
            if isinstance(ev_authors, str):
                ev_authors = [a.strip() for a in ev_authors.split(",") if a.strip()] if ev_authors else []
            author_str = ""
            if ev_authors:
                author_str = ", ".join(ev_authors[:3])
                if len(ev_authors) > 3:
                    author_str += " et al."

            # FIX-273: Extract publication date from URL path or evidence text.
            # CrossRef only works for DOI URLs; most web sources lack DOIs.
            ev_pub_date = ""
            ev_url = ev_dict.get("source_url", "") or ""
            # Try URL path: /2024/01/... or /2023-05-... patterns
            url_year_match = re.search(r'/(\d{4})/(\d{1,2})/', ev_url)
            if url_year_match:
                year_val = int(url_year_match.group(1))
                if 1990 <= year_val <= 2030:
                    ev_pub_date = f"{year_val}"
            if not ev_pub_date:
                url_year_match = re.search(r'/(\d{4})[-/]', ev_url)
                if url_year_match:
                    year_val = int(url_year_match.group(1))
                    if 1990 <= year_val <= 2030:
                        ev_pub_date = f"{year_val}"
            # Try evidence text: "published in 2023" or "(2022)" patterns
            if not ev_pub_date:
                ev_text = ev_dict.get("text", "") or ""
                text_year_match = re.search(
                    r'(?:published|updated|dated|copyright|\()\s*(?:in\s+)?(\d{4})\b',
                    ev_text[:500], re.IGNORECASE
                )
                if text_year_match:
                    year_val = int(text_year_match.group(1))
                    if 1990 <= year_val <= 2030:
                        ev_pub_date = f"{year_val}"

            source = CitationSource(
                chunk_id=evidence_id,
                url=ev_url,
                title=ev_title,
                author=author_str,  # FIX-227
                publication_date=ev_pub_date,  # FIX-273
                snippet=ev_dict.get("text", "")[:300] if ev_dict.get("text") else "",
                source_type="web",
            )
            registry.sources[evidence_id] = source

    # FIX-180B: Wire CrossRef enrichment for bibliography metadata
    try:
        max_crossref = int(os.environ.get("POLARIS_MAX_CROSSREF_ENRICHMENT", "50"))
        enriched_count = registry.enrich_from_crossref(max_citations=max_crossref)
        if enriched_count > 0:
            logger.info(f"[FIX-180B] CrossRef enriched {enriched_count} citations with metadata")
    except Exception as e:
        logger.warning(f"[FIX-180B] CrossRef enrichment failed (non-fatal): {e}")

    # FIX-183B: Normalize citation tokens before extraction
    draft_report = normalize_cite_tokens(draft_report)

    # Extract citation IDs from draft report
    cite_pattern = r'\[CITE:([^\]]+)\]'
    cited_ids = re.findall(cite_pattern, draft_report)
    unique_cited_ids = list(dict.fromkeys(cited_ids))  # Preserve order, remove duplicates

    logger.info(f"[FIX 80] Found {len(cited_ids)} total citations ({len(unique_cited_ids)} unique) in report")

    # FIX-178B: Strip unknown/placeholder citation IDs
    known_ids = set(registry.sources.keys())
    unknown_stripped = 0
    for cite_id in list(unique_cited_ids):
        if cite_id not in known_ids:
            logger.warning(f"[FIX-178B] Unknown citation stripped: {cite_id}")
            draft_report = draft_report.replace(f"[CITE:{cite_id}]", "")
            unknown_stripped += 1
    if unknown_stripped > 0:
        # Re-extract after stripping
        cited_ids = re.findall(cite_pattern, draft_report)
        unique_cited_ids = list(dict.fromkeys(cited_ids))
        logger.info(
            f"[FIX-178B] Stripped {unknown_stripped} unknown citations, "
            f"{len(unique_cited_ids)} valid citations remain"
        )

    # FIX 80.1: RECOVERY - If LLM used [N] format instead of [CITE:xxx], try to map them
    if not cited_ids:
        numeric_pattern = r'\[(\d+)\]'
        numeric_citations = re.findall(numeric_pattern, draft_report)
        if numeric_citations:
            logger.warning(f"[FIX 80.1] RECOVERY: LLM used [N] format ({len(numeric_citations)} citations) instead of [CITE:xxx]")

            # Build mapping from [N] to evidence_id based on order
            # Assume [1] = first evidence, [2] = second, etc.
            evidence_ids_ordered = list(registry.sources.keys())
            n_to_cite_map = {}
            for n in sorted(set(int(x) for x in numeric_citations)):
                if 1 <= n <= len(evidence_ids_ordered):
                    n_to_cite_map[n] = evidence_ids_ordered[n - 1]

            # Convert [N] -> [CITE:xxx] in draft report
            def replace_numeric(match):
                n = int(match.group(1))
                if n in n_to_cite_map:
                    return f"[CITE:{n_to_cite_map[n]}]"
                return match.group(0)

            draft_report = re.sub(numeric_pattern, replace_numeric, draft_report)

            # Re-extract citations after conversion
            cited_ids = re.findall(cite_pattern, draft_report)
            unique_cited_ids = list(dict.fromkeys(cited_ids))
            logger.info(f"[FIX 80.1] RECOVERY: Converted {len(n_to_cite_map)} numeric citations to [CITE:xxx] format")

    # Bind citations: [CITE:ev_xxx] -> [1], [2], etc.
    if cited_ids:
        bound_text, bibliography = registry.bind_citations(draft_report, format_style="numbered")

        # FIX-183E: Post-bind orphan audit — verify every [N] has a bibliography entry
        bib_numbers = {entry["number"] for entry in bibliography}
        numeric_refs = set(int(n) for n in re.findall(r'\[(\d+)\]', bound_text))
        orphan_refs = numeric_refs - bib_numbers
        if orphan_refs:
            logger.warning(f"[FIX-183E] {len(orphan_refs)} orphan [N] refs, stripping")
            for n in orphan_refs:
                bound_text = bound_text.replace(f"[{n}]", "")
            bound_text = re.sub(r'\s{2,}', ' ', bound_text)
        state["citation_orphans"] = len(orphan_refs) if orphan_refs else 0

        state["final_report"] = bound_text
        state["bibliography"] = bibliography
        state["final_citation_count"] = len(unique_cited_ids)
        logger.info(f"[FIX 80] Bound {len(bibliography)} citations to numbered format")
    else:
        state["final_report"] = draft_report
        state["bibliography"] = []
        state["final_citation_count"] = 0
        logger.warning("[FIX 80] No [CITE:xxx] tokens found in report (even after recovery attempt)")

    # FIX-267: Use alphanumeric word count consistent with audit D1/D8 measurement.
    # Previously used split() which counts markdown artifacts (##, ---, *) as words,
    # inflating count vs audit's re.findall(r"[a-z0-9]+") method.
    state["final_word_count"] = len(re.findall(r"[a-z0-9]+", state["final_report"].lower()))

    # ==========================================================================
    # FIX-131: Calculate Perspective Coverage on CITED Evidence (Refines FIX-127)
    # ==========================================================================
    # We must grade the REPORT, not the SEARCH PILE.
    #
    # FIX-129 balances the input evidence chain (caps dominant perspectives),
    # so measuring entropy on the full chain yields a tautologically high score.
    # Instead, we filter the chain to ONLY evidence actually cited in the report,
    # then compute normalized Shannon entropy on that cited subset.
    #
    # This ensures the gating metric reflects what the LLM actually wrote about,
    # not what was available to it.
    # ==========================================================================
    evidence_chain = state.get("evidence_chain", [])

    # Step 1: Build set of cited evidence IDs from the report
    # unique_cited_ids was already extracted from draft_report above (line ~1774)
    cited_id_set = set(unique_cited_ids) if unique_cited_ids else set()

    # Step 2: Filter evidence chain to cited items only
    if cited_id_set:
        cited_evidence = []
        for ev in evidence_chain:
            ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
            e_id = str(ev_dict.get("evidence_id", ""))
            e_uuid = str(ev_dict.get("id", ""))
            if e_id in cited_id_set or e_uuid in cited_id_set:
                cited_evidence.append(ev)

        if not cited_evidence:
            # Fallback: citation IDs don't match evidence chain (format mismatch)
            logger.warning(
                f"[FIX-131] No evidence matched {len(cited_id_set)} cited IDs, "
                f"falling back to full chain ({len(evidence_chain)} items)"
            )
            cited_evidence = evidence_chain
        else:
            logger.info(
                f"[FIX-131] Filtered evidence: {len(evidence_chain)} total -> "
                f"{len(cited_evidence)} cited in report"
            )
    else:
        # No citations found — use full chain as fallback
        cited_evidence = evidence_chain

    # Step 3: Count perspectives on CITED evidence only
    perspective_counts_for_gating = {}
    for ev in cited_evidence:
        ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
        perspectives = ev_dict.get("perspective_origins", [])
        for p in perspectives:
            perspective_counts_for_gating[p] = perspective_counts_for_gating.get(p, 0) + 1

    # Step 4: Compute Normalized Shannon Entropy (FIX-127)
    if perspective_counts_for_gating:
        perspective_values = list(perspective_counts_for_gating.values())
        total_cited_perspectives = sum(perspective_values)
        storm_perspective_count = 9  # Fixed: 9 STORM perspectives
        if total_cited_perspectives > 0 and len(perspective_counts_for_gating) > 1:
            probs = [count / total_cited_perspectives for count in perspective_values]
            entropy = -sum(p * math.log(p) for p in probs if p > 0)
            max_entropy = math.log(storm_perspective_count)
            balance_score_calc = entropy / max_entropy if max_entropy > 0 else 0.0
        else:
            balance_score_calc = 0.0

        state["perspective_coverage"] = {
            "perspectives_represented": len(perspective_counts_for_gating),
            "distribution": perspective_counts_for_gating,
            "dominant_perspective": max(perspective_counts_for_gating, key=perspective_counts_for_gating.get),
            "balance_score": balance_score_calc,
            "balance_metric": "normalized_shannon_entropy_cited",  # FIX-131: On cited evidence
            "total_perspective_tagged": total_cited_perspectives,
            "total_evidence_in_chain": len(evidence_chain),
            "cited_evidence_count": len(cited_evidence),
        }
        logger.info(
            f"[FIX-131] Cited perspective stats: {len(perspective_counts_for_gating)} perspectives, "
            f"entropy={balance_score_calc:.3f} (on {len(cited_evidence)} cited evidence, "
            f"not {len(evidence_chain)} total)"
        )
    else:
        state["perspective_coverage"] = {
            "perspectives_represented": 0,
            "distribution": {},
            "dominant_perspective": None,
            "balance_score": 0.0,
            "total_perspective_tagged": 0,
            "total_evidence_in_chain": len(evidence_chain),
            "cited_evidence_count": 0,
        }

    # FIX-247: Write immune faithfulness key that Phase 4 cannot overwrite
    pipeline_faith = state.get("post_hoc_faithfulness", 0)
    if pipeline_faith > 0:
        state["pipeline_faithfulness"] = pipeline_faith
        logger.info(f"[FIX-247] pipeline_faithfulness={pipeline_faith:.3f} (immune key)")

    # Determine confidence band
    # FIX 13: Prefer Auditor's measured faithfulness (ground truth) over Critic's estimate
    faithfulness = state.get("post_hoc_faithfulness", 0)
    if faithfulness == 0:
        # Fallback to Critic's estimate if Auditor didn't run
        quality = state.get("quality_metrics", {})
        faithfulness = quality.get("faithfulness", 0) if isinstance(quality, dict) else getattr(quality, "faithfulness", 0)
    logger.info(f"[FINALIZE] Faithfulness for gating: {faithfulness:.3f} (source: {'auditor' if state.get('post_hoc_faithfulness', 0) > 0 else 'critic'})")

    if faithfulness >= 0.8:
        state["confidence_band"] = "high"
        state["gating_case"] = "CASE_1"
    elif faithfulness >= 0.6:
        state["confidence_band"] = "medium"
        state["gating_case"] = "CASE_2"
    else:
        state["confidence_band"] = "low"
        state["gating_case"] = "CASE_3"

    # ==========================================================================
    # FIX-168: Word Count + Citation Count Quality Gates
    # ==========================================================================
    min_report_words = int(os.environ.get("POLARIS_MIN_REPORT_WORDS", "2000"))
    min_report_citations = int(os.environ.get("POLARIS_MIN_REPORT_CITATIONS", "5"))
    report_word_count = state.get("final_word_count", len(draft_report.split()) if draft_report else 0)
    report_citation_count = state.get("final_citation_count", len(unique_cited_ids) if unique_cited_ids else 0)

    quality_gates = {
        "word_count": report_word_count,
        "word_count_threshold": min_report_words,
        "word_count_passed": report_word_count >= min_report_words,
        "citation_count": report_citation_count,
        "citation_count_threshold": min_report_citations,
        "citation_count_passed": report_citation_count >= min_report_citations,
    }

    if not quality_gates["word_count_passed"]:
        if state["gating_case"] == "CASE_1":
            state["gating_case"] = "CASE_2"
            state["confidence_band"] = "medium"
        elif state["gating_case"] == "CASE_2":
            state["gating_case"] = "CASE_3"
            state["confidence_band"] = "low"
        logger.warning(
            f"[FIX-168] Word count gate FAILED: {report_word_count} < {min_report_words}, "
            f"downgraded to {state['gating_case']}"
        )

    if not quality_gates["citation_count_passed"]:
        if state["gating_case"] == "CASE_1":
            state["gating_case"] = "CASE_2"
            state["confidence_band"] = "medium"
        elif state["gating_case"] == "CASE_2":
            state["gating_case"] = "CASE_3"
            state["confidence_band"] = "low"
        logger.warning(
            f"[FIX-168] Citation count gate FAILED: {report_citation_count} < {min_report_citations}, "
            f"downgraded to {state['gating_case']}"
        )

    state["quality_gates"] = quality_gates
    if quality_gates["word_count_passed"] and quality_gates["citation_count_passed"]:
        logger.info(
            f"[FIX-168] Quality gates PASSED: words={report_word_count}, "
            f"citations={report_citation_count}"
        )

    # ==========================================================================
    # FIX-124F: STORM Perspective Balance Gating
    # ==========================================================================
    # CASE_1 requires perspective diversity. A report dominated by a single
    # perspective is incomplete regardless of faithfulness score.
    perspective_coverage = state.get("perspective_coverage", {})
    balance_score = perspective_coverage.get("balance_score", 1.0)
    perspectives_count = perspective_coverage.get("perspectives_represented", 0)

    # ==========================================================================
    # FIX-127: Recalibrated Gating Thresholds (Normalized Shannon Entropy)
    # ==========================================================================
    # Old thresholds (min/max): CASE_1 >= 0.30, CASE_2 >= 0.10
    # New thresholds (entropy): CASE_1 >= 0.55, CASE_2 >= 0.35
    #
    # Rationale: Run #6 had 7 perspectives with entropy ~0.72, which correctly
    # represents genuine multi-perspective coverage. The old min/max formula
    # gave 0.02 for the same distribution.
    #
    # Entropy reference points:
    #   9 uniform perspectives: 1.00
    #   7 perspectives (natural imbalance): ~0.70-0.85
    #   3 perspectives (poor coverage): ~0.40-0.50
    #   1 perspective (no diversity): 0.00

    original_case = state["gating_case"]
    if state["gating_case"] == "CASE_1":
        if balance_score < 0.55 or perspectives_count < 3:
            state["gating_case"] = "CASE_2"
            state["confidence_band"] = "medium"
            logger.warning(
                f"[FIX-127] Downgraded CASE_1 -> CASE_2: entropy={balance_score:.3f}, "
                f"perspectives={perspectives_count} (requires entropy>=0.55, perspectives>=3)"
            )

    if state["gating_case"] == "CASE_2":
        if balance_score < 0.35 or perspectives_count < 2:
            state["gating_case"] = "CASE_3"
            state["confidence_band"] = "low"
            logger.warning(
                f"[FIX-127] Downgraded CASE_2 -> CASE_3: entropy={balance_score:.3f}, "
                f"perspectives={perspectives_count} (requires entropy>=0.35, perspectives>=2)"
            )

    if original_case != state["gating_case"]:
        logger.info(f"[FIX-127] Final gating: {original_case} -> {state['gating_case']} (STORM entropy enforcement)")
    else:
        logger.info(f"[FIX-127] Gating maintained: {state['gating_case']} (entropy={balance_score:.3f} passed)")

    # ==========================================================================
    # FIX-138C: Output Quality Gate
    # ==========================================================================
    # Check report for readability issues (CoT leakage, markers, duplicates, PDF noise).
    # If OQG fails AND current case is CASE_1, downgrade to CASE_2.
    try:
        final_report_for_oqg = state.get("final_report", "") or state.get("draft_report", "")
        if final_report_for_oqg:
            # FIX-144: Repair artifacts BEFORE quality measurement
            repaired_report = repair_output_quality(final_report_for_oqg)
            if repaired_report != final_report_for_oqg:
                # Write repaired text back to state
                if state.get("final_report"):
                    state["final_report"] = repaired_report
                else:
                    state["draft_report"] = repaired_report
                final_report_for_oqg = repaired_report

            # FIX-176: Chain CoT scrubber after repair_output_quality
            scrubbed_report = scrub_cot_from_report(final_report_for_oqg)
            if scrubbed_report != final_report_for_oqg:
                if state.get("final_report"):
                    state["final_report"] = scrubbed_report
                else:
                    state["draft_report"] = scrubbed_report
                final_report_for_oqg = scrubbed_report

            # FIX-211: LLM post-filter for CoT lines that survive regex
            # FIX-229: Skip when FIX-220 structural separation is active (LITE mode).
            # FIX-211 is redundant with structural CoT separation and can false-positive
            # on legitimate short prose, causing content destruction.
            cot_lite_active = os.environ.get("POLARIS_COT_SCRUBBER_LITE", "0") == "1"
            kimi_fallback_count = state.get("kimi_fallback_count", 0)
            if cot_lite_active and kimi_fallback_count == 0:
                logger.info("[FIX-229] Skipping FIX-211 LLM post-filter (structural separation active, 0 fallbacks)")
            else:
                if kimi_fallback_count > 0:
                    logger.warning(f"[FIX-229] Running FIX-211 LLM post-filter ({kimi_fallback_count} KimiClient fallbacks detected)")
                from src.utils.cot_post_filter import create_default_llm_invoke
                llm_invoke_fn = create_default_llm_invoke()
                if llm_invoke_fn:
                    query_for_filter = state.get("original_query", state.get("vector_id", ""))
                    filtered_report = cot_post_filter_report(
                        final_report_for_oqg, query_for_filter, llm_invoke=llm_invoke_fn,
                    )
                    if filtered_report != final_report_for_oqg:
                        if state.get("final_report"):
                            state["final_report"] = filtered_report
                        else:
                            state["draft_report"] = filtered_report
                        final_report_for_oqg = filtered_report

            oqg_result = check_output_quality(final_report_for_oqg)
            state["output_quality_gate"] = {
                "passed": oqg_result.passed,
                "score": oqg_result.score,
                "cot_count": oqg_result.cot_count,
                "marker_count": oqg_result.marker_count,
                "duplicate_count": oqg_result.duplicate_count,
                "pdf_noise_count": oqg_result.pdf_noise_count,
                "total_sentences": oqg_result.total_sentences,
                "issues": [
                    {"category": i.category, "severity": i.severity, "description": i.description}
                    for i in oqg_result.issues
                ],
            }

            if not oqg_result.passed and state["gating_case"] == "CASE_1":
                state["gating_case"] = "CASE_2"
                state["confidence_band"] = "medium"
                issue_summary = ", ".join(
                    f"{i.category}={i.count}" for i in oqg_result.issues if i.count > 0
                )
                logger.warning(
                    f"[FIX-138C] OQG FAILED (score={oqg_result.score:.1f}), "
                    f"downgrading CASE_1 -> CASE_2: {issue_summary}"
                )
            elif not oqg_result.passed:
                logger.warning(
                    f"[FIX-138C] OQG failed (score={oqg_result.score:.1f}) but "
                    f"gating already {state['gating_case']}, no further downgrade"
                )
    except Exception as e:
        # FIX-212 P0: OQG crash must NOT be masked as passed=True (LAW II violation)
        logger.error(f"[FIX-212] Output quality gate CRASHED: {e}")
        state["output_quality_gate"] = {"passed": False, "score": 0, "error": str(e), "crashed": True}
        # Downgrade CASE_1 since we can't verify quality
        if state.get("gating_case") == "CASE_1":
            state["gating_case"] = "CASE_2"
            state["confidence_band"] = "medium"
            logger.warning("[FIX-212] OQG crash forced CASE_1 -> CASE_2 downgrade")

    # ==========================================================================
    # FIX 70: Memory Consolidation (LTM Promotion)
    # ==========================================================================
    # If CASE_1 (high quality), promote verified evidence to LTM for future vectors
    if state["gating_case"] == "CASE_1":
        try:
            vector_id = state.get("vector_id", "unknown")
            stage = state.get("stage", 1)
            region = state.get("region", "NORTH_AMERICA")

            logger.info(f"[MEMORY] CASE_1 achieved - promoting evidence to LTM")

            chroma = get_chroma_manager()

            # Collect GOLD/SILVER evidence for LTM-Stage promotion
            evidence_chain = state.get("evidence_chain", [])
            documents_to_promote = []

            for evidence in evidence_chain:
                # Handle both dict and Pydantic model
                if hasattr(evidence, "model_dump"):
                    evidence = evidence.model_dump()
                elif not isinstance(evidence, dict):
                    continue

                # FIX 77: Cannibal Loop Protection
                # Skip evidence that came from LTM to prevent recursive promotion
                # (ltm_s_xxx = stage recall, ltm_g_xxx = global recall)
                evidence_id = str(evidence.get("evidence_id", ""))
                extraction_method = evidence.get("extraction_method", "")
                if evidence_id.startswith("ltm_") or extraction_method in ["ltm_stage_recall", "ltm_global_recall"]:
                    logger.debug(f"[FIX 77] Skipping LTM evidence {evidence_id} (prevent cannibal loop)")
                    continue

                quality_tier = evidence.get("quality_tier", "UNVERIFIED")
                if quality_tier in ["GOLD", "SILVER"]:
                    documents_to_promote.append({
                        "id": evidence.get("evidence_id", evidence.get("chunk_id", "unknown")),
                        "content": evidence.get("text", ""),
                        "metadata": {
                            "quality_tier": quality_tier,
                            "relevance_score": evidence.get("relevance_score", 0),
                            "source_url": evidence.get("source_url", ""),
                            "source_quality_score": evidence.get("source_quality_score", 0),
                        }
                    })

            # Promote to LTM-Stage
            if documents_to_promote:
                ltm_stage_promoted = chroma.promote_documents_to_ltm_stage(
                    vector_id=vector_id,
                    stage=stage,
                    region=region,
                    documents=documents_to_promote,
                )
                state["ltm_stage_promoted"] = ltm_stage_promoted
                logger.info(
                    f"[MEMORY] Promoted {ltm_stage_promoted} documents to "
                    f"LTM-Stage {stage} ({region})"
                )

                # Promote high-quality LTM-Stage content to LTM-Global
                ltm_global_promoted = chroma.promote_to_ltm_global(
                    stage=stage,
                    region=region,
                    quality_threshold=0.7,
                )
                state["ltm_global_promoted"] = ltm_global_promoted
                logger.info(f"[MEMORY] Promoted {ltm_global_promoted} documents to LTM-Global")
            else:
                logger.warning("[MEMORY] No GOLD/SILVER evidence to promote")
                state["ltm_stage_promoted"] = 0
                state["ltm_global_promoted"] = 0

            # Cleanup VWM (working memory no longer needed)
            chroma.cleanup_vwm(vector_id)
            logger.debug(f"[MEMORY] VWM cleaned up for {vector_id}")

        except Exception as e:
            logger.error(f"[MEMORY] Memory consolidation failed: {e}")
            state["ltm_stage_promoted"] = 0
            state["ltm_global_promoted"] = 0
            state = record_error(state, "memory_consolidation", e)
    else:
        # Non-CASE_1: Don't promote to LTM (quality not sufficient)
        state["ltm_stage_promoted"] = 0
        state["ltm_global_promoted"] = 0
        logger.info(f"[MEMORY] Skipping LTM promotion ({state['gating_case']} - quality insufficient)")

    # ==========================================================================
    # SOTA Integration: Multi-Format Output Generation (Task #21)
    # ==========================================================================
    try:
        final_report = state.get("final_report", "")
        if final_report and OutputFormatter is not None:
            formatter = OutputFormatter()

            # Generate HTML version
            html_report = formatter.format(final_report, OutputFormat.HTML)
            state["report_html"] = html_report

            # Generate executive summary
            executive_summary = formatter.format(final_report, OutputFormat.EXECUTIVE)
            state["report_executive"] = executive_summary

            # Generate structured JSON
            json_report = formatter.format(final_report, OutputFormat.JSON)
            state["report_json"] = json_report

            logger.info(f"[FORMAT] Generated multi-format outputs: HTML, Executive, JSON")
    except Exception as e:
        logger.warning(f"[FORMAT] Multi-format generation failed: {e}")

    # ==========================================================================
    # SOTA Integration: Visual Statistics Generation (Task #21)
    # ==========================================================================
    try:
        evidence_chain = state.get("evidence_chain", [])
        if evidence_chain:
            visual_gen = VisualGenerator()

            # Create source quality distribution chart
            quality_tiers = {}
            for ev in evidence_chain:
                ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else ev if isinstance(ev, dict) else {}
                tier = ev_dict.get("quality_tier", "UNKNOWN")
                quality_tiers[tier] = quality_tiers.get(tier, 0) + 1

            if quality_tiers:
                labels = list(quality_tiers.keys())
                values = list(quality_tiers.values())
                chart_data = ChartData(labels=labels, values=values, series_name="Evidence Quality")
                quality_chart = visual_gen.create_bar_chart(chart_data, "Evidence Quality Distribution")
                state["visual_quality_chart"] = quality_chart.content

                logger.info(f"[VISUAL] Generated quality distribution chart")

            # ==========================================================================
            # FIX-124D: STORM Perspective Coverage Dashboard (Visual Chart)
            # ==========================================================================
            # Note: perspective_coverage was already calculated before gating (FIX-124F)
            # Here we just generate the visual chart from the existing data
            perspective_info = state.get("perspective_coverage", {})
            perspective_counts = perspective_info.get("distribution", {})

            if perspective_counts:
                perspective_labels = list(perspective_counts.keys())
                perspective_values = list(perspective_counts.values())
                perspective_chart_data = ChartData(
                    labels=perspective_labels,
                    values=perspective_values,
                    series_name="STORM Perspective Coverage"
                )
                perspective_chart = visual_gen.create_bar_chart(
                    perspective_chart_data,
                    "STORM Perspective Distribution"
                )
                state["visual_perspective_chart"] = perspective_chart.content
                logger.info(f"[FIX-124D] Generated perspective distribution chart")

            # Create summary statistics card (enhanced with perspective data)
            perspective_info = state.get("perspective_coverage", {})
            stats = {
                "Total Evidence": len(evidence_chain),
                "Unique Sources": len(set(
                    (ev.model_dump() if hasattr(ev, "model_dump") else ev).get("source_url", "")
                    for ev in evidence_chain if hasattr(ev, "model_dump") or isinstance(ev, dict)
                )),
                "Citations": state.get("final_citation_count", 0),
                "Word Count": state.get("final_word_count", 0),
                "Faithfulness": f"{state.get('post_hoc_faithfulness', 0)*100:.1f}%",
                "STORM Perspectives": perspective_info.get("perspectives_represented", 0),
                "Perspective Balance": f"{perspective_info.get('balance_score', 0)*100:.0f}%",
            }
            summary_card = visual_gen.create_summary_card(stats, "Research Summary")
            state["visual_summary_card"] = summary_card.content

            logger.info(f"[VISUAL] Generated summary statistics card with perspective data")
    except Exception as e:
        logger.warning(f"[VISUAL] Visual generation failed: {e}")

    # Mark as converged
    state["converged"] = True
    state["convergence_reason"] = "Finalization complete"

    # Final timestamp
    state["timestamps"]["completed"] = datetime.now(UTC).isoformat()

    save_state(state, "final")

    # FIX-124: Include perspective coverage in final summary
    perspective_info = state.get("perspective_coverage", {})
    perspective_count = perspective_info.get("perspectives_represented", 0)
    balance_score = perspective_info.get("balance_score", 0)

    logger.info(
        f"[FINALIZE] Complete: {state.get('gating_case')}, {state.get('confidence_band')} confidence, "
        f"LTM: +{state.get('ltm_stage_promoted', 0)} stage, +{state.get('ltm_global_promoted', 0)} global, "
        f"STORM: {perspective_count} perspectives (balance={balance_score:.0%})"
    )

    return state


# =============================================================================
# Routing Functions
# =============================================================================

def route_after_auditor(state: ResearchState) -> str:
    """
    Route after auditor verification - feedback loop for revision.

    FIX 21 (Gemini Audit FIX 1): This function is now READ-ONLY.
    State mutations (auditor_revision_count increment) are handled in
    auditor_node() to ensure they persist in the LangGraph state.

    Routes back to synthesizer for correction if:
    - revision_required is True AND
    - auditor_revision_count < max_revisions (5)

    FIX 107: Routes to citation_enrichment when faithfulness >= 85%
    to boost citation density after verification passes.

    OpenAI o3 Parity: Routes to dynamic_replan after enrichment.
    """
    import os

    audit_result = state.get("audit_result", {})
    revision_count = state.get("auditor_revision_count", 0)

    # ==========================================================================
    # O3 PARITY: Record reasoning step and check backtracking
    # ==========================================================================
    faithfulness = state.get("post_hoc_faithfulness", 0.5)
    state = check_backtrack_needed(state, "auditor", faithfulness)

    # FIX 43 (Gemini Audit #3): Static Safety Cap
    # FIX 32's dynamic math caused a "Moving Goalpost" bug (cutoff dropped as errors were fixed).
    # We set a hard safety cap of 5 loops, which is sufficient for 15*5 = 75 errors.
    max_revisions = 5
    logger.debug(f"[FIX 43] Static max_revisions: {max_revisions}")

    revision_required = audit_result.get("revision_required", False)
    faithfulness = state.get("post_hoc_faithfulness", 0)

    # ==========================================================================
    # FIX 117 Phase 3.3: Convergence-Based Stopping
    # ==========================================================================
    # Instead of fixed 5 iterations, detect when faithfulness stops improving.
    # This prevents wasted iterations when we've hit a ceiling.
    #
    # Convergence criteria:
    # 1. Faithfulness improvement < 1% from previous revision
    # 2. OR faithfulness >= 90% (target achieved)
    # 3. OR revision count >= max_revisions (safety cap)

    # FIX 117: Convergence detection is computed in auditor_node (not here)
    # because LangGraph routing functions are read-only (state mutations discarded).
    # We only READ the convergence flag here.
    converged = state.get("convergence_detected", False)
    if converged:
        convergence_reason = state.get("convergence_reason", "unknown")
        logger.info(f"[FIX 117] Convergence flag set: {convergence_reason}")
        revision_required = False

    # Route back to synthesizer if revision needed and under limit
    # NOTE: revision_count is already incremented by auditor_node (FIX 21)
    if revision_required and revision_count <= max_revisions:
        logger.info(
            f"[ROUTE] Auditor feedback loop: revision {revision_count}/{max_revisions} "
            f"(faithfulness={faithfulness:.1%})"
        )
        return "synthesizer"

    # ==========================================================================
    # FIX 107J: "AUDITOR TRUST" - Citation Enrichment Routing (Gemini Audit RUN11)
    # ==========================================================================
    # THE METRIC MISMATCH FIX:
    #
    # Problem: The Auditor and Router were speaking different languages.
    # - Auditor uses Soft Pass (FIX 105A-SOFT): 3/5 atoms pass = sentence PASSES
    # - Router uses raw faithfulness: sees 2/5 failed = low score (68.4%)
    # Result: Auditor says "Approved!" but Router says "Block Enrichment!"
    #
    # Solution: TRUST THE AUDITOR.
    # If revision_required is False, the Auditor has signed off on the report.
    # We should ALWAYS enrich an approved report, regardless of raw faithfulness.
    #
    # The only exception is catastrophically low faithfulness (<50%), which
    # indicates something went seriously wrong.
    # ==========================================================================

    enrichment_enabled = os.environ.get("POLARIS_ENRICHMENT_ENABLED", "1") == "1"
    already_enriched = state.get("enrichment_applied", False)

    # CRITICAL: Check if Auditor has approved the report
    # revision_required = False means the Auditor is SATISFIED
    auditor_approved = not revision_required

    # "Fail Open" Logic - Enrich if ANY of these conditions is true:
    # 1. Auditor Approved (revision_required = False) - The Auditor signed off
    # 2. Faithfulness >= 0.70 - Report is fundamentally sound (FIX 108G: raised from 0.60)
    # 3. Hail Mary (revision_count > max_revisions) - Desperation mode
    #
    # FIX 108G: Raised threshold from 0.60 to 0.70 to only enrich fundamentally sound reports.
    # Enriching a 60% faithful report adds citations to potentially hallucinated content.

    hail_mary_triggered = revision_count > max_revisions
    enrichment_faith_threshold = float(os.environ.get("POLARIS_ENRICHMENT_FAITH_THRESHOLD", "0.70"))
    good_enough_faith = faithfulness >= enrichment_faith_threshold

    should_enrich = (
        enrichment_enabled and
        not already_enriched and
        (auditor_approved or good_enough_faith or hail_mary_triggered)
    )

    # Safety floor: Don't enrich catastrophically bad reports (<50%)
    # This catches cases where something went seriously wrong
    if should_enrich and faithfulness < 0.50:
        logger.warning(
            f"[FIX 107J] SAFETY FLOOR: Faithfulness {faithfulness:.1%} < 50% is catastrophic. "
            f"Skipping enrichment despite approval. Report needs fundamental fixes."
        )
        should_enrich = False

    if should_enrich:
        reason = []
        if auditor_approved:
            reason.append("Auditor_Approved")
        if good_enough_faith:
            reason.append(f"Faith>{enrichment_faith_threshold:.0%}({faithfulness:.1%})")
        if hail_mary_triggered:
            reason.append("HailMary")

        logger.info(
            f"[FIX 107J] AUDITOR TRUST: Routing to citation_enrichment "
            f"(reasons={'+'.join(reason)}, faithfulness={faithfulness:.1%}, "
            f"revision_count={revision_count}, auditor_approved={auditor_approved})"
        )
        return "citation_enrichment"

    # OpenAI o3 Parity: Route to dynamic_replan for evaluation
    # This allows adaptive re-planning based on research findings
    if revision_count > max_revisions:
        logger.info(
            f"[ROUTE] Max revisions ({max_revisions}) reached, proceeding to dynamic_replan "
            f"(faithfulness={faithfulness:.1%}, enrichment already applied={already_enriched})"
        )

    return "dynamic_replan"


def route_after_supervisor(state: ResearchState) -> str:
    """Route based on supervisor decision."""
    next_agent = state.get("_next_agent", "finalize")

    # Debug logging
    logger.info(f"[ROUTE] Supervisor routing: _next_agent={next_agent}, keys={list(state.keys())[:10]}")

    # Map agent names to node names
    node_map = {
        "search": "search",
        "analyst": "analyst",
        "verifier": "verifier",
        "synthesizer": "synthesizer",
        "critic": "critic",
        "planner": "planner",
        "finalize": "finalize",
        "halt": "finalize",  # Halt goes to finalize
    }

    result = node_map.get(next_agent, "finalize")
    logger.info(f"[ROUTE] Routing to: {result}")
    return result


def route_after_critic(state: ResearchState) -> str:
    """
    Route after critic evaluation using iteration manager.

    Uses knowledge saturation detection and convergence criteria
    to determine whether to continue iterating or synthesize.

    O3 Parity: Includes backtrack checking based on critic confidence.
    """
    manager = get_iteration_manager()
    iteration = state.get("iteration_count", 0)

    # ==========================================================================
    # O3 PARITY: Check for backtracking based on critic evaluation
    # ==========================================================================
    quality_metrics = state.get("quality_metrics", {})
    if isinstance(quality_metrics, dict):
        critic_confidence = quality_metrics.get("faithfulness", 0.5)
    else:
        critic_confidence = getattr(quality_metrics, "faithfulness", 0.5)

    # Record reasoning step and check for backtrack
    state = check_backtrack_needed(state, "critic", critic_confidence)

    # If we backtracked, we should return to planning to try a different approach
    if state.get("reasoning_backtrack_count", 0) > state.get("_last_backtrack_count", 0):
        state["_last_backtrack_count"] = state.get("reasoning_backtrack_count", 0)
        logger.info("[ROUTE] Backtrack triggered - returning to planner for revised approach")
        return "planner"

    # Update saturation metrics
    novelty = manager.update_saturation(state, iteration)

    # Check if we should continue
    should_continue, reason = manager.should_continue(state, iteration)

    if not should_continue:
        # Mark as converged
        manager.mark_converged(reason)
        state["converged"] = True
        state["convergence_reason"] = reason.value if reason else "unknown"
        state["iteration_summary"] = manager.get_iteration_summary()
        logger.info(f"Convergence reached: {reason.value if reason else 'unknown'}")
        return "synthesizer"

    # Check if iteration is explicitly needed (from critic)
    if state.get("needs_iteration", False):
        # Analyze and prioritize gaps
        gap_analysis = analyze_gaps(state, manager)
        state["gap_analysis"] = gap_analysis

        # Record gap fill attempts for prioritized gaps
        for gap in gap_analysis.get("prioritized_gaps", [])[:3]:
            gap_id = gap.get("gap_id", "")
            if gap_id:
                manager.record_gap_attempt(gap_id)

        logger.info(f"Iteration {iteration + 1}: {gap_analysis['total_gaps']} gaps, coverage={gap_analysis['coverage_ratio']:.2f}")
        return "planner"  # Go back to planning

    # Check evidence sufficiency
    is_sufficient, reason_text = check_evidence_sufficiency(state, manager.config)

    if not is_sufficient:
        logger.info(f"Evidence insufficient: {reason_text}")
        # Force another iteration if possible
        if iteration < manager.config.max_iterations:
            state["needs_iteration"] = True
            return "planner"

    # All checks passed, proceed to synthesis
    progress = calculate_overall_progress(state, manager)
    logger.info(f"Research progress: {progress:.1%}, proceeding to synthesis")

    return "synthesizer"


def should_end(state: ResearchState) -> bool:
    """Check if graph should end."""
    return state.get("converged", False) or state.get("final_report") is not None


# =============================================================================
# Graph Builder
# =============================================================================

def build_research_graph() -> StateGraph:
    """
    Build the LangGraph state machine for research workflow.

    Graph Structure (FIX 75 - Time Paradox Fix):
    START → triage → retrieve_memories → planner → supervisor → [routing] → ... → finalize → END

    FIX 75: CRITICAL - triage must run BEFORE retrieve_memories!
            Triage sets the `region` field, which retrieve_memories needs to
            query the correct LTM-Stage collection. Without this fix, memory
            would load WRONG region data (default "NORTH_AMERICA" instead of
            the actual region determined from the query).

    FIX 70/71: finalize_node promotes GOLD/SILVER evidence to LTM after CASE_1.

    The supervisor node decides routing between:
    - search → analyst → critic (verifier bypassed)
    - critic → planner (iteration) OR synthesizer (finalize)
    - synthesizer → auditor → finalize (post-hoc verification)

    NOTE: Pre-synthesis verification (verifier node) is disabled.
    Post-synthesis verification (auditor node) checks generated claims.
    """

    # Create graph with ResearchState
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("triage", triage_node)
    # FIX 75: Memory retrieval runs AFTER triage (needs region)
    graph.add_node("retrieve_memories", retrieve_memories_node)

    # KIMI K2.5 Parity: Tool integration nodes
    graph.add_node("process_files", process_file_attachments_node)  # Analyze file attachments
    graph.add_node("check_feedback", check_user_feedback_node)  # User feedback checkpoints
    graph.add_node("access_bypass", enhanced_fetch_with_bypass_node)  # Retry failed fetches
    graph.add_node("process_images", process_images_node)  # Extract image data

    graph.add_node("planner", planner_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("search", search_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("critic", critic_node)
    graph.add_node("synthesizer", synthesizer_node)
    graph.add_node("auditor", auditor_node)  # SPRINT 2 FIX 2.1
    graph.add_node("citation_enrichment", citation_enrichment_node)  # FIX 107
    graph.add_node("dynamic_replan", dynamic_replan_node)  # OpenAI o3 Parity
    graph.add_node("finalize", finalize_node)

    # FIX 75: Entry point is triage (sets region), not retrieve_memories
    graph.set_entry_point("triage")

    # Add edges
    # FIX 75: triage → retrieve_memories (triage sets region first)
    graph.add_edge("triage", "retrieve_memories")

    # KIMI Parity: Process file attachments after memory retrieval
    graph.add_edge("retrieve_memories", "process_files")

    # FIX 75: process_files → planner (file insights inform planning)
    graph.add_edge("process_files", "planner")

    # planner → supervisor (always)
    graph.add_edge("planner", "supervisor")

    # supervisor → conditional routing
    # SPRINT 2 FIX: Removed "verifier" from routing - verification is now post-synthesis
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "search": "search",
            "analyst": "analyst",
            # "verifier": "verifier",  # DISABLED - auditor handles post-synthesis verification
            "critic": "critic",
            "synthesizer": "synthesizer",
            "planner": "planner",
            "finalize": "finalize",
        }
    )

    # KIMI Parity: search → access_bypass (retry failed fetches)
    graph.add_edge("search", "access_bypass")

    # access_bypass → analyst (always)
    graph.add_edge("access_bypass", "analyst")

    # SPRINT 1 FIX 1.3 (Gemini): BYPASS verifier entirely
    # Gemini said: "Disable the current Verifier loop (save $40/run)"
    # The 87 verification rounds were "Verification Theatre" - checked inputs not outputs
    # Post-hoc verification (Auditor node) should check the OUTPUT instead
    #
    # FIX 84: RE-ENABLE VERIFIER for SOTA compliance
    # SOTA requires 30+ verified claims. Without verifier, claims_verified=0.
    # Cost increase is acceptable for SOTA quality.
    graph.add_edge("analyst", "verifier")
    graph.add_edge("verifier", "process_images")

    # process_images → check_feedback → critic
    graph.add_edge("process_images", "check_feedback")
    graph.add_edge("check_feedback", "critic")

    # NOTE: verifier node still exists but is never called in main flow
    # It can be re-enabled via supervisor routing if needed
    # graph.add_edge("verifier", "critic")  # DISABLED

    # critic → conditional (iterate or synthesize)
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "planner": "planner",
            "synthesizer": "synthesizer",
        }
    )

    # SPRINT 2 FIX 2.1: synthesizer → auditor → finalize
    # Post-hoc verification of generated report before finalization
    graph.add_edge("synthesizer", "auditor")

    # FIX: Wire up auditor feedback loop
    # Previously was direct edge to finalize, ignoring revision_required flag
    # Now routes back to synthesizer for correction if unfaithful sentences detected
    # OpenAI o3 Parity: Auditor now routes to dynamic_replan instead of finalize
    # FIX 107: Auditor routes to citation_enrichment when faithfulness >= 85%
    graph.add_conditional_edges(
        "auditor",
        route_after_auditor,
        {
            "synthesizer": "synthesizer",              # Revision needed
            "citation_enrichment": "citation_enrichment",  # FIX 107: Enrich citations
            "dynamic_replan": "dynamic_replan",        # Passed - evaluate for replan
        }
    )

    # FIX 107: Citation enrichment → dynamic_replan
    graph.add_edge("citation_enrichment", "dynamic_replan")

    # OpenAI o3 Parity: Dynamic replan routing
    # Routes back to planner if replan triggered, otherwise to finalize
    graph.add_conditional_edges(
        "dynamic_replan",
        route_after_dynamic_replan,
        {
            "planner": "planner",    # Replan triggered - new research direction
            "finalize": "finalize",  # No replan - proceed to finalize
        }
    )

    # finalize → END
    graph.add_edge("finalize", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    graph = build_research_graph()
    return graph.compile()


# =============================================================================
# Execution Helper
# =============================================================================

def run_research(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int,
    max_iterations: int = 10,
    max_execution_minutes: int = 30,
    min_faithfulness: float = 0.70
) -> ResearchState:
    """
    Run the complete research workflow for a vector.

    Args:
        vector_id: Unique identifier
        query: Research question
        application: Product category
        region: Geographic scope
        stage: Research stage (1-13)
        max_iterations: Maximum ReAct iterations
        max_execution_minutes: Maximum execution time
        min_faithfulness: Minimum faithfulness threshold

    Returns:
        Final ResearchState with results
    """
    from .state import create_initial_state

    # OpenAI o3 Parity: Reset state for new research run
    reset_o3_parity_state()

    # Create and set iteration manager
    manager = create_iteration_manager(
        max_iterations=max_iterations,
        max_execution_minutes=max_execution_minutes,
        min_faithfulness=min_faithfulness
    )
    set_iteration_manager(manager)

    # Create initial state
    state = create_initial_state(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
        stage=stage,
        max_iterations=max_iterations
    )

    logger.info(f"Starting research workflow for {vector_id}")
    logger.info(f"Config: max_iter={max_iterations}, max_time={max_execution_minutes}m, min_faith={min_faithfulness}")

    # Compile and run graph
    app = compile_graph()
    # FIX 80: Recursion limit bump for deep research cycles (S1V6 hit default 25 limit)
    final_state = app.invoke(state, {"recursion_limit": 150})

    # Add iteration summary to final state
    final_state["iteration_summary"] = manager.get_iteration_summary()

    logger.info(f"Completed research for {vector_id}: {final_state.get('gating_case')}")
    logger.info(f"Iterations: {len(manager.metrics_history)}, Converged: {manager.convergence_reason}")

    return final_state


def run_research_with_config(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int,
    config: IterationConfig
) -> ResearchState:
    """
    Run research with custom iteration configuration.

    Args:
        vector_id: Unique identifier
        query: Research question
        application: Product category
        region: Geographic scope
        stage: Research stage
        config: Custom iteration configuration

    Returns:
        Final ResearchState with results
    """
    from .state import create_initial_state

    # Create and set iteration manager with custom config
    manager = IterationManager(config)
    set_iteration_manager(manager)

    # Create initial state
    state = create_initial_state(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
        stage=stage,
        max_iterations=config.max_iterations
    )

    logger.info(f"Starting research workflow for {vector_id} with custom config")

    # Compile and run graph
    app = compile_graph()
    # FIX 80: Recursion limit bump for deep research cycles
    final_state = app.invoke(state, {"recursion_limit": 150})

    # Add iteration summary
    final_state["iteration_summary"] = manager.get_iteration_summary()

    return final_state
