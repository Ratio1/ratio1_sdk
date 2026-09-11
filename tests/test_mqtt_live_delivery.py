import os
import threading
import time
import unittest
from unittest import mock
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt import __version__ as mqtt_version

from ratio1.comm.mqtt_wrapper import MQTTWrapper
from ratio1.const import COMMS


LIVE_HOST_ENV = "EE_TEST_MQTT_HOST"
LIVE_PORT_ENV = "EE_TEST_MQTT_PORT"


class _Log:
  def P(self, *args, **kwargs):
    return

  def get_unique_id(self):
    return uuid4().hex

  def time_to_str(self):
    return "test-time"


def _new_client(client_id):
  if mqtt_version.startswith("2"):
    return mqtt.Client(
      callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
      client_id=client_id,
      clean_session=True,
    )
  return mqtt.Client(client_id=client_id, clean_session=True)


@unittest.skipUnless(os.environ.get(LIVE_HOST_ENV), "isolated MQTT broker not configured")
class TestMqttLiveDelivery(unittest.TestCase):

  def test_receive_resubscribes_after_disconnect_during_ready_publication(self):
    host = os.environ[LIVE_HOST_ENV]
    port = int(os.environ.get(LIVE_PORT_ENV, '1883'))
    for require_suback in (False, True):
      with self.subTest(require_suback=require_suback):
        root = 'ecomms-generation-' + uuid4().hex
        received = threading.Event()
        config = {
          COMMS.HOST: host, COMMS.PORT: port, COMMS.USER: '', COMMS.PASS: '',
          COMMS.EE_ADDR: '0xai_SDK', COMMS.QOS: 1, COMMS.SECURED: 0,
          COMMS.COMMUNICATION_CTRL_CHANNEL: {COMMS.TOPIC: root + '/ctrl'},
        }
        wrapper = MQTTWrapper(
          log=_Log(), config=config, recv_buff=[],
          recv_channel_name=COMMS.COMMUNICATION_CTRL_CHANNEL,
          recv_topics=[root + '/ctrl'], require_suback=require_suback,
          on_message=lambda *args: received.set(), verbosity=99,
        )
        publisher = _new_client(root + '-publisher')
        try:
          self.assertTrue(wrapper.server_connect(max_retries=2)['has_connection'])
          old = wrapper.connection
          record = wrapper._record_topic_status

          def disconnect_before_ready(*args, **kwargs):
            record(*args, **kwargs)
            wrapper.release(expected_client=old)

          with mock.patch.object(wrapper, '_record_topic_status', side_effect=disconnect_before_ready):
            self.assertFalse(wrapper.subscribe(max_retries=1)['has_connection'])
          self.assertFalse(wrapper.receive_ready)
          self.assertTrue(wrapper.server_connect(max_retries=2)['has_connection'])
          self.assertIsNot(wrapper.connection, old)
          if not wrapper.receive_ready:
            self.assertTrue(wrapper.subscribe(max_retries=1)['has_connection'])
          publisher.connect(host, port)
          publisher.loop_start()
          result = publisher.publish(root + '/ctrl', 'after-reconnect', qos=1)
          result.wait_for_publish(timeout=5)
          self.assertTrue(result.is_published())
          self.assertTrue(received.wait(5), 'replacement missed its receive subscription')
        finally:
          wrapper.release()
          publisher.disconnect()
          publisher.loop_stop()

  def test_command_delivery_survives_heartbeat_burst_and_reconnect(self):
    host = os.environ[LIVE_HOST_ENV]
    port = int(os.environ.get(LIVE_PORT_ENV, "1883"))
    root = "ecomms-live-{}".format(uuid4().hex)
    node_address = "0xai_TEST_NODE"
    command_topic = "{}/{}/config".format(root, node_address)
    heartbeat_topic = "{}/ctrl".format(root)
    received_commands = []
    command_received = threading.Event()
    subscriber_connected = threading.Event()
    heartbeat_connected = threading.Event()

    subscriber = _new_client("ecomms-subscriber-" + uuid4().hex)

    def on_subscriber_connect(client, userdata, flags, reason_code, *args):
      if reason_code == 0:
        client.subscribe(command_topic, qos=2)
        subscriber_connected.set()

    def on_command(client, userdata, message):
      received_commands.append(message.payload.decode("utf-8"))
      command_received.set()

    subscriber.on_connect = on_subscriber_connect
    subscriber.on_message = on_command
    subscriber.connect(host, port)
    subscriber.loop_start()
    self.assertTrue(subscriber_connected.wait(5.0))

    heartbeat_publisher = _new_client("ecomms-heartbeats-" + uuid4().hex)

    def on_heartbeat_connect(client, userdata, flags, reason_code, *args):
      if reason_code == 0:
        heartbeat_connected.set()

    heartbeat_publisher.on_connect = on_heartbeat_connect
    heartbeat_publisher.connect(host, port)
    heartbeat_publisher.loop_start()
    self.assertTrue(heartbeat_connected.wait(5.0))

    config = {
      COMMS.HOST: host,
      COMMS.PORT: port,
      COMMS.USER: "",
      COMMS.PASS: "",
      COMMS.EE_ADDR: "0xai_SDK",
      COMMS.QOS: 0,
      COMMS.SECURED: 0,
      COMMS.COMMUNICATION_CONFIG_CHANNEL: {
        COMMS.TOPIC: root + "/{}/config",
        COMMS.QOS: 2,
      },
    }
    command_publisher = MQTTWrapper(
      log=_Log(),
      config=config,
      send_channel_name=COMMS.COMMUNICATION_CONFIG_CHANNEL,
      connection_name="ecomms-command",
      verbosity=99,
    )
    self.assertTrue(command_publisher.server_connect(max_retries=2)["has_connection"])

    def publish_heartbeat_burst():
      payload = "h" * 6000
      for idx in range(2000):
        heartbeat_publisher.publish(
          heartbeat_topic,
          payload="{}:{}".format(idx, payload),
          qos=1,
        )

    burst = threading.Thread(target=publish_heartbeat_burst, daemon=True)
    burst.start()
    started = time.monotonic()
    command_publisher.send("command-1", send_to=node_address)
    self.assertTrue(command_received.wait(5.0))
    first_latency = time.monotonic() - started
    burst.join(timeout=10.0)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
      if command_publisher.get_delivery_lifecycle_status()["broker_acknowledged"] >= 1:
        break
      time.sleep(0.01)

    first_status = command_publisher.get_delivery_lifecycle_status()
    self.assertLess(first_latency, 2.0)
    self.assertEqual(received_commands[0], "command-1")
    self.assertGreaterEqual(first_status["broker_acknowledged"], 1)

    command_publisher.release()
    self.assertTrue(command_publisher.server_connect(max_retries=2)["has_connection"])
    command_received.clear()
    command_publisher.send("command-2", send_to=node_address)
    self.assertTrue(command_received.wait(5.0))
    self.assertEqual(received_commands[-1], "command-2")

    command_publisher.release()
    heartbeat_publisher.disconnect()
    heartbeat_publisher.loop_stop()
    subscriber.disconnect()
    subscriber.loop_stop()


if __name__ == "__main__":
  unittest.main()
