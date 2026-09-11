"""Initial setup and shutdown use the real session cancellation predicate."""
import unittest
from unittest import mock

from ratio1.comm.heartbeat_observation import (
  HeartbeatObservationConfig,
  HeartbeatObservationMonitor,
)
from ratio1.default.session.mqtt_session import MqttSession
from test_mqtt_delivery_lifecycle import _ImmediateCallbackClient, _wrapper


ADDRESS = '0xai_' + 'A' * 43


def _session(mode='selected_nodes'):
  session = MqttSession.__new__(MqttSession)
  session._GenericSession__running_main_loop_thread = False
  session._GenericSession__closing = False
  session._GenericSession__closed_everything = False
  session._GenericSession__at_least_a_netmon_received = False
  session.P = session.Pd = lambda *args, **kwargs: None
  config = HeartbeatObservationConfig.from_values(
    mode=mode, nodes=[ADDRESS] if mode == 'selected_nodes' else None,
    summary_publishers=[ADDRESS] if mode == 'summary_discovery' else None,
    observation_timeout_seconds=.1,
  )
  session._heartbeat_observation_config = config
  session._heartbeat_observation_monitor = HeartbeatObservationMonitor(config)
  wrappers = [_wrapper(receive=True) for _ in range(3)]
  for index, wrapper in enumerate(wrappers):
    wrapper._explicit_recv_topics = ('startup/channel-' + str(index),)
    wrapper._require_suback = index == 1 and mode == 'selected_nodes'
    wrapper._mqttc = _ImmediateCallbackClient(wrapper)
    wrapper.connected = True
  if mode == 'summary_discovery':
    wrappers[1]._explicit_recv_topics = ()
  session._default_communicator, session._heartbeats_communicator, session._notifications_communicator = wrappers
  return session, wrappers


class TestMqttSessionStartup(unittest.TestCase):
  def test_initial_connect_subscribes_before_main_loop_starts(self):
    for mode in ('full_network', 'selected_nodes', 'summary_discovery'):
      with self.subTest(mode=mode):
        session, wrappers = _session(mode)
        self.addCleanup(session._communication_close)
        session._connect()
        expected = [1, 0 if mode == 'summary_discovery' else 1, 1]
        self.assertEqual([len(w.connection.subscribed) for w in wrappers], expected)
        self.assertTrue(session._connected)
        self.assertFalse(session._GenericSession__running_main_loop_thread)
        if mode == 'selected_nodes':
          status = session._heartbeat_observation_monitor.snapshot()
          self.assertTrue(status['subscription_ready'])
          self.assertEqual(status['state'], 'waiting_for_targeted_heartbeat')

  def test_close_during_setup_stops_follow_on_communicators(self):
    session, wrappers = _session()
    self.addCleanup(session._communication_close)
    session._GenericSession__running_main_loop_thread = True
    old_subscribe = wrappers[0].connection.subscribe

    def subscribe_and_close(**kwargs):
      result = old_subscribe(**kwargs)
      session.close(wait_close=False)
      return result

    wrappers[0].connection.subscribe = subscribe_and_close
    wrappers[1]._mqttc = None
    wrappers[2]._mqttc = None
    with mock.patch.object(wrappers[1], 'server_connect') as second, \
         mock.patch.object(wrappers[2], 'server_connect') as third:
      session._connect()
    second.assert_not_called()
    third.assert_not_called()
    self.assertFalse(session._communication_should_continue())

  def test_close_cancels_subscription_retry(self):
    session, wrappers = _session()
    self.addCleanup(session._communication_close)
    session._GenericSession__running_main_loop_thread = True
    calls = []

    def reject_and_close(**kwargs):
      calls.append(kwargs)
      session.close(wait_close=False)
      return 4, 1

    wrappers[0].connection.subscribe = reject_and_close
    with mock.patch('ratio1.comm.mqtt_wrapper.sleep', return_value=None):
      result = wrappers[0].subscribe(should_continue=session._communication_should_continue)
    self.assertEqual(len(calls), 1)
    self.assertFalse(result['has_connection'])

  def test_close_before_main_loop_start_runs_cleanup_without_reconnecting(self):
    for mode in ('full_network', 'selected_nodes', 'summary_discovery'):
      with self.subTest(mode=mode):
        session, wrappers = _session(mode)
        self.addCleanup(session._communication_close)
        session.close(wait_close=False)
        calls = []
        session._GenericSession__release_callback_threads = lambda: calls.append('callbacks')
        session._communication_close = lambda: calls.append('transport')

        class InlineThread:
          def __init__(self, target, **kwargs):
            self.target = target

          def start(self):
            self.target()

        with mock.patch('ratio1.base.generic_session.Thread', InlineThread), \
             mock.patch.object(session, '_connect', side_effect=AssertionError('reconnected after close')), \
             mock.patch('ratio1.base.generic_session.sleep', side_effect=AssertionError('waited after close')):
          session._GenericSession__start_main_loop_thread()
        self.assertEqual(calls, ['transport', 'callbacks'])
        self.assertTrue(session._GenericSession__closed_everything)
        self.assertFalse(session._communication_should_continue())


if __name__ == '__main__':
  unittest.main()
