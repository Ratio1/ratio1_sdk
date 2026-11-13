"""Verify that dauth_autocomplete never logs the env secrets it receives."""
import os
import unittest
from unittest import mock

import requests

from ratio1.bc.base import BaseBlockEngine
from test_dauth_job_secret_client import _DauthClientHarness


SECRET_KEY = "EE_TEST_DAUTH_SECRET"
SECRET_VALUE = "dauth-secret-value"
DAUTH_URL = "https://dauth.example/get_auth_data"


class _AutocompleteHarness(_DauthClientHarness):
  """
  Bind dauth_autocomplete to the isolated dAuth engine fixture.

  Notes
  -----
  Signature checks use fixture results; HTTP is always mocked.
  """
  dauth_autocomplete = BaseBlockEngine.dauth_autocomplete

  def __init__(self):
    super().__init__()
    self.eth_address = "0x" + "a" * 40
    self.allowed = []

  def add_address_to_allowed(self, addresses):
    self.allowed.extend(addresses)


class TestDauthAutocompleteLogging(unittest.TestCase):
  """Cover the debug, normal and failure log paths of dauth_autocomplete."""

  def setUp(self):
    """Mock the HTTP boundary and isolate the process environment."""
    self.engine = _AutocompleteHarness()
    self.response = mock.Mock(status_code=200)
    self.response.json.return_value = {
      "result": {
        "auth": {SECRET_KEY: SECRET_VALUE, "whitelist": ["0xai_peer"]},
        "server_alias": "oracle",
        "EE_SENDER": "0xai_oracle",
      },
    }
    for target, kwargs in [
      ("ratio1.bc.base.requests.post", {"return_value": self.response}),
      ("ratio1.bc.base.EE_VPN_IMPL", {"new": False}),
    ]:
      patcher = mock.patch(target, **kwargs)
      patcher.start()
      self.addCleanup(patcher.stop)
    env = mock.patch.dict(os.environ)
    env.start()
    self.addCleanup(env.stop)
    os.environ.pop(SECRET_KEY, None)

  def _logs(self):
    return "\n".join(self.engine.log_messages)

  def test_debug_network_logs_key_names_but_not_values(self):
    """Devnet forces debug mode; the secret still reaches only the env."""
    result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="devnet")

    self.assertEqual(result, {SECRET_KEY: SECRET_VALUE})
    self.assertEqual(os.environ[SECRET_KEY], SECRET_VALUE)
    self.assertEqual(self.engine.allowed, ["0xai_peer"])
    self.assertIn(f"Adding key `{SECRET_KEY}` to env.", self._logs())
    self.assertNotIn(SECRET_VALUE, self._logs())

  def test_overwrite_logs_key_name_only(self):
    """An existing env key is reported as overwritten without its new value."""
    os.environ[SECRET_KEY] = "old-value"

    self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", debug=True)

    self.assertEqual(os.environ[SECRET_KEY], SECRET_VALUE)
    self.assertIn(f"Overwrite  `{SECRET_KEY}` in env.", self._logs())
    self.assertNotIn(SECRET_VALUE, self._logs())

  def test_failure_after_response_does_not_log_the_response(self):
    """An exception after the response was parsed must not dump it."""
    self.engine.add_address_to_allowed = mock.Mock(side_effect=RuntimeError("whitelist failed"))

    result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1)

    self.assertIsNone(result)
    self.assertIn("Error in dAuth URL request: whitelist failed", self._logs())
    self.assertNotIn(SECRET_VALUE, self._logs())

  def test_busy_oracle_is_retryable_and_paced(self):
    """A 503 is not a bad URL: return {} so the node retries, pausing between tries."""
    self.response.status_code = 503
    self.response.text = "busy"
    with mock.patch("ratio1.bc.base.sleep") as pause:
      result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=3)
    self.assertEqual(result, {})
    self.assertEqual(pause.call_count, 2)

  def test_timeout_is_retryable_but_an_outage_is_not(self):
    """A timeout is a busy oracle ({}); a 530 (no tunnel) still means stop (None)."""
    timeout = requests.exceptions.ReadTimeout("slow")
    with mock.patch("ratio1.bc.base.requests.post", side_effect=timeout):
      result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1)
    self.assertEqual(result, {})
    self.response.status_code = 530
    result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=1)
    self.assertIsNone(result)

  def test_only_a_busy_answer_is_paced_and_the_last_answer_decides(self):
    """Outages and unreachable hosts return None without pauses, also after an earlier busy answer."""
    answers = [mock.Mock(status_code=503, text="busy")] + [mock.Mock(status_code=530, text="no tunnel")] * 4
    with mock.patch("ratio1.bc.base.requests.post", side_effect=answers), mock.patch("ratio1.bc.base.sleep") as pause:
      result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=5)
    self.assertIsNone(result)
    self.assertEqual(pause.call_count, 1)  # after the 503 only
    for error in (requests.exceptions.ConnectTimeout("no route"), requests.exceptions.ConnectionError("refused")):
      with mock.patch("ratio1.bc.base.requests.post", side_effect=error), mock.patch("ratio1.bc.base.sleep") as pause:
        result = self.engine.dauth_autocomplete(dauth_endp=DAUTH_URL, network="mainnet", max_tries=3)
      self.assertIsNone(result)
      pause.assert_not_called()

  def test_an_sdk_first_process_reports_no_core_version(self):
    """The core version is read only when the node loaded naeural_core before the SDK."""
    import subprocess, sys
    code = ("import sys, types; core = types.ModuleType('naeural_core'); core.__path__ = []; "
            "main = types.ModuleType('naeural_core.main'); main.__path__ = []; "
            "ver = types.ModuleType('naeural_core.main.ver'); ver.__VER__ = '9.9.9'; "
            "sys.modules.update({'naeural_core.main': main, 'naeural_core.main.ver': ver}); "
            "@FIRST@"
            "import ratio1.bc.base as base; print(base.core_version)")
    run = lambda first: subprocess.run([sys.executable, "-c", code.replace("@FIRST@", first)], capture_output=True, text=True,
                                       env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path))).stdout.strip().splitlines()[-1]
    self.assertEqual(run(""), "None")  # the SDK came first: the core is importable but was not loaded
    self.assertEqual(run("sys.modules['naeural_core'] = core; "), "9.9.9")  # a node: the core is already loaded

  def test_a_node_whose_core_version_cannot_be_imported_fails_at_import(self):
    """No fallback: a loaded core without main.ver stops the SDK import instead of sending no core version."""
    import subprocess, sys
    code = ("import sys, types; core = types.ModuleType('naeural_core'); core.__path__ = []; "
            "sys.modules['naeural_core'] = core; import ratio1.bc.base")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)))
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("No module named 'naeural_core.main'", result.stderr)


if __name__ == "__main__":
  unittest.main()
