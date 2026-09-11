import json
import math
import unittest
from unittest import mock
from datetime import datetime, timezone

from ratio1 import (
  HEARTBEAT_MODE_FULL_NETWORK as PUBLIC_FULL_NETWORK,
  HEARTBEAT_MODE_SELECTED_NODES as PUBLIC_SELECTED_NODES,
  HEARTBEAT_MODE_SUMMARY_DISCOVERY as PUBLIC_SUMMARY_DISCOVERY,
)
from ratio1.comm.heartbeat_observation import (
  HEARTBEAT_MODE_FULL_NETWORK,
  HEARTBEAT_MODE_SELECTED_NODES,
  HEARTBEAT_MODE_SUMMARY_DISCOVERY,
  HeartbeatObservationConfig,
  HeartbeatObservationMonitor,
  HeartbeatObservationPolicy,
)
from ratio1.const import COMMS


NODE_A = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiF"
NODE_B = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiG"
ORACLE = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMh"


class _VerifyResult:
  def __init__(self, valid, sender, message=""):
    self.valid = valid
    self.sender = sender
    self.message = message


class _Verifier:
  def __init__(self, valid=True, sender=None):
    self.valid = valid
    self.sender = sender
    self.calls = []

  def verify(self, payload, **kwargs):
    self.calls.append((payload, kwargs))
    sender = self.sender or payload.get("EE_SENDER")
    return _VerifyResult(self.valid, sender, "test verification result")


class _Clock:
  def __init__(self, value=0.0):
    self.value = value

  def __call__(self):
    return self.value


def _decompress_text(value):
  return value


def _channel_config():
  return {
    COMMS.TOPIC: "ratio1/ctrl",
    COMMS.TARGETED_TOPIC: "ratio1/ctrl/{}",
  }


def _signed_envelope(sender=NODE_A, timestamp="2026-08-17 10:00:00.000000"):
  return {
    "EE_SENDER": sender,
    "EE_SIGN": "signature",
    "EE_HASH": "digest",
    "EE_TIMESTAMP": timestamp,
    "EE_TIMEZONE": "UTC+0",
    "EE_TZ": "Etc/UTC",
    "EE_PAYLOAD_PATH": ["node", "admin_pipeline", "NET_MON_01", "instance"],
    "CURRENT_NETWORK": {
      NODE_A: {
        "address": NODE_A,
        "working": "ONLINE",
      },
    },
  }


class TestHeartbeatObservationConfig(unittest.TestCase):

  def test_mode_constants_are_exported_by_the_public_package(self):
    self.assertEqual(PUBLIC_FULL_NETWORK, HEARTBEAT_MODE_FULL_NETWORK)
    self.assertEqual(PUBLIC_SELECTED_NODES, HEARTBEAT_MODE_SELECTED_NODES)
    self.assertEqual(PUBLIC_SUMMARY_DISCOVERY, HEARTBEAT_MODE_SUMMARY_DISCOVERY)

  def test_omitted_mode_preserves_global_ctrl_subscription(self):
    config = HeartbeatObservationConfig.from_values()

    self.assertEqual(config.mode, HEARTBEAT_MODE_FULL_NETWORK)
    self.assertEqual(config.heartbeat_topics(_channel_config()), ("ratio1/ctrl",))

  def test_explicit_full_network_matches_omitted_mode(self):
    implicit = HeartbeatObservationConfig.from_values()
    explicit = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_FULL_NETWORK,
    )

    self.assertEqual(explicit, implicit)

  def test_selected_nodes_uses_only_exact_targeted_topics(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A, NODE_B, NODE_A],
    )

    self.assertEqual(config.nodes, (NODE_A, NODE_B))
    self.assertEqual(
      config.heartbeat_topics(_channel_config()),
      (f"ratio1/ctrl/{NODE_A}", f"ratio1/ctrl/{NODE_B}"),
    )
    self.assertNotIn("ratio1/ctrl", config.heartbeat_topics(_channel_config()))

  def test_summary_discovery_has_no_heartbeat_subscription(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SUMMARY_DISCOVERY,
      summary_publishers=[ORACLE],
    )

    self.assertEqual(config.heartbeat_topics(_channel_config()), ())

  def test_reduced_modes_fail_closed_on_missing_inputs(self):
    with self.assertRaisesRegex(ValueError, "selected node"):
      HeartbeatObservationConfig.from_values(
        mode=HEARTBEAT_MODE_SELECTED_NODES,
        nodes=[],
      )

    with self.assertRaisesRegex(ValueError, "summary publisher"):
      HeartbeatObservationConfig.from_values(
        mode=HEARTBEAT_MODE_SUMMARY_DISCOVERY,
        summary_publishers=[],
      )

  def test_aliases_and_unknown_modes_are_rejected(self):
    with self.assertRaisesRegex(ValueError, "Ratio1 node address"):
      HeartbeatObservationConfig.from_values(
        mode=HEARTBEAT_MODE_SELECTED_NODES,
        nodes=["node-alias"],
      )

    with self.assertRaisesRegex(ValueError, "heartbeat observation mode"):
      HeartbeatObservationConfig.from_values(mode="selected")

    for invalid_mode in ("", False, 0):
      with self.subTest(invalid_mode=invalid_mode):
        with self.assertRaisesRegex(ValueError, "heartbeat observation mode"):
          HeartbeatObservationConfig.from_values(mode=invalid_mode)

  def test_address_lists_reject_non_iterable_config_values_cleanly(self):
    for invalid_nodes in (True, 42, {NODE_A: True}):
      with self.subTest(invalid_nodes=invalid_nodes):
        with self.assertRaisesRegex(ValueError, "selected nodes"):
          HeartbeatObservationConfig.from_values(
            mode=HEARTBEAT_MODE_SELECTED_NODES,
            nodes=invalid_nodes,
          )

  def test_targeted_mode_requires_targeted_topic_capability(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
    )

    with self.assertRaisesRegex(ValueError, "TARGETED_TOPIC"):
      config.heartbeat_topics({COMMS.TOPIC: "ratio1/ctrl"})

  def test_observation_limits_reject_non_finite_values(self):
    fields = (
      "max_age_seconds",
      "future_skew_seconds",
      "observation_timeout_seconds",
    )
    values = (math.nan, math.inf, -math.inf, "nan", "inf", "-inf")
    for field_name in fields:
      for value in values:
        with self.subTest(field_name=field_name, value=value):
          with self.assertRaisesRegex(ValueError, "finite"):
            HeartbeatObservationConfig.from_values(**{
              field_name: value,
            })

  def test_observation_limits_reject_booleans_as_numeric_values(self):
    fields = (
      "max_age_seconds",
      "future_skew_seconds",
      "observation_timeout_seconds",
    )
    for field_name in fields:
      for value in (True, False):
        with self.subTest(field_name=field_name, value=value):
          with self.assertRaisesRegex(ValueError, "numeric"):
            HeartbeatObservationConfig.from_values(**{
              field_name: value,
            })

  def test_explicit_values_override_config_values(self):
    config = HeartbeatObservationConfig.from_sources(
      {
        "HEARTBEAT_OBSERVATION_MODE": "selected_nodes",
        "HEARTBEAT_OBSERVATION_NODES": [NODE_A],
      },
      mode="full_network",
    )

    self.assertEqual(config.mode, "full_network")
    self.assertEqual(config.nodes, ())


class TestHeartbeatObservationPolicy(unittest.TestCase):

  def setUp(self):
    self.now = datetime(2026, 8, 17, 10, 0, 30, tzinfo=timezone.utc)

  def test_selected_heartbeat_is_verified_before_acceptance(self):
    verifier = _Verifier()
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
      max_age_seconds=60,
    )
    policy = HeartbeatObservationPolicy(
      config=config,
      verifier=verifier,
      decompress_text=_decompress_text,
    )
    envelope = _signed_envelope()

    result = policy.authorize_heartbeat(json.dumps(envelope), now=self.now)

    self.assertTrue(result.accepted)
    self.assertEqual(result.sender, NODE_A)
    self.assertEqual(verifier.calls[0][0], envelope)
    self.assertFalse(verifier.calls[0][1]["log_hash_sign_fails"])

  def test_selected_heartbeat_rejects_bad_signature_or_unselected_sender(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
    )

    bad_signature = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(valid=False),
    ).authorize_heartbeat(json.dumps(_signed_envelope()), now=self.now)
    unselected = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(),
    ).authorize_heartbeat(
      json.dumps(_signed_envelope(sender=NODE_B)),
      now=self.now,
    )

    self.assertFalse(bad_signature.accepted)
    self.assertEqual(bad_signature.reason, "invalid_signature")
    self.assertFalse(unselected.accepted)
    self.assertEqual(unselected.reason, "unselected_sender")

  def test_selected_heartbeat_rejects_stale_and_future_timestamps(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
      max_age_seconds=60,
      future_skew_seconds=5,
    )
    policy = HeartbeatObservationPolicy(config=config, verifier=_Verifier())

    stale = policy.authorize_heartbeat(
      json.dumps(_signed_envelope(timestamp="2026-08-17 09:58:00.000000")),
      now=self.now,
    )
    future = policy.authorize_heartbeat(
      json.dumps(_signed_envelope(timestamp="2026-08-17 10:00:40.000000")),
      now=self.now,
    )

    self.assertFalse(stale.accepted)
    self.assertEqual(stale.reason, "stale_timestamp")
    self.assertFalse(future.accepted)
    self.assertEqual(future.reason, "future_timestamp")

  def test_selected_heartbeat_rejects_verifier_sender_mismatch(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
    )
    policy = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(sender=NODE_B),
    )

    result = policy.authorize_heartbeat(
      json.dumps(_signed_envelope(sender=NODE_A)),
      now=self.now,
    )

    self.assertFalse(result.accepted)
    self.assertEqual(result.reason, "verified_sender_mismatch")

  def test_selected_v2_heartbeat_rejects_inner_identity_and_time(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SELECTED_NODES,
      nodes=[NODE_A],
      max_age_seconds=60,
    )
    policy = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(),
      decompress_text=_decompress_text,
    )
    identity_mismatch = _signed_envelope()
    identity_mismatch.update({
      "HEARTBEAT_VERSION": "v2",
      "ENCODED_DATA": json.dumps({
        "EE_ADDR": NODE_B,
        "CURRENT_TIME": "2026-08-17 10:00:00.000000",
      }),
    })
    stale_inner = _signed_envelope()
    stale_inner.update({
      "HEARTBEAT_VERSION": "v2",
      "ENCODED_DATA": json.dumps({
        "EE_ADDR": NODE_A,
        "CURRENT_TIME": "2026-08-17 09:58:00.000000",
      }),
    })

    mismatch_result = policy.authorize_heartbeat(
      json.dumps(identity_mismatch),
      now=self.now,
    )
    stale_result = policy.authorize_heartbeat(
      json.dumps(stale_inner),
      now=self.now,
    )

    self.assertFalse(mismatch_result.accepted)
    self.assertEqual(mismatch_result.reason, "inner_sender_mismatch")
    self.assertFalse(stale_result.accepted)
    self.assertEqual(stale_result.reason, "stale_inner_timestamp")

  def test_summary_requires_trusted_signer_and_exact_netmon_path(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SUMMARY_DISCOVERY,
      summary_publishers=[ORACLE],
      max_age_seconds=60,
    )
    policy = HeartbeatObservationPolicy(config=config, verifier=_Verifier())

    trusted = policy.authorize_summary(
      json.dumps(_signed_envelope(sender=ORACLE)),
      now=self.now,
    )
    untrusted = policy.authorize_summary(
      json.dumps(_signed_envelope(sender=NODE_A)),
      now=self.now,
    )
    wrong_path_envelope = _signed_envelope(sender=ORACLE)
    wrong_path_envelope["EE_PAYLOAD_PATH"] = [
      "oracle", "other_pipeline", "NET_MON_01", "instance",
    ]
    wrong_path = policy.authorize_summary(
      json.dumps(wrong_path_envelope),
      now=self.now,
    )

    self.assertTrue(trusted.accepted)
    self.assertFalse(untrusted.accepted)
    self.assertEqual(untrusted.reason, "untrusted_summary_publisher")
    self.assertFalse(wrong_path.accepted)
    self.assertEqual(wrong_path.reason, "not_netmon_summary")

  def test_summary_requires_valid_raw_json_and_nonempty_decoded_network(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SUMMARY_DISCOVERY,
      summary_publishers=[ORACLE],
    )
    policy = HeartbeatObservationPolicy(config=config, verifier=_Verifier())
    empty = _signed_envelope(sender=ORACLE)
    empty["CURRENT_NETWORK"] = {}

    authorized = policy.authorize_summary(json.dumps(empty), now=self.now)
    empty_result = policy.validate_summary_content(empty)
    malformed_result = policy.authorize_summary("{not-json", now=self.now)

    self.assertTrue(authorized.accepted)
    self.assertFalse(empty_result.accepted)
    self.assertEqual(empty_result.reason, "empty_network_summary")
    self.assertFalse(malformed_result.accepted)
    self.assertEqual(malformed_result.reason, "invalid_json")

  def test_summary_rejects_bad_signature_sender_mismatch_and_bad_time(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_SUMMARY_DISCOVERY,
      summary_publishers=[ORACLE],
      max_age_seconds=60,
      future_skew_seconds=5,
    )
    envelope = _signed_envelope(sender=ORACLE)

    bad_signature = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(valid=False),
    ).authorize_summary(json.dumps(envelope), now=self.now)
    sender_mismatch = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(sender=NODE_A),
    ).authorize_summary(json.dumps(envelope), now=self.now)
    stale = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(),
    ).authorize_summary(
      json.dumps(_signed_envelope(
        sender=ORACLE,
        timestamp="2026-08-17 09:58:00.000000",
      )),
      now=self.now,
    )
    future = HeartbeatObservationPolicy(
      config=config,
      verifier=_Verifier(),
    ).authorize_summary(
      json.dumps(_signed_envelope(
        sender=ORACLE,
        timestamp="2026-08-17 10:00:40.000000",
      )),
      now=self.now,
    )

    self.assertEqual(bad_signature.reason, "invalid_signature")
    self.assertEqual(sender_mismatch.reason, "verified_sender_mismatch")
    self.assertEqual(stale.reason, "stale_timestamp")
    self.assertEqual(future.reason, "future_timestamp")

  def test_full_network_policy_preserves_legacy_acceptance(self):
    config = HeartbeatObservationConfig.from_values(
      mode=HEARTBEAT_MODE_FULL_NETWORK,
    )
    verifier = _Verifier(valid=False)
    policy = HeartbeatObservationPolicy(config=config, verifier=verifier)

    result = policy.authorize_heartbeat(
      json.dumps(_signed_envelope(sender=NODE_B)),
      now=self.now,
    )

    self.assertTrue(result.accepted)
    self.assertEqual(result.reason, "legacy_full_network")
    self.assertEqual(verifier.calls, [])


class TestHeartbeatObservationMonitor(unittest.TestCase):

  def test_selected_subscription_wait_has_a_deadline_and_can_recover(self):
    clock = _Clock(0.0)
    config = HeartbeatObservationConfig.from_values(
      mode='selected_nodes', nodes=[NODE_A], observation_timeout_seconds=5,
    )
    monitor = HeartbeatObservationMonitor(config=config, clock=clock)
    clock.value = 4.9
    self.assertEqual(monitor.snapshot()['state'], 'waiting_for_suback')
    clock.value = 5.0
    self.assertEqual(monitor.snapshot()['state'], 'degraded')
    self.assertEqual(monitor.snapshot()['reason'], 'targeted_subscription_timeout')
    monitor.set_subscription_status(True, [f'ratio1/ctrl/{NODE_A}'])
    monitor.record_valid_observation(NODE_A)
    self.assertEqual(monitor.snapshot()['state'], 'ready')

  def test_selected_startup_returns_after_deadline_without_subscription_attempt(self):
    from ratio1.base.generic_session import GenericSession

    clock = _Clock(0.0)
    config = HeartbeatObservationConfig.from_values(
      mode='selected_nodes', nodes=[NODE_A], observation_timeout_seconds=1,
    )
    monitor = HeartbeatObservationMonitor(config=config, clock=clock)
    session = GenericSession.__new__(GenericSession)
    session._GenericSession__closing = False
    session._heartbeat_observation_config = config
    session._heartbeat_observation_monitor = monitor
    session.Pd = mock.Mock()
    session.P = mock.Mock()
    clock.value = 1000
    with mock.patch('ratio1.base.generic_session.Thread'), mock.patch(
      'ratio1.base.generic_session.sleep',
      side_effect=AssertionError('startup slept beyond observation deadline'),
    ):
      session._GenericSession__start_main_loop_thread()
    self.assertEqual(monitor.snapshot()['state'], 'degraded')

  def test_selected_mode_becomes_degraded_without_targeted_heartbeat(self):
    clock = _Clock(10.0)
    config = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE_A],
      observation_timeout_seconds=5,
    )
    monitor = HeartbeatObservationMonitor(config=config, clock=clock)

    self.assertEqual(monitor.snapshot()["state"], "waiting_for_suback")
    monitor.set_subscription_status(ready=True, topics=[f"ratio1/ctrl/{NODE_A}"])
    self.assertEqual(monitor.snapshot()["state"], "waiting_for_targeted_heartbeat")
    clock.value = 16.0
    self.assertEqual(monitor.snapshot()["state"], "degraded")
    self.assertEqual(monitor.snapshot()["reason"], "targeted_heartbeat_timeout")

  def test_valid_selected_observation_recovers_degraded_state(self):
    clock = _Clock(10.0)
    config = HeartbeatObservationConfig.from_values(
      mode="selected_nodes",
      nodes=[NODE_A],
      observation_timeout_seconds=5,
    )
    monitor = HeartbeatObservationMonitor(config=config, clock=clock)
    monitor.set_subscription_status(ready=True, topics=[f"ratio1/ctrl/{NODE_A}"])
    clock.value = 16.0
    self.assertEqual(monitor.snapshot()["state"], "degraded")

    monitor.record_valid_observation(NODE_A)

    self.assertEqual(monitor.snapshot()["state"], "ready")
    self.assertEqual(monitor.snapshot()["last_valid_sender"], NODE_A)
    self.assertEqual(monitor.snapshot()["accepted_heartbeats"], 1)
    self.assertEqual(monitor.snapshot()["accepted_summaries"], 0)
    self.assertEqual(monitor.snapshot()["last_valid_age_seconds"], 0.0)

  def test_summary_mode_never_claims_a_ctrl_subscription(self):
    clock = _Clock(0.0)
    config = HeartbeatObservationConfig.from_values(
      mode="summary_discovery",
      summary_publishers=[ORACLE],
      observation_timeout_seconds=5,
    )
    monitor = HeartbeatObservationMonitor(config=config, clock=clock)

    self.assertEqual(monitor.snapshot()["state"], "waiting_for_trusted_summary")
    self.assertEqual(monitor.snapshot()["heartbeat_topics"], [])
    clock.value = 6.0
    self.assertEqual(monitor.snapshot()["state"], "degraded")
    self.assertEqual(monitor.snapshot()["reason"], "trusted_summary_timeout")

    monitor.record_valid_observation(ORACLE, source="summary")

    self.assertEqual(monitor.snapshot()["state"], "ready")
    self.assertEqual(monitor.snapshot()["accepted_summaries"], 1)


if __name__ == "__main__":
  unittest.main()
