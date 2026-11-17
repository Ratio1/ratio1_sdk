"""The oracle-only secret is kept in process memory: moved out of the environment, never written to it, never logged."""
# Serializes the results so a single search finds the value anywhere in them.
import json
# The process environment under test.
import os
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


class DauthClientTests(unittest.TestCase):
  """The dAuth client asks with the flag and keeps a received secret in memory only."""

  def setUp(self):
    """
    Isolate the environment and the holder, and answer every dAuth request with the secret.

    The client is the SDK's own ``dauth_autocomplete`` on a stand-in engine; every HTTP request
    gets an oracle's answer with one env key and the secret.

    Returns
    -------
    None
    """
    # Environment and holder, restored after the test.
    _isolate(self)
    # The SDK's own dauth_autocomplete on a stand-in engine that records its log lines and signed requests.
    self.engine = _AutocompleteHarness()
    # A served HTTP answer.
    self.response = mock.Mock(status_code=200)
    # An oracle's answer: one env key and the secret.
    self.response.json.return_value = {
      "result": {
        "auth": {"EE_TEST_KEY": "plain-value", dAuth.DAUTH_ORACLE_SECRET: FAKE_SECRET},
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
    """On a debug network, with and without the full answer returned, the value is only in the holder."""
    # Both kinds of result: the env keys, and the full answer.
    for full in (False, True):
      # Each kind reports on its own.
      with self.subTest(return_full_data=full):
        # Each pass starts from the original answer (the client pops the field out of it).
        self.response.json.return_value["result"]["auth"][dAuth.DAUTH_ORACLE_SECRET] = FAKE_SECRET
        # Each pass starts from an empty holder, restored when the pass ends.
        with mock.patch.object(BaseBlockEngine, "_BaseBlockEngine__oracle_secret", None):
          # A start-up dAuth on devnet, where debug logging is forced on.
          result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="devnet", return_full_data=full)
          # The value is held in process memory.
          self.assertEqual(BaseBlockEngine.oracle_secret(), FAKE_SECRET)
        # It is not in the result.
        self.assertNotIn(FAKE_SECRET, json.dumps(result))
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


if __name__ == "__main__":
  # Runs this file's tests when it is started on its own.
  unittest.main()
