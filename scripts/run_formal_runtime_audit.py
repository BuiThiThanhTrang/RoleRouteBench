"""Select a formal runtime cohort, verify its pinned runtime, then use the shared runner.

Use this entry point for configs containing runtime_audit. The shared runner's
--packet flags record the exact selection in resolved_config.json. Selection is
based on public contracts, independently of packet names and dataset provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from routing_benchmark.v4.artifacts.manifest import load_manifest, validate_artifact_pack
from routing_benchmark.v4.artifacts.schema import sha256_file
from routing_benchmark.v4.execution.runtime import resolve_runtime


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def resolve(path):
    path = Path(path)
    return path.resolve() if path.is_absolute() else (PROJECT / path).resolve()


def inspect_cohort(config):
    if config['domain'] != 'formal_proof':
        raise ValueError('This audit requires the formal_proof domain')
    audit = config['runtime_audit']
    version, revision = audit['lean_version'], audit['mathlib_revision']
    root = resolve(config['packet_root'])
    packets, runtime = [], None
    for path in sorted((root / 'packs/formal_proof').glob('*/manifest.json')):
        contract = read_json(path.parent / 'public/execution_contract.json')
        match = re.fullmatch(r'Lean (\d+\.\d+\.\d+(?:-rc\d+)?) with Mathlib4 ([0-9a-f]{40})', contract['toolchain'])
        if not match:
            raise ValueError(f'Unrecognized runtime contract: {path}')
        if match[1] != version:
            continue
        if match[2] != revision:
            raise ValueError(f'Unexpected Mathlib revision: {path}')
        manifest = load_manifest(path)
        if manifest.base_workflow_id != path.parent.name:
            raise ValueError(f'Packet directory and manifest ID differ: {path}')
        if not validate_artifact_pack(path.parent)['valid']:
            raise ValueError(f'Packet integrity check failed: {path}')
        profile = resolve_runtime(config, path, PROJECT)
        if runtime is not None and profile != runtime:
            raise ValueError('The selected cohort resolves to multiple runtime profiles')
        runtime = profile
        packets.append(manifest.base_workflow_id)
    if len(packets) != audit['expected_packets']:
        raise ValueError(f"Expected {audit['expected_packets']} packets, found {len(packets)}")
    if not packets:
        raise ValueError('Empty audit cohort')

    locked = read_json(root / 'runtime_lock.json')[version]
    runtime_files = {
        'lean_binary_sha256': Path(runtime['lean_executable']),
        'mathlib_toolchain_sha256': Path(runtime['project_dir']) / 'lean-toolchain',
        'lake_manifest_sha256': Path(runtime['project_dir']) / 'lake-manifest.json',
    }
    for key, path in runtime_files.items():
        if sha256_file(path) != locked[key]:
            raise ValueError(f'Runtime lock mismatch: {path}')
    commit = subprocess.check_output(
        ['git', '-C', runtime['project_dir'], 'rev-parse', 'HEAD'], text=True,
    ).strip()
    if commit != revision:
        raise ValueError(f'Mathlib checkout mismatch: expected {revision}, found {commit}')
    binary_version = subprocess.check_output([runtime['lean_executable'], '--version'], text=True).strip()
    if not re.search(r'\bLean \(version ' + re.escape(version) + r'(?:,|\))', binary_version):
        raise ValueError(f'Lean executable version mismatch: {binary_version}')
    protocol = config['executor'].get('formal_protocol')
    if protocol:
        from routing_benchmark.v4.execution.formal_actor import FormalRoleActor
        FormalRoleActor(None, config['executor']['model'], max_tokens=config['executor']['max_tokens'], formal_protocol=protocol)
    return packets, {
        'passed': True, 'lean_version': version, 'mathlib_revision': revision,
        'packets': packets, 'packet_count': len(packets),
        'runtime_lock_verified': True, 'lean_binary_version': binary_version,
        'router': config['router'].get('model', config['router'].get('type', 'decision')),
        'executor': config['executor']['model'],
        'max_calls': config['max_calls'],
        'executor_protocol': protocol,
        'formal_context_policy': runtime.get('formal_context_policy', 'legacy'),
        'formal_inspection_policy': runtime.get('formal_inspection_policy', 'legacy'),
        'formal_candidate_identity': runtime.get('formal_candidate_identity', 'exact_source_sha256'),
        'compile_timeout_seconds': runtime.get('compile_timeout_seconds', 180),
        'comparison': 'Different task cohorts; this is not a same-task runtime A/B experiment.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run-id')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--check-only', action='store_true', help='Validate without writing a run or calling any model')
    parser.add_argument('--packet', action='append', help='Run only this packet from the verified runtime cohort; repeatable')
    args = parser.parse_args()
    if not args.check_only and not args.run_id:
        parser.error('--run-id is required when executing an audit')
    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    from routing_benchmark.v4.execution.formal_actor import TokenizerSetupError
    try:
        packets, report = inspect_cohort(config)
    except TokenizerSetupError as error:
        parser.exit(2, str(error) + '\n')
    if args.packet:
        if not set(args.packet).issubset(packets):
            parser.error('--packet must belong to the verified runtime cohort')
        packets = [packet for packet in packets if packet in args.packet]
        report['selected_packets'] = packets
    print(json.dumps(report, indent=2), flush=True)
    if args.check_only:
        return 0
    command = [sys.executable, str(PROJECT / 'scripts/run_shared_environment.py'),
               '--config', str(config_path), '--run-id', args.run_id]
    for packet in packets:
        command.extend(['--packet', packet])
    if args.resume:
        command.append('--resume')
    return subprocess.call(command)


if __name__ == '__main__':
    raise SystemExit(main())
