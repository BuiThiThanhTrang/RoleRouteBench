from __future__ import annotations

import json
import random
from collections import Counter, defaultdict, deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from .canonicalize import (
    canonical_json,
    read_json,
    read_jsonl,
    sha256_file,
    sha256_text,
    write_json,
    write_jsonl,
)


PROJECT = Path(__file__).resolve().parents[3]
ROUTERS = ("jev", "sol", "drex", "pplx")
PUBLIC_STATE_FIELDS = (
    "packet_id",
    "domain",
    "task",
    "agent_pool",
    "candidate_actions",
    "observation",
    "router_visible_private_reference",
)
RUN_SNAPSHOT_FILES = (
    "resolved_config.json",
    "role_cards.json",
    "source_hashes.json",
    "freeze_verification.json",
    "summary.json",
)


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT / path


def _read_optional_json(path: Path, default: Any = None) -> Any:
    return read_json(path) if path.exists() else default


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _public_router_view(state: dict[str, Any]) -> dict[str, Any]:
    """Return only fields available at the Track B routing boundary."""

    return {key: deepcopy(state.get(key)) for key in PUBLIC_STATE_FIELDS if key in state}


def _critical_runtime_hashes(domain: str, source_hashes: dict[str, Any]) -> dict[str, str]:
    common_suffixes = (
        "routing_benchmark/v4/execution/base.py",
    )
    domain_suffixes = {
        "code_debugging": (
            "routing_benchmark/v4/execution/adapters/code_debugging.py",
            "routing_benchmark/v4/execution/adapters/external_code_debugging.py",
        ),
        "database_migration_integrity": (
            "routing_benchmark/v4/execution/adapters/database.py",
        ),
        "formal_proof": (
            "routing_benchmark/v4/execution/adapters/formal_proof.py",
            "routing_benchmark/v4/execution/adapters/formal_proof_v2.py",
        ),
        "structured_data_processing": (
            "routing_benchmark/v4/execution/adapters/table_qa.py",
            "routing_benchmark/v4/execution/table_qa_policy.py",
        ),
    }
    wanted = common_suffixes + domain_suffixes.get(domain, ())
    result: dict[str, str] = {}
    for raw_path, digest in source_hashes.items():
        normalized = str(raw_path).replace("\\", "/")
        for suffix in wanted:
            if normalized.endswith(suffix):
                result[suffix] = str(digest)
    return dict(sorted(result.items()))


def _normalized_environment_config(config: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(config)
    for key in ("router", "workers", "selected_packets", "output_root", "packet_root", "role_cards", "lean_cache"):
        value.pop(key, None)
    executor = value.get("executor")
    if isinstance(executor, dict):
        executor.pop("api_key_env", None)
    return value


def _locate_packet_manifest(config: dict[str, Any], domain: str, packet_id: str) -> Path:
    packet_root = _project_path(config["packet_root"])
    candidates = (
        packet_root / "packs" / domain / packet_id / "manifest.json",
        packet_root / domain / packet_id / "manifest.json",
        packet_root / packet_id / "manifest.json",
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"cannot locate manifest for {domain}/{packet_id} below {packet_root}")


def _load_run_snapshot(run_path: Path, router: str, domain: str) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    files: list[dict[str, Any]] = []
    for name in RUN_SNAPSHOT_FILES:
        path = run_path / name
        if path.exists():
            payloads[name] = read_json(path)
            files.append({"path": _relative(path), "sha256": sha256_file(path), "size": path.stat().st_size})
    config = payloads.get("resolved_config.json")
    role_cards = payloads.get("role_cards.json")
    source_hashes = payloads.get("source_hashes.json", {})
    if not isinstance(config, dict) or role_cards is None:
        raise ValueError(f"run is missing resolved_config.json or role_cards.json: {run_path}")
    role_cards_sha = sha256_text(canonical_json(role_cards))
    critical_hashes = _critical_runtime_hashes(domain, source_hashes if isinstance(source_hashes, dict) else {})
    environment_contract = {
        "domain": domain,
        "normalized_resolved_config": _normalized_environment_config(config),
        "role_cards_sha256": role_cards_sha,
        "critical_runtime_hashes": critical_hashes,
    }
    return {
        "run_snapshot_id": f"run-{sha256_text(_relative(run_path))[:24]}",
        "run_id": run_path.name,
        "run_path": _relative(run_path),
        "router_family": router,
        "domain": domain,
        "files": files,
        "payloads": payloads,
        "role_cards_sha256": role_cards_sha,
        "critical_runtime_hashes": critical_hashes,
        "environment_contract_base_sha256": sha256_text(canonical_json(environment_contract)),
    }


def _complete_run_packets(run_path: Path) -> list[str]:
    summary_path = run_path / "summary.json"
    if summary_path.exists():
        summary = read_json(summary_path)
        ids = [str(row["packet_id"]) for row in summary.get("episodes", [])]
        if ids:
            return sorted(set(ids))
    return sorted(path.name for path in (run_path / "episodes").iterdir() if path.is_dir())


def discover_sources(config: dict[str, Any]) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for domain, spec in config["domains"].items():
        kind = spec["source_kind"]
        if kind == "complete_runs":
            for router, raw_path in spec["runs"].items():
                run_path = _project_path(raw_path)
                for packet_id in _complete_run_packets(run_path):
                    sources.append(
                        {
                            "domain": domain,
                            "router": router,
                            "run_path": _relative(run_path),
                            "packet_id": packet_id,
                        }
                    )
        elif kind == "selection_manifest":
            manifest = read_json(_project_path(spec["manifest"]))
            allowed = set(spec["allowed_methods"])
            run_root = _project_path(spec["run_root"])
            for run in manifest["runs"]:
                router = run["method"]
                if router not in allowed:
                    continue
                for packet_id in run["selected_packets"]:
                    sources.append(
                        {
                            "domain": domain,
                            "router": router,
                            "run_path": _relative(run_root / run["run_id"]),
                            "packet_id": packet_id,
                        }
                    )
        else:
            raise ValueError(f"unsupported source_kind: {kind}")
    return sorted(sources, key=lambda row: (row["domain"], row["router"], row["packet_id"], row["run_path"]))


def _observable_phase(observation: dict[str, Any], source_index: int) -> str:
    if source_index == 0:
        return "initial"
    state = observation.get("current_state") or {}
    budget = observation.get("budget") or {}
    remaining = budget.get("calls_remaining")
    compact = canonical_json(state).lower()
    if state.get("terminal") is True or '"task_status":"completed"' in compact:
        return "terminal_ready"
    terminal_markers = (
        '"candidate_test_outcome":"pass"',
        '"verification_status":{"artifact_id"',
        '"status":"passed"',
        '"status":"verified"',
        '"proof_status":"pass"',
    )
    if any(marker in compact for marker in terminal_markers):
        return "validation_or_terminal"
    failure_markers = (
        '"last_error":',
        '"status":"failed"',
        '"outcome":"fail"',
        '"action_rejected"',
        '"invalid_output"',
        '"compile_error"',
    )
    if any(marker in compact for marker in failure_markers) and not ('"last_error":null' in compact):
        return "observable_failure_or_recovery"
    if isinstance(remaining, int) and remaining <= 1:
        return "budget_end"
    if any(token in compact for token in ("candidate", "patch", "proof", "answer", "selection", "calculation")):
        return "artifact_progress"
    return "mid_trajectory"


def _environment_id(run_snapshot: dict[str, Any], packet_manifest_sha: str) -> str:
    payload = {
        "base": run_snapshot["environment_contract_base_sha256"],
        "packet_manifest_sha256": packet_manifest_sha,
    }
    return f"env-{sha256_text(canonical_json(payload))[:24]}"


def _episode_rows(
    source: dict[str, str],
    run_snapshot: dict[str, Any],
    packet_snapshots: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_path = _project_path(source["run_path"])
    episode = run_path / "episodes" / source["packet_id"]
    states_path = episode / "decision_states.jsonl"
    decisions_path = episode / "decisions.jsonl"
    trajectory_path = episode / "trajectory.jsonl"
    states = read_jsonl(states_path)
    decisions = read_jsonl(decisions_path)
    trajectory = read_jsonl(trajectory_path)
    decisions_by_id = {row["decision_id"]: row for row in decisions}
    trajectory_by_id = {row.get("decision_id"): row for row in trajectory if row.get("decision_id")}
    result_path = episode / "result.json"
    runtime_path = episode / "runtime.json"
    result = _read_optional_json(result_path, {})
    runtime = _read_optional_json(runtime_path, {})
    config = run_snapshot["payloads"]["resolved_config.json"]
    packet_manifest_path = _locate_packet_manifest(config, source["domain"], source["packet_id"])
    packet_manifest = read_json(packet_manifest_path)
    packet_manifest_sha = sha256_text(canonical_json(packet_manifest))
    packet_snapshot_id = f"packet-{packet_manifest_sha[:24]}"
    packet_snapshots.setdefault(
        packet_snapshot_id,
        {
            "packet_snapshot_id": packet_snapshot_id,
            "domain": source["domain"],
            "packet_id": source["packet_id"],
            "source_paths": [],
            "packet_manifest_sha256": packet_manifest_sha,
            "packet_manifest": packet_manifest,
        },
    )
    source_path = _relative(packet_manifest_path)
    if source_path not in packet_snapshots[packet_snapshot_id]["source_paths"]:
        packet_snapshots[packet_snapshot_id]["source_paths"].append(source_path)
    environment_id = _environment_id(run_snapshot, packet_manifest_sha)
    rows: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        decision_id = state["decision_id"]
        decision = decisions_by_id.get(decision_id)
        if decision is None:
            raise ValueError(f"missing decision for {source['run_path']}::{decision_id}")
        trace = trajectory_by_id.get(decision_id)
        router_view = _public_router_view(state)
        observation = state.get("observation") or {}
        candidates = state.get("candidate_actions") or []
        allowed = observation.get("constraints", {}).get("allowed_actions")
        if candidates != allowed:
            raise ValueError(f"candidate/allowed-action mismatch: {source['run_path']}::{decision_id}")
        occurrence_key = f"{source['run_path']}::{decision_id}"
        occurrence_id = f"occ-{sha256_text(occurrence_key)[:24]}"
        public_state_payload = {
            "environment_id": environment_id,
            "router_view": router_view,
        }
        public_state_sha = sha256_text(canonical_json(public_state_payload))
        trace_result = trace.get("result", {}) if isinstance(trace, dict) else {}
        requests = trace_result.get("requests", []) if isinstance(trace_result, dict) else []
        if requests:
            executor_visibility_mode = "model_requests_recorded"
        elif trace is not None:
            executor_visibility_mode = "deterministic_or_no_request_execution"
        elif decision.get("agent_id") == "STOP":
            executor_visibility_mode = "stop_has_no_executor"
        else:
            executor_visibility_mode = "no_executor_trace_recorded"
        source_files = []
        for path in (states_path, decisions_path, trajectory_path, result_path, runtime_path):
            if path.exists():
                source_files.append({"path": _relative(path), "sha256": sha256_file(path), "size": path.stat().st_size})
        rows.append(
            {
                "occurrence_id": occurrence_id,
                "domain": source["domain"],
                "packet_id": source["packet_id"],
                "router_family": source["router"],
                "run_snapshot_id": run_snapshot["run_snapshot_id"],
                "packet_snapshot_id": packet_snapshot_id,
                "environment_id": environment_id,
                "source_run_path": source["run_path"],
                "source_decision_id": decision_id,
                "source_decision_index": index,
                "public_state_sha256": public_state_sha,
                "router_view_sha256": sha256_text(canonical_json(router_view)),
                "router_observation_sha256": sha256_text(canonical_json(observation)),
                "decision_state": state,
                "decision": decision,
                "trajectory": trace,
                "episode_result": result,
                "episode_runtime": runtime,
                "executor_visibility_mode": executor_visibility_mode,
                "executor_request_count": len(requests),
                "observable_phase": _observable_phase(observation, index),
                "primary_eligible": decision.get("dispatch_status") != "suppressed_by_budget",
                "source_files": source_files,
            }
        )
    return rows


def _canonical_states(occurrences: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for occurrence in occurrences:
        groups[occurrence["public_state_sha256"]].append(occurrence)
    primary: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for state_sha, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda row: (row["router_family"], row["source_run_path"], row["source_decision_id"]))
        eligible = [row for row in ordered if row["primary_eligible"]]
        representative_pool = eligible or ordered
        representative = representative_pool[int(state_sha[:8], 16) % len(representative_pool)]
        state = representative["decision_state"]
        observation = state["observation"]
        sample_id = f"rra2-{state_sha[:24]}"
        row = {
            "sample_id": sample_id,
            "decision_id": sample_id,
            "domain": representative["domain"],
            "packet_id": representative["packet_id"],
            "environment_id": representative["environment_id"],
            "router_view_json": canonical_json(_public_router_view(state)),
            "router_input_json": canonical_json(observation),
            "candidate_actions_json": canonical_json(state["candidate_actions"]),
            "budget_remaining": observation.get("budget", {}).get("calls_remaining"),
            "public_state_sha256": state_sha,
            "observable_phase": representative["observable_phase"],
            "representative_occurrence_id": representative["occurrence_id"],
            "occurrence_ids_json": canonical_json([item["occurrence_id"] for item in ordered]),
            "origin_router_families_json": canonical_json(sorted({item["router_family"] for item in ordered})),
            "occurrence_count": len(ordered),
            "primary_eligible": bool(eligible),
            "exclusion_reason": None if eligible else "all_occurrences_suppressed_by_budget",
            "split": "full",
        }
        (primary if eligible else audit).append(row)
    return primary, audit


def _balanced_select(rows: list[dict[str, Any]], target_per_domain: int, seed: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_domain[row["domain"]].append(row)
    for domain in sorted(by_domain):
        domain_rows = by_domain[domain]
        buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in domain_rows:
            origins = json.loads(row["origin_router_families_json"])
            assigned = origins[int(row["public_state_sha256"][8:16], 16) % len(origins)]
            buckets[(assigned, row["observable_phase"])].append(row)
        rng = random.Random(f"{seed}:{domain}")
        queues: dict[tuple[str, str], deque[dict[str, Any]]] = {}
        for key, values in buckets.items():
            values = list(values)
            rng.shuffle(values)
            queues[key] = deque(values)
        keys = sorted(queues)
        domain_selected: list[dict[str, Any]] = []
        while keys and len(domain_selected) < min(target_per_domain, len(domain_rows)):
            next_keys: list[tuple[str, str]] = []
            for key in keys:
                queue = queues[key]
                if queue and len(domain_selected) < target_per_domain:
                    row = dict(queue.popleft())
                    row["selection_router_stratum"] = key[0]
                    row["selection_phase_stratum"] = key[1]
                    domain_selected.append(row)
                if queue:
                    next_keys.append(key)
            keys = next_keys
        selected.extend(domain_selected)
    return sorted(selected, key=lambda row: (row["domain"], row["packet_id"], row["public_state_sha256"]))


def _phase4_manifest(output_dir: Path, selected: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    phase4 = config["phase4"]
    label_dir = output_dir / phase4["sample_dir"]
    decision_ids = [row["decision_id"] for row in selected]
    manifest = {
        "sample_manifest_version": "roleroutebench.track_a.sample.v2",
        "source_states": str((output_dir / "track_a_states.jsonl").resolve()),
        "source_count": len(selected),
        "sample_count": len(selected),
        "seed": config["selection"]["seed"],
        "sampling_method": "all_phase3_selected_states_in_frozen_order",
        "decision_ids": decision_ids,
        "decision_ids_sha256": sha256_text("\n".join(decision_ids)),
        "domain_counts": dict(Counter(row["domain"] for row in selected)),
        "labeler": phase4,
        "labeler_visibility": "router_view_json/candidate_actions_json only; occurrence and executor audit files excluded",
    }
    write_json(label_dir / "sample_manifest.json", manifest)
    write_jsonl(label_dir / "sample_states.jsonl", selected)
    return manifest


def _build_parity_report(
    sources: list[dict[str, str]],
    occurrences: list[dict[str, Any]],
    run_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    run_by_id = {row["run_snapshot_id"]: row for row in run_snapshots}
    first_states: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in occurrences:
        key = (row["domain"], row["packet_id"], row["router_family"])
        if key not in first_states or row["source_decision_index"] < first_states[key]["source_decision_index"]:
            first_states[key] = row
    domains: dict[str, Any] = {}
    for domain in sorted({row["domain"] for row in sources}):
        packets = sorted({row["packet_id"] for row in sources if row["domain"] == domain})
        packet_rows: list[dict[str, Any]] = []
        for packet_id in packets:
            per_router = {
                router: first_states.get((domain, packet_id, router))
                for router in ROUTERS
            }
            missing = [router for router, row in per_router.items() if row is None]
            env_ids = sorted({row["environment_id"] for row in per_router.values() if row})
            initial_views = sorted({row["router_view_sha256"] for row in per_router.values() if row})
            role_hashes = sorted(
                {
                    run_by_id[row["run_snapshot_id"]]["role_cards_sha256"]
                    for row in per_router.values()
                    if row
                }
            )
            critical_fingerprints = sorted(
                {
                    sha256_text(canonical_json(run_by_id[row["run_snapshot_id"]]["critical_runtime_hashes"]))
                    for row in per_router.values()
                    if row
                }
            )
            packet_rows.append(
                {
                    "packet_id": packet_id,
                    "missing_routers": missing,
                    "environment_contract_count": len(env_ids),
                    "initial_router_view_count": len(initial_views),
                    "role_pool_hash_count": len(role_hashes),
                    "critical_runtime_fingerprint_count": len(critical_fingerprints),
                    "matched_public_initial_state": not missing and len(initial_views) == 1,
                    "matched_environment_contract": not missing and len(env_ids) == 1,
                }
            )
        domains[domain] = {
            "packet_count": len(packets),
            "router_episode_counts": dict(
                Counter(row["router"] for row in sources if row["domain"] == domain)
            ),
            "packets_with_all_routers": sum(not row["missing_routers"] for row in packet_rows),
            "packets_with_identical_initial_router_view": sum(row["matched_public_initial_state"] for row in packet_rows),
            "packets_with_identical_environment_contract": sum(row["matched_environment_contract"] for row in packet_rows),
            "packet_audit": packet_rows,
        }
    return {
        "report_version": "roleroutebench.track_a.parity.v2",
        "status": "audited",
        "strict_parity_definition": "same role pool, normalized executor/runtime settings, packet manifest and domain adapter/base hashes",
        "domains": domains,
    }


def build_v2(config_path: Path, output_override: Path | None = None) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = read_json(config_path)
    output_dir = (output_override or _project_path(config["output_dir"])).resolve()
    sources = discover_sources(config)
    run_specs = sorted({(row["run_path"], row["router"], row["domain"]) for row in sources})
    run_snapshots = [
        _load_run_snapshot(_project_path(run_path), router, domain)
        for run_path, router, domain in run_specs
    ]
    run_by_path = {row["run_path"]: row for row in run_snapshots}
    occurrences: list[dict[str, Any]] = []
    packet_snapshots: dict[str, dict[str, Any]] = {}
    for position, source in enumerate(sources, start=1):
        occurrences.extend(_episode_rows(source, run_by_path[source["run_path"]], packet_snapshots))
        if position % 40 == 0 or position == len(sources):
            print(f"collected {position}/{len(sources)} Track B episodes", flush=True)
    canonical, audit = _canonical_states(occurrences)
    target = int(config["selection"]["target_per_domain"])
    selected = _balanced_select(canonical, target, int(config["selection"]["seed"]))
    parity = _build_parity_report(sources, occurrences, run_snapshots)
    for snapshot in packet_snapshots.values():
        snapshot["source_paths"].sort()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "frozen_spec.json", config)
    write_json(output_dir / "source_inventory.json", {"episodes": sources})
    write_jsonl(output_dir / "run_snapshots.jsonl", run_snapshots)
    write_jsonl(output_dir / "packet_snapshots.jsonl", sorted(packet_snapshots.values(), key=lambda row: row["packet_snapshot_id"]))
    write_jsonl(output_dir / "track_b_occurrences.jsonl", occurrences)
    write_jsonl(output_dir / "canonical_states.jsonl", canonical)
    write_jsonl(output_dir / "audit_only_states.jsonl", audit)
    write_jsonl(output_dir / "track_a_states.jsonl", selected)
    phase4 = _phase4_manifest(output_dir, selected, config)
    write_json(output_dir / "environment_parity_report.json", parity)
    counts = {
        "source_episodes": len(sources),
        "run_snapshots": len(run_snapshots),
        "packet_snapshots": len(packet_snapshots),
        "raw_occurrences": len(occurrences),
        "canonical_primary_candidates": len(canonical),
        "canonical_audit_only": len(audit),
        "selected_track_a_states": len(selected),
        "selected_by_domain": dict(Counter(row["domain"] for row in selected)),
        "selected_by_router_stratum": dict(Counter(row["selection_router_stratum"] for row in selected)),
        "selected_by_phase_stratum": dict(Counter(row["selection_phase_stratum"] for row in selected)),
    }
    source_files = [config_path]
    for snapshot in run_snapshots:
        source_files.extend(_project_path(item["path"]) for item in snapshot["files"] if _project_path(item["path"]).exists())
    build_manifest = {
        "manifest_version": "roleroutebench.track_a.build.v2",
        "dataset_id": config["dataset_id"],
        "output_dir": str(output_dir),
        "config_path": _relative(config_path),
        "config_sha256": sha256_file(config_path),
        "counts": counts,
        "phase4": phase4,
        "artifact_files": {},
    }
    write_json(output_dir / "build_manifest.json", build_manifest)
    phase4_dir = output_dir / config["phase4"]["sample_dir"]
    artifact_paths = list(output_dir.iterdir()) + [
        phase4_dir / "sample_manifest.json",
        phase4_dir / "sample_states.jsonl",
    ]
    for path in sorted(artifact_paths):
        if path.is_file() and path.name not in {"build_manifest.json", "validation_report.json"}:
            artifact_name = path.relative_to(output_dir).as_posix()
            build_manifest["artifact_files"][artifact_name] = {
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
    write_json(output_dir / "build_manifest.json", build_manifest)
    return build_manifest


def _source_row_at(path: Path, index: int) -> dict[str, Any]:
    rows = read_jsonl(path)
    if index < 0 or index >= len(rows):
        raise IndexError(f"source index {index} outside {path}")
    return rows[index]


def validate_v2(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    build = read_json(root / "build_manifest.json")
    config = read_json(root / "frozen_spec.json")
    runs = read_jsonl(root / "run_snapshots.jsonl")
    packets = read_jsonl(root / "packet_snapshots.jsonl")
    occurrences = read_jsonl(root / "track_b_occurrences.jsonl")
    canonical = read_jsonl(root / "canonical_states.jsonl")
    audit = read_jsonl(root / "audit_only_states.jsonl")
    selected = read_jsonl(root / "track_a_states.jsonl")
    for relative_path, metadata in build.get("artifact_files", {}).items():
        artifact_path = root / relative_path
        if not artifact_path.exists():
            errors.append(f"missing frozen artifact: {relative_path}")
            continue
        if sha256_file(artifact_path) != metadata["sha256"]:
            errors.append(f"frozen artifact checksum mismatch: {relative_path}")
        if artifact_path.stat().st_size != metadata["size"]:
            errors.append(f"frozen artifact size mismatch: {relative_path}")
    run_ids = {row["run_snapshot_id"] for row in runs}
    packet_ids = {row["packet_snapshot_id"] for row in packets}
    occurrence_ids = [row["occurrence_id"] for row in occurrences]
    occurrence_id_set = set(occurrence_ids)
    jsonl_cache: dict[str, list[dict[str, Any]]] = {}

    def cached_jsonl(path: Path) -> list[dict[str, Any]]:
        key = str(path.resolve())
        if key not in jsonl_cache:
            jsonl_cache[key] = read_jsonl(path)
        return jsonl_cache[key]

    if len(occurrence_ids) != len(set(occurrence_ids)):
        errors.append("duplicate occurrence_id")
    for occurrence in occurrences:
        if occurrence["run_snapshot_id"] not in run_ids:
            errors.append(f"unknown run snapshot: {occurrence['occurrence_id']}")
        if occurrence["packet_snapshot_id"] not in packet_ids:
            errors.append(f"unknown packet snapshot: {occurrence['occurrence_id']}")
        state_path = _project_path(occurrence["source_files"][0]["path"])
        try:
            source_rows = cached_jsonl(state_path)
            source_state = source_rows[int(occurrence["source_decision_index"])]
        except Exception as exc:
            errors.append(f"cannot replay state {occurrence['occurrence_id']}: {exc}")
            continue
        if canonical_json(source_state) != canonical_json(occurrence["decision_state"]):
            errors.append(f"decision state differs from Track B source: {occurrence['occurrence_id']}")
        router_view = _public_router_view(source_state)
        expected_sha = sha256_text(canonical_json({"environment_id": occurrence["environment_id"], "router_view": router_view}))
        if expected_sha != occurrence["public_state_sha256"]:
            errors.append(f"public-state hash mismatch: {occurrence['occurrence_id']}")
        if (
            occurrence["trajectory"] is None
            and occurrence["decision"].get("agent_id") != "STOP"
            and occurrence["decision"].get("dispatch_status") != "suppressed_by_budget"
        ):
            errors.append(f"unexpected missing executor trace: {occurrence['occurrence_id']}")
        trajectory_files = [item for item in occurrence["source_files"] if item["path"].endswith("trajectory.jsonl")]
        if trajectory_files:
            trace_rows = cached_jsonl(_project_path(trajectory_files[0]["path"]))
            matching = [row for row in trace_rows if row.get("decision_id") == occurrence["source_decision_id"]]
            source_trace = matching[0] if matching else None
            if canonical_json(source_trace) != canonical_json(occurrence["trajectory"]):
                errors.append(f"executor trace differs from Track B source: {occurrence['occurrence_id']}")
    candidate_hashes = [row["public_state_sha256"] for row in canonical]
    if len(candidate_hashes) != len(set(candidate_hashes)):
        errors.append("duplicate canonical primary state hash")
    selected_hashes = [row["public_state_sha256"] for row in selected]
    if len(selected_hashes) != len(set(selected_hashes)):
        errors.append("duplicate selected Track A state hash")
    if not set(selected_hashes).issubset(set(candidate_hashes)):
        errors.append("selected state is absent from canonical primary candidates")
    for row in selected:
        try:
            router_view = json.loads(row["router_view_json"])
            observation = json.loads(row["router_input_json"])
            candidates = json.loads(row["candidate_actions_json"])
            occurrence_refs = json.loads(row["occurrence_ids_json"])
        except Exception as exc:
            errors.append(f"invalid selected-state JSON: {row.get('decision_id')}: {exc}")
            continue
        if router_view.get("observation") != observation:
            errors.append(f"router observation is not exact router-view member: {row['decision_id']}")
        if router_view.get("candidate_actions") != candidates:
            errors.append(f"candidate actions are not exact router-view member: {row['decision_id']}")
        if not set(occurrence_refs).issubset(occurrence_id_set):
            errors.append(f"unknown occurrence reference: {row['decision_id']}")
        forbidden = {"source_action_as_run", "episode_result", "trajectory", "decision", "selected_action", "valid_actions"}
        if forbidden.intersection(row):
            errors.append(f"private outcome field leaked into Track A public row: {row['decision_id']}")
    sample_dir = root / config["phase4"]["sample_dir"]
    sample = read_jsonl(sample_dir / "sample_states.jsonl")
    sample_manifest = read_json(sample_dir / "sample_manifest.json")
    if sample != selected:
        errors.append("Phase 4 sample is not byte-semantic identical to selected Track A states")
    if sample_manifest["sample_count"] != len(selected):
        errors.append("Phase 4 sample count mismatch")
    expected_counts = build["counts"]
    actual_counts = {
        "source_episodes": sum(1 for _ in read_json(root / "source_inventory.json")["episodes"]),
        "run_snapshots": len(runs),
        "packet_snapshots": len(packets),
        "raw_occurrences": len(occurrences),
        "canonical_primary_candidates": len(canonical),
        "canonical_audit_only": len(audit),
        "selected_track_a_states": len(selected),
        "selected_by_domain": dict(Counter(row["domain"] for row in selected)),
        "selected_by_router_stratum": dict(Counter(row["selection_router_stratum"] for row in selected)),
        "selected_by_phase_stratum": dict(Counter(row["selection_phase_stratum"] for row in selected)),
    }
    if actual_counts != expected_counts:
        errors.append(f"build count mismatch: {actual_counts} != {expected_counts}")
    report = {
        "validation_version": "roleroutebench.track_a.validation.v2",
        "valid": not errors,
        "errors": errors,
        "counts": actual_counts,
        "fidelity_checks": {
            "router_state_replayed_from_track_b": len(occurrences),
            "executor_trace_replayed_from_track_b": sum(row["trajectory"] is not None for row in occurrences),
            "selected_public_rows_without_private_outcome_fields": len(selected),
        },
    }
    write_json(root / "validation_report.json", report)
    return report

