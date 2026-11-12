import json
import os
import shutil
import tempfile
import threading
import types
import unittest
from datetime import datetime, timezone
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ratio1.ipfs import r1fs
from ratio1.ipfs.r1fs import IPFSCt, R1FSEngine

KEY = b"k" * 32
DOC = {"plan": 1}
RELAY = "/dns4/relay.invalid/tcp/4001/p2p/RelayId"
# Kubo's error for `pin rm` of a CID with no direct or recursive pin, written out here rather than taken from the SDK.
NOT_PINNED = "not pinned or pinned indirectly"
LEDGER = "Ledger for {peer}\nDebt ratio:\t0.000000\nExchanges:\t0\nBytes sent:\t0\nBytes received:\t0"


def _iso(seconds: float) -> str:
  """A time.time() value written as __utc_now_iso writes relay_last_success_at."""
  return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


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
    """``reachable``: whether `ipfs get` / `ipfs pin add` find the CID (else they time out); a CID that is not
    reachable was never pinned here, so `ipfs pin rm` answers it with Kubo's "not pinned" error.
    ``pin_fails``: `ipfs pin` commands time out, as when the daemon does not answer.
    ``get_seconds``: how far a get moves ``engine.now``, the clock a test can put in place of time.time.
    ``engine.answers``: the output of other `ipfs` commands, by subcommand (``swarm``, ``bitswap``).
    ``engine.ciphertext``: the object a good get stores, which a test can replace with a crafted one."""
    engine = object.__new__(R1FSEngine)
    engine.commands = []
    engine.answers = {}
    engine.ciphertext = _ciphertext(json.dumps(DOC).encode())
    engine.relay_calls = []
    engine.relay_accepts = False
    engine.relay_gate = threading.Event()  # cleared = the relay API hangs
    engine.relay_gate.set()
    engine.relay_entered = threading.Semaphore(0)  # released each time the fake relay API is called
    engine.now = 1000.0

    def run_command(cmd_list, raise_on_error=True, timeout=IPFSCt.TIMEOUT, **kwargs):
      engine.commands.append((cmd_list[1], timeout))
      if cmd_list[1] in engine.answers:
        # `ipfs bitswap ledger <peer>` names the peer it was asked about.
        return engine.answers[cmd_list[1]].format(peer=cmd_list[-1])
      if cmd_list[1] == "get":
        engine.now += get_seconds  # a get that finds nothing takes its time too
      if cmd_list[1] == "get" and reachable:
        os.makedirs(cmd_list[-1])
        with open(os.path.join(cmd_list[-1], cmd_list[2]), "wb") as fhandle:
          fhandle.write(engine.ciphertext)
        return ""
      if cmd_list[1] == "pin" and reachable and not pin_fails:
        return "pinned"
      if not raise_on_error:
        return ""  # like the real __run_command: a failed command returns "" when raise_on_error is False
      if cmd_list[1:3] == ["pin", "rm"] and not reachable:
        # Kubo exits 1 with this on stderr, which the real __run_command puts in its exception.
        raise Exception(f"Error while running '{' '.join(cmd_list)}': Error: {NOT_PINNED}")
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
    engine._R1FSEngine__relay_data_failures = 0
    engine._R1FSEngine__relay_data_logged_at = 0
    engine._R1FSEngine__rate_limited_reports = {}
    engine._R1FSEngine__relay_in_flight = None
    engine._R1FSEngine__ipfs_relay = RELAY
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

  def _sandbox(self, engine):
    """
    Give the engine a downloads folder two levels inside a private root, with files to keep around it.

    Parameters
    ----------
    engine : R1FSEngine
      The engine from ``_engine``; its downloads folder is replaced.

    Returns
    -------
    tuple
      ``(keep, cids)``: the files that must survive, and path-like CIDs that name each of their folders.

    Notes
    -----
    Every path a CID below names lies inside the private root, so code without the CID check deletes
    only there, never in the shared temporary folder.

    Examples
    --------
    >>> keep, cids = self._sandbox(engine)
    """
    root = tempfile.mkdtemp(prefix="r1fs_cid_")
    self.addCleanup(shutil.rmtree, root, ignore_errors=True)
    downloads = os.path.join(root, "node", "downloads")
    keep = [os.path.join(root, "victim", "keep"), os.path.join(root, "node", "victim", "keep"),
            os.path.join(root, "node", "keep"), os.path.join(downloads, "QmOther", "keep")]
    for path in keep:
      os.makedirs(os.path.dirname(path), exist_ok=True)
      open(path, "w").close()
    engine._R1FSEngine__downloads_dir = downloads
    # An absolute path, a climb to a sibling, the parent folder and the downloads folder itself.
    return keep, (os.path.join(root, "victim"), "../victim", "..", ".")

  def test_read_of_a_cid_that_is_a_path_is_refused_before_anything_is_deleted(self):
    """The pin no longer runs before the cleanup, so the CID check is what keeps the cleanup in the folder."""
    for pin in (True, False):
      engine = self._engine()
      keep, cids = self._sandbox(engine)
      for cid in cids:
        with self.subTest(pin=pin, cid=cid):
          self.assertIsNone(engine.get_file(cid, pin=pin, show_logs=False))
          with self.assertRaises(ValueError):
            engine.get_file(cid, pin=pin, raise_on_error=True, show_logs=False)
          self.assertEqual([path for path in keep if not os.path.exists(path)], [])
      self.assertEqual(engine.commands, [])  # no `ipfs` command saw these strings
      self.assertEqual(engine._R1FSEngine__relay_heal_pending, set())  # and none was left for the relay
      self.assertEqual(engine.relay_calls, [])

  def test_delete_of_a_cid_that_is_a_path_is_refused_and_a_real_cid_is_still_cleaned_up(self):
    engine = self._engine()
    engine._R1FSEngine__uploaded_files = {}
    keep, cids = self._sandbox(engine)
    for cid in cids:
      with self.subTest(cid=cid):
        self.assertFalse(engine.delete_file(cid, unpin_remote=False, cleanup_local_files=True, show_logs=False))
        with self.assertRaises(ValueError):
          engine.delete_file(cid, unpin_remote=False, cleanup_local_files=True, show_logs=False, raise_on_error=True)
        self.assertEqual([path for path in keep if not os.path.exists(path)], [])
    self.assertEqual(engine.commands, [])  # refused before the local `ipfs pin rm`, whose failure would not stop it
    self.assertTrue(engine.delete_file("QmOther", unpin_remote=False, cleanup_local_files=True, show_logs=False))
    self.assertEqual(engine.commands, [("pin", IPFSCt.TIMEOUT)])
    self.assertFalse(os.path.exists(os.path.join(engine._R1FSEngine__downloads_dir, "QmOther")))

  def test_none_or_empty_cid_keeps_its_old_handling(self):
    """Refused quietly with show_logs=False where it was refused before; left to the command where it was not."""
    engine = self._with_relay_api(self._engine())
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    for cid in (None, ""):
      with self.subTest(cid=cid):
        self.assertIsNone(engine.get_file(cid, show_logs=False))
        self.assertFalse(engine.delete_file(cid, show_logs=False))
        self.assertFalse(engine.unpin_file(cid, show_logs=False))
        self.assertEqual(logs, [])
    self.assertFalse(engine.unpin_file(None))
    self.assertEqual(logs, [("CID parameter cannot be None or empty", "r")])  # unpin_file's own message
    engine.is_pinned("")
    engine.is_cid_available("")
    self.assertEqual(engine.commands, [("pin", IPFSCt.TIMEOUT), ("block", 3)])

  def test_a_bare_cid_still_reaches_the_command_or_the_cleanup(self):
    engine = self._engine()
    keep, _ = self._sandbox(engine)
    engine.answers = {"pin": "{peer} recursive", "block": "Key: {peer}"}
    self.assertTrue(engine.is_pinned("QmLive"))
    self.assertTrue(engine.is_cid_available("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"))
    self.assertEqual(engine.cleanup_downloads("QmOther", show_logs=False), 1)
    self.assertEqual(engine.commands, [("pin", IPFSCt.TIMEOUT), ("block", 3)])
    self.assertEqual([path for path in keep if not os.path.exists(path)], [keep[-1]])  # only QmOther's own file

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

  def _with_relay_api(self, engine):
    """Give the engine the relay settings unpin_file reads before its relay pin/rm."""
    engine._R1FSEngine__ipfs_relay_api = "https://relay.invalid"
    engine._R1FSEngine__ipfs_api_key_username = engine._R1FSEngine__ipfs_api_key_password = "x"
    engine._R1FSEngine__ipfs_certificate_path = None
    engine._R1FSEngine__uploaded_files = {}
    return engine

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

  def _files(self, root):
    """Every file under ``root``, as {path: content}."""
    found = {}
    for folder, _, names in os.walk(root):
      for name in names:
        with open(os.path.join(folder, name), "rb") as fhandle:
          found[os.path.join(folder, name)] = fhandle.read()
    return found

  def test_stored_file_name_that_is_not_plain_is_refused_and_nothing_lands_outside_the_folder(self):
    """The output name comes from the object itself, so whoever added the object chose it."""
    engine = self._engine()
    keep, _ = self._sandbox(engine)
    root = os.path.dirname(os.path.dirname(engine._R1FSEngine__downloads_dir))
    before = self._files(root)
    # An absolute path to an existing file, a climb to a sibling folder, the folder, its parent, nothing, a sub path.
    for name in (keep[0], "../../victim/new", ".", "..", "", "sub/data.json"):
      engine.ciphertext = _ciphertext(json.dumps(DOC).encode(), filename=name)
      with self.subTest(name=name):
        self.assertIsNone(engine.get_json("QmCrafted", show_logs=False))
        with self.assertRaises(RuntimeError):
          engine.get_file("QmCrafted", raise_on_error=True, show_logs=False)
        self.assertEqual(self._files(root), before)  # nothing written or changed, and nothing left behind
        self.assertFalse(os.path.exists(os.path.join(engine._R1FSEngine__downloads_dir, "QmCrafted")))

  def test_failed_tag_check_leaves_no_unauthenticated_plaintext(self):
    """The plaintext is written before the tag is checked: a failed check removes it with the ciphertext."""
    engine = self._engine()
    good = engine.ciphertext
    engine.ciphertext = good[:-1] + bytes([good[-1] ^ 1])  # the last byte of the GCM tag flipped
    folder = os.path.join(engine._R1FSEngine__downloads_dir, "QmForged")
    self.assertIsNone(engine.get_json("QmForged", show_logs=False))
    self.assertFalse(os.path.exists(folder))
    with self.assertRaises(RuntimeError):
      engine.get_file("QmForged", raise_on_error=True, show_logs=False)
    self.assertFalse(os.path.exists(folder))
    engine.ciphertext = good
    self.assertEqual(engine.get_json("QmForged", show_logs=False), DOC)  # the same object with its tag intact

  def test_download_that_is_not_one_regular_file_is_refused_and_nothing_outside_is_read_or_changed(self):
    """`ipfs get` writes a UnixFS symlink as a link to any path here; an R1FS object is one regular file."""
    outside = tempfile.mkdtemp(prefix="r1fs_outside_")
    self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
    data = os.path.join(outside, "data")
    os.makedirs(data)
    with open(os.path.join(data, "ct.bin"), "wb") as fhandle:
      fhandle.write(_ciphertext(json.dumps({"read": "outside"}).encode(), filename="written.json"))
    before = self._files(data)
    pipe = os.path.join(outside, "pipe")  # kept out of ``data``: reading every file there would block on it
    os.mkfifo(pipe)
    writes = {
      "entry links to a file": lambda path: (os.makedirs(path), os.symlink(os.path.join(data, "ct.bin"), path + "/c")),
      "entry links to a pipe": lambda path: (os.makedirs(path), os.symlink(pipe, path + "/c")),
      "folder links to a folder": lambda path: os.symlink(data, path),
    }

    def bounded(call):
      """``call``'s value or exception, run on a thread so a read blocked on the pipe fails instead of hanging."""
      result = {}

      def run():
        try:
          result["value"] = call()
        except Exception as exc:
          result["raised"] = exc

      reader = threading.Thread(target=run, daemon=True)
      reader.start()
      reader.join(3)
      if reader.is_alive():
        os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))  # let the blocked reader go before failing
        reader.join(5)
        self.fail("the read blocked on a pipe outside the downloads folder")
      return result

    for case, write in writes.items():
      with self.subTest(case=case):
        engine = self._engine()
        run_command = engine._R1FSEngine__run_command
        found = []

        def get_writes(cmd_list, **kwargs):
          if cmd_list[1] != "get":
            return run_command(cmd_list, **kwargs)
          found.append(os.path.lexists(cmd_list[-1]))  # something left at the output path by the read before
          write(cmd_list[-1])
          return ""

        engine._R1FSEngine__run_command = get_writes
        self.assertEqual(bounded(lambda: engine.get_json("QmLinked", show_logs=False)), {"value": None})
        raised = bounded(lambda: engine.get_file("QmLinked", raise_on_error=True, show_logs=False)).get("raised")
        self.assertIsInstance(raised, RuntimeError)
        self.assertEqual(found, [False, False])  # the second read removed the first one's leftover, link included
        self.assertEqual(self._files(data), before)  # nothing read into a result, written or deleted there

  def _name_sandbox(self, engine):
    """
    Give the engine an uploads folder, a temporary folder and a working folder inside a private root.

    Parameters
    ----------
    engine : R1FSEngine
      The engine from ``_engine``. Its add_file and calculate_file_cid are replaced by a recorder.

    Returns
    -------
    tuple
      ``(root, seen)``: the private root, and the (file path, file exists) pairs the recorder was given.

    Notes
    -----
    The working folder is two levels down, and so is each unique folder made in the temporary folder, so a
    "../../" name lands inside the root even on code without the check.

    Examples
    --------
    >>> root, seen = self._name_sandbox(engine)
    """
    root = tempfile.mkdtemp(prefix="r1fs_fn_")
    self.addCleanup(shutil.rmtree, root, ignore_errors=True)
    for folder in ("tmp", "uploads", "victim", os.path.join("work", "cwd")):
      os.makedirs(os.path.join(root, folder))
    engine._R1FSEngine__uploads_dir = os.path.join(root, "uploads")
    seen = []

    def record(file_path, **kwargs):
      seen.append((file_path, os.path.isfile(file_path)))
      return "QmNew"

    engine.add_file = engine.calculate_file_cid = record
    self.addCleanup(os.chdir, os.getcwd())
    os.chdir(os.path.join(root, "work", "cwd"))
    gettempdir = mock.patch.object(r1fs.tempfile, "gettempdir", return_value=os.path.join(root, "tmp"))
    gettempdir.start()
    self.addCleanup(gettempdir.stop)
    return root, seen

  def test_caller_file_name_that_is_not_plain_is_refused_before_anything_is_written(self):
    engine = self._engine()
    root, seen = self._name_sandbox(engine)
    victim = os.path.join(root, "victim", "keep")
    with open(victim, "wb") as fhandle:
      fhandle.write(b"keep")
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    for name in (victim, "../../victim/keep", ".", "..", ""):
      with self.subTest(name=name):
        del logs[:]
        self.assertIsNone(engine.add_json(DOC, fn=name, show_logs=False))
        self.assertIsNone(engine.add_pickle(DOC, fn=name, show_logs=False))
        refused = (f"Invalid file name {name!r}: a file name must have no path part and must not be '', '.' or '..'", "r")
        self.assertEqual(logs, [refused, refused])  # in red although show_logs is False
        for call in (lambda: engine.add_json(DOC, fn=name, raise_on_error=True, show_logs=False),
                     lambda: engine.add_pickle(DOC, fn=name, raise_on_error=True, show_logs=False),
                     lambda: engine.calculate_json_cid(DOC, nonce=1, fn=name, show_logs=False),
                     lambda: engine.calculate_pickle_cid(DOC, nonce=1, fn=name, show_logs=False)):
          with self.assertRaises(ValueError):
            call()
    self.assertEqual(seen, [])
    self.assertEqual(self._files(root), {victim: b"keep"})
    self.assertEqual(os.listdir(os.path.join(root, "tmp")), [])  # no unique folder was even made

  def test_plain_caller_file_name_is_the_stored_name_and_add_pickle_writes_it_in_the_uploads_folder(self):
    """add_pickle opened the caller's name in the working folder, then deleted it: device.py, for one."""
    engine = self._engine()
    root, seen = self._name_sandbox(engine)
    work_file = os.path.join(root, "work", "cwd", "device.py")
    with open(work_file, "wb") as fhandle:
      fhandle.write(b"keep")
    self.assertEqual(engine.add_pickle(DOC, fn="device.py", show_logs=False), "QmNew")
    self.assertEqual(engine.add_json(DOC, fn="deployment-plan.json", show_logs=False), "QmNew")
    self.assertEqual(engine.calculate_json_cid(DOC, nonce=42, fn="data.json", show_logs=False), "QmNew")
    self.assertEqual(engine.calculate_pickle_cid(DOC, nonce=42, fn="model.pkl", show_logs=False), "QmNew")
    self.assertEqual(engine.calculate_pickle_cid(DOC, nonce=42, show_logs=False), "QmNew")  # its default name
    self.assertEqual(engine.add_pickle(DOC, fn="device.py", show_logs=False), "QmNew")  # the same name again
    # The file each one encrypted existed and carries the caller's name, which is what the stored name is made of.
    self.assertEqual([(os.path.basename(path), existed) for path, existed in seen[:4]],
                     [("device.py", True), ("deployment-plan.json", True), ("data.json", True), ("model.pkl", True)])
    # add_pickle: a folder of its own in the uploads folder, a new one per call, so two calls share no file.
    self.assertEqual([os.path.dirname(os.path.dirname(seen[i][0])) for i in (0, 5)], [os.path.join(root, "uploads")] * 2)
    self.assertNotEqual(os.path.dirname(seen[0][0]), os.path.dirname(seen[5][0]))
    self.assertEqual(os.path.dirname(seen[4][0]), os.path.join(root, "uploads"))  # a full path there, as before
    self.assertEqual(self._files(root), {work_file: b"keep"})  # every temporary file removed, device.py untouched
    self.assertEqual(os.listdir(os.path.join(root, "uploads")), [])  # and every folder of its own


if __name__ == "__main__":
  unittest.main()
