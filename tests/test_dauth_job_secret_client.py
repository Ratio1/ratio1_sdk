import os
import unittest
from types import SimpleNamespace
from unittest import mock

import requests

from ratio1.bc.base import BaseBlockEngine
from ratio1.const.base import DAUTH_ENV_KEY, dAuth


class _DauthClientHarness:
  get_dauth_job_secret_bundle = BaseBlockEngine.get_dauth_job_secret_bundle

  def __init__(self):
    self.evm_network = "mainnet"
    self.log_messages = []
    self.signed_payloads = []
    self.verification_calls = []
    self.verification_valid = True
    self.verification_sender = "server"
    self.dauth_oracle = True
    self.oracle_checks = []
    self.network_data_calls = []
    self.default_dauth_url = "https://default.dauth.example/get_auth_data"

  def P(self, message, **kwargs):
    self.log_messages.append(str(message))

  def get_network_data(self, network):
    self.network_data_calls.append(network)
    return {
      dAuth.EvmNetData.DAUTH_URL_KEY: self.default_dauth_url,
    }

  def sign(self, payload):
    self.signed_payloads.append(dict(payload))
    payload["EE_SIGN"] = "request-signature"
    payload["EE_SENDER"] = "requester"
    return payload["EE_SIGN"]

  def verify(self, payload, **kwargs):
    self.verification_calls.append((payload, kwargs))
    return SimpleNamespace(
      valid=self.verification_valid,
      sender=self.verification_sender,
    )

  def node_address_to_eth_address(self, address):
    return "0x" + address

  def web3_is_dauth_oracle(self, address, network=None):
    self.oracle_checks.append((address, network))
    return self.dauth_oracle


def _secret_bundle(job_id="7", secret_value="top-secret"):
  return {
    "job_id": job_id,
    "job_secrets": {
      "plugins": {
        "CONTAINER_APP_RUNNER": [{
          "instance_conf": {
            "ENV": {
              "API_KEY": secret_value,
            },
          },
        }],
      },
    },
  }


def _response_for(bundle=None, **result_overrides):
  bundle = bundle if bundle is not None else _secret_bundle()
  result = {
    "status": "success",
    "job_id": bundle["job_id"],
    "secret_bundle": bundle,
    "EE_SIGN": "server-signature",
    "EE_SENDER": "server",
  }
  result.update(result_overrides)
  response = mock.Mock(status_code=200)
  response.json.return_value = {"result": result}
  return response


class TestDauthJobSecretClient(unittest.TestCase):

  def setUp(self):
    self.engine = _DauthClientHarness()

  @mock.patch("ratio1.bc.base.requests.post")
  def test_returns_full_secret_bundle_from_signed_success_response(self, post):
    bundle = _secret_bundle()
    post.return_value = _response_for(bundle)

    result = self.engine.get_dauth_job_secret_bundle(
      7,
      request_timeout=(2, 5),
    )

    self.assertIs(result, bundle)
    self.assertEqual(self.engine.signed_payloads, [{"job_id": "7"}])
    self.assertEqual(
      self.engine.verification_calls,
      [(post.return_value.json.return_value["result"], {"log_hash_sign_fails": False})],
    )
    self.assertEqual(self.engine.oracle_checks, [("0xserver", "mainnet")])
    self.assertEqual(self.engine.network_data_calls, ["mainnet"])
    post.assert_called_once_with(
      "https://default.dauth.example/get_secrets",
      json={
        "body": {
          "job_id": "7",
          "EE_SIGN": "request-signature",
          "EE_SENDER": "requester",
        },
      },
      timeout=(2, 5),
    )

  @mock.patch("ratio1.bc.base.requests.post")
  def test_uses_network_data_and_ignores_environment_override(self, post):
    post.return_value = _response_for()

    with mock.patch.dict(
      os.environ,
      {DAUTH_ENV_KEY: "https://env.dauth.example/old/path/get_auth_data?debug=1"},
    ):
      self.engine.get_dauth_job_secret_bundle("7", network="testnet")
    self.assertEqual(
      post.call_args.args[0],
      "https://default.dauth.example/get_secrets",
    )
    self.assertEqual(self.engine.network_data_calls, ["testnet"])

  @mock.patch("ratio1.bc.base.requests.post")
  def test_preserves_reverse_proxy_prefix_from_network_data(self, post):
    post.return_value = _response_for()
    self.engine.default_dauth_url = "https://dauth.example/proxy/api/get_auth_data"

    self.engine.get_dauth_job_secret_bundle("7")

    self.assertEqual(
      post.call_args.args[0],
      "https://dauth.example/proxy/api/get_secrets",
    )

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_invalid_result_signature(self, post):
    post.return_value = _response_for()
    self.engine.verification_valid = False

    with self.assertRaisesRegex(ValueError, "signature is invalid"):
      self.engine.get_dauth_job_secret_bundle("7")

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_valid_signature_from_non_dauth_oracle(self, post):
    post.return_value = _response_for()
    self.engine.dauth_oracle = False

    with self.assertRaisesRegex(ValueError, "signer is not authorized"):
      self.engine.get_dauth_job_secret_bundle(
        "7",
        network="testnet",
      )

    self.assertEqual(self.engine.oracle_checks, [("0xserver", "testnet")])

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_http_failure_without_reading_body(self, post):
    response = mock.Mock(status_code=503)
    post.return_value = response

    with self.assertRaisesRegex(RuntimeError, "HTTP status 503"):
      self.engine.get_dauth_job_secret_bundle("7")

    response.json.assert_not_called()

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_transport_failure_with_generic_error(self, post):
    post.side_effect = requests.ConnectionError("upstream connection failed")

    with self.assertRaisesRegex(RuntimeError, "dAuth secret request failed"):
      self.engine.get_dauth_job_secret_bundle("7")

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_malformed_responses(self, post):
    malformed_responses = []

    invalid_json = mock.Mock(status_code=200)
    invalid_json.json.side_effect = ValueError("response contains secret text")
    malformed_responses.append(invalid_json)

    not_a_dictionary = mock.Mock(status_code=200)
    not_a_dictionary.json.return_value = []
    malformed_responses.append(not_a_dictionary)

    missing_result = mock.Mock(status_code=200)
    missing_result.json.return_value = {}
    malformed_responses.append(missing_result)

    malformed_responses.append(_response_for(secret_bundle=[]))

    malformed_bundle = _secret_bundle()
    malformed_bundle["job_secrets"] = []
    malformed_responses.append(_response_for(malformed_bundle))

    for response in malformed_responses:
      with self.subTest(response=response):
        post.return_value = response
        with self.assertRaises(ValueError):
          self.engine.get_dauth_job_secret_bundle("7")

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_server_error_and_status_mismatch(self, post):
    for overrides, exception_type in [
      ({"error": "not authorized"}, RuntimeError),
      ({"status": "pending"}, ValueError),
    ]:
      with self.subTest(overrides=overrides):
        post.return_value = _response_for(**overrides)
        with self.assertRaises(exception_type):
          self.engine.get_dauth_job_secret_bundle("7")

  @mock.patch("ratio1.bc.base.requests.post")
  def test_rejects_result_and_bundle_job_id_mismatch(self, post):
    mismatched_responses = [
      _response_for(job_id="8"),
      _response_for(_secret_bundle(job_id="8"), job_id="7"),
    ]

    for response in mismatched_responses:
      with self.subTest(response=response):
        post.return_value = response
        with self.assertRaisesRegex(ValueError, "job ID does not match"):
          self.engine.get_dauth_job_secret_bundle("7")

  @mock.patch("ratio1.bc.base.requests.post")
  def test_does_not_log_sensitive_request_or_response_content(self, post):
    secret_value = "must-never-appear-in-logs"
    post.return_value = _response_for(_secret_bundle(secret_value=secret_value))

    self.engine.get_dauth_job_secret_bundle("7")

    logged_text = "\n".join(self.engine.log_messages)
    self.assertNotIn(secret_value, logged_text)
    self.assertNotIn("job_secrets", logged_text)
    self.assertNotIn("request-signature", logged_text)
    self.assertEqual(logged_text, "")


if __name__ == "__main__":
  unittest.main()
