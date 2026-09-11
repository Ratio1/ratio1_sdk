import unittest

from ratio1.comm.message_buffer import ObservableMessageBuffer
from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


class _FakeLog:
  def __init__(self):
    self.messages = []

  def P(self, message, **kwargs):
    self.messages.append((message, kwargs))


class _Message:
  def __init__(self, payload):
    self.payload = payload


def _config():
  return {
    COMMS.HOST: "localhost",
    COMMS.PORT: 1883,
    COMMS.USER: "",
    COMMS.PASS: "",
    COMMS.EE_ADDR: "0xSELF",
    COMMS.QOS: 1,
    COMMS.SECURED: 0,
    COMMS.COMMUNICATION_CTRL_CHANNEL: {
      COMMS.TOPIC: "root/ctrl",
      COMMS.QOS: 1,
    },
  }


class TestMqttIngressAdmission(unittest.TestCase):

  def test_callback_reports_full_admission_without_evicting_oldest(self):
    buffer = ObservableMessageBuffer(capacity=1)
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    current_client = object()
    wrapper._mqttc = current_client

    wrapper._callback_on_message(
      current_client, None, _Message(b"first"),
    )
    wrapper._callback_on_message(
      current_client, None, _Message(b"second"),
    )

    self.assertEqual(buffer.popleft(), "first")
    self.assertEqual(wrapper.nr_dropped_messages, 1)
    self.assertEqual(buffer.snapshot().rejected_full, 1)

  def test_stale_client_callback_is_rejected_after_reconnect(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    stale_client = object()
    current_client = object()
    wrapper._mqttc = current_client

    wrapper._callback_on_message(
      stale_client, None, _Message(b"stale"),
    )

    self.assertEqual(len(buffer), 0)
    self.assertEqual(wrapper.nr_stale_messages, 1)

  def test_late_callback_is_rejected_after_release_clears_client(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    retired_client = object()
    wrapper._mqttc = None

    wrapper._callback_on_message(
      retired_client, None, _Message(b"late"),
    )

    self.assertEqual(len(buffer), 0)
    self.assertEqual(wrapper.nr_stale_messages, 1)

  def test_plain_deque_compatible_callback_remains_supported(self):
    from collections import deque

    buffer = deque()
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )
    current_client = object()
    wrapper._mqttc = current_client

    wrapper._callback_on_message(
      current_client, None, _Message(b"legacy"),
    )

    self.assertEqual(list(buffer), ["legacy"])


if __name__ == "__main__":
  unittest.main()
