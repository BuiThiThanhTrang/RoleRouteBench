"""Formal packets with upstream repair candidates and library reproving checks."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .common import read_json
from .formal_proof import FormalProofAdapter, constrained_source, proof_template, uncomment
from ..base import ToolResult
from ...artifacts.schema import sha256_file


def dependency_probe(target, forbidden):
    names = ', '.join('`' + name for name in forbidden)
    return f'''
open Lean in
partial def formal40CheckDependencies (pending : List Name) (seen : NameSet) : CoreM Unit := do
  match pending with
  | [] => pure ()
  | name :: rest =>
    if seen.contains name then
      formal40CheckDependencies rest seen
    else
      if ([{names}] : List Name).contains name then
        throwError "Forbidden reference to benchmark target: {{name}}"
      let info ← getConstInfo name
      let deps := match info.value? with
        | some value => value.getUsedConstants.toList
        | none => []
      formal40CheckDependencies (deps ++ rest) (seen.insert name)

run_elab do
  formal40CheckDependencies [`{target}] {{}}
  Lean.logInfo "FORMAL40_DEPENDENCIES_OK"
'''


class FormalProofV2Adapter(FormalProofAdapter):
    adapter_id = 'formal_proof.lean4.v2'

    @property
    def supports_executor_errors(self):
        return self.runtime.get('formal_context_policy') in ('bounded_artifact_handoff_v1', 'bounded_artifact_handoff_v2')

    @property
    def uses_presentation_identity(self):
        return self.runtime.get('formal_candidate_identity') == 'lean_tokens_layout_v1'

    def configure_runtime(self, profile):
        super().configure_runtime(profile)
        if self.runtime.get('formal_candidate_identity') not in (None, 'lean_tokens_layout_v1'):
            raise ValueError('Unknown formal candidate identity policy')
        if self.uses_presentation_identity and self.runtime.get('formal_context_policy') != 'bounded_artifact_handoff_v2':
            raise ValueError('Presentation identity requires handoff v2')

    def record_role_result(self, env, role, before, result):
        """Public measured outcomes only; no prescribed next action or extra call."""
        if self.runtime.get('formal_context_policy') != 'bounded_artifact_handoff_v2':
            return
        state = self._state(env)
        versions = self.versions(env)
        old = before.get('artifacts', {})
        created = [key for key, item in state['artifacts'].items()
                   if item.get('artifact_id') != old.get(key, {}).get('artifact_id')]
        submitted = any(e['tool_call']['name'] == 'write_source' and e['tool_result']['status'] == 'success'
                        for e in result.get('tool_events', []))
        metadata = (result.get('responses') or [{}])[-1].get('metadata', {})
        partial = metadata.get('diagnosis_artifact', {}).get('status') == 'partial'
        row = {'role': role, 'status': result['status'], 'artifact_created': bool(created),
               'created_artifacts': created, 'source_hash_before': before['source_hash'],
               'source_hash_after': versions['source_hash'],
               'candidate_changed': versions['source_hash'] != before['source_hash'],
               'duplicate_candidate': submitted and versions['source_hash'] == before['source_hash'],
               'generation_failure': result.get('contract_error', {}).get('code') or
                                     metadata.get('diagnosis_artifact', {}).get('generation_failure'),
               'partial_diagnosis': partial}
        if self.uses_presentation_identity:
            from ..formal_identity import source_identity
            identity = source_identity((env.workspace_dir / 'public/Main.lean').read_bytes().decode('utf-8'))
            changed = identity['fingerprint'] != before['source_identity']['fingerprint']
            row.update(source_changed=row['candidate_changed'], candidate_changed=changed,
                       duplicate_candidate=bool(submitted and before.get('candidate_hash') and not changed),
                       candidate_identity_policy=identity['policy'],
                       candidate_fingerprint_before=before['source_identity']['fingerprint'],
                       candidate_fingerprint_after=identity['fingerprint'])
        state.setdefault('role_results', []).append(row)
        self._save_state(env, state)

    def record_contract_error(self, env, error):
        if not self.supports_executor_errors:
            return
        state = self._state(env)
        state['events'].append({'tool_name': 'executor_generation', 'status': 'invalid_output',
                                'output': {'error': error.get('message'), 'code': error.get('code'),
                                           **({k: error.get(k) for k in ('role', 'generation_details', 'observed_completion_tokens')}
                                              if self.runtime.get('formal_context_policy') == 'bounded_artifact_handoff_v2' else {})},
                                'input_versions': self.versions(env), 'origin': 'selected_agent'})
        self._save_state(env, state)

    def executor_context(self, env, action, role_profile=None):
        context = super().executor_context(env, action, role_profile)
        if self.supports_executor_errors:
            from ..formal_handoff import attach_handoff
            context['context_policy'] = self.runtime['formal_context_policy']
            if self.runtime['formal_context_policy'] == 'bounded_artifact_handoff_v2':
                for artifact in context['state']['artifacts'].values():
                    artifact.pop('critical', None)  # Delivered once in handoff_evidence.
            return attach_handoff(env, context)
        return context

    def progress_observation(self, observation):
        if self.runtime.get('formal_context_policy') != 'bounded_artifact_handoff_v2':
            return observation
        if self.uses_presentation_identity:
            fingerprint = observation['source_identity']['fingerprint']
            candidate = observation.get('artifacts', {}).get('candidate')
            candidate_fingerprint = candidate['presentation_identity']['fingerprint'] if candidate else None
            return {'source_identity': fingerprint,
                    'candidate_identity': candidate_fingerprint,
                    'terminal': observation.get('terminal'),
                    'artifacts': {key: (candidate_fingerprint if key == 'candidate' else item['sha256'])
                                  for key, item in observation.get('artifacts', {}).items()}}
        # Counters and new artifact IDs alone must not masquerade as progress.
        return {key: observation.get(key) for key in ('source_hash', 'candidate_hash', 'terminal')} | {
            'artifacts': {key: {'sha256': item['sha256'], 'fresh': item['fresh']}
                          for key, item in observation.get('artifacts', {}).items()}}

    def public_observation(self, env):
        observation = super().public_observation(env)
        if self.uses_presentation_identity:
            from ..formal_identity import source_identity
            observation['source_identity'] = source_identity(
                (env.workspace_dir / 'public/Main.lean').read_bytes().decode('utf-8'))
            candidate = observation['artifacts'].get('candidate')
            if candidate:
                candidate['presentation_identity'] = (observation['source_identity']
                    if candidate['sha256'] == observation['source_hash'] else source_identity(
                        (env.workspace_dir / candidate['path']).read_bytes().decode('utf-8')))
        if self.supports_executor_errors:
            events = self._state(env)['events']
            if events and events[-1]['output'].get('code') and observation.get('latest_tool_feedback'):
                observation['latest_tool_feedback']['code'] = events[-1]['output']['code']
        if self.runtime.get('formal_inspection_policy') == 'tactic_state_v1':
            inspection = observation['artifacts'].get('inspection')
            if inspection:
                # This contains goals/types/positions, never the raw proof body.
                inspection['content'] = (env.workspace_dir / inspection['path']).read_text(encoding='utf-8')
        if self.runtime.get('formal_context_policy') == 'bounded_artifact_handoff_v2':
            from ..formal_handoff import project_tool_evidence
            failed = next((event for event in reversed(self._state(env)['events'])
                           if event['tool_name'] == 'executor_generation'), None)
            if failed:
                observation['latest_generation_failure'] = {
                    **failed['output'], 'input_versions': failed['input_versions'],
                    'fresh': failed['input_versions'] == self.versions(env),
                    'interpretation': 'Generation failure; any repeated-text sample is unverified model output.'}
            for key in ('compilation', 'verification', 'premises', 'inspection'):
                artifact = observation['artifacts'].get(key)
                if artifact and artifact.get('content'):
                    try:
                        artifact['critical'] = project_tool_evidence(key, json.loads(artifact['content']))[0]
                    except json.JSONDecodeError:
                        pass
            rows = self._state(env).get('role_results', [])
            summaries = {}
            for role in dict.fromkeys(row['role'] for row in rows):
                selected = [row for row in rows if row['role'] == role]
                consecutive = 0
                for row in reversed(selected):
                    if not row['generation_failure']:
                        break
                    consecutive += 1
                summaries[role] = {'calls': len(selected), 'consecutive_generation_failures_for_role': consecutive,
                                   'duplicate_candidates': sum(row['duplicate_candidate'] for row in selected)}
                if self.uses_presentation_identity:
                    summaries[role]['consecutive_duplicate_candidates_for_role'] = next(
                        (i for i, row in enumerate(reversed(selected)) if not row['duplicate_candidate']), len(selected))
            observation['role_progress'] = {'last_result': rows[-1] if rows else None, 'by_role': summaries}
        return observation

    def _store(self, env, state, key, text, inputs, tool):
        super()._store(env, state, key, text, inputs, tool)
        if key == 'candidate':
            # A standalone Lean source depends on its immutable context. New
            # diagnostic or rejected-output artifacts do not invalidate it.
            state['artifacts'][key]['input_refs'] = []

    def materialize(self, manifest_path, workspace):
        env = super().materialize(manifest_path, workspace)
        if env.manifest.adapter_id != self.adapter_id:
            raise ValueError('Wrong adapter for formal v2 packet')
        contract = read_json(env.workspace_dir / 'public/execution_contract.json')
        if contract.get('initial_candidate'):
            state = self._state(env)
            source = (env.workspace_dir / 'public/Main.lean').read_text(encoding='utf-8')
            self._store(env, state, 'candidate', source, {}, 'materialize_initial_candidate')
            candidate = state['artifacts']['candidate']
            # Preserve the exact upstream input bytes on Windows as well.
            artifact_path = env.workspace_dir / candidate['path']
            artifact_path.write_bytes((env.workspace_dir / 'public/Main.lean').read_bytes())
            candidate['sha256'] = sha256_file(artifact_path)
            state['events'].append({
                'tool_name': 'materialize_initial_candidate', 'status': 'success',
                'output': {'artifact': candidate}, 'origin': 'environment',
                'input_versions': {'source_hash': candidate['sha256'], 'candidate_hash': candidate['sha256']},
            })
            self._save_state(env, state)
        return env

    def _compile(self, path):
        path = Path(path)
        if path.name == 'assumptions.lean':
            contract = read_json(path.parent.parent / 'public/execution_contract.json')
            forbidden = contract.get('forbidden_proof_dependencies', [])
            if forbidden:
                content = path.read_text(encoding='utf-8')
                path.write_text(content + dependency_probe(contract['target_declaration'], forbidden),
                                encoding='utf-8', newline='\n')
        return super()._compile(path)

    def _reject(self, env, tool_name, output):
        state = self._state(env)
        state['events'].append({
            'tool_name': tool_name, 'status': 'invalid_output', 'output': output,
            'input_versions': self.versions(env), 'origin': 'selected_agent',
        })
        self._save_state(env, state)
        return ToolResult(tool_name, 'invalid_output', output, json.dumps(output))

    def execute_tool(self, env, tool_name, arguments=None):
        if tool_name == 'inspect_proof' and self.runtime.get('formal_inspection_policy') == 'tactic_state_v1':
            from ..formal_inspection import inspect_candidate
            report, trace = inspect_candidate(env, self.runtime)
            state = self._state(env)
            inputs = self.versions(env)
            if trace is not None:
                self._store(env, state, 'inspection_trace', trace, inputs, tool_name)
            self._store(env, state, 'inspection', report, inputs, tool_name)
            status = 'success' if report['status'] != 'unavailable' else 'failed'
            output = {**report, 'artifact': state['artifacts']['inspection']}
            state['events'].append({'tool_name': tool_name, 'status': status, 'output': output,
                                    'input_versions': inputs, 'origin': 'selected_agent'})
            self._save_state(env, state)
            return ToolResult(tool_name, status, output, json.dumps(output, ensure_ascii=False))
        if tool_name == 'write_source':
            original = (env.pack_dir / 'public/Main.lean').read_text(encoding='utf-8')
            content = str((arguments or {}).get('content') or '')
            blocks = re.findall(r'```(?:lean4?)?\s*\n(.*?)```', content, re.S)
            content = blocks[-1] if blocks else content
            try:
                canonical = constrained_source(original, content)
            except ValueError:
                canonical = None
            if canonical is not None:
                prefix, _ = proof_template(original)
                body = uncomment(canonical[len(prefix):])
                if re.search(r'\b(?:run_tac|run_elab|run_cmd|unsafe|IO|System)\b', body):
                    return self._reject(env, tool_name, {
                        'error': 'Proof submissions may use mathematical tactics and terms. Runtime metaprogramming and host IO are excluded.',
                    })
        if tool_name == 'write_premises':
            contract = read_json(env.workspace_dir / 'public/execution_contract.json')
            forbidden = set(contract.get('forbidden_proof_dependencies', []))
            symbols = (arguments or {}).get('symbols', [])
            if forbidden.intersection(symbol.removeprefix('_root_.') for symbol in symbols):
                return self._reject(env, tool_name, {
                    'error': 'The original library target is excluded from premise lookup.',
                })
        return super().execute_tool(env, tool_name, arguments)
