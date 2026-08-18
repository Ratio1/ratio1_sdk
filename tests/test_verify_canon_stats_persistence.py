import json
import os
import tempfile
import threading
import types
import unittest

from ratio1.bc.base import BaseBlockEngine


def _make_stats_engine(stats_path):
  engine = object.__new__(BaseBlockEngine)
  engine._verify_canon_stats_lock = threading.Lock()
  engine._verify_canon_stats = {
    "total": {
      engine.SIGN_CANON_V_CURRENT: 0,
      engine.SIGN_CANON_V_LEGACY: 0,
      engine.SIGN_CANON_V_UNVERSIONED: 0,
    },
    "by_sender": {},
  }
  engine._verify_canon_stats_flush_every = 1
  engine._verify_canon_stats_counter = 0
  engine._verify_canon_stats_path = stats_path
  engine._verify_canon_stats_flush_event = threading.Event()
  engine._verify_canon_stats_worker_lock = threading.Lock()
  engine._verify_canon_stats_worker = None
  return engine


class TestVerifyCanonStatsPersistence(unittest.TestCase):

  def test_slow_persistence_does_not_block_verification_accounting(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      engine = _make_stats_engine(
        os.path.join(temp_dir, "verify_canon_stats.json"),
      )
      flush_started = threading.Event()
      release_flush = threading.Event()
      producer_returned = threading.Event()

      def blocking_flush(_self, _snapshot):
        flush_started.set()
        release_flush.wait(timeout=2.0)

      engine._flush_verify_canon_stats = types.MethodType(
        blocking_flush,
        engine,
      )

      producer = threading.Thread(
        target=lambda: (
          engine._bump_verify_canon_stats(
            "0xai_sender",
            engine.SIGN_CANON_V_CURRENT,
          ),
          producer_returned.set(),
        ),
      )
      producer.start()
      try:
        self.assertTrue(flush_started.wait(timeout=1.0))
        self.assertTrue(producer_returned.wait(timeout=0.25))
      finally:
        release_flush.set()
        producer.join(timeout=1.0)

      self.assertTrue(engine.wait_for_verify_canon_stats_flush(timeout=1.0))

  def test_coalesced_writer_persists_latest_snapshot(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      stats_path = os.path.join(temp_dir, "verify_canon_stats.json")
      engine = _make_stats_engine(stats_path)

      for idx in range(250):
        engine._bump_verify_canon_stats(
          "0xai_sender_{}".format(idx % 5),
          engine.SIGN_CANON_V_CURRENT,
        )

      self.assertTrue(
        engine.flush_verify_canon_stats(wait=True, timeout=2.0),
      )
      with open(stats_path, "rt") as fh:
        persisted = json.load(fh)

      self.assertEqual(
        persisted["total"][engine.SIGN_CANON_V_CURRENT],
        250,
      )
      self.assertEqual(sum(
        values[engine.SIGN_CANON_V_CURRENT]
        for values in persisted["by_sender"].values()
      ), 250)

  def test_non_persisting_accounting_keeps_memory_stats_without_io(self):
    with tempfile.TemporaryDirectory() as temp_dir:
      engine = _make_stats_engine(
        os.path.join(temp_dir, "verify_canon_stats.json"),
      )

      engine._bump_verify_canon_stats(
        "0xai_sender",
        engine.SIGN_CANON_V_CURRENT,
        persist=False,
      )

      self.assertEqual(engine._verify_canon_stats_counter, 1)
      self.assertEqual(
        engine._verify_canon_stats["by_sender"]["0xai_sender"][
          engine.SIGN_CANON_V_CURRENT
        ],
        1,
      )
      self.assertIsNone(engine._verify_canon_stats_worker)
      self.assertFalse(os.path.exists(engine._verify_canon_stats_path))


if __name__ == "__main__":
  unittest.main()
