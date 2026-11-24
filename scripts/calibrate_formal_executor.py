"""Compare decoding modes on identical saved public contexts, without a router.

Never writes to the source run, reads private witnesses, or retries model output
failures. Each case/mode is one explicitly recorded request. Optional real Lean
checks use separate workspaces and the existing public submission/verifier tools.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import yaml

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from routing_benchmark.v4.artifacts.schema import sha256_file
from routing_benchmark.v4.execution.adapters.common import write_json
from routing_benchmark.v4.execution.adapters.formal_proof_v2 import FormalProofV2Adapter
from routing_benchmark.v4.execution.formal_actor import FormalRoleActor, PROOF_ROLES
from routing_benchmark.v4.execution.formal_handoff import attach_handoff, delivered_evidence
from routing_benchmark.v4.execution.runtime import resolve_runtime

VARIANTS = ('greedy', 'sampled', 'aux_no_think', 'all_no_think')


def select_cases(run, packets, limit):
    # Round-robin roles prevents a small pilot from measuring only synthesis.
    groups = {role: [] for role in ('Formal Failure Diagnostician', 'Proof Repair Specialist', 'Tactic Synthesizer')}
    for episode in sorted((run / 'episodes').iterdir()):
        if not (episode / 'result.json').is_file() or (packets and episode.name not in packets):
            continue
        trace = episode / 'trajectory.jsonl'
        seen = set()
        for line in trace.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            role = row.get('agent_id')
            if role not in groups or role in seen:
                continue
            requests = row.get('result', {}).get('requests', [])
            if requests and 'executor_payload' in requests[0]:
                groups[role].append({'packet': episode.name, 'role': role, 'request': requests[0],
                                     'trace': trace, 'workspace': episode / 'workspace'})
                seen.add(role)
    selected = []
    for index in range(max(map(len, groups.values()), default=0)):
        for group in groups.values():
            if index < len(group):
                selected.append(group[index])
    return selected[:limit]


def variant_protocol(base, variant):
    protocol = copy.deepcopy(base)
    protocol['version'] = 'artifact_first_v2'
    protocol['generation'] = {'temperature': 0} if variant == 'greedy' else {'temperature': 0.6, 'top_p': 0.95}
    protocol['role_generation'] = {}
    if variant in ('aux_no_think', 'all_no_think'):
        protocol['role_generation'] = {role: {'enable_thinking': False}
            for role in ('Formal Failure Diagnostician', 'Premise and Lemma Retriever')}
    if variant == 'all_no_think':
        for role in PROOF_ROLES:
            protocol['role_generation'][role] = {'enable_thinking': False}
    return protocol


def check_proof(config, case, product, folder):
    root = PROJECT / config['packet_root']
    manifest = root / 'packs/formal_proof' / case['packet'] / 'manifest.json'
    adapter = FormalProofV2Adapter()
    adapter.configure_runtime(resolve_runtime(config, manifest, PROJECT))
    env = adapter.materialize(manifest, folder / 'workspace')
    submission = adapter.execute_tool(env, 'write_source', {'content': product})
    report = {'submission_status': submission.status, 'tool_events': [submission.to_dict()]}
    if submission.status == 'success':
        compilation = adapter.execute_tool(env, 'compile_proof')
        report['tool_events'].append(compilation.to_dict())
        report['compiled'] = compilation.status == 'success'
        if report['compiled']:
            verification = adapter.execute_tool(env, 'verify_proof')
            report['tool_events'].append(verification.to_dict())
            report['verified'] = verification.output.get('passed', False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True, help='Existing source run; read only')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the source run')
    parser.add_argument('--packet', action='append')
    parser.add_argument('--max-contexts', type=int, default=8)
    parser.add_argument('--variants', nargs='+', choices=VARIANTS, default=list(VARIANTS[:3]))
    parser.add_argument('--check-only', action='store_true', help='Render/check contexts, no model requests')
    parser.add_argument('--check-proofs', action='store_true', help='Compile/verify eligible proofs in separate workspaces')
    args = parser.parse_args()
    source, output = args.run.resolve(), args.output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output) or output.exists():
        parser.error('Use a new output directory separate from the source run')
    if args.max_contexts <= 0:
        parser.error('--max-contexts must be positive')
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    cases = select_cases(source, args.packet, args.max_contexts)
    if not cases:
        parser.error('No completed episodes with saved executor contexts were found')
    if not args.check_only:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(PROJECT.parent / '.env')
        load_dotenv(PROJECT / '.env')
        client = OpenAI(api_key=os.environ[config['executor'].get('api_key_env', 'HF_TOKEN')],
                        base_url=config['executor']['base_url'], timeout=120, max_retries=0)
    else:
        client = None
    output.mkdir(parents=True)
    hashes = {str(case['trace']): sha256_file(case['trace']) for case in cases}
    rows = []
    try:
        for index, case in enumerate(cases):
            for variant in args.variants:
                actor = FormalRoleActor(client, config['executor']['model'], transport_retries=0,
                                        formal_protocol=variant_protocol(config['executor']['formal_protocol'], variant))
                actor.action = case['role']
                actor.max_tokens = actor.protocol['proof_max_tokens' if case['role'] in PROOF_ROLES else 'diagnosis_max_tokens']
                payload = copy.deepcopy(case['request']['executor_payload'])
                context = payload['public_context']
                context['context_policy'] = 'bounded_artifact_handoff_v2'
                attach_handoff(SimpleNamespace(workspace_dir=case['workspace']), context)
                adapter = SimpleNamespace(adapter_id='formal_proof.lean4.v2')
                instruction = actor.instruction_for('Return only one allowed JSON tool call.', action=case['role'], adapter=adapter,
                                                     plain_tool='write_source' if case['role'] in PROOF_ROLES else 'write_diagnosis')
                payload = actor.prepare_payload(payload, adapter=adapter, instruction=instruction)
                messages = [{'role': 'system', 'content': 'You are a bounded executor in a multi-agent workflow.'},
                            {'role': 'user', 'content': instruction + '\n' + actor.render_payload(payload, adapter)}]
                row = {'case': index, 'packet': case['packet'], 'role': case['role'], 'variant': variant,
                       'max_tokens': actor.max_tokens, 'generation_options': actor.generation_options(),
                       'messages_sha256': hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(),
                       'input_budget': payload['public_context']['input_budget'],
                       'delivered_evidence': delivered_evidence(payload['public_context'])}
                folder = output / f'{index:02d}_{variant}'
                if not args.check_only:
                    try:
                        raw, metadata = actor._query(messages)
                        eligible = not metadata.get('generation_error')
                        try:
                            reading = json.loads(raw).get('tool') == 'read_artifact'
                        except (ValueError, AttributeError):
                            reading = False
                        if case['role'] == 'Formal Failure Diagnostician':
                            eligible = eligible and bool(metadata.get('diagnosis_artifact'))
                        eligible = eligible and not reading
                        row.update(metadata=metadata, artifact_eligible=eligible, read_requested=reading)
                        write_json(folder / 'response.json', {'raw_output': raw, 'metadata': metadata})
                        if args.check_proofs and eligible and case['role'] in PROOF_ROLES:
                            row['proof_check'] = check_proof(config, case, actor.prepare_work_product(raw, metadata), folder)
                    except Exception as error:
                        # Do not print credentials, response bodies, or retry silently.
                        row.update(error_type=type(error).__name__, artifact_eligible=False,
                                   cause_type=getattr(error, 'cause_type', None),
                                   http_status=getattr(error, 'http_status', None))
                write_json(folder / 'request.json', {'messages': messages, 'options': actor.generation_options(),
                                                     'max_tokens': actor.max_tokens})
                rows.append(row)
                write_json(output / 'report.json', {'mode': 'fixed_public_context_executor_calibration',
                    'router_calls': 0, 'check_only': args.check_only, 'cases': len(cases), 'rows': rows,
                    'source_trace_sha256': hashes, 'uses_private_witness': False})
                print(json.dumps({k: row.get(k) for k in ('case', 'packet', 'role', 'variant', 'artifact_eligible', 'error_type')}), flush=True)
    finally:
        if client:
            client.close()
    if any(sha256_file(Path(path)) != digest for path, digest in hashes.items()):
        raise RuntimeError('Source trajectory changed during calibration')
    return int(any(row.get('error_type') for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
