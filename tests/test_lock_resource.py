import io
import threading
import time
import unittest
from collections import OrderedDict
from contextlib import redirect_stdout
from unittest import mock

from ratio1.logging import base_logger
from ratio1.logging.base_logger import BaseLogger


def _make_logger():
  # Only the lock table state from BaseLogger.__init__; the full constructor
  # creates folders and probes the host.
  log = object.__new__(BaseLogger)
  log._lock_table = OrderedDict()
  log._lock_table_identities = {}
  log._lock_table_mutex = threading.Lock()
  return log


class LockResourceTest(unittest.TestCase):
  def test_existing_lock_does_not_wait_for_table_mutex(self):
    log = _make_logger()
    log.lock_resource("NETMON")
    log.unlock_resource("NETMON")

    acquired = threading.Event()

    def worker():
      log.lock_resource("NETMON")
      acquired.set()
      log.unlock_resource("NETMON")

    with log._lock_table_mutex:
      thread = threading.Thread(target=worker, daemon=True)
      thread.start()
      self.assertTrue(acquired.wait(timeout=2.0))
    thread.join(timeout=2.0)

  def test_reuses_lock_and_records_owner(self):
    log = _make_logger()
    first = log.lock_resource("res")
    self.assertTrue(first.locked())
    self.assertEqual(log._lock_table_identities["res"], threading.get_ident())
    log.unlock_resource("res")
    self.assertFalse(first.locked())
    self.assertIsNone(log._lock_table_identities["res"])

    second = log.lock_resource("res")
    self.assertIs(second, first)
    log.unlock_resource("res")

  def test_concurrent_first_use_creates_one_lock(self):
    log = _make_logger()
    nr_threads = 16
    barrier = threading.Barrier(nr_threads)
    seen_locks = []
    inside = []
    max_inside = []
    seen_mutex = threading.Lock()

    def worker():
      barrier.wait()
      lock = log.lock_resource("new")
      with seen_mutex:
        seen_locks.append(lock)
        inside.append(1)
        max_inside.append(len(inside))
      time.sleep(0.001)
      with seen_mutex:
        inside.pop()
      log.unlock_resource("new")

    threads = [threading.Thread(target=worker) for _ in range(nr_threads)]
    for thread in threads:
      thread.start()
    for thread in threads:
      thread.join(timeout=5.0)

    self.assertEqual(len(seen_locks), nr_threads)
    self.assertEqual(len({id(lock) for lock in seen_locks}), 1)
    self.assertIs(seen_locks[0], log._lock_table["new"])
    self.assertEqual(max(max_inside), 1)

  def test_creation_failure_returns_none_without_blocking(self):
    log = _make_logger()
    output = io.StringIO()
    with mock.patch.object(base_logger.threading, "Lock", side_effect=RuntimeError("boom")):
      with redirect_stdout(output):
        result = log.lock_resource("broken")
    self.assertIsNone(result)
    self.assertNotIn("broken", log._lock_table)
    self.assertIn("PANIC", output.getvalue())
    self.assertFalse(log._lock_table_mutex.locked())


if __name__ == "__main__":
  unittest.main()
