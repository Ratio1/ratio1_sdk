"""Offline coverage for node capacity and Deeploy allocation columns."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from ratio1.base.generic_session import GenericSession
from ratio1.cli.cli import build_parser
from ratio1.cli.nodes import get_nodes
from ratio1.const import PAYLOAD_DATA


def pipeline(resources, deployed=True, name="job"):
  """Build the resource-bearing part of a cached SDK pipeline.

  Parameters
  ----------
  resources : list
      Resource dictionaries for the pipeline's instances.
  deployed : bool, optional
      Whether Deeploy owns the pipeline.
  name : str, optional
      Pipeline identifier.

  Returns
  -------
  types.SimpleNamespace
      Minimal cached pipeline containing real config key names.
  """
  return SimpleNamespace(
    name=name, config={"IS_DEEPLOYED": deployed},
    lst_plugin_instances=[SimpleNamespace(config={"CONTAINER_RESOURCES": item}) for item in resources],
  )


class TestGetNodesResources(unittest.TestCase):
  """Exercise real report assembly and CLI rendering with cached data.

  Notes
  -----
  Transport and blockchain calls are replaced to keep verification offline.
  """

  def make_session(self, configs=None):
    """Create a session with one peered and one unpeered network node.

    Parameters
    ----------
    configs : dict, optional
        Cached pipeline maps by internal node address.

    Returns
    -------
    GenericSession
        Offline fixture using production report assembly.
    """
    session = GenericSession.__new__(GenericSession)
    session._dct_online_nodes_pipelines = configs or {}
    session.bc_engine = SimpleNamespace(
      address="client", evm_network="testnet",
      contains_current_address=lambda whitelist: "client" in whitelist,
      _remove_prefix=lambda addr: addr,
      _add_prefix=lambda addr: addr,
      node_address_to_eth_address=lambda addr: "eth-" + addr,
      web3_get_addresses_balances=lambda addresses: {
        addr: {"ethBalance": 0.1234, "r1Balance": 2.3456} for addr in addresses
      },
    )
    session._shorten_addr = lambda value: value
    session.P = lambda *args, **kwargs: None
    session._GenericSession__wait_for_supervisors_net_mon_data = Mock(return_value=(True, 0))
    session._GenericSession__request_pipelines_from_net_config_monitor = Mock()
    session._GenericSession__current_network_statuses = {
      "node-a": {
        addr: {
          PAYLOAD_DATA.NETMON_ADDRESS: addr,
          PAYLOAD_DATA.NETMON_EEID: alias,
          PAYLOAD_DATA.NETMON_STATUS_KEY: PAYLOAD_DATA.NETMON_STATUS_ONLINE,
          PAYLOAD_DATA.NETMON_WHITELIST: whitelist,
          PAYLOAD_DATA.NETMON_NODE_VERSION: "3.5.53",
          PAYLOAD_DATA.NETMON_LAST_SEEN: 1,
          "total_mem": 31.25, "total_disk": 499.96,
        }
        for addr, alias, whitelist in [
          ("node-a", "alpha", ["client"]), ("node-b", "beta", []),
        ]
      },
    }
    return session

  def test_report_totals_sum_all_deeploy_instances(self):
    """Exclude admin and non-Deeploy jobs without losing multiple instances.

    Notes
    -----
    Allocation sizes are binary units and independent of hardware totals.
    """
    session = self.make_session({"node-a": {
      "job": pipeline([{"memory": "512m", "storage": "2g"}, {"memory": "1.5g", "storage": "512m"}]),
      "job2": pipeline([{"memory": 1073741824, "storage": "1GiB"}]),
      "manual": pipeline([{"memory": "100g", "storage": "100g"}], deployed=False),
      "admin_pipeline": pipeline([{"memory": "100g", "storage": "100g"}], name="admin_pipeline"),
    }})

    result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)

    self.assertEqual(result.loc[0, ["TMem", "PMem", "TDisk", "PDisk"]].tolist(), [31.25, 3.0, 499.96, 3.5])
    self.assertTrue(result.loc[1, ["PMem", "PDisk"]].isna().all())

  def test_unknown_allocations_are_distinct_from_empty_nodes(self):
    """Keep an unknown dimension unknown even when other jobs report values.

    Notes
    -----
    A cached empty pipeline map is evidence of zero allocation.
    """
    session = self.make_session({"node-a": {}, "node-b": {
      "job": pipeline([{"memory": "1g", "storage": "1g"}, {"memory": None, "storage": "2g"}]),
    }})
    result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)
    self.assertEqual(result.loc[0, ["PMem", "PDisk"]].tolist(), [0, 0])
    self.assertTrue(pd.isna(result.loc[1, "PMem"]))
    self.assertEqual(result.loc[1, "PDisk"], 3)

  def test_malformed_resource_values_do_not_crash_report(self):
    """Reject invalid capacities and allocations as unavailable values.

    Notes
    -----
    NaN, infinity, negative values, and malformed config blocks are not zero.
    """
    for resources in (None, [], {"memory": "bad", "storage": -1}, {"memory": float("nan"), "storage": float("inf")}):
      with self.subTest(resources=resources):
        session = self.make_session({"node-a": {"job": pipeline([resources])}})
        info = session._GenericSession__current_network_statuses["node-a"]["node-a"]
        info.update(total_mem=None, total_disk=-1)
        result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)
        self.assertTrue(result.loc[0, ["TMem", "PMem", "TDisk", "PDisk"]].isna().all())

  def test_config_collection_targets_filtered_peered_nodes(self):
    """Use internal node addresses for fetching even with ETH display enabled.

    Notes
    -----
    An immediate simulated config reply avoids timers and real transport.
    """
    session = self.make_session()
    request = session._GenericSession__request_pipelines_from_net_config_monitor
    request.side_effect = lambda *args, **kwargs: session._dct_online_nodes_pipelines.update({"node-a": {}})
    result = session.get_network_known_nodes(
      include_resources=True, alias_filter="alpha", eth=True, df_only=True,
    )
    request.assert_called_once_with(["node-a"], force=True)
    self.assertEqual(result["Address"].tolist(), ["eth-node-a"])
    self.assertEqual(result["PMem"].tolist(), [0.0])

  def test_config_collection_timeout_is_shared_across_nodes(self):
    """Bound config collection when a peered node does not respond.

    Notes
    -----
    A simulated clock verifies timeout handling without sleeping.
    """
    session = self.make_session()
    session._GenericSession__current_network_statuses["node-a"]["node-b"][PAYLOAD_DATA.NETMON_WHITELIST] = ["client"]
    with patch("ratio1.base.generic_session.tm", side_effect=[0, 0, 0, 11]), \
         patch("ratio1.base.generic_session.sleep"):
      result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=10)
    self.assertTrue(result["PMem"].isna().all())
    session._GenericSession__request_pipelines_from_net_config_monitor.assert_called_once_with(["node-a", "node-b"], force=True)

  def test_empty_or_filtered_reports_keep_resource_columns(self):
    """Keep a stable empty table without requesting excluded node configs.

    Notes
    -----
    Both no-supervisor and no-alias-match cases should remain displayable.
    """
    for no_report in (False, True):
      with self.subTest(no_report=no_report):
        session = self.make_session()
        if no_report:
          session._GenericSession__current_network_statuses = {}
        result = session.get_network_known_nodes(
          include_resources=True, alias_filter=None if no_report else "missing", df_only=True,
        )
        self.assertTrue(result.empty)
        self.assertTrue({"TMem", "PMem", "TDisk", "PDisk"}.issubset(result.columns))
        session._GenericSession__request_pipelines_from_net_config_monitor.assert_not_called()

  def test_reports_without_resources_do_not_fetch_configs(self):
    """Preserve report behavior for other SDK and supervisor callers.

    Notes
    -----
    Only get nodes opts into allocation collection.
    """
    session = self.make_session()
    result = session.get_network_known_nodes(df_only=True)
    self.assertNotIn("PMem", result)
    session._GenericSession__request_pipelines_from_net_config_monitor.assert_not_called()

  def test_cli_renders_resources_with_one_decimal_in_both_views(self):
    """Render GiB columns without changing balance precision or grouping.

    Notes
    -----
    Exercise the CLI's session forwarding, normal/wide/ETH layouts, and groups.
    """
    for flags in ([], ["--wide"], ["--eth"], ["--group-by", "TMem"], ["--group-by", "TMem", "--explicit"]):
      with self.subTest(flags=flags):
        session = self.make_session({"node-a": {}})
        args = build_parser().parse_args(["get", "nodes", *flags])
        with patch("ratio1.Session", return_value=session), \
             patch("ratio1.cli.nodes.log_with_color") as output, \
             pd.option_context("display.max_columns", None, "display.width", 2000):
          result = get_nodes(args)
        table = output.call_args.args[0]
        self.assertIn("TMem", table)
        self.assertIn("31.2", table)
        self.assertNotIn("31.2500", table)
        self.assertNotIn("31.25", table)
        if "--group-by" not in flags:
          self.assertEqual(result["PMem"].iloc[0], 0)
          self.assertIn("PMem", table)
          self.assertIn("PDisk", table)
          self.assertIn("500.0", table)
          if flags:
            self.assertIn("0.1234", table)


if __name__ == "__main__":
  unittest.main()
