"""Build a public-safe RoleRouteBench 4.1.0-rc.1 Hugging Face candidate.

The builder is intentionally write-once and never modifies the published beta.2
folder. The legacy synthetic Track A is copied byte-for-byte from that folder for
backward compatibility; it is not the unreleased empirical Track A V1. Track B is
rebuilt from the current four-domain packet banks and the frozen JEV episode
selections. Empirical Track A V2 is reserved for a follow-up update after its
results table finishes and is verified. Private evaluator directories and raw
model outputs are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT.parent
DATA_ROOT = PROJECT / "data" / "RoutingBench"
RUNS_ROOT = PROJECT / "runs"
BASE_RELEASE = PROJECT / "hf_release" / "RoutingBench-V4"
DEFAULT_OUTPUT = PROJECT / "hf_release" / "RoleRouteBench-4.1.0-rc1"
README_TEMPLATE = PROJECT / "docs" / "templates" / "hf_roleroutebench_4_1_0_rc1_README.md"
NOTES_TEMPLATE = PROJECT / "docs" / "templates" / "hf_roleroutebench_4_1_0_rc1_RELEASE_NOTES.md"

RELEASE_VERSION = "4.1.0-rc.1"
TRACK_A_PROVENANCE = {
    "published_legacy_track": {
        "track_id": "legacy_synthetic_track_a",
        "state_origin": "llm_generated_simulation",
        "empirical_trajectory": False,
        "status": "published_legacy_compatibility",
    },
    "empirical_track_a_v1": {
        "state_origin": "recorded_live_routing_states",
        "status": "unreleased_internal",
    },
    "empirical_track_a_v2": {
        "state_origin": "recorded_multi_router_track_b_trajectories",
        "status": "follow_up_pending_results_table_completion_and_verification",
    },
}
TRACK_A_CONFIGS = (
    "router_state",
    "router_structured",
    "router_raw_development",
    "track_a_labels",
    "agent_catalog",
    "provenance",
    "human_review",
)

DOMAIN_SPECS: dict[str, dict[str, Any]] = {
    "database_migration_integrity": {
        "packet_root": DATA_ROOT / "v4_domain_packets_rc1" / "packs" / "database_migration_integrity",
        "source_kind": "collection_manifest",
        "source_manifest": RUNS_ROOT / "database" / "collection_manifest.json",
        "reference_method": "jev",
        "expected_packets": 12,
        "result_metric": "p_plus_e",
        "review_status": "inherited_packet_review; routing_labels_pending",
    },
    "code_debugging": {
        "packet_root": DATA_ROOT / "v4_code_debugging_rc1" / "packs" / "code_debugging",
        "source_kind": "collection_manifest",
        "source_manifest": RUNS_ROOT / "code_debugging" / "collection_manifest.json",
        "reference_method": "jev",
        "expected_packets": 20,
        "result_metric": "p_plus_e",
        "review_status": "inherited_packet_review; routing_labels_pending",
    },
    "formal_proof": {
        "packet_root": DATA_ROOT / "formal40_pythagoras_v1_20261118" / "packs" / "formal_proof",
        "source_kind": "selection_manifest",
        "source_manifest": RUNS_ROOT / "formal_proof" / "official_run_manifest.json",
        "reference_method": "jev",
        "expected_packets": 40,
        "result_metric": "workflow_and_proof_audit",
        "review_status": "runtime_verified; human_packet_review_pending",
    },
    "structured_data_processing": {
        "packet_root": DATA_ROOT / "structured_table_qa_v1_40" / "packs" / "structured_data_processing",
        "source_kind": "complete_run",
        "run_path": RUNS_ROOT / "structured_data" / "table_qa_jev_qwen9b_full40_b12",
        "reference_method": "jev",
        "expected_packets": 40,
        "result_metric": "trusted_gold_end_task_pass",
        "review_status": "runtime_verified; human_packet_review_pending",
    },
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_run_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    candidate = PROJECT / path
    return candidate if candidate.exists() else RUNS_ROOT / path


def manifest_run_path(manifest: dict[str, Any], run: dict[str, Any]) -> Path:
    if run.get("new_path"):
        return resolve_run_path(run["new_path"])
    if manifest.get("run_root"):
        candidate = PROJECT / str(manifest["run_root"]) / str(run["run_id"])
        if candidate.exists():
            return candidate
    return resolve_run_path(run["run_id"])


def summary_packet_ids(run_path: Path) -> list[str]:
    summary = read_json(run_path / "summary.json")
    return sorted({str(row["packet_id"]) for row in summary.get("episodes", [])})


def reference_episode_sources(domain: str, spec: dict[str, Any]) -> dict[str, Path]:
    if spec["source_kind"] == "complete_run":
        run_path = Path(spec["run_path"])
        return {packet_id: run_path for packet_id in summary_packet_ids(run_path)}

    manifest = read_json(Path(spec["source_manifest"]))
    selected: dict[str, Path] = {}
    for run in manifest["runs"]:
        if run["method"] != spec["reference_method"]:
            continue
        run_path = manifest_run_path(manifest, run)
        packet_ids = run.get("selected_packets") or summary_packet_ids(run_path)
        for packet_id in packet_ids:
            if packet_id in selected:
                raise ValueError(f"duplicate reference selection: {domain}/{packet_id}")
            selected[packet_id] = run_path
    return selected


def public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "base_workflow_id",
        "domain",
        "task",
        "adapter_id",
        "public_files",
        "fixture_files",
        "source_type",
        "generator_version",
        "seed",
        "license",
        "human_review_status",
        "packet_review_status",
        "execution_readiness",
        "artifact_schema_version",
        "metadata",
    }
    result = {key: value for key, value in manifest.items() if key in keep}
    result["private_files"] = []
    result["private_artifacts_published"] = False
    return result


def copy_public_packet(source: Path, destination: Path, manifest: dict[str, Any]) -> None:
    destination.mkdir(parents=True)
    for name in ("public", "fixtures"):
        child = source / name
        if child.is_dir():
            shutil.copytree(child, destination / name)
    write_json(destination / "manifest.json", public_manifest(manifest))


def task_text(packet_dir: Path, manifest: dict[str, Any]) -> str:
    task_path = packet_dir / "public" / "task.md"
    return task_path.read_text(encoding="utf-8") if task_path.is_file() else str(manifest.get("task", ""))


def compact_decisions(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in read_jsonl(path):
        metadata = item.get("metadata") or {}
        rows.append(
            {
                "decision_id": item.get("decision_id"),
                "agent_id": item.get("agent_id"),
                "budget_before": item.get("budget_before"),
                "dispatch_status": item.get("dispatch_status"),
                "confidence": metadata.get("confidence"),
                "probabilities": metadata.get("probabilities"),
                "input_tokens": metadata.get("input_tokens"),
                "latency_ms": metadata.get("latency_ms"),
                "model": metadata.get("model"),
                "prompt_version": metadata.get("prompt_version"),
                "role_card_mode": metadata.get("role_card_mode"),
            }
        )
    return rows


def compact_events(path: Path) -> list[dict[str, Any]]:
    keys = (
        "kind",
        "decision_id",
        "agent_id",
        "status",
        "origin",
        "semantic_delta",
        "state_before_hash",
        "state_after_hash",
    )
    return [{key: item.get(key) for key in keys} for item in read_jsonl(path)]


def model_id(config: dict[str, Any], section: str) -> str | None:
    value = config.get(section)
    return value.get("model") if isinstance(value, dict) else None


def evaluation_by_packet(run_path: Path) -> dict[str, dict[str, Any]]:
    report = read_json(run_path / "evaluation_report.json")
    return {str(row["packet_id"]): row for row in report.get("episodes", [])}


def add_agent_rows(domain: str, run_paths: Iterable[Path], rows: list[dict[str, Any]]) -> None:
    seen = {(row["domain"], row["agent_id"]) for row in rows}
    for run_path in run_paths:
        for card in read_json(run_path / "role_cards.json"):
            key = (domain, card["agent_id"])
            if key in seen:
                continue
            rows.append(
                {
                    "domain": domain,
                    "agent_id": card["agent_id"],
                    "role_name": card.get("role_name", card["agent_id"]),
                    "role_goal": card.get("role_goal", ""),
                    "semantic_family": card.get("semantic_family"),
                    "tools_json": jdump(card.get("tools", [])),
                    "use_when_json": jdump(card.get("use_when", [])),
                    "avoid_when_json": jdump(card.get("avoid_when", [])),
                    "supported_inputs_json": jdump(card.get("supported_inputs", [])),
                    "expected_outputs_json": jdump(card.get("expected_outputs", [])),
                }
            )
            seen.add(key)


def copy_track_a(output: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for name in TRACK_A_CONFIGS:
        source = BASE_RELEASE / "data" / name
        destination = output / "data" / name
        shutil.copytree(source, destination)
        source_files = sorted(path for path in source.rglob("*") if path.is_file())
        for source_file in source_files:
            relative = source_file.relative_to(source)
            copied = destination / relative
            if sha256(source_file) != sha256(copied):
                raise ValueError(f"Track A copy mismatch: {name}/{relative.as_posix()}")
        checks[name] = {"files": len(source_files), "status": "byte_identical_to_beta2"}
    for name in ("specs",):
        source = BASE_RELEASE / name
        if source.is_dir():
            shutil.copytree(source, output / name)
    split_manifest = BASE_RELEASE / "split_manifest.json"
    if split_manifest.is_file():
        shutil.copy2(split_manifest, output / "split_manifest.json")
    return checks


def selected_rows_from_manifest(manifest_path: Path, method: str) -> list[tuple[Path, str]]:
    manifest = read_json(manifest_path)
    selected: list[tuple[Path, str]] = []
    for run in manifest["runs"]:
        if run["method"] != method:
            continue
        run_path = manifest_run_path(manifest, run)
        packet_ids = run.get("selected_packets") or summary_packet_ids(run_path)
        selected.extend((run_path, str(packet_id)) for packet_id in packet_ids)
    return selected


def p_plus_e_result_rows(domain: str, manifest_path: Path) -> list[dict[str, Any]]:
    method_aliases = {
        "jev": "jev",
        "sol": "sol",
        "drex": "drex",
        "pplx": "pplx",
        "fixed": "fixed",
        "single_agent": "single_agent",
    }
    manifest = read_json(manifest_path)
    present = []
    for run in manifest["runs"]:
        if run["method"] not in present:
            present.append(run["method"])
    rows: list[dict[str, Any]] = []
    for raw_method in present:
        selections = selected_rows_from_manifest(manifest_path, raw_method)
        evaluation_cache: dict[Path, dict[str, dict[str, Any]]] = {}
        episodes: list[dict[str, Any]] = []
        for run_path, packet_id in selections:
            if run_path not in evaluation_cache:
                evaluation_cache[run_path] = evaluation_by_packet(run_path)
            episodes.append(evaluation_cache[run_path][packet_id])
        workflow_pass = sum(bool(row.get("passed")) for row in episodes)
        end_task_pass = sum((row.get("end_task_audit") or {}).get("passed") is True for row in episodes)
        end_task_unavailable = sum((row.get("end_task_audit") or {}).get("passed") is None for row in episodes)
        primary = sum(
            bool(row.get("passed")) or (row.get("end_task_audit") or {}).get("passed") is True
            for row in episodes
        )
        rows.append(
            {
                "method": method_aliases[raw_method],
                "domain": domain,
                "packet_count": len(episodes),
                "primary_metric": "P+E: public workflow pass with STOP OR independent end-task pass",
                "primary_pass": primary,
                "primary_accuracy": primary / len(episodes),
                "workflow_pass": workflow_pass,
                "end_task_pass": end_task_pass,
                "end_task_unavailable": end_task_unavailable,
                "stop_f1": None,
                "recovery_success": None,
                "recovery_opportunities": None,
                "source_report": project_relative(manifest_path),
                "coverage_status": "matched",
                "split": "full",
            }
        )
    return rows


def formal_result_rows() -> list[dict[str, Any]]:
    path = PROJECT / "report" / "formal40_final_results.json"
    report = read_json(path)
    return [
        {
            "method": row["Method"],
            "domain": "formal_proof",
            "packet_count": row["Packets"],
            "primary_metric": "workflow success AND independent proof audit pass",
            "primary_pass": row["Success"],
            "primary_accuracy": row["Success"] / row["Packets"],
            "workflow_pass": row["Success"],
            "end_task_pass": row["ProofPass"],
            "end_task_unavailable": 0,
            "stop_f1": None,
            "recovery_success": row["Recovered"],
            "recovery_opportunities": row["RecoveryOpportunities"],
            "source_report": project_relative(path),
            "coverage_status": "matched",
            "split": "full",
        }
        for row in report["Totals"]
    ]


def structured_result_rows() -> list[dict[str, Any]]:
    path = PROJECT / "report" / "structured40_final_results.json"
    report = read_json(path)
    rows = []
    for row in report["Totals"]:
        method = "fixed" if row["Method"] == "predefined" else row["Method"]
        rows.append(
            {
                "method": method,
                "domain": "structured_data_processing",
                "packet_count": row["Packets"],
                "primary_metric": "trusted-gold end-task answer pass; STOP not required",
                "primary_pass": row["EndTaskPass"],
                "primary_accuracy": row["EndTaskPass"] / row["Packets"],
                "workflow_pass": row["Passed"],
                "end_task_pass": row["EndTaskPass"],
                "end_task_unavailable": 0,
                "stop_f1": row["StopF1"],
                "recovery_success": row["RecoverySuccess"],
                "recovery_opportunities": row["RecoveryOpportunities"],
                "source_report": project_relative(path),
                "coverage_status": "matched",
                "split": "full",
            }
        )
    return rows


def benchmark_result_rows() -> list[dict[str, Any]]:
    rows = []
    rows.extend(p_plus_e_result_rows("database_migration_integrity", RUNS_ROOT / "database" / "collection_manifest.json"))
    rows.extend(p_plus_e_result_rows("code_debugging", RUNS_ROOT / "code_debugging" / "collection_manifest.json"))
    rows.extend(formal_result_rows())
    rows.extend(structured_result_rows())

    for method in ("jev", "sol", "drex", "pplx", "fixed"):
        selected = [row for row in rows if row["method"] == method]
        if len(selected) != 4 or sum(row["packet_count"] for row in selected) != 112:
            raise ValueError(f"incomplete 112-task aggregate for {method}")
        primary = sum(row["primary_pass"] for row in selected)
        rows.append(
            {
                "method": method,
                "domain": "all_primary_endpoints",
                "packet_count": 112,
                "primary_metric": "heterogeneous aggregate of each domain's declared primary endpoint",
                "primary_pass": primary,
                "primary_accuracy": primary / 112,
                "workflow_pass": None,
                "end_task_pass": None,
                "end_task_unavailable": sum(row["end_task_unavailable"] for row in selected),
                "stop_f1": None,
                "recovery_success": None,
                "recovery_opportunities": None,
                "source_report": "derived from the four domain rows in this table",
                "coverage_status": "matched_112; heterogeneous_endpoint",
                "split": "full",
            }
        )
    return rows


def write_table(output: Path, name: str, rows: list[dict[str, Any]]) -> None:
    target = output / "data" / name
    target.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(target / "full.parquet", index=False)


def build(output: Path) -> dict[str, Any]:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"release candidate already exists: {output}")
    if not BASE_RELEASE.is_dir():
        raise FileNotFoundError(BASE_RELEASE)
    output.mkdir(parents=True)

    track_a_checks = copy_track_a(output)
    tasks: list[dict[str, Any]] = []
    agents: list[dict[str, Any]] = []
    trajectories: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    selected_run_ids: dict[str, list[str]] = {}

    for domain, spec in DOMAIN_SPECS.items():
        packet_root = Path(spec["packet_root"])
        packet_dirs = sorted(path for path in packet_root.iterdir() if (path / "manifest.json").is_file())
        if len(packet_dirs) != spec["expected_packets"]:
            raise ValueError(f"{domain}: expected {spec['expected_packets']} packet dirs, found {len(packet_dirs)}")
        episode_sources = reference_episode_sources(domain, spec)
        packet_ids = {path.name for path in packet_dirs}
        if set(episode_sources) != packet_ids:
            raise ValueError(
                f"{domain}: episode selection mismatch; missing={sorted(packet_ids-set(episode_sources))}, "
                f"extra={sorted(set(episode_sources)-packet_ids)}"
            )
        unique_runs = sorted(set(episode_sources.values()), key=lambda path: str(path))
        selected_run_ids[domain] = [path.name for path in unique_runs]
        add_agent_rows(domain, unique_runs, agents)
        eval_cache = {run_path: evaluation_by_packet(run_path) for run_path in unique_runs}

        domain_results = []
        for packet_dir in packet_dirs:
            packet_id = packet_dir.name
            manifest = read_json(packet_dir / "manifest.json")
            public = public_manifest(manifest)
            destination = output / "track_b_packets" / domain / packet_id
            copy_public_packet(packet_dir, destination, manifest)
            metadata = manifest.get("metadata") or {}
            tasks.append(
                {
                    "packet_id": packet_id,
                    "domain": domain,
                    "task": task_text(packet_dir, manifest),
                    "adapter_id": manifest.get("adapter_id"),
                    "source_type": manifest.get("source_type"),
                    "license": manifest.get("license", "NOASSERTION"),
                    "human_review_status": manifest.get("human_review_status", "pending"),
                    "packet_review_status": manifest.get("packet_review_status", "pending"),
                    "execution_readiness": manifest.get("execution_readiness"),
                    "public_packet_path": f"track_b_packets/{domain}/{packet_id}/public",
                    "evaluator_packet_path": None,
                    "public_manifest_json": jdump(public),
                    "split": "full",
                }
            )
            provenance.append(
                {
                    "packet_id": packet_id,
                    "domain": domain,
                    "source_type": manifest.get("source_type"),
                    "source_repository": metadata.get("source_repository"),
                    "source_revision": metadata.get("source_revision"),
                    "source_split": metadata.get("source_split"),
                    "source_record_id": metadata.get("source_record_id"),
                    "license": manifest.get("license", "NOASSERTION"),
                    "generator_version": manifest.get("generator_version"),
                    "manifest_sha256": sha256(packet_dir / "manifest.json"),
                    "split": "full",
                }
            )

            run_path = episode_sources[packet_id]
            episode_dir = run_path / "episodes" / packet_id
            config = read_json(run_path / "resolved_config.json")
            evaluation = eval_cache[run_path][packet_id]
            result = read_json(episode_dir / "result.json")
            trajectories.append(
                {
                    "packet_id": packet_id,
                    "domain": domain,
                    "run_id": run_path.name,
                    "router_model": model_id(config, "router"),
                    "executor_model": model_id(config, "executor"),
                    "max_calls": config.get("max_calls"),
                    "seed": config.get("seed"),
                    "decision_sequence_json": jdump(compact_decisions(episode_dir / "decisions.jsonl")),
                    "event_sequence_json": jdump(compact_events(episode_dir / "trajectory.jsonl")),
                    "raw_outputs_included": False,
                    "split": "full",
                }
            )
            audit = evaluation.get("end_task_audit") or {}
            metrics = evaluation.get("metrics") or {}
            result_row = {
                "packet_id": packet_id,
                "domain": domain,
                "run_id": run_path.name,
                "trajectory_passed": bool(evaluation.get("passed", result.get("passed"))),
                "independent_end_task_passed": audit.get("passed"),
                "terminal_contract_passed": bool(result.get("terminal_contract_passed")),
                "terminal_reason": result.get("terminal_reason"),
                "router_stop_selected": bool(result.get("router_stop_selected")),
                "primary_routing_decisions": result.get("primary_routing_decisions"),
                "router_decision_count": result.get("router_decision_count"),
                "suppressed_by_budget": result.get("suppressed_by_budget"),
                "dispatched": result.get("dispatched"),
                "executor_calls": result.get("executor_calls"),
                "metrics_json": jdump(metrics),
                "split": "full",
            }
            results.append(result_row)
            domain_results.append(result_row)

        runs.append(
            {
                "domain": domain,
                "packet_count": len(domain_results),
                "router_model": "reference JEV selection; see per-row trajectory metadata",
                "executor_models_json": jdump(sorted({row["executor_model"] for row in trajectories if row["domain"] == domain})),
                "run_ids_json": jdump(selected_run_ids[domain]),
                "trajectory_passed": sum(bool(row["trajectory_passed"]) for row in domain_results),
                "independent_end_task_passed": sum(row["independent_end_task_passed"] is True for row in domain_results),
                "primary_routing_decisions": sum(int(row["primary_routing_decisions"] or 0) for row in domain_results),
                "router_decisions": sum(int(row["router_decision_count"] or 0) for row in domain_results),
                "suppressed_by_budget": sum(int(row["suppressed_by_budget"] or 0) for row in domain_results),
                "packet_human_review_status": spec["review_status"],
                "state_label_review_status": "pending",
                "metric_notes": spec["result_metric"],
                "split": "full",
            }
        )

    benchmark_rows = benchmark_result_rows()
    tables = {
        "track_b_tasks": tasks,
        "track_b_agents": agents,
        "track_b_trajectories": trajectories,
        "track_b_results": results,
        "track_b_runs": runs,
        "track_b_provenance": provenance,
        "benchmark_results": benchmark_rows,
    }
    for name, rows in tables.items():
        write_table(output, name, rows)

    shutil.copy2(README_TEMPLATE, output / "README.md")
    shutil.copy2(NOTES_TEMPLATE, output / "RELEASE_NOTES.md")
    checklist = """# Publication checklist\n\n- [x] Track B contains 112 unique tasks.\n- [x] Reference JEV trajectories/results cover the same 112 tasks.\n- [x] Legacy synthetic Track A is copied byte-for-byte from beta.2 for compatibility.\n- [x] The unreleased empirical Track A V1 is not represented as published.\n- [x] Empirical Track A V2 is reserved for a follow-up after its results table finishes and is verified.\n- [x] Packet private directories and raw model outputs are excluded.\n- [x] Multi-method results preserve domain-specific primary endpoints.\n- [ ] Final semantic version approved.\n- [ ] Git code commit and tag created; README placeholder replaced.\n- [ ] TableBench upstream revision/license text reviewed.\n- [ ] Formal40 and Structured40 human-review wording approved.\n- [ ] Hugging Face parent revision recorded and final upload diff reviewed.\n- [ ] Dataset revision and DOI revision links inserted after upload.\n"""
    (output / "PUBLICATION_CHECKLIST.md").write_text(checklist, encoding="utf-8", newline="\n")

    write_json(
        output / "track_b_split_manifest.json",
        {
            "schema_version": "roleroutebench.track_b_split.v2",
            "release": RELEASE_VERSION,
            "split": "full",
            "holdout": False,
            "packet_count": len(tasks),
            "packets_by_domain": dict(sorted(pd.Series([row["domain"] for row in tasks]).value_counts().to_dict().items())),
            "policy": "Transparent controlled-comparison cohort; not a sealed test set.",
        },
    )
    package_report = {
        "schema_version": "roleroutebench.hf_candidate.v2",
        "release": RELEASE_VERSION,
        "status": "LOCAL_RELEASE_CANDIDATE_NOT_UPLOADED",
        "track_a_policy": (
            "legacy synthetic Track A byte-identical to beta.2; empirical Track A V1 "
            "unreleased; empirical Track A V2 reserved for a follow-up after the results "
            "table finishes and is verified"
        ),
        "track_a_provenance": TRACK_A_PROVENANCE,
        "track_b_split": "full",
        "track_c_policy": "not included",
        "counts": {name: len(rows) for name, rows in tables.items()},
        "domain_packet_counts": dict(sorted(pd.Series([row["domain"] for row in tasks]).value_counts().to_dict().items())),
        "reference_run_ids": selected_run_ids,
        "private_evaluator_artifacts_published": False,
        "raw_model_outputs_published": False,
        "track_a_copy_checks": track_a_checks,
    }
    write_json(output / "track_b_package_report.json", package_report)

    payload_files = sorted(
        path for path in output.rglob("*")
        if path.is_file() and path.name not in {"release_manifest.json", "checksums.sha256"}
    )
    manifest_files = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in payload_files
    ]
    write_json(
        output / "release_manifest.json",
        {
            "schema_version": "roleroutebench.release_candidate.v1",
            "release": RELEASE_VERSION,
            "status": "LOCAL_RELEASE_CANDIDATE_NOT_UPLOADED",
            "base_release": "4.0.0-beta.2",
            "code_revision": "TO_BE_FILLED_AFTER_GIT_COMMIT",
            "dataset_revision": "TO_BE_FILLED_AFTER_HUB_UPLOAD",
            "track_a_provenance": TRACK_A_PROVENANCE,
            "track_b_packet_count": len(tasks),
            "private_evaluator_artifacts_published": False,
            "files": manifest_files,
        },
    )
    checksum_lines = [f"{entry['sha256']}  {entry['path']}" for entry in manifest_files]
    (output / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
    return validate(output)


def validate(output: Path) -> dict[str, Any]:
    output = output.resolve()
    errors: list[str] = []
    tables: dict[str, pd.DataFrame] = {}
    for name in (
        "track_b_tasks",
        "track_b_agents",
        "track_b_trajectories",
        "track_b_results",
        "track_b_runs",
        "track_b_provenance",
        "benchmark_results",
    ):
        path = output / "data" / name / "full.parquet"
        if not path.is_file():
            errors.append(f"missing_table:{name}")
            continue
        tables[name] = pd.read_parquet(path)

    expected = {
        "database_migration_integrity": 12,
        "code_debugging": 20,
        "formal_proof": 40,
        "structured_data_processing": 40,
    }
    if "track_b_tasks" in tables:
        actual = tables["track_b_tasks"].groupby("domain").size().to_dict()
        if actual != expected:
            errors.append(f"domain_counts:{actual}")
        if tables["track_b_tasks"]["packet_id"].duplicated().any():
            errors.append("duplicate_task_packet_id")
    for name in ("track_b_trajectories", "track_b_results", "track_b_provenance"):
        if name in tables and len(tables[name]) != 112:
            errors.append(f"row_count:{name}:{len(tables[name])}")
    if any(path.is_dir() for path in output.glob("track_b_packets/*/*/private")):
        errors.append("private_packet_directory_present")
    if (output / "data" / "track_a_v2").exists():
        errors.append("track_a_v2_must_not_be_published")

    expected_aggregates = {"sol": 65, "drex": 58, "jev": 56, "pplx": 55, "fixed": 61}
    if "benchmark_results" in tables:
        aggregates = tables["benchmark_results"]
        aggregates = aggregates[aggregates["domain"] == "all_primary_endpoints"]
        actual_aggregates = dict(zip(aggregates["method"], aggregates["primary_pass"]))
        if actual_aggregates != expected_aggregates:
            errors.append(f"aggregate_results:{actual_aggregates}")

    manifest_path = output / "release_manifest.json"
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        if manifest.get("track_a_provenance") != TRACK_A_PROVENANCE:
            errors.append("track_a_provenance_mismatch")
        expected_paths = {entry["path"] for entry in manifest["files"]}
        actual_paths = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file() and path.name not in {"release_manifest.json", "checksums.sha256"}
        }
        if expected_paths != actual_paths:
            errors.append("release_manifest_file_set_mismatch")
        for entry in manifest["files"]:
            path = output / entry["path"]
            if not path.is_file() or sha256(path) != entry["sha256"]:
                errors.append(f"checksum_mismatch:{entry['path']}")
    else:
        errors.append("missing_release_manifest")

    report = {
        "valid": not errors,
        "release": RELEASE_VERSION,
        "output": str(output),
        "track_b_tasks": len(tables.get("track_b_tasks", [])),
        "reference_trajectories": len(tables.get("track_b_trajectories", [])),
        "reference_results": len(tables.get("track_b_results", [])),
        "benchmark_result_rows": len(tables.get("benchmark_results", [])),
        "private_packet_directories": len(list(output.glob("track_b_packets/*/*/private"))),
        "errors": errors,
    }
    if errors:
        raise ValueError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    report = validate(args.output) if args.verify else build(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
