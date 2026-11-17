"""Offline checks of the per-peer key cache of the encryption paths (`BaseBCEllipticCurveEngine._shared_key`)."""
# Each test's engines keep their key files and logs in a temporary folder.
import tempfile
# The test runner.
import unittest
# A random suffix keeps the engines of different tests apart (engines are singletons per name).
from uuid import uuid4

# The logger every block engine needs.
from ratio1 import Logger
# The default info text and the engine the nodes use.
from ratio1.bc import BCct, DefaultBlockEngine
# The class that holds the cached helper and its cache counters.
from ratio1.bc.ec import BaseBCEllipticCurveEngine

# A second HKDF info text, to show that it gets its own key.
OTHER_INFO = 'another handshake'


def _engine(cache, name):
  """
  Build a block engine with its own new key, under a unique name.

  Parameters
  ----------
  cache : str
    Folder for the engine's logger and key file.
  name : str
    Name prefix; a random suffix keeps engines of different tests apart (engines are singletons per name).

  Returns
  -------
  DefaultBlockEngine
    The engine, with a new secp256k1 key.

  Examples
  --------
  >>> node = _engine(tempfile.mkdtemp(), 'node')
  """
  # A new key file is created in the engine's own folder of `cache`.
  return DefaultBlockEngine(
    name=name + uuid4().hex,
    log=Logger(lib_name=name, base_folder=cache, app_folder=name, silent=True),
    config={'PEM_FILE': name + '.pem'},
    verbosity=0,
  )


def _uncached(engine, peer_address, info=BCct.DEFAULT_INFO):
  """
  Derive the shared key the way every message did before the cache.

  Parameters
  ----------
  engine : DefaultBlockEngine
    The engine whose current private key is used.
  peer_address : str
    The peer's address.
  info : str, optional
    The HKDF info text. Default BCct.DEFAULT_INFO.

  Returns
  -------
  bytes
    The 32-byte key: peer address decoded, ECDH with the engine's key, HKDF.

  Examples
  --------
  >>> _uncached(node, peer.address) == node._shared_key(node.address, peer.address, BCct.DEFAULT_INFO, False)
  True
  """
  # The two calls each message made before: decode the address, then ECDH and HKDF.
  return engine._BaseBCEllipticCurveEngine__derive_shared_key(engine._address_to_pk(peer_address), info=info)


class SharedKeyCacheTests(unittest.TestCase):
  """The cache returns the uncached key, once per (engine, own address, peer, info), and never another peer's."""

  def setUp(self):
    """Three engines with their own keys, and an empty cache so each test counts its own derivations."""
    # A folder of its own for the engines' key files and logs.
    self.tmp = tempfile.TemporaryDirectory()
    # Removed after the test.
    self.addCleanup(self.tmp.cleanup)
    # The node under test and two peers.
    self.node, self.peer, self.other = (_engine(self.tmp.name, name) for name in ('node', 'peer', 'other'))
    # The cache is shared by every engine of the process: start each test from zero entries and counts.
    BaseBCEllipticCurveEngine._shared_key.cache_clear()

  def test_cached_key_is_the_uncached_key(self):
    """For two peers and two info texts the cached key is byte for byte the uncached one, also on a hit."""
    # Every peer with every info text.
    for peer in (self.peer, self.other):
      # Both info texts for this peer.
      for info in (BCct.DEFAULT_INFO, OTHER_INFO):
        # First call derives, second one is served from the cache: both equal the old per-message derivation.
        keys = [self.node._shared_key(self.node.address, peer.address, info, False) for _ in range(2)]
        # Same bytes on the miss and on the hit.
        self.assertEqual(keys, [_uncached(self.node, peer.address, info)] * 2)
    # The cache counters after the loop.
    info = BaseBCEllipticCurveEngine._shared_key.cache_info()
    # 4 derivations (2 peers x 2 info texts) and 4 hits.
    self.assertEqual((info.misses, info.hits), (4, 4))

  def test_many_messages_cost_one_derivation_per_peer_and_side(self):
    """100 rounds of a two-receiver package and a single-receiver message, all decrypted, derive 4 keys in all."""
    # 100 rounds of messages in both layouts.
    for i in range(100):
      # A different text per round.
      text = 'message {}'.format(i)
      # One package for both peers: the node derives one key per receiver, on the first message only.
      package = self.node.encrypt_for_multi(text, [self.peer.address, self.other.address])
      # Each peer derives its key with the node once and then reads it from the cache.
      self.assertEqual([p.decrypt_for_multi(package, self.node.address) for p in (self.peer, self.other)], [text] * 2)
      # The single-receiver layout uses the same entries.
      self.assertEqual(self.peer._decrypt(self.node._encrypt(text, self.peer.address), self.node.address), text)
    # The cache counters after the 100 rounds.
    info = BaseBCEllipticCurveEngine._shared_key.cache_info()
    # node->peer, node->other, peer<-node, other<-node: 4 derivations for 600 key uses (6 per round).
    self.assertEqual((info.misses, info.hits), (4, 596))

  def test_different_peer_info_or_own_key_is_a_different_entry(self):
    """Another peer, another info text or a rotated own key each miss and get their own correct key."""
    # The node's entry with the peer.
    with_peer = self.node._shared_key(self.node.address, self.peer.address, BCct.DEFAULT_INFO, False)
    # The node's entry with the other peer.
    with_other = self.node._shared_key(self.node.address, self.other.address, BCct.DEFAULT_INFO, False)
    # The node's entry with the peer under the other info text.
    other_info = self.node._shared_key(self.node.address, self.peer.address, OTHER_INFO, False)
    # Three different keys: no peer or info text gets another one's key.
    self.assertEqual(len({with_peer, with_other, other_info}), 3)
    # Three entries in the cache.
    self.assertEqual(BaseBCEllipticCurveEngine._shared_key.cache_info().currsize, 3)
    # A message the node sent with its old key, which the peer has not read yet.
    old_message = self.node._encrypt('before', self.peer.address)
    # The node's address before the rotation.
    old_address = self.node.address
    # The node's key is replaced: same engine object, new private key and address.
    self.node.rotate_private_key()
    # The rotation gave a new address.
    self.assertNotEqual(self.node.address, old_address)
    # The new own address misses and derives with the new private key.
    rotated = self.node._shared_key(self.node.address, self.peer.address, BCct.DEFAULT_INFO, False)
    # It is the key the new private key gives ...
    self.assertEqual(rotated, _uncached(self.node, self.peer.address))
    # ... not the cached key of the old one.
    self.assertNotEqual(rotated, with_peer)
    # The peer reads new messages under the node's new address ...
    self.assertEqual(self.peer._decrypt(self.node._encrypt('after', self.peer.address), self.node.address), 'after')
    # ... and the message sent before the rotation under the old one.
    self.assertEqual(self.peer._decrypt(old_message, old_address), 'before')

  def test_invalid_address_raises_or_returns_none_and_stores_nothing(self):
    """An address that is not a public key raises on encrypt, gives None on decrypt, and leaves no entry."""
    # Valid base64 of the right length, but not a point on the curve.
    bad = '0xai_' + 'A' * 44
    # Encrypting to it fails loudly, as before the cache.
    with self.assertRaises(ValueError):
      # The address is decoded inside _shared_key.
      self.node._encrypt('x', bad)
    # A message claimed to come from it is not decrypted.
    self.assertIsNone(self.peer.decrypt(self.node.encrypt('x', self.peer.address), bad))
    # Only the node->peer entry exists: a failed derivation is not cached, so the next use checks the address again.
    self.assertEqual(BaseBCEllipticCurveEngine._shared_key.cache_info().currsize, 1)


if __name__ == '__main__':
  # Run this file alone.
  unittest.main()
