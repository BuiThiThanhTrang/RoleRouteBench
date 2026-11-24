"""Provider errors remain useful without disclosing credentials or changing routing."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import PermissionDeniedError

from routing_benchmark.routers import RoutingDecision
from routing_benchmark.v4.execution.base import PreconditionResult
from routing_benchmark.v4.execution.shared_actor import RoleTransportError, SharedRoleActor
from routing_benchmark.v4.execution.shared_runner import SharedTrajectoryRunner
from routing_benchmark.v4.execution.transport_diagnostics import BODY_LIMIT, transport_error_details


def denied(body, headers=None):
    request = httpx.Request('POST', 'https://provider.example/v1/chat/completions',
                            headers={'Authorization': 'Bearer custom-credential-123456'})
    response = httpx.Response(403, request=request, headers=headers or {}, json=body)
    return PermissionDeniedError('Denied', response=response, body=body)


class TransportDiagnosticsTests(unittest.TestCase):
    def test_sdk_json_error_keeps_message_and_trace_but_redacts_credentials(self):
        error = denied({'error': {'message': 'Denied Bearer custom-credential-123456; hf_example987654',
                                  'api_key': 'not-from-environment', 'code': 'access_denied'}},
                       {'x-request-id': 'req-123', 'cf-ray': 'ray-456', 'set-cookie': 'private-cookie'})
        with patch.dict(os.environ, {'HF_TOKEN': 'hf_example987654'}, clear=True):
            result = transport_error_details(error)
        self.assertEqual(result['request_id'], 'req-123')
        self.assertEqual(result['provider_request_ids'], {'x-request-id': 'req-123', 'cf-ray': 'ray-456'})
        self.assertIn('access_denied', result['error_body'])
        for secret in ('custom-credential-123456', 'hf_example987654', 'not-from-environment', 'private-cookie'):
            self.assertNotIn(secret, json.dumps(result))

    def test_html_error_and_missing_sdk_body_keep_cloudflare_identifier(self):
        error = denied(None, {'cf-ray': 'ray-789'})
        error.response = httpx.Response(403, request=error.request,
                                        headers={'cf-ray': 'ray-789'}, text='<html>Request blocked</html>')
        result = transport_error_details(error)
        self.assertEqual(result['request_id'], 'ray-789')
        self.assertEqual(result['error_body'], '<html>Request blocked</html>')

    def test_body_request_id_and_bounded_log(self):
        result = transport_error_details(denied({'request_id': 'body-123', 'message': 'x' * (BODY_LIMIT + 100)}))
        self.assertEqual(result['request_id'], 'body-123')
        self.assertEqual(len(result['error_body']), BODY_LIMIT)
        self.assertTrue(result['error_body_truncated'])

    def test_connection_error_does_not_dump_request_or_exception_repr(self):
        result = transport_error_details(ConnectionError('private request contents'))
        self.assertIsNone(result['error_body'])
        self.assertIsNone(result['request_id'])
        self.assertIsNone(result['http_status'])
        self.assertNotIn('private request contents', json.dumps(result))

    def test_unread_http_response_does_not_hide_original_failure(self):
        error = denied(None, {'x-request-id': 'unread-123'})
        error.response = httpx.Response(403, request=error.request, headers={'x-request-id': 'unread-123'},
                                        stream=httpx.ByteStream(b'not read'))
        result = transport_error_details(error)
        self.assertEqual(result['request_id'], 'unread-123')
        self.assertIsNone(result['error_body'])

    def test_stream_error_can_take_trace_id_from_stream_response(self):
        response = httpx.Response(200, headers={'x-request-id': 'stream-request-1'})
        result = transport_error_details(ConnectionError('stream closed'), response=response)
        self.assertEqual(result['request_id'], 'stream-request-1')

    def test_403_is_not_retried_and_diagnostics_reach_runner_log_only(self):
        error = denied({'error': {'message': 'Security rule blocked request'}}, {'x-request-id': 'blocked-1'})
        query = Mock(side_effect=error)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=query)))
        actor = SharedRoleActor(client, 'model', transport_retries=5)
        with self.assertRaises(RoleTransportError) as caught:
            actor._query([{'role': 'user', 'content': 'Public task'}])
        self.assertEqual(query.call_count, 1)
        self.assertEqual(caught.exception.diagnostics['request_id'], 'blocked-1')

        class FailingActor:
            def execute(self, **kwargs):
                raise caught.exception

        class Adapter:
            def materialize(self, manifest_path, workspace):
                return SimpleNamespace(manifest=SimpleNamespace(base_workflow_id='sample', domain='formal_proof', task='Public task'))

            def public_observation(self, env):
                return {'terminal': False}

            def public_preconditions(self, env, action, profile):
                return PreconditionResult(True)

            def terminal_status(self, env):
                return {'terminal': False}

        class Router:
            def reset(self, seed):
                self.observations = []

            def select(self, observation, actions):
                self.observations.append(observation)
                return RoutingDecision('Proof Repair Specialist' if len(self.observations) == 1 else 'STOP', {})

        router = Router()
        with tempfile.TemporaryDirectory() as folder:
            runner = SharedTrajectoryRunner(router=router, actor=FailingActor(), max_calls=12)
            result = runner.run(manifest_path='unused', adapter=Adapter(), workspace=Path(folder)/'workspace',
                                output_dir=folder, roles=[{'agent_id': 'Proof Repair Specialist'}])
            event = json.loads((Path(folder)/'trajectory.jsonl').read_text(encoding='utf-8').splitlines()[0])
        self.assertEqual(result['executor_calls'], 1)
        self.assertEqual(result['terminal_reason'], 'PREMATURE_STOP')
        self.assertEqual(event['result']['request_id'], 'blocked-1')
        self.assertIn('Security rule blocked request', event['result']['error_body'])
        self.assertNotIn('error_body', json.dumps(router.observations))
        self.assertEqual(router.observations[1]['constraints']['allowed_actions'], ['Proof Repair Specialist', 'STOP'])


if __name__ == '__main__':
    unittest.main()
