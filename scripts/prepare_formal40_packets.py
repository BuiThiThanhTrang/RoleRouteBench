"""Build and verify the selected formal cohort using local Lean runtimes."""
from __future__ import annotations

import argparse
import concurrent.futures
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT))

from routing_benchmark.v4.artifacts.manifest import validate_artifact_pack
from routing_benchmark.v4.artifacts.schema import sha256_file
from routing_benchmark.v4.domain_packets.builder import _Writer, _json_bytes
from routing_benchmark.v4.domain_packets.roles import role_cards_for
from routing_benchmark.v4.execution.adapters.formal_proof import proof_template, uncomment
from routing_benchmark.v4.execution.adapters.formal_proof_v2 import dependency_probe

SELECTION = PROJECT / 'data/RoutingBench/formal40_pythagoras_candidate_selection_20261118'
CHECKS = PROJECT / 'runs/formal40_preparation_20261118'
OUTPUT = PROJECT / 'data/RoutingBench/formal40_pythagoras_v1_20261118'
RECIPES = PROJECT / 'data/RoutingBench/formal40_preparation_inputs_20261118'
CACHE = ROOT / '.routingbench_lean_cache'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def runtime(version):
    project = CACHE / ('mathlib-' + '.'.join(version.split('.')[:2]))
    roots = [project, *[p for p in (project / '.lake/packages').iterdir() if p.is_dir()]]
    libraries = [p / '.lake/build/lib' for p in roots]
    return {
        'lean_executable': str(CACHE / f'elan-home/toolchains/leanprover--lean4---v{version}/bin/lean.exe'),
        'project_dir': str(project),
        'lean_path': os.pathsep.join(str(p / 'lean' if (p / 'lean').is_dir() else p) for p in libraries),
    }


def compile_source(path, version):
    profile = runtime(version)
    environment = dict(os.environ, LEAN_PATH=profile['lean_path'])
    try:
        result = subprocess.run(
            [profile['lean_executable'], str(Path(path).resolve())],
            cwd=profile['project_dir'], env=environment, capture_output=True,
            text=True, encoding='utf-8', errors='replace', timeout=180,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'returncode': -1, 'stdout': '', 'stderr': str(error), 'failure_origin': 'tool_environment'}


def active_context(prefix):
    """Copy scoped variable/open commands, retaining only still-open sections."""
    masked = uncomment(prefix, mask_strings=False)
    lines = prefix.splitlines(keepends=True)
    masked_lines = masked.splitlines(keepends=True)
    frames = [[]]
    namespaces = []
    scopes = []
    index = 0
    while index < len(lines):
        line = masked_lines[index]
        scope = re.match(r'^(namespace|section)\b\s*([\w.]*)', line)
        if scope:
            kind, name = scope.groups()
            frames.append([])
            scopes.append(kind)
            if kind == 'namespace':
                frames[-1].append('namespace ' + name + '\n')
                namespaces.append(name)
        elif re.match(r'^end\b', line) and scopes:
            if scopes.pop() == 'namespace':
                namespaces.pop()
            frames.pop()
        elif re.match(r'^(?:open|universe|variable|local (?:notation|infixr?|infixl|prefix|postfix))\b', line):
            end = index + 1
            while end < len(lines) and (not masked_lines[end].strip() or masked_lines[end][:1].isspace()):
                end += 1
            frames[-1].append(''.join(lines[index:end]).rstrip() + '\n')
            index = end - 1
        index += 1
    return ''.join(command for frame in frames for command in frame), '.'.join(namespaces)


def initial_recipes():
    selection = read_json(SELECTION / 'selection.json')
    for row in selection['packets']:
        source_path = SELECTION / row['private_record_path']
        if sha256_file(source_path) != row['source_record_sha256']:
            raise ValueError(f'Source record hash mismatch: {row["packet_id"]}')
        record = read_json(source_path)
        folder = RECIPES / row['packet_id']
        folder.mkdir(parents=True, exist_ok=True)
        if (folder / 'recipe.json').exists():
            continue
        adaptations = []
        forbidden = []
        target_declaration = None
        if row['source'] == 'minif2f':
            original = PROJECT / 'data/RoutingBench/v4_minif2f_20_20261101/packs/formal_proof' / ('proof-minif2f-' + row['source_id'].replace('_', '-'))
            reference = (original / 'private/Reference.lean').read_text(encoding='utf-8')
            initial = record['lean4_code'].rstrip() + '\n'
            version = '4.8.0-rc1'
        elif row['source'] == 'april':
            reference = record['correct_proof'].rstrip() + '\n'
            initial = record['incorrect_proof'].rstrip() + '\n'
            version = '4.22.0-rc4'
        elif row['source'] == 'putnam':
            initial = record['source'].rstrip() + '\n'
            reference = initial
            version = '4.8.0-rc1'
        else:
            upstream = PROJECT / 'data/RoutingBench/formal40_candidate_sources_20261118/mathlib_original' / record['file_path']
            text = upstream.read_text(encoding='utf-8')
            lines = text.splitlines(keepends=True)
            start, end = record['start'], record['end']
            declaration = ''.join(lines[start[0] - 1:end[0] - 1]) + lines[end[0] - 1][:end[1] - 1]
            declaration = declaration[re.search(r'\b(?:theorem|lemma)\b', uncomment(declaration)).start():]
            context, namespace = active_context(''.join(lines[:start[0] - 1]))
            name = 'rb_formal40_' + str(row['number'])
            declaration = re.sub(r'(\b(?:theorem|lemma)\s+)[\w.]+', r'\g<1>' + name, declaration, count=1)
            reference = 'import Mathlib\n\n' + context + '\n' + declaration.rstrip() + '\n'
            prefix, _ = proof_template(reference)
            initial = prefix + ' by sorry\n'
            version = '4.8.0-rc1'
            target_declaration = namespace + '.' + name if namespace else name
            forbidden = [record['full_name']]
            adaptations = [
                'Retain the source declaration header and active variable/open/namespace commands.',
                'Normalize declaration name and import the pinned Mathlib runtime for syntax compatibility.',
                'Exclude the original library target and transitive proof dependencies on it at kernel verification.',
            ]
        (folder / 'Initial.lean').write_text(initial, encoding='utf-8', newline='\n')
        (folder / 'Reference.lean').write_text(reference, encoding='utf-8', newline='\n')
        write_json(folder / 'recipe.json', {
            'selection': row, 'lean_version': version, 'adaptations': adaptations,
            'target_declaration': target_declaration, 'forbidden_proof_dependencies': forbidden,
        })


def check_recipes(packet_ids=()):
    folders = sorted(RECIPES.glob('*/recipe.json'))
    if packet_ids:
        folders = [p for p in folders if p.parent.name in packet_ids]

    def check(path):
        recipe = read_json(path)
        folder = path.parent
        version = recipe['lean_version']
        result = compile_source(folder / 'Reference.lean', version)
        write_json(folder / 'reference_compile.json', result)
        print(folder.name, 'reference', result['returncode'], flush=True)
        return {'packet_id': folder.name, **result}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(check, folders))
    write_json(CHECKS / 'reference_checks.json', results)
    return results


def batch_reference_check(packet_ids=()):
    paths = sorted(RECIPES.glob('*/recipe.json'))
    if packet_ids:
        paths = [p for p in paths if p.parent.name in packet_ids]
    groups = {}
    for path in paths:
        recipe = read_json(path)
        groups.setdefault(recipe['lean_version'], []).append(path)
    for version, group in groups.items():
        imports = set()
        fragments = []
        for index, path in enumerate(group):
            source = (path.parent / 'Reference.lean').read_text(encoding='utf-8')
            imports.update(re.findall(r'^import .+$', source, re.M))
            source = re.sub(r'^import .+$', '', source, flags=re.M)
            namespaces = re.findall(r'^namespace\s+([\w.]+)', source, re.M)
            fragments.append('section\n' + source + '\n' +
                             '\n'.join('end ' + name for name in reversed(namespaces)) +
                             '\nend\n')
        batch = CHECKS / ('reference_batch_' + version + '.lean')
        batch.write_text('\n'.join(sorted(imports)) + '\n' + '\n'.join(fragments), encoding='utf-8', newline='\n')
        result = compile_source(batch, version)
        write_json(batch.with_suffix('.json'), result)
        print(version, 'batch', len(group), result['returncode'], flush=True)


def validate_kernel_batch(result, paths):
    names = re.findall(r"'([^']+)' (?:depends on axioms:|does not depend on any axioms)", result['stdout'])
    expected = set()
    for path in paths:
        recipe = read_json(path)
        _, name = proof_template((path.parent / 'Reference.lean').read_text(encoding='utf-8'))
        expected.add(recipe.get('target_declaration') or name)
    if set(names) != expected or len(names) != len(paths):
        raise ValueError('Missing theorem kernel results')
    axioms = re.findall(r'depends on axioms:\s*\[([^\]]*)\]', result['stdout'])
    if any(name.strip() not in ('', 'propext', 'Classical.choice', 'Quot.sound')
           for group in axioms for name in group.split(',')):
        raise ValueError('Unexpected axiom in private witness')


def check_initial_candidates():
    rows = []
    previous_path = CHECKS / 'initial_candidate_checks.json'
    previous = ({row['packet_id']: row for row in read_json(previous_path)['packets']}
                if previous_path.exists() else {})
    for path in sorted(RECIPES.glob('*/recipe.json')):
        recipe = read_json(path)
        if recipe['selection']['source'] != 'april':
            continue
        digest = sha256_file(path.parent / 'Initial.lean')
        old = previous.get(path.parent.name)
        result = (old['compilation'] if old and old['initial_sha256'] == digest
                  else compile_source(path.parent / 'Initial.lean', recipe['lean_version']))
        if result['returncode'] == 0 or result.get('failure_origin'):
            raise ValueError(f'Initial candidate is not a reproducible proof failure: {path.parent.name}')
        rows.append({'packet_id': path.parent.name, 'initial_sha256': digest,
                     'compilation': result})
        write_json(CHECKS / 'initial_candidate_checks.json', {'passed': len(rows) == 10, 'packets': rows})
        print('initial fault', path.parent.name, 'confirmed', flush=True)
    if len(rows) != 10:
        raise ValueError('Expected ten repair candidates')


def individual_kernel_gates():
    paths = sorted(RECIPES.glob('*/recipe.json'))

    def check(path):
        recipe = read_json(path)
        folder = CHECKS / 'individual' / path.parent.name
        source = (path.parent / 'Reference.lean').read_text(encoding='utf-8')
        _, name = proof_template(source)
        source += '\n#print axioms ' + name + '\n'
        if recipe.get('forbidden_proof_dependencies'):
            source += dependency_probe(recipe['target_declaration'], recipe['forbidden_proof_dependencies'])
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / 'kernel.lean'
        probe.write_text(source, encoding='utf-8', newline='\n')
        digest = sha256_file(probe)
        old = folder / 'report.json'
        if old.exists():
            report = read_json(old)
            if report.get('passed') and report.get('gate_source_sha256') == digest:
                print('individual', path.parent.name, 'cached PASS', flush=True)
                return report
        result = compile_source(probe, recipe['lean_version'])
        passed = result['returncode'] == 0
        if passed:
            try:
                validate_kernel_batch(result, [path])
            except ValueError as error:
                result['validation_error'] = str(error)
                passed = False
        report = {'packet_id': path.parent.name, 'passed': passed, 'gate_source_sha256': digest,
                  'reference_sha256': sha256_file(path.parent / 'Reference.lean'), 'compilation': result}
        write_json(old, report)
        print('individual', path.parent.name, 'PASS' if passed else 'FAIL', flush=True)
        return report

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(check, paths))
    write_json(CHECKS / 'individual_kernel_report.json', {
        'packets': rows, 'passed': len(rows) == 40 and all(row['passed'] for row in rows),
    })


def gate_batches():
    groups = {}
    for path in sorted(RECIPES.glob('*/recipe.json')):
        recipe = read_json(path)
        groups.setdefault(recipe['lean_version'], []).append(path)
    for version, paths in groups.items():
        for mode in ('context', 'kernel'):
            inputs = {
                path.parent.name: {name: sha256_file(path.parent / name)
                                   for name in ('recipe.json', 'Initial.lean', 'Reference.lean')}
                for path in paths
            }
            previous = CHECKS / f'{mode}_batch_{version}.json'
            if previous.exists():
                old = read_json(previous)
                if old.get('returncode') == 0 and old.get('inputs') == inputs:
                    if mode == 'kernel':
                        validate_kernel_batch(old, paths)
                    print(mode, version, 'existing matching gate PASS', flush=True)
                    continue
            imports = set()
            fragments = []
            for index, path in enumerate(paths):
                recipe = read_json(path)
                source = (path.parent / 'Reference.lean').read_text(encoding='utf-8')
                prefix, name = proof_template(source)
                namespaces = re.findall(r'^namespace\s+([\w.]+)', source, re.M)
                if mode == 'context':
                    packet = path.parent.name
                    source = prefix + f''' by
  run_tac do
    let goal ← Lean.Elab.Tactic.getMainGoal
    Lean.logInfo m!"FORMAL40_GOAL_BEGIN {packet}\\n{{← Lean.Meta.ppGoal goal}}\\nFORMAL40_GOAL_END {packet}"
  sorry
'''
                else:
                    source += '\n#print axioms ' + name + '\n'
                    if recipe.get('forbidden_proof_dependencies'):
                        source += dependency_probe(recipe['target_declaration'], recipe['forbidden_proof_dependencies']).replace(
                            'formal40CheckDependencies', 'formal40CheckDependencies' + str(index))
                imports.update(re.findall(r'^import .+$', source, re.M))
                source = re.sub(r'^import .+$', '', source, flags=re.M)
                fragments.append('section\n' + source + '\n' +
                                 '\n'.join('end ' + name for name in reversed(namespaces)) + '\nend\n')
            batch = CHECKS / f'{mode}_batch_{version}.lean'
            batch.write_text('\n'.join(sorted(imports)) + '\n' + '\n'.join(fragments), encoding='utf-8', newline='\n')
            result = compile_source(batch, version)
            result['inputs'] = inputs
            write_json(batch.with_suffix('.json'), result)
            print(mode, version, len(paths), result['returncode'], flush=True)
            if result['returncode'] != 0:
                continue
            if mode == 'context':
                for path in paths:
                    packet = path.parent.name
                    match = re.search('FORMAL40_GOAL_BEGIN ' + packet + r'\n(.*?)\nFORMAL40_GOAL_END ' + packet,
                                      result['stdout'], re.S)
                    if not match or '⊢' not in match.group(1):
                        raise ValueError(f'Missing actual Lean goal for {packet}')
                    write_json(CHECKS / packet / 'proof_state.json', {
                        'initial_proof_state': match.group(1),
                        'origin': 'Pinned Lean ppGoal before proof construction; candidate diagnostics require compilation.',
                        'source_sha256': sha256_file(path.parent / 'Initial.lean'),
                    })
            else:
                validate_kernel_batch(result, paths)


def build_packets(refresh_draft=False):
    selection = read_json(SELECTION / 'selection.json')
    if OUTPUT.exists() and not refresh_draft:
        raise FileExistsError(f'Packet release already exists: {OUTPUT}')
    recipes = [read_json(RECIPES / row['packet_id'] / 'recipe.json') for row in selection['packets']]
    individual_path = CHECKS / 'individual_kernel_report.json'
    if individual_path.exists():
        individual = read_json(individual_path)
        if not individual['passed']:
            raise ValueError('Individual packet kernel checks have failures')
        for row in individual['packets']:
            if sha256_file(RECIPES / row['packet_id'] / 'Reference.lean') != row['reference_sha256']:
                raise ValueError('Private witness changed after standalone kernel gate')
    else:
        raise ValueError('Run --individual-gates before building the release')
    versions = {recipe['lean_version'] for recipe in recipes}
    for version in versions:
        for mode in ('context', 'kernel'):
            gate = read_json(CHECKS / f'{mode}_batch_{version}.json')
            if gate['returncode'] != 0:
                raise ValueError(f'{mode} gate has not passed for Lean {version}')
            for recipe in recipes:
                if recipe['lean_version'] == version:
                    packet = recipe['selection']['packet_id']
                    for name, digest in gate['inputs'][packet].items():
                        if sha256_file(RECIPES / packet / name) != digest:
                            raise ValueError(f'Preparation input changed after gate: {packet}/{name}')
    source_root = PROJECT / 'data/RoutingBench/formal40_candidate_sources_20261118'
    licenses = {
        'minif2f': (PROJECT / 'data/RoutingBench/minif2f_sources_20261101/LICENSE.miniF2F').read_bytes(),
        'leandojo': (source_root / 'LICENSE.mathlib').read_bytes(),
        'april': (source_root / 'LICENSE.mathlib').read_bytes(),
    }
    with ZipFile(source_root / 'putnam.zip') as archive:
        licenses['putnam'] = archive.read('PutnamBench-main/lean4/LICENSE')
    index = []
    OUTPUT.mkdir(parents=True, exist_ok=refresh_draft)
    for recipe in recipes:
        row = recipe['selection']
        packet = row['packet_id']
        folder = RECIPES / packet
        initial = (folder / 'Initial.lean').read_text(encoding='utf-8')
        reference = (folder / 'Reference.lean').read_text(encoding='utf-8')
        prefix, name = proof_template(initial)
        if proof_template(reference)[0] != prefix:
            raise ValueError(f'Initial and reference statements differ: {packet}')
        version = recipe['lean_version']
        profile = runtime(version)
        revision = subprocess.run(['git', '-C', profile['project_dir'], 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True, check=True).stdout.strip()
        task = ('Repair the supplied Lean proof and verify the theorem in its original context.'
                if row['source'] == 'april' else
                'Complete the supplied Lean proof and verify the theorem in its original context.')
        task += ' Preserve the assumptions and conclusion. The final proof must use only the allowed axioms.'
        contract = {
            'adapter_id': 'formal_proof.lean4.v2', 'contract_version': 'formal.packet.v2',
            'language': 'Lean 4', 'toolchain': f'Lean {version} with Mathlib4 {revision}',
            'public_source': 'public/Main.lean', 'initial_candidate': row['source'] == 'april',
            'editable': 'proof term only', 'context_and_statement': 'immutable',
            'allowed_validation_command': 'pinned lean public/Main.lean',
            'network_during_execution': False, 'timeout_seconds': 180,
            'candidate_acceptance': 'Context and statement preservation. Lean correctness requires compilation.',
            'terminal_condition': 'Fresh successful compilation and kernel/assumption verification, followed by router STOP.',
            'allowed_axioms': ['propext', 'Classical.choice', 'Quot.sound'],
            'forbidden_placeholders': ['sorry', 'admit'], 'router_raw_source': False,
            'forbidden_runtime_operations': ['run_tac', 'run_elab', 'run_cmd', 'unsafe', 'IO', 'System'],
            'executor_visible_files': ['public/task.md', 'public/Main.lean', 'public/proof_state.json'],
            'evaluator_oracle_visibility': 'private',
            'target_declaration': recipe.get('target_declaration') or name,
            'forbidden_proof_dependencies': recipe.get('forbidden_proof_dependencies', []),
            'library_reproving_policy': 'The original library target and proofs depending on it are excluded. Kernel verification checks transitive proof dependencies.',
        }
        provenance = {
            key: row[key] for key in ('source', 'source_id', 'source_locator', 'source_revision',
                                      'source_record_sha256', 'topic', 'static_difficulty', 'task_type')
        }
        provenance.update(adaptations=recipe['adaptations'], selected_before_live_trajectory=True,
                          reference_origin=recipe.get('reference_origin', 'Pinned upstream proof'),
                          runtime_mathlib_revision=revision,
                          difficulty_status='project_authored_pending_human_review')
        if row['source'] == 'minif2f':
            provenance['reference_origin'] = 'Project-authored witness reused from the pinned miniF2F preparation bank v4_minif2f_20_20261101'
        repositories = {
            'minif2f': 'https://github.com/Goedel-LM/Goedel-Prover-V2',
            'leandojo': 'https://zenodo.org/records/8242200',
            'april': 'https://huggingface.co/datasets/uw-math-ai/APRIL',
            'putnam': 'https://github.com/trishullab/PutnamBench',
        }
        provenance['dataset_repository'] = repositories[row['source']]
        provenance['source_split'] = ('novel_premises/test' if row['source'] == 'leandojo'
                                      else 'unsplit' if row['source'] == 'putnam' else 'test')
        if row['source'] == 'leandojo':
            upstream = read_json(SELECTION / row['private_record_path'])
            provenance['source_repository'] = upstream['url']
            provenance['upstream_file_sha256'] = sha256_file(source_root / 'mathlib_original' / upstream['file_path'])
        else:
            provenance['source_repository'] = repositories[row['source']]
        writer = _Writer(OUTPUT / 'packs/formal_proof' / packet)
        writer.add('public/Main.lean', initial, 'public')
        writer.add('public/task.md', task + '\n', 'public')
        writer.add('public/execution_contract.json', _json_bytes(contract), 'public')
        writer.add('public/proof_state.json', (CHECKS / packet / 'proof_state.json').read_bytes(), 'public')
        writer.add('private/Reference.lean', reference, 'private')
        writer.add('private/upstream_record.json', (SELECTION / row['private_record_path']).read_bytes(), 'private')
        if row['source'] == 'leandojo':
            upstream = read_json(SELECTION / row['private_record_path'])
            writer.add('private/Upstream.lean',
                       (source_root / 'mathlib_original' / upstream['file_path']).read_bytes(), 'private')
        writer.add('private/preparation_recipe.json', _json_bytes(recipe), 'private')
        writer.add('private/runtime_gate.json', _json_bytes({
            'context_compiles': True, 'reference_compiles': True, 'allowed_axioms_verified': True,
            'proof_dependency_gate': bool(contract['forbidden_proof_dependencies']),
            'validation_mode': 'Standalone per-packet kernel check plus scoped batch goal/kernel probes',
            'reference_exposed_to_agents': False,
        }), 'private')
        writer.add('fixtures/upstream_provenance.json', _json_bytes(provenance), 'fixture')
        writer.add('fixtures/LICENSE', licenses[row['source']], 'fixture')
        manifest = writer.manifest(
            packet_id=packet, domain='formal_proof', task=task, adapter_id=contract['adapter_id'],
            source_type=row['source'], license_name='MIT' if row['source'] == 'minif2f' else 'Apache-2.0',
            execution_readiness='runtime_verified', metadata=provenance)
        manifest = replace(manifest, generator_version='routingbench-formal40-v1')
        write_json(writer.pack_dir / 'manifest.json', manifest.to_dict())
        validation = validate_artifact_pack(writer.pack_dir)
        if not validation['valid']:
            raise ValueError(validation)
        index.append({'packet_id': packet, 'source': row['source'], 'source_id': row['source_id'],
                      'task_type': row['task_type'], 'manifest_sha256': sha256_file(writer.pack_dir / 'manifest.json')})
    write_json(OUTPUT / 'packet_index.json', {'version': 'routingbench-formal40-v1', 'packets': index})
    write_json(OUTPUT / 'agent_pools/formal_proof.json', role_cards_for('formal_proof'))
    write_json(OUTPUT / 'selection.json', {
        **selection, 'status': 'runtime_verified_pending_pythagoras_pilot',
        'candidate_selection_sha256': sha256_file(SELECTION / 'selection.json'),
    })
    write_json(OUTPUT / 'preparation_report.json', {
        'packets': len(index), 'context_pass': len(index), 'private_witness_kernel_pass': len(index),
        'manifest_valid': len(index), 'preflight': 'pending', 'human_review_status': 'pending',
        'pythagoras_pilot': 'pending', 'hosted_model_calls': 0,
    })
    write_json(OUTPUT / 'runtime_lock.json', {
        version: {**runtime(version), 'lean_binary_sha256': sha256_file(runtime(version)['lean_executable']),
                  'mathlib_toolchain_sha256': sha256_file(Path(runtime(version)['project_dir']) / 'lean-toolchain'),
                  'lake_manifest_sha256': sha256_file(Path(runtime(version)['project_dir']) / 'lake-manifest.json')}
        for version in versions
    })
    write_json(OUTPUT / 'source_lock.json', {
        'selection_sha256': sha256_file(SELECTION / 'selection.json'),
        'sources': selection['sources'],
        'preparation_inputs': {
            row['packet_id']: {name: sha256_file(RECIPES / row['packet_id'] / name)
                               for name in ('recipe.json', 'Initial.lean', 'Reference.lean')}
            for row in selection['packets']
        },
    })
    print('Built', len(index), 'packets at', OUTPUT, flush=True)


def main():
    global CHECKS, OUTPUT, RECIPES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--batch', action='store_true')
    parser.add_argument('--gates', action='store_true')
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--refresh-draft', action='store_true')
    parser.add_argument('--check-initials', action='store_true')
    parser.add_argument('--individual-gates', action='store_true')
    parser.add_argument('--checks', type=Path, default=CHECKS)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--recipes', type=Path, default=RECIPES)
    parser.add_argument('--packet', action='append', default=[])
    args = parser.parse_args()
    CHECKS, OUTPUT, RECIPES = args.checks, args.output, args.recipes
    initial_recipes()
    if args.check:
        check_recipes(args.packet)
    if args.batch:
        batch_reference_check(args.packet)
    if args.gates:
        gate_batches()
    if args.check_initials:
        check_initial_candidates()
    if args.individual_gates:
        individual_kernel_gates()
    if args.build:
        build_packets(args.refresh_draft)


if __name__ == '__main__':
    main()
