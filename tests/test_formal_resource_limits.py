"""Resource profile checks; no model requests or warm-up executions."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from routing_benchmark.v4.artifacts.manifest import load_manifest
from routing_benchmark.v4.execution.adapters.formal_proof import FormalProofAdapter
from routing_benchmark.v4.execution.adapters.formal_proof_v2 import FormalProofV2Adapter
from routing_benchmark.v4.execution.base import EnvironmentHandle
from routing_benchmark.v4.execution.formal_actor import FormalRoleActor
from routing_benchmark.v4.execution.runtime import resolve_runtime

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PROJECT/'config/shared_environment/formal40_recovery_v3_input12k_lean48_jev.yaml').read_text(encoding='utf-8'))
RUN = PROJECT/'runs/formal40_jev_recovery_v3_lean48_pilot6_b12'


class FormalResourceTests(unittest.TestCase):
    def test_profile_only_changes_input_and_lean_timeout(self):
        old = yaml.safe_load((PROJECT/'config/shared_environment/formal40_recovery_v3_lean48_jev.yaml').read_text(encoding='utf-8'))
        new = copy.deepcopy(CONFIG)
        self.assertEqual(new['executor']['formal_protocol']['input_max_tokens'], 12288)
        new['executor']['formal_protocol']['input_max_tokens'] = 8192
        self.assertEqual(new['runtime'].pop('compile_timeout_seconds'), 300)
        self.assertEqual(old, new)

    def test_compile_and_kernel_probe_use_runtime_timeout(self):
        for limit in (None, 300):
            adapter = FormalProofAdapter()
            runtime = {'lean_executable': 'lean.exe', 'project_dir': str(PROJECT)}
            if limit is not None:
                runtime['compile_timeout_seconds'] = limit
            adapter.configure_runtime(runtime)
            for filename in ('Main.lean', 'assumptions.lean'):
                with patch('routing_benchmark.v4.execution.adapters.formal_proof.subprocess.run',
                           return_value=SimpleNamespace(returncode=0, stdout='', stderr='')) as run:
                    self.assertEqual(adapter._compile(PROJECT/filename)['returncode'], 0)
                    self.assertEqual(run.call_args.kwargs['timeout'], 180 if limit is None else 300)

    def test_invalid_timeout_is_rejected(self):
        for limit in (0, -1, True, '300'):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                FormalProofAdapter().configure_runtime({'compile_timeout_seconds': limit})

    def test_timeout_survives_pinned_runtime_resolution(self):
        manifest = PROJECT/CONFIG['packet_root']/'packs/formal_proof/formal40-09-leandojo/manifest.json'
        self.assertEqual(resolve_runtime(CONFIG, manifest, PROJECT)['compile_timeout_seconds'], 300)

    @unittest.skipUnless((RUN/'episodes/formal40-16-leandojo/workspace/_runtime/state.json').is_file(), 'Saved sample 16 is unavailable')
    def test_sample16_end_context_fits_new_input_limit_without_mutating_old_run(self):
        pack = PROJECT/CONFIG['packet_root']/'packs/formal_proof/formal40-16-leandojo'
        workspace = RUN/'episodes/formal40-16-leandojo/workspace'
        state_path = workspace/'_runtime/state.json'
        before = hashlib.sha256(state_path.read_bytes()).hexdigest()
        adapter = FormalProofV2Adapter()
        adapter.configure_runtime(CONFIG['runtime'])
        env = EnvironmentHandle(load_manifest(pack), pack, workspace)
        roles = json.loads((RUN/'role_cards.json').read_text(encoding='utf-8'))
        role = next(role for role in roles if role['agent_id'] == 'Formal Failure Diagnostician')
        context = adapter.executor_context(env, role['agent_id'], role)
        payload = {'task': env.manifest.task, 'role': role, 'public_context': context,
                   'allowed_tools': [t.to_dict() for t in adapter.tool_spec(env, role['agent_id'], role)],
                   'constraints': {'perform_only_selected_role': True, 'private_reference_visible': False, 'do_not_choose_next_agent': True}}
        actor = FormalRoleActor(None, CONFIG['executor']['model'], formal_protocol=CONFIG['executor']['formal_protocol'])
        instruction = actor.instruction_for('', action=role['agent_id'], adapter=adapter, plain_tool='write_diagnosis')
        bounded = actor.prepare_payload(payload, adapter=adapter, instruction=instruction)
        tokens = bounded['public_context']['input_budget']['estimated_tokens_with_chat_reserve']
        self.assertLessEqual(tokens, 12288)
        self.assertTrue(bounded['public_context']['state']['role_progress'])
        self.assertEqual(before, hashlib.sha256(state_path.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
