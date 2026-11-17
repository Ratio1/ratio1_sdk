"""The R1FS engine module holds none of the expressions that printed key material in its log lines."""
# The engine module's source is read.
import inspect
# The printed expressions are matched as patterns.
import re
# The test runner.
import unittest

# The R1FS engine module.
from ratio1.ipfs import r1fs


class R1FSLogSecretsTests(unittest.TestCase):
  """The R1FS module source holds none of the expressions that printed key material in its log lines."""

  def test_no_line_prints_a_secret_or_key_bytes(self):
    """No line of the module slices a passphrase or the swarm key, hex-prints bytes of the AES key derived from the
    passphrase, or puts the swarm key in a message: the expressions that the debug lines of add_json, add_pickle,
    add_file, calculate_file_cid, calculate_json_cid and calculate_pickle_cid, and the start lines of
    maybe_start_ipfs, printed."""
    # The module source, line by line.
    lines = inspect.getsource(r1fs).splitlines()
    # What each printed expression showed -> its pattern. The swarm-key slice has no leading word boundary, so a slice
    # of the engine's private copy (self.__base64_swarm_key) matches too.
    patterns = {
      'a prefix of the passphrase': r'\bsecret\[:',
      'bytes of the derived AES key': r'\bkey\[:\d*\]\.hex\(\)',
      'a part of the swarm key': r'base64_swarm_key\)?\[',
      'the whole swarm key': r'\{base64_swarm_key\}',
    }
    # Every line that matches a pattern: its number, what it showed, and the line.
    found = [(number, shown, line.strip()) for number, line in enumerate(lines, 1)
             for shown, pattern in patterns.items() if re.search(pattern, line)]
    # None.
    self.assertEqual(found, [])


if __name__ == '__main__':
  # Run this file alone.
  unittest.main()
