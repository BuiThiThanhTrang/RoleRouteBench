from __future__ import annotations

from typing import Any


LABEL_CONTRACT_VERSION = "roleroutebench.track_a.labels.v2"
PROMPT_VERSION = "roleroutebench.track_a.terra.v2"

ACTION_CLASSES = (
    "valid_progress",
    "valid_recovery",
    "valid_stop",
    "redundant_no_progress",
    "invalid_precondition",
    "unsafe",
    "uncertain",
)

STATE_PHASES = (
    "initial",
    "evidence_collection",
    "candidate_authoring",
    "execution",
    "failure_diagnosis",
    "repair_or_recovery",
    "validation",
    "terminal",
)

PROGRESS_KINDS = (
    "evidence_collection",
    "diagnosis",
    "artifact_authoring",
    "execution",
    "verification",
    "recovery",
    "termination",
    "none",
    "uncertain",
)


def prelabel_json_schema_v2() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "classification": {"type": "string", "enum": list(ACTION_CLASSES)},
                        "rationale": {"type": "string"},
                    },
                    "required": ["action", "classification", "rationale"],
                    "additionalProperties": False,
                },
            },
            # OpenAI/Azure strict structured outputs reject the JSON Schema
            # ``uniqueItems`` keyword. The local validator below still
            # enforces uniqueness as part of the Track A label contract.
            "recommended_actions": {"type": "array", "items": {"type": "string"}},
            "recommendation_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "terminal_valid": {"type": "boolean"},
            "recovery_opportunity": {"type": "boolean"},
            "expected_progress_kind": {"type": "string", "enum": list(PROGRESS_KINDS)},
            "state_phase": {"type": "string", "enum": list(STATE_PHASES)},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "summary": {"type": "string"},
        },
        "required": [
            "actions",
            "recommended_actions",
            "recommendation_confidence",
            "terminal_valid",
            "recovery_opportunity",
            "expected_progress_kind",
            "state_phase",
            "confidence",
            "summary",
        ],
        "additionalProperties": False,
    }


def validate_prelabel_v2(payload: dict[str, Any], candidate_actions: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["prelabel must be an object"]
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return ["actions must be an array"]
    seen: list[str] = []
    by_action: dict[str, str] = {}
    for index, item in enumerate(actions):
        if not isinstance(item, dict):
            errors.append(f"actions[{index}] must be an object")
            continue
        action = item.get("action")
        classification = item.get("classification")
        rationale = item.get("rationale")
        if not isinstance(action, str):
            errors.append(f"actions[{index}].action must be a string")
            continue
        seen.append(action)
        if action in by_action:
            errors.append(f"duplicate action: {action}")
        if classification not in ACTION_CLASSES:
            errors.append(f"invalid classification for {action}: {classification}")
        else:
            by_action[action] = classification
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"missing rationale for {action}")
    if seen != candidate_actions:
        errors.append("actions must exactly match candidate_actions in source order")
    recommended = payload.get("recommended_actions")
    if not isinstance(recommended, list) or any(not isinstance(item, str) for item in recommended):
        errors.append("recommended_actions must be an array of strings")
        recommended = []
    elif len(recommended) != len(set(recommended)):
        errors.append("recommended_actions must be unique")
    for action in recommended:
        if action not in candidate_actions:
            errors.append(f"recommended action is not a candidate: {action}")
        elif by_action.get(action) not in {"valid_progress", "valid_recovery", "valid_stop"}:
            errors.append(f"recommended action is not classified valid: {action}")
    if payload.get("state_phase") not in STATE_PHASES:
        errors.append("invalid state_phase")
    if payload.get("expected_progress_kind") not in PROGRESS_KINDS:
        errors.append("invalid expected_progress_kind")
    if payload.get("confidence") not in {"low", "medium", "high"}:
        errors.append("invalid confidence")
    if payload.get("recommendation_confidence") not in {"low", "medium", "high"}:
        errors.append("invalid recommendation_confidence")
    if not isinstance(payload.get("terminal_valid"), bool):
        errors.append("terminal_valid must be boolean")
    if not isinstance(payload.get("recovery_opportunity"), bool):
        errors.append("recovery_opportunity must be boolean")
    stop_class = by_action.get("STOP")
    if stop_class == "valid_stop" and payload.get("terminal_valid") is not True:
        errors.append("STOP=valid_stop requires terminal_valid=true")
    if payload.get("terminal_valid") is True and stop_class != "valid_stop":
        errors.append("terminal_valid=true requires STOP=valid_stop")
    return errors


def derived_action_sets_v2(payload: dict[str, Any]) -> dict[str, list[str]]:
    grouped = {classification: [] for classification in ACTION_CLASSES}
    for item in payload["actions"]:
        grouped[item["classification"]].append(item["action"])
    return {
        "valid_actions": grouped["valid_progress"] + grouped["valid_recovery"] + grouped["valid_stop"],
        "recommended_actions": payload["recommended_actions"],
        "unsafe_actions": grouped["unsafe"],
        "redundant_actions": grouped["redundant_no_progress"],
        "uncertain_actions": grouped["uncertain"],
    }
