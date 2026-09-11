import copy
import json
import threading
import unittest
from collections import defaultdict
from datetime import datetime, timezone
from unittest import mock

from ratio1.base.generic_session import GenericSession
from ratio1.comm.heartbeat_observation import (
  HeartbeatObservationConfig,
  HeartbeatObservationMonitor,
  HeartbeatObservationPolicy,
)
from ratio1.const import DEFAULT_PIPELINES, HB, PAYLOAD_DATA, PLUGIN_SIGNATURES
from ratio1.io_formatter.default.aixp1 import Aixp1Formatter


ORACLE = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMh"
NODE_ADDRESS_FOR_MISMATCH = "0xai_A_b3ELqPfiAjV7iBSiOyUEO7gWOQG9WUsUuojPWbiMiF"


class _VerifyResult:
  def __init__(self, valid=True, sender=ORACLE):
    self.valid = valid
    self.sender = sender
    self.message = "test result"


class _Verifier:
  def __init__(self, valid=True, sender=ORACLE):
    self.valid = valid
    self.sender = sender

  def verify(self, payload, **kwargs):
    return _VerifyResult(valid=self.valid, sender=self.sender)


class _IdentityFormatter:
  def decode_output(self, payload):
    return payload


class _FormatterWrapper:
  def get_required_formatter_from_payload(self, payload):
    return _IdentityFormatter()


class _FakeLog:
  def compress_text(self, text):
    import base64
    import zlib

    return base64.b64encode(zlib.compress(text.encode("utf-8"), level=9)).decode("utf-8")

  def decompress_text(self, text):
    import base64
    import zlib

    try:
      return zlib.decompress(base64.b64decode(text)).decode("utf-8")
    except Exception:
      return None

  def second_of_minute(self):
    return 7


def build_v1_netmon_payload():
  return {
    PAYLOAD_DATA.EE_ID: "oracle-1",
    PAYLOAD_DATA.EE_SENDER: "0xoracle",
    PAYLOAD_DATA.EE_PAYLOAD_PATH: ["0xoracle", "admin_pipeline", "NET_MON_01", "NETMON_01_INST"],
    PAYLOAD_DATA.STREAM_NAME: "admin_pipeline",
    PAYLOAD_DATA.SIGNATURE: "NET_MON_01",
    PAYLOAD_DATA.INSTANCE_ID: "NETMON_01_INST",
    PAYLOAD_DATA.SESSION_ID: "sess-1",
    PAYLOAD_DATA.INITIATOR_ID: "sdk-user",
    PAYLOAD_DATA.INITIATOR_ADDR: "0xself",
    PAYLOAD_DATA.MODIFIED_BY_ID: "sdk-user",
    PAYLOAD_DATA.MODIFIED_BY_ADDR: "0xself",
    "USE_LOCAL_COMMS_ONLY": False,
    PAYLOAD_DATA.NETMON_CURRENT_NETWORK: {
      "node-1": {
        PAYLOAD_DATA.NETMON_ADDRESS: "0xpeer",
        PAYLOAD_DATA.NETMON_EEID: "peer-1",
        PAYLOAD_DATA.NETMON_STATUS_KEY: PAYLOAD_DATA.NETMON_STATUS_ONLINE,
        PAYLOAD_DATA.NETMON_WHITELIST: [0],
      }
    },
    PAYLOAD_DATA.NETMON_WHITELIST_MAP: {
      "0xself": 0,
    },
    "CURRENT_ALERTED": {},
    "CURRENT_RANKING": [],
    "CURRENT_NEW": [],
    "STATUS": "ok",
    "MESSAGE": "ok",
    "SEND_CURRENT_NETWORK_EACH": 0,
    "IS_SUPERVISOR": True,
  }


def build_v2_netmon_payload(log=None):
  log = log or _FakeLog()
  return PAYLOAD_DATA.maybe_encode_netmon_payload(copy.deepcopy(build_v1_netmon_payload()), log=log)


class TestNetmonPayloadHelpers(unittest.TestCase):

  def setUp(self):
    self.log = _FakeLog()

  def test_encode_keeps_transport_fields_top_level(self):
    payload = build_v1_netmon_payload()

    encoded = PAYLOAD_DATA.maybe_encode_netmon_payload(copy.deepcopy(payload), log=self.log)

    self.assertEqual(encoded[PAYLOAD_DATA.NETMON_VERSION], PAYLOAD_DATA.NETMON_VERSION_V2)
    self.assertIn(HB.ENCODED_DATA, encoded)
    self.assertNotIn(PAYLOAD_DATA.NETMON_CURRENT_NETWORK, encoded)
    self.assertEqual(encoded[PAYLOAD_DATA.STREAM_NAME], payload[PAYLOAD_DATA.STREAM_NAME])
    self.assertEqual(encoded[PAYLOAD_DATA.SIGNATURE], payload[PAYLOAD_DATA.SIGNATURE])
    self.assertEqual(encoded[PAYLOAD_DATA.INSTANCE_ID], payload[PAYLOAD_DATA.INSTANCE_ID])
    self.assertEqual(encoded[PAYLOAD_DATA.SESSION_ID], payload[PAYLOAD_DATA.SESSION_ID])
    self.assertEqual(encoded[PAYLOAD_DATA.INITIATOR_ADDR], payload[PAYLOAD_DATA.INITIATOR_ADDR])

  def test_decode_restores_business_body(self):
    encoded = build_v2_netmon_payload(self.log)

    decoded = PAYLOAD_DATA.maybe_decode_netmon_payload(encoded, log=self.log)

    self.assertIsInstance(decoded[PAYLOAD_DATA.NETMON_CURRENT_NETWORK], dict)
    self.assertEqual(decoded["MESSAGE"], "ok")
    self.assertEqual(decoded["STATUS"], "ok")

  def test_decode_is_idempotent(self):
    encoded = build_v2_netmon_payload(self.log)

    decoded_once = PAYLOAD_DATA.maybe_decode_netmon_payload(encoded, log=self.log)
    decoded_twice = PAYLOAD_DATA.maybe_decode_netmon_payload(decoded_once, log=self.log)

    self.assertEqual(decoded_once, decoded_twice)
    self.assertIsInstance(decoded_twice[PAYLOAD_DATA.NETMON_CURRENT_NETWORK], dict)

  def test_decode_leaves_malformed_payload_unchanged(self):
    malformed = {
      PAYLOAD_DATA.EE_ID: "oracle-1",
      PAYLOAD_DATA.NETMON_VERSION: PAYLOAD_DATA.NETMON_VERSION_V2,
      HB.ENCODED_DATA: "not-valid-base64",
    }

    decoded = PAYLOAD_DATA.maybe_decode_netmon_payload(copy.deepcopy(malformed), log=self.log)

    self.assertEqual(decoded, malformed)
    self.assertNotIn(PAYLOAD_DATA.NETMON_CURRENT_NETWORK, decoded)


class TestGenericSessionNetmonDecode(unittest.TestCase):

  def _make_session(self):
    session = GenericSession.__new__(GenericSession)
    session._eth_enabled = True
    session.log = _FakeLog()
    session._netmon_second_bins = defaultdict(int)
    session._netmon_elapsed_by_oracle = defaultdict(list)
    session._dct_netconfig_pipelines_requests = {}
    session._dct_can_send_to_node = {}
    session._GenericSession__at_least_a_netmon_received = False
    session._GenericSession__at_least_one_node_peered = False
    session._GenericSession__current_network_statuses = {}
    session._shorten_addr = lambda addr: addr
    session.D = lambda *args, **kwargs: None
    session.Pd = lambda *args, **kwargs: None
    session.P = lambda *args, **kwargs: None
    session._GenericSession__track_allowed_node_by_netmon = lambda node_addr, node_data: False
    session._GenericSession__request_pipelines_from_net_config_monitor = lambda: None
    return session

  def _make_summary_session(self, verifier=None):
    session = self._make_session()
    session._eth_enabled = False
    session.filter_workers = None
    session.own_pipelines = []
    session._GenericSession__open_transactions = []
    session._GenericSession__open_transactions_lock = threading.Lock()
    session.custom_on_payload = mock.Mock()
    session._GenericSession__maybe_process_net_config = mock.Mock()
    session.formatter_wrapper = _FormatterWrapper()
    session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
      mode="summary_discovery",
      summary_publishers=[ORACLE],
      max_age_seconds=60,
      future_skew_seconds=5,
    )
    session._heartbeat_observation_policy = HeartbeatObservationPolicy(
      config=session._heartbeat_observation_config,
      verifier=verifier or _Verifier(),
      decompress_text=session.log.decompress_text,
    )
    session._heartbeat_observation_monitor = HeartbeatObservationMonitor(
      config=session._heartbeat_observation_config,
    )
    return session

  def _wire_summary(self, **overrides):
    payload = build_v1_netmon_payload()
    payload.update({
      PAYLOAD_DATA.EE_SENDER: ORACLE,
      PAYLOAD_DATA.EE_SIGN: "signature",
      PAYLOAD_DATA.EE_HASH: "hash",
      PAYLOAD_DATA.EE_TIMESTAMP: datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S.%f",
      ),
      PAYLOAD_DATA.EE_TIMEZONE: "UTC+0",
      "EE_TZ": "Etc/UTC",
    })
    payload[PAYLOAD_DATA.EE_PAYLOAD_PATH][0] = "oracle"
    payload.update(overrides)
    return payload

  def test_netmon_processing_normalizes_v2_before_use(self):
    session = self._make_session()
    payload = build_v2_netmon_payload(session.log)

    session._GenericSession__maybe_process_net_mon(
      dict_msg=payload,
      msg_pipeline=DEFAULT_PIPELINES.ADMIN_PIPELINE,
      msg_signature=PLUGIN_SIGNATURES.NET_MON_01,
      sender_addr=payload[PAYLOAD_DATA.EE_SENDER],
    )

    self.assertTrue(session._GenericSession__at_least_a_netmon_received)
    self.assertIsInstance(payload[PAYLOAD_DATA.NETMON_CURRENT_NETWORK], dict)
    node_data = payload[PAYLOAD_DATA.NETMON_CURRENT_NETWORK]["node-1"]
    self.assertEqual(node_data[PAYLOAD_DATA.NETMON_WHITELIST], ["0xself"])
    self.assertIn(payload[PAYLOAD_DATA.EE_SENDER], session._GenericSession__current_network_statuses)

  def test_trusted_summary_updates_discovery_before_user_filter(self):
    session = self._make_session()
    session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
      mode="summary_discovery",
      summary_publishers=[ORACLE],
    )
    session.filter_workers = ["0xselected"]
    session.own_pipelines = []
    session.custom_on_payload = mock.Mock()
    session._GenericSession__maybe_process_net_mon = mock.Mock()
    session._GenericSession__maybe_process_net_config = mock.Mock()
    payload = build_v1_netmon_payload()
    payload[PAYLOAD_DATA.EE_SENDER] = ORACLE

    session._GenericSession__on_payload(
      payload,
      payload[PAYLOAD_DATA.EE_SENDER],
      DEFAULT_PIPELINES.ADMIN_PIPELINE,
      PLUGIN_SIGNATURES.NET_MON_01,
      "NETMON_01_INST",
      trusted_summary=True,
    )

    session._GenericSession__maybe_process_net_mon.assert_called_once()
    session._GenericSession__maybe_process_net_config.assert_not_called()
    session.custom_on_payload.assert_not_called()

  def test_raw_trusted_summary_auth_is_required_before_state_mutation(self):
    session = self._make_summary_session()
    payload = self._wire_summary()

    session._GenericSession__on_message_default_callback(
      json.dumps(payload),
      session._GenericSession__on_payload,
      source="payload",
    )

    self.assertIn(ORACLE, session._GenericSession__current_network_statuses)
    status = session._heartbeat_observation_monitor.snapshot()
    self.assertEqual(status["accepted_summaries"], 1)
    self.assertEqual(status["last_valid_sender"], ORACLE)

  def test_rejected_or_empty_summary_cannot_mutate_discovery_state(self):
    cases = [
      (
        "bad_signature",
        _Verifier(valid=False),
        self._wire_summary(),
      ),
      (
        "sender_mismatch",
        _Verifier(sender=NODE_ADDRESS_FOR_MISMATCH),
        self._wire_summary(),
      ),
      (
        "stale",
        _Verifier(),
        self._wire_summary(**{
          PAYLOAD_DATA.EE_TIMESTAMP: "2000-01-01 00:00:00.000000",
        }),
      ),
      (
        "empty_network",
        _Verifier(),
        self._wire_summary(**{
          PAYLOAD_DATA.NETMON_CURRENT_NETWORK: {},
        }),
      ),
    ]
    for name, verifier, payload in cases:
      with self.subTest(name=name):
        session = self._make_summary_session(verifier=verifier)

        session._GenericSession__on_message_default_callback(
          json.dumps(payload),
          session._GenericSession__on_payload,
          source="payload",
        )

        self.assertEqual(session._GenericSession__current_network_statuses, {})
        self.assertEqual(
          session._heartbeat_observation_monitor.snapshot()["accepted_summaries"],
          0,
        )

  def _use_aixp1_formatter(self, session):
    """Use the production decoder with an isolated timing logger.

    Parameters
    ----------
    session : GenericSession
      Test session whose formatter lookup is replaced.
    """
    formatter = Aixp1Formatter(log=mock.Mock(), signature="aixp1")
    session.formatter_wrapper = mock.Mock()
    session.formatter_wrapper.get_required_formatter_from_payload.return_value = formatter

  def test_formatter_route_changes_cannot_admit_unverified_summaries(self):
    """Every Aixp1 routing overwrite must retain the raw trust decision.

    Notes
    -----
    No worker filter is installed: rejection must come from authorization,
    not from filtering out the publisher before discovery processing.
    """
    for location in ("DATA", "PLUGIN_META", "PIPELINE_META"):
      with self.subTest(location=location):
        verifier = mock.Mock(wraps=_Verifier(valid=False))
        session = self._make_summary_session(verifier=verifier)
        self._use_aixp1_formatter(session)
        payload = self._wire_summary()
        summary_path = payload[PAYLOAD_DATA.EE_PAYLOAD_PATH]
        summary_path[1:3] = ["ADMIN_PIPELINE", "net_mon_01"]
        body = {
          PAYLOAD_DATA.NETMON_CURRENT_NETWORK:
            payload.pop(PAYLOAD_DATA.NETMON_CURRENT_NETWORK),
        }
        route = {PAYLOAD_DATA.EE_PAYLOAD_PATH: summary_path}
        if location == "DATA":
          body.update(route)
        else:
          body[location] = route
        payload.update({
          "EE_EVENT_TYPE": "PAYLOAD",
          "EE_FORMATTER": "aixp1",
          PAYLOAD_DATA.EE_PAYLOAD_PATH: ["oracle", "ordinary", "CUSTOM", "instance"],
          "DATA": body,
        })

        session._GenericSession__on_message_default_callback(
          json.dumps(payload), session._GenericSession__on_payload, source="payload",
        )

        verifier.verify.assert_not_called()
        self.assertEqual(session._GenericSession__current_network_statuses, {})
        self.assertFalse(session._GenericSession__at_least_a_netmon_received)
        self.assertEqual(
          session._heartbeat_observation_monitor.snapshot()["accepted_summaries"], 0,
        )
        session._GenericSession__maybe_process_net_config.assert_not_called()
        session.custom_on_payload.assert_not_called()

  def test_trusted_formatted_summary_still_updates_discovery_and_callbacks(self):
    """A trusted raw NetMon route remains valid through Aixp1 decoding."""
    verifier = mock.Mock(wraps=_Verifier())
    session = self._make_summary_session(verifier=verifier)
    self._use_aixp1_formatter(session)
    payload = self._wire_summary()
    payload.update({
      "EE_EVENT_TYPE": "PAYLOAD",
      "EE_FORMATTER": "aixp1",
      "DATA": {
        PAYLOAD_DATA.NETMON_CURRENT_NETWORK:
          payload.pop(PAYLOAD_DATA.NETMON_CURRENT_NETWORK),
      },
    })

    session._GenericSession__on_message_default_callback(
      json.dumps(payload), session._GenericSession__on_payload, source="payload",
    )

    verifier.verify.assert_called_once()
    self.assertIn(ORACLE, session._GenericSession__current_network_statuses)
    self.assertEqual(
      session._heartbeat_observation_monitor.snapshot()["accepted_summaries"], 1,
    )
    session.custom_on_payload.assert_called_once()

  def test_ordinary_payload_callbacks_are_preserved_in_every_mode(self):
    """Reduced-mode summary checks do not discard ordinary application data."""
    for mode in ("summary_discovery", "selected_nodes", "full_network"):
      with self.subTest(mode=mode):
        session = self._make_summary_session()
        session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
          mode=mode, summary_publishers=[ORACLE], nodes=[ORACLE],
        )
        payload = self._wire_summary(**{
          PAYLOAD_DATA.EE_PAYLOAD_PATH: ["oracle", "ordinary", "CUSTOM", "instance"],
        })
        session._GenericSession__on_message_default_callback(
          json.dumps(payload), session._GenericSession__on_payload, source="payload",
        )

        self.assertEqual(session._GenericSession__current_network_statuses, {})
        session._GenericSession__maybe_process_net_config.assert_called_once()
        session.custom_on_payload.assert_called_once()

  def test_non_summary_modes_preserve_legacy_netmon_processing(self):
    """The new summary-mode boundary does not change other modes' NetMon path."""
    for mode in ("full_network", "selected_nodes"):
      with self.subTest(mode=mode):
        session = self._make_summary_session()
        session._heartbeat_observation_config = HeartbeatObservationConfig.from_values(
          mode=mode, nodes=[ORACLE],
        )
        session._GenericSession__on_message_default_callback(
          json.dumps(self._wire_summary()),
          session._GenericSession__on_payload,
          source="payload",
        )

        self.assertIn(ORACLE, session._GenericSession__current_network_statuses)
        session.custom_on_payload.assert_called_once()


if __name__ == "__main__":
  unittest.main()
