# Copyright 2026 MoeIntel
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
agentctrl — Pluggable rate-limit backend protocol.

The library historically embedded an in-process counter inside
``RuntimeGateway``.  That is correct for a single-process consumer but
breaks under cluster deployment where each worker would maintain its
own bucket.

This module defines the minimal protocol any backend must implement.
The library ships with an :class:`InMemoryRateLimitBackend` for
test / single-process use.  Cluster-safe backends (Redis INCR/EXPIRE,
DynamoDB atomic counters, etc.) are the responsibility of the
consumer — they implement the protocol and pass an instance into
``RuntimeGateway(rate_limit_backend=...)``.

Failure semantics
-----------------
A backend that cannot reach its store MUST raise
``RateLimitBackendError``.  ``RuntimeGateway`` interprets that as a
fail-safe BLOCK rather than admitting the request — consistent with
the kill-switch fail-safe contract.  Backends MUST NOT silently fall
back to local counters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class RateLimitBackendError(Exception):
    """Raised by a backend when the underlying store is unreachable."""


@dataclass
class BackendResult:
    """Result of a single record-and-check probe."""

    current_count: int
    burst_count: int
    max_requests: int
    window_seconds: int
    burst_window: float


@runtime_checkable
class RateLimitBackend(Protocol):
    """Protocol every backend must satisfy.

    Implementations are expected to atomically (a) record this hit and
    (b) return the current count for the configured window plus a
    short-window burst count.
    """

    async def record_and_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        burst_window: float,
    ) -> BackendResult: ...


class InMemoryRateLimitBackend:
    """Process-local fixed-window counter.

    NOT cluster-safe.  Provided only so ``RuntimeGateway`` works out of
    the box for tests and single-process consumers.  Production
    deployments MUST inject a cluster-safe backend.
    """

    def __init__(self) -> None:
        import time

        self._time = time.monotonic
        self._buckets: dict[str, list[float]] = {}

    async def record_and_check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        burst_window: float,
    ) -> BackendResult:
        now = self._time()
        cutoff = now - window_seconds
        bucket = [t for t in self._buckets.get(key, []) if t > cutoff]
        bucket.append(now)
        self._buckets[key] = bucket

        burst_cutoff = now - burst_window
        burst_count = sum(1 for t in bucket if t > burst_cutoff)

        return BackendResult(
            current_count=len(bucket),
            burst_count=burst_count,
            max_requests=max_requests,
            window_seconds=window_seconds,
            burst_window=burst_window,
        )


__all__ = [
    "BackendResult",
    "InMemoryRateLimitBackend",
    "RateLimitBackend",
    "RateLimitBackendError",
]
