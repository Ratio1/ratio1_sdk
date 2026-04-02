import copy
import unittest
from collections import defaultdict

from ratio1.base.generic_session import GenericSession
from ratio1.const import DEFAULT_PIPELINES, HB, PAYLOAD_DATA, PLUGIN_SIGNATURES


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


if __name__ == "__main__":
  unittest.main()
