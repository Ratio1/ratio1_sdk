import threading
import unittest
from unittest import mock

from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


class _FakeLog:
  def P(self, *args, **kwargs):
    return


class _SubackClient:
  def __init__(self, wrapper, granted_qos):
    self.wrapper = wrapper
    self.granted_qos = granted_qos
    self.mid = 0
    self.subscribed = []

  def subscribe(self, topic, qos):
    self.mid += 1
    mid = self.mid
    self.subscribed.append((topic, qos, mid))
    threading.Timer(
      0.01,
      lambda: self.wrapper._callback_on_subscribe(
        self,
        None,
        mid,
        [self.granted_qos],
      ),
    ).start()
    return (0, mid)


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


class TestMqttSuback(unittest.TestCase):

  def _wrapper(self):
    return MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=[],
      recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
      recv_topics=["ratio1/ctrl/selected"],
      require_suback=True,
      verbosity=99,
    )

  def test_required_suback_grant_marks_subscription_ready(self):
    wrapper = self._wrapper()
    client = _SubackClient(wrapper=wrapper, granted_qos=1)
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1, ack_timeout=0.2)

    self.assertTrue(result["has_connection"])
    self.assertTrue(wrapper.get_subscription_status()["ready"])
    self.assertEqual(
      wrapper.get_subscription_status()["acknowledged_topics"],
      ["ratio1/ctrl/selected"],
    )

  def test_rejected_suback_fails_without_topic_fallback(self):
    wrapper = self._wrapper()
    client = _SubackClient(wrapper=wrapper, granted_qos=128)
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1, ack_timeout=0.2)

    self.assertFalse(result["has_connection"])
    status = wrapper.get_subscription_status()
    self.assertFalse(status["ready"])
    self.assertEqual(status["rejected_topics"], ["ratio1/ctrl/selected"])
    self.assertEqual(client.subscribed[0][0], "ratio1/ctrl/selected")

  def test_missing_suback_times_out_as_degraded(self):
    wrapper = self._wrapper()

    class _SilentClient:
      def subscribe(self, topic, qos):
        return (0, 7)

    wrapper._mqttc = _SilentClient()

    result = wrapper.subscribe(max_retries=1, ack_timeout=0.01)

    self.assertFalse(result["has_connection"])
    self.assertEqual(
      wrapper.get_subscription_status()["timed_out_topics"],
      ["ratio1/ctrl/selected"],
    )

  def test_first_failed_exact_topic_stops_later_topic_attempts(self):
    wrapper = self._wrapper()
    wrapper._explicit_recv_topics = (
      "ratio1/ctrl/first",
      "ratio1/ctrl/second",
      "ratio1/ctrl/third",
    )

    class _SilentClient:
      def __init__(self):
        self.subscribed = []

      def subscribe(self, topic, qos):
        self.subscribed.append(topic)
        return (0, len(self.subscribed))

    client = _SilentClient()
    wrapper._mqttc = client

    with mock.patch("ratio1.comm.mqtt_wrapper.sleep", return_value=None):
      result = wrapper.subscribe(max_retries=2, ack_timeout=0)

    self.assertFalse(result["has_connection"])
    self.assertEqual(client.subscribed, ["ratio1/ctrl/first"] * 2)

  def test_subscription_retry_can_be_cancelled_by_session_shutdown(self):
    wrapper = self._wrapper()

    class _UnexpectedClient:
      def subscribe(self, topic, qos):
        raise AssertionError("shutdown must cancel before broker handoff")

    wrapper._mqttc = _UnexpectedClient()

    result = wrapper.subscribe(
      max_retries=5,
      ack_timeout=2.0,
      should_continue=lambda: False,
    )

    self.assertFalse(result["has_connection"])
    self.assertIn("cancelled", result["msg"].lower())

  def test_suback_from_retired_client_is_ignored(self):
    wrapper = self._wrapper()
    active_client = object()
    wrapper._mqttc = active_client

    wrapper._callback_on_subscribe(object(), None, 42, [1])

    self.assertEqual(wrapper.get_subscription_status()["stale_callbacks"], 1)

  def test_reconnect_resubscribes_only_to_immutable_explicit_topics(self):
    wrapper = self._wrapper()
    first_client = _SubackClient(wrapper=wrapper, granted_qos=1)
    wrapper._mqttc = first_client
    self.assertTrue(wrapper.subscribe(max_retries=1, ack_timeout=0.2)["has_connection"])

    second_client = _SubackClient(wrapper=wrapper, granted_qos=1)
    wrapper._mqttc = second_client
    result = wrapper.subscribe(max_retries=1, ack_timeout=0.2)

    self.assertTrue(result["has_connection"])
    self.assertEqual(
      [topic for topic, _qos, _mid in second_client.subscribed],
      ["ratio1/ctrl/selected"],
    )
    self.assertNotIn("ratio1/ctrl", wrapper.get_recv_channel_topics())


if __name__ == "__main__":
  unittest.main()
