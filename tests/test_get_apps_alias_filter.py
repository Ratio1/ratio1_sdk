from argparse import Namespace
from time import time
import unittest
from unittest.mock import patch

from pandas import DataFrame

from ratio1.base.generic_session import GenericSession
from ratio1.cli.cli import build_parser
from ratio1.cli.nodes import get_apps
from ratio1.const import HB, PAYLOAD_DATA


class _FakeLog:
  def colored_dataframe(self, rows, color_condition=None):
    return DataFrame(rows)


class _FakeInstance:
  def __init__(self, signature="FAKE_PLUGIN", instance_id="inst-01"):
    self.signature = signature
    self.instance_id = instance_id

  def get_status(self):
    return {
      HB.ACTIVE_PLUGINS_INFO.INIT_TIMESTAMP: "2026-01-01 00:00:00",
      HB.ACTIVE_PLUGINS_INFO.EXEC_TIMESTAMP: "2026-01-01 00:01:00",
      HB.ACTIVE_PLUGINS_INFO.LAST_PAYLOAD_TIME: "2026-01-01 00:02:00",
      HB.ACTIVE_PLUGINS_INFO.FIRST_ERROR_TIME: None,
      HB.ACTIVE_PLUGINS_INFO.LAST_ERROR_TIME: None,
    }


class _FakePipeline:
  def __init__(self, owner="owner-01", owner_alias="owner-alias", signatures=None):
    self.config = {
      "INITIATOR_ADDR": owner,
      "INITIATOR_ID": owner_alias,
    }
    signatures = signatures or ["FAKE_PLUGIN"]
    self.lst_plugin_instances = [_FakeInstance(signature=signature) for signature in signatures]


class TestGetAppsAliasFilter(unittest.TestCase):

  def _make_session(self):
    session = GenericSession.__new__(GenericSession)
    session.log = _FakeLog()
    session._shorten_addr = lambda addr: addr
    session.get_active_nodes = lambda: ["node-smart", "node-other"]
    session._dct_online_nodes_last_heartbeat = {
      "node-smart": {},
      "node-other": {},
    }
    session._GenericSession__current_network_statuses = {
      "oracle-1": {
        "smart-key": {
          PAYLOAD_DATA.NETMON_ADDRESS: "node-smart",
          PAYLOAD_DATA.NETMON_IS_SUPERVISOR: True,
        },
        "other-key": {
          PAYLOAD_DATA.NETMON_ADDRESS: "node-other",
          PAYLOAD_DATA.NETMON_IS_SUPERVISOR: False,
        },
      },
    }
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

  def test_cli_parser_accepts_apps_supervisor_filters(self):
    parser = build_parser()

    args = parser.parse_args(["get", "apps", "--super"])
    alias_args = parser.parse_args(["get", "apps", "--supervisors"])

    self.assertTrue(args.super)
    self.assertTrue(alias_args.supervisors)

  def test_cli_parser_accepts_app_name_filter(self):
    parser = build_parser()

    args = parser.parse_args(["get", "apps", "--app", "XYZ"])

    self.assertEqual(args.app, "XYZ")

  def test_get_nodes_apps_filters_to_supervisors_before_requesting_configs(self):
    session = self._make_session()

    result = session.get_nodes_apps(supervisors_only=True, as_df=True)

    self.assertTrue(result.empty)
    self.assertEqual(session.requested_nodes, [(["node-smart"], True)])

  def test_active_supervisors_fall_back_to_netmon_status(self):
    session = GenericSession.__new__(GenericSession)
    session.online_timeout = 60
    session._dct_node_last_seen_time = {
      "node-super": time(),
      "node-worker": time(),
    }
    session._dct_online_nodes_last_heartbeat = {
      "node-super": {},
      "node-worker": {},
    }
    session._GenericSession__current_network_statuses = {
      "oracle-1": {
        "super-key": {
          PAYLOAD_DATA.NETMON_ADDRESS: "node-super",
          PAYLOAD_DATA.NETMON_IS_SUPERVISOR: True,
        },
        "worker-key": {
          PAYLOAD_DATA.NETMON_ADDRESS: "node-worker",
          PAYLOAD_DATA.NETMON_IS_SUPERVISOR: False,
        },
      },
    }

    result = session.get_active_supervisors()

    self.assertEqual(result, ["node-super"])

  def test_get_nodes_apps_filters_app_names(self):
    session = self._make_session()
    session.get_active_pipelines = lambda node: {
      "alpha-XYZ-worker": _FakePipeline(),
      "alpha-background": _FakePipeline(),
    }

    result = session.get_nodes_apps(node="node-smart", app_filter="XYZ", as_df=True)

    self.assertEqual(result["App"].tolist(), ["alpha-XYZ-worker"])

  def test_get_nodes_apps_filters_plugin_names(self):
    session = self._make_session()
    session.get_active_pipelines = lambda node: {
      "oracle-services": _FakePipeline(signatures=["ORACLE_API", "OTHER_PLUGIN"]),
      "background-services": _FakePipeline(signatures=["CONTAINER_APP_RUNNER"]),
    }

    result = session.get_nodes_apps(node="node-smart", app_filter="ORACLE_API", show_full=True, as_df=True)

    self.assertEqual(result["App"].tolist(), ["oracle-services"])
    self.assertEqual(result["Plugin"].tolist(), ["ORACLE_API"])

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
      app=None,
      super=False,
      supervisors=False,
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

  def test_get_apps_passes_supervisor_and_app_filters_to_session(self):
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
      alias=None,
      app="XYZ",
      super=True,
      supervisors=False,
      full=False,
      json=False,
      owner=None,
      timeout=None,
      wide=False,
    )

    with patch("ratio1.Session", return_value=fake_session):
      with patch("ratio1.cli.nodes.log_with_color"):
        get_apps(args)

    self.assertTrue(fake_session.calls[0]["supervisors_only"])
    self.assertEqual(fake_session.calls[0]["app_filter"], "XYZ")


if __name__ == "__main__":
  unittest.main()
