import json
import threading
import unittest

from ratio1.base.generic_session import GenericSession
from ratio1.comm.heartbeat_observation import (
  HeartbeatObservationConfig,
  ObservationDecision,
)


NODE = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiF"


class _Policy:
  def __init__(self, events):
    self.events = events
    self.inputs = []

  def authorize_heartbeat(self, raw_message, now=None):
    self.events.append("verify")
    self.inputs.append(raw_message)
    return ObservationDecision(
      accepted=True,
      reason="accepted",
      sender=NODE,
      envelope=json.loads(raw_message),
    )


class _MutatingFormatter:
  def __init__(self, events):
    self.events = events

  def decode_output(self, payload):
    self.events.append("decode")
    payload["EE_SENDER"] = "0xai_formatter_rewrite"
    return payload


class _FormatterWrapper:
  def __init__(self, events):
    self.formatter = _MutatingFormatter(events)

  def get_required_formatter_from_payload(self, payload):
    return self.formatter


class _Monitor:
  def __init__(self, events):
    self.events = events
    self.observations = []

  def record_valid_observation(self, sender, source):
    self.events.append("ready")
    self.observations.append((sender, source))


class TestSessionObservationAuthBoundary(unittest.TestCase):

  def _heartbeat_session(self, events):
    session = object.__new__(GenericSession)
    session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE],
    )
    session._heartbeat_observation_policy = _Policy(events)
    session._heartbeat_observation_monitor = _Monitor(events)
    session.formatter_wrapper = _FormatterWrapper(events)
    session._dct_online_nodes_last_heartbeat = {}
    session._dct_node_whitelist = {}
    session._GenericSession__open_transactions = []
    session._GenericSession__open_transactions_lock = threading.Lock()
    session._GenericSession__track_online_node = (
      lambda **kwargs: events.append("internal")
    )
    session._GenericSession__maybe_ignore_message = lambda *args: False
    session._GenericSession__track_allowed_node_by_hb = lambda *args: None
    session._shorten_addr = lambda address: address
    session.bc_engine = type(
      "_Blockchain",
      (),
      {"contains_current_address": lambda self, whitelist: False},
    )()
    session.D = lambda *args, **kwargs: None
    return session

  def test_selected_heartbeat_verification_precedes_formatter_decode(self):
    events = []
    session = object.__new__(GenericSession)
    session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE],
    )
    session._heartbeat_observation_policy = _Policy(events)
    session.formatter_wrapper = _FormatterWrapper(events)
    session.D = lambda *args, **kwargs: None
    callback_inputs = []

    def callback(*args, **kwargs):
      events.append("callback")
      callback_inputs.append((args, kwargs))

    raw_envelope = {
      "EE_SENDER": NODE,
      "EE_SIGN": "signature",
      "EE_HASH": "hash",
      "EE_TIMESTAMP": "2026-08-17 10:00:00.000000",
      "EE_TIMEZONE": "UTC+0",
      "EE_PAYLOAD_PATH": ["node", None, None, None],
    }

    session._GenericSession__on_message_default_callback(
      json.dumps(raw_envelope),
      callback,
      source="heartbeat",
    )

    self.assertEqual(events, ["verify", "decode", "callback"])
    verified = json.loads(session._heartbeat_observation_policy.inputs[0])
    self.assertEqual(verified["EE_SENDER"], NODE)
    self.assertEqual(callback_inputs[0][0][1], NODE)

  def test_verified_readiness_does_not_depend_on_user_callback_success(self):
    events = []
    session = self._heartbeat_session(events)

    def failing_callback(*args):
      events.append("callback")
      raise RuntimeError("user callback failed")

    session.custom_on_heartbeat = failing_callback

    raw_envelope = {
      "EE_SENDER": NODE,
      "EE_ID": "selected-node",
      "EE_SIGN": "signature",
      "EE_HASH": "hash",
      "EE_TIMESTAMP": "2026-08-17 10:00:00.000000",
      "EE_TIMEZONE": "UTC+0",
      "EE_PAYLOAD_PATH": ["node", None, None, None],
    }

    with self.assertRaisesRegex(RuntimeError, "user callback failed"):
      session._GenericSession__on_message_default_callback(
        json.dumps(raw_envelope),
        session._GenericSession__on_heartbeat,
        source="heartbeat",
      )

    self.assertEqual(
      events,
      ["verify", "decode", "internal", "ready", "callback"],
    )
    self.assertEqual(
      session._heartbeat_observation_monitor.observations,
      [(NODE, "heartbeat")],
    )

  def test_internal_heartbeat_failure_does_not_mark_readiness(self):
    events = []
    session = self._heartbeat_session(events)
    session.custom_on_heartbeat = None
    raw_envelope = {
      "EE_SENDER": NODE,
      "EE_SIGN": "signature",
      "EE_HASH": "hash",
      "EE_TIMESTAMP": "2026-08-17 10:00:00.000000",
      "EE_TIMEZONE": "UTC+0",
      "EE_PAYLOAD_PATH": ["node", None, None, None],
    }

    with self.assertRaises(KeyError):
      session._GenericSession__on_message_default_callback(
        json.dumps(raw_envelope),
        session._GenericSession__on_heartbeat,
        source="heartbeat",
      )

    self.assertEqual(events, ["verify", "decode"])
    self.assertEqual(session._heartbeat_observation_monitor.observations, [])


if __name__ == "__main__":
  unittest.main()
