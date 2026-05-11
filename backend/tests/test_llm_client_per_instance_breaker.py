"""Verify each LLMClient owns its own circuit breaker.

After the dual-mode (Instant/Thinking) refactor, the LLMClient no longer
uses the module-level ``llm_cb`` singleton inside its methods. Each
instance constructs its own ``AsyncCircuitBreaker`` so that failures on
one backend cannot trip the breaker for another.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio

import pytest

from app.services.circuit_breaker import AsyncCircuitBreaker, CircuitBreakerState
from app.services.llm_client import (
    LLMClient,
    create_instant_client,
    create_thinking_client,
)


def test_per_instance_circuit_breaker_distinct_objects():
    """Two LLMClient instances must hold distinct circuit breaker instances."""
    a = LLMClient()
    b = LLMClient()
    assert isinstance(a._circuit_breaker, AsyncCircuitBreaker)
    assert isinstance(b._circuit_breaker, AsyncCircuitBreaker)
    assert a._circuit_breaker is not b._circuit_breaker


def test_thinking_and_instant_factories_have_distinct_breakers():
    """Factory-created Thinking and Instant clients must have isolated breakers and distinct names."""
    thinking = create_thinking_client()
    instant = create_instant_client()
    assert thinking._circuit_breaker is not instant._circuit_breaker
    assert thinking._circuit_breaker.name == "llm_thinking"
    assert instant._circuit_breaker.name == "llm_instant"


def test_breaker_failure_on_one_does_not_trip_other():
    """Recording failures on instance A's breaker must NOT affect instance B's state."""
    a = LLMClient()
    b = LLMClient()

    async def trip_a():
        # fail_max=5 — record 5 failures to trip A.
        async with a._circuit_breaker._lock:
            for _ in range(5):
                a._circuit_breaker.record_failure()

    asyncio.run(trip_a())

    assert a._circuit_breaker.current_state == CircuitBreakerState.OPEN
    assert b._circuit_breaker.current_state == CircuitBreakerState.CLOSED


def test_reconfigure_updates_base_url_and_model_in_place():
    """LLMClient.reconfigure must hot-swap base_url and model without recreating the client."""
    c = LLMClient(base_url="http://old.example:1234", model="old-model")
    breaker_ref = c._circuit_breaker
    c.reconfigure(base_url="http://new.example:5678", model="new-model")
    assert c.base_url == "http://new.example:5678"
    assert c.model == "new-model"
    # Breaker reference is preserved — no recreation.
    assert c._circuit_breaker is breaker_ref
