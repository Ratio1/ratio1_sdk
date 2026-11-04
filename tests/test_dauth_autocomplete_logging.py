"""Verify that dauth_autocomplete never logs the env secrets it receives."""
import os
import unittest
from unittest import mock

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


if __name__ == "__main__":
  unittest.main()
