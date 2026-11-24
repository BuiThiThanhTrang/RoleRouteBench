"""One-generalist baseline for shared-environment benchmarks."""
from __future__ import annotations

from collections.abc import Mapping

from routing_benchmark.routers import RoutingDecision


class SingleAgentPolicy:
    """Dispatch one configured generalist until public terminal state is reached."""

    name = "single_agent"

    def __init__(self, agent_id: str):
        self.agent_id = str(agent_id).strip()
        if not self.agent_id:
            raise ValueError("single_agent requires a non-empty agent_id")

    def reset(self, seed=None):
        del seed

    @staticmethod
    def _public_terminal(observation: Mapping) -> bool:
        state = observation.get("current_state") or {}
        return isinstance(state, Mapping) and state.get("terminal") is True

    def select(self, observation, candidate_actions, oracle_valid_actions=None):
        del oracle_valid_actions
        terminal = self._public_terminal(observation)
        action = "STOP" if terminal else self.agent_id
        if action not in candidate_actions:
            raise ValueError(f"Single-agent action is unavailable: {action}")
        return RoutingDecision(action, {
            "policy": self.name,
            "agent_id": self.agent_id,
            "terminal_short_circuit": terminal,
        })
