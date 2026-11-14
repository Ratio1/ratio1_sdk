"""R1FS get_pickle loads plain data only: what add_pickle stores for its callers loads, any object is refused unrun."""
# Paths of the uploads, downloads and marker files.
import os
# The control load, with the plain pickle loader.
import pickle
# Each test's files live in a temporary folder.
import tempfile
# The test runner.
import unittest
# New CIDs and unique engine names.
from uuid import uuid4

# The oracle-sync median comes from numpy, and a numpy value is the type the loader must refuse.
import numpy

# The logger the signing engine needs.
from ratio1 import Logger
# A real block engine signs the oracle-sync tables.
from ratio1.bc import DefaultBlockEngine
# The R1FS engine whose add_pickle and get_pickle are tested.
from ratio1.ipfs.r1fs import R1FSEngine


class _WritesMarker:
  """An object whose unpickling creates a file: what a crafted pickle in R1FS could hold."""

  def __init__(self, path):
    """
    Remember the file the unpickling would create.

    Parameters
    ----------
    path : str
      The marker file.

    Returns
    -------
    None

    Examples
    --------
    >>> _WritesMarker('/tmp/marker').path
    '/tmp/marker'
    """
    # The file the unpickling creates.
    self.path = path

  def __reduce__(self):
    """
    Tell pickle to rebuild this object by calling open(path, 'w'), which creates the marker file.

    Returns
    -------
    tuple
      (open, (path, 'w')): a plain pickle.load calls it and the file appears.

    Examples
    --------
    >>> pickle.loads(pickle.dumps(_WritesMarker('/tmp/marker'))).close()  # creates /tmp/marker
    """
    # The pickle names _io.open and its arguments; loading it calls open(path, 'w').
    return (open, (self.path, 'w'))


class R1FSPlainPickleTests(unittest.TestCase):
  """get_pickle builds plain data only; add_pickle's real writer and get_pickle's real reader are used."""

  def setUp(self):
    """An R1FS engine whose add_file / get_file keep files in a dict, and one block engine to sign payloads."""
    # Uploads, downloads, the marker file and the block engine's key all live in one temporary folder.
    tmp = tempfile.TemporaryDirectory()
    # Removed after the test.
    self.addCleanup(tmp.cleanup)
    # Its path.
    self.tmp = tmp.name
    # The file a crafted object would create when loaded.
    self.marker = os.path.join(self.tmp, 'marker')
    # The engine without _build: no IPFS, only what add_pickle and get_pickle read.
    self.engine = engine = object.__new__(R1FSEngine)
    # get_pickle requires a started R1FS.
    engine._R1FSEngine__ipfs_started = True
    # add_pickle writes its file in the uploads folder.
    engine._R1FSEngine__uploads_dir = os.path.join(self.tmp, 'uploads')
    # Made as _build makes it.
    os.makedirs(engine._R1FSEngine__uploads_dir)
    # CID -> (stored name, plaintext bytes), as add_file would store them and get_file restore them.
    engine.stored = {}
    # Red lines the engine logs.
    engine.logged = []
    # Every P line is recorded.
    engine.P = lambda message, *args, **kwargs: engine.logged.append(message)
    # Debug lines are dropped.
    engine.Pd = lambda *args, **kwargs: None

    def add_file(file_path, **kwargs):
      """
      Keep the file add_pickle wrote, under a new CID, as R1FS would.

      Parameters
      ----------
      file_path : str
        The pickle file add_pickle wrote.
      **kwargs
        secret, nonce, show_logs and raise_on_error, not used here.

      Returns
      -------
      str
        The new CID.

      Examples
      --------
      >>> cid = add_file(file_path='/tmp/r1fs_x.pkl')
      """
      # Read the bytes add_pickle wrote; it removes its file afterwards.
      with open(file_path, 'rb') as fhandle:
        # The whole pickle.
        content = fhandle.read()
      # A new CID for every stored file.
      cid = 'Qm' + uuid4().hex
      # Kept under its stored name.
      engine.stored[cid] = (os.path.basename(file_path), content)
      # The CID add_pickle returns to its caller.
      return cid

    def get_file(cid, **kwargs):
      """
      Restore a stored file under downloads/<cid>/<stored name>, as get_file does after decrypting it.

      Parameters
      ----------
      cid : str
        The CID add_file returned.
      **kwargs
        The other get_file arguments, not used here.

      Returns
      -------
      str
        The absolute path of the restored file.

      Examples
      --------
      >>> path = get_file(cid)
      """
      # The stored name and bytes.
      name, content = engine.stored[cid]
      # A folder per CID, as the real get_file makes.
      folder = os.path.join(self.tmp, 'downloads', cid)
      # It may exist from an earlier read of the same CID.
      os.makedirs(folder, exist_ok=True)
      # The restored file's path.
      path = os.path.join(folder, name)
      # The decrypted plaintext get_pickle then loads.
      with open(path, 'wb') as fhandle:
        # Written as get_file writes the plaintext.
        fhandle.write(content)
      # get_pickle opens this path.
      return path

    # add_pickle stores through the fake add_file.
    engine.add_file = add_file
    # get_pickle reads through the fake get_file.
    engine.get_file = get_file
    # A real block engine signs the oracle-sync tables, so they carry the real signature fields.
    self.bc = DefaultBlockEngine(
      name='oracle' + uuid4().hex,
      log=Logger(lib_name='oracle', base_folder=self.tmp, app_folder='oracle', silent=True),
      config={'PEM_FILE': 'oracle.pem'},
      verbosity=0,
    )

  def _signed(self, data, *dropped):
    """
    Sign a dict as oracle sync does (add_data, digest), then drop the keys it drops before sending.

    Parameters
    ----------
    data : dict
      The dict to sign; it gains the signature fields.
    *dropped : str
      Keys signed but not sent (oracle sync drops EPOCH, NODE and the compiled table).

    Returns
    -------
    dict
      The dict as oracle sync stores it in R1FS.

    Examples
    --------
    >>> self._signed({'VALUE': 255, 'EPOCH': 41, 'NODE': 'addr'}, 'EPOCH', 'NODE')['VALUE']
    255
    """
    # The signature fields (EE_SIGN, EE_SENDER, EE_HASH, the ETH fields and the canon version) are added to data.
    self.bc.sign(data, add_data=True, use_digest=True)
    # Signed but not sent.
    for key in dropped:
      # Removed as oracle sync removes it.
      data.pop(key)
    # The dict as stored.
    return data

  def test_every_caller_payload_round_trips(self):
    """Each shape add_pickle stores for its callers, and every plain type, comes back equal from get_pickle."""
    # The table keys: node addresses.
    nodes = [self.bc.address, '0xai_' + 'A' * 44, '0xai_' + 'B' * 44]
    # The median as oracle sync computes it on this interpreter: round() of a numpy median is a plain int.
    median = round(numpy.median([200, 201, 255]))
    # One payload per shape that add_pickle stores.
    payloads = {
      # Oracle sync: the local table (S2) and the agreed availability table of an epoch, node -> 0..255.
      'availability table': {node: value for node, value in zip(nodes, (255, 0, 137))},
      # Oracle sync: the median table (S4), node -> signed VALUE, with EPOCH and NODE dropped after signing.
      'median table': {node: self._signed({'VALUE': median, 'EPOCH': 41, 'NODE': node}, 'EPOCH', 'NODE')
                       for node in nodes},
      # Oracle sync: the agreement signatures of an epoch, oracle -> signature fields of the compiled table.
      'agreement signatures': {nodes[0]: self._signed({'COMPILED_AGREED_MEDIAN_TABLE': {nodes[0]: 255},
                                                       'EPOCH': 41}, 'EPOCH', 'COMPILED_AGREED_MEDIAN_TABLE')},
      # Document embedding (written by add_pickle until it moves to JSON): the documents and their context.
      'documents': {'DOCUMENTS': ['first document', 'second document'], 'CONTEXT_ID': 'context-1'},
      # The R1FS API's add_pickle endpoint: a JSON request body.
      'json body': {'a': [1, 2.5, 'x', None, True, {'b': False}]},
      # Every type the loader builds.
      'plain types': {'none': None, 'bool': True, 'int': 2 ** 70, 'float': -1.5, 'str': 'text', 'bytes': b'\x00',
                      'list': [1], 'tuple': (1, 'a'), 'dict': {1: 2}, 'set': {1, 2}, 'frozenset': frozenset([3])},
    }
    # Each shape on its own.
    for name, payload in payloads.items():
      # A failure names the shape.
      with self.subTest(payload=name):
        # Stored through the real add_pickle ...
        cid = self.engine.add_pickle(payload, show_logs=False)
        # ... and read back through the real get_pickle.
        loaded = self.engine.get_pickle(cid, show_logs=False)
        # Equal values.
        self.assertEqual(loaded, payload)
        # Same value types too (an int stays an int, a tuple a tuple).
        self.assertEqual(repr(loaded), repr(payload))
    # Nothing was refused.
    self.assertEqual(self.engine.logged, [])

  def test_object_is_refused_and_nothing_of_it_runs(self):
    """A file holding an object is refused with a clear error, and the call the object asks for never runs."""
    # The crafted file, stored through the real add_pickle (pickling it runs nothing).
    cid = self.engine.add_pickle({'LOCAL_TABLE': _WritesMarker(self.marker)}, show_logs=False)
    # Without raise_on_error: None ...
    self.assertIsNone(self.engine.get_pickle(cid))
    # ... and one red line ...
    self.assertEqual(len(self.engine.logged), 1)
    # ... that names what the file asked for.
    self.assertIn('R1FS pickle refused: it names _io.open; only plain data is loaded', self.engine.logged[0])
    # With raise_on_error: the same refusal as a RuntimeError.
    with self.assertRaisesRegex(RuntimeError, 'R1FS pickle refused: it names _io.open'):
      # The same CID again.
      self.engine.get_pickle(cid, raise_on_error=True, show_logs=False)
    # Nothing of the object ran: the marker file was never created.
    self.assertFalse(os.path.exists(self.marker))
    # Control: the same stored bytes under a plain pickle load do create it, so the payload above was live.
    pickle.loads(self.engine.stored[cid][1])['LOCAL_TABLE'].close()
    # The control created the marker.
    self.assertTrue(os.path.exists(self.marker))

  def test_numpy_value_is_refused(self):
    """A numpy value is not plain data: a table holding one is refused, so writers must store Python numbers."""
    # One availability value as a numpy integer instead of an int.
    cid = self.engine.add_pickle({'0xai_node': numpy.int64(255)}, show_logs=False)
    # Refused by the class the file names, before anything is built.
    with self.assertRaisesRegex(RuntimeError, 'R1FS pickle refused: it names numpy'):
      # Read with raise_on_error, so the refusal is the exception.
      self.engine.get_pickle(cid, raise_on_error=True, show_logs=False)


if __name__ == '__main__':
  # Run this file alone.
  unittest.main()
