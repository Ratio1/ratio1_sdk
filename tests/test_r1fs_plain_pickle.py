"""R1FS get_pickle loads plain data only: what add_pickle stores for its callers loads, any object is refused unrun."""
# Paths of the uploads, downloads and marker files.
import os
# The control load, with the plain pickle loader.
import pickle
# Refusal reasons are matched as plain text.
import re
# Memo indexes of the crafted pickles, packed as the opcodes take them.
import struct
# Each test's files live in a temporary folder.
import tempfile
# Refusals are timed: the crafted files must be refused in milliseconds.
import time
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
# The R1FS engine whose add_pickle and get_pickle are tested, and the bounds its loader applies.
from ratio1.ipfs.r1fs import (
  R1FSEngine, _PLAIN_PICKLE_MAX_BYTES, _PLAIN_PICKLE_MAX_DEPTH, _PLAIN_PICKLE_MAX_REUSE,
)


def _nested_lists(levels):
  """
  Build lists nested a given number of levels, each holding only the next one.

  Parameters
  ----------
  levels : int
    How many levels deep: an empty list is 1 level.

  Returns
  -------
  list
    The outermost list.

  Examples
  --------
  >>> _nested_lists(3)
  [[[]]]
  """
  # The innermost level.
  nested = []
  # Each further level wraps the one before.
  for _ in range(levels - 1):
    # One level deeper.
    nested = [nested]
  # The outermost list.
  return nested


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
      # A file that holds None, which oracle sync's reader fetches again.
      'none': None,
      # The deepest nesting the loader builds.
      'deepest nesting': _nested_lists(_PLAIN_PICKLE_MAX_DEPTH),
      # One string re-used within the loader's budget: pickle writes it once and fetches it 9 times.
      'one string re-used 10 times': ['v' * 1000] * 10,
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

  def test_oracle_sync_tables_at_network_size_load(self):
    """Oracle sync's tables at network size (2,000 nodes, 300 signed median entries) load unchanged in well under a
    second: their repeated keys and signer address stay inside the loader's bounds."""
    # Node addresses as the network has them: '0xai_' and 44 characters.
    nodes = ['0xai_' + (uuid4().hex * 2)[:44] for _ in range(2000)]
    # The two table shapes oracle sync writes, at network size.
    payloads = {
      # The local and agreed availability tables: node -> 0..255.
      'availability table': {node: index % 256 for index, node in enumerate(nodes)},
      # The median table: node -> signed VALUE, with EPOCH and NODE dropped after signing.
      'median table': {node: self._signed({'VALUE': 255, 'EPOCH': 41, 'NODE': node}, 'EPOCH', 'NODE')
                       for node in nodes[:300]},
    }
    # Each table on its own.
    for name, payload in payloads.items():
      # A failure names the table.
      with self.subTest(payload=name):
        # Stored through the real add_pickle.
        cid = self.engine.add_pickle(payload, show_logs=False)
        # The read is timed.
        started = time.perf_counter()
        # Read as oracle sync reads it.
        loaded = self.engine.get_pickle(cid, raise_on_error=True, show_logs=False)
        # Well under a second.
        self.assertLess(time.perf_counter() - started, 1.0)
        # Unchanged.
        self.assertEqual(loaded, payload)

  def _store_bytes(self, data):
    """
    Keep pickle bytes written by hand under a new CID, as R1FS keeps a file another node added.

    Parameters
    ----------
    data : bytes
      The pickle bytes, crafted rather than written by add_pickle.

    Returns
    -------
    str
      The CID get_pickle reads them back by.

    Examples
    --------
    >>> self.engine.get_pickle(self._store_bytes(pickle.dumps([1])))
    [1]
    """
    # A new CID, as for any stored file.
    cid = 'Qm' + uuid4().hex
    # Kept as the fake add_file keeps a file: its name and its bytes.
    self.engine.stored[cid] = ('crafted.pkl', data)
    # get_pickle reads them back through the fake get_file.
    return cid

  def _assert_refused_fast(self, data, reason):
    """
    Assert that get_pickle refuses pickle bytes for the given reason, in well under a second.

    Parameters
    ----------
    data : bytes
      The pickle bytes.
    reason : str
      The text that follows "R1FS pickle refused: " in the error.

    Returns
    -------
    None

    Examples
    --------
    >>> self._assert_refused_fast(b'\\x80\\x04]2e.', 'opcode DUP')
    """
    # Stored as another node's file would be.
    cid = self._store_bytes(data)
    # The refusal is timed from the read.
    started = time.perf_counter()
    # With raise_on_error the refusal is the exception, its reason in the text.
    with self.assertRaisesRegex(RuntimeError, re.escape('R1FS pickle refused: ' + reason)):
      # Read as oracle sync reads a file another oracle names.
      self.engine.get_pickle(cid, raise_on_error=True, show_logs=False)
    # Refused in milliseconds; one second leaves room for a slow host.
    self.assertLess(time.perf_counter() - started, 1.0)

  def test_shared_tuple_used_as_dict_key_is_refused_in_milliseconds(self):
    """A 665-byte pickle whose dict key is one tuple shared down 50 levels, which a load would hash in 2**50 steps
    while holding the GIL, is refused before anything of it is built."""
    # Level 0: the empty tuple, memoized at index 0 and popped.
    data = b'\x80\x04' + b')\x94' + b'0'
    # Levels 1 to 50.
    for level in range(1, 51):
      # A pair of the level below, fetched twice from the memo (LONG_BINGET), memoized at the next index and popped.
      data += (b'j' + struct.pack('<I', level - 1)) * 2 + b'\x86\x94' + b'0'
    # A dict whose one key is the 50-level tuple, so SETITEM would hash it.
    data += b'}' + b'j' + struct.pack('<I', 50) + b'K\x01' + b's' + b'.'
    # 665 bytes are enough.
    self.assertEqual(len(data), 665)
    # Refused at its first fetch of a container.
    self._assert_refused_fast(data, 'it uses one container in two places')

  def test_shared_deep_or_overreused_shapes_are_refused_in_milliseconds(self):
    """Small pickles that would expand exponentially (lists or dicts shared at every level, through memo fetches or
    DUP), nest too deep, re-use one string far past their size, or make the load clear a memo far larger than
    themselves, are refused in milliseconds."""
    # One list used twice at each of 20 levels: 142 bytes that print as about 4 MB of JSON.
    shared_list = []
    # Each level holds the level below twice.
    for _ in range(20):
      # Both items are one object.
      shared_list = [shared_list, shared_list]
    # The same with dicts.
    shared_dict = {}
    # Each level holds the level below twice.
    for _ in range(20):
      # Both values are one object.
      shared_dict = {'a': shared_dict, 'b': shared_dict}
    # Lists of two items built from memo fetches (MARK, BINGET, BINGET, LIST, MEMOIZE) for 50 levels, the top one
    # stored under 'n1'.
    by_memo = (b'\x80\x04' + b']\x94' + b'0'
               + b''.join(b'(' + (b'h' + bytes([level - 1])) * 2 + b'l\x94' + b'0' for level in range(1, 51))
               + b'}' + b'\x8c\x02n1' + b'h' + bytes([50]) + b's.')
    # The same through DUP, 20 levels: 21 lists, 20 marks between them; each (DUP, APPENDS) puts the top list twice
    # into the list below the mark.
    by_dup = b'\x80\x04}\x8c\x02n1' + b'](' * 20 + b']' + b'2e' * 20 + b's.'
    # A 100,000-level tuple as a dict key (EMPTY_TUPLE, then TUPLE1 per level), which SETITEM would hash recursively.
    deep_key = b'\x80\x04}' + b')' + b'\x85' * 100000 + b'K\x01s.'
    # One level too deep, the deepest item in the first batch of a list's items: pickle writes a list of more than
    # 1,000 items in batches (APPENDS), and the later batch of zeros must not lower the list's depth.
    deep_then_shallow = [[_nested_lists(_PLAIN_PICKLE_MAX_DEPTH - 1)] + [0] * 1000]
    # None put at memo index 2**24 (LONG_BINPUT) in a 9-byte file: the load would grow its memo to twice the index
    # and clear every slot, 256 MiB here and gigabytes with a larger index.
    memo_gap = b'\x80\x04N' + b'r' + struct.pack('<I', 1 << 24) + b'.'
    # An empty bytearray memoized at index 0, extended by 1,000 bytes (APPENDS, which the load applies to a bytearray
    # through its extend), then fetched 1,000 times into a list: one growing object in 1,001 places. With 200,000 of
    # each, 0.8 MB prints as about 160 GB.
    grown_bytearray = (b'\x80\x05](' + b'\x96' + struct.pack('<Q', 0) + b'q\x00' + b'(' + b'K\x00' * 1000 + b'e'
                       + b'h\x00' * 1000 + b'e.')
    # Why each shape is refused.
    shared = 'it uses one container in two places'
    # The reason for both too-deep shapes.
    deep = f'it nests deeper than {_PLAIN_PICKLE_MAX_DEPTH} levels'
    # Shape name, pickle bytes, refusal reason.
    shapes = [
      ('list shared at 20 levels', pickle.dumps({'n1': shared_list}), shared),
      ('dict shared at 20 levels', pickle.dumps({'n1': shared_dict}), shared),
      ('lists from memo fetches, 50 levels', by_memo, shared),
      ('lists through DUP, 20 levels', by_dup, 'opcode DUP'),
      ('tuple nested 100,000 levels as a dict key', deep_key, deep),
      ('lists nested one level too deep', pickle.dumps(_nested_lists(_PLAIN_PICKLE_MAX_DEPTH + 1)), deep),
      ('one level too deep, deepest item in an earlier batch', pickle.dumps(deep_then_shallow), deep),
      ('one string re-used 100 times', pickle.dumps(['v' * 1000] * 100),
       f'its re-used values add up to more than {_PLAIN_PICKLE_MAX_REUSE} times its size'),
      ('a memo index far past the next free one', memo_gap, 'memo index out of order'),
      ('a bytearray extended after it is memoized, fetched again', grown_bytearray, shared),
    ]
    # Each shape on its own.
    for name, data, reason in shapes:
      # A failure names the shape.
      with self.subTest(shape=name):
        # Refused, for its reason, in milliseconds.
        self._assert_refused_fast(data, reason)

  def test_keys_whose_hash_a_file_can_choose_are_refused_in_milliseconds(self):
    """Dict keys and set items that a file can build to share one hash (ints of 2**61 - 1 or more in size, tuples,
    frozensets), and floats, are refused in milliseconds, before the load hashes them; str, bytes, bool, None and
    smaller int keys and set items still load."""
    # The modulus of Python's int hash: every multiple of it hashes to 0.
    modulus = 2 ** 61 - 1
    # The largest and smallest int keys that load, a str key, set items of every allowed type, and a None key.
    allowed = {modulus - 1: 0, 1 - modulus: 1, 'k': {b'b', True, None, 2}, None: frozenset(['s'])}
    # Read with raise_on_error, so a refusal would be the exception.
    loaded = self.engine.get_pickle(self._store_bytes(pickle.dumps(allowed)), raise_on_error=True, show_logs=False)
    # Unchanged.
    self.assertEqual(loaded, allowed)
    # 5,000 int keys that all hash to 0 (69 KB): the load's dict compares each new key with every earlier one while
    # holding the GIL, 0.26 s at 2 cores, and 4 times as long per doubling (20,000 keys, 0.28 MB: 4.3 s).
    colliding = {modulus * (number + 1): 0 for number in range(5000)}
    # Shape name and pickle bytes: SETITEMS, SETITEM, DICT, ADDITEMS and FROZENSET each meet one.
    shapes = [
      ('5,000 int keys of one hash', pickle.dumps(colliding)),
      ('one int key of 2**61 - 1', pickle.dumps({modulus: 0})),
      ('a tuple key', pickle.dumps({(1, 2): 0})),
      ('a frozenset key', pickle.dumps({frozenset([1]): 0})),
      ('a float key', pickle.dumps({1.5: 0})),
      ('a tuple key in a DICT opcode', b'\x80\x02(K\x01K\x02\x86K\x00d.'),
      ('a set item of 2**61 - 1', pickle.dumps({modulus})),
      ('a frozenset item of 2**61 - 1', pickle.dumps(frozenset([modulus]))),
    ]
    # Each shape on its own.
    for name, data in shapes:
      # A failure names the shape.
      with self.subTest(shape=name):
        # Refused, for this reason, in milliseconds.
        self._assert_refused_fast(data, 'a dict key or set item is not str, bytes, bool, None or an int below 2**61 - 1')

  def test_file_larger_than_the_bound_is_refused(self):
    """A pickle of exactly the size bound loads; one byte more is refused before it is parsed."""
    # The bytes a pickle adds around a large bytes value, measured on this interpreter.
    overhead = len(pickle.dumps(bytes(1 << 20))) - (1 << 20)
    # A bytes value whose pickle is exactly the bound.
    at_bound = pickle.dumps(bytes(_PLAIN_PICKLE_MAX_BYTES - overhead))
    # The boundary is exact.
    self.assertEqual(len(at_bound), _PLAIN_PICKLE_MAX_BYTES)
    # It loads, whole.
    loaded = self.engine.get_pickle(self._store_bytes(at_bound), raise_on_error=True, show_logs=False)
    # Every byte came back.
    self.assertEqual(len(loaded), _PLAIN_PICKLE_MAX_BYTES - overhead)
    # One byte more is refused.
    self._assert_refused_fast(pickle.dumps(bytes(_PLAIN_PICKLE_MAX_BYTES - overhead + 1)),
                              f'larger than {_PLAIN_PICKLE_MAX_BYTES} bytes')

  def test_marks_and_memo_indexes_are_followed_as_the_unpickler_follows_them(self):
    """POP with nothing above a mark drops the mark, and MEMOIZE takes the next free memo index, as in the unpickler:
    files that do this load as a plain load builds them, and files that hide a shared list behind them are refused."""
    # An empty list, a mark, then POP: with nothing above the mark, POP drops the mark and the list is the result.
    pop_drops_mark = b'\x80\x04](0.'
    # 's' put at index 0 (BINPUT), a list memoized at the next free index, 1, then 's' fetched from index 0 into it.
    put_then_memoize = b'\x80\x04\x8c\x01sq\x00]\x94h\x00a.'
    # Each loads as a plain load builds it.
    for name, data in (('POP drops a mark', pop_drops_mark), ('BINPUT then MEMOIZE', put_then_memoize)):
      # A failure names the file.
      with self.subTest(shape=name):
        # Read with raise_on_error, so a refusal would be the exception.
        loaded = self.engine.get_pickle(self._store_bytes(data), raise_on_error=True, show_logs=False)
        # As built by the plain loader.
        self.assertEqual(loaded, pickle.loads(data))
    # Files that hide a list fetched twice from the memo behind these rules, the list then stored twice under 'n1'.
    hidden = {
      # A list, a mark, POP (which drops the mark), MEMOIZE of the list (index 0), POP of the list.
      'behind a POP that drops a mark': b'\x80\x04}\x8c\x02n1](0\x940(h\x00h\x00ls.',
      # 's' put at index 0 and popped, a list memoized at the next free index, 1, and popped.
      'behind MEMOIZE after BINPUT 0': b'\x80\x04}\x8c\x02n1\x8c\x01sq\x000]\x940(h\x01h\x01ls.',
    }
    # Each is refused.
    for name, data in hidden.items():
      # A failure names the file.
      with self.subTest(shape=name):
        # A plain load shares the list: the file is a shape the loader must refuse.
        shared = pickle.loads(data)['n1']
        # One object in both places.
        self.assertIs(shared[0], shared[1])
        # Refused at the fetch of the list.
        self._assert_refused_fast(data, 'it uses one container in two places')

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
