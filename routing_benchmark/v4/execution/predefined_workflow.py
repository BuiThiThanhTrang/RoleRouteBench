"""Deterministic, YAML-configured workflows for shared-environment baselines."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from routing_benchmark.routers import RoutingDecision


class PredefinedWorkflowPolicy:
    """Dispatch an exact sequence, with an optional public-terminal short circuit.

    The cursor advances for every selected workflow action, including actions that
    the environment later rejects.  This is intentional: the policy represents a
    literal predefined trajectory rather than a hidden state-aware router.
    """

    name = "predefined_workflow"

    def __init__(self, sequence: Sequence[str], *, stop_on_terminal: bool = True):
        if isinstance(sequence, (str, bytes)) or not sequence:
            raise ValueError("predefined_workflow requires a non-empty sequence")
        normalized = tuple(str(action).strip() for action in sequence)
        if any(not action for action in normalized):
            raise ValueError("predefined_workflow actions must be non-empty strings")
        if not isinstance(stop_on_terminal, bool):
            raise ValueError("stop_on_terminal must be a boolean")
        self.sequence = normalized
        self.stop_on_terminal = stop_on_terminal
        self.index = 0

    def reset(self, seed=None):
        del seed
        self.index = 0

    @staticmethod
    def _public_terminal(observation: Mapping) -> bool:
        state = observation.get("current_state") or {}
        return isinstance(state, Mapping) and state.get("terminal") is True

    def select(self, observation, candidate_actions, oracle_valid_actions=None):
        del oracle_valid_actions
        terminal_short_circuit = self.stop_on_terminal and self._public_terminal(observation)
        if terminal_short_circuit or self.index >= len(self.sequence):
            action = "STOP"
            workflow_step = self.index
        else:
            workflow_step = self.index
            action = self.sequence[self.index]
            self.index += 1
        if action not in candidate_actions:
            raise ValueError(f"Predefined workflow action is unavailable: {action}")
        return RoutingDecision(action, {
            "policy": self.name,
            "workflow_step": workflow_step,
            "workflow_length": len(self.sequence),
            "terminal_short_circuit": terminal_short_circuit,
        })
