"""Verify the SDK-owned dAuth reconciliation transport without network access."""
import copy
import traceback
import unittest
from unittest import mock

import requests

from ratio1.bc.base import BaseBlockEngine
# The client's error type of the one named refusal.
from ratio1.bc.base import DauthSecretRecordTooLarge
# The name of the reason field and its one code.
from ratio1.const.base import dAuth
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
    """Reject invalid envelopes without retrying or exposing their body contents."""
    # One answer per way an answer can be wrong: (name, HTTP status, body, signature valid, signer registered).
    cases = [
      # The service answers an error status.
      ('http', 503, {'result': self.result}, True, True),
      # The body is not an object.
      ('outer shape', 200, [], True, True),
      # The result is not an object.
      ('result shape', 200, {'result': []}, True, True),
      # The signature of the answer does not verify.
      ('signature', 200, {'result': self.result}, False, True),
      # The signer is not a registered dAuth oracle.
      ('oracle', 200, {'result': self.result}, True, False),
      # The answer carries the nonce of another request.
      ('nonce', 200, {'result': {**self.result, 'nonce': 'wrong'}}, True, True),
      # A signed refusal by its status.
      ('status', 200, {'result': {**self.result, 'status': 'fail'}}, True, True),
      # A signed refusal by its error text, which holds the value that must not show up anywhere.
      ('error', 200, {'result': {**self.result, 'error': 'private-token'}}, True, True),
      # A success for another job.
      ('job', 200, {'result': {**self.result, 'job_id': '8'}}, True, True),
      # A success without a CID.
      ('cid', 200, {'result': {**self.result, 'pipeline_cid': ''}}, True, True),
      # A success whose configs are for other nodes than the request named.
      ('nodes', 200, {'result': {**self.result, 'pipeline_configs': {'other': {}}}}, True, True),
      # A success with a config that is not an object.
      ('config', 200, {'result': {**self.result, 'pipeline_configs': {'worker': []}}}, True, True),
    ]
    # Every case is sent once and must be refused.
    for name, status, data, valid, oracle in cases:
      # Each case reports on its own.
      with self.subTest(case=name):
        # Count the posts of this case only.
        self.post.reset_mock()
        # The HTTP status the service answers.
        self.response.status_code = status
        # The body it answers.
        self.response.json.return_value = data
        # Whether the answer's signature verifies.
        self.engine.verification_valid = valid
        # Whether the signer is a registered dAuth oracle.
        self.engine.dauth_oracle = oracle
        # The client raises for every one of them.
        with self.assertRaises((ValueError, RuntimeError)) as caught:
          # The request whose answer is wrong.
          self.engine.reconcile_dauth_job_secrets(self.payload)
        # One post: nothing is sent again.
        self.assertEqual(self.post.call_count, 1)
        # Neither the raised error nor any log line carries the value, the refusal's own error text included.
        self.assertNotIn('private-token', str(caught.exception) + str(self.engine.log_messages))
    # The body was read: the cases did not all end at the status check.
    self.response.json.assert_called()

  def test_signed_refusal_still_raises_and_names_the_dauth_server_in_red(self):
    """A refusal says which dAuth server refused which action; its error text stays out of the log."""
    # Every line the client logs, with its colour.
    logs = []
    # The engine's log call is replaced so that whole lines can be compared.
    self.engine.P = lambda message, color=None, **kwargs: logs.append((message, color))
    # A correctly signed answer that refuses, with an error text that must not reach the log.
    self.result.update(status='error', error='private-token')
    # The refusal of a job update raises.
    with self.assertRaises(RuntimeError):
      # The job update that is refused.
      self.engine.reconcile_dauth_job_secrets(self.payload)
    # The same refusal for a lifecycle request with the action "revoke".
    self.lifecycle('revoke')
    # It raises too.
    with self.assertRaises(RuntimeError):
      # The lifecycle request that is refused.
      self.engine.reconcile_dauth_job_secrets(self.payload)
    # One red line per refusal, naming the server and the action and ending there: no error text.
    self.assertEqual(logs, [('dAuth server dauth-a refused secret reconciliation (job update).', 'r'),
                            ('dAuth server dauth-a refused secret reconciliation (revoke).', 'r')])

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

  def refuse(self, **fields):
    """
    Make the next answer a signed refusal of a "prepare", as a dAuth server sends it.

    Parameters
    ----------
    **fields
      Fields the refusal carries beside the request's nonce, the fixed error text and the server's own
      fields; for example ``reason``. A field given here replaces the one of that name.

    Returns
    -------
    None

    Examples
    --------
    >>> self.refuse(reason='record_too_large')
    >>> self.result['error'], self.result['reason']
    ('dAuth secret reconciliation failed', 'record_too_large')
    """
    # A lifecycle request for the action "prepare".
    self.lifecycle('prepare')
    # A refusal has no result fields: the nonce, the one error text of every refusal, the server's alias and signature.
    self.result = {'nonce': REQUEST_NONCE, 'error': 'dAuth secret reconciliation failed',
                   'server_alias': 'dauth-a', 'EE_SIGN': 'server-signature', 'EE_SENDER': 'server', **fields}
    # The answer the mocked HTTP call returns.
    self.response.json.return_value = {'result': self.result}

  def test_a_refusal_for_the_size_of_the_secret_record_raises_a_value_error_with_the_clients_own_text(self):
    """A signed refusal whose reason code is "record_too_large" raises the client's own error type, a ValueError,
    with the client's own fixed text, which names both copies a server refuses for size (the new revision's and
    the current one's kept for a rollback); before, it raised the RuntimeError of every refusal."""
    # The wire values are these two words.
    self.assertEqual((dAuth.DAUTH_REASON, dAuth.DAUTH_REASON_RECORD_TOO_LARGE), ('reason', 'record_too_large'))
    # The refusal of a dAuth server whose chain store refused the job's secret record for its size.
    self.refuse(reason='record_too_large')
    # The type of its own, so that a caller can end the request's work at once (a RuntimeError, or a ValueError of
    # another type, would not be caught here).
    with self.assertRaises(DauthSecretRecordTooLarge) as caught:
      # The preparation that is refused.
      self.engine.reconcile_dauth_job_secrets(self.payload)
    # Still a ValueError, so every handler of the client's ValueError (final for the request) handles it as before.
    self.assertIsInstance(caught.exception, ValueError)
    # The client's own text, whole: true of either copy.
    self.assertEqual(str(caught.exception),
                     "The deployment's secret record is larger than the store accepts: the new revision, or the "
                     "current one kept for a rollback, has too many nodes or too large configurations.")
    # One request, and the red line of any refusal: the server and the action, nothing else.
    self.post.assert_called_once()
    # The line as the client logged it.
    self.assertEqual(self.engine.log_messages, ['dAuth server dauth-a refused secret reconciliation (prepare).'])

  def test_the_size_reason_counts_only_in_an_answer_that_passed_signature_signer_and_nonce(self):
    """An answer that carries the size reason but fails the signature, the signer or the nonce check is refused
    by that check, with that check's text: the reason of an answer that is not authenticated is never read."""
    # Per check: what makes it fail (engine state or a field of the answer) and the text it raises.
    cases = [('signature', {'verification_valid': False}, {}, 'Invalid dAuth reconciliation response signature.'),
             ('signer', {'dauth_oracle': False}, {}, 'Unauthorized dAuth reconciliation response signer.'),
             ('nonce', {}, {'nonce': 'wrong'}, 'dAuth reconciliation response nonce mismatch.')]
    # Each check in turn.
    for name, state, fields, text in cases:
      # Each reports on its own.
      with self.subTest(check=name):
        # A fresh engine whose checks pass.
        self.engine = _UpdateClientHarness()
        # What makes this check fail, when it is a state of the engine.
        vars(self.engine).update(state)
        # The refusal with the size reason, and the failing field when it is one of the answer.
        self.refuse(reason='record_too_large', **fields)
        # Every one of these checks raises a ValueError too, so the text tells them apart.
        with self.assertRaises(ValueError) as caught:
          # The preparation whose answer is not authenticated.
          self.engine.reconcile_dauth_job_secrets(self.payload)
        # The failing check's own text, not the size text.
        self.assertEqual(str(caught.exception), text)

  def test_any_other_reason_or_none_is_the_refusal_of_before(self):
    """A refusal with no reason, an unknown one, the code in another case or type, or the code in the error text
    raises the same RuntimeError as before: the set of reasons is closed, and nothing is read from the text."""
    # A refusal without the field, as a dAuth server of an earlier release sends it, then other values of it.
    refusals = [{}, {'reason': None}, {'reason': ''}, {'reason': 'record_too_deep'}, {'reason': 'RECORD_TOO_LARGE'},
                {'reason': 'record_too_large '}, {'reason': ['record_too_large']}, {'reason': True},
                {'reason': {'code': 'record_too_large'}}, {'error': 'record_too_large'}]
    # Each refusal in turn.
    for fields in refusals:
      # Each reports on its own.
      with self.subTest(fields=fields):
        # The refusal.
        self.refuse(**fields)
        # Count the requests of this case only.
        self.post.reset_mock()
        # A RuntimeError, as every refusal raised before (a ValueError would not be caught here).
        with self.assertRaises(RuntimeError) as caught:
          # The preparation that is refused.
          self.engine.reconcile_dauth_job_secrets(self.payload)
        # The fixed text of a refusal, and one request.
        self.assertEqual((str(caught.exception), self.post.call_count), ('dAuth rejected secret reconciliation.', 1))

  def test_a_success_that_carries_the_reason_is_still_a_success(self):
    """The reason is read only in a refusal: a successful answer that happens to carry it is returned as it is."""
    # A successful "prepare".
    self.lifecycle('prepare')
    # With the field of a refusal in it.
    self.result['reason'] = 'record_too_large'
    # Returned, not raised.
    self.assertEqual(self.engine.reconcile_dauth_job_secrets(self.payload), self.result)

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
