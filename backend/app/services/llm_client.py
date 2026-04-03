"""
OpenAI-compatible LLM chat client using httpx.
"""

import json
import logging
from typing import AsyncGenerator, List, Dict, Any, Optional

import httpx

from app.config import settings
from app.services.circuit_breaker import llm_cb, CircuitBreakerError

logger = logging.getLogger(__name__)


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
        except Exception:
            pass  # Silently ignore any errors accessing internal pool state

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
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

            return content
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
        max_tokens: int = 2048,
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

                            if content:
                                yield content
                except GeneratorExit:
                    # Generator was closed by consumer - clean exit
                    raise
        except LLMError:
            # Re-raise LLMError exceptions (e.g., from content-type validation) cleanly
            raise
        except httpx.TimeoutException as e:
            raise LLMError(f"Streaming request timed out after {self.timeout}s") from e
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"HTTP error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Streaming request failed: {str(e)}") from e

        # Log connection pool metrics after streaming completes
        self._log_pool_stats()

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
