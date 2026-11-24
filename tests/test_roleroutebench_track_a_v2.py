from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from routing_benchmark.roleroutebench.track_a.schema_v2 import (
    prelabel_json_schema_v2,
    validate_prelabel_v2,
)


class TrackAV2SchemaTest(unittest.TestCase):
    def test_recommended_actions_must_be_valid_candidates(self) -> None:
        candidates = ["Inspector", "Executor", "STOP"]
        payload = {
            "actions": [
                {"action": "Inspector", "classification": "valid_progress", "rationale": "Evidence is absent."},
                {"action": "Executor", "classification": "invalid_precondition", "rationale": "No input artifact."},
                {"action": "STOP", "classification": "invalid_precondition", "rationale": "Not terminal."},
            ],
            "recommended_actions": ["Inspector"],
            "recommendation_confidence": "high",
            "terminal_valid": False,
            "recovery_opportunity": False,
            "expected_progress_kind": "evidence_collection",
            "state_phase": "initial",
            "confidence": "high",
            "summary": "Inspect first.",
        }
        self.assertEqual(validate_prelabel_v2(payload, candidates), [])
        payload["recommended_actions"] = ["Executor"]
        self.assertTrue(validate_prelabel_v2(payload, candidates))

    def test_provider_schema_avoids_unique_items_but_validator_rejects_duplicates(self) -> None:
        candidates = ["Inspector", "Executor", "STOP"]
        schema = prelabel_json_schema_v2()
        self.assertNotIn("uniqueItems", schema["properties"]["recommended_actions"])

        payload = {
            "actions": [
                {"action": "Inspector", "classification": "valid_progress", "rationale": "Inspect evidence."},
                {"action": "Executor", "classification": "invalid_precondition", "rationale": "No artifact."},
                {"action": "STOP", "classification": "invalid_precondition", "rationale": "Not terminal."},
            ],
            "recommended_actions": ["Inspector", "Inspector"],
            "recommendation_confidence": "high",
            "terminal_valid": False,
            "recovery_opportunity": False,
            "expected_progress_kind": "evidence_collection",
            "state_phase": "initial",
            "confidence": "high",
            "summary": "Duplicate recommendations must fail local validation.",
        }
        errors = validate_prelabel_v2(payload, candidates)
        self.assertIn("recommended_actions must be unique", errors)


class TrackAV2BuiltArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1] / "data" / "RoleRouteBench" / "track_a_4d_multirouter_v2"
        cls.states = [
            json.loads(line)
            for line in (cls.root / "track_a_states.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_phase3_is_balanced_and_has_no_duplicate_public_states(self) -> None:
        counts = Counter(row["domain"] for row in self.states)
        self.assertEqual(
            set(counts),
            {
                "code_debugging",
                "database_migration_integrity",
                "formal_proof",
                "structured_data_processing",
            },
        )
        self.assertGreaterEqual(len(self.states), 950)
        self.assertLessEqual(len(self.states), 1000)
        self.assertTrue(all(value <= 250 for value in counts.values()))
        self.assertLessEqual(max(counts.values()) - min(counts.values()), 5)
        hashes = [row["public_state_sha256"] for row in self.states]
        self.assertEqual(len(hashes), len(set(hashes)))

    def test_public_rows_keep_exact_router_view_but_no_outcome(self) -> None:
        forbidden = {"decision", "trajectory", "episode_result", "selected_action", "valid_actions"}
        for row in self.states:
            self.assertFalse(forbidden.intersection(row), row["decision_id"])
            router_view = json.loads(row["router_view_json"])
            self.assertEqual(router_view["observation"], json.loads(row["router_input_json"]))
            self.assertEqual(router_view["candidate_actions"], json.loads(row["candidate_actions_json"]))

    def test_phase4_input_is_frozen_phase3_selection(self) -> None:
        phase4 = [
            json.loads(line)
            for line in (self.root / "labeling_terra_v2" / "sample_states.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(phase4, self.states)


if __name__ == "__main__":
    unittest.main()
