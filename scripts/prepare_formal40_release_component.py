"""Prepare/verify a local Formal40 component for a later combined release.

No Hub client, upload, model call, registry rewrite, or other-domain packaging.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import yaml

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from routing_benchmark.v4.artifacts.manifest import validate_artifact_pack

BANK = Path('data/RoutingBench/formal40_pythagoras_v1_20261118')
VERSION = 'formal40-domain-20261122-final40'
STAGING = PROJECT / 'hf_release_staging'
RUNS = PROJECT / 'runs/formal_proof'
DOCS = [
    'formal_proof_state_protocol_vi.md', 'formal_proof_harness_information_flow_vi.md',
    'formal40_fixed_baseline_vi.md', 'formal40_release_preparation_vi.md',
    'formal40_router_fixed_release_observations_vi.md', 'formal40_packet_preparation_vi.md',
    'formal40_recovery_v3_vi.md', 'formal40_recovery_v2_vi.md',
    'formal40_handoff_inspector_implementation_vi.md', 'formal40_runtime_audit_jev_vi.md',
    'formal_proof_domain_integration_vi.md', 'predefined_domain_workflows_vi.md',
    'domain_extension_packet_adapter_artifact_standard_vi.md',
    'benchmark_domain_packet_completion_playbook_vi.md',
]
REPORTS = ['formal40_final_results']
ENTRYPOINTS = [
    'run_shared_environment.py', 'run_shared_environment_sol.py', 'run_formal_runtime_audit.py',
    'evaluate_shared_environment.py', 'prepare_formal_executor_resources.py',
    'prepare_minif2f_environment.py', 'prepare_formal40_packets.py',
    'check_formal40_packets.py', 'check_formal_executor_protocol.py',
    'prepare_formal40_release_component.py',
]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def safe_output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(STAGING.resolve()) or path == STAGING.resolve():
        raise ValueError('Output must be a new child of hf_release_staging')
    return path


def copy_file(source, payload):
    source = Path(source)
    if source.is_symlink() or not source.resolve().is_relative_to(PROJECT):
        raise ValueError(f'Unapproved source path: {source.name}')
    target = payload / source.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def python_closure(roots):
    """Collect local AST imports and parent initializers, never execute them."""
    pending, found = list(roots), set()

    def module_path(name):
        base = PROJECT.joinpath(*name.split('.'))
        return next((path for path in (base.with_suffix('.py'), base / '__init__.py') if path.is_file()), None)

    while pending:
        path = pending.pop().resolve()
        if path in found:
            continue
        if not path.is_relative_to(PROJECT) or path.suffix != '.py' or path.is_symlink():
            raise ValueError('Source closure escaped the project')
        found.add(path)
        rel = path.relative_to(PROJECT)
        package = list(rel.with_suffix('').parts[:-1])
        for i in range(1, len(rel.parts)):
            init = PROJECT.joinpath(*rel.parts[:i], '__init__.py')
            if init.is_file() and init != path:
                pending.append(init)
        tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(rel))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                parts = package[:len(package) - node.level + 1] if node.level else []
                parts += node.module.split('.') if node.module else []
                base = '.'.join(parts)
                names = ([base] if base else []) + [f'{base}.{alias.name}'.strip('.') for alias in node.names if alias.name != '*']
            for name in names:
                candidate = module_path(name)
                if candidate is not None:
                    pending.append(candidate)
    return found


def logical_failure(folder):
    for line in (folder / 'trajectory.jsonl').read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        for item in event.get('result', {}).get('tool_events', []):
            name = item.get('tool_call', {}).get('name')
            output = item.get('tool_result', {}).get('output', {})
            probe = output.get('result', {})
            if name == 'compile_proof' and probe.get('returncode', 0) > 0 and probe.get('failure_origin') != 'tool_environment':
                return True
            if name == 'verify_proof' and output.get('passed') is False and output.get('kernel_probe', {}).get('failure_origin') != 'tool_environment':
                return True
    return False


def verify(output):
    output = safe_output(output)
    manifest = read(output / 'file_manifest.json')
    expected = set(manifest['files']) | {'file_manifest.json'}
    actual = {path.relative_to(output).as_posix() for path in output.rglob('*') if path.is_file()}
    errors = []
    if expected != actual:
        errors.append({'missing': sorted(expected - actual), 'extra': sorted(actual - expected)})
    for name, digest in manifest['files'].items():
        path = (output / name).resolve()
        if not path.is_relative_to(output) or path.is_symlink() or not path.is_file() or sha(path) != digest:
            errors.append({'checksum_or_path': name})
    bank = output / 'payload' / BANK
    packets = sorted((bank / 'packs/formal_proof').glob('*/manifest.json'))
    for packet in packets:
        result = validate_artifact_pack(packet.parent)
        if not result['valid']:
            errors.append(result)
    integration = read(output / 'integration_manifest.json')
    rows = [json.loads(line) for line in (output / 'records/selected_episodes.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(packets) != 40 or len(rows) != 200 or len({(row['method'], row['packet_id']) for row in rows}) != 200:
        errors.append('Unexpected packet/episode coverage')
    if any(not row['completed'] or row['infrastructure'] for row in rows):
        errors.append('Final selection must be complete and infrastructure-clean')
    final = read(output / 'payload/report/formal40_final_results.json')
    if len(final['Totals']) != 5 or any(row['Packets'] != 40 or row['Infrastructure'] for row in final['Totals']):
        errors.append('Invalid final table denominator or infrastructure status')
    for total in final['Totals']:
        method_rows = [row for row in rows if row['method'] == total['Method']]
        if len(method_rows) != 40 or sum(row['success'] for row in method_rows) != total['Success']:
            errors.append('Final totals differ from selected episode records')
    if integration['upload_performed'] or integration['included_domains'] != ['formal_proof']:
        errors.append('Invalid component scope')
    archive = output / 'archives/experiment_records.zip'
    with zipfile.ZipFile(archive) as handle:
        if handle.testzip() is not None:
            errors.append('Corrupt experiment archive')
    return {'passed': not errors, 'files': len(manifest['files']), 'packets': len(packets),
            'selected_episodes': len(rows), 'completed_selected_episodes': sum(row['completed'] for row in rows),
            'errors': errors, 'file_manifest_sha256': sha(output / 'file_manifest.json')}


def build(output):
    output = safe_output(output)
    if output.exists() or output.with_suffix('.zip').exists():
        raise ValueError('Refusing to overwrite a prepared component; choose a new output')
    source_bank = PROJECT / BANK
    integrity = read(source_bank / 'integrity_manifest.json')
    for name, digest in integrity['files'].items():
        path = (source_bank / name).resolve()
        if not path.is_relative_to(source_bank.resolve()) or sha(path) != digest:
            raise ValueError(f'Original bank integrity mismatch: {name}')
    packets = sorted((source_bank / 'packs/formal_proof').glob('*/manifest.json'))
    if len(packets) != 40:
        raise ValueError('Expected 40 packets')
    for path in packets:
        if not validate_artifact_pack(path.parent)['valid']:
            raise ValueError(f'Invalid packet: {path.parent.name}')
    fixed_run = RUNS / 'formal40_fixed_lean48_pythagoras_b12'
    frozen = read(fixed_run / 'source_hashes.json')
    mismatches = [name for name, digest in frozen.items() if sha(PROJECT / name) != digest]
    unrelated = 'routing_benchmark/v4/execution/adapters/table_qa.py'
    if {name.replace('\\', '/') for name in mismatches} - {unrelated}:
        raise ValueError(f'Current frozen runtime differs from fixed run: {mismatches}')
    latest = read(RUNS / 'formal40_final_v3_input12k_b12_pplx_lean48_infra_retry3/source_hashes.json')
    unrelated_changes = []
    for name in mismatches:
        if sha(PROJECT / name) != latest.get(name):
            raise ValueError('Unrelated adapter changed again since the accepted final retry')
        unrelated_changes.append({'path': name, 'fixed_sha256': frozen[name], 'retry3_and_current_sha256': latest[name],
                                  'reason': 'Separate TableQA adapter; Formal40 uses FormalProofV2Adapter'})
    role_path = Path('config/shared_environment/formal40_inspector_roles.json')
    roles = read(PROJECT / role_path)
    profiles = sorted((PROJECT / 'config/shared_environment/formal40_final_v3_input12k_b12').glob('*.yaml'))
    profiles += [PROJECT / f'config/shared_environment/formal40_fixed_{runtime}_pythagoras_b12.yaml' for runtime in ('lean48', 'lean422')]
    if len(profiles) != 10 or len(roles) != 7:
        raise ValueError('Expected 10 profiles and 7 effective roles')
    expected = yaml.safe_load(profiles[0].read_text(encoding='utf-8'))
    shared = {key: value for key, value in expected.items() if key not in ('router', 'runtime_audit')}
    for path in profiles:
        cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
        if {key: value for key, value in cfg.items() if key not in ('router', 'runtime_audit')} != shared:
            raise ValueError(f'Profile parity failed: {path.name}')
    output.mkdir(parents=True)
    payload = output / 'payload'
    shutil.copytree(source_bank, payload / BANK)
    for path in profiles + [PROJECT / role_path]:
        copy_file(path, payload)
    seeds = {PROJECT / 'scripts' / name for name in ENTRYPOINTS}
    seeds.update(PROJECT / name for name in frozen if name.endswith('.py') and not name.startswith(str(BANK)))
    seeds.update(PROJECT / 'report' / name for name in ('build_formal40_api_retry2_results.py', 'build_formal40_fixed_comparison.py'))
    source_files = python_closure(seeds)
    for path in sorted(source_files):
        copy_file(path, payload)
    for path in (PROJECT / 'routing_benchmark/v4/execution/lean').glob('*.lean'):
        copy_file(path, payload)
    for name in ('requirements-formal-environment.txt', 'requirements-shared-environment.txt'):
        copy_file(PROJECT / name, payload)
    for name in DOCS:
        copy_file(PROJECT / 'docs' / name, payload)
    for stem in REPORTS:
        for extension in ('.json', '.md', '.csv'):
            copy_file(PROJECT / 'report' / (stem + extension), payload)
    for name in ('README.md', 'official_run_manifest.json'):
        copy_file(RUNS / name, payload)

    final_report = read(PROJECT / 'report/formal40_final_results.json')
    if final_report['Status'] != 'COMPLETE_CLEAN_40' or len(final_report['Episodes']) != 200:
        raise ValueError('Expected the final 200-episode, infrastructure-clean report')
    selected = [{'method': row['Router'], 'packet_id': row['Packet'], 'runtime': row['Runtime'],
                 'run_id': row['RunId'], 'completed': row['Completed'],
                 'success': row.get('Success'), 'proof_pass': row.get('ProofPass'),
                 'infrastructure': row.get('Infrastructure'), 'calls': row.get('Calls'),
                 'selection_status': 'completed' if row['Completed'] else 'pending_retry_no_fallback'}
                for row in final_report['Episodes']]
    if any(not row['completed'] or row['infrastructure'] for row in selected):
        raise ValueError('Final selection contains an incomplete or infrastructure-affected episode')
    full_metrics = final_report['Totals']
    task_rows = []
    for path in packets:
        manifest = read(path)
        contract = read(path.parent / 'public/execution_contract.json')
        task_rows.append({'packet_id': path.parent.name, 'domain': 'formal_proof', 'task': manifest['task'],
                          'adapter_id': manifest['adapter_id'], 'toolchain': contract['toolchain'],
                          'source_type': manifest['source_type'], 'license': manifest['license'],
                          'human_review_status': manifest['human_review_status'],
                          'packet_review_status': manifest['packet_review_status'],
                          'execution_readiness': manifest['execution_readiness'],
                          'packet_path': (Path('payload') / BANK / 'packs/formal_proof' / path.parent.name).as_posix(),
                          'effective_role_cards': 'payload/' + role_path.as_posix(),
                          'source_metadata': manifest['metadata']})
    write_rows(output / 'records/tasks.jsonl', task_rows)
    write_rows(output / 'records/agents.jsonl', roles)
    write_rows(output / 'records/selected_episodes.jsonl', selected)
    results_status = 'complete_clean_40'
    write(output / 'records/results_full_denominator.json', {'status': results_status, 'rows': full_metrics,
          'policy': final_report['SelectionPolicy'], 'same_clean_packet_comparison':
          'payload/report/formal40_final_results.json'})
    run_ids = sorted({f'formal40_final_v3_input12k_b12_{method}_{runtime}' for method in ('jev', 'sol', 'drex', 'pplx') for runtime in ('lean48', 'lean422')} |
                     {row['run_id'] for row in selected})
    inventory = []
    archive = output / 'archives/experiment_records.zip'
    archive.parent.mkdir(parents=True)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for name in ('README.md', 'official_run_manifest.json'):
            path = RUNS / name
            zipped.write(path, path.relative_to(PROJECT).as_posix())
        for run_id in run_ids:
            run = RUNS / run_id
            cfg = read(run / 'resolved_config.json')
            freeze = run / 'freeze_verification.json'
            inventory.append({'run_id': run_id, 'source_directory': run.relative_to(PROJECT).as_posix(), 'router_type': cfg['router']['type'],
                              'router_model': cfg['router'].get('model'), 'executor_model': cfg['executor']['model'],
                              'completed_episodes': len(list(run.glob('episodes/*/result.json'))),
                              'selected_packets': cfg.get('selected_packets'),
                              'evaluation_sha256': sha(run / 'evaluation_report.json') if (run / 'evaluation_report.json').exists() else None,
                              'freeze_verification': read(freeze) if freeze.exists() else None,
                              'raw_archive_publication_review': 'pending_combined_assembly'})
            files = [run / name for name in ('resolved_config.json', 'role_cards.json', 'source_hashes.json',
                     'freeze_verification.json', 'summary.json', 'evaluation_report.json')]
            for episode in (run / 'episodes').iterdir():
                files += [episode / name for name in ('result.json', 'decisions.jsonl', 'decision_states.jsonl',
                          'trajectory.jsonl', 'runtime.json', 'evaluation/final_task_audit.json', 'workspace/_runtime/state.json')]
                files += list((episode / 'workspace/public').glob('*'))
                files += list((episode / 'workspace/_runtime/artifacts').glob('*'))
            for path in sorted(set(files)):
                if path.is_file():
                    if path.is_symlink() or not path.resolve().is_relative_to(run.resolve()):
                        raise ValueError('Experiment path escaped run folder')
                    zipped.write(path, path.relative_to(PROJECT).as_posix())
    write_rows(output / 'records/runs.jsonl', inventory)

    # Validate the copied entry point with copied packets and the host's pinned
    # external runtime/tokenizer. The shipped profiles remain unmodified.
    code = '''import json,sys,pathlib,yaml
project=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(project))
from scripts.run_formal_runtime_audit import inspect_cohort
reports=[]
for runtime in ('lean48','lean422'):
 config=yaml.safe_load((project/f'config/shared_environment/formal40_fixed_{runtime}_pythagoras_b12.yaml').read_text(encoding='utf-8'))
 config['lean_cache']=sys.argv[2]
 config['executor']['formal_protocol']['tokenizer_path']=sys.argv[3]
 packets,report=inspect_cohort(config)
 reports.append({'runtime':runtime,'packets':len(packets),'passed':report['passed'],'runtime_lock_verified':report['runtime_lock_verified']})
print(json.dumps(reports))
'''
    native = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(payload),
                            str((PROJECT.parent / '.routingbench_lean_cache').resolve()),
                            str((PROJECT / expected['executor']['formal_protocol']['tokenizer_path']).resolve())],
                            capture_output=True, text=True, encoding='utf-8', timeout=120)
    if native.returncode:
        raise RuntimeError('Staged runtime validation failed: ' + native.stderr[-3000:])
    native_reports = json.loads(native.stdout)
    credential = re.compile(rb'\b(?:hf_[A-Za-z0-9]{20,}|sk-(?:or-v1-)?[A-Za-z0-9_-]{20,})\b')
    secret_matches = [str(path.relative_to(output)) for path in payload.rglob('*')
                      if path.is_file() and path.suffix in ('.py', '.json', '.yaml', '.txt', '.md') and credential.search(path.read_bytes())]
    if secret_matches:
        raise ValueError(f'Credential-like literal needs review (values withheld): {secret_matches}')
    preparation = read(source_bank / 'preparation_report.json')
    write(output / 'integration_manifest.json', {
        'component_version': VERSION, 'status': 'prepared_for_combined_assembly', 'included_domains': ['formal_proof'],
        'combined_release_scope': ['formal_proof', 'structured_data_processing', 'track_a_partial'],
        'structured_data_or_track_a_changes_included': False, 'upload_performed': False,
        'legacy_packager_or_registry_modified': False, 'packets': 40, 'effective_roles': 7,
        'human_review_status': 'pending', 'routing_labels': 'pending', 'results_status': results_status,
        'selected_episode_slots': 200, 'completed_selected_episodes': sum(row['completed'] for row in selected),
        'source_run_root': RUNS.relative_to(PROJECT).as_posix(),
        'pending_selected_episodes': [row for row in selected if not row['completed']],
        'bank_original_bytes_preserved': True, 'bank_readme_and_preparation_report': 'historical_snapshot',
        'effective_role_cards': 'payload/' + role_path.as_posix(),
        'bank_original_role_cards': 'preserved_historical_Inspector_card_overridden_by_current_profile',
        'evaluator_only_artifacts_present_locally': True, 'private_artifact_publication_policy': 'defer_to_combined_release',
        'raw_logs_publication_policy': 'local_audit_archive_review_at_combined_assembly',
        'external_resources_not_bundled': ['model_weights', 'tokenizer_cache', 'Lean_Mathlib_binaries'],
        'validated_platform': 'Windows', 'output_format': 'domain_component_jsonl_not_final_HF_parquet',
    })
    write(output / 'validation_report.json', {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'packet_validation': '40/40',
        'bank_integrity_verified': True, 'profile_parity': '10 profiles differ only in router/cohort metadata',
        'python_source_files': len(source_files), 'native_staged_cohort_checks': native_reports,
        'external_resources_used_only_for_validation': True, 'hosted_model_calls': 0,
        'witness_evidence_reused': {'kernel_pass': preparation['individual_private_witness_kernel_pass'],
                                  'report_sha256': sha(source_bank / 'preparation_report.json')},
        'review_status_preserved': dict(Counter(row['human_review_status'] for row in task_rows)),
        'frozen_formal_runtime_match': True, 'full_source_match': not mismatches,
        'unrelated_source_changes': unrelated_changes, 'credential_literal_scan': 'no_matches_in_payload_text',
        'other_domains_registry_and_Hub_mutations': 0,
    })
    (output / 'README.md').write_text(
        '# Formal40 component: prepared locally, not uploaded\n\n'
        'This component is for the upcoming combined Formal Proof + Structured Data + partial Track A release.\n'
        'It is not a final Hub upload folder. It contains local evaluator-only artifacts and an audit log archive.\n\n'
        'Use integration_manifest.json and records/*.jsonl when assembling the combined dataset. '
        'Keep pending review/result statuses; do not inherit human_verified from the legacy formal30 packager.\n\n'
        'Current instructions: [release preparation](payload/docs/formal40_release_preparation_vi.md).\n'
        'Publication notes: [router/fixed observations](payload/docs/formal40_router_fixed_release_observations_vi.md).\n'
        'Original bank README/role pool are historical; the shipped profiles select the current Inspector role card.\n'
        'Model/tokenizer/native runtime resources are external, not bundled. Staged native gates used verified host resources.\n',
        encoding='utf-8')
    write(output / 'file_manifest.json', {'algorithm': 'sha256', 'files': {
        path.relative_to(output).as_posix(): sha(path) for path in sorted(output.rglob('*')) if path.is_file()}})
    receipt = verify(output)
    if not receipt['passed']:
        raise ValueError(receipt)
    archive_path = output.with_suffix('.zip')
    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                zipped.write(path, Path(output.name) / path.relative_to(output))
    receipt.update(component=str(output), archive=str(archive_path), archive_sha256=sha(archive_path),
                   upload_performed=False, status='prepared_for_combined_assembly')
    write(output.parent / (output.name + '_verification.json'), receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=STAGING / 'formal40_20261122_final40_grouped')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    report = verify(args.verify) if args.verify else build(args.output)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
