# Copyright 2026 MoeIntel
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Tests for the pluggable rate-limit backend protocol.

The library ships two backends:

* :class:`InMemoryRateLimitBackend` — single-process counter for tests
  and dev; NOT cluster-safe by design.
* :class:`RateLimitBackend` — the protocol any cluster-safe backend
  must satisfy.  Consumers implement Redis (or equivalent) and pass
  an instance into ``RuntimeGateway(rate_limit_backend=...)``.

These tests cover:

1. In-memory window arithmetic (count + burst).
2. Protocol conformance via ``isinstance`` against the ``Protocol``.
3. Gateway fail-safe behaviour when a backend raises
   :class:`RateLimitBackendError`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── In-memory backend ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inmemory_counts_per_key():
    from agentctrl import InMemoryRateLimitBackend

    be = InMemoryRateLimitBackend()
    r1 = await be.record_and_check("k", max_requests=10, window_seconds=60, burst_window=5.0)
    r2 = await be.record_and_check("k", max_requests=10, window_seconds=60, burst_window=5.0)
    r3 = await be.record_and_check("k", max_requests=10, window_seconds=60, burst_window=5.0)

    assert r1.current_count == 1
    assert r2.current_count == 2
    assert r3.current_count == 3
    # Result payload exposes the rule parameters so the caller can check
    # pressure without holding on to the original rule dict.
    assert r3.max_requests == 10
    assert r3.window_seconds == 60
    assert r3.burst_window == 5.0


@pytest.mark.asyncio
async def test_inmemory_isolated_per_key():
    from agentctrl import InMemoryRateLimitBackend

    be = InMemoryRateLimitBackend()
    a = await be.record_and_check("a", max_requests=5, window_seconds=60, burst_window=5.0)
    b = await be.record_and_check("b", max_requests=5, window_seconds=60, burst_window=5.0)
    assert a.current_count == 1
    assert b.current_count == 1


@pytest.mark.asyncio
async def test_inmemory_burst_counts_within_short_window():
    from agentctrl import InMemoryRateLimitBackend

    be = InMemoryRateLimitBackend()
    for _ in range(4):
        r = await be.record_and_check("k", max_requests=10, window_seconds=60, burst_window=5.0)
    # All 4 hits land inside the 5-second burst window
    assert r.burst_count == 4


# ── Protocol conformance ────────────────────────────────────────────────────


def test_in_memory_backend_implements_protocol():
    from agentctrl import InMemoryRateLimitBackend, RateLimitBackend

    # RateLimitBackend is declared @runtime_checkable so this check is valid.
    assert isinstance(InMemoryRateLimitBackend(), RateLimitBackend)


def test_backend_result_has_expected_fields():
    from agentctrl import BackendResult

    r = BackendResult(
        current_count=1,
        burst_count=1,
        max_requests=10,
        window_seconds=60,
        burst_window=5.0,
    )
    assert r.current_count == 1
    assert r.burst_count == 1
    assert r.max_requests == 10


# ── Gateway integration: fail-safe BLOCK on backend error ────────────────────


class _FailingBackend:
    """Backend that always raises — simulates Redis outage."""

    async def record_and_check(self, key, max_requests, window_seconds, burst_window):
        from agentctrl import RateLimitBackendError
        raise RateLimitBackendError("backend unreachable (test-injected)")


@pytest.mark.asyncio
async def test_gateway_fails_safe_to_block_when_backend_unreachable():
    """Backend errors MUST produce a BLOCK decision, never silent admit."""
    from agentctrl import ActionProposal, RuntimeGateway

    gateway = RuntimeGateway(
        rate_limits=[{
            "target_type": "global",
            "target_id": "*",
            "max_requests": 100,
            "window_seconds": 60,
        }],
        rate_limit_backend=_FailingBackend(),
    )

    result = await gateway.validate(ActionProposal(
        agent_id="agent-x",
        action_type="invoice.approve",
        action_params={"amount": 1000},
        autonomy_level=2,
    ))

    assert result.decision == "BLOCK"
    # rate_pressure is saturated to signal downstream scoring
    stage_names = [s.stage for s in result.pipeline_stages]
    assert "rate_limit" in stage_names


@pytest.mark.asyncio
async def test_gateway_admits_when_backend_returns_below_limit():
    """Successful backend responses flow through the rest of the pipeline."""
    from agentctrl import (
        ActionProposal,
        InMemoryRateLimitBackend,
        RuntimeGateway,
    )

    gateway = RuntimeGateway(
        rate_limits=[{
            "target_type": "global",
            "target_id": "*",
            "max_requests": 100,
            "window_seconds": 60,
        }],
        rate_limit_backend=InMemoryRateLimitBackend(),
        autonomy_scopes={2: ["invoice"]},
    )

    result = await gateway.validate(ActionProposal(
        agent_id="agent-ok",
        action_type="invoice.approve",
        action_params={"amount": 100},
        autonomy_level=2,
    ))

    # Rate limiter should not be the blocking stage (result might still
    # escalate for other reasons like default policy).  The invariant
    # being tested: the gateway didn't short-circuit at the rate-limit
    # pre-gate because the backend is healthy.
    stage_names = [s.stage for s in result.pipeline_stages]
    rate_stage = next((s for s in result.pipeline_stages if s.stage == "rate_limit"), None)
    if rate_stage is not None:
        assert rate_stage.status != "BLOCK"
    assert "autonomy_check" in stage_names  # pipeline advanced past the pre-gate
