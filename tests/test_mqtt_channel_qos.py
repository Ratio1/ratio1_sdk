import unittest
import copy
import pathlib
import tomllib
from collections import deque
from unittest import mock

import ratio1
from ratio1.base.generic_session import GenericSession
from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS
from ratio1.const.payload import STATUS_TYPE


class _FakeLog:
  def __init__(self):
    self.messages = []

  def P(self, message, **kwargs):
    self.messages.append((message, kwargs))
    return

  def get_unique_id(self):
    return "testid"


class _PublishResult:
  rc = 0


class _FakeMqttClient:
  def __init__(self):
    self.published = []
    self.subscribed = []

  def publish(self, topic, payload, qos):
    self.published.append({
      "topic": topic,
      "payload": payload,
      "qos": qos,
    })
    return _PublishResult()

  def subscribe(self, topic, qos):
    self.subscribed.append({
      "topic": topic,
      "qos": qos,
    })
    return (0, len(self.subscribed))


class _FlakyMqttClient(_FakeMqttClient):
  def __init__(self, failures_by_topic):
    super().__init__()
    self.failures_by_topic = dict(failures_by_topic)
    self.attempts_by_topic = {}

  def subscribe(self, topic, qos):
    self.attempts_by_topic[topic] = self.attempts_by_topic.get(topic, 0) + 1
    remaining_failures = self.failures_by_topic.get(topic, 0)
    if remaining_failures > 0:
      self.failures_by_topic[topic] = remaining_failures - 1
      raise RuntimeError(f"transient subscribe failure for {topic}")
    return super().subscribe(topic=topic, qos=qos)


class _RcFailMqttClient(_FakeMqttClient):
  def __init__(self, failures_by_topic):
    super().__init__()
    self.failures_by_topic = dict(failures_by_topic)
    self.attempts_by_topic = {}

  def subscribe(self, topic, qos):
    self.attempts_by_topic[topic] = self.attempts_by_topic.get(topic, 0) + 1
    remaining_failures = self.failures_by_topic.get(topic, 0)
    if remaining_failures > 0:
      self.failures_by_topic[topic] = remaining_failures - 1
      return (1, self.attempts_by_topic[topic])
    return super().subscribe(topic=topic, qos=qos)


def _base_config():
  return {
    COMMS.HOST: "localhost",
    COMMS.PORT: 1883,
    COMMS.USER: "",
    COMMS.PASS: "",
    COMMS.EE_ADDR: "0xSELF",
    COMMS.QOS: 0,
    COMMS.SECURED: 0,
    COMMS.COMMUNICATION_CONFIG_CHANNEL: {
      COMMS.TOPIC: "root/{}/config",
      COMMS.QOS: 2,
    },
    COMMS.COMMUNICATION_CTRL_CHANNEL: {
      COMMS.TOPIC: "root/ctrl",
      COMMS.QOS: 1,
    },
    COMMS.COMMUNICATION_PAYLOADS_CHANNEL: {
      COMMS.TOPIC: "root/payloads",
    },
  }


class TestMqttChannelQos(unittest.TestCase):

  def test_package_metadata_version_matches_runtime_export(self):
    pyproject_path = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as fh:
      pyproject_data = tomllib.load(fh)

    self.assertEqual(pyproject_data["project"]["version"], ratio1.__version__)

  def test_send_uses_channel_qos_when_available(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      send_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    wrapper.send("hb")

    self.assertEqual(client.published[0]["topic"], "root/ctrl")
    self.assertEqual(client.published[0]["qos"], 1)

  def test_targeted_command_send_uses_config_channel_qos(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      send_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    wrapper.send("cmd", send_to="0xNODE")

    self.assertEqual(client.published[0]["topic"], "root/0xNODE/config")
    self.assertEqual(client.published[0]["qos"], 2)

  def test_subscribe_uses_receive_channel_qos(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      recv_buff=deque(),
      recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1)

    self.assertTrue(result["has_connection"])
    self.assertEqual(client.subscribed[0]["topic"], "root/0xSELF/config")
    self.assertEqual(client.subscribed[0]["qos"], 2)

  def test_subscribe_retries_are_per_topic(self):
    config = _base_config()
    config[COMMS.COMMUNICATION_PAYLOADS_CHANNEL][COMMS.TARGETED_TOPIC] = "root/{}/payloads"
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=config,
      recv_buff=deque(),
      recv_channel_name=COMMS.COMMUNICATION_PAYLOADS_CHANNEL,
      verbosity=99,
    )
    client = _FlakyMqttClient({
      "root/payloads": 2,
      "root/0xSELF/payloads": 2,
    })
    wrapper._mqttc = client

    with mock.patch("ratio1.comm.mqtt_wrapper.sleep", lambda _seconds: None):
      result = wrapper.subscribe(max_retries=3)

    self.assertTrue(result["has_connection"])
    self.assertEqual(client.attempts_by_topic["root/payloads"], 3)
    self.assertEqual(client.attempts_by_topic["root/0xSELF/payloads"], 3)
    self.assertEqual([row["topic"] for row in client.subscribed], ["root/payloads", "root/0xSELF/payloads"])

  def test_subscribe_retries_nonzero_paho_return_codes(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      recv_buff=deque(),
      recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    client = _RcFailMqttClient({"root/0xSELF/config": 2})
    wrapper._mqttc = client

    with mock.patch("ratio1.comm.mqtt_wrapper.sleep", lambda _seconds: None):
      result = wrapper.subscribe(max_retries=3)

    self.assertTrue(result["has_connection"])
    self.assertEqual(client.attempts_by_topic["root/0xSELF/config"], 3)

  def test_subscribe_partial_failure_keeps_exception_status(self):
    config = _base_config()
    config[COMMS.COMMUNICATION_PAYLOADS_CHANNEL][COMMS.TARGETED_TOPIC] = "root/{}/payloads"
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=config,
      recv_buff=deque(),
      recv_channel_name=COMMS.COMMUNICATION_PAYLOADS_CHANNEL,
      verbosity=99,
    )
    client = _FlakyMqttClient({
      "root/payloads": 2,
    })
    wrapper._mqttc = client

    with mock.patch("ratio1.comm.mqtt_wrapper.sleep", lambda _seconds: None):
      result = wrapper.subscribe(max_retries=2)

    self.assertFalse(result["has_connection"])
    self.assertEqual(result["msg_type"], STATUS_TYPE.STATUS_EXCEPTION)
    self.assertIn("root/payloads", result["msg"])

  def test_global_qos_is_fallback_for_channels_without_qos(self):
    config = _base_config()
    config[COMMS.QOS] = 1
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=config,
      send_channel_name=COMMS.COMMUNICATION_PAYLOADS_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    wrapper.send("payload")

    self.assertEqual(client.published[0]["qos"], 1)

  def test_channel_qos_does_not_require_global_fallback(self):
    config = _base_config()
    del config[COMMS.QOS]
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=config,
      send_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    wrapper.send("hb")

    self.assertEqual(client.published[0]["qos"], 1)

  def test_session_env_qos_populates_channel_config(self):
    default_config = copy.deepcopy(GenericSession.default_config)
    session = GenericSession.__new__(GenericSession)
    session._config = copy.deepcopy(GenericSession.default_config)

    with mock.patch.dict("os.environ", {
      "EE_MQTT_HEARTBEAT_QOS": "1",
      "EE_MQTT_COMMAND_QOS": "2",
    }):
      session._GenericSession__apply_channel_qos_from_env()

    self.assertEqual(session._config[COMMS.COMMUNICATION_CTRL_CHANNEL][COMMS.QOS], 1)
    self.assertEqual(session._config[COMMS.COMMUNICATION_CONFIG_CHANNEL][COMMS.QOS], 2)
    self.assertEqual(GenericSession.default_config, default_config)

  def test_subscribe_without_receive_channel_is_explicit_noop(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1)

    self.assertTrue(result["has_connection"])
    self.assertIn("disabled", result["msg"])
    self.assertEqual(client.subscribed, [])


if __name__ == "__main__":
  unittest.main()
