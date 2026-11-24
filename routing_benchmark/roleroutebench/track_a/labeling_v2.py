from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonicalize import append_jsonl, read_jsonl, sha256_text
from .prompt_v2 import SYSTEM_INSTRUCTIONS_V2, build_user_prompt_v2
from .schema_v2 import (
    LABEL_CONTRACT_VERSION,
    PROMPT_VERSION,
    derived_action_sets_v2,
    prelabel_json_schema_v2,
    validate_prelabel_v2,
)


PROJECT = Path(__file__).resolve().parents[3]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return json.loads(json.dumps(value, default=lambda item: getattr(item, "__dict__", str(item))))


@dataclass
class OpenRouterTrackALabelClientV2:
    model_id: str = "openai/gpt-6.1-terra"
    reasoning_effort: str = "high"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    max_output_tokens: int = 25_000
    timeout_seconds: float = 900.0
    provider_name: str = "openrouter_chat_completions"

    def __post_init__(self) -> None:
        from dotenv import load_dotenv

        load_dotenv(PROJECT.parent / ".env", override=False)
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API credential: set {self.api_key_env}; no request has been sent")
        from openai import OpenAI

        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
            default_headers={
                "HTTP-Referer": "https://huggingface.co/datasets/TrangBui/RoleRouteBench",
                "X-Title": "RoleRouteBench Track A v2 labeling",
            },
        )

    def label(self, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], str]:
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS_V2},
                {"role": "user", "content": build_user_prompt_v2(row)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "roleroutebench_track_a_v2_prelabel",
                    "strict": True,
                    "schema": prelabel_json_schema_v2(),
                },
            },
            max_tokens=self.max_output_tokens,
            extra_body={
                "reasoning": {"effort": self.reasoning_effort, "exclude": True},
                "provider": {"allow_fallbacks": True},
            },
        )
        raw_text = response.choices[0].message.content or ""
        usage = _as_dict(response.usage)
        usage["response_id"] = response.id
        usage["resolved_model"] = response.model
        raw_response = _as_dict(response)
        if raw_response.get("provider"):
            usage["resolved_provider"] = raw_response["provider"]
        return json.loads(raw_text), usage, raw_text


def _completed(path: Path) -> set[str]:
    return {
        row["decision_id"]
        for row in read_jsonl(path)
        if row.get("status") == "proposed" and not row.get("validation_errors")
    }


def run_prelabeling_v2(
    sample_states_path: Path,
    output_dir: Path,
    client: OpenRouterTrackALabelClientV2,
    *,
    max_attempts: int = 2,
    limit: int | None = None,
) -> dict[str, Any]:
    rows = read_jsonl(sample_states_path)
    if limit is not None:
        rows = rows[:limit]
    attempts_path = output_dir / "llm_attempts.jsonl"
    prelabels_path = output_dir / "llm_prelabels.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    done = _completed(prelabels_path)
    successes = failures = skipped = 0
    for position, row in enumerate(rows, start=1):
        decision_id = row["decision_id"]
        if decision_id in done:
            skipped += 1
            continue
        candidates = json.loads(row["candidate_actions_json"])
        proposed = False
        for attempt_number in range(1, max_attempts + 1):
            started = time.perf_counter()
            try:
                payload, usage, raw_text = client.label(row)
                errors = validate_prelabel_v2(payload, candidates)
                status = "proposed" if not errors else "schema_failed"
                error_text = None
            except Exception as exc:
                payload, usage, raw_text = {}, {}, ""
                errors = [str(exc)]
                status = "transport_failed"
                error_text = str(exc)
            attempt = {
                "decision_id": decision_id,
                "public_state_sha256": row["public_state_sha256"],
                "sample_position": position,
                "attempt_number": attempt_number,
                "started_at": _utc_now(),
                "model_provider": client.provider_name,
                "model_id": client.model_id,
                "reasoning_effort": client.reasoning_effort,
                "prompt_version": PROMPT_VERSION,
                "label_contract_version": LABEL_CONTRACT_VERSION,
                "status": status,
                "validation_errors": errors,
                "error": error_text,
                "raw_response_sha256": sha256_text(raw_text),
                "raw_response": raw_text,
                "usage": usage,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
            append_jsonl(attempts_path, attempt)
            if status == "proposed":
                record = {
                    "decision_id": decision_id,
                    "public_state_sha256": row["public_state_sha256"],
                    "model_provider": client.provider_name,
                    "model_id": client.model_id,
                    "reasoning_effort": client.reasoning_effort,
                    "prompt_version": PROMPT_VERSION,
                    "label_contract_version": LABEL_CONTRACT_VERSION,
                    "status": "proposed",
                    "usage": usage,
                    "latency_ms": attempt["latency_ms"],
                    "classification": payload,
                    **derived_action_sets_v2(payload),
                    "terminal_valid": payload["terminal_valid"],
                    "recovery_opportunity": payload["recovery_opportunity"],
                    "expected_progress_kind": payload["expected_progress_kind"],
                    "state_phase": payload["state_phase"],
                    "human_review_status": "pending",
                }
                append_jsonl(prelabels_path, record)
                successes += 1
                proposed = True
                break
        if not proposed:
            failures += 1
        print(f"[{position}/{len(rows)}] {decision_id}: {'ok' if proposed else 'failed'}", flush=True)
    summary = {
        "requested": len(rows),
        "successes_this_run": successes,
        "failures_this_run": failures,
        "skipped_completed": skipped,
        "completed_total": len(_completed(prelabels_path)),
        "model_id": client.model_id,
        "reasoning_effort": client.reasoning_effort,
        "provider": client.provider_name,
        "label_contract_version": LABEL_CONTRACT_VERSION,
        "prompt_version": PROMPT_VERSION,
    }
    (output_dir / "labeling_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary
