# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in `agentctrl`, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, use [GitHub's private security advisory feature](https://github.com/moeintel/AgentCTRL/security/advisories/new) or email **security@moeintel.ai**.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

We will acknowledge receipt within 48 hours and provide a fix or mitigation plan within 7 days for critical issues.

---

## Security Model

`agentctrl` is a governance enforcement library. It evaluates agent actions against policies, authority graphs, and risk scores, then returns ALLOW / ESCALATE / BLOCK decisions.

### What agentctrl enforces

- **Fail-closed design.** Any error in the governance pipeline produces BLOCK, never ALLOW. Three independent layers enforce this (gateway catch, stage-level catch, top-level catch).
- **Deterministic evaluation.** Policy matching, authority resolution, and risk scoring are all deterministic — no LLM calls, no prompt engineering, no probabilistic behavior.
- **Structural enforcement.** Policies use operator-based rule matching. Authority is graph traversal. Risk is weighted factor scoring. None of this is prompt-based.

### What agentctrl does NOT enforce

- **Caller identity verification.** `agent_id` is a self-declared string. The library does not verify that the caller actually is that agent. Your application is responsible for identity.
- **Bypass prevention.** If a tool is called directly without going through `RuntimeGateway` or `@governed`, agentctrl has no visibility. Governance only covers actions routed through the library.
- **Persistence.** The library is stateless by default. Rate limiting uses in-memory counters that reset on restart. For durable state, integrate with your own storage.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |
| < 0.3   | No        |

Security fixes will be applied to the latest release.
