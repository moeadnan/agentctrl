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

"""agentctrl CLI — demo, validate, init.

Usage:
    agentctrl demo              Run the governance pipeline demo
    agentctrl validate          Validate a JSON action proposal
    agentctrl init              Scaffold starter config files
"""

import argparse
import asyncio
import json
import pathlib
import sys


def cmd_demo(args):
    """Run the theatrical demo (delegates to __main__)."""
    from .__main__ import main as demo_main
    demo_main()


def cmd_validate(args):
    """Validate a JSON action proposal against the pipeline."""
    from . import RuntimeGateway, ActionProposal, PolicyEngine

    raw = args.proposal
    if raw == "-":
        raw = sys.stdin.read()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    proposal = ActionProposal(
        agent_id=data.get("agent_id", "cli-agent"),
        action_type=data.get("action_type", "unknown"),
        action_params=data.get("action_params", {}),
        autonomy_level=data.get("autonomy_level", 2),
    )

    kwargs = {}
    if args.policies:
        kwargs["policy_engine"] = PolicyEngine.from_file(args.policies)
    if args.audit_log:
        kwargs["audit_log"] = args.audit_log

    gateway = RuntimeGateway(**kwargs)
    result = asyncio.run(gateway.validate(proposal))

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        color = {"ALLOW": "\033[32m", "ESCALATE": "\033[33m", "BLOCK": "\033[31m"}.get(result.decision, "")
        reset = "\033[0m"
        print(f"{color}{result.decision}{reset}  {result.action_type}  risk={result.risk_score:.2f} ({result.risk_level})")
        if result.decision != "ALLOW":
            print(f"  → {result.reason}")


INIT_POLICIES = """\
{
  "policies": [
    {
      "id": "high_value_threshold",
      "name": "High Value Transaction Threshold",
      "scope": "finance",
      "priority": 10,
      "rules": [
        {
          "action_type": "invoice.approve",
          "conditions": [{"param": "amount", "op": "gt", "value": 5000}],
          "condition_logic": "AND",
          "action": "ESCALATE",
          "target": "manager",
          "reason": "Transaction exceeds $5,000 autonomous threshold."
        }
      ]
    },
    {
      "id": "pii_access",
      "name": "PII Data Access",
      "scope": "global",
      "rules": [
        {
          "action_type": "data.*",
          "conditions": [{"param": "classification", "op": "eq", "value": "PII"}],
          "condition_logic": "AND",
          "action": "ESCALATE",
          "target": "data_owner",
          "reason": "PII data access requires data owner approval."
        }
      ]
    }
  ]
}
"""

INIT_AUTHORITY = """\
{
  "nodes": [
    {"id": "admin", "label": "Admin", "type": "role",
     "financial_limit": null, "action_scopes": ["*"]},
    {"id": "analyst", "label": "Analyst Agent", "type": "agent",
     "financial_limit": 5000, "action_scopes": ["invoice.approve", "data.read", "report.generate"]}
  ],
  "edges": [
    {"parent": "admin", "child": "analyst", "type": "delegation", "financial_limit": 5000}
  ],
  "separation_of_duty": []
}
"""


def cmd_init(args):
    """Scaffold starter governance config files."""
    target = pathlib.Path(args.dir)
    target.mkdir(parents=True, exist_ok=True)

    policies_path = target / "policies.json"
    authority_path = target / "authority.json"

    wrote = []
    if not policies_path.exists():
        policies_path.write_text(INIT_POLICIES)
        wrote.append(str(policies_path))
    else:
        print(f"  skip  {policies_path} (already exists)")

    if not authority_path.exists():
        authority_path.write_text(INIT_AUTHORITY)
        wrote.append(str(authority_path))
    else:
        print(f"  skip  {authority_path} (already exists)")

    if wrote:
        print(f"Created {len(wrote)} file(s):")
        for f in wrote:
            print(f"  → {f}")
        print()
        print("Quick start:")
        print(f'  agentctrl validate --policies {target / "policies.json"} \\')
        print('    \'{"agent_id": "analyst", "action_type": "invoice.approve", "action_params": {"amount": 6000}}\'')
    else:
        print("No files created (all already exist).")


def main():
    parser = argparse.ArgumentParser(
        prog="agentctrl",
        description="Institutional control layer for AI agent actions.",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("demo", help="Run the governance pipeline demo")

    val_p = sub.add_parser("validate", help="Validate a JSON action proposal")
    val_p.add_argument("proposal", nargs="?", default="-",
                       help="JSON string or '-' for stdin")
    val_p.add_argument("--policies", help="Path to policies JSON/YAML file")
    val_p.add_argument("--audit-log", help="Path to JSONL audit log file")
    val_p.add_argument("--json", action="store_true", help="Output full JSON result")

    init_p = sub.add_parser("init", help="Scaffold starter config files")
    init_p.add_argument("--dir", default=".agentctrl",
                        help="Directory for config files (default: .agentctrl)")

    args = parser.parse_args()

    if args.command == "demo":
        cmd_demo(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "init":
        cmd_init(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
