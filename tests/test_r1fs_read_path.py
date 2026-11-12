import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ratio1.ipfs import r1fs
from ratio1.ipfs.r1fs import IPFSCt, R1FSEngine

KEY = b"k" * 32
DOC = {"plan": 1}


def _ciphertext(content: bytes, filename: str = "data.json") -> bytes:
  """The single file add_file stores under a CID: nonce, meta length, meta, content, GCM tag."""
  nonce = os.urandom(12)
  encryptor = Cipher(algorithms.AES(KEY), modes.GCM(nonce)).encryptor()
  meta = encryptor.update(json.dumps({"filename": filename}).encode())
  body = encryptor.update(content) + encryptor.finalize()
  return nonce + len(meta).to_bytes(4, "big") + meta + body + encryptor.tag


class R1FSReadPathTests(unittest.TestCase):
  """get_json against fake `ipfs` commands and a fake relay API."""

  def _engine(self, reachable=True, pin_fails=False, get_seconds=0):
    """``reachable``: whether `ipfs get` / `ipfs pin add` find the CID (else they time out).
    ``get_seconds``: how far a good get moves ``engine.now``, the clock a test can put in place of time.time."""
    engine = object.__new__(R1FSEngine)
    engine.commands = []
    engine.relay_calls = []
    engine.relay_accepts = False
    engine.relay_gate = threading.Event()  # cleared = the relay API hangs
    engine.relay_gate.set()
    engine.relay_entered = threading.Semaphore(0)  # released each time the fake relay API is called
    engine.now = 1000.0

    def run_command(cmd_list, raise_on_error=True, timeout=IPFSCt.TIMEOUT, **kwargs):
      engine.commands.append((cmd_list[1], timeout))
      if cmd_list[1] == "get" and reachable:
        engine.now += get_seconds
        os.makedirs(cmd_list[-1])
        with open(os.path.join(cmd_list[-1], cmd_list[2]), "wb") as fhandle:
          fhandle.write(_ciphertext(json.dumps(DOC).encode()))
        return ""
      if cmd_list[1] == "pin" and reachable and not pin_fails:
        return "pinned"
      raise Exception(f"Timeout expired after {timeout}s for '{' '.join(cmd_list)}'")

    def publish(cid, **kwargs):
      engine.relay_calls.append((cid, threading.current_thread().name))
      engine.relay_entered.release()
      engine.relay_gate.wait(10)
      return engine.relay_accepts

    folder = tempfile.mkdtemp(prefix="r1fs_read_")
    self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
    engine._R1FSEngine__run_command = run_command
    engine._R1FSEngine__publish_cid_to_relay = publish
    engine._R1FSEngine__relay_retry_queue = {}
    engine._R1FSEngine__relay_busy = threading.Lock()
    engine._R1FSEngine__relay_heal_pending = set()
    engine._R1FSEngine__relay_publication_status = {}
    engine._R1FSEngine__ipfs_started = True
    engine._R1FSEngine__DEFAULT_SECRET = "ratio1"
    engine._R1FSEngine__downloads_dir = folder
    engine._R1FSEngine__downloaded_files = {}
    engine._hash_secret = lambda secret: KEY
    engine.P = lambda *args, **kwargs: None
    engine.Pd = lambda *args, **kwargs: None
    return engine

  def _release_relay(self, engine):
    """Let the hung relay API answer, then wait for the background relay pass to end."""
    engine.relay_gate.set()
    self.assertTrue(engine._R1FSEngine__relay_busy.acquire(timeout=10))
    engine._R1FSEngine__relay_busy.release()

  def test_missing_cid_read_is_bounded_by_the_caller_timeout_not_a_90s_pin(self):
    engine = self._engine(reachable=False)
    self.assertIsNone(engine.get_json("QmMissing", timeout=10, show_logs=False))
    self.assertEqual(engine.commands, [("get", 10)])

  def test_healthy_read_is_pinned_after_the_get_with_only_the_time_left(self):
    for get_seconds, pin_timeout in [(4, 6), (10, 1)]:  # the get used all 10 s: the pin gets the 1 s floor
      engine = self._engine(get_seconds=get_seconds)
      with mock.patch.object(r1fs.time, "time", lambda: engine.now):
        self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
      self.assertEqual(engine.commands, [("get", 10), ("pin", pin_timeout)])

  def test_failed_pin_after_a_good_get_does_not_fail_the_read_and_is_logged_in_red(self):
    engine = self._engine(pin_fails=True)
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
    self.assertEqual([command for command, _ in engine.commands], ["get", "pin"])
    self.assertEqual([color for message, color in logs if message.startswith("Pin after download failed")], ["r"])

  def test_reads_leave_the_relay_queue_to_one_background_pass(self):
    engine = self._engine()
    engine._R1FSEngine__relay_retry_queue["QmQueued"] = {"cid": "QmQueued", "queued_at": "t0"}
    engine.relay_gate.clear()  # a synchronous drain would hold these reads on the hung relay API
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)  # a pass runs: kick dropped
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [("QmQueued", "r1fs-relay")])

  def test_missing_cid_is_healed_in_the_background_before_the_queue_drain(self):
    engine = self._engine(reachable=False)
    engine.relay_accepts = True  # even when the relay finds it, the reader does not wait for a second get
    engine._R1FSEngine__relay_retry_queue["QmQueued"] = {"cid": "QmQueued", "queued_at": "t0"}
    engine.relay_gate.clear()
    self.assertIsNone(engine.get_json("QmMissing", timeout=10, show_logs=False))
    self.assertEqual(engine.commands, [("get", 10)])
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [("QmMissing", "r1fs-relay"), ("QmQueued", "r1fs-relay")])

  def test_heal_asked_for_while_a_pass_runs_is_done_by_that_pass(self):
    """Healed before the next queued publication, or before the pass ends when none is left."""
    for queued, expected in [(["QmQ1", "QmQ2"], ["QmQ1", "QmMissing", "QmQ2"]), (["QmQ1"], ["QmQ1", "QmMissing"])]:
      engine = self._engine(reachable=False)
      for cid in queued:
        engine._R1FSEngine__relay_retry_queue[cid] = {"cid": cid, "queued_at": "t0"}
      engine.relay_gate.clear()
      engine._R1FSEngine__relay_in_background(show_logs=False)  # a pass starts for the queue
      self.assertTrue(engine.relay_entered.acquire(timeout=10))  # the publication of QmQ1 hangs
      self.assertIsNone(engine.get_json("QmMissing", timeout=10, show_logs=False))  # finds the pass running
      self._release_relay(engine)
      self.assertEqual(engine.relay_calls, [(cid, "r1fs-relay") for cid in expected])

  def test_reads_that_keep_failing_cannot_keep_the_pass_from_its_queue(self):
    """Each heal point heals what was remembered when it started; a CID asked for again meanwhile waits."""
    engine = self._engine(reachable=False)
    engine._R1FSEngine__relay_retry_queue["QmQ1"] = {"cid": "QmQ1", "queued_at": "t0"}
    publish = engine._R1FSEngine__publish_cid_to_relay

    def publish_while_the_read_fails_again(cid, **kwargs):
      if cid == "QmMissing":
        # The same read fails again during every heal of its CID.
        engine._R1FSEngine__relay_heal_pending.add("QmMissing")
      return publish(cid, **kwargs)

    engine._R1FSEngine__publish_cid_to_relay = publish_while_the_read_fails_again
    engine._R1FSEngine__relay_in_background(heal_cid="QmMissing", show_logs=False)
    self._release_relay(engine)
    # One heal before the publication, one after it; with a heal loop that ran until the set was empty the
    # pass never reached QmQ1 and never ended.
    self.assertEqual([cid for cid, _ in engine.relay_calls], ["QmMissing", "QmQ1", "QmMissing"])
    self.assertEqual(engine._R1FSEngine__relay_heal_pending, {"QmMissing"})  # asked again: the next pass heals it

  def test_a_heal_left_over_is_done_by_the_pass_the_next_good_read_starts(self):
    engine = self._engine()
    engine._R1FSEngine__relay_heal_pending.add("QmMissing")  # added too late for the pass that was running
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)  # empty queue, good read
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [("QmMissing", "r1fs-relay")])

  def test_relay_pass_that_cannot_start_is_logged_in_red_and_frees_the_lock(self):
    engine = self._engine()
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    with mock.patch.object(r1fs, "Thread") as thread:
      thread.return_value.start.side_effect = RuntimeError("can't start new thread")
      # The read keeps its own result: the relay work is not part of it.
      self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
      engine._R1FSEngine__relay_in_background(heal_cid="QmMissing", show_logs=False)
    self.assertEqual(logs, [("Background relay pass could not start: can't start new thread", "r")])
    self.assertTrue(engine._R1FSEngine__relay_busy.acquire(blocking=False))
    self.assertEqual(engine._R1FSEngine__relay_heal_pending, {"QmMissing"})  # kept for the next pass

  def test_cid_unpinned_during_a_pass_is_not_published(self):
    engine = self._engine()
    engine._R1FSEngine__ipfs_relay_api = "https://relay.invalid"
    engine._R1FSEngine__ipfs_api_key_username = engine._R1FSEngine__ipfs_api_key_password = "x"
    engine._R1FSEngine__ipfs_certificate_path = None
    engine._R1FSEngine__uploaded_files = {}
    for cid in ("QmA", "QmB"):
      engine._R1FSEngine__relay_retry_queue[cid] = {"cid": cid, "queued_at": "t0"}
    engine.relay_gate.clear()
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)  # starts the pass
    self.assertTrue(engine.relay_entered.acquire(timeout=10))  # the publication of QmA is in progress
    not_pinned = mock.Mock(status_code=500, text="not pinned")  # the relay never pinned QmB: pin/rm fails
    with mock.patch.object(r1fs.requests, "post", return_value=not_pinned):
      self.assertFalse(engine.unpin_file("QmB", show_logs=False))
    self.assertNotIn("QmB", engine._R1FSEngine__relay_retry_queue)
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [("QmA", "r1fs-relay")])

  def test_relay_unpin_is_bounded(self):
    engine = self._engine()
    engine._R1FSEngine__ipfs_relay_api = "https://relay.invalid"
    engine._R1FSEngine__ipfs_api_key_username = engine._R1FSEngine__ipfs_api_key_password = "x"
    engine._R1FSEngine__ipfs_certificate_path = None
    engine._R1FSEngine__uploaded_files = {}
    hung_relay = r1fs.requests.Timeout("the relay API did not answer")
    with mock.patch.object(r1fs.requests, "post", side_effect=hung_relay) as post:
      self.assertFalse(engine.unpin_file("QmGone", show_logs=False))
    self.assertEqual(post.call_args.kwargs.get("timeout"), IPFSCt.RELAY_PIN_TIMEOUT_SECONDS)


if __name__ == "__main__":
  unittest.main()
