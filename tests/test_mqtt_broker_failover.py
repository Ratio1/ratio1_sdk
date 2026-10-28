"""Broker selection and transport cleanup without contacting a live network."""

import copy
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from ratio1.base.generic_session import GenericSession
from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS
from test_mqtt_delivery_lifecycle import _FakeMqttClient, _FakeLog, _config


class _BrokerClient(_FakeMqttClient):
  """Paho stand-in that supplies a host-specific connection outcome."""

  def __init__(self, outcomes, attempts, tls_hosts, wrapper):
    """Retain the shared connection script and record actual host selection."""
    super().__init__()
    self._client_id = b"test-client"
    self.outcomes = outcomes
    self.attempts = attempts
    self.tls_hosts = tls_hosts
    self.wrapper = wrapper

  def username_pw_set(self, **kwargs):
    """Accept the production client's authentication setup."""
    self.credentials = kwargs

  def tls_set(self, *args):
    """Record which candidate is active while TLS is configured."""
    self.tls_hosts.append(self.wrapper.cfg_host)

  def connect(self, host, port):
    """Record the attempt and optionally simulate a socket failure."""
    self.host = host
    self.attempts.append(host)
    if self.outcomes.get(host) == "exception":
      raise OSError("simulated connection failure")

  def loop_start(self):
    """Simulate successful, rejected, or absent CONNACK callbacks."""
    outcome = self.outcomes.get(self.host)
    if outcome != "timeout":
      self.on_connect(self, None, {}, 0 if outcome == "ok" else 5)


class TestMqttBrokerFailover(unittest.TestCase):
  """Exercise the production connect loop, Paho setup, and generation guards."""

  def setUp(self):
    """Construct an isolated communicator and deterministic Paho factory."""
    self.config = _config()
    self.config.update({COMMS.HOST: "mqtt-a", COMMS.HOSTS: ["mqtt-a", "mqtt-b", "mqtt-c", "mqtt-d"]})
    log = _FakeLog()
    log.get_unique_id = lambda: "test-id"
    log.time_to_str = lambda: "test-time"
    self.wrapper = MQTTWrapper(log=log, config=self.config, verbosity=99)
    self.addCleanup(self.wrapper.release)
    self.outcomes = {}
    self.attempts = []
    self.clients = []
    self.tls_hosts = []

    def factory(**kwargs):
      """Require cleanup before another client generation is created."""
      if self.clients:
        self.assertEqual(self.clients[-1].loop_stop_calls, 1)
      client = _BrokerClient(self.outcomes, self.attempts, self.tls_hosts, self.wrapper)
      self.clients.append(client)
      return client

    client_patch = mock.patch("ratio1.comm.mqtt_wrapper.mqtt.Client", side_effect=factory)
    self.factory = client_patch.start()
    self.addCleanup(client_patch.stop)
    sleep_patch = mock.patch("ratio1.comm.mqtt_wrapper.sleep", return_value=None)
    sleep_patch.start()
    self.addCleanup(sleep_patch.stop)

  def test_socket_failure_and_connack_failure_advance_in_order(self):
    """Every failed generation is stopped before trying the next endpoint."""
    self.outcomes.update({"mqtt-a": "exception", "mqtt-b": "rejected", "mqtt-c": "timeout", "mqtt-d": "ok"})
    self.config[COMMS.SECURED] = 1

    result = self.wrapper.server_connect(max_retries=2)

    self.assertTrue(result["has_connection"])
    self.assertIn("mqtt-d", result["msg"])
    self.assertEqual(self.attempts, ["mqtt-a", "mqtt-b", "mqtt-c", "mqtt-d"])
    self.assertEqual(self.tls_hosts, self.attempts)
    for client in self.clients[:-1]:
      self.assertEqual(client.disconnect_calls, 1)
      self.wrapper._callback_on_connect(client, None, {}, 0)
      self.wrapper._callback_on_disconnect(client, None, 0)
    self.assertIs(self.wrapper.connection, self.clients[-1])
    self.assertTrue(self.wrapper.connected)

  def test_total_outage_visits_every_broker_before_returning(self):
    """A Core burst of two retries still exhausts all four candidates."""
    self.outcomes.update(dict.fromkeys(self.config[COMMS.HOSTS], "exception"))
    for burst in range(2):
      result = self.wrapper.server_connect(max_retries=2)
      self.assertFalse(result["has_connection"])
      self.assertIsNone(self.wrapper.connection)
      self.assertEqual(self.wrapper._nr_full_retries, burst + 1)
    self.assertEqual(self.attempts, self.config[COMMS.HOSTS] * 2)
    self.assertTrue(all(client.loop_stop_calls == 1 for client in self.clients))

  def test_success_is_sticky_and_later_failure_continues_from_that_broker(self):
    """Reconnect retries the working endpoint before advancing on failure."""
    self.outcomes.update({"mqtt-a": "exception", "mqtt-b": "exception", "mqtt-c": "ok", "mqtt-d": "ok"})
    self.assertTrue(self.wrapper.server_connect(max_retries=2)["has_connection"])
    self.wrapper.release()
    self.assertTrue(self.wrapper.server_connect(max_retries=2)["has_connection"])
    self.wrapper.release()
    self.outcomes["mqtt-c"] = "exception"
    self.assertTrue(self.wrapper.server_connect(max_retries=2)["has_connection"])
    self.assertEqual(self.attempts, ["mqtt-a", "mqtt-b", "mqtt-c", "mqtt-c", "mqtt-c", "mqtt-d"])

  def test_json_candidates_are_deduplicated_and_shared_config_is_unchanged(self):
    """dAuth JSON works without moving other communicators' primary host."""
    self.config[COMMS.HOSTS] = json.dumps(["mqtt-b", "mqtt-a", "mqtt-b", "mqtt-c"])
    before = copy.deepcopy(self.config)
    self.outcomes.update({"mqtt-a": "exception", "mqtt-b": "exception", "mqtt-c": "ok"})
    self.assertTrue(self.wrapper.server_connect(max_retries=1)["has_connection"])
    self.assertEqual(self.attempts, ["mqtt-a", "mqtt-b", "mqtt-c"])
    self.assertEqual(self.config, before)
    other = MQTTWrapper(log=self.wrapper.log, config=self.config, verbosity=99)
    self.assertEqual(other.cfg_host, "mqtt-a")

  def test_single_host_keeps_legacy_retry_budget(self):
    """Old dAuth responses need no list and retain the configured retries."""
    del self.config[COMMS.HOSTS]
    self.outcomes["mqtt-a"] = "exception"
    self.assertFalse(self.wrapper.server_connect(max_retries=3)["has_connection"])
    self.assertEqual(self.attempts, ["mqtt-a"] * 3)

  def test_configuration_is_read_after_wrapper_construction(self):
    """Session startup may add HOSTS after it has created all wrappers."""
    self.config[COMMS.HOST] = "mqtt-b"
    self.config[COMMS.HOSTS] = '["mqtt-b", "mqtt-c"]'
    self.outcomes.update({"mqtt-b": "exception", "mqtt-c": "ok"})
    self.assertTrue(self.wrapper.server_connect(max_retries=1)["has_connection"])
    self.assertEqual(self.attempts, ["mqtt-b", "mqtt-c"])

  def test_malformed_candidates_fail_before_starting_a_transport(self):
    """Reject invalid lists instead of handing them to Paho as hostnames."""
    for hosts in ('not-json', '"mqtt-b"', '{"host":"mqtt-b"}', '[null]', '[""]', [4]):
      with self.subTest(hosts=hosts):
        self.config[COMMS.HOSTS] = hosts
        with self.assertRaises(ValueError):
          self.wrapper.server_connect(max_retries=1)
    self.factory.assert_not_called()


class TestSessionBrokerConfiguration(unittest.TestCase):
  """Ensure dAuth alternatives follow the effective primary's precedence."""

  def test_environment_candidates_only_follow_the_matching_primary(self):
    """Preserve explicit lists, custom hosts, and single-host responses."""
    env = {"EE_MQTT_HOST": "mqtt-a", "EE_MQTT_HOSTS": '["mqtt-a", "mqtt-b"]'}
    for config, host_argument, expected in (
      ({}, None, env["EE_MQTT_HOSTS"]),
      ({}, "custom-broker", None),
      ({COMMS.HOST: "custom-broker"}, None, None),
      ({COMMS.HOSTS: ["custom-fallback"]}, None, ["custom-fallback"]),
      ({COMMS.HOSTS: []}, None, []),
    ):
      with self.subTest(config=config, host_argument=host_argument):
        session = GenericSession.__new__(GenericSession)
        session._config = copy.deepcopy(config)
        session.name = "test"
        session.bc_engine = SimpleNamespace(address="test-address")
        with mock.patch.dict("os.environ", env, clear=True):
          session._GenericSession__fill_config(host_argument, 1883, "test", "test", False, "address")
        self.assertEqual(session._config.get(COMMS.HOSTS), expected)


if __name__ == "__main__":
  unittest.main()
