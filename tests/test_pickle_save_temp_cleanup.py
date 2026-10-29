import os
import tempfile
import threading
import unittest

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


if __name__ == "__main__":
  unittest.main()
