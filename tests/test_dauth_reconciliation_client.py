"""Verify the SDK-owned dAuth reconciliation transport without network access."""
import copy
import traceback
import unittest
from unittest import mock

import requests

from ratio1.bc.base import BaseBlockEngine
from test_dauth_job_secret_client import _DauthClientHarness, REQUEST_TIME, REQUEST_NONCE


class _UpdateClientHarness(_DauthClientHarness):
  """
  Bind the reconciliation API to the existing isolated dAuth engine fixture.

  Notes
  -----
  Signature and oracle checks use fixture results; HTTP is always mocked.
  """
  reconcile_dauth_job_secrets = BaseBlockEngine.reconcile_dauth_job_secrets


class TestDauthSecretReconciliationClient(unittest.TestCase):
  """
  Cover request integrity, response authentication and single-attempt transport.

  Notes
  -----
  Secret reconciliation semantics remain covered by Edge integration tests.
  """
  def setUp(self):
    """Prepare a signed-response fixture and mock the clock and HTTP boundary."""
    self.engine = _UpdateClientHarness()
    self.payload = {'job_id': '7', 'expected_pipeline_cid': 'old-cid',
                    'pipeline_configs': {'worker': {'ENV': {'TOKEN': 'private-token'}}}}
    self.result = {'status': 'success', 'nonce': REQUEST_NONCE, 'job_id': '7',
                   'pipeline_cid': 'new-cid', 'pipeline_configs': {'worker': {}},
                   'EE_SIGN': 'server-signature', 'EE_SENDER': 'server'}
    self.response = mock.Mock(status_code=200)
    self.response.json.return_value = {'result': self.result}
    clock = mock.patch('ratio1.bc.base.time', return_value=REQUEST_TIME)
    self.clock = clock.start()
    self.addCleanup(clock.stop)
    post = mock.patch('ratio1.bc.base.requests.post', return_value=self.response)
    self.post = post.start()
    self.addCleanup(post.stop)

  def test_signs_request_and_checks_selected_network_without_mutating_payload(self):
    """Keep operation data intact and authenticate the selected-network reply."""
    self.engine.default_dauth_url = 'https://dauth.example/proxy/get_auth_data'
    original = copy.deepcopy(self.payload)
    result = self.engine.reconcile_dauth_job_secrets(self.payload, network='testnet', request_timeout=(2, 5))
    self.assertEqual(result, self.result)
    self.assertEqual(self.payload, original)
    self.assertEqual(self.engine.signed_payloads[-1], {**original, 'nonce': REQUEST_NONCE})
    self.assertEqual(self.engine.network_data_calls[-1], 'testnet')
    self.assertEqual(self.engine.oracle_checks[-1], ('0xserver', 'testnet'))
    self.assertEqual(self.engine.verification_calls[-1][1], {'log_hash_sign_fails': False})
    self.assertEqual(self.post.call_args.args[0], 'https://dauth.example/proxy/reconcile_job_secrets')
    self.assertEqual(self.post.call_args.kwargs['timeout'], (2, 5))
    self.assertEqual(self.engine.log_messages, [])

  def test_rejects_malformed_http_and_unauthenticated_or_unsuccessful_responses(self):
    """Reject invalid envelopes without retrying or exposing their body contents."""
    cases = [
      ('http', 503, {'result': self.result}, True, True),
      ('outer shape', 200, [], True, True),
      ('result shape', 200, {'result': []}, True, True),
      ('signature', 200, {'result': self.result}, False, True),
      ('oracle', 200, {'result': self.result}, True, False),
      ('nonce', 200, {'result': {**self.result, 'nonce': 'wrong'}}, True, True),
      ('status', 200, {'result': {**self.result, 'status': 'fail'}}, True, True),
      ('error', 200, {'result': {**self.result, 'error': 'private-token'}}, True, True),
      ('job', 200, {'result': {**self.result, 'job_id': '8'}}, True, True),
      ('cid', 200, {'result': {**self.result, 'pipeline_cid': ''}}, True, True),
      ('nodes', 200, {'result': {**self.result, 'pipeline_configs': {'other': {}}}}, True, True),
      ('config', 200, {'result': {**self.result, 'pipeline_configs': {'worker': []}}}, True, True),
    ]
    for name, status, data, valid, oracle in cases:
      with self.subTest(case=name):
        self.post.reset_mock()
        self.response.status_code = status
        self.response.json.return_value = data
        self.engine.verification_valid = valid
        self.engine.dauth_oracle = oracle
        with self.assertRaises((ValueError, RuntimeError)) as caught:
          self.engine.reconcile_dauth_job_secrets(self.payload)
        self.assertEqual(self.post.call_count, 1)
        self.assertNotIn('private-token', str(caught.exception) + str(self.engine.log_messages))
    self.response.json.assert_called()

  def test_dependency_failures_remain_credential_safe_and_transport_is_not_retried(self):
    """Suppress credential-bearing exception chains from external dependencies."""
    for dependency in ('sign', 'verify', 'web3_is_dauth_oracle', 'json', 'post'):
      with self.subTest(dependency=dependency):
        self.post.reset_mock()
        target = 'ratio1.bc.base.requests.post' if dependency == 'post' else None
        failure = requests.Timeout('private-token') if dependency == 'post' else ValueError('private-token')
        if target:
          patcher = mock.patch(target, side_effect=failure)
        else:
          owner = self.response if dependency == 'json' else self.engine
          patcher = mock.patch.object(owner, dependency, side_effect=failure)
        with patcher as failed, self.assertRaises((ValueError, RuntimeError)) as caught:
          self.engine.reconcile_dauth_job_secrets(self.payload)
        self.assertEqual(failed.call_count, 1)
        formatted = ''.join(traceback.format_exception(type(caught.exception), caught.exception, caught.exception.__traceback__))
        self.assertNotIn('private-token', formatted + str(self.engine.log_messages))
        self.assertTrue(caught.exception.__suppress_context__)
    with self.assertRaises(ValueError):
      self.engine.reconcile_dauth_job_secrets(None)

  def lifecycle(self, action):
    """Build a reference-only lifecycle request and its authenticated response."""
    self.payload = dict(job_id='7', action=action, operation=dict(operation_id='op', plan_cid='plan'))
    self.result.update(action=action, operation_id='op', plan_cid='plan', prepared=True)
    if action in ('commit', 'delete'):
      self.payload['pointer'] = {'pipeline_cid': None if action == 'delete' else 'cid'}
      self.result['pipeline_cid'] = self.payload['pointer']['pipeline_cid']

  def test_lifecycle_actions_keep_operation_identity_and_use_one_request(self):
    """Lifecycle retries belong to the coordinator, including status recovery."""
    for action in ('prepare', 'status', 'commit', 'revoke', 'delete'):
      with self.subTest(action=action):
        self.lifecycle(action)
        self.post.reset_mock()
        original = copy.deepcopy(self.payload)
        self.assertEqual(self.engine.reconcile_dauth_job_secrets(self.payload), self.result)
        self.assertEqual(self.payload, original)
        self.post.assert_called_once()
        self.assertEqual(self.post.call_args.kwargs['json']['body']['operation'], original['operation'])
    self.lifecycle('status')
    self.result['prepared'] = False
    self.assertFalse(self.engine.reconcile_dauth_job_secrets(self.payload)['prepared'])

  def test_lifecycle_rejects_wrong_scope_incomplete_preparation_and_wrong_publication(self):
    """An authenticated reply must still match the exact requested action."""
    cases = [('prepare', 'operation_id', 'other'), ('prepare', 'plan_cid', 'other'),
             ('prepare', 'action', 'commit'), ('prepare', 'prepared', None),
             ('prepare', 'prepared', False), ('commit', 'pipeline_cid', 'other'),
             ('delete', 'pipeline_cid', 'other')]
    for action, field, value in cases:
      with self.subTest(action=action, field=field, value=value):
        self.lifecycle(action)
        self.result[field] = value
        self.post.reset_mock()
        with self.assertRaises((ValueError, RuntimeError)):
          self.engine.reconcile_dauth_job_secrets(self.payload)
        self.post.assert_called_once()
    self.lifecycle('delete')
    del self.result['pipeline_cid']
    with self.assertRaises(ValueError):
      self.engine.reconcile_dauth_job_secrets(self.payload)

  def test_lifecycle_rejects_invalid_action_and_pointer_before_http(self):
    """Malformed mutation requests must not reach the external service."""
    for action, operation, pointer in [('unknown', {}, {}), ('prepare', None, {}),
                                       ('commit', {}, None), ('delete', {}, [])]:
      with self.subTest(action=action, pointer=pointer):
        self.post.reset_mock()
        with self.assertRaises(ValueError):
          self.engine.reconcile_dauth_job_secrets(dict(job_id='7', action=action, operation=operation, pointer=pointer))
        self.post.assert_not_called()


if __name__ == '__main__':
  unittest.main()
