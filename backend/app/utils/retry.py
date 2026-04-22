"""Retry utilities with bounded exponential backoff and jitter."""

import asyncio
import random
import time
from functools import wraps
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar

P = ParamSpec('P')
R = TypeVar('R')


class MaxRetriesExceededError(Exception):
    """Raised when a function fails after max retry attempts."""
    pass


def _get_backoff_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay with jitter.

    Args:
        attempt: Current attempt number (0-indexed)

    Returns:
        Delay in seconds with jitter applied
    """
    # Base delays: 100ms, 200ms, 400ms
    base_delay_ms = 100 * (2 ** attempt)
    # Add jitter: ±25% of base delay
    jitter = base_delay_ms * 0.25 * (random.random() * 2 - 1)
    return (base_delay_ms + jitter) / 1000.0


def with_retry(
    max_attempts: int = 3,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    raise_last_exception: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator for synchronous functions to add retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        retry_exceptions: Tuple of exception types to catch and retry on
        raise_last_exception: If True, re-raise the last caught exception after retries.
                              If False (default), raise MaxRetriesExceededError.

    Returns:
        Decorated function with retry logic

    Example:
        @with_retry(max_attempts=3)
        def read_from_db():
            # database operation
            pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = _get_backoff_delay(attempt)
                        time.sleep(delay)
            # If raise_last_exception=True, re-raise the actual exception
            if raise_last_exception and last_exception:
                raise last_exception
            # Otherwise, raise MaxRetriesExceededError (default behavior)
            raise MaxRetriesExceededError(
                f"Function '{func.__name__}' failed after {max_attempts} attempts."
            ) from last_exception
        return wrapper
    return decorator


def with_async_retry(
    max_attempts: int = 3,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    raise_last_exception: bool = False,
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    """
    Decorator for asynchronous functions to add retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        retry_exceptions: Tuple of exception types to catch and retry on
        raise_last_exception: If True, re-raise the last caught exception after retries.
                              If False (default), raise MaxRetriesExceededError.

    Returns:
        Decorated async function with retry logic

    Example:
        @with_async_retry(max_attempts=3)
        async def fetch_from_api():
            # async operation
            pass
    """
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = _get_backoff_delay(attempt)
                        await asyncio.sleep(delay)
            # If raise_last_exception=True, re-raise the actual exception
            if raise_last_exception and last_exception:
                raise last_exception
            # Otherwise, raise MaxRetriesExceededError (default behavior)
            raise MaxRetriesExceededError(
                f"Async function '{func.__name__}' failed after {max_attempts} attempts."
            ) from last_exception
        return wrapper
    return decorator
