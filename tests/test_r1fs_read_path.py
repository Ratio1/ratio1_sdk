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
    """
    Build an engine whose `ipfs` commands and relay API are fakes, with the state _build would give it.

    The fake commands record ``(subcommand, timeout)`` in ``engine.commands``. ``engine.answers`` gives the
    output of other `ipfs` commands by subcommand (``swarm``, ``bitswap``); ``engine.ciphertext`` is the object
    a good get stores, which a test can replace with a crafted one. The fake relay pin/add records
    ``(cid, thread name)`` in ``engine.relay_calls``, waits while ``engine.relay_gate`` is cleared, and answers
    ``engine.relay_accepts``.

    Parameters
    ----------
    reachable : bool, optional
      Whether `ipfs get` / `ipfs pin add` find the CID (else they time out); a CID that is not reachable was
      never pinned here, so `ipfs pin rm` answers it with Kubo's "not pinned" error. Default True.
    pin_fails : bool, optional
      Whether `ipfs pin` commands time out, as when the daemon does not answer. Default False.
    get_seconds : float, optional
      How far a get moves ``engine.now``, the clock a test can put in place of time.time. Default 0.

    Returns
    -------
    R1FSEngine
      The engine, built without _build, so nothing real is started.

    Examples
    --------
    >>> engine = self._engine(reachable=False, get_seconds=10)
    """
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

    def run_command(cmd_list, raise_on_error=True, timeout=IPFSCt.TIMEOUT, return_errors=False, **kwargs):
      """
      Answer an `ipfs` command as the real __run_command would, from the settings of _engine.

      Parameters
      ----------
      cmd_list : list
        The command, ``["ipfs", <subcommand>, ...]``.
      raise_on_error : bool, optional
        Whether a failed command raises (True) or returns empty text (False). Default True.
      timeout : float, optional
        The command's timeout, recorded with its subcommand. Default IPFSCt.TIMEOUT.
      return_errors : bool, optional
        Whether stdout and stderr come back as a pair, as `swarm disconnect` and `swarm connect` ask. Default False.

      Returns
      -------
      str or tuple
        The command's output, or ``(output, "")`` when ``return_errors`` is True.

      Raises
      ------
      Exception
        When the command fails and ``raise_on_error`` is True.

      Examples
      --------
      >>> run_command(["ipfs", "bitswap", "ledger", "RelayId"], raise_on_error=False, timeout=5)
      """
      engine.commands.append((cmd_list[1], timeout))
      if cmd_list[1] in engine.answers:
        # `ipfs bitswap ledger <peer>` names the peer it was asked about.
        output = engine.answers[cmd_list[1]].format(peer=cmd_list[-1])
        # The swarm wrappers ask for (stdout, stderr), as the real runner gives them.
        return (output, "") if return_errors else output
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
        # Like the real __run_command: a failed command returns "" (and "" for stderr when both are asked for).
        return ("", "") if return_errors else ""
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
    # No reconnect of the relay is due, as _build leaves it; a RELAY DATA PATH line sets it.
    engine._R1FSEngine__relay_reconnect_peer = None
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

  def test_every_cid_entry_refuses_a_value_that_is_not_a_bare_cid_and_says_so_in_red(self):
    """Whatever show_logs is: such a value is a caller bug or an attack. Nothing is run, sent or deleted."""
    engine = self._with_relay_api(self._engine())
    keep, cids = self._sandbox(engine)
    cids += ("--help", "QmA&arg=QmB", "Qm١", "QmA\n")  # an option, a relay parameter, a non-ASCII digit
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    entries = {
      "get_file": (lambda cid, **kw: engine.get_file(cid, show_logs=False, **kw), None),
      "delete_file": (lambda cid, **kw: engine.delete_file(cid, cleanup_local_files=True, show_logs=False, **kw), False),
      "unpin_file": (lambda cid, **kw: engine.unpin_file(cid, show_logs=False, **kw), False),
      "is_pinned": (lambda cid: engine.is_pinned(cid), False),
      "is_cid_available": (lambda cid: engine.is_cid_available(cid), False),
      "cleanup_downloads": (lambda cid: engine.cleanup_downloads(cid, show_logs=False), 0),
    }
    with mock.patch.object(r1fs.requests, "post") as post:
      for cid in cids:
        for name, (call, failure) in entries.items():
          with self.subTest(entry=name, cid=cid):
            del logs[:]
            self.assertIs(call(cid), failure)
            self.assertEqual(logs, [(f"Invalid CID {cid!r}: a CID must be a non-empty string of at most 255 ASCII "
                                     "letters and digits", "r")])
        for name in ("get_file", "delete_file", "unpin_file"):
          with self.subTest(entry=name, cid=cid, raise_on_error=True):
            with self.assertRaises(ValueError):
              entries[name][0](cid, raise_on_error=True)
    self.assertEqual([path for path in keep if not os.path.exists(path)], [])
    self.assertEqual(engine.commands, [])
    post.assert_not_called()
    self.assertEqual(engine._R1FSEngine__relay_heal_pending, set())

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

  def test_cid_unpinned_while_its_heal_waits_is_not_pinned_on_the_relay_again(self):
    """QmB's read fails while QmA is being published, then QmB is unpinned with success."""
    engine = self._with_relay_api(self._engine(reachable=False))
    engine._R1FSEngine__relay_retry_queue["QmA"] = {"cid": "QmA", "queued_at": "t0"}
    engine.relay_gate.clear()
    engine._R1FSEngine__relay_in_background(show_logs=False)  # a pass starts for the queue
    self.assertTrue(engine.relay_entered.acquire(timeout=10))  # the publication of QmA hangs
    self.assertIsNone(engine.get_json("QmB", timeout=10, show_logs=False))  # its heal waits for the pass
    # QmB was never pinned here, so the local `ipfs pin rm` answers "not pinned"; the relay held it, so pin/rm succeeds.
    unpinned = mock.Mock(status_code=200, text="")
    with mock.patch.object(r1fs.requests, "post", return_value=unpinned):
      self.assertTrue(engine.unpin_file("QmB", show_logs=False))
    self.assertNotIn("QmB", engine._R1FSEngine__relay_heal_pending)
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [("QmA", "r1fs-relay")])  # no relay pin/add of QmB after its unpin

  def test_cid_unpinned_while_an_earlier_heal_of_the_same_snapshot_runs_is_not_healed(self):
    engine = self._with_relay_api(self._engine())
    engine._R1FSEngine__relay_heal_pending.update({"QmB", "QmC"})
    engine.relay_gate.clear()
    engine._R1FSEngine__relay_in_background(show_logs=False)  # empty queue: one heal snapshot of both CIDs
    self.assertTrue(engine.relay_entered.acquire(timeout=10))  # the first heal of the snapshot hangs
    healing = engine.relay_calls[0][0]
    waiting = ({"QmB", "QmC"} - {healing}).pop()  # still in the snapshot, its heal not started
    with mock.patch.object(r1fs.requests, "post", return_value=mock.Mock(status_code=200, text="")):
      self.assertTrue(engine.unpin_file(waiting, show_logs=False))
    self._release_relay(engine)
    self.assertEqual(engine.relay_calls, [(healing, "r1fs-relay")])

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

  def test_relay_unpin_checks_the_relay_certificate_whatever_the_configured_path(self):
    """
    The relay pin/rm verifies the relay's certificate: with the configured file, or the default check.

    A configured certificate file is the ``verify`` value of the request. With no path (None) or an empty one
    the value is True, the default check of requests; an empty path passed as it is would not get that check.
    """
    # Certificate path stored on the engine -> the ``verify`` value the relay request must carry.
    expected = {"/certs/relay.crt": "/certs/relay.crt", None: True, "": True}
    for path, verify in expected.items():
      with self.subTest(path=path):
        engine = self._with_relay_api(self._engine())
        # The certificate path as maybe_start_ipfs stores it.
        engine._R1FSEngine__ipfs_certificate_path = path
        # The relay answers 200, so the unpin succeeds and only the arguments of the request are in question.
        with mock.patch.object(r1fs.requests, "post", return_value=mock.Mock(status_code=200, text="")) as post:
          self.assertTrue(engine.unpin_file("QmLive", show_logs=False))
        # Exactly one request went out...
        post.assert_called_once()
        # ...the relay pin/rm...
        self.assertEqual(post.call_args.args[0], "https://relay.invalid/api/v0/pin/rm")
        # ...and it carries the certificate file, or True, never an empty value.
        self.assertEqual(post.call_args.kwargs["verify"], verify)
        # True itself, not a value that only compares equal to it (assertEqual(1, True) passes).
        self.assertIs(type(post.call_args.kwargs["verify"]), type(verify))

  def _confirmed(self, engine, cid, at):
    """Record, as __publish_cid_to_relay does, that the relay answered a pin/add of ``cid`` with 200 at ``at``."""
    engine._R1FSEngine__relay_publication_status[cid] = {
      "relay_status": "published", "relay_published": True, "relay_last_success_at": _iso(at)}

  def _boxed_lines(self, engine):
    """Keep the boxed log lines of ``engine`` as (message, color)."""
    lines = []

    def log(message, *args, color=None, boxed=False, **kwargs):
      if boxed:
        lines.append((message, color))

    engine.P = log
    return lines

  def test_failed_read_of_a_cid_the_relay_accepted_before_it_prints_one_boxed_red_line(self):
    """
    Even with show_logs=False, as dAuth reads: the relay held the CID before the read, the read got nothing.

    The read prints its one RELAY DATA PATH line after its two checks; the reconnect that line asks for runs
    on the background pass, which adds its two commands and a boxed line of its own.
    """
    # A read whose get takes all of its 10 s and finds nothing.
    engine = self._engine(reachable=False, get_seconds=10)
    # The relay accepted the CID 60 s before the read.
    self._confirmed(engine, "QmGone", at=engine.now - 60)
    # A direct connection to the relay, and a connection to another peer through the relay's circuit.
    engine.answers = {"swarm": RELAY + "\n" + RELAY + "/p2p-circuit/p2p/OtherPeer", "bitswap": LEDGER}
    # Every boxed line, in order.
    lines = self._boxed_lines(engine)
    # The engine's clock is the test's, so the seconds in the line are known.
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      # The read returns nothing.
      self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
    # The read's background pass, with its reconnect, is over before anything is checked.
    self._release_relay(engine)
    # The read's own line comes first: what the relay accepted and when, the seconds waited, the link, the ledger.
    self.assertEqual(lines[0], (
      f"RELAY DATA PATH: relay {RELAY} accepted QmGone at 1970-01-01T00:15:40Z, but this node got nothing in 10 s. "
      "Direct link: True. Ledger for RelayId Debt ratio: 0.000000 Exchanges: 0 Bytes sent: 0 Bytes received: 0. "
      # The count of such reads, and the line's color, red.
      "1 such read(s) since start.", "r"))
    # Then only the reconnect's line.
    self.assertEqual(len(lines), 2)
    # The get and the two checks (5 s each) on the reader's thread, then the pass's disconnect (5 s) and dial (15 s).
    self.assertEqual(engine.commands, [("get", 10), ("swarm", 5), ("bitswap", 5), ("swarm", 5), ("swarm", 15)])

  def test_repeat_within_600s_prints_nothing_and_the_next_line_has_the_count(self):
    """A failed read within 600 s of a line is only counted; the next line, with its reconnect, comes at 600 s."""
    # Reads that find nothing.
    engine = self._engine(reachable=False)
    # The relay accepted the CID 60 s before the first read.
    self._confirmed(engine, "QmGone", at=engine.now - 60)
    # A direct link to the relay and an empty ledger.
    engine.answers = {"swarm": RELAY, "bitswap": LEDGER}
    # Every boxed line, in order.
    lines = self._boxed_lines(engine)
    # The engine's clock is the test's, so each read happens at a chosen time.
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      # A read at the start, one 1 s before the 600 s are over, and one when they are.
      for now in (1000.0, 1599.0, 1600.0):
        # The clock of this read.
        engine.now = now
        # The read returns nothing.
        self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
        # This read's background pass ends before the next read, so the commands come in a fixed order.
        self._release_relay(engine)
    # Two data-path lines, each followed by its reconnect's line.
    self.assertEqual(len(lines), 4)
    # The second data-path line counts all three reads.
    self.assertTrue(lines[2][0].endswith(" 3 such read(s) since start."))
    # The read at +599 s ran only its get, and its pass reconnected nothing.
    self.assertEqual([command for command, _ in engine.commands],
                     ["get", "swarm", "bitswap", "swarm", "swarm", "get", "get", "swarm", "bitswap", "swarm", "swarm"])

  def test_unconfirmed_late_or_healing_cids_and_good_reads_run_no_extra_command(self):
    """
    Only a 200 recorded before the read began counts, and a good read is left alone.

    Neither runs a command after its get, on the reader's thread or on the background pass: no check of the
    link and no reconnect of the relay.
    """
    # Relay statuses that do not show the relay held the CID before the read, by name.
    statuses = {
      "never seen": None,
      "queued": {"relay_status": "queued", "relay_published": False},
      "healing after an earlier 200": {"relay_status": "publishing", "relay_published": False,
                                       "relay_last_success_at": _iso(940)},
      # The read starts at 1000.0, whose text has no fraction: as text, this later time sorts before it.
      "accepted during the read": {"relay_status": "published", "relay_published": True,
                                   "relay_last_success_at": _iso(1000.5)},
    }
    # Each status in its own sub-test.
    for name, status in statuses.items():
      with self.subTest(status=name):
        # A read that finds nothing.
        engine = self._engine(reachable=False, get_seconds=10)
        if status is not None:
          # The CID's relay status before the read.
          engine._R1FSEngine__relay_publication_status["QmGone"] = status
        # The answers a check or a reconnect would get, so any such command would show.
        engine.answers = {"swarm": RELAY, "bitswap": LEDGER}
        # Every boxed line, in order.
        lines = self._boxed_lines(engine)
        # The engine's clock is the test's, so the read starts at 1000.0.
        with mock.patch.object(r1fs.time, "time", lambda: engine.now):
          # The read returns nothing.
          self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
        # The read's background pass is over, so a reconnect it ran would be in the commands below.
        self._release_relay(engine)
        # Only the get, and no line.
        self.assertEqual((engine.commands, lines), ([("get", 10)], []))
    # A good read.
    engine = self._engine()
    # The relay accepted the CID 60 s before the read.
    self._confirmed(engine, "QmLive", at=engine.now - 60)
    # The answers a check or a reconnect would get, so any such command would show.
    engine.answers = {"swarm": RELAY, "bitswap": LEDGER}
    # Every boxed line, in order.
    lines = self._boxed_lines(engine)
    # The engine's clock is the test's.
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      # The read returns the document.
      self.assertEqual(engine.get_json("QmLive", timeout=10, show_logs=False), DOC)
    # A pass, if one started, is over before the check.
    self._release_relay(engine)
    # Only the get and its pin, and no line.
    self.assertEqual((engine.commands, lines), ([("get", 10), ("pin", 10)], []))

  def test_empty_ledger_answer_is_reported_as_unreadable_and_the_read_still_returns_none(self):
    """A ledger command that answers nothing is said as unreadable, and a link only through a circuit as not direct."""
    # A read that finds nothing.
    engine = self._engine(reachable=False)
    # The relay accepted the CID 60 s before the read.
    self._confirmed(engine, "QmGone", at=engine.now - 60)
    # The only connection to the relay goes through another relay's circuit, so it is not a direct link.
    engine.answers = {"swarm": "/dns4/other.invalid/tcp/4001/p2p/OtherRelay/p2p-circuit/p2p/RelayId", "bitswap": ""}
    # Every boxed line, in order.
    lines = self._boxed_lines(engine)
    # The engine's clock is the test's.
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      # The read still returns nothing.
      self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
    # The read's background pass, which adds the reconnect's line, is over before anything is checked.
    self._release_relay(engine)
    # The read's line and the reconnect's line.
    self.assertEqual(len(lines), 2)
    # The read's line says the link is not direct and the ledger unreadable.
    self.assertIn(" Direct link: False. Ledger unreadable. 1 such read(s) since start.", lines[0][0])

  def test_relay_multiaddr_without_tcp_port_is_reported_without_the_two_commands(self):
    """
    R1FS can start with such a relay through ipfs swarm connect; there is no peer id to look up then.

    The line says the two checks were not run, and no reconnect is asked for: once the read's background pass is
    over, the get is still the only command.
    """
    # A read that finds nothing.
    engine = self._engine(reachable=False)
    # A relay multiaddr with no tcp port, for which __parse_multiaddr returns None.
    engine._R1FSEngine__ipfs_relay = "/dns4/relay.invalid/udp/4001/quic-v1/p2p/RelayId"
    # The relay accepted the CID 60 s before the read.
    self._confirmed(engine, "QmGone", at=engine.now - 60)
    # Every boxed line, in order.
    lines = self._boxed_lines(engine)
    # The engine's clock is the test's.
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      # The read returns nothing.
      self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
    # The read's background pass is over, so a reconnect it ran would be in the commands below.
    self._release_relay(engine)
    # Only the get: no check of the link and no reconnect.
    self.assertEqual(engine.commands, [("get", 10)])
    # The line says why the link and ledger were not checked.
    self.assertIn("so the link and ledger were not checked. 1 such read(s)", lines[0][0])

  def test_reported_read_reconnects_the_relay_once_per_printed_line_on_the_background_pass(self):
    """
    After a RELAY DATA PATH line, the background pass closes the relay link by peer id and dials it once.

    The two commands run on the "r1fs-relay" pass, not on the reader's thread, with 5 s and 15 s bounds, once per
    printed line (here lines 600 s apart, each read's pass over before the next read); the outcome is said in a
    boxed red line: "connected" with Kubo's answer when the dial got through, "dial failed" with Kubo's error when
    it did not.
    """
    # Kubo's answer to the dial as (stdout, stderr), as the real runner gives it, and the outcome the line says.
    for answer, said in ((("connect RelayId success", ""), "connected (connect RelayId success)"),
                         (("", "Error: connect RelayId failure: refused"),
                          "dial failed (Error: connect RelayId failure: refused)")):
      # Each answer in its own sub-test, on an engine of its own.
      with self.subTest(said=said):
        # Reads that find nothing.
        engine = self._engine(reachable=False)
        # The relay accepted the CID 60 s before the first read.
        self._confirmed(engine, "QmGone", at=engine.now - 60)
        # A direct link to the relay and an empty ledger, as on a blind link.
        engine.answers = {"swarm": RELAY, "bitswap": LEDGER}
        # The fake `ipfs` of _engine, kept for every command other than the reconnect's two.
        run_command = engine._R1FSEngine__run_command
        # Each reconnect command as (command line, timeout, thread name), in order.
        reconnects = []

        def kubo_reconnect(cmd_list, **kwargs):
          """
          Note `swarm disconnect` and `swarm connect` with their thread, and answer them as Kubo does.

          Parameters
          ----------
          cmd_list : list
            The command, ``["ipfs", <subcommand>, ...]``.
          **kwargs
            The runner's keyword arguments; the reconnect's two commands always pass ``timeout``.

          Returns
          -------
          str or tuple
            ``(stdout, stderr)`` for the two reconnect commands: the disconnect succeeds, the dial gets ``answer``.
            Any other command gets the answer of the fake runner of _engine.

          Examples
          --------
          >>> kubo_reconnect(["ipfs", "swarm", "disconnect", "/p2p/RelayId"], timeout=5)
          ('disconnect RelayId success', '')
          """
          if cmd_list[1:3] not in (["swarm", "disconnect"], ["swarm", "connect"]):
            # Any other command gets the fake answer of _engine.
            return run_command(cmd_list, **kwargs)
          # Which command, naming what, with which bound, on which thread.
          reconnects.append((" ".join(cmd_list[1:]), kwargs["timeout"], threading.current_thread().name))
          if cmd_list[2] == "disconnect":
            # Kubo's answer when it closed the link, as (stdout, stderr): both wrappers ask for the two.
            return "disconnect RelayId success", ""
          # The dial gets this sub-test's answer: accepted, or refused with Kubo's error on stderr.
          return answer

        # Put the Kubo answers in place of the fake ones for the reconnect.
        engine._R1FSEngine__run_command = kubo_reconnect
        # Every boxed line, in order.
        lines = self._boxed_lines(engine)
        # The engine's clock is the test's, so each read happens at a chosen time.
        with mock.patch.object(r1fs.time, "time", lambda: engine.now):
          # A line at 1000 s, none at 1599 s, the next at 1600 s.
          for now in (1000.0, 1599.0, 1600.0):
            # The clock of this read.
            engine.now = now
            # The read returns nothing.
            self.assertIsNone(engine.get_json("QmGone", timeout=10, show_logs=False))
            # This read's background pass ends before the next read.
            self._release_relay(engine)
        # One disconnect by peer id alone, then one dial of the relay, both on the pass.
        reconnect = [("swarm disconnect /p2p/RelayId", 5, "r1fs-relay"), (f"swarm connect {RELAY}", 15, "r1fs-relay")]
        # Once per line, so twice.
        self.assertEqual(reconnects, reconnect * 2)
        # The outcome line of the reconnect, with Kubo's answer to the dial.
        outcome = (f"RELAY DATA PATH: link to relay {RELAY} closed and dialed again: {said}.", "r")
        # Each one right after the line that asked for it.
        self.assertEqual(lines[1::2], [outcome, outcome])
        # The two data-path lines, before them.
        self.assertEqual([message.startswith(f"RELAY DATA PATH: relay {RELAY} accepted") for message, _ in lines[0::2]],
                         [True, True])

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

  def test_dangling_link_left_at_the_download_path_is_removed_by_the_next_read(self):
    """
    A link whose target does not exist, left at ``<downloads>/<cid>``, is removed before the next get.

    ``os.path.exists`` follows a link and answers False for a dangling one, so a clean-up that asks it skips
    the link, which then stays at the path `ipfs get` writes to. The read must remove the link itself. The
    last check is a guard and not the proof (it also holds without the fix): the clean-up only unlinks.
    """
    engine = self._engine()
    # A folder outside the downloads folder, removed after the test.
    outside = tempfile.mkdtemp(prefix="r1fs_outside_")
    self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
    # The name in it that the link points at; it does not exist and must never come to exist.
    target = os.path.join(outside, "missing")
    # The leftover of an earlier refused read: a link at the CID's download path with no target behind it.
    link = os.path.join(engine._R1FSEngine__downloads_dir, "QmLinked")
    os.symlink(target, link)
    # The fake `ipfs` of _engine, kept to run every command once the output path was looked at.
    run_command = engine._R1FSEngine__run_command
    # What each get found at its output path: True when an old entry was still there.
    found = []

    def get_sees(cmd_list, **kwargs):
      """Note whether anything is still at the output path when `ipfs get` runs, then run the fake command."""
      if cmd_list[1] == "get":
        # lexists: the question is whether the link itself is still there, not whether its target is.
        found.append(os.path.lexists(cmd_list[-1]))
      return run_command(cmd_list, **kwargs)

    # Put the observing command in place of the fake one for this read.
    engine._R1FSEngine__run_command = get_sees
    # A good read: with the link gone the fake get writes a real folder and the document comes back.
    self.assertEqual(engine.get_json("QmLinked", show_logs=False), DOC)
    # The get found its output path empty, so the link was removed before it ran.
    self.assertEqual(found, [False])
    # A guard: the clean-up only unlinks, so nothing was created where the link pointed.
    self.assertFalse(os.path.lexists(target))

  def test_cid_rule_has_a_length_bound_and_a_refused_value_is_shown_cut_to_100_characters(self):
    """A CID is a folder name under the downloads folder (NAME_MAX 255), and a huge refused value made a huge line."""
    engine = self._with_relay_api(self._engine())
    logs = self._logs(engine)
    rule = ": a CID must be a non-empty string of at most 255 ASCII letters and digits"
    with mock.patch.object(r1fs.requests, "post") as post:
      self.assertIsNone(engine.get_file("A" * 256, show_logs=False))
      self.assertFalse(engine.unpin_file("A" * 256, show_logs=False))
      self.assertFalse(engine.is_pinned("A" * 256))
      self.assertIsNone(engine.get_file("/" * 1_000_000, show_logs=False))
      self.assertIsNone(engine.add_json(DOC, fn="/" * 1_000_000, show_logs=False))
    post.assert_not_called()
    self.assertEqual(engine.commands, [])  # no `ipfs` command saw these values
    # repr() cut to 100 characters: the opening quote and the first 99 characters of the value.
    self.assertEqual(logs, [(f"Invalid CID '{'A' * 99}{rule}", "r")] * 3 + [
      (f"Invalid CID '{'/' * 99}{rule}", "r"),
      (f"Invalid file name '{'/' * 99}: a file name must have no path part and must not be '', '.' or '..'", "r")])
    # The longest value that fits a folder name still reaches `ipfs get`.
    self.assertEqual(engine.get_json("A" * 255, show_logs=False), DOC)
    self.assertEqual(engine.commands[0][0], "get")

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

  def _relay_url(self, post):
    """The URL the relay receives for the last call of the mocked requests.post."""
    call = post.call_args
    return r1fs.requests.Request("POST", call.args[0], params=call.kwargs.get("params")).prepare().url

  def test_relay_requests_carry_the_cid_as_a_parameter_and_the_relay_gets_the_same_url(self):
    engine = self._with_relay_api(self._engine())
    publish = R1FSEngine._R1FSEngine__publish_cid_to_relay  # the real one: _engine fakes it on the instance
    with mock.patch.object(r1fs.requests, "post", return_value=mock.Mock(status_code=200, text="")) as post:
      self.assertTrue(publish(engine, "QmLive", retries=1, show_logs=False))
      self.assertEqual(post.call_args.kwargs["params"], {"arg": "QmLive"})
      self.assertEqual(self._relay_url(post), "https://relay.invalid/api/v0/pin/add?arg=QmLive")
      self.assertTrue(engine.unpin_file("QmLive", show_logs=False))
      self.assertEqual(post.call_args.kwargs["params"], {"arg": "QmLive"})
      self.assertEqual(self._relay_url(post), "https://relay.invalid/api/v0/pin/rm?arg=QmLive")
      # A value with '&' that reaches the relay call stays one `arg` value instead of adding a second one.
      publish(engine, "QmA&arg=QmB", retries=1, show_logs=False)
      self.assertEqual(parse_qs(urlsplit(self._relay_url(post)).query), {"arg": ["QmA&arg=QmB"]})

  def _logs(self, engine):
    """Keep every line ``engine`` logs through P as (message, color)."""
    logs = []
    engine.P = lambda message, *args, color=None, **kwargs: logs.append((message, color))
    return logs

  def _relay_api(self, engine, add=(200, ""), rm=(200, "")):
    """
    Let the engine send its real relay requests to a fake relay API.

    Parameters
    ----------
    engine : R1FSEngine
      The engine from ``_engine``; its fake __publish_cid_to_relay is removed, so the real one runs.
    add, rm : tuple
      ``(status code, text)`` the relay answers to pin/add and to pin/rm.

    Returns
    -------
    types.SimpleNamespace
      ``post`` (to patch requests.post with), ``calls`` (("add" | "rm", cid) in order), ``gate`` (cleared: a
      pin/add waits at the relay), ``entered`` (released when a pin/add reaches the relay), and ``add`` and
      ``rm``, the answers, which a test can change between two requests.

    Examples
    --------
    >>> relay = self._relay_api(engine, add=(503, "busy"))
    """
    del engine._R1FSEngine__publish_cid_to_relay
    relay = types.SimpleNamespace(calls=[], gate=threading.Event(), entered=threading.Semaphore(0), add=add, rm=rm)
    relay.gate.set()

    def post(url, params=None, **kwargs):
      kind = url.rsplit("/", 1)[-1]
      relay.calls.append((kind, params["arg"]))
      if kind == "add":
        relay.entered.release()
        relay.gate.wait(10)
      status, text = relay.add if kind == "add" else relay.rm
      return mock.Mock(status_code=status, text=text)

    relay.post = post
    return relay

  def test_heal_set_is_bounded_and_a_refused_heal_is_said_in_red_at_most_once_per_600s(self):
    """Each waiting heal costs relay requests before every queued publication, so failing reads cannot grow it."""
    engine = self._engine(reachable=False)
    logs = self._logs(engine)
    waiting = {f"QmWait{i}" for i in range(IPFSCt.RELAY_HEAL_PENDING_LIMIT)}
    engine._R1FSEngine__relay_heal_pending.update(waiting)
    self.assertTrue(engine._R1FSEngine__relay_busy.acquire(blocking=False))  # a pass runs: reads only leave a heal
    with mock.patch.object(r1fs.time, "time", lambda: engine.now):
      for now, cid in [(1000.0, "QmNew1"), (1599.0, "QmNew2"), (1600.0, "QmNew3"), (1600.0, "QmWait0")]:
        engine.now = now
        self.assertIsNone(engine.get_json(cid, timeout=10, show_logs=False))
    engine._R1FSEngine__relay_busy.release()
    # Full: the new heals were refused and the waiting ones kept; a CID that already waits is not refused.
    self.assertEqual(engine._R1FSEngine__relay_heal_pending, waiting)
    full = f"Relay heal set full ({IPFSCt.RELAY_HEAL_PENDING_LIMIT} CIDs wait): "
    rest = " is not remembered for a relay heal; its next failed read asks again"
    self.assertEqual([line for line in logs if line[0].startswith(full)], [
      (f"{full}QmNew1{rest} (1 since start, at most one such line per 600 s).", "r"),
      (f"{full}QmNew3{rest} (3 since start, at most one such line per 600 s).", "r")])

  def test_unpin_of_a_cid_not_pinned_here_goes_on_to_the_relay_whatever_raise_on_error(self):
    """Deleting a CID this node never pinned is a normal call: Kubo's "not pinned" is not an error."""
    engine = self._with_relay_api(self._engine(reachable=False))  # never fetched here, so never pinned here
    engine._R1FSEngine__relay_retry_queue["QmB"] = {"cid": "QmB", "queued_at": "t0"}
    logs = self._logs(engine)
    with mock.patch.object(r1fs.requests, "post", return_value=mock.Mock(status_code=200, text="")) as post:
      self.assertTrue(engine.unpin_file("QmB", show_logs=False))
      self.assertTrue(engine.unpin_file("QmB", show_logs=False, raise_on_error=True))
      self.assertTrue(engine.delete_file("QmB", show_logs=False, raise_on_error=True))
    self.assertEqual(post.call_count, 3)  # each one went on to the relay pin/rm
    self.assertEqual(logs, [])
    self.assertNotIn("QmB", engine._R1FSEngine__relay_retry_queue)

  def test_failed_local_unpin_is_said_in_red_and_the_relay_is_not_told(self):
    """A daemon that does not answer: with raise_on_error=False the empty answer passed as an unpin."""
    engine = self._with_relay_api(self._engine(pin_fails=True))
    engine._R1FSEngine__relay_retry_queue["QmB"] = {"cid": "QmB", "queued_at": "t0"}
    engine._R1FSEngine__relay_heal_pending.add("QmB")
    folder = os.path.join(engine._R1FSEngine__downloads_dir, "QmB")
    os.makedirs(folder)
    logs = self._logs(engine)
    with mock.patch.object(r1fs.requests, "post", return_value=mock.Mock(status_code=200, text="")) as post:
      self.assertFalse(engine.unpin_file("QmB", show_logs=False))
      self.assertFalse(engine.delete_file("QmB", cleanup_local_files=True, show_logs=False))
      with self.assertRaises(RuntimeError):
        engine.unpin_file("QmB", show_logs=False, raise_on_error=True)
    post.assert_not_called()
    failed = (f"Error unpinning CID QmB locally: Timeout expired after {IPFSCt.TIMEOUT}s for 'ipfs pin rm QmB'", "r")
    self.assertEqual(logs, [failed, failed])  # in red although show_logs is False
    # It may still be pinned here: still queued for the relay, its heal still waiting, its files kept.
    self.assertIn("QmB", engine._R1FSEngine__relay_retry_queue)
    self.assertIn("QmB", engine._R1FSEngine__relay_heal_pending)
    self.assertTrue(os.path.isdir(folder))

  def test_heal_running_when_its_cid_is_unpinned_records_nothing_and_its_pin_is_undone(self):
    """The heal's pin/add can reach the relay after the unpin's pin/rm; it is undone unless the CID is wanted again."""
    expected = {
      "undone": [("add", "QmB"), ("rm", "QmB"), ("rm", "QmB")],
      "relay already dropped it": [("add", "QmB"), ("rm", "QmB"), ("rm", "QmB")],  # Kubo's "not pinned": done
      "undo refused": [("add", "QmB"), ("rm", "QmB"), ("rm", "QmB")],  # said in red although show_logs is False
      "pinned here again": [("add", "QmB"), ("rm", "QmB")],  # uploaded again under the same CID meanwhile
      "relay keeps its copy": [("add", "QmB")],  # unpin_remote=False: nothing is marked
    }
    # What the relay answers the undo's pin/rm; the unpin's own pin/rm gets 200.
    undo_answers = {"relay already dropped it": (500, '{"Message":"' + NOT_PINNED + '"}'), "undo refused": (503, "busy")}
    for case, calls in expected.items():
      with self.subTest(case=case):
        engine = self._with_relay_api(self._engine(reachable=False))
        relay = self._relay_api(engine)
        logs = self._logs(engine)
        engine._R1FSEngine__relay_heal_pending.add("QmB")
        relay.gate.clear()
        with mock.patch.object(r1fs.requests, "post", side_effect=relay.post):
          engine._R1FSEngine__relay_in_background(show_logs=False)
          self.assertTrue(relay.entered.acquire(timeout=10))  # the heal's pin/add of QmB is at the relay
          self.assertTrue(engine.unpin_file("QmB", unpin_remote=case != "relay keeps its copy", show_logs=False))
          relay.rm = undo_answers.get(case, relay.rm)
          if case == "pinned here again":
            engine.answers = {"pin": "{peer} recursive"}
          relay.gate.set()
          self._release_relay(engine)
        self.assertEqual(relay.calls, calls)
        published = case == "relay keeps its copy"
        self.assertEqual(engine.get_upload_status("QmB").get("relay_status"), "published" if published else None)
        self.assertIsNone(engine._R1FSEngine__relay_in_flight)  # it lived only while the request ran
        undo_failed = "Relay pin/rm to undo the pin of QmB, unpinned while the relay pinned it, failed: HTTP 503: busy"
        self.assertEqual([line for line in logs if line[0].startswith("Relay pin/rm to undo")],
                         [(undo_failed, "r")] if case == "undo refused" else [])

  def test_cid_uploaded_again_while_its_pin_is_undone_is_published_once_more(self):
    """The re-upload's `ipfs add` lands after the undo's check, and its relay pin/add before the undo's pin/rm."""
    engine = self._with_relay_api(self._engine(reachable=False))
    relay = self._relay_api(engine)
    pinned_on_relay = {}
    answer = relay.post

    def post(url, params=None, **kwargs):
      # The relay's own pinset: a pin/add pins the CID there, a pin/rm unpins it.
      response = answer(url, params=params, **kwargs)
      pinned_on_relay[params["arg"]] = url.endswith("/add")
      return response

    run_command = engine._R1FSEngine__run_command

    def run_command_with_reupload(cmd_list, **kwargs):
      output = run_command(cmd_list, **kwargs)
      if cmd_list[1:3] == ["pin", "ls"] and not engine.answers:
        # The undo's check found QmB not pinned here. The same content is uploaded again right after it, and
        # add_file's relay pin/add (on the caller's thread, never marked) is accepted before the undo's pin/rm.
        engine.answers = {"pin": "{peer} recursive"}
        engine._R1FSEngine__publish_cid_to_relay(cid="QmB", source_path="f", context="upload", show_logs=False)
      return output

    engine._R1FSEngine__run_command = run_command_with_reupload
    engine._R1FSEngine__relay_heal_pending.add("QmB")
    relay.gate.clear()
    with mock.patch.object(r1fs.requests, "post", side_effect=post):
      engine._R1FSEngine__relay_in_background(show_logs=False)
      self.assertTrue(relay.entered.acquire(timeout=10))  # the heal's pin/add of QmB is at the relay
      self.assertTrue(engine.unpin_file("QmB", show_logs=False))
      relay.gate.set()
      self._release_relay(engine)
    # The heal, the unpin, the re-upload, the undo, and the publication once more that puts the pin back.
    self.assertEqual(relay.calls, [("add", "QmB"), ("rm", "QmB"), ("add", "QmB"), ("rm", "QmB"), ("add", "QmB")])
    self.assertTrue(pinned_on_relay["QmB"])
    self.assertEqual(engine.get_upload_status("QmB").get("relay_status"), "published")

  def test_publication_running_when_its_cid_is_unpinned_is_not_queued_again(self):
    """The relay never got QmA, so the unpin's pin/rm fails and only the pass itself can keep QmA out of the queue."""
    for when in ("during its request", "between its check and its enqueue"):
      with self.subTest(when=when):
        engine = self._with_relay_api(self._engine())
        relay = self._relay_api(engine, add=(503, "busy"), rm=(500, '{"Message":"' + NOT_PINNED + '"}'))
        engine._R1FSEngine__relay_retry_queue["QmA"] = {"cid": "QmA", "queued_at": "t0"}
        unpinned = []
        if when == "during its request":
          relay.gate.clear()
        else:
          enqueue = engine._R1FSEngine__enqueue_relay_retry

          def unpin_then_enqueue(**kwargs):
            # The unpin lands after the pass found QmA unmarked and before it queues QmA again.
            unpinned.append(engine.unpin_file("QmA", show_logs=False))
            enqueue(**kwargs)

          engine._R1FSEngine__enqueue_relay_retry = unpin_then_enqueue
        with mock.patch.object(r1fs.requests, "post", side_effect=relay.post), mock.patch.object(r1fs.time, "sleep"):
          engine._R1FSEngine__relay_in_background(show_logs=False)
          if when == "during its request":
            self.assertTrue(relay.entered.acquire(timeout=10))  # attempt 1 of QmA's publication is at the relay
            unpinned.append(engine.unpin_file("QmA", show_logs=False))
            relay.gate.set()
          self._release_relay(engine)
        self.assertEqual(unpinned, [False])  # the relay answered "not pinned"
        self.assertNotIn("QmA", engine._R1FSEngine__relay_retry_queue)
        # No attempt after the unpin, and no undo since no pin got through.
        attempts = 1 if when == "during its request" else IPFSCt.RELAY_PIN_RETRY_COUNT
        self.assertEqual(relay.calls, [("add", "QmA")] * attempts + [("rm", "QmA")])

  def test_cid_queued_again_before_the_unpin_looks_at_the_request_is_dropped_by_its_second_pop(self):
    """The pass queues its failed QmA again between the unpin's first queue pop and its look at the request.

    The relay never had QmA, so the unpin's pin/rm fails and its final, success-only pop does not run."""
    for flight in (None, ["QmA", False]):  # the pass has ended by then, or still shows its request
      with self.subTest(flight=flight):
        engine = self._with_relay_api(self._engine())
        queue = engine._R1FSEngine__relay_retry_queue

        class QueuedAgainOnDiscard(set):
          """The heal set: unpin_file's discard is its step between the first queue pop and the look."""

          def discard(pending, cid):
            queue[cid] = {"cid": cid, "queued_at": "t0"}
            return set.discard(pending, cid)

        engine._R1FSEngine__relay_heal_pending = QueuedAgainOnDiscard()
        engine._R1FSEngine__relay_in_flight = flight
        not_pinned = mock.Mock(status_code=500, text='{"Message":"' + NOT_PINNED + '"}')
        with mock.patch.object(r1fs.requests, "post", return_value=not_pinned):
          self.assertFalse(engine.unpin_file("QmA", show_logs=False))
        self.assertNotIn("QmA", queue)
        self.assertEqual(flight, None if flight is None else ["QmA", True])  # a request still shown is marked

  def test_final_heal_failure_is_said_in_red_whatever_show_logs_at_most_once_per_600s(self):
    """Reads pass show_logs=False, so a relay that refuses heals was silent; an outage must not print per read."""
    engine = self._with_relay_api(self._engine(reachable=False))
    relay = self._relay_api(engine, add=(401, "unauthorized"))
    logs = self._logs(engine)
    with mock.patch.object(r1fs.requests, "post", side_effect=relay.post), mock.patch.object(r1fs.time, "sleep"), \
         mock.patch.object(r1fs.time, "time", lambda: engine.now):
      for now, cid in [(1000.0, "QmB1"), (1599.0, "QmB2"), (1600.0, "QmB3")]:
        engine.now = now
        self.assertIsNone(engine.get_json(cid, timeout=10, show_logs=False))
        self._release_relay(engine)
    self.assertEqual([line for line in logs if line[0].startswith("Relay")], [
      ("Relay heal of QmB1 failed: HTTP 401: unauthorized (1 since start, at most one such line per 600 s).", "r"),
      ("Relay heal of QmB3 failed: HTTP 401: unauthorized (3 since start, at most one such line per 600 s).", "r")])
    # A heal the relay accepts logs nothing with show_logs=False, as before.
    engine = self._with_relay_api(self._engine(reachable=False))
    relay = self._relay_api(engine)
    logs = self._logs(engine)
    with mock.patch.object(r1fs.requests, "post", side_effect=relay.post):
      self.assertIsNone(engine.get_json("QmB", timeout=10, show_logs=False))
      self._release_relay(engine)
    self.assertEqual(relay.calls, [("add", "QmB")])
    self.assertEqual([line for line in logs if line[0].startswith("Relay")], [])

  def _daemon_start(self, engine, connect_answer="connect success"):
    """Run __start_daemon against fake commands; return the order of what happened and the red lines."""
    events, red = [], []

    def run_command(cmd_list, raise_on_error=True, return_errors=False, **kwargs):
      events.append(" ".join(cmd_list[1:3]))
      # `bootstrap list` answers with the list the repository holds; `swarm connect` with the given answer.
      output = RELAY if cmd_list[1:3] == ["bootstrap", "list"] else connect_answer
      return (output, "") if return_errors else output

    engine._R1FSEngine__run_command = run_command
    engine.is_ipfs_daemon_running = lambda: events.append("api answers") or True
    engine.P = lambda msg, *args, **kwargs: red.append(msg) if kwargs.get("color") == "r" else None
    with mock.patch.object(r1fs.subprocess, "Popen", side_effect=lambda *args, **kwargs: events.append("daemon launched")):
      started = engine._R1FSEngine__start_daemon()
    return started, events, red

  def test_daemon_is_launched_with_no_bootstrap_peer_and_the_relay_is_dialed_once_its_api_answers(self):
    """
    The relay is dialed only once the API answers, right after every connection to it is closed by its peer id.

    A connection the relay opened while the daemon was being built is as blind as one the daemon dialed then,
    and `swarm connect` would keep it as already connected. The disconnect names the peer id alone, so it
    closes such a connection whatever address or port it came from.
    """
    # An engine whose Bootstrap list holds the relay (see _daemon_start).
    engine = self._engine()
    # The real disconnect, watched for what it names; it still runs through the fake commands of _daemon_start.
    real_disconnect = engine._R1FSEngine__swarm_disconnect
    # The watch is on for the start only.
    with mock.patch.object(engine, "_R1FSEngine__swarm_disconnect", wraps=real_disconnect) as disconnect:
      # One daemon start, in order of what happened.
      started, events, red = self._daemon_start(engine)
    # The API answered, so the start succeeded.
    self.assertTrue(started)
    # The list is read and emptied before the launch; only after the API answers is the relay disconnected, dialed
    # and put back.
    self.assertEqual(events, ["bootstrap list", "bootstrap rm", "daemon launched", "api answers",
                              # After the API answers: the disconnect, then the dial, then the relay back in the list.
                              "swarm disconnect", "swarm connect", "bootstrap add"])
    # Named by the relay's peer id alone, bounded at 5 s.
    disconnect.assert_called_once_with("/p2p/RelayId", timeout=5)
    # Nothing in red: the disconnect's answer is not read.
    self.assertEqual(red, [])

  def test_relay_that_cannot_be_dialed_after_the_start_is_said_in_red_and_still_put_back(self):
    started, events, red = self._daemon_start(self._engine(), connect_answer="failure: dial backoff")
    self.assertTrue(started)
    self.assertEqual(events[-2:], ["swarm connect", "bootstrap add"])
    self.assertEqual(len(red), 1)
    self.assertIn(RELAY, red[0])

  def test_relay_not_dialable_at_start_is_dialed_again_only_by_the_call_that_launched_the_daemon(self):
    """
    The call that launched the daemon dials the relay up to 6 times, 10 s apart, before R1FS is left off for the run.

    A relay that accepts the third dial starts R1FS. One that refuses all six leaves R1FS off and ends with the red
    line the single dial gave (the runner is a fake here; the real one also says each failed try in red). Each try
    but the last is bounded at 10 s and returns instead of raising; the last one is the dial of before. A call that
    finds the daemon already running, as a serving process does, dials once as before: a relay that refuses that
    dial leaves R1FS off with no pause and no further try, even one that would accept the third dial.
    """
    # A private IPFS home under a "_local_cache" folder, as maybe_start_ipfs accepts from IPFS_PATH.
    home = os.path.join(tempfile.mkdtemp(prefix="r1fs_start_"), "_local_cache", ".ipfs")
    # The whole private root is removed after the test.
    self.addCleanup(shutil.rmtree, os.path.dirname(os.path.dirname(home)), ignore_errors=True)
    # The home folder itself.
    os.makedirs(home)
    # An initialized repository, so no `ipfs init` runs.
    open(os.path.join(home, "config"), "w").close()
    # The dial of the relay, as each try sends it.
    dial = f"swarm connect {RELAY}"
    # The red line of a relay that cannot be dialed, as the single dial said it.
    failure = f"Error connecting to relay: Error while running 'ipfs {dial}': Error: connect RelayId failure: refused"
    # Whether this call launches the daemon, the dials the relay refuses, whether R1FS starts, the quiet tries
    # (10 s each) and the 10 s pauses that follow: a launching call whose relay accepts the third dial, one whose
    # relay refuses all six, and a call that finds the daemon running, whose relay refuses its one dial.
    for launch, refused, started, quiet, pauses in (
        (True, 2, True, 3, 2), (True, IPFSCt.RELAY_START_TRIES, False, 5, 5), (False, 2, False, 0, 0)):
      # Each case in its own sub-test, on an engine of its own.
      with self.subTest(launch=launch, refused=refused):
        # An engine with nothing started yet.
        engine = self._engine()
        # R1FS is not started, so maybe_start_ipfs runs.
        engine._R1FSEngine__ipfs_started = False
        # The settings _build gives it, used by the start-up message.
        engine._R1FSEngine__name, engine._R1FSEngine__debug = "default", False
        # The uploads folder, also in that message.
        engine._R1FSEngine__uploads_dir = engine._R1FSEngine__downloads_dir
        # Nothing known about this node's address and agent yet.
        engine._R1FSEngine__ipfs_address = engine._R1FSEngine__ipfs_agent = None
        # No daemon answers, so this call launches one; or the daemon already runs, as a serving process finds it.
        engine.is_ipfs_daemon_running = lambda: not launch
        # The daemon start, which answers at once; its own dial of the relay is tested with _daemon_start.
        engine._R1FSEngine__start_daemon = start_daemon = mock.Mock(return_value=True)
        # No swarm peer yet: the relay is not connected, so it is dialed.
        engine._get_swarm_peers = lambda: []
        # The same-host workaround is off ...
        engine._R1FSEngine__samehost_fix_enabled = lambda: False
        # ... has nothing to clean up ...
        engine._R1FSEngine__cleanup_samehost_relay_workaround = lambda: False
        # ... and nothing to apply after a start.
        engine._R1FSEngine__maybe_apply_samehost_relay_workaround = lambda: False
        # This node's peer id.
        engine._R1FSEngine__get_id = lambda: "SelfId"
        # A relay check that finds the relay once it is dialed.
        engine._check_and_record_relay_connection = lambda debug=False: True
        # Each dial as (command line, raises on failure, timeout), in order.
        dials = []

        def relay(cmd_list, raise_on_error=True, timeout=IPFSCt.TIMEOUT, **kwargs):
          """
          Answer `ipfs swarm connect` as Kubo and the real runner do: refused ``refused`` times, then accepted.

          Parameters
          ----------
          cmd_list : list
            The command, ``["ipfs", <subcommand>, ...]``.
          raise_on_error : bool, optional
            Whether a failed command raises (True) or returns "" (False). Default True.
          timeout : float, optional
            The command's bound, recorded with each dial. Default IPFSCt.TIMEOUT.
          **kwargs
            Any other keyword argument of the runner; not used.

          Returns
          -------
          str
            "" for the set-up commands of a launch (bootstrap and config) and for a refused quiet try; Kubo's
            success answer for a dial the relay accepts.

          Raises
          ------
          Exception
            The real runner's error, for a refused dial that raises on failure.

          Examples
          --------
          >>> relay(["ipfs", "swarm", "connect", RELAY], raise_on_error=False, timeout=10)
          ''
          """
          if cmd_list[1:3] != ["swarm", "connect"]:
            # The set-up commands before a launch (bootstrap and config) succeed with no output.
            return ""
          # Which dial, whether it raises on failure, and its bound.
          dials.append((" ".join(cmd_list[1:]), raise_on_error, timeout))
          if len(dials) > refused:
            # Kubo's answer to a dial it made.
            return "connect RelayId success"
          if not raise_on_error:
            # The real runner returns "" for a failed command it does not raise for.
            return ""
          # The real runner's error for a command that exits with an error.
          raise Exception(f"Error while running 'ipfs {dial}': Error: connect RelayId failure: refused")

        # Only the dials and the set-up commands of a launch reach the commands; everything else above is answered
        # in place.
        engine._R1FSEngine__run_command = relay
        # Every logged line as (message, color).
        logs = self._logs(engine)
        # The home in IPFS_PATH, and every wait recorded instead of waited for.
        with mock.patch.dict(os.environ, {"IPFS_PATH": home}), mock.patch.object(r1fs.time, "sleep") as sleep:
          # The relay settings as the node passes them; the key only has to decode.
          result = engine.maybe_start_ipfs(
            base64_swarm_key="a2V5a2V5a2V5", ipfs_relay=RELAY, ipfs_relay_api="https://relay.invalid",
            ipfs_api_key_username="x", ipfs_api_key_password="x", ipfs_certificate_path="/certs/relay.crt",
          )
        # R1FS starts only when the relay answered.
        self.assertIs(result, started)
        # The daemon is launched only when none answered.
        self.assertEqual(start_daemon.call_count, int(launch))
        # Quiet tries of 10 s until the relay answers; when it never does, those of a launching call and then the
        # dial of before, which is the only dial of a call that found the daemon running.
        self.assertEqual(dials, [(dial, False, IPFSCt.RELAY_START_TRY_TIMEOUT_SECONDS)] * quiet + (
          [] if started else [(dial, True, IPFSCt.TIMEOUT)]))
        # Before a launch the three 2 s checks for a running daemon; then a 10 s pause after each refused quiet try,
        # and no other wait.
        self.assertEqual(sleep.call_args_list,
                         [mock.call(2)] * 3 * launch + [mock.call(IPFSCt.RELAY_START_PAUSE_SECONDS)] * pauses)
        # Each refused quiet try is said in yellow with the next step.
        self.assertEqual([message for message, color in logs if color == "y"], [
          f"Relay {RELAY} could not be dialed (try {i} of 6), next try in 10 s." for i in range(1, pauses + 1)])
        # The start-up code's own red lines (the command runner is a fake here and says nothing): the line a launch
        # always gave, none when the relay answered, and otherwise exactly the failure line of before.
        self.assertEqual([message for message, color in logs if color == "r"],
                         ["IPFS daemon not running. Trying to start..."] * launch + ([] if started else [failure]))

if __name__ == "__main__":
  unittest.main()
