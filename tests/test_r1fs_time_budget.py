import tempfile
import unittest
from unittest import mock

from ratio1.ipfs import r1fs
from ratio1.ipfs.r1fs import R1FSEngine


class R1FSTimeBudgetTests(unittest.TestCase):
  """get_file / get_json with an overall time budget, against an unreachable CID."""

  def _engine(self, pin_seconds=None, get_seconds=None):
    """An engine whose IPFS commands take ``*_seconds`` (None = never answer, so they time out)."""
    engine = object.__new__(R1FSEngine)
    engine.now = 1000.0
    engine.commands = []
    engine.relay_retries = 0
    engine.self_heals = 0

    def run_command(cmd_list, raise_on_error=True, timeout=None, **kwargs):
      cost = pin_seconds if cmd_list[1] == "pin" else get_seconds
      engine.commands.append((cmd_list[1], round(timeout, 3)))
      if cost is None or cost > timeout:
        engine.now += timeout
        raise Exception("Timeout expired for '{}'".format(" ".join(cmd_list)))
      engine.now += cost
      if cmd_list[1] == "get":
        raise Exception("stop after the download step")  # decryption is out of scope here
      return "pinned"

    def self_heal(cid, show_logs=True):
      engine.self_heals += 1
      engine.now += 32  # two relay attempts of 15 s and a 2 s pause
      return True

    def relay_retries(context, show_logs=True):
      engine.relay_retries += 1

    engine._R1FSEngine__run_command = run_command
    engine._R1FSEngine__attempt_download_self_heal = self_heal
    engine._R1FSEngine__retry_queued_relay_publications = relay_retries
    engine._R1FSEngine__ipfs_started = True
    engine._R1FSEngine__DEFAULT_SECRET = "ratio1"
    engine._R1FSEngine__downloads_dir = tempfile.mkdtemp(prefix="r1fs_budget_")
    engine._hash_secret = lambda secret: b"k" * 32
    engine.P = lambda *args, **kwargs: None
    engine.Pd = lambda *args, **kwargs: None
    return engine

  def _call(self, engine, **kwargs):
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      start = engine.now
      result = engine.get_json("QmUnreachable", show_logs=False, **kwargs)
      return result, engine.now - start

  def test_without_a_budget_an_unreachable_cid_holds_the_caller_for_minutes(self):
    engine = self._engine()
    result, elapsed = self._call(engine, timeout=10)
    self.assertIsNone(result)
    self.assertEqual(engine.commands, [("pin", 90), ("pin", 90)])  # the caller's timeout does not reach the pin
    self.assertEqual((engine.relay_retries, engine.self_heals), (1, 1))
    self.assertEqual(elapsed, 212)

  def test_budget_bounds_the_whole_call(self):
    engine = self._engine()
    result, elapsed = self._call(engine, timeout=10, max_seconds=15)
    self.assertIsNone(result)
    self.assertEqual(engine.commands, [("pin", 15)])
    self.assertEqual((engine.relay_retries, engine.self_heals), (0, 0))
    self.assertEqual(elapsed, 15)

  def test_budget_without_pin_bounds_the_get(self):
    engine = self._engine()
    result, elapsed = self._call(engine, timeout=10, pin=False, max_seconds=15)
    self.assertIsNone(result)
    self.assertEqual(engine.commands, [("get", 10)])
    self.assertEqual(engine.self_heals, 0)
    self.assertEqual(elapsed, 10)

  def test_get_receives_what_the_pin_left(self):
    engine = self._engine(pin_seconds=4, get_seconds=None)
    result, elapsed = self._call(engine, max_seconds=15)
    self.assertIsNone(result)
    self.assertEqual(engine.commands, [("pin", 15), ("get", 11)])
    self.assertEqual(elapsed, 15)

  def test_spent_budget_still_gives_the_next_command_a_moment(self):
    engine = self._engine(pin_seconds=15, get_seconds=None)
    result, elapsed = self._call(engine, max_seconds=15)
    self.assertEqual(engine.commands, [("pin", 15), ("get", 0.1)])
    self.assertLess(elapsed, 15.2)

  def test_default_call_is_unchanged_for_a_reachable_cid(self):
    engine = self._engine(pin_seconds=1, get_seconds=None)
    self._call(engine)
    self.assertEqual(engine.commands[0], ("pin", 90))
    self.assertEqual(engine.commands[1], ("get", 90))
    self.assertEqual(engine.relay_retries, 1)


if __name__ == "__main__":
  unittest.main()
