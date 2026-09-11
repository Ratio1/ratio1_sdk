import unittest
from dataclasses import FrozenInstanceError
from unittest import mock

from ratio1.base.generic_session import GenericSession
from ratio1.comm.heartbeat_observation import HeartbeatObservationConfig
from ratio1.const import COMMS
from ratio1.default.session.mqtt_session import MqttSession


NODE_A = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiF"
ORACLE = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMh"


class _Wrapper:
  def __init__(self, **kwargs):
    self.kwargs = kwargs


def _session(observation=None):
  session = object.__new__(MqttSession)
  session.log = object()
  session._config = {
    COMMS.COMMUNICATION_CTRL_CHANNEL: {
      COMMS.TOPIC: "ratio1/ctrl",
      COMMS.TARGETED_TOPIC: "ratio1/ctrl/{}",
    },
  }
  session._payload_messages = []
  session._hb_messages = []
  session._notif_messages = []
  session.name = "test"
  session._verbosity = 99
  if observation is not None:
    session._heartbeat_observation_config = observation
  return session


class TestMqttSessionObservationTopics(unittest.TestCase):

  def _startup(self, session):
    wrappers = []

    def build_wrapper(**kwargs):
      wrapper = _Wrapper(**kwargs)
      wrappers.append(wrapper)
      return wrapper

    with mock.patch(
      "ratio1.default.session.mqtt_session.MQTTWrapper",
      side_effect=build_wrapper,
    ), mock.patch.object(GenericSession, "startup", return_value=None):
      session.startup()
    return wrappers

  def test_no_observation_config_keeps_current_global_subscription(self):
    wrappers = self._startup(_session())

    heartbeat = wrappers[1].kwargs
    self.assertEqual(
      heartbeat["recv_channel_name"],
      COMMS.COMMUNICATION_CTRL_CHANNEL,
    )
    self.assertNotIn("recv_topics", heartbeat)
    self.assertNotIn("require_suback", heartbeat)

  def test_selected_mode_passes_exact_topics_and_requires_suback(self):
    observation = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE_A],
    )
    wrappers = self._startup(_session(observation))

    heartbeat = wrappers[1].kwargs
    self.assertEqual(heartbeat["recv_topics"], [f"ratio1/ctrl/{NODE_A}"])
    self.assertTrue(heartbeat["require_suback"])
    self.assertNotIn("ratio1/ctrl", heartbeat["recv_topics"])

  def test_summary_mode_disables_heartbeat_receive(self):
    observation = HeartbeatObservationConfig.from_values(
      mode="summary_discovery",
      summary_publishers=[ORACLE],
    )
    wrappers = self._startup(_session(observation))

    heartbeat = wrappers[1].kwargs
    self.assertEqual(heartbeat["recv_topics"], [])
    self.assertFalse(heartbeat["require_suback"])

  def test_observation_contract_is_immutable_after_session_creation(self):
    observation = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE_A],
    )
    session = _session(observation)

    with self.assertRaisesRegex(RuntimeError, "immutable"):
      session.set_heartbeat_observation(
        mode="full_network",
      )
    with self.assertRaises(FrozenInstanceError):
      observation.mode = "full_network"


if __name__ == "__main__":
  unittest.main()
