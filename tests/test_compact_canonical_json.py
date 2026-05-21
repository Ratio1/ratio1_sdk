import unittest

from ratio1.bc.base import compact_canonical_json, compact_canonical_sha256
from ratio1.const.base import BCctbase


class TestCompactCanonicalJson(unittest.TestCase):

  def test_compact_canonical_json_sorts_keys_and_preserves_unicode(self):
    value = {
      "z": [2, None],
      "a": {
        "city": "Iași",
        "greeting": "bună ziua",
      },
    }

    self.assertEqual(
      compact_canonical_json(value),
      '{"a":{"city":"Iași","greeting":"bună ziua"},"z":[2,null]}',
    )

  def test_compact_canonical_sha256_matches_deeploy_dapp_fixture(self):
    payload = {
      "nonce": "0xabc",
      "app_alias": "münchen_api",
      "target_nodes": ["0xai_node_a", "0xai_node_b"],
      "target_nodes_count": 0,
      "plugins": [
        {
          "plugin_signature": "WORKER_APP_RUNNER",
          "plugin_name": "api",
          "ENV": {"GREETING": "bună ziua"},
          "DYNAMIC_ENV": {
            "API_URL": [
              {"type": "static", "value": "https://"},
              {"type": "shmem", "path": ["web", "HOST_PORT"]},
            ],
          },
        },
        {
          "plugin_signature": "EDGE_NODE_API_TEST",
          "plugin_name": "probe",
        },
      ],
      "pipeline_params": {
        "labels": {"city": "Iași"},
      },
      "address": "remove-me",
      "signature": "remove-me",
      BCctbase.SIGN: "remove-me",
      BCctbase.SENDER: "remove-me",
      BCctbase.HASH: "remove-me",
      BCctbase.SIGN_CANON_V: "remove-me",
      BCctbase.ETH_SIGN: "remove-me",
      BCctbase.ETH_SENDER: "remove-me",
    }

    self.assertEqual(
      compact_canonical_sha256(
        payload,
        excluded_keys={
          "address",
          "signature",
          BCctbase.SIGN,
          BCctbase.SENDER,
          BCctbase.HASH,
          BCctbase.SIGN_CANON_V,
          BCctbase.ETH_SIGN,
          BCctbase.ETH_SENDER,
        },
      ),
      "12169fe2f1a33373ba651d14318eb18d3239c0148a0d601de9f4ce3be9d2dded",
    )


if __name__ == "__main__":
  unittest.main()
