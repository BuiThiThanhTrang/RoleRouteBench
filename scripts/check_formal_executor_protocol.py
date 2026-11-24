"""Offline handoff preflight, optional real Lean smokes, and recorded-loop replay.

All generated workspaces are preparation evidence. Witness-backed test doubles
are not model trajectories and do not measure executor accuracy.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import sys

import yaml

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from routing_benchmark.routers import RoutingDecision
from routing_benchmark.v4.artifacts.schema import sha256_file
from routing_benchmark.v4.execution.adapters.common import write_json
from routing_benchmark.v4.execution.adapters.formal_proof import proof_template
from routing_benchmark.v4.execution.adapters.formal_proof_v2 import FormalProofV2Adapter
from routing_benchmark.v4.execution.final_evaluation import audit_domain
from routing_benchmark.v4.execution.formal_actor import FormalRoleActor, END, repetition
from routing_benchmark.v4.execution.runtime import resolve_runtime
from routing_benchmark.v4.execution.shared_runner import SharedTrajectoryRunner
from scripts.run_formal_runtime_audit import inspect_cohort


def configuration(name):
    return yaml.safe_load((PROJECT / 'config/shared_environment' / name).read_text(encoding='utf-8'))


def adapter_for(config, manifest):
    adapter = FormalProofV2Adapter()
    adapter.configure_runtime(resolve_runtime(config, manifest, PROJECT))
    return adapter


def replay(run, actor):
    rows = []
    for packet in ('formal40-10-leandojo', 'formal40-12-leandojo', 'formal40-14-leandojo'):
        path = run / 'episodes' / packet / 'trajectory.jsonl'
        events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
        for number, event in enumerate(events, 1):
            for response in event.get('result', {}).get('responses', []):
                if response['metadata'].get('finish_reason') != 'length':
                    continue
                original = response['raw_output']
                cap = 1024 if event['agent_id'] == 'Formal Failure Diagnostician' else 4096
                ids = actor.tokenizer.encode(original, add_special_tokens=False).ids
                prefix = actor.tokenizer.decode(ids[:cap], skip_special_tokens=False)
                detected, length = None, len(prefix)
                for end in range(128, len(prefix) + 128, 128):
                    detected = repetition(prefix[:end])
                    if detected:
                        length = min(end, len(prefix))
                        break
                rows.append({'packet_id': packet, 'call': number, 'role': event['agent_id'],
                             'original_tokens': len(ids), 'new_role_cap': cap,
                             'detected': detected, 'prefix_tokens_at_stop': len(actor.tokenizer.encode(prefix[:length], add_special_tokens=False).ids),
                             'recorded_trace_sha256': sha256_file(path)})
    return {'mode': 'offline_replay_of_old_outputs_not_new_model_generation', 'responses': rows,
            'detected_before_cap': sum(row['detected'] is not None for row in rows),
            'old_output_tokens': sum(row['original_tokens'] for row in rows),
            'bounded_prefix_tokens': sum(row['prefix_tokens_at_stop'] for row in rows)}


def smoke(config, root, output, packet):
    manifest = root / 'packs/formal_proof' / packet / 'manifest.json'
    adapter = adapter_for(config, manifest)
    reference = (manifest.parent / 'private/Reference.lean').read_text(encoding='utf-8')
    prefix, _ = proof_template(reference)
    body = reference[len(prefix):].strip()

    class WitnessActor(FormalRoleActor):
        def _query(self, messages):
            if self.protocol.get('parser_policy') == 'presentation_v1':
                # Exercise the new full-source transport with the same existing
                # immutable adapter and native checker, without model inference.
                from types import SimpleNamespace
                text = reference + '\n' + END
                class Stream:
                    def __iter__(self):
                        yield SimpleNamespace(model='preparation-test-double', id='witness', usage=None,
                            choices=[SimpleNamespace(finish_reason='stop', delta=SimpleNamespace(content=text))])
                    def close(self): pass
                self.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: Stream())))
                return super()._query(messages)
            return body + '\n' + END, {'artifact_end_offset': len(body), 'finish_reason': 'preparation_test_double',
                                      'usage': None, 'executor_protocol': 'artifact_first_v1'}

    class Sequence:
        def reset(self, seed):
            self.steps = iter(['Proof State Inspector', 'Tactic Synthesizer', 'Lean Compiler Executor', 'Kernel and Assumption Verifier', 'STOP'])

        def select(self, observation, candidates):
            return RoutingDecision(next(self.steps))

    roles = json.loads((PROJECT / config['role_cards']).read_text(encoding='utf-8'))
    folder = output / 'smoke' / packet
    actor = WitnessActor(None, 'preparation-test-double', formal_protocol=config['executor']['formal_protocol'])
    result = SharedTrajectoryRunner(router=Sequence(), actor=actor, max_calls=12).run(
        manifest_path=manifest, adapter=adapter, workspace=folder / 'workspace', output_dir=folder, roles=roles)
    if not result['passed']:
        raise ValueError(f'Witness-backed integration smoke failed: {packet}')
    state = json.loads((folder / 'workspace/_runtime/state.json').read_text(encoding='utf-8'))
    report = json.loads((folder / 'workspace' / state['artifacts']['inspection']['path']).read_text(encoding='utf-8'))
    if report['status'] == 'unavailable':
        raise ValueError(f'Real packet inspection failed: {packet}: {report}')
    final = audit_domain(folder, config, PROJECT)
    if final.get('status') != 'PASS':
        raise ValueError(f'Independent final evaluator failed: {packet}: {final}')
    write_json(folder / 'final_task_audit.json', final)
    print('Real Lean smoke PASS', packet, flush=True)
    return {'packet_id': packet, 'passed': True, 'inspection_status': report['status'],
            'tactic_states': report['captured_tactics'], 'final_evaluator': final['status'],
            'uses_private_witness_test_double': True, 'hosted_model_calls': 0}


def inspect_all(configs, root, output):
    def one(manifest):
        contract = json.loads((manifest.parent / 'public/execution_contract.json').read_text(encoding='utf-8'))
        config = configs['lean422' if '4.22.0-rc4' in contract['toolchain'] else 'lean48']
        adapter = adapter_for(config, manifest)
        env = adapter.materialize(manifest, output / 'inspection' / manifest.parent.name / 'workspace')
        before = adapter.versions(env)
        result = adapter.execute_tool(env, 'inspect_proof')
        if adapter.versions(env) != before or 'compilation' in adapter._state(env)['artifacts']:
            raise ValueError('Inspection mutated or certified a candidate')
        row = {'packet_id': manifest.parent.name, 'passed': result.status == 'success',
               'status': result.output['status'], 'captured_tactics': result.output.get('captured_tactics'),
               'elapsed_ms': result.output.get('elapsed_ms'), 'error': result.output.get('error')}
        print('Inspection', row['packet_id'], row['status'], flush=True)
        return row
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(one, sorted((root / 'packs/formal_proof').glob('*/manifest.json'))))
    report = {'passed': all(row['passed'] for row in rows), 'packets': rows}
    write_json(output / 'inspection_sweep.json', report)
    if not report['passed']:
        raise ValueError('Some initial packets could not be inspected; see inspection_sweep.json')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--real-lean', action='store_true')
    parser.add_argument('--inspect-all', action='store_true')
    parser.add_argument('--replay-run', type=Path)
    parser.add_argument('--profile-prefix', default='formal40_inspector', help='Config prefix, e.g. formal40_recovery_v2')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory to preserve existing preparation evidence')
    args.output.mkdir(parents=True)
    configs = {runtime: configuration(f'{args.profile_prefix}_{runtime}_jev.yaml') for runtime in ('lean48', 'lean422')}
    root = PROJECT / configs['lean48']['packet_root']
    summaries = {}
    for runtime, config in configs.items():
        _, summaries[runtime] = inspect_cohort(config)
    for runtime in configs:
        inspect_cohort(configuration(f'formal40_handoff_{runtime}_jev.yaml'))
    roles = json.loads((PROJECT / configs['lean48']['role_cards']).read_text(encoding='utf-8'))
    rows = []
    actor = FormalRoleActor(None, 'preparation-only', formal_protocol=configs['lean48']['executor']['formal_protocol'])
    for manifest in sorted((root / 'packs/formal_proof').glob('*/manifest.json')):
        contract = json.loads((manifest.parent / 'public/execution_contract.json').read_text(encoding='utf-8'))
        config = configs['lean422' if '4.22.0-rc4' in contract['toolchain'] else 'lean48']
        adapter = adapter_for(config, manifest)
        env = adapter.materialize(manifest, args.output / 'context' / manifest.parent.name / 'workspace')
        if (env.workspace_dir / 'private').exists() or (env.workspace_dir / 'fixtures').exists():
            raise ValueError('Private/fixture materialization leak')
        before = adapter.versions(env)
        marker = 'Observed failure: synthetic public handoff probe from preparation, not a model diagnosis.'
        adapter.execute_tool(env, 'write_diagnosis', {'content': marker})
        for role in roles:
            context = adapter.executor_context(env, role['agent_id'], role)
            payload = {'task': env.manifest.task, 'role': role, 'public_context': context,
                       'allowed_tools': [tool.to_dict() for tool in adapter.tool_spec(env, role['agent_id'], role)]}
            plain = 'write_source' if role['agent_id'] in ('Tactic Synthesizer', 'Proof Repair Specialist') else 'write_diagnosis'
            instruction = actor.instruction_for('Use the selected role tools.', action=role['agent_id'], adapter=adapter, plain_tool=plain)
            payload = actor.prepare_payload(payload, adapter=adapter, instruction=instruction)
            if marker not in json.dumps(payload):
                raise ValueError('Handoff probe was not delivered')
            if 'Reference.lean' in json.dumps(payload) or 'upstream_record' in json.dumps(payload):
                raise ValueError('Private oracle/provenance leaked into executor context')
            rows.append({'packet_id': manifest.parent.name, 'role': role['agent_id'],
                         'input_budget': payload['public_context']['input_budget'], 'handoff_delivered': True})
        if adapter.versions(env) != before:
            raise ValueError('Context building changed the proof')
    write_json(args.output / 'context_report.json', {'passed': True, 'packets': 40, 'role_contexts': rows})
    smokes = [smoke(configs['lean48'], root, args.output, 'formal40-09-leandojo'),
              smoke(configs['lean422'], root, args.output, 'formal40-33-april')] if args.real_lean else []
    sweep = inspect_all(configs, root, args.output) if args.inspect_all else None
    if args.replay_run:
        write_json(args.output / 'repetition_replay.json', replay(args.replay_run, actor))
    files = [Path(__file__), *list((PROJECT / 'routing_benchmark/v4/execution').rglob('*.py')),
             *list((PROJECT / 'routing_benchmark/v4/execution/lean').glob('*.lean'))]
    write_json(args.output / 'report.json', {'passed': True, 'packet_contexts': 40, 'role_contexts': len(rows),
               'config_checks': summaries, 'real_lean_smokes': smokes, 'hosted_model_calls': 0,
               'inspection_sweep_passed': sweep['passed'] if sweep else None,
               'benchmark_trajectories': 0, 'provider_streaming_smoke': 'pending',
               'source_hashes': {str(path.relative_to(PROJECT)): sha256_file(path) for path in files if '__pycache__' not in path.parts}})
    print('PASS: 40 packets, 280 role contexts; hosted model calls: 0', flush=True)


if __name__ == '__main__':
    main()
