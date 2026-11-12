"""Offline checks of node key rotation after dAuth reports the key as revoked."""
import glob
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine
from ratio1.const.base import DAUTH_SUBKEY, dAuth


def _engine(cache, name):
  return DefaultBlockEngine(
    name=name + uuid4().hex,
    log=Logger(lib_name=name, base_folder=cache, app_folder=name, silent=True),
    config={'PEM_FILE': name + '.pem'},
    verbosity=0,
  )


def _response(result):
  return Mock(status_code=200, json=Mock(return_value={'result': result}))


class NodeKeyRotationTests(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.node = _engine(self.tmp.name, 'node')
    self.server = _engine(self.tmp.name, 'server')

  def _auth_response(self, revoked_address):
    result = {DAUTH_SUBKEY: {'error': 'not allowed', dAuth.DAUTH_REVOKED: revoked_address}}
    self.server.sign(result)
    return _response(result)

  def test_revoked_verdict_is_kept_only_from_a_dauth_oracle(self):
    for is_oracle, named, expected in (
      (True, self.node.address, self.server.address),
      (False, self.node.address, None),
      (True, self.server.address, None),
    ):
      with self.subTest(is_oracle=is_oracle, named=named), \
          patch('ratio1.bc.base.requests.post', return_value=self._auth_response(named)), \
          patch.object(self.node, 'web3_is_dauth_oracle', return_value=is_oracle):
        self.node.dauth_autocomplete(dauth_endp='https://dauth.example/get_auth_data', max_tries=1)
        self.assertEqual(self.node.dauth_revoked_by, expected)

  def test_rotation_archives_the_key_and_signs_the_successor_with_the_old_key(self):
    old_address = self.node.address
    announcement = self.node.rotate_private_key()
    self.assertNotEqual(self.node.address, old_address)
    self.assertEqual(announcement['EE_SENDER'], old_address)
    self.assertEqual(announcement['new_node'], self.node.address)
    self.assertEqual(announcement['purpose'], dAuth.DAUTH_KEY_ROTATION_PURPOSE)
    self.assertTrue(self.server.verify(dict(announcement)).valid)
    pem_files = [os.path.basename(fn) for fn in glob.glob(os.path.join(self.tmp.name, 'node', '**', 'node.pem*'), recursive=True)]
    self.assertEqual(sorted(fn.split('.revoked-')[0] for fn in pem_files), ['node.pem', 'node.pem', 'node.pem.rotation.json'])

  def _announce(self, announcement, answer=None, is_oracle=True, echo_nonce=True, env=None):
    """Announce against a fake dAuth that signs `answer`; returns (result, url, body)."""
    def post(url, json, timeout):
      result = dict({'old_node': announcement['EE_SENDER'], 'new_node': self.node.address, 'confirmed': True}
                    if answer is None else answer)
      if echo_nonce:
        result['nonce'] = json['body']['nonce']
      self.server.sign(result)
      return _response(result)
    with patch('ratio1.bc.base.requests.post', side_effect=post) as mocked, \
        patch.object(self.node, 'web3_is_dauth_oracle', return_value=is_oracle), \
        patch.dict(os.environ, env or {}):
      result = self.node.dauth_announce_node_key(announcement)
    return result, mocked.call_args.args[0], mocked.call_args.kwargs['json']['body']

  def test_announcement_is_signed_by_the_new_key(self):
    announcement = self.node.rotate_private_key()
    result, url, body = self._announce(announcement)
    self.assertTrue(result['confirmed'])
    self.assertTrue(url.endswith('/announce_node_key'))
    self.assertEqual(body['EE_SENDER'], self.node.address)
    self.assertEqual(body[dAuth.DAUTH_KEY_ROTATION], announcement)
    self.assertTrue(self.server.verify(dict(body)).valid)

  def test_announcement_goes_to_the_configured_dauth_endpoint(self):
    announcement = self.node.rotate_private_key()
    _, url, _ = self._announce(announcement, env={'EE_DAUTH_URL': 'https://private.example/get_auth_data'})
    self.assertEqual(url, 'https://private.example/announce_node_key')

  def test_rotation_proof_is_verifiable_by_any_engine(self):
    old_address = self.node.address
    announcement = self.node.rotate_private_key()
    _, _, proof = self._announce(announcement)
    self.assertEqual(self.server.verify_node_key_rotation(proof), (old_address, self.node.address))

    forged = {dAuth.DAUTH_KEY_ROTATION: dict(announcement, new_node=self.server.address), 'nonce': '0x1'}
    self.server.sign(forged)
    resigned = {dAuth.DAUTH_KEY_ROTATION: announcement, 'nonce': '0x1'}
    self.server.sign(resigned)
    for bad in (forged, resigned, dict(proof, nonce='0x2'), {'new_node': self.node.address}):
      with self.subTest(bad=sorted(bad)), self.assertRaises(ValueError):
        self.server.verify_node_key_rotation(bad)

  def test_only_a_dauth_oracle_answer_to_this_request_is_accepted(self):
    announcement = self.node.rotate_private_key()
    confirmed = {'old_node': announcement['EE_SENDER'], 'new_node': self.node.address, 'confirmed': True}
    cases = {
      'not a dAuth oracle': (dict(is_oracle=False), ValueError),
      'no request nonce': (dict(echo_nonce=False), ValueError),
      'another old node': (dict(answer=dict(confirmed, old_node=self.server.address)), ValueError),
      'refused': (dict(answer={'error': 'Only a revoked node key can announce a new key.'}), RuntimeError),
    }
    for name, (kwargs, error) in cases.items():
      with self.subTest(name), self.assertRaises(error):
        self._announce(announcement, **kwargs)
    with patch('ratio1.bc.base.requests.post', return_value=_response(confirmed)), self.assertRaises(ValueError):
      self.node.dauth_announce_node_key(announcement)  # unsigned

  def test_interrupted_rotation_keeps_a_usable_key_and_the_announcement(self):
    old_address = self.node.address
    self.assertIsNone(self.node.pending_node_key_announcement())
    with patch('ratio1.bc.base.os.replace', side_effect=OSError('disk full')), self.assertRaises(OSError):
      self.node.rotate_private_key()
    with patch('ratio1.bc.base.shutil.copy2', side_effect=OSError('disk full')), self.assertRaises(OSError):
      self.node.rotate_private_key()
    # the old key is still the active one and no announcement for another key is pending
    self.assertEqual(_engine(self.tmp.name, 'node').address, old_address)
    self.assertIsNone(self.node.pending_node_key_announcement())

    announcement = self.node.rotate_private_key()
    restarted = _engine(self.tmp.name, 'node')
    self.assertEqual(restarted.address, announcement['new_node'])
    self.assertEqual(restarted.pending_node_key_announcement(), announcement)
    restarted.node_key_announcement_done()
    self.assertIsNone(restarted.pending_node_key_announcement())


if __name__ == '__main__':
  unittest.main()
