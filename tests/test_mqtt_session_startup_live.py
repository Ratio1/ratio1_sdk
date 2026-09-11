"""Real constructor subscriptions against an explicitly configured test broker."""
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from ratio1 import Session
from ratio1.bc import DefaultBlockEngine
from ratio1.logging import Logger
from test_mqtt_live_delivery import LIVE_HOST_ENV, LIVE_PORT_ENV, _new_client


ADDRESS = '0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiF'


class _ObservedSession(Session):
  """Capture the real first connection before the main loop can repair it."""

  START_TIMEOUT = .2

  def __init__(self, on_initial_connect=None, **kwargs):
    """Retain an optional test synchronization hook and initialize normally."""
    self.initial_setup = None
    self.on_initial_connect = on_initial_connect
    super().__init__(**kwargs)

  def _connect(self):
    """Record initial subscription evidence without replacing transport logic."""
    super()._connect()
    if self.initial_setup is None:
      self.initial_setup = {
        'running': self._GenericSession__running_main_loop_thread,
        'subscriptions': [
          wrapper.get_delivery_lifecycle_status()['subscribe_handoff_accepted']
          for wrapper in (
            self._default_communicator,
            self._heartbeats_communicator,
            self._notifications_communicator,
          )
        ],
        'observation': self.get_heartbeat_observation_status(),
      }
      if self.on_initial_connect is not None:
        self.on_initial_connect(self)


@unittest.skipUnless(os.environ.get(LIVE_HOST_ENV), 'isolated MQTT broker not configured')
class TestMqttSessionStartupLive(unittest.TestCase):
  """Exercise construction, selected observations, reconnect, and early close."""

  def _kwargs(self, cache, mode, address=ADDRESS):
    """Keep all session state and MQTT topics local to this test."""
    return dict(
      host=os.environ[LIVE_HOST_ENV],
      port=int(os.environ.get(LIVE_PORT_ENV, '1883')),
      user='test', pwd='test', secured=False,
      name='startup-' + uuid4().hex, root_topic='startup-' + uuid4().hex,
      auto_configuration=False, run_dauth=False, eth_enabled=False,
      use_home_folder=False, local_cache_base_folder=cache,
      local_cache_app_folder='session', silent=True, verbosity=0,
      heartbeat_observation_mode=mode,
      heartbeat_observation_nodes=[address] if mode == 'selected_nodes' else None,
      heartbeat_summary_publishers=[address] if mode == 'summary_discovery' else None,
      heartbeat_observation_timeout_seconds=3,
    )

  def _assert_initial_subscriptions(self, session, mode):
    """Require handoffs in the first synchronous connect, not later retries."""
    initial = session.initial_setup
    self.assertFalse(initial['running'])
    for count, active in zip(initial['subscriptions'], (True, mode != 'summary_discovery', True)):
      if active:
        self.assertGreater(count, 0, initial)
      else:
        self.assertEqual(count, 0, initial)

  def _close(self, session):
    """Bound cleanup so a shutdown regression fails instead of hanging tests."""
    session.close(wait_close=False)
    session._main_loop_thread.join(timeout=10)
    self.assertFalse(session._main_loop_thread.is_alive(), 'session cleanup hung')
    self.assertTrue(session._GenericSession__closed_everything)

  def test_constructor_subscribes_in_all_modes_before_main_loop(self):
    """Healthy targeted subscriptions must wait for the missing heartbeat."""
    for mode in ('full_network', 'selected_nodes', 'summary_discovery'):
      with self.subTest(mode=mode), tempfile.TemporaryDirectory() as cache:
        session = _ObservedSession(**self._kwargs(cache, mode))
        try:
          self._assert_initial_subscriptions(session, mode)
          self.assertTrue(session._connected)
          if mode == 'selected_nodes':
            initial = session.initial_setup['observation']
            self.assertTrue(initial['subscription_ready'])
            self.assertEqual(initial['state'], 'waiting_for_targeted_heartbeat')
            status = session.get_heartbeat_observation_status()
            self.assertEqual(status['reason'], 'targeted_heartbeat_timeout')
        finally:
          self._close(session)

  def test_selected_constructor_waits_for_signed_heartbeat_and_reconnects(self):
    """Delayed authenticated observations must unblock the original constructor."""
    with tempfile.TemporaryDirectory() as cache:
      signer = DefaultBlockEngine(
        name='signer-' + uuid4().hex,
        log=Logger(lib_name='signer', base_folder=cache, app_folder='signer', silent=True),
        config={'PEM_FILE': os.path.join(cache, 'signer.pem')},
        eth_enabled=False, verbosity=0,
      )
      kwargs = self._kwargs(cache, 'selected_nodes', signer.address)
      initial_connected = threading.Event()
      stop = threading.Event()
      published = threading.Event()
      reconnected = threading.Event()
      received_after_reconnect = threading.Event()
      failures = []
      publisher = _new_client('startup-publisher-' + uuid4().hex)
      publisher.connect(kwargs['host'], kwargs['port'])
      publisher.loop_start()

      def publish_heartbeats():
        """Publish only after first setup, with a visible observation delay."""
        try:
          if not initial_connected.wait(10) or stop.wait(.35):
            return
          while not stop.is_set():
            heartbeat = {
              'EE_EVENT_TYPE': 'HEARTBEAT', 'EE_ID': 'startup_peer',
              'EE_ADDR': signer.address,
              'EE_TIMESTAMP': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f'),
              'EE_TIMEZONE': 'UTC+0', 'EE_TZ': 'Etc/UTC',
              'EE_PAYLOAD_PATH': ['startup_peer', None, None, None],
              'TEST_AFTER_RECONNECT': reconnected.is_set(),
            }
            signer.sign(heartbeat)
            result = publisher.publish(
              kwargs['root_topic'] + '/ctrl/' + signer.address,
              json.dumps(heartbeat), qos=1,
            )
            result.wait_for_publish(timeout=5)
            if not result.is_published():
              raise AssertionError('heartbeat publish was not acknowledged')
            published.set()
            stop.wait(.1)
        except Exception as exc:
          failures.append(exc)

      thread = threading.Thread(target=publish_heartbeats, daemon=True)
      thread.start()
      session = None
      try:
        session = _ObservedSession(
          on_initial_connect=lambda _: initial_connected.set(),
          on_heartbeat=lambda _, __, message: (
            received_after_reconnect.set() if message.get('TEST_AFTER_RECONNECT') else None
          ),
          **kwargs,
        )
        self._assert_initial_subscriptions(session, 'selected_nodes')
        self.assertEqual(session.initial_setup['observation']['state'], 'waiting_for_targeted_heartbeat')
        status = session.get_heartbeat_observation_status()
        self.assertTrue(published.is_set(), failures)
        self.assertEqual(status['state'], 'ready', status)
        self.assertEqual(status['last_valid_sender'], signer.address)
        self.assertGreaterEqual(status['accepted_heartbeats'], 1)

        wrapper = session._heartbeats_communicator
        old_client = wrapper.connection
        wrapper.release(expected_client=old_client)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
          if (wrapper.connection is not None and wrapper.connection is not old_client
              and wrapper.receive_ready):
            break
          time.sleep(.05)
        self.assertIsNot(wrapper.connection, old_client)
        self.assertTrue(wrapper.receive_ready)
        reconnected.set()
        self.assertTrue(received_after_reconnect.wait(5), 'no new heartbeat after replacement SUBACK')
        status = session.get_heartbeat_observation_status()
        self.assertGreater(status['accepted_heartbeats'], 1)
        self.assertEqual(status['heartbeat_topics'], [kwargs['root_topic'] + '/ctrl/' + signer.address])
        self.assertFalse(failures)
      finally:
        stop.set()
        thread.join(timeout=6)
        publisher.disconnect()
        publisher.loop_stop()
        if session is not None:
          self._close(session)
        self.assertFalse(thread.is_alive(), 'publisher did not stop')

  def test_close_during_constructor_keeps_shutdown_sticky(self):
    """The real constructor must finish cleanup without resuming retries."""
    for mode in ('full_network', 'selected_nodes', 'summary_discovery'):
      with self.subTest(mode=mode), tempfile.TemporaryDirectory() as cache:
        session = _ObservedSession(
          on_initial_connect=lambda current: current.close(wait_close=False),
          **self._kwargs(cache, mode),
        )
        self._close(session)
        self._assert_initial_subscriptions(session, mode)
        self.assertFalse(session._communication_should_continue())
        self.assertFalse(session._connected)


if __name__ == '__main__':
  unittest.main()
