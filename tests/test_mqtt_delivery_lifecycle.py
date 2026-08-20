import unittest
from collections import deque
from threading import Event, Thread
from unittest import mock

from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


class _FakeLog:
  def P(self, *args, **kwargs):
    return


class _PublishResult:
  def __init__(self, rc=0, mid=1):
    self.rc = rc
    self.mid = mid


class _FakeMqttClient:
  def __init__(self, publish_rc=0, publish_mid=1, subscribe_rc=0, subscribe_mid=2):
    self.publish_rc = publish_rc
    self.publish_mid = publish_mid
    self.subscribe_rc = subscribe_rc
    self.subscribe_mid = subscribe_mid
    self.published = []
    self.subscribed = []
    self.disconnect_calls = 0
    self.loop_stop_calls = 0

  def publish(self, topic, payload, qos):
    self.published.append((topic, payload, qos))
    return _PublishResult(rc=self.publish_rc, mid=self.publish_mid)

  def subscribe(self, topic, qos):
    self.subscribed.append((topic, qos))
    return self.subscribe_rc, self.subscribe_mid

  def disconnect(self):
    self.disconnect_calls += 1

  def loop_stop(self):
    self.loop_stop_calls += 1


class _ImmediateCallbackClient(_FakeMqttClient):
  def __init__(self, wrapper, **kwargs):
    super().__init__(**kwargs)
    self.wrapper = wrapper

  def publish(self, topic, payload, qos):
    result = super().publish(topic=topic, payload=payload, qos=qos)
    self.wrapper._callback_on_publish(self, None, result.mid)
    return result

  def subscribe(self, topic, qos):
    result = super().subscribe(topic=topic, qos=qos)
    self.wrapper._callback_on_subscribe(self, None, result[1], [qos])
    return result


class _RejectingBuffer:
  def __init__(self):
    self.items = []

  def try_append(self, item):
    self.items.append(item)
    return False


class _Message:
  payload = b"command"


def _config(command_qos=2):
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
      COMMS.QOS: command_qos,
    },
  }


def _wrapper(command_qos=2, receive=False):
  return MQTTWrapper(
    log=_FakeLog(),
    config=_config(command_qos=command_qos),
    recv_buff=deque() if receive else None,
    send_channel_name=None if receive else COMMS.COMMUNICATION_CONFIG_CHANNEL,
    recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL if receive else None,
    verbosity=99,
  )


class TestMqttPublishLifecycle(unittest.TestCase):

  def test_publish_handoff_is_pending_until_callback(self):
    wrapper = _wrapper(command_qos=2)
    client = _FakeMqttClient(publish_mid=41)
    wrapper._mqttc = client

    admission = wrapper.send("command", send_to="0xNODE")
    before_ack = wrapper.get_delivery_lifecycle_status()

    self.assertTrue(admission["paho_accepted"])
    self.assertEqual(admission["mid"], 41)
    self.assertEqual(before_ack["publish_attempts"], 1)
    self.assertEqual(before_ack["publish_handoff_accepted"], 1)
    self.assertEqual(before_ack["publish_pending"], 1)
    self.assertEqual(before_ack["broker_acknowledged"], 0)

    wrapper._callback_on_publish(client, None, 41)
    after_ack = wrapper.get_delivery_lifecycle_status()

    self.assertEqual(after_ack["publish_pending"], 0)
    self.assertEqual(after_ack["publish_completed"], 1)
    self.assertEqual(after_ack["broker_acknowledged"], 1)

  def test_nonzero_publish_result_is_rejected_not_reported_as_sent(self):
    for result_code in (4, 5, 15):
      with self.subTest(result_code=result_code):
        wrapper = _wrapper(command_qos=2)
        wrapper._mqttc = _FakeMqttClient(
          publish_rc=result_code,
          publish_mid=42,
        )

        with self.assertRaises(RuntimeError):
          wrapper.send("command", send_to="0xNODE")

        status = wrapper.get_delivery_lifecycle_status()
        self.assertEqual(status["publish_attempts"], 1)
        self.assertEqual(status["publish_handoff_accepted"], 0)
        self.assertEqual(status["publish_handoff_rejected"], 1)
        self.assertEqual(status["publish_pending"], 0)

  def test_qos_zero_completion_is_not_labeled_broker_acknowledgement(self):
    wrapper = _wrapper(command_qos=0)
    client = _FakeMqttClient(publish_mid=43)
    wrapper._mqttc = client

    wrapper.send("command", send_to="0xNODE")
    wrapper._callback_on_publish(client, None, 43)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["publish_completed"], 1)
    self.assertEqual(status["broker_acknowledged"], 0)

  def test_stale_publish_callback_cannot_complete_current_session_mid(self):
    wrapper = _wrapper(command_qos=2)
    current = _FakeMqttClient(publish_mid=44)
    stale = _FakeMqttClient(publish_mid=44)
    wrapper._mqttc = current
    wrapper.send("command", send_to="0xNODE")

    wrapper._callback_on_publish(stale, None, 44)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["publish_pending"], 1)
    self.assertEqual(status["stale_publish_callbacks"], 1)
    self.assertEqual(status["publish_completed"], 0)

  def test_release_marks_unfinished_publish_as_abandoned(self):
    wrapper = _wrapper(command_qos=2)
    client = _FakeMqttClient(publish_mid=45)
    wrapper._mqttc = client
    wrapper.send("command", send_to="0xNODE")

    wrapper.release()

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["publish_pending"], 0)
    self.assertEqual(status["publish_abandoned"], 1)

  def test_publish_callback_race_before_send_returns_is_conserved(self):
    wrapper = _wrapper(command_qos=2)
    client = _ImmediateCallbackClient(wrapper, publish_mid=46)
    wrapper._mqttc = client

    wrapper.send("command", send_to="0xNODE")

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["publish_handoff_accepted"], 1)
    self.assertEqual(status["publish_pending"], 0)
    self.assertEqual(status["publish_completed"], 1)
    self.assertEqual(status["broker_acknowledged"], 1)

  def test_stale_disconnect_cannot_release_replacement_client(self):
    wrapper = _wrapper(command_qos=2)
    stale = _FakeMqttClient()
    current = _FakeMqttClient()
    wrapper._mqttc = current
    wrapper.connected = True

    with mock.patch("ratio1.comm.mqtt_wrapper.mqtt_version", "1.6.1"):
      wrapper._callback_on_disconnect(stale, None, 0)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertIs(wrapper._mqttc, current)
    self.assertTrue(wrapper.connected)
    self.assertEqual(current.disconnect_calls, 0)
    self.assertEqual(status["stale_disconnect_callbacks"], 1)

  def test_stale_connect_cannot_mark_replacement_client_connected(self):
    wrapper = _wrapper(command_qos=2)
    stale = _FakeMqttClient()
    current = _FakeMqttClient()
    wrapper._mqttc = current

    wrapper._callback_on_connect(stale, None, None, 0)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertFalse(wrapper.connected)
    self.assertEqual(status["stale_connect_callbacks"], 1)

  def test_slow_old_client_release_cannot_clear_replacement_state(self):
    wrapper = _wrapper(command_qos=2)
    teardown_started = Event()
    allow_teardown = Event()

    class _SlowClient(_FakeMqttClient):
      def disconnect(self):
        teardown_started.set()
        allow_teardown.wait(timeout=2.0)
        super().disconnect()

    old_client = _SlowClient()
    replacement = _FakeMqttClient()
    wrapper._mqttc = old_client
    wrapper.connected = True
    release_thread = Thread(target=wrapper.release)
    release_thread.start()
    self.assertTrue(teardown_started.wait(timeout=1.0))

    wrapper._mqttc = replacement
    wrapper.connected = True
    with wrapper._subscription_lock:
      wrapper._subscription_status["ready"] = True
    allow_teardown.set()
    release_thread.join(timeout=2.0)

    self.assertFalse(release_thread.is_alive())
    self.assertIs(wrapper._mqttc, replacement)
    self.assertTrue(wrapper.connected)
    self.assertTrue(wrapper.receive_ready)


class TestMqttSubscriptionLifecycle(unittest.TestCase):

  def test_subscribe_request_is_pending_until_suback(self):
    wrapper = _wrapper(receive=True)
    client = _FakeMqttClient(subscribe_mid=71)
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1)
    before_suback = wrapper.get_delivery_lifecycle_status()

    self.assertTrue(result["has_connection"])
    self.assertIn("request accepted", result["msg"])
    self.assertEqual(before_suback["subscribe_requested"], 1)
    self.assertEqual(before_suback["subscribe_pending"], 1)
    self.assertEqual(before_suback["subscribe_confirmed"], 0)

    wrapper._callback_on_subscribe(client, None, 71, [2])
    after_suback = wrapper.get_delivery_lifecycle_status()

    self.assertEqual(after_suback["subscribe_pending"], 0)
    self.assertEqual(after_suback["subscribe_confirmed"], 1)
    self.assertEqual(after_suback["subscribe_rejected"], 0)

  def test_rejected_suback_is_visible(self):
    wrapper = _wrapper(receive=True)
    client = _FakeMqttClient(subscribe_mid=72)
    wrapper._mqttc = client
    wrapper.subscribe(max_retries=1)

    wrapper._callback_on_subscribe(client, None, 72, [128])

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["subscribe_pending"], 0)
    self.assertEqual(status["subscribe_confirmed"], 0)
    self.assertEqual(status["subscribe_rejected"], 1)

  def test_downgraded_suback_is_confirmed_and_visible(self):
    wrapper = _wrapper(receive=True)
    client = _FakeMqttClient(subscribe_mid=75)
    wrapper._mqttc = client
    wrapper.subscribe(max_retries=1)

    wrapper._callback_on_subscribe(client, None, 75, [1])

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["subscribe_pending"], 0)
    self.assertEqual(status["subscribe_confirmed"], 1)
    self.assertEqual(status["subscribe_downgraded"], 1)

  def test_stale_suback_does_not_confirm_current_subscription(self):
    wrapper = _wrapper(receive=True)
    current = _FakeMqttClient(subscribe_mid=73)
    stale = _FakeMqttClient(subscribe_mid=73)
    wrapper._mqttc = current
    wrapper.subscribe(max_retries=1)

    wrapper._callback_on_subscribe(stale, None, 73, [2])

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["subscribe_pending"], 1)
    self.assertEqual(status["subscribe_confirmed"], 0)
    self.assertEqual(status["stale_subscribe_callbacks"], 1)

  def test_suback_race_before_subscribe_returns_is_conserved(self):
    wrapper = _wrapper(receive=True)
    client = _ImmediateCallbackClient(wrapper, subscribe_mid=74)
    wrapper._mqttc = client

    wrapper.subscribe(max_retries=1)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["subscribe_requested"], 1)
    self.assertEqual(status["subscribe_pending"], 0)
    self.assertEqual(status["subscribe_confirmed"], 1)

  def test_release_accounts_pending_subscription_and_publish(self):
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(command_qos=2),
      recv_buff=deque(),
      send_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient(publish_mid=76, subscribe_mid=77)
    wrapper._mqttc = client
    wrapper.send("command", send_to="0xNODE")
    wrapper.subscribe(max_retries=1)

    wrapper.release()

    status = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(status["publish_pending"], 0)
    self.assertEqual(status["publish_abandoned"], 1)
    self.assertEqual(status["subscribe_pending"], 0)
    self.assertEqual(status["subscribe_abandoned"], 1)
    self.assertTrue(status["publish_conserved"])
    self.assertTrue(status["subscribe_conserved"])

  def test_nonzero_subscribe_result_is_counted_as_handoff_rejection(self):
    wrapper = _wrapper(receive=True)
    wrapper._mqttc = _FakeMqttClient(subscribe_rc=5)

    result = wrapper.subscribe(max_retries=1)

    status = wrapper.get_delivery_lifecycle_status()
    self.assertFalse(result["has_connection"])
    self.assertEqual(status["subscribe_attempts"], 1)
    self.assertEqual(status["subscribe_handoff_accepted"], 0)
    self.assertEqual(status["subscribe_handoff_rejected"], 1)
    self.assertTrue(status["subscribe_conserved"])


class TestMqttReceiveAdmission(unittest.TestCase):

  def test_full_observable_buffer_is_counted_as_dropped(self):
    buffer = _RejectingBuffer()
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    client = _FakeMqttClient()
    wrapper._mqttc = client

    wrapper._callback_on_message(client, None, _Message())

    self.assertEqual(buffer.items, ["command"])
    self.assertEqual(wrapper.nr_dropped_messages, 1)

  def test_stale_message_after_release_is_not_admitted(self):
    buffer = deque()
    wrapper = MQTTWrapper(
      log=_FakeLog(),
      config=_config(),
      recv_buff=buffer,
      recv_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      verbosity=99,
    )
    stale = _FakeMqttClient()
    wrapper._mqttc = stale
    wrapper.release()

    wrapper._callback_on_message(stale, None, _Message())

    self.assertEqual(list(buffer), [])
    self.assertEqual(wrapper.nr_stale_messages, 1)


if __name__ == "__main__":
  unittest.main()
