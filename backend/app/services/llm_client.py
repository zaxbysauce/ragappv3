"""
OpenAI-compatible LLM chat client using httpx.
"""

import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

import httpx

from app.config import settings
from app.services.circuit_breaker import (
    llm_cb,
    CircuitBreakerError,
    CircuitBreakerState,
)

logger = logging.getLogger(__name__)

_MAX_THINKING_BUFFER = 1024 * 1024  # 1MB max thinking buffer


class LLMError(Exception):
    """Exception raised for LLM client errors."""

    pass


class LLMClient:
    """OpenAI-compatible LLM chat client."""

    def __init__(self, timeout: float = 300.0):
        """
        Initialize the LLM client.

        Args:
            timeout: Request timeout in seconds (default: 300.0 for model loading)
        """
        self.base_url = settings.ollama_chat_url.rstrip("/")
        self.model = settings.chat_model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Start the HTTP client. Must be called before using the client."""
        # Configure limits for connection pooling with keep-alive
        limits = httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=300.0,  # Keep connections alive for 5 minutes
        )
        # Add keep-alive headers to prevent LM Studio from unloading
        headers = {"Connection": "keep-alive", "Keep-Alive": "timeout=300, max=1000"}
        self._client = httpx.AsyncClient(
            timeout=self.timeout, limits=limits, headers=headers
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _ensure_started(self) -> httpx.AsyncClient:
        """Ensure the client has been started and return it."""
        if self._client is None:
            raise RuntimeError(
                "LLMClient not started. Call start() before using the client."
            )
        return self._client

    def _log_pool_stats(self) -> None:
        """Log connection pool statistics for monitoring."""
        try:
            client = self._client
            if client is None:
                return
            pool = getattr(client, "_transport", None)
            if pool and hasattr(pool, "_pool"):
                pool_obj = pool._pool
                connections = getattr(pool_obj, "_num_connections", 0)
                keepalive = getattr(pool_obj, "_num_keepalive", 0)
                limits = getattr(pool_obj, "_limits", None)
                max_connections = (
                    getattr(limits, "max_connections", 10) if limits else 10
                )
                max_keepalive = (
                    getattr(limits, "max_keepalive_connections", 5) if limits else 5
                )
                logger.info(
                    f"LLM client pool: {connections}/{max_connections} connections, "
                    f"{keepalive}/{max_keepalive} keepalive"
                )
        except Exception as e:
            logger.debug("Could not log pool stats: %s", e)

    def _strip_thinking_content(self, content: str) -> str:
        """
        Remove thinking content blocks from a complete response string.

        Handles two patterns:
        1. _lhs to _rhs tags (standard pattern with opening/closing tags)
        2. "Thinking Process:" prefix to </think> closing tag (qwen3.5-122b pattern)

        Args:
            content: The complete response content string

        Returns:
            Content with all thinking blocks removed, whitespace stripped
        """
        result = content

        # Pattern 1: _lhs to _rhs (standard tags)
        while "_lhs" in result and "_rhs" in result:
            start = result.find("_lhs")
            end = result.find("_rhs") + 4  # Include "_rhs" length
            result = result[:start] + result[end:]

        # Pattern 2: "Thinking Process:" prefix to </think> closing tag (qwen3.5-122b)
        # Content may start with "Thinking Process:\n\n" followed by thinking, ends with </think>
        if result.startswith("Thinking Process:"):
            close_pos = result.find("</think>")
            if close_pos != -1:
                result = result[close_pos + 8 :]
            else:
                result = ""

        return result.strip()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 32768,
    ) -> str:
        """
        Send a chat completion request and return the full response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens to generate (default: 2048)

        Returns:
            The generated content string

        Raises:
            LLMError: If the request fails or response is invalid
            RuntimeError: If the client has not been started
        """
        client = self._ensure_started()
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = await llm_cb(client.post)(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if "choices" not in data or not data["choices"]:
                raise LLMError("Invalid response: no choices in response")

            message = data["choices"][0].get("message", {})
            content = message.get("content", "")

            # Log connection pool metrics
            self._log_pool_stats()

            return self._strip_thinking_content(content)
        except CircuitBreakerError as e:
            raise LLMError(
                f"LLM service is currently unavailable (circuit breaker open): {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise LLMError(f"Request timed out after {self.timeout}s") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"HTTP error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Request failed: {str(e)}") from e
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse response JSON: {str(e)}") from e

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 32768,
    ) -> AsyncGenerator[str, None]:
        """
        Send a streaming chat completion request and yield content chunks.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            temperature: Sampling temperature (default: 0.7)
            max_tokens: Maximum tokens to generate (default: 2048)

        Yields:
            Content chunks as they arrive from the SSE stream

        Raises:
            LLMError: If the request fails
            RuntimeError: If the client has not been started
        """
        client = self._ensure_started()
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Check circuit breaker state before attempting stream connection.
        # Use the lock to avoid race conditions with concurrent requests.
        async with llm_cb._lock:
            if llm_cb.current_state == CircuitBreakerState.OPEN:
                llm_cb._check_timeout()
                if llm_cb.current_state == CircuitBreakerState.OPEN:
                    raise LLMError(
                        "LLM service is currently unavailable (circuit breaker open)"
                    )

        # State for filtering thinking content (_lhs/_rhs tags from qwen3.5)
        _thinking_active = False
        _buffer = ""

        stream_succeeded = False
        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                # Validate content-type for SSE
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    # Fall back to non-stream completion for providers that don't return SSE
                    content = await self.chat_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    if content:
                        yield content
                    stream_succeeded = True
                    return

                try:
                    async for line in response.aiter_lines():
                        line = line.strip()

                        # Skip empty lines and SSE keep-alive comments
                        if not line or line.startswith(":"):
                            continue

                        # SSE format: data: {...}
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix

                            # Check for stream end marker
                            if data_str == "[DONE]":
                                break

                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            # Extract content delta from choices
                            choices = data.get("choices", [])
                            if not choices:
                                continue

                            delta = choices[0].get("delta", {})
                            # Handle both standard content and reasoning_content (used by some models like nvidia_nemotron)
                            content = (
                                delta.get("content")
                                or delta.get("reasoning_content")
                                or ""
                            )

                            # Filter thinking content from qwen3.5-122b model
                            # Handles two patterns:
                            # 1. _lhs to _rhs tags (standard)
                            # 2. "Thinking Process:" prefix to </think> closing tag (qwen3.5-122b)
                            _buffer += content

                            if len(_buffer) > _MAX_THINKING_BUFFER:
                                logger.error(
                                    "Thinking content buffer exceeded %d bytes, possible malformed response",
                                    _MAX_THINKING_BUFFER,
                                )
                                raise LLMError(
                                    "Thinking content buffer overflow - model response may be malformed"
                                )

                            if not _thinking_active:
                                # Not currently in thinking block - look for opening pattern
                                # Check for standard _lhs opening tag
                                if "_lhs" in _buffer:
                                    # Log once when thinking content is first detected
                                    logger.debug(
                                        "Filtering thinking content from model response"
                                    )
                                    # Yield any content before the _lhs tag
                                    pre_think, _, remainder = _buffer.partition("_lhs")
                                    if pre_think:
                                        yield pre_think
                                    _thinking_active = True
                                    _buffer = remainder
                                    # Check if _rhs is also in this same chunk
                                    if "_rhs" in _buffer:
                                        # _rhs found in same chunk - extract content after it
                                        _, _, after_think = _buffer.partition("_rhs")
                                        _thinking_active = False
                                        _buffer = after_think
                                # Check for qwen3.5-122b pattern: "Thinking Process:" at start
                                # Use substring check to handle fragmented streaming
                                elif (
                                    "Thinking Process:".startswith(_buffer)
                                    or "Thinking Process:" in _buffer
                                ):
                                    # Could be the start of thinking content - check if full prefix present
                                    if "Thinking Process:" in _buffer:
                                        logger.debug(
                                            "Filtering thinking content from model response (Thinking Process pattern)"
                                        )
                                        _thinking_active = True
                                        _buffer = ""  # Discard everything up to and including the prefix
                                    # else: still accumulating "Thinking Process:" prefix, hold buffer
                                elif _buffer:
                                    # Not in thinking mode and no opening pattern - yield buffer content
                                    yield _buffer
                                    _buffer = ""
                            else:
                                # Currently inside thinking block - look for closing tag
                                # Check for standard _rhs closing tag
                                if "_rhs" in _buffer:
                                    # End of thinking block - extract content after _rhs
                                    _, _, after_think = _buffer.partition("_rhs")
                                    _thinking_active = False
                                    _buffer = after_think
                                # Check for qwen3.5-122b pattern: </think> closing tag
                                elif "</think>" in _buffer:
                                    # End of thinking block - extract content after </think>
                                    _, _, after_think = _buffer.partition("</think>")
                                    _thinking_active = False
                                    _buffer = after_think
                                # Else: still inside thinking, keep full buffer until closing tag arrives
                            # Yield any buffered content when not in thinking mode
                            if (
                                not _thinking_active
                                and _buffer
                                and not "Thinking Process:".startswith(_buffer)
                            ):
                                yield _buffer
                                _buffer = ""
                    stream_succeeded = True
                except GeneratorExit:
                    # Generator was closed by consumer - clean exit
                    stream_succeeded = True
                    raise
        except LLMError:
            # Don't record LLMError as transport failure — it may come from
            # the chat_completion() fallback path and represent an app-level error,
            # not a service-unavailability signal.
            raise
        except httpx.TimeoutException as e:
            async with llm_cb._lock:
                llm_cb.record_failure()
            raise LLMError(f"Streaming request timed out after {self.timeout}s") from e
        except httpx.HTTPStatusError as e:
            async with llm_cb._lock:
                llm_cb.record_failure()
            # Read response content first to avoid ResponseNotRead error in streaming context
            try:
                response_text = (await e.response.aread()).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                response_text = "<unable to read response>"
            raise LLMError(
                f"HTTP error {e.response.status_code}: {response_text}"
            ) from e
        except httpx.RequestError as e:
            async with llm_cb._lock:
                llm_cb.record_failure()
            raise LLMError(f"Streaming request failed: {str(e)}") from e
        finally:
            if stream_succeeded:
                async with llm_cb._lock:
                    llm_cb.record_success()

        # Log connection pool metrics after streaming completes
        self._log_pool_stats()

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
