"""
POLARIS v3 Base Agent

Abstract base class for all POLARIS agents.
Provides common functionality:
- LLM client management
- Tool binding
- State reading/writing
- Logging and tracing
- Error handling

Based on LangChain/LangGraph agent patterns.
"""

import os
import json
import logging
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type, Union
from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.orchestration.state import ResearchState
from src.config import get_config
try:
    from src.callbacks.cost_tracking_callback import GeminiCostTrackingCallback
except ImportError:
    GeminiCostTrackingCallback = None  # Legacy module archived

# FIX-220: KimiClient for structural reasoning/content separation
try:
    from src.llm.kimi_client import KimiClient
    KIMI_CLIENT_AVAILABLE = True
except ImportError:
    KIMI_CLIENT_AVAILABLE = False

# Import LLM providers - prefer KIMI (Fireworks), fallback to Gemini
try:
    from langchain_fireworks import ChatFireworks
    FIREWORKS_AVAILABLE = True
except ImportError:
    FIREWORKS_AVAILABLE = False

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# Configure logging
logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    """Configuration for an agent instance."""
    name: str
    description: str
    task_tier: str = "simple"  # "simple" or "important" - determines model selection
    temperature: Optional[float] = None  # Override from config if set
    max_tokens: Optional[int] = None  # Override from config if set
    tools: List[str] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    retry_attempts: int = 3
    timeout_seconds: int = 120


class AgentTrace(BaseModel):
    """A single trace entry for agent execution."""
    agent_name: str
    action: str
    timestamp: str
    input_summary: str
    output_summary: str
    duration_ms: int
    tokens_used: int = 0
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract base class for all POLARIS v3 agents.

    Each agent:
    1. Reads from ResearchState
    2. Performs specialized processing
    3. Writes results back to ResearchState
    4. Logs all actions for traceability

    Subclasses must implement:
    - process(): Main processing logic
    - get_system_prompt(): Agent-specific system prompt
    """

    def __init__(
        self,
        config: AgentConfig,
        tools: Optional[List[BaseTool]] = None
    ):
        """
        Initialize the base agent.

        Args:
            config: Agent configuration
            tools: Optional list of LangChain tools this agent can use
        """
        self.config = config
        self.name = config.name
        self.tools = tools or []

        # Get global config for model settings
        global_config = get_config()

        # Get tiered model config based on task complexity
        tier = config.task_tier  # "simple" or "important"
        llm_config = global_config.models.llm

        # Determine temperature and max_tokens from tier config
        if llm_config.tiers:
            tier_config = getattr(llm_config.tiers, tier, None)
        else:
            tier_config = None

        if tier_config:
            default_temp = tier_config.temperature
            default_tokens = tier_config.max_tokens
            thinking_budget = getattr(tier_config, 'thinking_budget', 0)
        else:
            default_temp = 0.0
            default_tokens = 4096
            thinking_budget = 0

        temperature = config.temperature if config.temperature is not None else default_temp
        max_tokens = config.max_tokens if config.max_tokens is not None else default_tokens

        # PRIMARY LLM: KIMI K2.5 via Fireworks (preferred)
        # FALLBACK: Gemini (if Fireworks unavailable or quota exceeded)
        self.fallback_llm = None
        self._fallback_model_name = None
        self._is_fireworks = False  # FIX 91: Track LLM type for structured output method
        self._structured_llm = None  # FIX 92: Separate LLM for structured output (non-thinking mode)

        if FIREWORKS_AVAILABLE and global_config.env.fireworks_api_key:
            # Use KIMI K2.5 as primary LLM.
            # I-cd-010 / GH#625: pipeline-C frozen — KIMI K2.5 hardcoding intentional
            # per CLAUDE.md §5 (Carney demo Pipeline-A uses src/polaris_graph/* + OpenRouter V4 Pro).
            model_name = "accounts/fireworks/models/kimi-k2p5"
            self._cost_callback = GeminiCostTrackingCallback(model_name=model_name)

            # FIX 92: KIMI K2.5 has TWO modes with DIFFERENT temperature requirements:
            #   - Thinking mode: temperature=1.0 (immutable) - for general reasoning
            #   - Non-thinking mode: temperature=0.6 (immutable) - for structured output
            # We need SEPARATE instances for each mode

            # Primary LLM for general calls (thinking mode, temp=1.0)
            # FIX-170: Fireworks KIMI K2.5 requires stream=true for max_tokens > 4096.
            # Enable streaming automatically when token budget exceeds non-streaming limit.
            use_streaming = max_tokens > 4096
            self.llm = ChatFireworks(
                model=model_name,
                api_key=global_config.env.fireworks_api_key,
                temperature=1.0,  # KIMI K2.5 thinking mode REQUIRES 1.0
                max_tokens=max_tokens,
                streaming=use_streaming,
            )

            # FIX 92: Structured output LLM (non-thinking mode, temp=0.6)
            self._structured_llm = ChatFireworks(
                model=model_name,
                api_key=global_config.env.fireworks_api_key,
                temperature=0.6,  # KIMI K2.5 non-thinking mode REQUIRES 0.6
                max_tokens=min(max_tokens, 4096),  # Structured output stays non-streaming
            )

            self._is_fireworks = True  # FIX 91: Mark as Fireworks for structured output

            # FIX-220: Initialize KimiClient for prose generation
            # FIX-280: Use thinking_mode=False (instant mode) for prose generation.
            # Root cause: Fireworks KIMI K2.5 does NOT return reasoning_content as a
            # separate field — all output (thinking + prose) goes into content.
            # With thinking_mode=True, meta-reasoning leaks into prose output.
            # Instant mode (temp=0.6) produces clean prose without meta-commentary.
            self._kimi_synthesis_client = None
            self._kimi_fallback_count = 0  # FIX-230: Track ChatFireworks fallbacks
            if KIMI_CLIENT_AVAILABLE:
                try:
                    synthesis_max_tokens = int(os.environ.get(
                        "POLARIS_SYNTHESIS_MAX_TOKENS", "16000"
                    ))
                    self._kimi_synthesis_client = KimiClient(
                        thinking_mode=False,
                        max_tokens=synthesis_max_tokens,
                    )
                    logger.info(
                        f"[FIX-280] KimiClient initialized for prose generation "
                        f"(thinking=False/instant, max_tokens={synthesis_max_tokens})"
                    )
                except Exception as e:
                    logger.warning(f"[FIX-220] KimiClient init failed, synthesis will use ChatFireworks: {e}")

            logger.info(f"Initialized agent: {self.name} with KIMI K2.5 via Fireworks (tier={tier}, thinking=1.0, structured=0.6)")

            # Setup Gemini as fallback if available.
            # I-cd-010 / GH#625: pipeline-C frozen — Gemini fallback per CLAUDE.md §5.
            if GEMINI_AVAILABLE and global_config.env.gemini_api_key:
                fallback_model = llm_config.fallback_model if llm_config.fallback_model else "gemini-2.5-flash"
                self._fallback_model_name = fallback_model
                fallback_thinking = 1024 if "pro" in fallback_model else 0
                self.fallback_llm = ChatGoogleGenerativeAI(
                    model=fallback_model,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    google_api_key=global_config.env.gemini_api_key,
                    thinking_budget=fallback_thinking,
                    callbacks=[GeminiCostTrackingCallback(model_name=fallback_model)],

                )
                logger.info(f"Fallback LLM configured: Gemini {fallback_model}")

        elif GEMINI_AVAILABLE and global_config.env.gemini_api_key:
            # Fallback to Gemini if Fireworks unavailable
            if tier_config:
                model_name = tier_config.model
            else:
                model_name = llm_config.model

            self._cost_callback = GeminiCostTrackingCallback(model_name=model_name)

            self.llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=temperature,
                max_output_tokens=max_tokens,
                google_api_key=global_config.env.gemini_api_key,
                thinking_budget=thinking_budget,
                callbacks=[self._cost_callback],
            )
            thinking_status = "enabled" if thinking_budget > 0 else "disabled"
            logger.info(f"Initialized agent: {self.name} with Gemini {model_name} (tier={tier}, thinking={thinking_status})")

            # Setup secondary Gemini model as fallback
            if tier == "important" and llm_config.fallback_model:
                fallback_model_name = llm_config.fallback_model
                self._fallback_model_name = fallback_model_name
                fallback_thinking = 1024 if "pro" in fallback_model_name else 0
                self.fallback_llm = ChatGoogleGenerativeAI(
                    model=fallback_model_name,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                    google_api_key=global_config.env.gemini_api_key,
                    thinking_budget=fallback_thinking,
                    callbacks=[GeminiCostTrackingCallback(model_name=fallback_model_name)],

                )
                logger.info(f"Fallback LLM configured: Gemini {fallback_model_name}")
        else:
            raise RuntimeError(
                "No LLM provider available. Install langchain-fireworks and set FIREWORKS_API_KEY, "
                "or install langchain-google-genai and set GEMINI_API_KEY."
            )

        # Bind tools if provided
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt for this agent.

        Each agent type has a specialized prompt defining its role,
        capabilities, and output format.
        """
        pass

    @abstractmethod
    def process(self, state: ResearchState) -> ResearchState:
        """
        Main processing method for the agent.

        Args:
            state: Current research state

        Returns:
            Updated research state with agent's contributions
        """
        pass

    def invoke(self, state: ResearchState) -> ResearchState:
        """
        Invoke the agent with full tracing and error handling.

        This is the main entry point called by the orchestrator.

        Args:
            state: Current research state

        Returns:
            Updated research state
        """
        start_time = datetime.now(UTC)
        trace = AgentTrace(
            agent_name=self.name,
            action="invoke",
            timestamp=start_time.isoformat(),
            input_summary=self._summarize_input(state),
            output_summary="",
            duration_ms=0,
        )

        try:
            # Execute agent processing
            updated_state = self.process(state)

            # Calculate duration
            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Update trace
            trace.output_summary = self._summarize_output(updated_state)
            trace.duration_ms = duration_ms

            # Add trace to state
            if "agent_trace" not in updated_state:
                updated_state["agent_trace"] = []
            updated_state["agent_trace"].append(trace.model_dump())

            logger.info(
                f"Agent {self.name} completed in {duration_ms}ms"
            )

            return updated_state

        except Exception as e:
            # Log error
            logger.error(f"Agent {self.name} failed: {str(e)}")

            # Update trace with error
            end_time = datetime.now(UTC)
            trace.duration_ms = int((end_time - start_time).total_seconds() * 1000)
            trace.error = str(e)

            # Add error to state
            if "errors" not in state:
                state["errors"] = []
            state["errors"].append({
                "agent": self.name,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            })

            # Add trace to state
            if "agent_trace" not in state:
                state["agent_trace"] = []
            state["agent_trace"].append(trace.model_dump())

            # Re-raise for orchestrator to handle
            raise

    def _is_quota_error(self, error: Exception) -> bool:
        """
        FIX 11: Check if an error is a quota/rate-limit exhaustion error.

        Detects Google API 429 RESOURCE_EXHAUSTED errors that indicate
        daily quota limits have been reached.
        """
        error_str = str(error).lower()
        return (
            "resource_exhausted" in error_str
            or "429" in error_str
            or "quota exceeded" in error_str
        )

    def call_llm(
        self,
        messages: List[Union[HumanMessage, AIMessage, SystemMessage]],
        use_tools: bool = False
    ) -> AIMessage:
        """
        Call the LLM with messages.

        FIX 11: Falls back to fallback model on quota exhaustion.

        Args:
            messages: List of messages to send
            use_tools: Whether to enable tool use

        Returns:
            AI response message
        """
        llm = self.llm_with_tools if use_tools and self.tools else self.llm

        try:
            # FIX-195: Use .stream() + chunk collection when LLM has streaming enabled
            # Fireworks KIMI K2.5 .invoke() returns empty intermittently with streaming=True
            if getattr(llm, 'streaming', False) and self._is_fireworks:
                from langchain_core.messages import AIMessage as _AIMessage
                chunks = []
                for chunk in llm.stream(messages):
                    if chunk.content:
                        chunks.append(chunk.content)
                collected = "".join(chunks)
                return _AIMessage(content=collected)
            response = llm.invoke(messages)
            return response
        except Exception as e:
            if self.fallback_llm and self._is_quota_error(e):
                logger.warning(
                    f"[FIX 11] Primary model quota exhausted, "
                    f"falling back to {self._fallback_model_name}"
                )
                fallback = self.fallback_llm
                response = fallback.invoke(messages)
                return response
            raise

    def call_llm_structured(
        self,
        messages: List[Union[HumanMessage, AIMessage, SystemMessage]],
        output_schema: Type[BaseModel],
        timeout: Optional[int] = None
    ) -> Optional[BaseModel]:
        """
        Call the LLM with structured output and timeout enforcement.

        P0.1 FIX: Added timeout enforcement to prevent infinite hangs.
        See deployment_plan_20260126.md for details.

        Args:
            messages: List of messages to send
            output_schema: Pydantic model for structured output
            timeout: Timeout in seconds (defaults to config.timeout_seconds)

        Returns:
            Parsed output conforming to schema, or None if timeout/error
        """
        timeout = timeout or self.config.timeout_seconds
        # FIX 91 + FIX 92: Use dedicated structured LLM for Fireworks (KIMI K2.5)
        # - FIX 91: Use json_schema method (function_calling doesn't work with KIMI)
        # - FIX 92: Use _structured_llm with temp=0.6 (non-thinking mode requirement)
        if getattr(self, '_is_fireworks', False) and getattr(self, '_structured_llm', None):
            structured_llm = self._structured_llm.with_structured_output(output_schema, method='json_schema')
        elif getattr(self, '_is_fireworks', False):
            # Fallback if _structured_llm not available (shouldn't happen)
            structured_llm = self.llm.with_structured_output(output_schema, method='json_schema')
        else:
            structured_llm = self.llm.with_structured_output(output_schema)

        # P3.2 FIX: Progress logging during LLM calls
        logger.info(f"LLM call started: {output_schema.__name__} (timeout={timeout}s)")
        start_time = time.time()

        # FIX 17A: Pass callbacks explicitly - with_structured_output() drops them
        invoke_config = RunnableConfig(callbacks=[self._cost_callback])

        # FIX 17B: Manual executor to avoid shutdown(wait=True) blocking after timeout
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                structured_llm.invoke, messages, invoke_config
            )
            try:
                response = future.result(timeout=timeout)
                duration = time.time() - start_time
                logger.info(f"LLM call completed: {output_schema.__name__} in {duration:.1f}s")
                return response
            except FuturesTimeoutError:
                duration = time.time() - start_time
                logger.error(f"LLM call TIMEOUT after {duration:.1f}s for {output_schema.__name__}")
                future.cancel()
                return None
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"LLM call FAILED after {duration:.1f}s: {e}")

            # FIX 11: Try fallback model on quota exhaustion
            if self.fallback_llm and self._is_quota_error(e):
                logger.warning(
                    f"[FIX 11] Primary model quota exhausted, "
                    f"retrying with fallback: {self._fallback_model_name}"
                )
                return self._call_llm_structured_fallback(
                    messages, output_schema, timeout
                )

            return None
        finally:
            # FIX 17B: Non-blocking shutdown - don't wait for timed-out threads
            executor.shutdown(wait=False)

    def _call_llm_structured_fallback(
        self,
        messages: List[Union[HumanMessage, AIMessage, SystemMessage]],
        output_schema: Type[BaseModel],
        timeout: int,
    ) -> Optional[BaseModel]:
        """
        FIX 11: Retry structured LLM call with fallback model.

        Called when the primary model (gemini-3-pro-preview) hits quota limits.
        Uses the fallback model (gemini-2.5-flash) as a degraded alternative.
        """
        start_time = time.time()
        structured_fallback = self.fallback_llm.with_structured_output(
            output_schema
        )
        # FIX 17A: Pass callbacks explicitly to fallback as well
        invoke_config = RunnableConfig(callbacks=[self._cost_callback])
        # FIX 17B: Manual executor to avoid shutdown(wait=True) blocking
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                structured_fallback.invoke, messages, invoke_config
            )
            try:
                response = future.result(timeout=timeout)
                duration = time.time() - start_time
                logger.info(
                    f"[FIX 11] Fallback LLM completed: "
                    f"{output_schema.__name__} in {duration:.1f}s"
                )
                return response
            except FuturesTimeoutError:
                duration = time.time() - start_time
                logger.error(
                    f"[FIX 11] Fallback LLM TIMEOUT after {duration:.1f}s "
                    f"for {output_schema.__name__}"
                )
                future.cancel()
                return None
        except Exception as fallback_err:
            duration = time.time() - start_time
            logger.error(
                f"[FIX 11] Fallback LLM FAILED after {duration:.1f}s: "
                f"{fallback_err}"
            )
            return None
        finally:
            # FIX 17B: Non-blocking shutdown for fallback executor too
            executor.shutdown(wait=False)

    def _invoke_synthesis_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 0,
    ) -> str:
        """
        FIX-220: Invoke LLM with STRUCTURAL reasoning/content separation.

        Uses KimiClient which correctly separates reasoning_content from content
        at the API level. Reasoning is logged for debugging but NEVER included
        in output. This matches the SOTA pattern used by Gemini 3 Pro, GPT-5.2,
        and DeepSeek-R1.

        Falls back to standard _invoke_llm() if KimiClient is unavailable.

        Args:
            prompt: The user prompt
            system_prompt: Optional system instruction
            max_tokens: Per-call token limit (0 = use client default)

        Returns:
            Clean content string with reasoning structurally removed
        """
        kimi = getattr(self, '_kimi_synthesis_client', None)
        if kimi is None:
            # FIX-230: Loud fallback — no KimiClient, CoT separation LOST for this call
            self._kimi_fallback_count = getattr(self, '_kimi_fallback_count', 0) + 1
            logger.warning(
                f"[FIX-230] KimiClient UNAVAILABLE — falling back to ChatFireworks "
                f"(CoT separation LOST, fallback #{self._kimi_fallback_count})"
            )
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            response = self.llm.invoke(messages)
            # FIX-284: Scrub CoT from ChatFireworks fallback — thinking_mode output
            # has ZERO structural separation, so regex scrubbing is the only defense.
            from src.utils.cot_scrubber import scrub_cot_from_report
            return scrub_cot_from_report(response.content) if response.content else ""

        tokens = max_tokens if max_tokens > 0 else kimi.max_tokens

        try:
            result = kimi.generate_with_reasoning_sync(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=tokens,
            )

            # Log reasoning stats (NEVER include in output)
            reasoning = result.get("reasoning")
            content = result.get("content", "")
            if reasoning:
                logger.debug(
                    f"[FIX-220] Reasoning separated: {len(reasoning)} chars, "
                    f"{len(reasoning.split())} words (structurally excluded from output)"
                )
            else:
                logger.debug("[FIX-280] No reasoning_content (instant mode / API limitation)")

            if not content:
                logger.warning("[FIX-220] KimiClient returned empty content")

            # FIX-281: Defense-in-depth — scrub at lowest level before any caller sees content.
            # Even with thinking_mode=False (FIX-280), apply scrubbing as safety net.
            if content and not reasoning:
                from src.utils.cot_scrubber import scrub_cot_from_report
                content_before = len(content)
                content = scrub_cot_from_report(content)
                chars_removed = content_before - len(content)
                if chars_removed > 0:
                    logger.info(
                        f"[FIX-281] Pre-return scrub removed {chars_removed} chars "
                        f"({content_before} -> {len(content)})"
                    )

            return content or ""

        except Exception as e:
            # FIX-230: Loud fallback — KimiClient error, CoT separation LOST for this call
            self._kimi_fallback_count = getattr(self, '_kimi_fallback_count', 0) + 1
            logger.error(
                f"[FIX-230] KimiClient FAILED: {e} — falling back to ChatFireworks "
                f"(CoT separation LOST, fallback #{self._kimi_fallback_count})"
            )
            messages = []
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            messages.append(HumanMessage(content=prompt))
            response = self.llm.invoke(messages)
            # FIX-284: Scrub CoT from ChatFireworks fallback — thinking_mode output
            # has ZERO structural separation, so regex scrubbing is the only defense.
            from src.utils.cot_scrubber import scrub_cot_from_report
            return scrub_cot_from_report(response.content) if response.content else ""

    def _summarize_input(self, state: ResearchState) -> str:
        """Create a brief summary of input state for tracing."""
        return (
            f"vector_id={state.get('vector_id', 'unknown')}, "
            f"iteration={state.get('iteration_count', 0)}, "
            f"evidence_count={len(state.get('evidence_chain', []))}"
        )

    def _summarize_output(self, state: ResearchState) -> str:
        """Create a brief summary of output state for tracing."""
        return (
            f"evidence_count={len(state.get('evidence_chain', []))}, "
            f"gaps_count={len(state.get('gaps', []))}, "
            f"converged={state.get('converged', False)}"
        )


# =============================================================================
# Agent Registry
# =============================================================================

_agent_registry: Dict[str, Type[BaseAgent]] = {}


def register_agent(name: str):
    """Decorator to register an agent class."""
    def decorator(cls: Type[BaseAgent]):
        _agent_registry[name] = cls
        return cls
    return decorator


def get_agent_class(name: str) -> Type[BaseAgent]:
    """Get an agent class by name."""
    if name not in _agent_registry:
        raise ValueError(f"Unknown agent: {name}. Available: {list(_agent_registry.keys())}")
    return _agent_registry[name]


def list_agents() -> List[str]:
    """List all registered agent names."""
    return list(_agent_registry.keys())
