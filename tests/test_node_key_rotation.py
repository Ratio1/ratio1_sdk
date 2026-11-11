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
    self.assertEqual(len(pem_files), 2)
    self.assertTrue(any('.revoked-' in fn for fn in pem_files))

  def test_announcement_is_signed_by_the_new_key(self):
    announcement = self.node.rotate_private_key()
    answer = {'old_node': announcement['EE_SENDER'], 'new_node': self.node.address, 'confirmed': True}
    self.server.sign(answer)
    with patch('ratio1.bc.base.requests.post', return_value=_response(answer)) as post:
      result = self.node.dauth_announce_node_key(announcement)
    self.assertTrue(result['confirmed'])
    url, body = post.call_args.args[0], post.call_args.kwargs['json']['body']
    self.assertTrue(url.endswith('/announce_node_key'))
    self.assertEqual(body['EE_SENDER'], self.node.address)
    self.assertEqual(body[dAuth.DAUTH_KEY_ROTATION], announcement)
    self.assertTrue(self.server.verify(dict(body)).valid)

  def test_unsigned_or_refused_answer_raises(self):
    announcement = self.node.rotate_private_key()
    refused = {'error': 'Only a revoked node key can announce a new key.'}
    self.server.sign(refused)
    for answer, error in (({'new_node': 'x', 'confirmed': True}, ValueError), (refused, RuntimeError)):
      with self.subTest(error=error.__name__), patch('ratio1.bc.base.requests.post', return_value=_response(answer)):
        with self.assertRaises(error):
          self.node.dauth_announce_node_key(announcement)


if __name__ == '__main__':
  unittest.main()
