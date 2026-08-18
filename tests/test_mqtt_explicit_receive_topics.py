import unittest

from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


class _FakeLog:
  def P(self, *args, **kwargs):
    return


def _base_config():
  return {
    COMMS.HOST: "localhost",
    COMMS.PORT: 1883,
    COMMS.USER: "",
    COMMS.PASS: "",
    COMMS.EE_ADDR: "0xai_self",
    COMMS.QOS: 0,
    COMMS.SECURED: 0,
    COMMS.COMMUNICATION_CTRL_CHANNEL: {
      COMMS.TOPIC: "ratio1/ctrl",
      COMMS.TARGETED_TOPIC: "ratio1/ctrl/{}",
    },
  }


class TestMqttExplicitReceiveTopics(unittest.TestCase):

  def test_channel_can_publish_targeted_without_automatic_subscription(self):
    config = _base_config()
    config[COMMS.COMMUNICATION_CTRL_CHANNEL][COMMS.SUBSCRIBE_TARGETED] = False
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=config,
      recv_buff=[],
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      verbosity=99,
    )

    self.assertEqual(wrapper.get_recv_channel_topics(), ["ratio1/ctrl"])

  def test_explicit_topics_replace_channel_derived_topics(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      recv_buff=[],
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      recv_topics=["ratio1/ctrl/0xai_a", "ratio1/ctrl/0xai_b"],
      verbosity=99,
    )

    self.assertEqual(
      wrapper.get_recv_channel_topics(),
      ["ratio1/ctrl/0xai_a", "ratio1/ctrl/0xai_b"],
    )
    self.assertNotIn("ratio1/ctrl", wrapper.get_recv_channel_topics())

  def test_explicit_empty_topics_disable_receive_without_fallback(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_base_config(),
      recv_buff=[],
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      recv_topics=[],
      verbosity=99,
    )

    self.assertEqual(wrapper.get_recv_channel_topics(), [])
    self.assertIsNone(wrapper.get_recv_channel_def())


if __name__ == "__main__":
  unittest.main()
