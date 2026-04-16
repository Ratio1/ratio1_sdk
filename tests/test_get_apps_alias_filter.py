from argparse import Namespace
import unittest
from unittest.mock import patch

from pandas import DataFrame

from ratio1.base.generic_session import GenericSession
from ratio1.cli.cli import build_parser
from ratio1.cli.nodes import get_apps


class _FakeLog:
  def colored_dataframe(self, rows, color_condition=None):
    return DataFrame(rows)


class TestGetAppsAliasFilter(unittest.TestCase):

  def _make_session(self):
    session = GenericSession.__new__(GenericSession)
    session.log = _FakeLog()
    session._shorten_addr = lambda addr: addr
    session.get_active_nodes = lambda: ["node-smart", "node-other"]
    session.get_node_alias = lambda node: {
      "node-smart": "smart-edge-01",
      "node-other": "batch-edge-01",
    }.get(node)
    session.is_peered = lambda node: True
    session.wait_for_node = lambda node, timeout=15: True
    session.wait_for_node_configs = lambda node, timeout=15: None
    session.get_active_pipelines = lambda node: {}
    session.requested_nodes = []
    session._GenericSession__request_pipelines_from_net_config_monitor = (
      lambda node_addr, force=False: session.requested_nodes.append((list(node_addr), force))
    )
    return session

  def test_get_nodes_apps_filters_aliases_before_requesting_configs(self):
    session = self._make_session()

    result = session.get_nodes_apps(alias_filter="smart", as_df=True)

    self.assertTrue(result.empty)
    self.assertEqual(session.requested_nodes, [(["node-smart"], True)])

  def test_cli_parser_accepts_apps_alias_filter(self):
    parser = build_parser()

    args = parser.parse_args(["get", "apps", "--alias", "smart"])

    self.assertEqual(args.alias, "smart")

  def test_get_apps_passes_alias_filter_to_session(self):
    class _FakeSession:
      def __init__(self):
        self.bc_engine = type("Engine", (), {"evm_network": "testnet"})()
        self.calls = []

      def get_nodes_apps(self, **kwargs):
        self.calls.append(kwargs)
        return DataFrame()

      def get_node_alias(self, node):
        return None

    fake_session = _FakeSession()
    args = Namespace(
      verbose=False,
      node=None,
      alias="smart",
      full=False,
      json=False,
      owner=None,
      timeout=None,
      wide=False,
    )

    with patch("ratio1.Session", return_value=fake_session):
      with patch("ratio1.cli.nodes.log_with_color"):
        get_apps(args)

    self.assertEqual(fake_session.calls[0]["alias_filter"], "smart")


if __name__ == "__main__":
  unittest.main()
