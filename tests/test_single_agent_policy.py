import json
from pathlib import Path
import unittest

import yaml

from routing_benchmark.v4.execution.adapters.database import DatabaseMigrationAdapter, ROLE_TOOLS
from routing_benchmark.v4.execution.adapters.external_code_debugging import (
    CANONICAL_CODE_ROLES,
    ExternalCodeDebuggingAdapter,
)
from routing_benchmark.v4.execution.adapters.formal_proof import FormalProofAdapter, ROLES
from routing_benchmark.v4.execution.adapters.table_qa import ROLE_TO_TOOL, TableQAAdapter
from routing_benchmark.v4.execution.single_agent_policy import SingleAgentPolicy
from scripts.run_shared_environment import build_router


PROJECT = Path(__file__).resolve().parents[1]
CONFIGS = (
    "database_single_agent_qwen9b.yaml",
    "code_single_agent_gemini25flash.yaml",
    "formal_single_agent_goedel32b.yaml",
    "table_qa_single_agent_qwen9b.yaml",
)


class SingleAgentPolicyTests(unittest.TestCase):
    def test_dispatches_generalist_until_public_terminal(self):
        policy = SingleAgentPolicy("Generalist")
        actions = ["Generalist", "STOP"]

        active = policy.select({"current_state": {"terminal": False}}, actions)
        terminal = policy.select({"current_state": {"terminal": True}}, actions)

        self.assertEqual(active.action, "Generalist")
        self.assertEqual(terminal.action, "STOP")
        self.assertTrue(terminal.metadata["terminal_short_circuit"])

    def test_configs_bind_exactly_one_generalist(self):
        root = PROJECT / "config/shared_environment"
        for name in CONFIGS:
            with self.subTest(config=name):
                config = yaml.safe_load((root / name).read_text(encoding="utf-8"))
                roles = json.loads((PROJECT / config["role_cards"]).read_text(encoding="utf-8"))

                self.assertEqual(len(roles), 1)
                self.assertEqual(roles[0]["tool_access"], "all_domain_tools")
                self.assertEqual(config["router"]["agent_id"], roles[0]["agent_id"])
                self.assertIsInstance(build_router(config["router"], config["seed"]), SingleAgentPolicy)

    def test_generalists_receive_each_domain_tool_union(self):
        root = PROJECT / "config/shared_environment"
        cases = (
            (DatabaseMigrationAdapter(), ROLE_TOOLS, "database_single_agent_role.json"),
            (ExternalCodeDebuggingAdapter(), CANONICAL_CODE_ROLES, "code_single_agent_role.json"),
            (FormalProofAdapter(), ROLES, "formal_single_agent_role.json"),
            (TableQAAdapter(), ROLE_TO_TOOL, "table_qa_single_agent_role.json"),
        )
        for adapter, specialist_roles, role_file in cases:
            with self.subTest(adapter=adapter.adapter_id):
                generalist = json.loads((root / role_file).read_text(encoding="utf-8"))[0]
                expected = {
                    spec.name
                    for role in specialist_roles
                    for spec in adapter.tool_spec(None, role, {"agent_id": role})
                }
                actual = {
                    spec.name
                    for spec in adapter.tool_spec(None, generalist["agent_id"], generalist)
                }
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
