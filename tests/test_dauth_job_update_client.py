"""Verify the SDK-owned dAuth update transport without network access."""
import copy
import traceback
import unittest
from unittest import mock

import requests

from ratio1.bc.base import BaseBlockEngine
from test_dauth_job_secret_client import _DauthClientHarness, REQUEST_TIME, REQUEST_NONCE


class _UpdateClientHarness(_DauthClientHarness):
  """
  Bind the update API to the existing isolated dAuth engine fixture.

  Notes
  -----
  Signature and oracle checks use fixture results; HTTP is always mocked.
  """
  request_dauth_job_update = BaseBlockEngine.request_dauth_job_update


class TestDauthJobUpdateClient(unittest.TestCase):
  """
  Cover request integrity, response authentication and bounded retry behavior.

  Notes
  -----
  Deployment receipt semantics remain covered by Edge integration tests.
  """
  def setUp(self):
    """Prepare a signed-response fixture and mock the clock and HTTP boundary."""
    self.engine = _UpdateClientHarness()
    self.payload = {'action': 'stage', 'wallet_request': {'secret': 'private-token', 'EE_ETH_SIGN': 'wallet-signature'}}
    self.result = {'status': 'success', 'nonce': REQUEST_NONCE, 'receipt': {'operation_id': 'op'},
                   'EE_SIGN': 'server-signature', 'EE_SENDER': 'server'}
    self.response = mock.Mock(status_code=200)
    self.response.json.return_value = {'result': self.result}
    clock = mock.patch('ratio1.bc.base.time', return_value=REQUEST_TIME)
    self.clock = clock.start()
    self.addCleanup(clock.stop)
    post = mock.patch('ratio1.bc.base.requests.post', return_value=self.response)
    self.post = post.start()
    self.addCleanup(post.stop)

  def test_signs_all_actions_and_checks_selected_network_without_mutating_payload(self):
    """Keep operation data intact and authenticate each supported transport action."""
    self.engine.default_dauth_url = 'https://dauth.example/proxy/get_auth_data'
    for action in ('stage', 'commit', 'rollback'):
      with self.subTest(action=action):
        self.payload['action'] = action
        original = copy.deepcopy(self.payload)
        result = self.engine.request_dauth_job_update(self.payload, network='testnet', request_timeout=(2, 5))
        self.assertEqual(result, self.result)
        self.assertEqual(self.payload, original)
        self.assertEqual(self.engine.signed_payloads[-1], {**original, 'nonce': REQUEST_NONCE})
        self.assertEqual(self.engine.network_data_calls[-1], 'testnet')
        self.assertEqual(self.engine.oracle_checks[-1], ('0xserver', 'testnet'))
        self.assertEqual(self.engine.verification_calls[-1][1], {'log_hash_sign_fails': False})
        self.assertEqual(self.post.call_args.args[0], 'https://dauth.example/proxy/stage_job_update')
        self.assertEqual(self.post.call_args.kwargs['timeout'], (2, 5))
    self.assertEqual(self.engine.log_messages, [])

  def test_transport_retry_uses_fresh_signing_of_identical_frozen_operation(self):
    """Retry once without carrying authentication or mutable nested data forward."""
    self.clock.side_effect = [REQUEST_TIME, REQUEST_TIME + 1]
    self.result['nonce'] = hex((REQUEST_TIME + 1) * 1000)
    self.post.side_effect = [requests.Timeout('private-token'), self.response]
    original = copy.deepcopy(self.payload)
    self.engine.request_dauth_job_update(self.payload)
    self.assertEqual(self.post.call_count, 2)
    first = self.post.call_args_list[0].kwargs['json']['body']
    second = self.post.call_args_list[1].kwargs['json']['body']
    self.assertNotEqual(first['nonce'], second['nonce'])
    self.assertNotIn('EE_SIGN', self.engine.signed_payloads[1])
    self.assertEqual(first['wallet_request'], second['wallet_request'])
    first['wallet_request']['secret'] = 'changed-after-send'
    self.assertEqual(second['wallet_request'], original['wallet_request'])
    self.assertEqual(self.payload, original)
    self.assertEqual(self.engine.network_data_calls, ['mainnet'])
    self.assertEqual(self.post.call_args.kwargs['timeout'], (10, 60))

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
    ]
    for name, status, data, valid, oracle in cases:
      with self.subTest(case=name):
        self.post.reset_mock()
        self.response.status_code = status
        self.response.json.return_value = data
        self.engine.verification_valid = valid
        self.engine.dauth_oracle = oracle
        with self.assertRaises((ValueError, RuntimeError)) as caught:
          self.engine.request_dauth_job_update(self.payload)
        self.assertEqual(self.post.call_count, 1)
        self.assertNotIn('private-token', str(caught.exception) + str(self.engine.log_messages))
    self.response.json.assert_called()

  def test_dependency_failures_remain_credential_safe_and_retries_are_bounded(self):
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
          self.engine.request_dauth_job_update(self.payload)
        self.assertEqual(failed.call_count, 2 if dependency == 'post' else 1)
        formatted = ''.join(traceback.format_exception(type(caught.exception), caught.exception, caught.exception.__traceback__))
        self.assertNotIn('private-token', formatted + str(self.engine.log_messages))
        self.assertTrue(caught.exception.__suppress_context__)
    with self.assertRaises(ValueError):
      self.engine.request_dauth_job_update(None)


if __name__ == '__main__':
  unittest.main()
