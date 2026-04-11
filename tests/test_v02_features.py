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

"""Tests for v0.2.0 features: subscriptable record, audit log, CLI, demo, empty authority."""

import json
import os
import subprocess
import sys
import tempfile

import pytest


class TestSubscriptableRecord:
    @pytest.mark.asyncio
    async def test_attribute_and_subscript_access(self):
        from agentctrl import RuntimeGateway, ActionProposal
        gw = RuntimeGateway()
        r = await gw.validate(ActionProposal(
            agent_id="agent-1", action_type="invoice.approve",
            action_params={"amount": 100}, autonomy_level=2))
        assert r.decision == r["decision"]
        assert r.risk_score == r["risk_score"]
        assert r.agent_id == r["agent_id"]

    @pytest.mark.asyncio
    async def test_get_with_default(self):
        from agentctrl import RuntimeGateway, ActionProposal
        gw = RuntimeGateway()
        r = await gw.validate(ActionProposal(
            agent_id="agent-1", action_type="invoice.approve",
            action_params={"amount": 100}, autonomy_level=2))
        assert r.get("decision") is not None
        assert r.get("nonexistent_field", "fallback") == "fallback"

    @pytest.mark.asyncio
    async def test_contains(self):
        from agentctrl import RuntimeGateway, ActionProposal
        gw = RuntimeGateway()
        r = await gw.validate(ActionProposal(
            agent_id="agent-1", action_type="invoice.approve",
            action_params={"amount": 100}, autonomy_level=2))
        assert "decision" in r
        assert "pipeline" in r
        assert "pipeline_stages" in r
        assert "nonexistent" not in r

    @pytest.mark.asyncio
    async def test_to_dict(self):
        from agentctrl import RuntimeGateway, ActionProposal
        gw = RuntimeGateway()
        r = await gw.validate(ActionProposal(
            agent_id="agent-1", action_type="invoice.approve",
            action_params={"amount": 100}, autonomy_level=2))
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == r.decision
        assert isinstance(d["decided_at"], str)


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_writes_jsonl(self):
        from agentctrl import RuntimeGateway, ActionProposal
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            gw = RuntimeGateway(audit_log=path)
            await gw.validate(ActionProposal(
                agent_id="agent-1", action_type="data.read",
                action_params={"amount": 100}, autonomy_level=2))
            await gw.validate(ActionProposal(
                agent_id="agent-2", action_type="invoice.approve",
                action_params={"amount": 200}, autonomy_level=2))
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            record = json.loads(lines[0])
            assert "decision" in record
            assert "agent_id" in record
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_audit_log_chains_with_hook(self):
        from agentctrl import RuntimeGateway, ActionProposal, PipelineHooks
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
        hook_records = []
        try:
            gw = RuntimeGateway(
                audit_log=path,
                hooks=PipelineHooks(on_audit=lambda r: hook_records.append(r)),
            )
            await gw.validate(ActionProposal(
                agent_id="agent-1", action_type="data.read",
                action_params={}, autonomy_level=2))
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            assert len(hook_records) == 1
        finally:
            os.unlink(path)


class TestEmptyAuthorityDefault:
    @pytest.mark.asyncio
    async def test_empty_graph_passes_authority(self):
        from agentctrl import AuthorityGraphEngine, ActionProposal
        engine = AuthorityGraphEngine()
        result = await engine.resolve(ActionProposal(
            agent_id="any-agent", action_type="anything",
            action_params={}, autonomy_level=2))
        assert result.status == "PASS"
        assert "No authority graph configured" in result.reason

    @pytest.mark.asyncio
    async def test_full_pipeline_without_authority_graph(self):
        from agentctrl import RuntimeGateway, ActionProposal
        gw = RuntimeGateway()
        r = await gw.validate(ActionProposal(
            agent_id="agent-1", action_type="invoice.approve",
            action_params={"amount": 100}, autonomy_level=2,
            trust_context={"total_actions": 10, "success_rate": 0.95}))
        assert r.decision == "ALLOW"


class TestConflictDetectorIsolation:
    @pytest.mark.asyncio
    async def test_separate_instances_are_isolated(self):
        from agentctrl import ConflictDetector
        cd1 = ConflictDetector()
        cd2 = ConflictDetector()
        await cd1.register_workflow("wf-1", ["resource:A"])
        assert len(cd1._active_workflows) == 1
        assert len(cd2._active_workflows) == 0


class TestDemo:
    def test_demo_runs_without_error(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentctrl"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
        )
        assert result.returncode == 0
        assert "ALLOW" in result.stdout
        assert "ESCALATE" in result.stdout
        assert "BLOCK" in result.stdout


class TestCLI:
    def test_cli_validate(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentctrl.cli", "validate",
             '{"agent_id": "test", "action_type": "invoice.approve", "action_params": {"amount": 100}}'],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
        )
        assert result.returncode == 0
        assert "ALLOW" in result.stdout or "ESCALATE" in result.stdout

    def test_cli_validate_json_output(self):
        result = subprocess.run(
            [sys.executable, "-m", "agentctrl.cli", "validate", "--json",
             '{"agent_id": "test", "action_type": "invoice.approve", "action_params": {"amount": 6000}}'],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "decision" in data

    def test_cli_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, "test-init")
            result = subprocess.run(
                [sys.executable, "-m", "agentctrl.cli", "init", "--dir", target],
                capture_output=True, text=True, timeout=10,
                cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            )
            assert result.returncode == 0
            assert os.path.exists(os.path.join(target, "policies.json"))
            assert os.path.exists(os.path.join(target, "authority.json"))
