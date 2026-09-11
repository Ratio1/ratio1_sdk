"""Deterministic disconnect interleavings at MQTT handoff boundaries."""

import unittest
from threading import Event, Thread, current_thread
from types import SimpleNamespace
from unittest import mock

from ratio1.default.session.mqtt_session import MqttSession
from test_mqtt_delivery_lifecycle import (
  _FakeMqttClient,
  _ImmediateCallbackClient,
  _wrapper,
)


class TestMqttGenerationRaces(unittest.TestCase):
  """Keep retired transport results out of replacement client state."""

  def test_retired_subscribe_cannot_publish_readiness(self):
    for require_suback in (False, True):
      with self.subTest(require_suback=require_suback):
        wrapper = _wrapper(receive=True)
        wrapper._require_suback = require_suback
        old = _ImmediateCallbackClient(wrapper)
        wrapper._mqttc = old
        record = wrapper._record_topic_status

        def disconnect_after_topic(*args, **kwargs):
          record(*args, **kwargs)
          wrapper.release(expected_client=old)

        with mock.patch.object(wrapper, '_record_topic_status', side_effect=disconnect_after_topic):
          result = wrapper.subscribe(max_retries=1, ack_timeout=0.1)

        self.assertFalse(result['has_connection'])
        self.assertFalse(wrapper.receive_ready)
        self.assertIsNone(wrapper.connection)

  def test_replacement_is_subscribed_before_session_reports_connected(self):
    wrapper = _wrapper(receive=True)
    old = _ImmediateCallbackClient(wrapper)
    wrapper._mqttc = old
    record = wrapper._record_topic_status

    def disconnect_after_topic(*args, **kwargs):
      record(*args, **kwargs)
      wrapper.release(expected_client=old)

    with mock.patch.object(wrapper, '_record_topic_status', side_effect=disconnect_after_topic):
      wrapper.subscribe(max_retries=1)

    class Replacement(_ImmediateCallbackClient):
      _client_id = b'replacement'

      def connect(self, **kwargs):
        wrapper._callback_on_connect(self, None, None, 0)

      def loop_start(self):
        return

    replacement = Replacement(wrapper)
    wrapper.log.get_unique_id = lambda: 'generation-test'
    other = SimpleNamespace(connection=object(), connected=True, receive_ready=True)
    session = MqttSession.__new__(MqttSession)
    session._default_communicator = wrapper
    session._heartbeats_communicator = other
    session._notifications_communicator = other
    session._communication_should_continue = lambda: True
    with mock.patch.object(wrapper, '_MQTTWrapper__create_mqttc_object', return_value=replacement):
      session._connect()

    self.assertEqual(len(replacement.subscribed), 1)
    self.assertTrue(session._connected)
    wrapper.release()

  def test_late_handoffs_are_abandoned_without_blocking_retirement(self):
    for operation in ('publish', 'subscribe'):
      with self.subTest(operation=operation):
        wrapper = _wrapper(receive=operation == 'subscribe')
        entered = Event()
        retired = Event()
        errors = []

        class PausedClient(_FakeMqttClient):
          def publish(self, **kwargs):
            result = super().publish(**kwargs)
            entered.set()
            if not retired.wait(2):
              raise AssertionError('retirement blocked by publish call')
            return result

          def subscribe(self, **kwargs):
            result = super().subscribe(**kwargs)
            entered.set()
            if not retired.wait(2):
              raise AssertionError('retirement blocked by subscribe call')
            return result

        old = PausedClient()
        wrapper._mqttc = old

        def handoff():
          try:
            if operation == 'publish':
              wrapper.send('command', send_to='0xNODE')
            else:
              wrapper.subscribe(max_retries=1, ack_timeout=0.1)
          except Exception as exc:
            errors.append(exc)

        thread = Thread(target=handoff, daemon=True)
        thread.start()
        self.assertTrue(entered.wait(1))
        try:
          wrapper.release(expected_client=old)
          wrapper._mqttc = _FakeMqttClient()
        finally:
          retired.set()
          thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        if operation == 'publish':
          wrapper._callback_on_publish(old, None, old.publish_mid)
        else:
          wrapper._callback_on_subscribe(old, None, old.subscribe_mid, [2])
        wrapper.release()
        status = wrapper.get_delivery_lifecycle_status()
        self.assertEqual(status[operation + '_pending'], 0)
        self.assertEqual(status[operation + '_abandoned'], 1)
        self.assertTrue(status[operation + '_conserved'])

  def test_retired_topic_result_cannot_overwrite_replacement_readiness(self):
    for grant in (2, 128):
      with self.subTest(grant=grant):
        wrapper = _wrapper(receive=True)
        wrapper._require_suback = True
        paused = Event()
        resume = Event()
        results = []

        class OldClient(_FakeMqttClient):
          def subscribe(self, **kwargs):
            result = super().subscribe(**kwargs)
            wrapper._callback_on_subscribe(self, None, result[1], [grant])
            return result

        old = OldClient()
        wrapper._mqttc = old
        record = wrapper._record_topic_status

        def pause_old_result(*args, **kwargs):
          if current_thread() is old_thread:
            paused.set()
            if not resume.wait(2):
              raise AssertionError('replacement blocked by retired topic result')
          record(*args, **kwargs)

        def subscribe_old():
          results.append(wrapper.subscribe(max_retries=1, ack_timeout=0.1))

        old_thread = Thread(target=subscribe_old, daemon=True)
        with mock.patch.object(wrapper, '_record_topic_status', side_effect=pause_old_result):
          old_thread.start()
          self.assertTrue(paused.wait(1))
          try:
            wrapper.release(expected_client=old)
            replacement = _ImmediateCallbackClient(wrapper)
            wrapper._mqttc = replacement
            self.assertTrue(wrapper.subscribe(max_retries=1, ack_timeout=0.1)['has_connection'])
            replacement_status = wrapper.get_subscription_status()
          finally:
            resume.set()
            old_thread.join(3)

        self.assertFalse(old_thread.is_alive())
        self.assertFalse(results[0]['has_connection'])
        self.assertEqual(wrapper.get_subscription_status(), replacement_status)
        wrapper.release()

  def test_old_waiter_cleanup_cannot_remove_replacement_same_mid_waiter(self):
    wrapper = _wrapper(receive=True)
    old = _FakeMqttClient()
    replacement = _FakeMqttClient()
    wrapper._mqttc = old
    old_waiting = Event()
    resume_old = Event()
    replacement_waiting = Event()
    results = {}

    class PausedEvent:
      def set(self):
        return

      def wait(self, timeout):
        old_waiting.set()
        return resume_old.wait(2)

    def wait_old():
      results['old'] = wrapper._wait_for_suback(7, 'old', 1, old)

    with mock.patch('ratio1.comm.mqtt_wrapper.Event', return_value=PausedEvent()):
      old_thread = Thread(target=wait_old, daemon=True)
      old_thread.start()
      self.assertTrue(old_waiting.wait(1))
    wrapper.release(expected_client=old)
    wrapper._mqttc = replacement

    class ReplacementEvent(Event):
      def wait(self, timeout):
        replacement_waiting.set()
        return super().wait(timeout)

    def wait_replacement():
      results['replacement'] = wrapper._wait_for_suback(7, 'new', 1, replacement)

    with mock.patch('ratio1.comm.mqtt_wrapper.Event', ReplacementEvent):
      replacement_thread = Thread(target=wait_replacement, daemon=True)
      replacement_thread.start()
      self.assertTrue(replacement_waiting.wait(1))
    resume_old.set()
    old_thread.join(2)
    wrapper._callback_on_subscribe(old, None, 7, [128])
    wrapper._callback_on_subscribe(replacement, None, 7, [2])
    replacement_thread.join(2)
    self.assertFalse(old_thread.is_alive())
    self.assertFalse(replacement_thread.is_alive())
    self.assertEqual(results['replacement'], (True, None))
    self.assertFalse(results['old'][0])
    wrapper.release()


if __name__ == '__main__':
  unittest.main()
