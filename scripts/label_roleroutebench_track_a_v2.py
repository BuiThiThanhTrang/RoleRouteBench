from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from routing_benchmark.roleroutebench.track_a.labeling_v2 import (
    OpenRouterTrackALabelClientV2,
    run_prelabeling_v2,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-label RoleRouteBench Track A v2 through OpenRouter")
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT / "data" / "RoleRouteBench" / "track_a_4d_multirouter_v2",
    )
    parser.add_argument("--sample-dir", default="labeling_terra_v2")
    parser.add_argument("--model", default="openai/gpt-6.1-terra")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default="high")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--max-output-tokens", type=int, default=25000)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--limit", type=int, help="Optional smoke-test limit; omit to label the frozen full sample")
    args = parser.parse_args()
    sample_dir = args.root / args.sample_dir
    client = OpenRouterTrackALabelClientV2(
        model_id=args.model,
        reasoning_effort=args.reasoning_effort,
        api_key_env=args.api_key_env,
        base_url=args.base_url,
        max_output_tokens=args.max_output_tokens,
    )
    summary = run_prelabeling_v2(
        sample_dir / "sample_states.jsonl",
        sample_dir,
        client,
        max_attempts=args.max_attempts,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failures_this_run"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
