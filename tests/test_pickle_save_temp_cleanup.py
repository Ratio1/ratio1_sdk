import io
import os
import pickle
import tempfile
import threading
import unittest
from unittest import mock

from ratio1.logging.logger_mixins import pickle_serialization_mixin
from ratio1.logging.logger_mixins.pickle_serialization_mixin import _PickleSerializationMixin


class _Saver(_PickleSerializationMixin):
  def P(self, *args, **kwargs):  # pylint: disable=unused-argument
    return

  def get_target_folder(self, target=None):  # pylint: disable=unused-argument
    return None

  def managed_lock_resource(self, *args, **kwargs):  # pylint: disable=unused-argument
    return threading.Lock()


class _Unpicklable:
  def __reduce__(self):
    raise RuntimeError("cannot pickle")


class PickleSaveTempCleanupTest(unittest.TestCase):
  def test_failed_pickle_leaves_no_temp_file(self):
    with tempfile.TemporaryDirectory() as folder:
      path = os.path.join(folder, "object.pickle")
      _Saver().save_pickle({"bad": _Unpicklable()}, fn=path, verbose=False)
      self.assertEqual(os.listdir(folder), [])

  def test_successful_pickle_replaces_target(self):
    with tempfile.TemporaryDirectory() as folder:
      path = os.path.join(folder, "object.pickle")
      _Saver().save_pickle({"ok": 1}, fn=path, verbose=False)
      self.assertEqual(os.listdir(folder), ["object.pickle"])


class _CountingRaw(io.RawIOBase):
  """A raw file that counts the write() calls reaching it, i.e. the write syscalls."""
  def __init__(self, path, mode):
    super().__init__()
    self.file = io.FileIO(path, mode)
    self.writes = 0

  def writable(self):
    return True

  def write(self, data):
    self.writes += 1
    return self.file.write(data)

  def fileno(self):
    return self.file.fileno()

  def close(self):
    self.file.close()
    super().close()


class PickleSaveBufferingTest(unittest.TestCase):
  def test_large_pickle_is_identical_and_written_in_few_syscalls(self):
    data = {i: "node-%06d" % i * 8 for i in range(50000)}
    expected = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
    self.assertGreater(len(expected), 4 << 20)
    raws = []

    def counting_open(path, mode="r", buffering=-1):
      raws.append(_CountingRaw(path, mode))
      # Same buffer choice as open() for binary writes: the requested size, else the default.
      return io.BufferedWriter(raws[-1], buffering if buffering > 1 else io.DEFAULT_BUFFER_SIZE)

    with tempfile.TemporaryDirectory() as folder:
      path = os.path.join(folder, "object.pickle")
      with mock.patch.object(pickle_serialization_mixin, "open", counting_open, create=True):
        _Saver().save_pickle(data, fn=path, verbose=False)
      with open(path, "rb") as fhandle:
        self.assertEqual(fhandle.read(), expected)
    self.assertEqual(len(raws), 1)
    # The pickler hands write() one 64 KB frame at a time; a default-size buffer passes each
    # frame through as its own syscall (~70 here), a 1 MiB buffer gathers them (~5).
    self.assertLessEqual(raws[0].writes, len(expected) // (1 << 20) + 2)


if __name__ == "__main__":
  unittest.main()
