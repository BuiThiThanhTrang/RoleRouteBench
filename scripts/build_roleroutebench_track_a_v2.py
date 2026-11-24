from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from routing_benchmark.roleroutebench.track_a.v2_pipeline import build_v2, validate_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Build RoleRouteBench Track A v2 from exact Track B states")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "config" / "roleroutebench" / "track_a_4d_multirouter_v2.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()
    build = build_v2(args.config, args.output)
    payload = {"build": build}
    exit_code = 0
    if not args.skip_validation:
        validation = validate_v2(Path(build["output_dir"]))
        payload["validation"] = validation
        exit_code = 0 if validation["valid"] else 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
