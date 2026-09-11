import unittest

from ratio1.comm.message_buffer import ObservableMessageBuffer
from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


class _FakeLog:
  def P(self, *args, **kwargs):
    return

  def time_to_str(self):
    return "time"


class _Message:
  def __init__(self, payload, topic="ratio1/ctrl"):
    self.payload = payload
    self.topic = topic


def _config():
  return {
    COMMS.HOST: "localhost",
    COMMS.PORT: 1883,
    COMMS.USER: "",
    COMMS.PASS: "",
    COMMS.EE_ADDR: "0xai_self",
    COMMS.QOS: 1,
    COMMS.SECURED: 0,
    COMMS.COMMUNICATION_CTRL_CHANNEL: {
      COMMS.TOPIC: "ratio1/ctrl",
      COMMS.QOS: 1,
    },
  }


class TestMqttIngressAdmission(unittest.TestCase):

  def _wrapper(self, buffer):
    return MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )

  def test_real_callback_uses_bounded_reject_newest_admission(self):
    buffer = ObservableMessageBuffer(capacity=1)
    wrapper = self._wrapper(buffer)
    current_client = object()
    wrapper._mqttc = current_client

    wrapper._callback_on_message(current_client, None, _Message(b"first"))
    wrapper._callback_on_message(current_client, None, _Message(b"second"))

    self.assertEqual(buffer.popleft(), "first")
    self.assertEqual(buffer.snapshot().rejected_full, 1)
    self.assertEqual(wrapper.nr_dropped_messages, 1)

  def test_message_and_disconnect_from_retired_client_are_ignored(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = self._wrapper(buffer)
    active_client = object()
    retired_client = object()
    wrapper._mqttc = active_client

    wrapper._callback_on_message(retired_client, None, _Message(b"stale"))
    wrapper._callback_on_disconnect(retired_client, None, 1)

    self.assertEqual(len(buffer), 0)
    self.assertIs(wrapper._mqttc, active_client)
    self.assertEqual(wrapper.nr_stale_messages, 1)
    self.assertEqual(wrapper.get_subscription_status()["stale_callbacks"], 1)


if __name__ == "__main__":
  unittest.main()
