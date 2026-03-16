"""
Streaming Reasoning Tokens (OpenAI Parity)
===========================================
Provides real-time visibility into the thinking process.

OpenAI shows reasoning tokens as they're generated.
We implement this with KIMI K2.5's streaming API.
"""

import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReasoningToken:
    """A streaming reasoning token."""
    content: str
    token_type: str  # "thinking", "output", "citation"
    position: int
    timestamp_ms: int


class StreamingReasoner:
    """
    Streaming reasoning token provider.

    Streams thinking tokens in real-time for visibility.
    """

    def __init__(
        self,
        on_token: Optional[Callable[[ReasoningToken], None]] = None,
        on_thinking_start: Optional[Callable[[], None]] = None,
        on_thinking_end: Optional[Callable[[str], None]] = None,
    ):
        self.on_token = on_token
        self.on_thinking_start = on_thinking_start
        self.on_thinking_end = on_thinking_end

        # Tracking
        self.total_tokens = 0
        self.thinking_tokens = 0
        self.output_tokens = 0
        self._cancelled = False

    async def stream_reasoning(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> AsyncIterator[ReasoningToken]:
        """
        Stream reasoning tokens from KIMI.

        Yields tokens as they're generated.
        """
        import os
        from openai import AsyncOpenAI
        import time

        client = AsyncOpenAI(
            api_key=os.getenv("FIREWORKS_API_KEY"),
            base_url="https://api.fireworks.ai/inference/v1",
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Signal thinking start
        if self.on_thinking_start:
            self.on_thinking_start()

        thinking_complete = False
        position = 0
        start_time = time.time()

        try:
            stream = await client.chat.completions.create(
                model="accounts/fireworks/models/kimi-k2-5-instruct",
                messages=messages,
                temperature=1.0,
                max_tokens=16000,
                stream=True,
                extra_body={"thinking": {"type": "enabled"}},
            )

            async for chunk in stream:
                if self._cancelled:
                    break

                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Check for reasoning content
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    token = ReasoningToken(
                        content=delta.reasoning_content,
                        token_type="thinking",
                        position=position,
                        timestamp_ms=int((time.time() - start_time) * 1000),
                    )
                    self.thinking_tokens += 1
                    position += 1

                    if self.on_token:
                        self.on_token(token)

                    yield token

                # Check for output content
                if delta.content:
                    # Mark thinking as complete on first output token
                    if not thinking_complete:
                        thinking_complete = True
                        if self.on_thinking_end:
                            self.on_thinking_end("Thinking complete")

                    token = ReasoningToken(
                        content=delta.content,
                        token_type="output",
                        position=position,
                        timestamp_ms=int((time.time() - start_time) * 1000),
                    )
                    self.output_tokens += 1
                    position += 1

                    if self.on_token:
                        self.on_token(token)

                    yield token

                self.total_tokens = position

        except Exception as e:
            logger.error(f"[STREAM] Streaming error: {e}")
            raise

    def cancel(self):
        """Cancel ongoing streaming."""
        self._cancelled = True
        logger.info("[STREAM] Cancelled")

    async def generate_with_progress(
        self,
        prompt: str,
        system_prompt: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Generate with progress tracking.

        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Called with (current_tokens, estimated_total)
        """
        thinking_content = []
        output_content = []

        async for token in self.stream_reasoning(prompt, system_prompt):
            if token.token_type == "thinking":
                thinking_content.append(token.content)
            else:
                output_content.append(token.content)

            if progress_callback:
                # Estimate progress
                progress_callback(self.total_tokens, self.total_tokens + 100)

        return {
            "thinking": "".join(thinking_content),
            "output": "".join(output_content),
            "stats": {
                "thinking_tokens": self.thinking_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
            }
        }


class WebSocketReasoningStream:
    """
    WebSocket endpoint for UI streaming.

    Provides real-time token updates via WebSocket.
    """

    def __init__(self, websocket):
        self.websocket = websocket
        self.streamer = StreamingReasoner(
            on_token=self._send_token,
            on_thinking_start=self._send_thinking_start,
            on_thinking_end=self._send_thinking_end,
        )

    async def _send_token(self, token: ReasoningToken):
        """Send token via WebSocket."""
        import json
        await self.websocket.send(json.dumps({
            "type": "token",
            "data": {
                "content": token.content,
                "token_type": token.token_type,
                "position": token.position,
                "timestamp_ms": token.timestamp_ms,
            }
        }))

    async def _send_thinking_start(self):
        """Signal thinking started."""
        import json
        await self.websocket.send(json.dumps({
            "type": "thinking_start",
        }))

    async def _send_thinking_end(self, summary: str):
        """Signal thinking ended."""
        import json
        await self.websocket.send(json.dumps({
            "type": "thinking_end",
            "summary": summary,
        }))

    async def stream(self, prompt: str, system_prompt: str = ""):
        """Run streaming over WebSocket."""
        async for _ in self.streamer.stream_reasoning(prompt, system_prompt):
            pass  # Tokens sent via callbacks
