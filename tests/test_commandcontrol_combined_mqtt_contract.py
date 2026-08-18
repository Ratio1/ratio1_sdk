import threading
import unittest

import paho.mqtt.client as mqtt

from ratio1.comm.heartbeat_observation import (
  HEARTBEAT_MODE_FULL_NETWORK,
  HEARTBEAT_MODE_SELECTED_NODES,
  HeartbeatObservationConfig,
)
from ratio1.comm.message_buffer import ObservableMessageBuffer
from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


NODE = "0xai_12345678901234567890"


class _Log:
  def P(self, *args, **kwargs):
    return

  def time_to_str(self):
    return "time"


class _PublishResult:
  def __init__(self, rc=mqtt.MQTT_ERR_SUCCESS, mid=1):
    self.rc = rc
    self.mid = mid


class _Client:
  def __init__(self, wrapper=None, publish_rc=0, publish_mid=1, grant=1):
    self.wrapper = wrapper
    self.publish_rc = publish_rc
    self.publish_mid = publish_mid
    self.grant = grant
    self.next_mid = 10
    self.subscribed = []
    self.disconnect_calls = 0
    self.loop_stop_calls = 0

  def publish(self, topic, payload, qos):
    return _PublishResult(self.publish_rc, self.publish_mid)

  def subscribe(self, topic, qos):
    self.next_mid += 1
    mid = self.next_mid
    self.subscribed.append((topic, qos))
    if self.wrapper is not None:
      threading.Timer(
        0.01,
        lambda: self.wrapper._callback_on_subscribe(
          self,
          None,
          mid,
          [self.grant],
        ),
      ).start()
    return mqtt.MQTT_ERR_SUCCESS, mid

  def disconnect(self):
    self.disconnect_calls += 1

  def loop_stop(self):
    self.loop_stop_calls += 1


class _SynchronousDisconnectClient(_Client):
  def disconnect(self):
    super().disconnect()
    self.wrapper._callback_on_disconnect(self, None, 0)


class _DisconnectRaisesClient(_Client):
  def disconnect(self):
    super().disconnect()
    raise RuntimeError("disconnect failed")


class _Message:
  def __init__(self, payload=b"heartbeat"):
    self.payload = payload
    self.topic = "ratio1/ctrl/{}".format(NODE)


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
      COMMS.TARGETED_TOPIC: "ratio1/ctrl/{}",
      COMMS.QOS: 1,
    },
    COMMS.COMMUNICATION_CONFIG_CHANNEL: {
      COMMS.TOPIC: "ratio1/{}/config",
      COMMS.QOS: 2,
    },
  }


def _wrapper(buffer=None, receive=True, send=True, require_suback=True):
  return MQTTWrapper(
    log=_Log(),
    config=_config(),
    recv_buff=buffer,
    send_channel_name=(
      COMMS.COMMUNICATION_CONFIG_CHANNEL if send else None
    ),
    recv_channel_name=(
      COMMS.COMMUNICATION_CTRL_CHANNEL if receive else None
    ),
    recv_topics=("ratio1/ctrl/{}".format(NODE),) if receive else None,
    require_suback=require_suback,
    verbosity=99,
  )


class TestCombinedMqttContract(unittest.TestCase):

  def test_default_mode_is_global_and_selected_mode_is_exact_only(self):
    channel = _config()[COMMS.COMMUNICATION_CTRL_CHANNEL]

    default = HeartbeatObservationConfig.from_values()
    selected = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE],
    )

    self.assertEqual(default.mode, HEARTBEAT_MODE_FULL_NETWORK)
    self.assertEqual(default.heartbeat_topics(channel), ("ratio1/ctrl",))
    self.assertEqual(
      selected.heartbeat_topics(channel),
      ("ratio1/ctrl/{}".format(NODE),),
    )
    self.assertNotIn("ratio1/ctrl", selected.heartbeat_topics(channel))

  def test_exact_suback_readiness_and_lifecycle_share_one_callback(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = _wrapper(buffer=buffer)
    client = _Client(wrapper=wrapper)
    wrapper._mqttc = client

    result = wrapper.subscribe(max_retries=1, ack_timeout=0.2)

    self.assertTrue(result["has_connection"])
    self.assertTrue(wrapper.receive_ready)
    self.assertEqual(client.subscribed, [("ratio1/ctrl/{}".format(NODE), 1)])
    self.assertTrue(wrapper.get_subscription_status()["ready"])
    lifecycle = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(lifecycle["subscribe_confirmed"], 1)
    self.assertEqual(lifecycle["subscribe_pending"], 0)
    self.assertTrue(lifecycle["subscribe_conserved"])

  def test_publish_rejection_and_missing_client_are_not_reported_as_handoff(self):
    wrapper = _wrapper(buffer=ObservableMessageBuffer(1), receive=False)

    with self.assertRaises(RuntimeError):
      wrapper.send("command", send_to=NODE)

    wrapper._mqttc = _Client(publish_rc=mqtt.MQTT_ERR_NO_CONN)
    with self.assertRaises(RuntimeError):
      wrapper.send("command", send_to=NODE)

    lifecycle = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(lifecycle["publish_attempts"], 2)
    self.assertEqual(lifecycle["publish_handoff_rejected"], 2)
    self.assertEqual(lifecycle["publish_handoff_accepted"], 0)

  def test_stale_callbacks_cannot_mutate_current_generation(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = _wrapper(buffer=buffer)
    active = _Client(wrapper=wrapper)
    stale = _Client(wrapper=wrapper)
    wrapper._mqttc = active

    wrapper._callback_on_connect(stale, None, None, 0)
    wrapper._callback_on_disconnect(stale, None, 1)
    wrapper._callback_on_publish(stale, None, 7)
    wrapper._callback_on_subscribe(stale, None, 8, [1])
    wrapper._callback_on_message(stale, None, _Message())

    lifecycle = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(len(buffer), 0)
    self.assertEqual(lifecycle["stale_connect_callbacks"], 1)
    self.assertEqual(lifecycle["stale_disconnect_callbacks"], 1)
    self.assertEqual(lifecycle["stale_publish_callbacks"], 1)
    self.assertEqual(lifecycle["stale_subscribe_callbacks"], 1)
    self.assertEqual(wrapper.nr_stale_messages, 1)

  def test_release_accounts_pending_work_and_rejects_late_message(self):
    buffer = ObservableMessageBuffer(capacity=2)
    wrapper = _wrapper(
      buffer=buffer,
      require_suback=False,
    )
    client = _Client(wrapper=None, publish_mid=31)
    wrapper._mqttc = client
    wrapper.send("command", send_to=NODE)
    self.assertTrue(wrapper.subscribe(max_retries=1)["has_connection"])

    wrapper.release()
    wrapper._callback_on_message(client, None, _Message())

    lifecycle = wrapper.get_delivery_lifecycle_status()
    self.assertEqual(lifecycle["publish_abandoned"], 1)
    self.assertEqual(lifecycle["subscribe_abandoned"], 1)
    self.assertTrue(lifecycle["publish_conserved"])
    self.assertTrue(lifecycle["subscribe_conserved"])
    self.assertEqual(len(buffer), 0)
    self.assertEqual(wrapper.nr_stale_messages, 1)

  def test_release_retires_active_client_before_disconnect_callback(self):
    wrapper = _wrapper(
      buffer=ObservableMessageBuffer(capacity=1),
      receive=False,
    )
    client = _SynchronousDisconnectClient(wrapper=wrapper)
    wrapper._mqttc = client

    wrapper.release()

    lifecycle = wrapper.get_delivery_lifecycle_status()
    self.assertIsNone(wrapper._mqttc)
    self.assertEqual(client.disconnect_calls, 1)
    self.assertEqual(client.loop_stop_calls, 1)
    self.assertEqual(lifecycle["intentional_disconnect_callbacks"], 1)

  def test_release_stops_loop_and_finishes_cleanup_when_disconnect_raises(self):
    wrapper = _wrapper(
      buffer=ObservableMessageBuffer(capacity=1),
      receive=False,
    )
    client = _DisconnectRaisesClient(wrapper=wrapper)
    wrapper._mqttc = client

    result = wrapper.release()

    self.assertIsNone(wrapper._mqttc)
    self.assertFalse(wrapper.connected)
    self.assertEqual(client.disconnect_calls, 1)
    self.assertEqual(client.loop_stop_calls, 1)
    self.assertIn("disconnect failed", result["msgs"][0])


if __name__ == "__main__":
  unittest.main()
