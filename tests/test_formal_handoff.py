"""Functional handoff/streaming regressions, plus opt-in real Lean observations."""
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import yaml

from routing_benchmark.v4.execution.adapters.formal_proof_v2 import FormalProofV2Adapter
from routing_benchmark.v4.execution.formal_actor import FormalRoleActor, END, repetition, load_tokenizer, TokenizerSetupError
from routing_benchmark.v4.execution.formal_handoff import compact_prose
from routing_benchmark.v4.execution.runtime import resolve_runtime
from routing_benchmark.v4.execution.shared_evaluation import episode_metrics

PROJECT = Path(__file__).resolve().parents[1]
BANK = PROJECT / 'data/RoutingBench/formal40_pythagoras_v1_20261118'
CONFIG = yaml.safe_load((PROJECT / 'config/shared_environment/formal40_inspector_lean48_jev.yaml').read_text(encoding='utf-8'))
PACK = BANK / 'packs/formal_proof/formal40-09-leandojo/manifest.json'


class FakeStream:
    def __init__(self, text, finish='stop', failure=False):
        self.text, self.finish, self.failure = text, finish, failure
        self.closed, self.delivered = False, 0

    def __iter__(self):
        for offset in range(0, len(self.text), 37):
            self.delivered += 37
            yield SimpleNamespace(model='fake', id='stream-1', usage=None,
                choices=[SimpleNamespace(finish_reason=None, delta=SimpleNamespace(content=self.text[offset:offset+37]))])
        if self.failure:
            raise ConnectionError('interrupted')
        yield SimpleNamespace(model='fake', id='stream-1', usage=None,
            choices=[SimpleNamespace(finish_reason=self.finish, delta=SimpleNamespace(content=None))])

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, stream):
        self.stream, self.requests = stream, []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.stream


class TokenizerSetupTests(unittest.TestCase):
    def test_old_decoder_error_reports_the_active_python_and_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tokenizer.json'
            path.write_bytes(b'{}')
            digest = hashlib.sha256(b'{}').hexdigest()
            def reject(_):
                raise Exception('data did not match any variant of untagged enum ModelWrapper')
            old = SimpleNamespace(__version__='0.19.1', Tokenizer=SimpleNamespace(from_file=reject))
            with patch.dict(sys.modules, {'tokenizers': old}):
                with self.assertRaises(TokenizerSetupError) as caught:
                    load_tokenizer.__wrapped__(str(path), digest)
            message = str(caught.exception)
            self.assertIn(sys.executable, message)
            self.assertIn('0.19.1', message)
            self.assertIn('tokenizers==0.22.2', message)
            self.assertIn('--check-only', message)

    def test_missing_cache_has_a_preparation_command(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(TokenizerSetupError) as caught:
                load_tokenizer.__wrapped__(str(Path(folder) / 'missing.json'), 'unused')
            self.assertIn('prepare_formal_executor_resources.py', str(caught.exception))


class FormalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.adapter = FormalProofV2Adapter()
        self.adapter.configure_runtime({'formal_context_policy': 'bounded_artifact_handoff_v1'})
        self.env = self.adapter.materialize(PACK, Path(self.tmp.name) / 'workspace')

    def tearDown(self):
        self.tmp.cleanup()

    def actor(self, text, **kwargs):
        stream = FakeStream(text, **kwargs)
        client = FakeClient(stream)
        actor = FormalRoleActor(client, 'fake', formal_protocol=CONFIG['executor']['formal_protocol'])
        return actor, client, stream

    def execute(self, actor, role='Proof Repair Specialist'):
        return actor.execute(env=self.env, adapter=self.adapter, action=role, role_profile={'agent_id': role}, task='Prove the theorem')

    def evidence(self):
        self.adapter.execute_tool(self.env, 'write_source', {'content': 'by\n  rfl'})
        with patch.object(self.adapter, '_compile', return_value={'returncode': 1, 'stdout': 'unknown constant missingLemma', 'stderr': ''}):
            self.adapter.execute_tool(self.env, 'compile_proof')
            self.adapter.execute_tool(self.env, 'write_premises', {'symbols': ['Nat.add_comm']})
        self.adapter.execute_tool(self.env, 'write_diagnosis', {'content': 'Observed failure: missingLemma. Location: line 6. Repair constraints: preserve x m n.'})

    def test_diagnosis_premises_and_failure_are_delivered_without_read(self):
        self.evidence()
        actor, client, _ = self.actor('by\n  rfl\n' + END)
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(client.requests), 1)
        prompt = client.requests[0]['messages'][1]['content']
        self.assertIn('Observed failure: missingLemma', prompt)
        self.assertIn('Nat.add_comm', prompt)
        self.assertIn('unknown constant missingLemma', prompt)
        self.assertNotIn('Reference.lean', prompt)
        self.assertEqual(client.requests[0]['max_tokens'], 4096)
        self.assertTrue(client.requests[0]['stream'])
        supplied = result['requests'][0]['delivered_evidence']
        self.assertEqual({item['key'] for item in supplied}, {'compilation', 'premises', 'diagnosis'})
        self.assertNotIn(END, (self.env.workspace_dir / 'public/Main.lean').read_text(encoding='utf-8'))
        self.assertIn(END, result['responses'][0]['raw_output'])

    def test_same_handoff_for_all_seven_roles_and_stale_marking(self):
        self.evidence()
        roles = json.loads((BANK / 'agent_pools/formal_proof.json').read_text(encoding='utf-8'))
        contexts = [self.adapter.executor_context(self.env, role['agent_id']) for role in roles]
        self.assertTrue(all(c == contexts[0] for c in contexts))
        self.adapter.execute_tool(self.env, 'write_source', {'content': 'by\n  exact rfl'})
        items = self.adapter.executor_context(self.env, 'Proof Repair Specialist')['handoff_evidence']
        self.assertTrue(all(not item['fresh'] for item in items))
        self.assertTrue(all(item['interpretation'].startswith('historical') for item in items))

    def test_dedup_keeps_code_and_original_reader_bytes(self):
        paragraph = 'Observed failure: ' + ('the exact compiler message matters. ' * 4)
        code = '```lean4\nby\n  simp\n  simp\n```'
        text = '\n\n'.join([paragraph, paragraph, code, code])
        compact, _ = compact_prose(text)
        self.assertEqual(compact.count(paragraph), 1)
        self.assertEqual(compact.count(code), 2)
        self.adapter.execute_tool(self.env, 'write_diagnosis', {'content': text})
        before = copy.deepcopy(self.adapter._state(self.env)['artifacts']['diagnosis'])
        context = self.adapter.executor_context(self.env, 'Proof Repair Specialist')
        self.assertEqual(context['handoff_evidence'][0]['content'].count(paragraph), 1)
        read = self.adapter.execute_tool(self.env, 'read_artifact', {'artifact': 'diagnosis'})
        self.assertEqual(read.output['content'], text)
        self.assertEqual(before, self.adapter._state(self.env)['artifacts']['diagnosis'])
        open_code = '```lean4\n' + paragraph + '\n\n' + paragraph
        self.assertEqual(compact_prose(open_code)[0], open_code)

    def test_stream_loop_aborts_without_replacing_candidate(self):
        self.evidence()
        before = self.adapter.versions(self.env)
        paragraph = 'But perhaps the required theorem is correct and the interpretation must be reconsidered. '
        text = (paragraph + '\n\n') * 200
        actor, _, stream = self.actor(text)
        result = self.execute(actor)
        self.assertEqual(result['contract_error']['code'], 'repetition_detected')
        self.assertEqual(before, self.adapter.versions(self.env))
        self.assertTrue(stream.closed)
        self.assertLess(stream.delivered, len(text))
        self.assertFalse(result['tool_events'])

    def test_truncation_never_submits_partial_proof(self):
        actor, _, stream = self.actor('by\n  have unfinished : True := by', finish='length')
        before = self.adapter.versions(self.env)
        result = self.execute(actor)
        self.assertEqual(result['contract_error']['code'], 'output_truncated')
        self.assertEqual(before, self.adapter.versions(self.env))
        self.assertTrue(stream.closed)

    def test_stream_interruption_is_infrastructure_and_is_not_retried(self):
        actor, client, stream = self.actor('by\n  rfl', failure=True)
        stream.response = SimpleNamespace(headers={'x-request-id': 'interrupted-stream-123'})
        result = self.execute(actor)
        self.assertEqual(result['status'], 'transport_error')
        self.assertEqual(result['failure_origin'], 'executor_service')
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result['responses'][0]['metadata']['generation_details']['request_id'], 'interrupted-stream-123')
        self.assertNotIn('request_id', result['contract_error'].get('generation_details') or {})
        self.assertFalse(result['tool_events'])
        self.assertTrue(stream.closed)

    def test_v2_stream_diagnostics_do_not_expand_public_feedback(self):
        self.adapter.configure_runtime({'formal_context_policy': 'bounded_artifact_handoff_v2'})
        actor, _, stream = self.actor('by\n  rfl', failure=True)
        actor.policy = actor.protocol['version'] = 'artifact_first_v2'
        stream.response = SimpleNamespace(headers={'x-request-id': 'audit-only-stream-123'})
        result = self.execute(actor)
        self.assertEqual(result['responses'][0]['metadata']['generation_details']['request_id'], 'audit-only-stream-123')
        details = result['contract_error']['generation_details']
        self.assertEqual(set(details), {'error_type', 'http_status'})

    def test_diagnosis_role_uses_1024_and_missing_usage_is_explicit(self):
        actor, client, _ = self.actor('Observed failure: an unknown name.\nLocation: line 2.\nSuspected cause: typo.\nRepair constraints: preserve statement.\nUncertainty: unresolved.\n' + END)
        result = self.execute(actor, 'Formal Failure Diagnostician')
        self.assertEqual(client.requests[0]['max_tokens'], 1024)
        self.assertIsNone(result['responses'][0]['metadata']['usage'])
        metrics = episode_metrics([], [{'kind': 'role_execution', 'agent_id': 'Formal Failure Diagnostician', 'status': 'success', 'result': result}])
        self.assertFalse(metrics['provider_token_usage_complete'])
        self.assertEqual(metrics['responses_without_provider_usage'], 1)

    def test_natural_completion_preserves_existing_last_block_codec(self):
        actor, _, _ = self.actor('Analysis first.\n```lean4\nby sorry\n```\n```lean4\nby rfl\n```')
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        normalization = result['responses'][0]['metadata']['output_normalization']
        self.assertEqual(normalization['selected_lean_block'], 1)
        self.assertNotIn('sorry', (self.env.workspace_dir / 'public/Main.lean').read_text(encoding='utf-8'))

    def test_no_complete_artifact_does_not_select_an_earlier_draft(self):
        for text in ['Analysis only, with no proof.', '```lean4\nby sorry\n```\n```lean4\nby rfl']:
            actor, _, _ = self.actor(text)
            result = self.execute(actor)
            self.assertEqual(result['contract_error']['code'], 'artifact_format')
            self.assertFalse(result['tool_events'])

    def test_input_budget_bounds_long_evidence_and_preserves_status(self):
        self.evidence()
        long = '\n\n'.join(f'Observation number {i}: ' + ('new fact ' * 30) for i in range(150))
        self.adapter.execute_tool(self.env, 'write_diagnosis', {'content': long})
        actor, _, _ = self.actor('by\n  rfl\n' + END)
        actor.protocol['input_max_tokens'] = 6000
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        context = result['requests'][0]['executor_payload']['public_context']
        self.assertLessEqual(context['input_budget']['estimated_tokens_with_chat_reserve'], 6000)
        self.assertTrue(any(item['truncated'] for item in context['handoff_evidence']))
        compilation = next(item for item in context['handoff_evidence'] if item['key'] == 'compilation')
        self.assertEqual(compilation['critical']['returncode'], 1)

    def test_impossible_input_budget_is_environment_failure_without_model_call(self):
        actor, client, _ = self.actor('by rfl')
        actor.protocol['input_max_tokens'] = 128
        before = self.adapter.versions(self.env)
        result = self.execute(actor)
        self.assertEqual(result['failure_origin'], 'tool_environment')
        self.assertEqual(result['contract_error']['code'], 'context_budget_exceeded')
        self.assertFalse(client.requests)
        self.assertEqual(before, self.adapter.versions(self.env))

    def test_normal_repeated_tactics_are_not_flagged(self):
        self.assertIsNone(repetition('by\n' + '  simp\n' * 30))
        nested = 'by\n' + '\n'.join(' ' * i + 'exact le_of_lt (by' for i in range(2, 40, 2))
        self.assertEqual(repetition(nested)['kind'], 'recursive_open_tactic')

    def test_end_marker_inside_a_lean_string_does_not_cut_the_proof(self):
        proof = 'by\n  have h := "<END_ARTIFACT>"\n  rfl'
        actor, _, _ = self.actor(proof + '\n' + END)
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['responses'][0]['metadata']['artifact_end_offset'], len(proof) + 1)
        self.assertIn(proof, (self.env.workspace_dir / 'public/Main.lean').read_text(encoding='utf-8'))

    def test_handoff_only_profile_supports_legacy_inspection(self):
        self.adapter.execute_tool(self.env, 'inspect_proof')
        context = self.adapter.executor_context(self.env, 'Proof Repair Specialist')
        item = next(item for item in context['handoff_evidence'] if item['key'] == 'inspection')
        self.assertEqual(item['critical']['status'], 'legacy_source_snapshot')
        self.assertFalse(item['critical']['certifies_proof'])

    def test_generation_error_reaches_next_router_observation_without_masking(self):
        from routing_benchmark.routers import RoutingDecision
        from routing_benchmark.v4.execution.shared_runner import SharedTrajectoryRunner
        paragraph = 'But perhaps the required theorem is correct and the interpretation must be reconsidered. '
        actor, _, _ = self.actor((paragraph + '\n\n') * 30)
        class Sequence:
            def reset(self, seed):
                self.actions = iter(['Tactic Synthesizer', 'STOP'])
            def select(self, observation, candidates):
                self.last_observation = observation
                self.candidates = candidates
                return RoutingDecision(next(self.actions))
        router = Sequence()
        roles = json.loads((BANK / 'agent_pools/formal_proof.json').read_text(encoding='utf-8'))
        result = SharedTrajectoryRunner(router=router, actor=actor, max_calls=12).run(
            manifest_path=PACK, adapter=self.adapter, workspace=Path(self.tmp.name) / 'runner/workspace',
            output_dir=Path(self.tmp.name) / 'runner', roles=roles)
        self.assertEqual(result['executor_calls'], 1)
        self.assertFalse(result['terminal_contract_passed'])
        self.assertEqual(router.last_observation['current_state']['latest_tool_feedback']['code'], 'repetition_detected')
        self.assertEqual(len(router.candidates), 8)


class FormalRecoveryTests(unittest.TestCase):
    setUp = FormalHandoffTests.setUp
    tearDown = FormalHandoffTests.tearDown
    execute = FormalHandoffTests.execute
    evidence = FormalHandoffTests.evidence

    def actor(self, text, **kwargs):
        self.adapter.configure_runtime({'formal_context_policy': 'bounded_artifact_handoff_v2'})
        config = yaml.safe_load((PROJECT / 'config/shared_environment/formal40_recovery_v2_lean48_jev.yaml').read_text(encoding='utf-8'))
        stream = FakeStream(text, **kwargs)
        client = FakeClient(stream)
        actor = FormalRoleActor(client, 'fake', formal_protocol=config['executor']['formal_protocol'])
        return actor, client, stream

    def test_sampling_and_thinking_match_actual_audited_requests(self):
        text = ('Observed error: unknown constant missingLemma\nLocation: line 6\n'
                'Likely cause: unavailable name\nRepair constraint: preserve statement\nUncertainty: unknown\n' + END)
        actor, client, _ = self.actor(text)
        result = self.execute(actor, 'Formal Failure Diagnostician')
        self.assertEqual(result['status'], 'success')
        actual, recorded = client.requests[0], result['requests'][0]
        for key in ('temperature', 'top_p', 'extra_body', 'max_tokens'):
            self.assertEqual(actual[key], recorded[key])
        self.assertFalse(actual['extra_body']['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(actual['max_tokens'], 1024)
        self.assertNotIn('extra_body', actor.protocol['generation'])
        observation = self.adapter.public_observation(self.env)
        diagnosis = json.loads(observation['artifacts']['diagnosis']['content'])
        self.assertEqual(diagnosis['status'], 'complete')

    def test_partial_diagnosis_keeps_completed_fields_not_unfinished_tail(self):
        text = 'Observed error: unknown constant missingLemma\nLocation: line 6\nLikely cause: unfinished guess'
        actor, _, _ = self.actor(text, finish='length')
        result = self.execute(actor, 'Formal Failure Diagnostician')
        self.assertEqual(result['status'], 'success')
        raw = result['responses'][0]
        self.assertEqual(raw['raw_output'], text)
        self.assertEqual(raw['metadata']['generation_failure'], 'output_truncated')
        observation = self.adapter.public_observation(self.env)
        diagnosis = json.loads(observation['artifacts']['diagnosis']['content'])
        self.assertEqual(diagnosis['status'], 'partial')
        self.assertEqual(set(diagnosis['fields']), {'Observed error', 'Location'})
        self.assertTrue(observation['role_progress']['last_result']['partial_diagnosis'])

    def test_abstract_plan_is_not_salvaged_as_a_diagnosis(self):
        for finish in ('length', 'stop'):
            actor, _, _ = self.actor('### Abstract Plan\nProve the theorem by induction.\n', finish=finish)
            result = self.execute(actor, 'Formal Failure Diagnostician')
            self.assertEqual(result['status'], 'invalid_output')
            self.assertNotIn('diagnosis', self.adapter._state(self.env)['artifacts'])

    def test_truncated_proof_still_never_submits(self):
        actor, _, _ = self.actor('by\n  have unfinished : True := by', finish='length')
        before = self.adapter.versions(self.env)
        result = self.execute(actor)
        self.assertEqual(result['contract_error']['code'], 'output_truncated')
        self.assertEqual(before, self.adapter.versions(self.env))

    def test_interrupted_diagnosis_is_not_salvaged(self):
        actor, _, _ = self.actor('Observed error: unknown name\nLocation: line 6\n', failure=True)
        result = self.execute(actor, 'Formal Failure Diagnostician')
        self.assertEqual(result['failure_origin'], 'executor_service')
        self.assertNotIn('diagnosis', self.adapter._state(self.env)['artifacts'])

    def test_error_at_end_survives_warning_prefix_and_further_budget_trim(self):
        actor, client, _ = self.actor('by\n  rfl\n' + END)
        state = self.adapter._state(self.env)
        reason = 'assumptions.lean:45:0: error: Forbidden reference to benchmark target: Int.lcm_assoc'
        original = {'passed': False, 'checks': {'kernel_assumptions': False}, 'unexpected_axioms': [],
                    'kernel_probe': {'returncode': 1, 'stdout': ('file.lean:1:0: warning: unused\n' * 300) + reason, 'stderr': ''}}
        self.adapter._store(self.env, state, 'verification', original, self.adapter.versions(self.env), 'verify_proof')
        self.adapter._save_state(self.env, state)
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        self.assertIn(reason, client.requests[0]['messages'][1]['content'])
        payload = result['requests'][0]['executor_payload']
        verification = next(e for e in payload['public_context']['handoff_evidence'] if e['key'] == 'verification')
        self.assertEqual(verification['critical']['forbidden_dependencies'], ['Int.lcm_assoc'])
        # The structured essentials are metadata, not part of a trimmable prefix.
        verification['content'] = verification['content'][:80]
        self.assertIn('Int.lcm_assoc', actor.render_payload(payload, self.adapter))
        raw = self.adapter.execute_tool(self.env, 'read_artifact', {'artifact': 'verification', 'offset': 8000})
        self.assertEqual(raw.output['content'], json.dumps(original, ensure_ascii=False, indent=2)[8000:16000])

    def test_focused_inspection_state_precedes_large_other_states(self):
        from routing_benchmark.v4.execution.formal_handoff import project_tool_evidence
        report = {'status': 'partial', 'certifies_proof': False, 'has_errors': True,
                  'diagnostics': [{'severity': 'error', 'line': 33, 'message': 'rcases failed'}],
                  'tactic_states': [{'position': {'line': 33}, 'goals_before': 'a in s and b = c'},
                                    {'goals_before': 'other ' * 3000}]}
        critical, text = project_tool_evidence('inspection', report)
        self.assertIn('a in s and b = c', text[:1000])
        self.assertEqual(critical['first_error']['message'], 'rcases failed')
        self.assertFalse(critical['certifies_proof'])

    def test_duplicate_candidate_is_reported_without_skipping_call(self):
        for _ in range(2):
            actor, client, _ = self.actor('by\n  rfl\n' + END)
            result = self.execute(actor)
            self.assertEqual(len(client.requests), 1)
            self.assertEqual(result['status'], 'success')
        progress = self.adapter.public_observation(self.env)['role_progress']
        self.assertTrue(progress['last_result']['duplicate_candidate'])
        self.assertFalse(progress['last_result']['candidate_changed'])
        self.assertEqual(progress['by_role']['Proof Repair Specialist']['calls'], 2)

    def test_generation_failure_count_reaches_both_router_and_executor(self):
        initial = None
        for _ in range(2):
            actor, _, _ = self.actor('by\n  have unfinished', finish='length')
            if initial is None:
                initial = self.adapter.progress_observation(self.adapter.public_observation(self.env))
            result = self.execute(actor)
            self.adapter.record_contract_error(self.env, result['contract_error'])
        observation = self.adapter.public_observation(self.env)
        summary = observation['role_progress']['by_role']['Proof Repair Specialist']
        self.assertEqual(summary['consecutive_generation_failures_for_role'], 2)
        context = self.adapter.executor_context(self.env, 'Formal Failure Diagnostician')
        self.assertEqual(context['state']['role_progress'], observation['role_progress'])
        self.assertEqual(context['state']['latest_generation_failure']['code'], 'output_truncated')
        self.assertTrue(context['state']['latest_generation_failure']['fresh'])
        self.assertFalse(observation['role_progress']['last_result']['artifact_created'])
        self.assertEqual(initial, self.adapter.progress_observation(observation))

    def test_repair_keeps_thinking_default_and_4096_cap(self):
        actor, client, _ = self.actor('by\n  rfl\n' + END)
        self.execute(actor)
        self.assertEqual(client.requests[0]['temperature'], 0.6)
        self.assertNotIn('extra_body', client.requests[0])
        self.assertEqual(client.requests[0]['max_tokens'], 4096)

    def test_retriever_sends_non_thinking_and_uses_existing_lookup_tool(self):
        actor, client, _ = self.actor('{"tool":"write_premises","arguments":{"symbols":["Nat.add_comm"]}}')
        with patch.object(self.adapter, '_compile', return_value={'returncode': 0, 'stdout': 'Nat.add_comm', 'stderr': ''}):
            result = self.execute(actor, 'Premise and Lemma Retriever')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(client.requests[0]['max_tokens'], 1024)
        self.assertFalse(client.requests[0]['extra_body']['chat_template_kwargs']['enable_thinking'])
        self.assertEqual(result['tool_events'][0]['tool_call']['name'], 'write_premises')

    def test_v2_router_keeps_all_choices_and_call_accounting(self):
        from routing_benchmark.routers import RoutingDecision
        from routing_benchmark.v4.execution.shared_runner import SharedTrajectoryRunner
        actor, _, _ = self.actor('by\n  have unfinished', finish='length')
        class Sequence:
            def reset(self, seed):
                self.actions = iter(['Tactic Synthesizer', 'Tactic Synthesizer', 'STOP'])
            def select(self, observation, candidates):
                self.last_observation, self.candidates = observation, candidates
                return RoutingDecision(next(self.actions))
        router = Sequence()
        roles = json.loads((BANK / 'agent_pools/formal_proof.json').read_text(encoding='utf-8'))
        result = SharedTrajectoryRunner(router=router, actor=actor, max_calls=12).run(
            manifest_path=PACK, adapter=self.adapter, workspace=Path(self.tmp.name) / 'runner/workspace',
            output_dir=Path(self.tmp.name) / 'runner', roles=roles)
        self.assertEqual(result['executor_calls'], 2)
        self.assertEqual(result['terminal_reason'], 'PREMATURE_STOP')
        self.assertEqual(len(router.candidates), 8)
        summary = router.last_observation['current_state']['role_progress']['by_role']['Tactic Synthesizer']
        self.assertEqual(summary['consecutive_generation_failures_for_role'], 2)
        trace = [json.loads(line) for line in (Path(self.tmp.name) / 'runner/trajectory.jsonl').read_text().splitlines()]
        self.assertTrue(all(row['semantic_delta'] == 'no_state_change' for row in trace))


@unittest.skipUnless(os.getenv('FORMAL_REAL_LEAN') == '1', 'Set FORMAL_REAL_LEAN=1 for pinned Lean integration')
class RealInspectionTests(unittest.TestCase):
    def test_real_tactic_context_types_and_no_certificate_on_both_runtimes(self):
        for version, packet in [('4.8.0-rc1', 'formal40-09-leandojo'), ('4.22.0-rc4', 'formal40-33-april')]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                manifest = BANK / 'packs/formal_proof' / packet / 'manifest.json'
                runtime = resolve_runtime(CONFIG, manifest, PROJECT)
                runtime.update(formal_inspection_policy='tactic_state_v1', formal_context_policy='bounded_artifact_handoff_v1')
                adapter = FormalProofV2Adapter(); adapter.configure_runtime(runtime)
                env = adapter.materialize(manifest, Path(temporary) / 'workspace')
                source = env.workspace_dir / 'public/Main.lean'
                source.write_text('import Lean\nexample (n : Nat) (h : n = 3) : n = 3 := by\n  exact Nat.add_comm 1 2\n', encoding='utf-8')
                before = source.read_bytes()
                result = adapter.execute_tool(env, 'inspect_proof')
                self.assertEqual(result.status, 'success', result.output)
                self.assertEqual(result.output['status'], 'partial')
                self.assertTrue(result.output['has_errors'])
                self.assertTrue(any('h : n = 3' in t['goals_before'] for t in result.output['tactic_states']))
                self.assertTrue(any(t['expected_type'] == 'n = 3' for t in result.output['term_types']))
                self.assertEqual(source.read_bytes(), before)
                self.assertNotIn('compilation', adapter._state(env)['artifacts'])
                self.assertFalse(adapter.terminal_status(env)['terminal'])
                cached = adapter.execute_tool(env, 'inspect_proof')
                self.assertTrue(cached.output['cache_hit'])
                context = adapter.executor_context(env, 'Proof Repair Specialist')
                self.assertIn('inspection', {item['key'] for item in context['handoff_evidence']})
                self.assertIn('inspection_trace', adapter._state(env)['artifacts'])


if __name__ == '__main__':
    unittest.main()
