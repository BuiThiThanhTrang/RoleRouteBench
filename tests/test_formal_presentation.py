"""Presentation-only parsing and duplicate identity; native validity stays separate."""
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import yaml

import test_formal_handoff as handoff
from test_formal_handoff import FakeClient, FakeStream, PROJECT, BANK, PACK
from routing_benchmark.v4.execution.formal_actor import FormalRoleActor, diagnosis_fields, END
from routing_benchmark.v4.execution.formal_identity import source_identity
from routing_benchmark.v4.execution.adapters.formal_proof import constrained_source

CONFIG = yaml.safe_load((PROJECT / 'config/shared_environment/formal40_recovery_v3_lean48_jev.yaml').read_text(encoding='utf-8'))
RUN = PROJECT / 'runs/formal40_jev_recovery_v2_lean48_pilot6_b12'


class IdentityTests(unittest.TestCase):
    def identity(self, text):
        return source_identity(text)['fingerprint']

    def test_comment_blank_lines_and_inline_spaces_are_presentation_only(self):
        a = 'by\n  -- old note\n  have h : True := by\n    trivial\n  exact h\n'
        b = 'by\n\n  have   h : True := by\n    trivial /- outer /- nested -/ note -/\n  exact  h\n'
        self.assertEqual(self.identity(a), self.identity(b))
        self.assertEqual(self.identity('by exact (f ⟨a,b⟩)'), self.identity('by exact ( f ⟨ a , b ⟩ )'))
        self.assertEqual(self.identity(a), self.identity(a.replace('\n', '\r\n')))

    def test_indentation_and_token_line_boundaries_remain_significant(self):
        self.assertNotEqual(self.identity('by\n  first\n  | exact h\n'), self.identity('by\n  first\n    | exact h\n'))
        self.assertNotEqual(self.identity('by exact h'), self.identity('by\n  exact h'))

    def test_literals_and_quoted_identifiers_preserve_content(self):
        for a, b in [
            ('by exact "a b"', 'by exact "ab"'),
            ('by exact "-- a"', 'by exact "-- b"'),
            ('by exact r#"a " /- text -/"#', 'by exact r#"a " /- changed -/"#'),
            ("by exact ' '", "by exact 'a'"),
            ('by exact «a b»', 'by exact «ab»'),
            ('by exact Nat.add_comm', 'by exact Nat.add_assoc'),
            ('by exact "a\nb"', 'by exact "a\r\nb"'),
            ('by exact a => b', 'by exact a = > b'),
        ]:
            with self.subTest(a=a):
                self.assertNotEqual(self.identity(a), self.identity(b))

    def test_unclosed_string_or_comment_uses_exact_fallback(self):
        for text in ['by /- unfinished', 'by exact "unfinished', 'by exact r#"unfinished']:
            self.assertFalse(source_identity(text)['lexed'])
            self.assertNotEqual(self.identity(text), self.identity(text + ' '))

    def test_profiles_change_only_parser_and_candidate_identity(self):
        for runtime in ('lean48', 'lean422'):
            root = PROJECT / 'config/shared_environment'
            old = yaml.safe_load((root/f'formal40_recovery_v2_{runtime}_jev.yaml').read_text(encoding='utf-8'))
            new = yaml.safe_load((root/f'formal40_recovery_v3_{runtime}_jev.yaml').read_text(encoding='utf-8'))
            self.assertEqual(new['executor']['formal_protocol'].pop('parser_policy'), 'presentation_v1')
            self.assertEqual(new['runtime'].pop('formal_candidate_identity'), 'lean_tokens_layout_v1')
            self.assertEqual(old, new)


class PresentationTests(unittest.TestCase):
    setUp = handoff.FormalHandoffTests.setUp
    tearDown = handoff.FormalHandoffTests.tearDown
    execute = handoff.FormalHandoffTests.execute

    def actor(self, text, **kwargs):
        self.adapter.configure_runtime(CONFIG['runtime'])
        stream = FakeStream(text, **kwargs)
        client = FakeClient(stream)
        return FormalRoleActor(client, 'fake', formal_protocol=CONFIG['executor']['formal_protocol']), client, stream

    def test_numbered_bulleted_bold_diagnosis_labels_are_normalized(self):
        labels = ['Observed error', 'Location', 'Likely cause', 'Repair constraint', 'Uncertainty']
        for style in ('numbered', 'bullet', 'bold'):
            lines = [f'{i}. {k}: value' if style == 'numbered' else
                     f'- {k}: value' if style == 'bullet' else f'**{k}:** value'
                     for i, k in enumerate(labels, 1)]
            text = '\n'.join(lines) + '\n' + END
            actor, _, _ = self.actor(text)
            result = self.execute(actor, 'Formal Failure Diagnostician')
            self.assertEqual(result['status'], 'success')
            response = result['responses'][0]
            self.assertEqual(response['raw_output'], text)
            self.assertEqual(response['metadata']['diagnosis_artifact']['fields'], dict.fromkeys(labels, 'value'))
        self.assertFalse(diagnosis_fields('1. Observed error: value\n'))  # Legacy policy unchanged.

    def test_conflicting_diagnosis_fields_are_not_resolved_by_parser(self):
        self.assertEqual(diagnosis_fields('1. Observed error: A\n2. Observed error: B\n', presentation=True), {})

    def test_plain_full_source_uses_existing_immutable_adapter(self):
        original = (BANK / 'packs/formal_proof/formal40-09-leandojo/public/Main.lean').read_text(encoding='utf-8')
        text = original.replace('sorry', 'rfl')
        actor, client, _ = self.actor(text)
        result = self.execute(actor)
        self.assertEqual(result['status'], 'success')
        self.assertIn('original full source', client.requests[0]['messages'][1]['content'])
        self.assertEqual((self.env.workspace_dir / 'public/Main.lean').read_text(encoding='utf-8'), constrained_source(original, text))
        self.assertEqual(result['responses'][0]['raw_output'], text)

    def test_wrong_context_unclosed_fence_and_truncated_source_still_fail(self):
        original = (BANK / 'packs/formal_proof/formal40-09-leandojo/public/Main.lean').read_text(encoding='utf-8')
        for text, finish in [('import Mathlib\ntheorem changed : True := by trivial', 'stop'),
                             (original.replace('sorry', 'rfl') + '\n```', 'stop'),
                             (original.replace('sorry', 'rfl'), 'length')]:
            actor, _, _ = self.actor(text, finish=finish)
            before = self.adapter.versions(self.env)
            result = self.execute(actor)
            self.assertEqual(result['status'], 'invalid_output')
            self.assertEqual(before, self.adapter.versions(self.env))

    def test_comment_only_candidate_reaches_router_and_executor_as_duplicate(self):
        actor, _, _ = self.actor('by\n  -- first attempt\n  rfl\n' + END)
        self.execute(actor)
        with patch.object(self.adapter, '_compile', return_value={'returncode': 1, 'stdout': 'error: example failure', 'stderr': ''}):
            self.adapter.execute_tool(self.env, 'compile_proof')
        before = self.adapter.public_observation(self.env)
        actor, client, _ = self.actor('by\n\n  rfl\n' + END)
        self.execute(actor)
        after = self.adapter.public_observation(self.env)
        row = after['role_progress']['last_result']
        self.assertTrue(row['source_changed'])
        self.assertFalse(row['candidate_changed'])
        self.assertTrue(row['duplicate_candidate'])
        self.assertEqual(len(client.requests), 1)
        self.assertNotEqual(before['source_hash'], after['source_hash'])
        self.assertTrue(before['artifacts']['compilation']['fresh'])
        self.assertFalse(after['artifacts']['compilation']['fresh'])  # No stale certificate reuse.
        self.assertEqual(self.adapter.progress_observation(before), self.adapter.progress_observation(after))
        context = self.adapter.executor_context(self.env, 'Proof Repair Specialist')
        self.assertTrue(context['state']['role_progress']['last_result']['duplicate_candidate'])

    def test_real_tactic_change_and_string_change_are_new_candidates(self):
        for first, second in [('by\n  rfl', 'by\n  simp'),
                              ('by\n  have s := "a b"\n  rfl', 'by\n  have s := "ab"\n  rfl')]:
            actor, _, _ = self.actor(first)
            self.execute(actor)
            actor, _, _ = self.actor(second)
            self.execute(actor)
            row = self.adapter.public_observation(self.env)['role_progress']['last_result']
            self.assertTrue(row['candidate_changed'])
            self.assertFalse(row['duplicate_candidate'])

    def test_duplicate_does_not_change_call_budget_or_remove_role_choices(self):
        from routing_benchmark.routers import RoutingDecision
        from routing_benchmark.v4.execution.shared_runner import SharedTrajectoryRunner
        actor, client, _ = self.actor('by\n  rfl')
        streams = iter([FakeStream('by\n  -- first\n  rfl'), FakeStream('by\n  rfl')])
        def query(**kwargs):
            client.requests.append(kwargs)
            return next(streams)
        client.create = query
        class Router:
            def reset(self, seed): self.actions = iter(['Tactic Synthesizer', 'Proof Repair Specialist', 'STOP'])
            def select(self, observation, candidates):
                self.last, self.candidates = observation, candidates
                return RoutingDecision(next(self.actions))
        router = Router()
        roles = json.loads((BANK / 'agent_pools/formal_proof.json').read_text(encoding='utf-8'))
        folder = Path(self.tmp.name) / 'runner'
        result = SharedTrajectoryRunner(router=router, actor=actor, max_calls=12).run(
            manifest_path=PACK, adapter=self.adapter, workspace=folder/'workspace', output_dir=folder, roles=roles)
        self.assertEqual(result['executor_calls'], 2)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(len(router.candidates), 8)
        self.assertTrue(router.last['current_state']['role_progress']['last_result']['duplicate_candidate'])
        trace = [json.loads(x) for x in (folder/'trajectory.jsonl').read_text().splitlines()]
        self.assertEqual(trace[-1]['semantic_delta'], 'no_state_change')


class RecordedPilotTests(unittest.TestCase):
    @unittest.skipUnless(RUN.exists(), 'Saved pilot is not available')
    def test_saved_contexts_fit_with_identity_metadata_and_preserve_rejection_reason(self):
        from types import SimpleNamespace
        actor = FormalRoleActor(None, 'context-preflight-only', formal_protocol=CONFIG['executor']['formal_protocol'])
        adapter = SimpleNamespace(adapter_id='formal_proof.lean4.v2')
        checked = 0
        for episode in sorted((RUN/'episodes').iterdir()):
            for line in (episode/'trajectory.jsonl').read_text(encoding='utf-8').splitlines():
                row = json.loads(line)
                for request in row.get('result', {}).get('requests', []):
                    payload = copy.deepcopy(request['executor_payload'])
                    state = payload['public_context']['state']
                    identity = source_identity(state['source'])
                    state['source_identity'] = identity
                    if candidate := state['artifacts'].get('candidate'):
                        candidate['presentation_identity'] = identity
                    if last := state['role_progress'].get('last_result'):
                        last.update(source_changed=last['candidate_changed'], candidate_identity_policy=identity['policy'],
                                    candidate_fingerprint_before=identity['fingerprint'], candidate_fingerprint_after=identity['fingerprint'])
                    for summary in state['role_progress']['by_role'].values():
                        summary['consecutive_duplicate_candidates_for_role'] = 0
                    role = row['agent_id']
                    instruction = actor.instruction_for('Return one allowed JSON tool call.', action=role, adapter=adapter,
                        plain_tool='write_source' if role in ('Tactic Synthesizer', 'Proof Repair Specialist') else
                                   'write_diagnosis' if role == 'Formal Failure Diagnostician' else None)
                    original_reason = 'Forbidden reference to benchmark target: Int.clog_natCast'
                    had_reason = original_reason in actor.render_payload(payload, adapter)
                    bounded = actor.prepare_payload(payload, adapter=adapter, instruction=instruction)
                    self.assertLessEqual(bounded['public_context']['input_budget']['estimated_tokens_with_chat_reserve'], 8192)
                    access = bounded['public_context']['state']['source_access']
                    self.assertEqual(access['visible_chars'], access['total_chars'])
                    if had_reason:
                        self.assertIn(original_reason, actor.render_payload(bounded, adapter))
                    checked += 1
        self.assertEqual(checked, 41)

    @unittest.skipUnless(RUN.exists(), 'Saved pilot is not available')
    def test_recorded_format_and_comment_only_cases_without_model_calls(self):
        for n, step, role in [(12, 1, 'Tactic Synthesizer'), (12, 9, 'Proof Repair Specialist'), (13, 1, 'Tactic Synthesizer'),
                               (12, 10, 'Formal Failure Diagnostician'), (16, 3, 'Formal Failure Diagnostician')]:
            path = RUN / 'episodes' / f'formal40-{n}-leandojo' / 'trajectory.jsonl'
            trace_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            row = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()][step]
            raw = row['result']['responses'][0]['raw_output']
            actor = FormalRoleActor(FakeClient(FakeStream(raw)), 'recorded-output-replay', formal_protocol=CONFIG['executor']['formal_protocol'])
            actor.action = role
            _, metadata = actor._query([{'role': 'user', 'content': 'Replay saved output; no model inference'}])
            self.assertNotIn('generation_error', metadata)
            if role != 'Formal Failure Diagnostician':
                source = (BANK / 'packs/formal_proof' / f'formal40-{n}-leandojo/public/Main.lean').read_text(encoding='utf-8')
                constrained_source(source, actor.prepare_work_product(raw, metadata))
            self.assertEqual(trace_hash, hashlib.sha256(path.read_bytes()).hexdigest())
        episode = RUN / 'episodes/formal40-16-leandojo/trajectory.jsonl'
        rows = [json.loads(x) for x in episode.read_text(encoding='utf-8').splitlines()]
        sources = []
        for step in (6, 9):
            raw = rows[step]['result']['tool_events'][0]['tool_call']['arguments']['content']
            sources.append(re.findall(r'```(?:lean4?)?\s*\n(.*?)```', raw, re.S)[-1])
        self.assertNotEqual(sources[0], sources[1])
        self.assertEqual(source_identity(sources[0])['fingerprint'], source_identity(sources[1])['fingerprint'])


if __name__ == '__main__':
    unittest.main()
