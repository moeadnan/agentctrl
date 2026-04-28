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

"""agentctrl — Institutional governance pipeline for AI agent actions.

Usage:
    from agentctrl import RuntimeGateway, ActionProposal

    gateway = RuntimeGateway()
    result = await gateway.validate(ActionProposal(
        agent_id="my-agent",
        action_type="data.read",
        action_params={"classification": "PII"},
        autonomy_level=2,
    ))
    print(result["decision"])  # ALLOW | ESCALATE | BLOCK
"""

from .types import (
    ActionProposal,
    PipelineStageResult,
    PipelineHooks,
    EscalationTarget,
    RuntimeDecisionRecord,
)
from .runtime_gateway import RuntimeGateway
from .policy_engine import PolicyEngine
from .authority_graph import AuthorityGraphEngine, FINANCE_SEED_GRAPH
from .risk_engine import RiskEngine, RiskScore
from .conflict_detector import ConflictDetector
from .decorator import governed, GovernanceBlockedError, GovernanceEscalatedError
from .rate_limit import (
    BackendResult,
    InMemoryRateLimitBackend,
    RateLimitBackend,
    RateLimitBackendError,
)


def register_hook(hook_type: str, fn):
    """Register a runner lifecycle hook (Phase 17 / T1.10).

    Valid hook_type values: ``SessionStart``, ``SessionEnd``, ``PreToolUse``,
    ``PostToolUse``, ``SubagentStop``.  Hooks are only invoked when you
    drive the CLI runner via ``run_agent`` or ``agentctrl run``; direct
    ``RuntimeGateway.validate`` calls bypass them by design.
    """
    # Deferred import — the runner pulls in LangChain at module load time
    # only if you actually use it.  Registering hooks must not force that
    # dep on callers that just want governance.
    from .runner import register_hook as _register
    return _register(hook_type, fn)


def clear_hooks(hook_type=None):
    """Clear one hook type (or all) — primarily a test aid."""
    from .runner import clear_hooks as _clear
    return _clear(hook_type)


def run_agent(*args, **kwargs):
    """Programmatic entrypoint for the CLI runner.

    See ``agentctrl.runner.run_agent`` for the full signature.  This
    shim exists so callers can import from the package root without
    triggering LangChain imports eagerly.
    """
    from .runner import run_agent as _run
    return _run(*args, **kwargs)


__all__ = [
    "ActionProposal",
    "PipelineStageResult",
    "PipelineHooks",
    "EscalationTarget",
    "RuntimeDecisionRecord",
    "RuntimeGateway",
    "PolicyEngine",
    "AuthorityGraphEngine",
    "FINANCE_SEED_GRAPH",
    "RiskEngine",
    "RiskScore",
    "ConflictDetector",
    "governed",
    "GovernanceBlockedError",
    "GovernanceEscalatedError",
    # Cluster-safe rate-limit backend protocol (consumer implements Redis/etc.)
    "BackendResult",
    "InMemoryRateLimitBackend",
    "RateLimitBackend",
    "RateLimitBackendError",
    # Phase 17 (runner lifecycle hooks + programmatic runner entry point)
    "register_hook",
    "clear_hooks",
    "run_agent",
]
