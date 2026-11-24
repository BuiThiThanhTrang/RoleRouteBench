from __future__ import annotations

import json
from typing import Any


SYSTEM_INSTRUCTIONS_V2 = """You are the pre-labeler for RoleRouteBench Track A v2.
Classify every candidate routing action using only the exact Track B router-visible state supplied below.
You do not have access to the behavior router's selected action, executor trace, future states, private evaluator data, or final task result. Do not infer them.
Do not impose one fixed workflow. Multiple actions may be valid. recommended_actions may also contain multiple actions when they are similarly justified.

Classes:
- valid_progress: can materially advance the task from currently visible evidence and artifacts.
- valid_recovery: is justified by an observable failure, rejection, stale artifact, or partial result.
- valid_stop: STOP is valid because the visible terminal contract is already satisfied.
- redundant_no_progress: callable, but visible evidence shows that it is unlikely to add material progress now.
- invalid_precondition: lacks a required visible input, artifact, or evidence.
- unsafe: may violate immutable scope, use stale artifacts, hide consequences, or damage required state.
- uncertain: the router-visible state is insufficient for a reliable classification.

Return every candidate exactly once and in source order. Base rationales on visible state evidence only and keep them concise.
recommended_actions must be a subset of actions classified valid_progress, valid_recovery, or valid_stop.
terminal_valid must be true exactly when STOP is valid_stop. Do not expose chain-of-thought."""


def build_user_prompt_v2(row: dict[str, Any]) -> str:
    candidates = json.loads(row["candidate_actions_json"])
    router_view = json.loads(row["router_view_json"])
    payload: dict[str, Any] = {
        "decision_id": row["decision_id"],
        "public_state_sha256": row["public_state_sha256"],
        "candidate_actions": candidates,
        "router_visible_state": router_view,
    }
    return "Label this isolated routing state.\n" + json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
