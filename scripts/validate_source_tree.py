"""Validate the standalone source tree without requiring external packet banks."""

from __future__ import annotations

import compileall
import importlib
import json
from pathlib import Path
import subprocess
import sys

import yaml


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt"}
SOURCE_ONLY_TESTS = (
    "test_shared_human_scoring.py",
    "test_shared_router_protocol.py",
    "test_single_agent_policy.py",
    "test_transport_diagnostics.py",
)
ENTRY_POINTS = (
    "scripts/build_roleroutebench_track_a_v2.py",
    "scripts/validate_roleroutebench_track_a_v2.py",
    "scripts/run_shared_environment.py",
    "scripts/evaluate_shared_environment.py",
    "scripts/prepare_roleroutebench_hf_4_1_rc1.py",
)


def _source_files() -> list[Path]:
    ignored = {".git", "__pycache__", "benchmarks", "data", "runs", "report", "hf_release"}
    return [
        path
        for path in PROJECT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not ignored.intersection(path.relative_to(PROJECT).parts)
    ]


def main() -> int:
    errors: list[str] = []
    legacy_name = "puppe" + "teer"
    legacy = [path for path in _source_files() if legacy_name in path.read_text(encoding="utf-8").casefold()]
    if legacy:
        errors.append("legacy workspace name remains in: " + ", ".join(str(path.relative_to(PROJECT)) for path in legacy))

    for path in PROJECT.rglob("*.json"):
        if "benchmarks" not in path.relative_to(PROJECT).parts:
            json.loads(path.read_text(encoding="utf-8"))
    for pattern in ("*.yaml", "*.yml"):
        for path in PROJECT.rglob(pattern):
            yaml.safe_load(path.read_text(encoding="utf-8"))

    if not compileall.compile_dir(PROJECT / "routing_benchmark", quiet=1):
        errors.append("routing_benchmark compile failed")
    for module in (
        "routing_benchmark",
        "routing_benchmark.routers",
        "routing_benchmark.v4.execution.shared_runner",
        "routing_benchmark.roleroutebench.track_a.v2_pipeline",
    ):
        importlib.import_module(module)

    for entry in ENTRY_POINTS:
        result = subprocess.run(
            [sys.executable, str(PROJECT / entry), "--help"],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            errors.append(f"entry point failed: {entry}: {result.stderr.strip()}")

    for pattern in SOURCE_ONLY_TESTS:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            errors.append(f"source-only test failed: {pattern}: {result.stderr.strip()}")

    payload = {"valid": not errors, "errors": errors}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

