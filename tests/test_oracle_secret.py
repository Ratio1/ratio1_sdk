"""The oracle-only secret is kept in process memory: moved out of the environment, never written to it, never logged."""
# Serializes the results so a single search finds the value anywhere in them.
import json
# The process environment under test.
import os
# A child interpreter started with the variable in its environment, as a seed's node is.
import subprocess
# That interpreter is this one.
import sys
# A folder of its own for each engine's key file.
import tempfile
# The test framework.
import unittest
# Isolates the environment, the holder and the HTTP boundary.
from unittest import mock
# A fresh engine name per test: engines are per-name multitons.
from uuid import uuid4

# The logger a real engine needs.
from ratio1 import Logger
# The engine class that holds the secret.
from ratio1.bc.base import BaseBlockEngine
# The engine class a node builds.
from ratio1.bc import DefaultBlockEngine
# The names of the variable and of the dAuth fields.
from ratio1.const.base import dAuth
# The dAuth client stand-in that runs the SDK's own dauth_autocomplete with a mocked HTTP answer.
from test_dauth_autocomplete_logging import DAUTH_URL, _AutocompleteHarness


# An obvious fake: no real secret is ever used in a test.
FAKE_SECRET = "fake-oracle-secret-for-tests-only"
# What the answer carries in its place: the server encrypts the secret to the requesting node's key.
CIPHERTEXT = "fake-ciphertext-of-the-oracle-secret"


def _isolate(test):
  """
  Isolate: give one test its own environment and an empty holder, both restored after it.

  The environment is a patched copy without the secret's variable, and the class-wide holder of
  the SDK engine starts empty; the test's cleanups put both back as they were.

  Parameters
  ----------
  test : unittest.TestCase
    The test whose cleanups restore them.

  Returns
  -------
  None

  Examples
  --------
  >>> _isolate(self)   # in setUp
  """
  # A copy of the environment, restored after the test.
  env = mock.patch.dict(os.environ)
  # Started now.
  env.start()
  # Stopped by the test's cleanups.
  test.addCleanup(env.stop)
  # The variable starts unset.
  os.environ.pop(dAuth.DAUTH_ORACLE_SECRET_ENV_KEY, None)
  # The class-wide holder starts empty and gets its value back after the test.
  holder = mock.patch.object(BaseBlockEngine, "_BaseBlockEngine__oracle_secret", None)
  # Started now.
  holder.start()
  # Stopped by the test's cleanups.
  test.addCleanup(holder.stop)
  return


def _report_after_a_build():
  """
  Report: build an engine in this process and print what its environment block shows before and after.

  Meant as the only work of a child interpreter started with the variable in its environment, as a
  seed's node is started: the value then lies in the process's original environment block, which
  ``/proc/<pid>/environ`` shows to every other process of the container.

  Returns
  -------
  None
    Prints one JSON line, ``{"before": bool, "after": bool, "held": bool}``: whether the block shows
    the value before and after the build, and whether the build holds it in memory.

  Examples
  --------
  >>> _report_after_a_build()   # in a child started with the variable set to the fake value
  {"before": true, "after": false, "held": true}
  """
  # The block as the process got it at start, as another process reads it.
  with open("/proc/self/environ", "rb") as block:
    # Whether the value is in it.
    before = FAKE_SECRET.encode() in block.read()
  # A folder for the engine's key file, removed afterwards.
  with tempfile.TemporaryDirectory() as folder:
    # A silent logger there.
    log = Logger(lib_name="secret", base_folder=folder, app_folder="secret", silent=True)
    # The engine build, as at a node's start.
    DefaultBlockEngine(name="secret", log=log, config={"PEM_FILE": "secret.pem"})
  # The same block after the build.
  with open("/proc/self/environ", "rb") as block:
    # Whether the value is still in it.
    after = FAKE_SECRET.encode() in block.read()
  # One JSON line, the last the child prints, for the test that started it.
  print(json.dumps({"before": before, "after": after, "held": BaseBlockEngine.oracle_secret() == FAKE_SECRET}))


class EngineBuildTests(unittest.TestCase):
  """A built engine moves the variable from the environment into process memory."""

  def setUp(self):
    """
    Isolate the environment and the holder, and give the engines a temporary folder.

    Each test starts without the variable and with an empty holder, and its engines keep their
    key files in a folder that is removed after it.

    Returns
    -------
    None
    """
    # Environment and holder, restored after the test.
    _isolate(self)
    # The folder of the key files of this test's engines.
    tmp = tempfile.TemporaryDirectory()
    # Removed after the test.
    self.addCleanup(tmp.cleanup)
    # Its path, for the engines' loggers.
    self.folder = tmp.name
    # Every line the engines log.
    self.lines = []

  def _engine(self):
    """
    Build a new engine, under a name of its own, whose log lines are recorded.

    The engine has a silent logger in the test folder whose log call keeps each line in
    ``self.lines``; a new name makes the multiton run the engine build.

    Returns
    -------
    DefaultBlockEngine
      The engine; its lines are in ``self.lines``.

    Examples
    --------
    >>> engine = self._engine()
    """
    # A silent logger in the test folder.
    log = Logger(lib_name="secret", base_folder=self.folder, app_folder="secret", silent=True)
    # The engine logs through this call, replaced so each line is kept.
    log.P = lambda text, *args, **kwargs: self.lines.append(str(text))
    # A new name, so the multiton builds a new engine and its build runs.
    return DefaultBlockEngine(
      name="secret" + uuid4().hex, log=log, config={"PEM_FILE": "secret.pem"}, verbosity=1,
    )

  def test_the_build_takes_the_value_and_deletes_the_variable(self):
    """The value is held, the variable is gone from the environment, and only a value-free line is logged."""
    # The variable as it is set on a seed oracle.
    os.environ[dAuth.DAUTH_ORACLE_SECRET_ENV_KEY] = FAKE_SECRET
    # A node building its engine at start.
    self._engine()
    # The value is held in process memory.
    self.assertEqual(BaseBlockEngine.oracle_secret(), FAKE_SECRET)
    # The variable is gone.
    self.assertNotIn(dAuth.DAUTH_ORACLE_SECRET_ENV_KEY, os.environ)
    # The value is under no other name either.
    self.assertNotIn(FAKE_SECRET, os.environ.values())
    # One line says so.
    self.assertIn("Oracle secret moved from the environment into process memory.", "\n".join(self.lines))
    # No line carries the value.
    self.assertNotIn(FAKE_SECRET, "\n".join(self.lines))

  def test_a_later_engine_keeps_the_value(self):
    """A second engine of the same process finds no variable and does not clear the held value."""
    # The variable as it is set on a seed oracle.
    os.environ[dAuth.DAUTH_ORACLE_SECRET_ENV_KEY] = FAKE_SECRET
    # The first engine takes it.
    self._engine()
    # A second engine, built after the variable is gone.
    self._engine()
    # The value is still held.
    self.assertEqual(BaseBlockEngine.oracle_secret(), FAKE_SECRET)

  def test_an_empty_or_missing_variable_holds_nothing(self):
    """An empty value is deleted and not held; without the variable nothing changes."""
    # An empty value under the variable name.
    os.environ[dAuth.DAUTH_ORACLE_SECRET_ENV_KEY] = ""
    # An engine built with it.
    self._engine()
    # Nothing is held.
    self.assertIsNone(BaseBlockEngine.oracle_secret())
    # The empty variable is gone too.
    self.assertNotIn(dAuth.DAUTH_ORACLE_SECRET_ENV_KEY, os.environ)
    # An engine built with no variable at all.
    self._engine()
    # Still nothing held.
    self.assertIsNone(BaseBlockEngine.oracle_secret())

  @unittest.skipUnless(os.path.exists("/proc/self/environ"), "the environment block is read through /proc")
  def test_a_seed_process_environment_block_no_longer_shows_the_value(self):
    """A process started with the variable, as a seed's node is, holds the value after the build, and its original
    environment block, which /proc/<pid>/environ shows to other processes, no longer has it."""
    # A child of this interpreter with the variable in its environment from the start; it imports this file.
    done = subprocess.run(
      [sys.executable, "-c", "import test_oracle_secret; test_oracle_secret._report_after_a_build()"],
      cwd=os.path.dirname(os.path.abspath(__file__)),
      env={**os.environ, dAuth.DAUTH_ORACLE_SECRET_ENV_KEY: FAKE_SECRET},
      capture_output=True, text=True, timeout=120,
    )
    # The child ended well; otherwise its errors are shown.
    self.assertEqual(done.returncode, 0, done.stderr)
    # The block had the value at start, does not have it after the build, and the value is held.
    self.assertEqual(json.loads(done.stdout.splitlines()[-1]), {"before": True, "after": False, "held": True})


class DauthClientTests(unittest.TestCase):
  """The dAuth client asks with the flag and keeps a received secret in memory only."""

  def setUp(self):
    """
    Isolate the environment and the holder, and answer every dAuth request with the encrypted secret.

    The client is the SDK's own ``dauth_autocomplete`` on a stand-in engine; every HTTP request
    gets an oracle's answer with one env key and the secret encrypted to the requester. The
    stand-in's decrypt turns ``CIPHERTEXT`` into the fake secret and anything else into None.

    Returns
    -------
    None
    """
    # Environment and holder, restored after the test.
    _isolate(self)
    # The SDK's own dauth_autocomplete on a stand-in engine that records its log lines and signed requests.
    self.engine = _AutocompleteHarness()
    # Its decryption: the fake secret from CIPHERTEXT only, None for anything else; the calls are recorded.
    self.engine.decrypt = mock.Mock(side_effect=lambda encrypted_data_b64, sender_address: {
      CIPHERTEXT: FAKE_SECRET}.get(encrypted_data_b64))
    # A served HTTP answer.
    self.response = mock.Mock(status_code=200)
    # An oracle's answer: one env key and the encrypted secret.
    self.response.json.return_value = {
      "result": {
        # The secret's field carries only its encrypted form, as a server sends it.
        "auth": {"EE_TEST_KEY": "plain-value", dAuth.DAUTH_ORACLE_SECRET: CIPHERTEXT},
        "server_alias": "oracle",
        "EE_SENDER": "0xai_oracle",
      },
    }
    # Every request gets that answer, and no VPN is assumed.
    for target, kwargs in [
      ("ratio1.bc.base.requests.post", {"return_value": self.response}),
      ("ratio1.bc.base.EE_VPN_IMPL", {"new": False}),
    ]:
      # The patch of this target.
      patcher = mock.patch(target, **kwargs)
      # Started now.
      patcher.start()
      # Stopped by the test's cleanups.
      self.addCleanup(patcher.stop)

  def _logs(self):
    """
    Join the stand-in's log lines.

    One text, so that a single search covers every line the client logged.

    Returns
    -------
    str
      Every line the client logged, one per line.

    Examples
    --------
    >>> "Oracle secret" in self._logs()
    True
    """
    # One text to search.
    return "\n".join(self.engine.log_messages)

  def test_the_request_declares_the_flag_and_kwargs_cannot_drop_it(self):
    """The signed request always carries the flag set to true, also when a caller passes it as false."""
    # A caller that tries to send the flag as false.
    self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1, sender_memory_secrets=False)
    # The signed request says true.
    self.assertIs(self.engine.signed_payloads[-1][dAuth.DAUTH_SENDER_MEMORY_SECRETS], True)

  def test_the_secret_is_held_and_reaches_no_environment_answer_or_log(self):
    """On a debug network, with and without the full answer returned, the value is decrypted with the signer's
    address and is then only in the holder."""
    # Both kinds of result: the env keys, and the full answer.
    for full in (False, True):
      # Each kind reports on its own.
      with self.subTest(return_full_data=full):
        # Each pass starts from the original answer (the client pops the field out of it).
        self.response.json.return_value["result"]["auth"][dAuth.DAUTH_ORACLE_SECRET] = CIPHERTEXT
        # Each pass starts from an empty holder, restored when the pass ends.
        with mock.patch.object(BaseBlockEngine, "_BaseBlockEngine__oracle_secret", None):
          # A start-up dAuth on devnet, where debug logging is forced on.
          result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="devnet", return_full_data=full)
          # The value is held in process memory.
          self.assertEqual(BaseBlockEngine.oracle_secret(), FAKE_SECRET)
        # It was decrypted with the key shared with the answer's signer.
        self.engine.decrypt.assert_called_with(encrypted_data_b64=CIPHERTEXT, sender_address="0xai_oracle")
        # Neither it nor its encrypted form is in the result.
        self.assertEqual([text in json.dumps(result) for text in (FAKE_SECRET, CIPHERTEXT)], [False, False])
        # It is in no environment variable.
        self.assertNotIn(FAKE_SECRET, os.environ.values())
        # Its field name is not a variable either.
        self.assertNotIn(dAuth.DAUTH_ORACLE_SECRET, os.environ)
        # It is in no log line.
        self.assertNotIn(FAKE_SECRET, self._logs())
        # One line says it is held.
        self.assertIn("Oracle secret from oracle <0xai_oracle> kept in process memory.", self._logs())
    # The env keys are still applied as before.
    self.assertEqual(os.environ["EE_TEST_KEY"], "plain-value")

  def test_an_answer_without_the_secret_leaves_the_holder_as_it_was(self):
    """A worker's answer, or one from a previous-release server, has no field and changes nothing."""
    # An answer without the field.
    del self.response.json.return_value["result"]["auth"][dAuth.DAUTH_ORACLE_SECRET]
    # A value already held before this answer.
    with mock.patch.object(BaseBlockEngine, "_BaseBlockEngine__oracle_secret", "held-before"):
      # One start-up dAuth round.
      self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1)
      # The held value is unchanged.
      self.assertEqual(BaseBlockEngine.oracle_secret(), "held-before")
    # No line about the secret.
    self.assertNotIn("Oracle secret", self._logs())

  def test_a_value_that_does_not_decrypt_is_not_kept(self):
    """A field that does not decrypt with this node's key (encrypted to another node, or not encrypted) leaves the
    holder as it was and says so in one red line that carries no part of the field."""
    # A field encrypted for another node: the stand-in's decrypt gives None for it.
    self.response.json.return_value["result"]["auth"][dAuth.DAUTH_ORACLE_SECRET] = "encrypted-for-another-node"
    # A value already held before this answer.
    with mock.patch.object(BaseBlockEngine, "_BaseBlockEngine__oracle_secret", "held-before"):
      # One start-up dAuth round.
      self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1)
      # The held value is unchanged.
      self.assertEqual(BaseBlockEngine.oracle_secret(), "held-before")
    # One line says why, and no line carries the field.
    self.assertEqual(
      (self._logs().count("Oracle secret from oracle <0xai_oracle> does not decrypt: not kept."),
       "encrypted-for-another-node" in self._logs()),
      (1, False),
    )

  def test_the_debug_request_line_names_the_fields_without_their_values(self):
    """On a debug network the request line lists the signed request's field names, flag included, but not the
    signature or any other value, so the logged line cannot be sent again as a request."""
    # A start-up dAuth on devnet, where debug logging is forced on.
    self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="devnet", max_tries=1)
    # The one request line.
    [line] = [text for text in self.engine.log_messages if text.startswith("Requesting dAuth")]
    # It names the flag and the signature field.
    self.assertEqual([name in line for name in (dAuth.DAUTH_SENDER_MEMORY_SECRETS, "EE_SIGN")], [True, True])
    # The stand-in's signature value and the request's nonce are in no log line.
    self.assertEqual(
      [value in self._logs() for value in ("request-signature", self.engine.signed_payloads[-1]["nonce"])],
      [False, False],
    )


if __name__ == "__main__":
  # Runs this file's tests when it is started on its own.
  unittest.main()
