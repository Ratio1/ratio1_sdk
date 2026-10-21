"""Offline HTTP contract tests; no session connection or real key is created."""
import copy
import unittest
from unittest.mock import Mock, patch

import requests

from ratio1.base.generic_session import GenericSession


class DeeployAsyncClientTests(unittest.TestCase):
  def setUp(self):
    self.session = object.__new__(GenericSession)
    self.session.P = Mock()
    self.logger = Mock()
    self.engine = Mock()
    self.engine.eth_sign_payload.side_effect = self.sign
    self.signed = []
    self.patches = [
      patch('ratio1.base.generic_session.DefaultBlockEngine', return_value=self.engine),
      patch('ratio1.base.generic_session.os.path.isfile', return_value=True),
      patch.object(GenericSession, '_GenericSession__validate_deeploy_network_and_get_api_url',
                   return_value=('test', 'https://oracle.invalid/deeploy')),
      patch('ratio1.base.generic_session.requests.post'),
      patch('ratio1.base.generic_session.BaseCodeChecker'),
    ]
    mocks = [item.start() for item in self.patches]
    for item in self.patches:
      self.addCleanup(item.stop)
    self.post = mocks[3]
    self.response = self.post.return_value
    self.response.status_code = 202
    self.response.json.return_value = {'result': {'status': 'accepted', 'operation_id': 'operation'}}
    self.checker = mocks[4].return_value
    self.checker._get_method_data.return_value = ('handler', ['plugin', 'message'], 'encoded')
    self.checker.get_function_source_code.return_value = 'pass'
    self.checker.code_to_base64.return_value = ('encoded', [])
    self.args = dict(logger=self.logger, signer_private_key_path='offline.pem',
                     request_id='persisted-id', job_id=7, target_nodes=['node'])

  def sign(self, payload, **kwargs):
    self.signed.append(copy.deepcopy(payload))
    payload.update(EE_ETH_SIGN='signature', EE_ETH_SENDER='wallet')

  def test_create_helpers_sign_job_and_stable_identity_and_return_acceptance(self):
    calls = [
      lambda: self.session.deeploy_launch_container_app(docker_image='image', port=80, **self.args),
      lambda: self.session.deeploy_custom_code(custom_code=lambda: None, **self.args),
      lambda: self.session.deeploy_simple_telegram_bot(
        message_handler=lambda: None, telegram_bot_token='test-token', **self.args),
    ]
    for call in calls:
      with self.subTest(call=call):
        result = call()
        self.assertEqual(result['result']['status'], 'accepted')
        self.assertEqual(self.signed[-1]['request_id'], 'persisted-id')
        self.assertEqual(self.signed[-1]['job_id'], 7)
        self.assertEqual(self.post.call_args.kwargs['timeout'], (10, 30))
        self.assertTrue(self.post.call_args.args[0].endswith('/create_pipeline'))

  def test_timeout_keeps_request_identity_for_caller_retry(self):
    self.post.side_effect = [requests.Timeout('acceptance unknown'), self.response]
    with self.assertRaises(requests.Timeout):
      self.session.deeploy_launch_container_app(docker_image='image', port=80, **self.args)
    self.session.deeploy_launch_container_app(docker_image='image', port=80, **self.args)
    self.assertEqual([value['request_id'] for value in self.signed], ['persisted-id'] * 2)
    self.logger.P.assert_not_called()

  def test_required_identity_and_whole_job_delete(self):
    for request_id in ('', None, ' '):
      with self.assertRaises(ValueError):
        self.session.deeploy_launch_container_app(
          docker_image='image', port=80, **{**self.args, 'request_id': request_id})
    self.post.assert_not_called()
    args = {key: value for key, value in self.args.items() if key != 'target_nodes'}
    self.session.deeploy_close(app_id='app', expected_revision=4, **args)
    request = self.signed[-1]
    self.assertEqual(request['expected_revision'], 4)
    self.assertEqual(request['job_id'], 7)
    self.assertNotIn('target_nodes', request)
    self.assertNotIn('target_nodes_count', request)
    with self.assertRaises(TypeError):
      self.session.deeploy_close(app_id='app', expected_revision=4, **self.args)

  def test_read_auth_is_nonce_only_and_reusable_across_oracles(self):
    url, auth = self.session.deeploy_get_read_auth(self.logger, 'offline.pem')
    self.assertEqual(set(self.signed[-1]), {'nonce'})
    original = copy.deepcopy(auth)
    for host in (url, 'https://second.invalid/deeploy'):
      self.session.deeploy_get_deployment_status(host, auth, operation_id='operation')
      self.assertEqual(self.post.call_args.kwargs['json']['request'],
                       {**auth, 'operation_id': 'operation'})
    self.assertEqual(auth, original)
    self.engine.eth_sign_payload.assert_called_once()
    self.session.deeploy_get_deployment_status(url, auth, request_id='persisted-id', job_id=7, kind='create')
    with self.assertRaises(ValueError):
      self.session.deeploy_get_deployment_status(url, auth, request_id='persisted-id')

  def test_delete_accepts_legacy_revision_zero_and_rejects_invalid_revisions(self):
    args = {key: value for key, value in self.args.items() if key != 'target_nodes'}
    self.session.deeploy_close(app_id='app', expected_revision=0, **args)
    self.assertEqual(self.signed[-1]['expected_revision'], 0)
    self.assertTrue(self.post.call_args.args[0].endswith('/delete_pipeline'))
    self.post.reset_mock()
    for revision in (-1, True, False, 1.5, '0', None):
      with self.subTest(revision=revision), self.assertRaises(ValueError):
        self.session.deeploy_close(app_id='app', expected_revision=revision, **args)
    self.post.assert_not_called()

  def test_http_auth_and_admission_errors_remain_observable(self):
    self.response.raise_for_status.side_effect = requests.HTTPError(response=self.response)
    with self.assertRaises(requests.HTTPError) as caught:
      self.session.deeploy_launch_container_app(docker_image='image', port=80, **self.args)
    self.assertIs(caught.exception.response, self.response)

  def test_unbounded_timeout_is_rejected_before_http(self):
    for timeout in (None, 0, float('inf'), (10, None)):
      with self.subTest(timeout=timeout), self.assertRaises(ValueError):
        self.session.deeploy_launch_container_app(
          docker_image='image', port=80, request_timeout=timeout, **self.args)
    self.post.assert_not_called()


if __name__ == '__main__':
  unittest.main()
