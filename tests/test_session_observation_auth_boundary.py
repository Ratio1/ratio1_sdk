import json
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


class TestSessionObservationAuthBoundary(unittest.TestCase):

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


if __name__ == "__main__":
  unittest.main()
