import json
from pathlib import Path
import unittest

import yaml

from routing_benchmark.v4.execution.predefined_workflow import PredefinedWorkflowPolicy
from scripts.run_shared_environment import build_router


PROJECT = Path(__file__).resolve().parents[1]
CONFIGS = (
    "database_predefined_qwen9b.yaml",
    "code_predefined_gemini25flash.yaml",
    "formal_predefined_goedel32b.yaml",
    "table_qa_predefined_qwen9b.yaml",
)


class PredefinedWorkflowPolicyTests(unittest.TestCase):
    def test_exact_sequence_then_stop(self):
        policy = PredefinedWorkflowPolicy(["A", "B"])
        policy.reset(42)
        observation = {"current_state": {"terminal": False}}
        actions = ["A", "B", "STOP"]

        decisions = [policy.select(observation, actions) for _ in range(3)]

        self.assertEqual([decision.action for decision in decisions], ["A", "B", "STOP"])
        self.assertEqual(decisions[0].metadata["workflow_step"], 0)
        self.assertEqual(decisions[1].metadata["workflow_step"], 1)

    def test_public_terminal_stops_without_consuming_next_step(self):
        policy = PredefinedWorkflowPolicy(["A", "B"], stop_on_terminal=True)
        policy.reset()
        terminal = {"current_state": {"terminal": True}}
        active = {"current_state": {"terminal": False}}
        actions = ["A", "B", "STOP"]

        stop = policy.select(terminal, actions)
        first = policy.select(active, actions)

        self.assertEqual(stop.action, "STOP")
        self.assertTrue(stop.metadata["terminal_short_circuit"])
        self.assertEqual(first.action, "A")

    def test_unavailable_configured_action_fails_closed(self):
        policy = PredefinedWorkflowPolicy(["missing"])
        policy.reset()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            policy.select({"current_state": {"terminal": False}}, ["STOP"])

    def test_domain_workflows_are_valid_and_fit_call_budget(self):
        config_root = PROJECT / "config/shared_environment"
        for name in CONFIGS:
            with self.subTest(config=name):
                config = yaml.safe_load((config_root / name).read_text(encoding="utf-8"))
                role_path = PROJECT / config["role_cards"]
                roles = json.loads(role_path.read_text(encoding="utf-8"))
                actions = {role["agent_id"] for role in roles}
                sequence = config["router"]["sequence"]

                self.assertLessEqual(len(sequence), config["max_calls"])
                self.assertTrue(set(sequence) <= actions)
                policy = build_router(config["router"], config["seed"])
                self.assertIsInstance(policy, PredefinedWorkflowPolicy)


if __name__ == "__main__":
    unittest.main()
