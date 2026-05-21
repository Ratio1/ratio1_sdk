import hashlib
import unittest

from ratio1.bc.base import BaseBlockEngine


class TestCompactCanonicalJson(unittest.TestCase):

  def test_deeploy_v3_fixture_matches_typescript_hash(self):
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
    }

    compact_json = BaseBlockEngine.compact_canonical_json(None, payload)

    self.assertEqual(
      compact_json,
      '{"app_alias":"münchen_api","nonce":"0xabc","pipeline_params":{"labels":{"city":"Iași"}},"plugins":[{"DYNAMIC_ENV":{"API_URL":[{"type":"static","value":"https://"},{"path":["web","HOST_PORT"],"type":"shmem"}]},"ENV":{"GREETING":"bună ziua"},"plugin_name":"api","plugin_signature":"WORKER_APP_RUNNER"},{"plugin_name":"probe","plugin_signature":"EDGE_NODE_API_TEST"}],"target_nodes":["0xai_node_a","0xai_node_b"],"target_nodes_count":0}',
    )
    self.assertEqual(
      hashlib.sha256(compact_json.encode("utf-8")).hexdigest(),
      "12169fe2f1a33373ba651d14318eb18d3239c0148a0d601de9f4ce3be9d2dded",
    )


if __name__ == "__main__":
  unittest.main()
