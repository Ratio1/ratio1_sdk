import json
import os
import shutil
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

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

  def _engine(self, reachable=True, pin_fails=False):
    """``reachable``: whether `ipfs get` / `ipfs pin add` find the CID (else they time out)."""
    engine = object.__new__(R1FSEngine)
    engine.commands = []
    engine.relay_calls = []
    engine.relay_accepts = False
    engine.relay_gate = threading.Event()  # cleared = the relay API hangs
    engine.relay_gate.set()

    def run_command(cmd_list, raise_on_error=True, timeout=IPFSCt.TIMEOUT, **kwargs):
      engine.commands.append((cmd_list[1], timeout))
      if cmd_list[1] == "get" and reachable:
        os.makedirs(cmd_list[-1])
        with open(os.path.join(cmd_list[-1], cmd_list[2]), "wb") as fhandle:
          fhandle.write(_ciphertext(json.dumps(DOC).encode()))
        return ""
      if cmd_list[1] == "pin" and reachable and not pin_fails:
        return "pinned"
      raise Exception(f"Timeout expired after {timeout}s for '{' '.join(cmd_list)}'")

    def publish(cid, **kwargs):
      engine.relay_calls.append((cid, threading.current_thread().name))
      engine.relay_gate.wait(10)
      return engine.relay_accepts

    folder = tempfile.mkdtemp(prefix="r1fs_read_")
    self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
    engine._R1FSEngine__run_command = run_command
    engine._R1FSEngine__publish_cid_to_relay = publish
    engine._R1FSEngine__relay_retry_queue = {}
    engine._R1FSEngine__relay_busy = threading.Lock()
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

  def test_healthy_read_is_pinned_after_the_get(self):
    engine = self._engine()
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
    self.assertEqual(engine.commands, [("get", 10), ("pin", 10)])

  def test_failed_pin_after_a_good_get_does_not_fail_the_read(self):
    engine = self._engine(pin_fails=True)
    self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
    self.assertEqual(engine.commands, [("get", 10), ("pin", 10)])

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


if __name__ == "__main__":
  unittest.main()
