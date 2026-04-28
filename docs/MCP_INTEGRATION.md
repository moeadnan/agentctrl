# MCP Integration

> **Status:** Shipped. MCP tool calls traverse the same 5-stage governance pipeline as native tool calls. Verified end-to-end in the platform's integration test suite.
>
> **Last verified:** April 2026, agent-model migration §Phase 5.

This document describes how the AgentCTRL platform integrates with [Anthropic's Model Context Protocol](https://modelcontextprotocol.io/) and what governance guarantees apply to MCP tool calls.

It distinguishes two concerns that are often conflated:

1. The **standalone `agentctrl` library** — a governance toolkit you install via pip. It does not ship an MCP adapter; you wire its `RuntimeGateway` into your own MCP integration.
2. The **AgentCTRL platform** — a hosted product that ships a working `McpAdapter`, discovers MCP tools at startup, and runs every MCP tool call through the same governance pipeline as native tools.

If you are building on top of the library, see [Library: governing your own MCP integration](#library-governing-your-own-mcp-integration). If you are operating the platform, see [Platform: how MCP tool calls are governed](#platform-how-mcp-tool-calls-are-governed).

---

## Platform: how MCP tool calls are governed

### The chain

```
LLM emits MCP tool call
        │
        ▼
ReAct agent (react_agent.py)
        │   builds an ActionProposal for the tool
        ▼
GovernanceEngine.evaluate(proposal)            ← 5-stage pipeline
        │   ├─ Kill switch (pre-gate)
        │   ├─ Autonomy check
        │   ├─ Policy engine
        │   ├─ Authority graph
        │   ├─ Risk engine
        │   └─ Conflict detector
        ▼
GovernanceDecision  ──── BLOCK or ESCALATE? ──→ stop, no execution
        │
        ▼ (ALLOW only)
governed_execute() enables _GOVERNANCE_APPROVED context
        │
        ▼
McpAdapter.execute(ApprovedAction)             ← execution/mcp.py
        │
        ▼
tools.registry.execute_tool(name, params)      ← tools/registry.py
        │   Re-checks _GOVERNANCE_APPROVED.
        │   If unset (someone bypassed governed_execute) → fail-closed,
        │   increment governance-violation tripwire counter.
        ▼
The MCP server is invoked (HTTP/SSE or stdio transport).
        │
        ▼
governed_execute() disables _GOVERNANCE_APPROVED, writes audit entry.
```

### Why this is impossible to bypass accidentally

Two independent guards must both be satisfied for an MCP tool to run:

| Guard | What it checks | Failure mode |
|---|---|---|
| `governed_execute(...)` | Pipeline returns ALLOW | Returns `BLOCK` / `ESCALATE` outcome with `executed=False`. |
| `tools.registry.execute_tool` | Caller is inside `_GOVERNANCE_APPROVED` context | Returns `{"success": False, "error": "Tool '...' cannot execute outside a governance-approved context."}` and increments the **governance-violation tripwire counter**. |

The contextvar is set only by `governed_execute()` and reset in its `finally` block. There is no public API that enables it without going through the pipeline. Any new code path that tries to call MCP tools by hand will fail closed and trip the counter — which makes review-time detection trivial.

### Where MCP tools live in the registry

`tools/mcp_adapter.py` discovers MCP tools at app startup (or via `POST /mcp/servers/reload`) and registers each one in the **shared** tool registry under `category="mcp"`, with the name `mcp.<server>.<tool>`. They are indistinguishable from native tools as far as the governance pipeline is concerned — this is by design.

### Verified by tests

The platform ships three test files that exercise the MCP governance guarantees:

- **`test_mcp_governance.py`** (integration) — proves the four cases for an MCP-namespaced tool:
  - **BLOCK** decision → MCP tool's body never runs.
  - **ESCALATE** decision → MCP tool's body never runs (suspended for review).
  - **ALLOW** decision → MCP tool runs and the result propagates.
  - **Direct `execute_tool` bypass attempt** → fails closed via the registry guard.
- **`test_governance_context_guard.py`** (unit) — proves the contextvar is reset after every governed execution, so a leaked context cannot let a later call slip through.
- **`test_governance_under_failure.py`** (unit) — proves the violation tripwire counter increments when an ungoverned call is attempted.

### What is NOT yet covered

Honest about scope so this doc doesn't drift:

- **MCP resources** (read-only data exposed by an MCP server) are not yet a first-class governed surface. The platform discovers tools (`mcp/list_tools`) but does not currently surface MCP resources or prompts to the agent. When that work lands, this section will be updated.
- **MCP sampling** (server-initiated LLM calls back to the client) is not exposed by AgentCTRL today.
- **Per-server policy scoping** is implicit through tool-name policies (`policy.action_type == "mcp.<server>.<tool>"`); there is no dedicated "MCP server" entity in the policy schema. If you need per-server controls, write policies that match the `mcp.<server>.*` prefix.
- **Streaming responses** from MCP tools are not separately governed beyond the initial tool call's ALLOW decision; long-running streams continue under the original approval.

These gaps are real. They do not affect the core guarantee — every MCP **tool invocation** is governed — but they bound the surface area we can claim.

---

## Library: governing your own MCP integration

The standalone `agentctrl` library (installable via pip) does **not** ship an MCP adapter. It ships the governance primitives — `RuntimeGateway`, `ActionProposal`, `PolicyEngine`, etc. — and you wire them into your own MCP integration.

The pattern mirrors what the platform does:

```python
from agentctrl import RuntimeGateway, ActionProposal, PolicyEngine

gateway = RuntimeGateway(
    policy_engine=PolicyEngine(policies=[
        # … your policies …
    ]),
)

async def call_mcp_tool(tool_name: str, params: dict, agent_id: str):
    """Wrap every outbound MCP call with the gateway."""
    proposal = ActionProposal(
        agent_id=agent_id,
        action_type=f"mcp.{tool_name}",
        action_params=params,
        autonomy_level=2,
    )
    result = await gateway.validate(proposal)
    if result.decision != "ALLOW":
        raise PermissionError(f"MCP call blocked: {result.reason}")

    # Only now invoke the MCP server.
    return await your_mcp_client.call_tool(tool_name, params)
```

For inbound MCP (your service exposing MCP tools to external agents), see the existing `Inbound Governance` section in the [README](../README.md#inbound-governance--controlling-external-agents) and the worked example in [`examples/inbound_governance.py`](../examples/inbound_governance.py).

---

## Frequently asked

**Does the gateway add latency to every MCP call?**
The pipeline runs in-process (no network hop) and completes in single-digit milliseconds for typical policies. Risk scoring + conflict detection are the largest contributors; both can be tuned via policy configuration.

**What about MCP servers running in the same process?**
The transport (HTTP/SSE vs stdio) is irrelevant to governance — both routes funnel through the same `McpAdapter.execute → execute_tool` path.

**Can a privileged agent bypass governance for MCP calls?**
No. Trust and autonomy levels modulate which pipeline stages produce ESCALATE vs ALLOW; they never let an action skip the pipeline entirely. There is no escape hatch by design.

**How do I see what governance decisions an MCP-using agent has made?**
Use the run-trace inspector on the agent detail page (Activity tab → Recent Runs → click any row). The drawer surfaces the engine decision and the correlated tool calls, including MCP ones.
