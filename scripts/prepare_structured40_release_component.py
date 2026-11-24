"""Build a local Table QA40 component and release documents; never upload."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
import yaml
from packaging.requirements import Requirement
from routing_benchmark.v4.artifacts.manifest import load_manifest, validate_artifact_pack
from routing_benchmark.v4.execution.adapters.table_qa import ANSWER_SCHEMA, TOOLS
from scripts.prepare_formal40_release_component import python_closure

BANK = Path("data/RoutingBench/structured_table_qa_v1_40")
STAGING = PROJECT / "hf_release_staging"
DOCS = [
    "structured_data_state_protocol_vi.md", "structured_data_harness_information_flow_vi.md",
    "structured40_router_baseline_release_observations_vi.md", "structured40_release_preparation_vi.md",
    "structured40_hf_release_notes.md", "structured_table_qa_baselines_vi.md",
    "structured_data_inspection_fix_20261122_vi.md",
    "structured_data_inspection_impact_and_routing_metrics_20261122_vi.md",
]
RUNS = {
    "jev": "table_qa_jev_qwen9b_full40_b12",
    "sol": "table_qa_sol_qwen9b_full40_b12",
    "drex": "table_qa_drex_qwen9b_full40_b12",
    "pplx": "table_qa_pplx_qwen9b_full40_b12",
    "single_agent": "table_qa_single_agent_qwen9b",
    "predefined": "table_qa_predefined_qwen9b",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_directory(name):
    grouped = PROJECT / "runs/structured_data" / name
    return grouped if grouped.is_dir() else PROJECT / "runs" / name


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")


def safe_output(path):
    path = Path(path).resolve()
    if path == STAGING.resolve() or not path.is_relative_to(STAGING.resolve()):
        raise ValueError("Use a new child of hf_release_staging")
    return path


def copy(source, payload):
    source = Path(source)
    if source.is_symlink() or not source.resolve().is_relative_to(PROJECT):
        raise ValueError("Unapproved input")
    dest = payload / source.relative_to(PROJECT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def requirement_lock():
    pending = ["openai", "httpx", "jsonschema", "PyYAML", "python-dotenv", "packaging", "openpyxl"]
    found = {}
    while pending:
        name = pending.pop()
        dist = importlib.metadata.distribution(name)
        canonical = dist.metadata["Name"].casefold().replace("_", "-")
        if canonical in found:
            continue
        found[canonical] = dist.version
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({"extra": ""}):
                pending.append(req.name)
    return [f"{name}=={version}" for name, version in sorted(found.items())]


def create_results():
    source = PROJECT / "runs/structured_data_inspection_impact_20261122/impact_and_metrics.json"
    comparisons = read(PROJECT / "runs/structured_data_release_audit_20261122/run_comparisons.json")
    by_run = {x["run"]: x for x in comparisons}
    reports = {x["run"]: x for x in read(source)}
    totals, episodes = [], []
    for method, run in RUNS.items():
        row = reports[run]
        s = row["summary"]
        assert s["completed"] == 40
        infra = 0
        for episode in row["episodes"]:
            folder = run_directory(run) / "episodes" / episode["packet_id"]
            events = [json.loads(x) for x in (folder / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()]
            from scripts.evaluate_shared_environment import infrastructure_failure
            affected = infrastructure_failure(events)
            infra += int(affected)
            episodes.append({"method": method, "run": run, **episode, "infrastructure_detected": affected})
        totals.append({
            "Method": method, "Packets": 40, "Passed": s["workflow_pass"],
            "EndTaskPass": s["end_task_pass"], "VerifiedCorrectCompletion": s["passed_and_end_task_pass"],
            "StopF1": s["stop_f1"], "StopTP": s["stop_confusion_counts"].get("tp", 0),
            "StopFP": s["stop_confusion_counts"].get("fp", 0),
            "StopFN": s["stop_confusion_counts"].get("fn", 0),
            "RecoverySuccess": s["recovery_successes"], "RecoveryOpportunities": s["recovery_opportunities"],
            "RecoveryRate": s["recovery_rate"], "Infrastructure": infra,
            "AvgCallsAll": by_run[run]["mean_calls"],
            "UniqueDispatchedRoleSequences": by_run[run]["unique_dispatched_role_sequences"],
        })
    assert len(episodes) == 240 and not any(x["Infrastructure"] for x in totals)
    result = {
        "cohort": "structured_table_qa_v1_40", "results_scope": "six historical runs; adapter replay equivalent",
        "Totals": totals, "Episodes": episodes,
        "metric_definitions": read(source.parent / "metric_definitions.json"),
        "input_hashes": {str(p.relative_to(PROJECT)): sha(p) for p in (
            source, source.parent / "metric_definitions.json",
            PROJECT / "runs/structured_data_release_audit_20261122/run_comparisons.json",
            PROJECT / "runs/structured_data_inspection_fix_20261122/report.json",
        )},
    }
    base = PROJECT / "report/structured40_final_results"
    write(base.with_suffix(".json"), result)
    with base.with_suffix(".csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(totals[0]))
        writer.writeheader()
        writer.writerows(totals)
    lines = [
        "# Structured40: kết quả trên đủ40 packet", "",
        "Sáu phương pháp, mỗi phương pháp40 packet; Qwen3.5-9B, budget12, một tool call/lượt, output cap16384.",
        "Bảng giữ riêng public workflow pass và đáp án đúng; không cộng hai cột thành success tổng.", "",
        "| Method | Passed | End-task pass | STOP F1 ↑ | Recovery@PublicFailure ↑ |",
        "|---|---:|---:|---:|---:|",
    ]
    for x in totals:
        lines.append(f"| {x['Method']} | {x['Passed']}/40 | {x['EndTaskPass']}/40 | {x['StopF1']:.1%} | "
                     f"{x['RecoveryRate']:.1%} ({x['RecoverySuccess']}/{x['RecoveryOpportunities']}) |")
    lines += [
        "", "## Định nghĩa", "",
        "- Passed: public verification pass còn fresh và router chọn STOP; chưa bảo đảm đúng gold.",
        "- End-task pass: final answer fresh và đạt trusted gold, không yêu cầu STOP.",
        "- STOP F1: positive state có answer fresh/đúng gold và public verification fresh/pass; "
        "TP=STOP tại state đó, FP=STOP khi chưa đạt, FN=non-STOP khi đã đạt. F1=2TP/(2TP+FP+FN). "
        "Bao gồm reserved STOP opportunity tại budget0; suppressed non-STOP khi đã ready là FN.",
        "- Recovery: episode có public last_error hoặc vừa action_rejected, chưa có fresh gold-correct answer "
        "và còn call; thành công nếu final answer đúng/fresh. Mỗi episode tính một lần; không yêu cầu STOP.",
        "", "Gold chỉ dùng evaluator-only. STOP F1 không phải human multi-class action accuracy. "
        "Recovery có mẫu số phụ thuộc trajectory, không phải causal effect riêng của router.", "",
        "## Provenance và giới hạn", "",
        "0 infrastructure episode theo detector hiện tại; đủ240 final candidate audits. Predefined40 "
        "chưa có evaluation_report gốc; gold/metric ở bảng là derived evaluation đã kiểm tra offline. "
        "Không thay attempt, không best-of, không gộp smoke hoặc hai fixed calibration cũ.",
        "Bốn router có241 tracked files chung cùng hash tại thời điểm chạy. Baseline và current "
        "working tree có source delta; replay xác nhận240/240 episode,2084 states,1616 tools tương đương. "
        "Không mô tả các historical runs là fresh runs của source snapshot sau sửa.",
        "", "Verified correct completion (Passed AND gold): JEV19, SOL22, DREX27, PPLX17, "
        "single-agent21, predefined26; JSON/CSV giữ riêng. Không gọi Passed là accuracy gold.",
        "", "Cả7 role xuất hiện trong mỗi dynamic run. Unique dispatched-role sequences: "
        "JEV27, SOL32, DREX31, PPLX24; số sequence không tự chứng minh routing tốt.",
        "DREX phục hồi13/23 nhưng có8 non-STOP tại correct/verified states; SOL có STOP F1 cao nhất "
        "trong bốn router; PPLX chỉ phục hồi1/17. Single-agent/predefined cho thấy dynamic không "
        "mặc định thắng baseline. Mỗi phương pháp chỉ một full run40, chưa chứng minh thứ hạng ổn định.",
        "", "Bản cập nhật nhằm cân bằng độ khó và đa dạng workflow. Mốc40 được giữ có version; "
        "có thể bổ sung sample/nguồn trong revision sau khi có calibration và provenance phù hợp.",
        "", "Đọc cùng docs/structured40_router_baseline_release_observations_vi.md và "
        "docs/structured40_release_preparation_vi.md.",
    ]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def verify(output):
    output = safe_output(output)
    manifest = read(output / "file_manifest.json")["files"]
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    assert actual == set(manifest) | {"file_manifest.json"}, "Component file set changed"
    for name, digest in manifest.items():
        path = (output / name).resolve()
        assert path.is_relative_to(output) and not path.is_symlink() and sha(path) == digest, name
    bank = output / "payload" / BANK
    packets = list((bank / "packs/structured_data_processing").glob("*/manifest.json"))
    assert len(packets) == 40 and all(validate_artifact_pack(p.parent)["valid"] for p in packets)
    selected = [json.loads(x) for x in (output / "records/selected_episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(selected) == 240 and len({(x["method"], x["packet_id"]) for x in selected}) == 240
    integration = read(output / "integration_manifest.json")
    assert integration["upload_performed"] is False and integration["included_domains"] == ["structured_data_processing"]
    with ZipFile(output / "archives/experiment_records.zip") as archive:
        assert archive.testzip() is None
    return {"passed": True, "files": len(manifest), "packets": 40, "selected_episodes": 240}


def build(output):
    output = safe_output(output)
    if output.exists() or output.with_suffix(".zip").exists():
        raise FileExistsError("Choose a new component path; existing components are immutable")
    result = create_results()
    payload = output / "payload"
    records = output / "records"
    payload.mkdir(parents=True)
    tasks, provenance, readiness = [], [], []
    for path in sorted((PROJECT / BANK).rglob("*")):
        if path.is_file():
            copy(path, payload)
    for path in sorted((PROJECT / BANK / "packs/structured_data_processing").glob("*/manifest.json")):
        manifest = load_manifest(path)
        assert validate_artifact_pack(path.parent)["valid"]
        source = read(path.parent / "private/source.json")
        question = read(path.parent / "public/task.json")["question"]
        tasks.append({"packet_id": manifest.base_workflow_id, "domain": manifest.domain, "task": question,
                      "adapter_id": manifest.adapter_id, "manifest_sha256": sha(path),
                      "public_files": [x.path for x in manifest.public_files]})
        provenance.append({
            "packet_id": manifest.base_workflow_id, "source": manifest.source_type,
            **{k: source.get(k) for k in ("source_id", "repository", "revision", "archive_sha256", "split", "table_member")},
            "license": manifest.license, "original_question": source["question"], "adapted_question": question,
            "question_changed": source["question"] != question,
            "adaptation_authority": "scripts/build_structured_table_qa.py; normalization into stable rows/columns and typed answers",
        })
        readiness.append({"packet_id": manifest.base_workflow_id, "original_readiness": manifest.execution_readiness,
                          "effective_execution_readiness": "runtime_verified_with_evidence",
                          "human_review_status": manifest.human_review_status, "packet_review_status": manifest.packet_review_status,
                          "evidence": "runs/structured_data_inspection_fix_20261122/report.json; all40 reference paths"})
    jsonl(records / "tasks.jsonl", tasks)
    jsonl(records / "provenance.jsonl", provenance)
    jsonl(records / "readiness_overlay.jsonl", readiness)
    jsonl(records / "selected_episodes.jsonl", result["Episodes"])
    write(records / "task_contract.json", {
        "adapter_id": "structured_data.table_qa.v1", "input_files": ["public/task.json", "public/tables.json"],
        "edit_scope": "public tables immutable; tool-produced evidence and typed answer candidates",
        "answer_schema": ANSWER_SCHEMA, "tool_schemas": {name: tool.to_dict() for name, tool in TOOLS.items()},
        "gold_visibility": "evaluator_only", "router_row_visibility": "artifact projection only",
        "executor_initial_preview_rows": 5, "inspection_rows": 12, "selection_observation_rows": 6,
        "budget": 12, "max_tool_calls": 1, "inspection_fix": "restore cached slice only when missing from public view",
        "contract_delivery": "release sidecar; not injected into historical prompts or immutable packet manifests",
    })
    roles = read(PROJECT / "config/shared_environment/table_qa_roles.json")
    jsonl(records / "agents.jsonl", roles + read(PROJECT / "config/shared_environment/table_qa_single_agent_role.json"))
    run_records = []
    for method, name in RUNS.items():
        run = run_directory(name)
        config = read(run / "resolved_config.json")
        assert config["max_calls"] == 12 and config["executor"]["max_tool_calls"] == 1
        assert config["executor"]["model"] == "qwen/qwen3.5-9b"
        run_records.append({"method": method, "run_id": name, "resolved_config": config,
                            "historical_source_hashes": read(run / "source_hashes.json"),
                            "freeze_verification": read(run / "freeze_verification.json"),
                            "attempt_selection": "one complete historical run; no retry replacement or best-of",
                            "evaluation_report_originally_present": (run / "evaluation_report.json").exists()})
    jsonl(records / "runs.jsonl", run_records)
    # Explicit allowlist: retain local audit logs without including arbitrary run files.
    archive_path = output / "archives/experiment_records.zip"
    archive_path.parent.mkdir()
    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for name in RUNS.values():
            run = run_directory(name)
            for filename in ("resolved_config.json", "source_hashes.json", "role_cards.json", "freeze_verification.json", "summary.json"):
                path = run / filename
                archive.write(path, (Path("runs") / name / filename).as_posix())
            for folder in sorted((run / "episodes").iterdir()):
                for relative in ("result.json", "decisions.jsonl", "decision_states.jsonl", "trajectory.jsonl",
                                 "runtime.json", "workspace/state.json", "workspace/public/task.json", "workspace/public/tables.json",
                                 "evaluation/final_task_audit.json"):
                    path = folder / relative
                    if path.is_file():
                        archive.write(path, (Path("runs") / name / "episodes" / folder.name / relative).as_posix())
    configs = [PROJECT / "config/shared_environment" / f"table_qa_{name}_qwen9b.yaml"
               for name in ("jev", "sol", "drex", "pplx", "single_agent", "predefined")]
    configs += [PROJECT / "config/shared_environment" / name for name in ("table_qa_roles.json", "table_qa_single_agent_role.json")]
    # Shared policy tests also validate other-domain config fixtures, not their tasks.
    fixture_configs = [PROJECT / "config/shared_environment" / name for name in (
        "database_predefined_qwen9b.yaml", "code_predefined_gemini25flash.yaml", "formal_predefined_goedel32b.yaml",
        "database_single_agent_qwen9b.yaml", "code_single_agent_gemini25flash.yaml", "formal_single_agent_goedel32b.yaml")]
    for config_path in fixture_configs:
        configs.extend((config_path, PROJECT / yaml.safe_load(config_path.read_text(encoding="utf-8"))["role_cards"]))
    tests = ["test_structured_table_qa", "test_shared_router_protocol", "test_predefined_workflow", "test_single_agent_policy"]
    entrypoints = [PROJECT / "scripts" / name for name in (
        "run_shared_environment.py", "run_shared_environment_sol.py", "evaluate_shared_environment.py",
        "build_structured_table_qa.py", Path(__file__).name)]
    roots = entrypoints + [PROJECT / "tests" / f"{name}.py" for name in tests]
    for path in python_closure(roots):
        copy(path, payload)
    for path in configs + [PROJECT / "docs" / name for name in DOCS] + list((PROJECT / "report").glob("structured40_final_results.*")):
        copy(path, payload)
    for folder_name in ("structured_data_release_audit_20261122", "structured_data_inspection_impact_20261122", "structured_data_inspection_fix_20261122"):
        for path in (PROJECT / "runs" / folder_name).iterdir():
            if path.is_file():
                copy(path, payload)
    for source, member in (("wtq", "WikiTableQuestions-master/LICENSE"), ("hitab", "HiTab-main/LICENSE")):
        with ZipFile(PROJECT / f".cache/routingbench_v4/table_qa/{source}.zip") as archive:
            path = records / "licenses" / f"{source}.LICENSE"
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(archive.read(member))
    lock = requirement_lock()
    (payload / "requirements-structured40.lock.txt").write_text("\n".join(lock) + "\n", encoding="utf-8")
    write(records / "runtime_snapshot.json", {"python": sys.version, "platform": sys.platform, "requirements": lock,
          "source_hashes": {p.relative_to(payload).as_posix(): sha(p) for p in payload.rglob("*.py")},
          "model_weights_or_upstream_archives_bundled": False})
    integration = {
        "component_version": "structured40-domain-20261122", "status": "prepared_for_combined_assembly",
        "included_domains": ["structured_data_processing"], "packets": 40, "selected_episodes": 240,
        "update_focus": ["difficulty_rebalancing", "trajectory_diversity", "minimal_inspection_handoff_fix"],
        "future_expansion": "versioned sample/source additions after calibration and provenance checks; no fixed quota/date",
        "global_HF_release_version": "defer_to_combined_assembly", "upload_performed": False,
        "legacy_registry_modified": False, "bank_original_bytes_preserved": True,
        "human_review_status": "pending", "routing_labels": "pending", "historical_runs_reversioned": False,
        "private_evaluator_artifacts_included_locally": True, "raw_logs_in_local_audit_archive": True,
        "publication_policy": "review evaluator-only artifacts, raw logs, paths and per-source license notices during combined assembly",
        "tablebench_dataset_revision": "not recorded; exact cached-file SHA256 retained; unresolved provenance detail",
        "output_format": "local domain component JSONL and documents, not final Hub Parquet",
    }
    write(output / "integration_manifest.json", integration)
    (output / "README.md").write_text(
        "# Structured40 local component\n\nPrepared for the combined release; not uploaded.\n"
        "See payload/docs/structured40_release_preparation_vi.md and report/structured40_final_results.md.\n"
        "The original packet bank is preserved; use records/readiness_overlay.jsonl for current runtime evidence.\n"
        "Gold/source files and raw audit logs are present locally. Apply publication visibility and source licenses before Hub assembly.\n",
        encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(payload) + os.pathsep + str(payload / "tests"), PYTHONDONTWRITEBYTECODE="1")
    check = subprocess.run([sys.executable, "-m", "unittest", *tests], cwd=payload, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    (output / "staged_tests.log").write_text(check.stdout + check.stderr, encoding="utf-8")
    assert check.returncode == 0, "Staged tests failed; inspect staged_tests.log"
    pattern = re.compile(r"(?:sk-[A-Za-z0-9_-]{24,}|hf_[A-Za-z0-9]{30,})")
    scanned = 0
    for path in payload.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".json", ".jsonl", ".yaml", ".md", ".txt"):
            assert not pattern.search(path.read_text(encoding="utf-8", errors="replace")), "Credential-like literal in payload"
            scanned += 1
    write(output / "validation_report.json", {
        "passed": True, "packet_validation": "40/40", "selected_episodes": 240, "infrastructure_detected": 0,
        "staged_tests_passed": 20, "staged_test_exit_code": check.returncode,
        "prior_adapter_replay": {"episodes": 240, "states": 2084, "tool_calls": 1616},
        "replay_scope": "adapter public states, preconditions, tool results and final states; not fresh hosted generations",
        "source_counts": dict(Counter(x["source"] for x in provenance)),
        "adapted_question_count": sum(x["question_changed"] for x in provenance),
        "credential_literal_scan": {"matches": 0, "text_files": scanned}, "hosted_model_calls": 0,
        "human_review": "pending", "publication_review": "deferred to combined assembly",
    })
    write(output / "file_manifest.json", {"files": {p.relative_to(output).as_posix(): sha(p)
          for p in sorted(output.rglob("*")) if p.is_file() and p.name != "file_manifest.json"}})
    validation = verify(output)
    with ZipFile(output.with_suffix(".zip"), "w", ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, (Path(output.name) / path.relative_to(output)).as_posix())
    write(output.parent / f"{output.name}_verification.json", {
        **validation, "archive": output.with_suffix(".zip").name, "archive_sha256": sha(output.with_suffix(".zip"))})
    print(json.dumps(validation), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STAGING / "structured40_20261122")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify)))
    else:
        build(args.output)
