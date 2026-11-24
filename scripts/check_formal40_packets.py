"""Packet preflight and real Lean adapter checks for the formal40 release."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from routing_benchmark.v4.artifacts.manifest import load_manifest, validate_artifact_pack
from routing_benchmark.v4.artifacts.schema import sha256_file
from routing_benchmark.v4.domain_packets.roles import role_cards_for
from routing_benchmark.v4.execution.adapters.common import read_json, write_json
from routing_benchmark.v4.execution.adapters.formal_proof import proof_template
from routing_benchmark.v4.execution.adapters.formal_proof_v2 import dependency_probe
from routing_benchmark.v4.execution.final_evaluation import audit_domain
from routing_benchmark.v4.execution.registry import live_adapter_for_manifest
from routing_benchmark.v4.execution.runtime import resolve_runtime


def preflight(root, checks):
    config = {'domain': 'formal_proof', 'packet_root': str(root), 'lean_cache': '../.routingbench_lean_cache'}
    manifests = sorted((root / 'packs/formal_proof').glob('*/manifest.json'))
    if len(manifests) != 40:
        raise ValueError('Expected exactly 40 selected packets')
    rows = []
    for path in manifests:
        manifest = load_manifest(path)
        if not validate_artifact_pack(path.parent)['valid']:
            raise ValueError(f'Invalid manifest {path}')
        adapter = live_adapter_for_manifest(manifest)
        adapter.configure_runtime(resolve_runtime(config, path, PROJECT))
        env = adapter.materialize(path, checks / 'static' / manifest.base_workflow_id / 'workspace')
        if any((env.workspace_dir / entry.path).exists()
               for entry in (*manifest.private_files, *manifest.fixture_files)):
            raise ValueError('Private/fixture artifact was materialized')
        observation = adapter.public_observation(env)
        json.dumps(observation)
        for role in role_cards_for('formal_proof'):
            context = adapter.executor_context(env, role['agent_id'], role)
            json.dumps(context)
            schemas = adapter.tool_spec(env, role['agent_id'], role)
            if not schemas:
                raise ValueError('Role has no tools')
            source = context['state']['source']
            if context['state']['source_access']['total_chars'] > len(source):
                raise ValueError('Initial source exceeds the readable public preview')
        seeded = read_json(env.workspace_dir / 'public/execution_contract.json')['initial_candidate']
        if seeded and observation['artifacts']['candidate']['sha256'] != observation['source_hash']:
            raise ValueError('Initial candidate bytes differ from the public source')
        if adapter.public_preconditions(env, 'Lean Compiler Executor').executable != seeded:
            raise ValueError('Initial compiler precondition differs from declared candidate state')
        before = adapter.versions(env)
        invalid = adapter.execute_tool(env, 'write_source', {'content': 'theorem altered : True := by trivial'})
        if invalid.status != 'invalid_output' or adapter.versions(env) != before:
            raise ValueError('Statement mutation was accepted')
        reference = (path.parent / 'private/Reference.lean').read_text(encoding='utf-8')
        if adapter.execute_tool(env, 'write_source', {'content': reference}).status != 'success':
            raise ValueError('Witness envelope rejected by live adapter')
        accepted = adapter.versions(env)
        invalid = adapter.execute_tool(env, 'write_source', {'content': 'by\n  axiom leaked : False'})
        if invalid.status != 'invalid_output' or adapter.versions(env) != accepted:
            raise ValueError('Forbidden source changed current candidate')
        if not adapter.public_observation(env)['artifacts']['candidate']['fresh']:
            raise ValueError('Rejected source invalidated the accepted candidate')
        if not adapter.public_preconditions(env, 'Lean Compiler Executor').executable:
            raise ValueError('Accepted candidate cannot be compiled')
        if adapter.public_preconditions(env, 'Kernel and Assumption Verifier').executable:
            raise ValueError('Uncompiled candidate was verifiable')
        rows.append({
            'packet_id': manifest.base_workflow_id, 'manifest_valid': True,
            'public_only': True, 'role_contexts_serializable_and_readable': 7,
            'initial_candidate_registered': seeded, 'immutable_statement_enforced': True,
            'witness_envelope_accepted': True, 'rejected_candidate_pointer_preserved': True,
        })
        print('preflight', manifest.base_workflow_id, flush=True)
    write_json(checks / 'static_report.json', {'packets': rows, 'passed': True})


def smoke(root, checks, packet):
    path = root / 'packs/formal_proof' / packet / 'manifest.json'
    folder = checks / 'smoke' / packet
    if (folder / 'report.json').exists():
        return read_json(folder / 'report.json')
    if (folder / 'workspace').exists():
        ordinal = 1
        while (checks / 'smoke_attempts' / str(ordinal) / packet).exists():
            ordinal += 1
        folder = checks / 'smoke_attempts' / str(ordinal) / packet
    manifest = load_manifest(path)
    config = {'domain': 'formal_proof', 'packet_root': str(root), 'lean_cache': '../.routingbench_lean_cache'}
    adapter = live_adapter_for_manifest(manifest)
    adapter.configure_runtime(resolve_runtime(config, path, PROJECT))
    env = adapter.materialize(path, folder / 'workspace')
    reference = (path.parent / 'private/Reference.lean').read_text(encoding='utf-8')
    if manifest.source_type == 'april':
        initial = adapter.execute_tool(env, 'compile_proof')
        if initial.output['result']['returncode'] == 0:
            raise ValueError('Upstream faulty proof unexpectedly compiled')
        write_json(folder / 'initial_failure.json', initial.to_dict())
    adapter.execute_tool(env, 'write_source', {'content': reference})
    compilation = adapter.execute_tool(env, 'compile_proof')
    write_json(folder / 'compilation.json', compilation.to_dict())
    if compilation.status != 'success':
        raise ValueError(f'Reference compile failed for {packet}')
    verification = adapter.execute_tool(env, 'verify_proof')
    write_json(folder / 'verification.json', verification.to_dict())
    if not verification.output['passed'] or not adapter.terminal_status(env)['terminal']:
        raise ValueError(f'Witness kernel verification failed for {packet}')
    candidate_hash = adapter.versions(env)['source_hash']
    # A new candidate must invalidate the old compilation/verification evidence.
    adapter.execute_tool(env, 'write_source', {'content': reference + '\n-- new artifact version\n'})
    if adapter.public_preconditions(env, 'Kernel and Assumption Verifier').executable or adapter.terminal_status(env)['terminal']:
        raise ValueError('Stale evidence remained terminal')
    final = audit_domain(folder, config, PROJECT)
    if final.get('status') != 'PASS':
        raise ValueError(f'Independent final checker failed for {packet}: {final}')
    write_json(folder / 'positive_audit.json', final)
    # A proof hole must fail trusted verification even though Lean accepts the declaration.
    prefix, _ = proof_template(reference)
    adapter.execute_tool(env, 'write_source', {'content': prefix + ' by sorry\n'})
    negative = audit_domain(folder, config, PROJECT)
    if negative.get('status') != 'FAIL':
        raise ValueError('A proof hole passed the independent evaluator')
    write_json(folder / 'negative_audit.json', negative)
    report = {
        'packet_id': packet, 'passed': True, 'reference_source_sha256': candidate_hash,
        'witness_compiles_and_kernel_passes': True, 'changed_candidate_stales_evidence': True,
        'independent_final_checker_pass': True, 'proof_hole_negative_fails': True,
        'initial_fault_compiler_checked': manifest.source_type == 'april',
        'evidence_directory': str(folder),
    }
    write_json(folder / 'report.json', report)
    write_json(checks / 'smoke' / packet / 'report.json', report)
    print('smoke', packet, 'PASS', flush=True)
    return report


def dependency_negative(checks):
    from scripts.prepare_formal40_packets import compile_source
    source = '''import Mathlib
theorem formal40Direct {x m n : Nat} (h : n ≤ m) (hx : 0 < x) :
    x ^ m / x ^ n = x ^ (m - n) := by
  exact Nat.pow_div h hx
'''
    source += dependency_probe('formal40Direct', ['Nat.pow_div'])
    source += '''
private theorem formal40Alias {x m n : Nat} (h : n ≤ m) (hx : 0 < x) :
    x ^ m / x ^ n = x ^ (m - n) := Nat.pow_div h hx
theorem formal40Indirect {x m n : Nat} (h : n ≤ m) (hx : 0 < x) :
    x ^ m / x ^ n = x ^ (m - n) := formal40Alias h hx
'''
    source += dependency_probe('formal40Indirect', ['Nat.pow_div']).replace(
        'formal40CheckDependencies', 'formal40CheckIndirectDependencies')
    path = checks / 'dependency_negative.lean'
    path.write_text(source, encoding='utf-8', newline='\n')
    result = compile_source(path, '4.8.0-rc1')
    passed = result['returncode'] != 0 and result['stdout'].count(
        'error: Forbidden reference to benchmark target: Nat.pow_div') == 2
    write_json(checks / 'dependency_negative.json', {'passed': passed, 'compilation': result})
    if not passed:
        raise ValueError('Direct/transitive target exclusion did not pass its negative control')
    print('dependency negative PASS', flush=True)


def finalize(root, checks, preparation):
    selection = read_json(root / 'selection.json')
    selected = {row['packet_id']: row for row in selection['packets']}
    individual = read_json(preparation / 'individual_kernel_report.json')
    faults = read_json(preparation / 'initial_candidate_checks.json')
    static = read_json(checks / 'static_report.json')
    regression = read_json(checks / 'regression_report.json')
    if not all(report['passed'] for report in (individual, faults, static,
            regression, read_json(checks / 'dependency_negative.json'), read_json(checks / 'v2_contract_report.json'))):
        raise ValueError('A required preparation gate has not passed')
    if {row['packet_id'] for row in individual['packets']} != set(selected):
        raise ValueError('Individual kernel coverage differs from selection')
    if {row['packet_id'] for row in static['packets']} != set(selected):
        raise ValueError('Static packet coverage differs from selection')
    for row in individual['packets']:
        pack = root / 'packs/formal_proof' / row['packet_id']
        if sha256_file(pack / 'private/Reference.lean') != row['reference_sha256']:
            raise ValueError('Private witness changed after individual kernel verification')
        if not validate_artifact_pack(pack)['valid']:
            raise ValueError('Final manifest integrity check failed')
        state = read_json(pack / 'public/proof_state.json')
        if state['source_sha256'] != sha256_file(pack / 'public/Main.lean'):
            raise ValueError('Initial goal provenance is stale')
    for row in faults['packets']:
        if sha256_file(root / 'packs/formal_proof' / row['packet_id'] / 'public/Main.lean') != row['initial_sha256']:
            raise ValueError('Seeded repair candidate changed after compilation check')
    smoke_ids = ['formal40-01-minif2f', 'formal40-09-leandojo', 'formal40-33-april', 'formal40-39-putnam']
    smokes = [read_json(checks / 'smoke' / packet / 'report.json') for packet in smoke_ids]
    if not all(row['passed'] for row in smokes):
        raise ValueError('An adapter integration smoke did not pass')
    sources = [
        PROJECT / 'scripts/prepare_formal40_packets.py', Path(__file__).resolve(),
        PROJECT / 'routing_benchmark/v4/execution/adapters/formal_proof.py',
        PROJECT / 'routing_benchmark/v4/execution/adapters/formal_proof_v2.py',
        PROJECT / 'routing_benchmark/v4/execution/shared_actor.py',
        PROJECT / 'routing_benchmark/v4/execution/shared_runner.py',
        PROJECT / 'routing_benchmark/v4/execution/final_evaluation.py',
        PROJECT / 'routing_benchmark/v4/execution/runtime.py',
        PROJECT / 'routing_benchmark/v4/execution/registry.py',
        PROJECT / 'routing_benchmark/v4/domain_packets/roles.py',
        PROJECT / 'config/shared_environment/formal40_pythagoras4b_jev.yaml',
    ]
    report = {
        'stage': 'deterministic-ready', 'packets': 40, 'context_pass': 40,
        'individual_private_witness_kernel_pass': 40, 'manifest_valid': 40,
        'public_only_and_role_context_checks': 40, 'seeded_proof_failures_confirmed': 10,
        'adapter_integration_smokes': smokes, 'dependency_shortcut_negative_pass': True,
        'v2_contract_checks_pass': True, 'configured_executor': selection['executor'],
        'regression_tests_passed': regression['cases'],
        'configured_budget': 12, 'hosted_model_calls': 0, 'benchmark_trajectories': 0,
        'human_review_status': 'pending', 'pythagoras_pilot': 'pending',
        'provider_io_smoke': 'pending',
        'evidence': {'preparation': str(preparation), 'preflight': str(checks)},
        'source_code_hashes': {str(path.relative_to(PROJECT)): sha256_file(path) for path in sources},
        'evidence_report_hashes': {
            str(path): sha256_file(path) for path in (
                preparation / 'individual_kernel_report.json',
                preparation / 'initial_candidate_checks.json',
                checks / 'static_report.json', checks / 'dependency_negative.json',
                checks / 'v2_contract_report.json', checks / 'regression_report.json',
                *(checks / 'smoke' / packet / 'report.json' for packet in smoke_ids),
            )
        },
    }
    write_json(root / 'preparation_report.json', report)
    with (root / 'packet_list.csv').open('w', encoding='utf-8-sig', newline='') as file:
        fields = ['number', 'packet_id', 'source', 'source_id', 'topic', 'task_type',
                  'static_difficulty', 'runtime_verified', 'pythagoras_pilot']
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows({**row, 'runtime_verified': True, 'pythagoras_pilot': 'pending'}
                         for row in selection['packets'])
    write_json(root / 'integrity_manifest.json', {
        'status': 'preparation_verified',
        'files': {str(path.relative_to(root)).replace('\\', '/'): sha256_file(path)
                  for path in sorted(root.rglob('*')) if path.is_file() and path.name != 'integrity_manifest.json'},
    })
    print('Finalized 40 deterministic-ready formal packets', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=PROJECT / 'data/RoutingBench/formal40_pythagoras_v1_20261118')
    parser.add_argument('--checks', type=Path, default=PROJECT / 'runs/formal40_preflight_20261118')
    parser.add_argument('--static', action='store_true')
    parser.add_argument('--smoke', action='append', default=[])
    parser.add_argument('--dependency-negative', action='store_true')
    parser.add_argument('--finalize', action='store_true')
    parser.add_argument('--preparation', type=Path, default=PROJECT / 'runs/formal40_preparation_20261118')
    args = parser.parse_args()
    args.checks.mkdir(parents=True, exist_ok=True)
    if args.static:
        preflight(args.root, args.checks)
    if args.dependency_negative:
        dependency_negative(args.checks)
    for packet in args.smoke:
        smoke(args.root, args.checks, packet)
    if args.finalize:
        finalize(args.root, args.checks, args.preparation)


if __name__ == '__main__':
    main()
