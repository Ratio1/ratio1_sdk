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
    # A dAuth server adds its alias to every answer before signing it.
    self.result = {'status': 'success', 'nonce': REQUEST_NONCE, 'job_id': '7',
                   'pipeline_cid': 'new-cid', 'pipeline_configs': {'worker': {}},
                   'server_alias': 'dauth-a', 'EE_SIGN': 'server-signature', 'EE_SENDER': 'server'}
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
    """An invalid envelope is rejected in one request; a value its body carries never reaches the raised error,
    and reaches the log only as the `error` of an answer whose signature, signer and nonce all passed."""
    # Name, HTTP status, JSON body, whether the signature verifies, whether the signer is a registered dAuth oracle.
    cases = [
      ('http', 503, {'result': self.result}, True, True),
      ('outer shape', 200, [], True, True),
      ('result shape', 200, {'result': []}, True, True),
      # A signature that does not verify: the `error` this answer carries must stay out of the log.
      ('signature', 200, {'result': {**self.result, 'error': 'private-token'}}, False, True),
      # A signer that is not a registered dAuth oracle: its `error` must stay out too.
      ('oracle', 200, {'result': {**self.result, 'error': 'private-token'}}, True, False),
      # The nonce of another request: its `error` must stay out too.
      ('nonce', 200, {'result': {**self.result, 'nonce': 'wrong', 'error': 'private-token'}}, True, True),
      ('status', 200, {'result': {**self.result, 'status': 'fail'}}, True, True),
      ('error', 200, {'result': {**self.result, 'error': 'private-token'}}, True, True),
      ('job', 200, {'result': {**self.result, 'job_id': '8'}}, True, True),
      ('cid', 200, {'result': {**self.result, 'pipeline_cid': ''}}, True, True),
      ('nodes', 200, {'result': {**self.result, 'pipeline_configs': {'other': {}}}}, True, True),
      ('config', 200, {'result': {**self.result, 'pipeline_configs': {'worker': []}}}, True, True),
    ]
    # Every case in turn.
    for name, status, data, valid, oracle in cases:
      # Each case reports on its own.
      with self.subTest(case=name):
        # Count the requests of this case only.
        self.post.reset_mock()
        # Keep the log lines of this case only.
        del self.engine.log_messages[:]
        # The HTTP status of the answer.
        self.response.status_code = status
        # Its JSON body.
        self.response.json.return_value = data
        # Whether its signature verifies.
        self.engine.verification_valid = valid
        # Whether its signer is a registered dAuth oracle.
        self.engine.dauth_oracle = oracle
        # Every case is refused.
        with self.assertRaises((ValueError, RuntimeError)) as caught:
          # The one request of the case.
          self.engine.reconcile_dauth_job_secrets(self.payload)
        # One request, never a second try.
        self.assertEqual(self.post.call_count, 1)
        # The raised error never carries a value from the body.
        self.assertNotIn('private-token', str(caught.exception))
        # The log carries the body's `error` for the authenticated refusal only: with a bad signature, an
        # unregistered signer or another request's nonce the same text is not logged.
        self.assertEqual('private-token' in str(self.engine.log_messages), name == 'error')
    # The JSON body was read at least once over the cases.
    self.response.json.assert_called()

  def test_signed_refusal_logs_the_servers_error_escaped_and_cut_to_200_characters(self):
    """A signed refusal is logged in red with the server, the action and the server's `error` as its repr cut to
    200 characters, whatever its length, characters or type; the raised error keeps its fixed text."""
    # The red lines of the client, with their colour.
    logs = []
    # The engine's log call, recorded.
    self.engine.P = lambda message, color=None, **kwargs: logs.append((message, color))
    # The fixed start of the line for an old-style job update and for a lifecycle "revoke".
    update, revoke = ('dAuth server dauth-a refused secret reconciliation ({}): '.format(a) for a in ('job update', 'revoke'))
    # A server that names the check that failed.
    self.result.update(status='error', error='Secret bundle is bound to another pipeline.')
    # The caller still gets the fixed text, without the server's.
    with self.assertRaisesRegex(RuntimeError, r'^dAuth rejected secret reconciliation\.$'):
      # The refused job update.
      self.engine.reconcile_dauth_job_secrets(self.payload)
    # The line names the check, in quotes (a repr).
    self.assertEqual(logs.pop(), (update + "'Secret bundle is bound to another pipeline.'", 'r'))
    # The next requests are lifecycle "revoke" requests.
    self.lifecycle('revoke')
    # A text holding a newline and a forged log line, then 5,000 more characters.
    self.result['error'] = 'no plan\n[forged] oracle line' + 'x' * 5000
    # Refused again.
    with self.assertRaises(RuntimeError):
      # The refused revoke.
      self.engine.reconcile_dauth_job_secrets(self.payload)
    # The line and its colour.
    line, color = logs.pop()
    # The part after the fixed start: the server's text as logged.
    text = line[len(revoke):]
    # Red, one line (the newline is escaped), and 200 characters of the text's repr however long the text is.
    self.assertEqual((color, line.startswith(revoke), '\n' in line, len(text), text[:30]),
                     ('r', True, False, 200, "'no plan\\n[forged] oracle line"))
    # A server may send any JSON value: a list, and no error at all beside a status that is not "success".
    for error, logged in ((['a', 1], "['a', 1]"), (None, 'None')):
      # Each value reports on its own.
      with self.subTest(error=error):
        # The value the server signs.
        self.result['error'] = error
        # Refused, not a formatting failure.
        with self.assertRaisesRegex(RuntimeError, r'^dAuth rejected secret reconciliation\.$'):
          # The refused revoke.
          self.engine.reconcile_dauth_job_secrets(self.payload)
        # The value is logged as its repr.
        self.assertEqual(logs.pop(), (revoke + logged, 'r'))

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
