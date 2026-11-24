from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from routing_benchmark.roleroutebench.track_a.v2_pipeline import validate_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Track A v2 fidelity against Track B")
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT / "data" / "RoleRouteBench" / "track_a_4d_multirouter_v2",
    )
    args = parser.parse_args()
    report = validate_v2(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
