"""Offline coverage for node capacity and Deeploy allocation columns."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from ratio1.base.generic_session import GenericSession
from ratio1.cli.cli import build_parser
from ratio1.cli.nodes import get_nodes
from ratio1.const import PAYLOAD_DATA
from ratio1.utils.resources import pipeline_allocations_gib, resource_cpu_cores


RESOURCE_COLUMNS = ["TCPU", "PCPU", "TRAM", "PRAM", "TDISK", "PDISK"]


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
          "total_cpu_cores": 16, "total_mem": 31.25, "total_disk": 499.96,
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
    CPU is measured in cores; memory/disk sizes use binary units.
    """
    session = self.make_session({"node-a": {
      "job": pipeline([
        {"cpu": 0.125, "memory": "512m", "storage": "2g"},
        {"cpu": "0.125", "memory": "1.5g", "storage": "512m"},
      ]),
      "job2": pipeline([{"cpu": "2", "memory": 1073741824, "storage": "1GiB"}]),
      "manual": pipeline([{"cpu": 100, "memory": "100g", "storage": "100g"}], deployed=False),
      "admin_pipeline": pipeline([{"cpu": 100, "memory": "100g", "storage": "100g"}], name="admin_pipeline"),
    }})

    result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)

    start = result.columns.get_loc("TCPU")
    self.assertEqual(result.columns[start:start + 6].tolist(), RESOURCE_COLUMNS)
    self.assertEqual(result.loc[0, RESOURCE_COLUMNS].tolist(), [16.0, 2.25, 31.25, 3.0, 499.96, 3.5])
    self.assertTrue(result.loc[1, ["PCPU", "PRAM", "PDISK"]].isna().all())
    self.assertEqual(pipeline_allocations_gib(session._dct_online_nodes_pipelines["node-a"]), (3.0, 3.5))

  def test_unknown_allocations_are_distinct_from_empty_nodes(self):
    """Keep an unknown dimension unknown even when other jobs report values.

    Notes
    -----
    A cached empty pipeline map is evidence of zero allocation.
    """
    session = self.make_session({"node-a": {}, "node-b": {
      "job": pipeline([
        {"cpu": 1, "memory": "1g", "storage": "1g"},
        {"cpu": 0.5, "memory": None, "storage": "2g"},
      ]),
    }})
    result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)
    self.assertEqual(result.loc[0, ["PCPU", "PRAM", "PDISK"]].tolist(), [0, 0, 0])
    self.assertTrue(pd.isna(result.loc[1, "PRAM"]))
    self.assertEqual(result.loc[1, ["PCPU", "PDISK"]].tolist(), [1.5, 3])

  def test_missing_cpu_does_not_hide_memory_or_disk(self):
    """Keep CPU unknown when any Deeploy instance omits its core limit.

    Notes
    -----
    Available dimensions still sum across every instance.
    """
    session = self.make_session({"node-a": {"job": pipeline([
      {"cpu": 2, "memory": "1g", "storage": "2g"},
      {"memory": "1g", "storage": "2g"},
    ])}})
    result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)
    self.assertTrue(pd.isna(result.loc[0, "PCPU"]))
    self.assertEqual(result.loc[0, ["PRAM", "PDISK"]].tolist(), [2.0, 4.0])

  def test_cpu_counts_accept_numbers_and_reject_invalid_values(self):
    """Parse core counts without treating booleans or resource sizes as cores.

    Notes
    -----
    The same parser handles hardware totals, allocations and app display.
    """
    for value, expected in ((0, 0.0), (2, 2.0), ("2", 2.0), ("0.125", 0.125), (" 1.5 ", 1.5)):
      with self.subTest(value=value):
        self.assertEqual(resource_cpu_cores(value), expected)
    for value in (None, True, False, [], {}, "bad", "512m", -1, "-1", float("nan"), float("inf")):
      with self.subTest(value=value):
        self.assertIsNone(resource_cpu_cores(value))

  def test_malformed_resource_values_do_not_crash_report(self):
    """Reject invalid capacities and allocations as unavailable values.

    Notes
    -----
    NaN, infinity, negative values, and malformed config blocks are not zero.
    """
    for resources in (
      None, [], {"cpu": "bad", "memory": "bad", "storage": -1},
      {"cpu": float("inf"), "memory": float("nan"), "storage": float("inf")},
    ):
      with self.subTest(resources=resources):
        session = self.make_session({"node-a": {"job": pipeline([resources])}})
        info = session._GenericSession__current_network_statuses["node-a"]["node-a"]
        info.update(total_cpu_cores=None, total_mem=None, total_disk=-1)
        result = session.get_network_known_nodes(include_resources=True, df_only=True, timeout=0)
        self.assertTrue(result.loc[0, RESOURCE_COLUMNS].isna().all())

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
    self.assertEqual(result.loc[0, ["PCPU", "PRAM", "PDISK"]].tolist(), [0.0, 0.0, 0.0])

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
    self.assertTrue(result[["PCPU", "PRAM", "PDISK"]].isna().all().all())
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
        self.assertTrue(set(RESOURCE_COLUMNS).issubset(result.columns))
        session._GenericSession__request_pipelines_from_net_config_monitor.assert_not_called()

  def test_reports_without_resources_do_not_fetch_configs(self):
    """Preserve report behavior for other SDK and supervisor callers.

    Notes
    -----
    Only get nodes opts into allocation collection.
    """
    session = self.make_session()
    result = session.get_network_known_nodes(df_only=True)
    self.assertTrue(set(RESOURCE_COLUMNS).isdisjoint(result.columns))
    session._GenericSession__request_pipelines_from_net_config_monitor.assert_not_called()

  def test_cli_renders_resources_with_one_decimal_in_both_views(self):
    """Render resources and a blue footnote without changing balance precision.

    Notes
    -----
    Exercise the CLI's session forwarding, normal/wide/ETH layouts, and groups.
    """
    for flags in (
      [], ["--wide"], ["--eth"], ["--group-by", "TRAM"], ["--group-by", "TRAM", "--explicit"],
      ["--group-by", "TCPU"], ["--group-by", "TCPU", "--explicit"],
    ):
      with self.subTest(flags=flags):
        session = self.make_session({"node-a": {"job": pipeline([
          {"cpu": "1.26", "memory": "1g", "storage": "2g"},
        ])}})
        args = build_parser().parse_args(["get", "nodes", *flags])
        with patch("ratio1.Session", return_value=session), \
             patch("ratio1.cli.nodes.log_with_color") as output, \
             pd.option_context("display.max_columns", None, "display.width", 2000):
          result = get_nodes(args)
        table = output.call_args_list[-2].args[0]
        footnote = output.call_args.args[0]
        self.assertEqual(output.call_args.kwargs.get("color"), "b")
        for column in RESOURCE_COLUMNS:
          self.assertIn(column, footnote)
        for definition in ("total", "Deeploy-allocated", "CPU cores", "RAM (GiB)", "disk (GiB)", "unavailable"):
          self.assertIn(definition, footnote)
        if "--group-by" not in flags or "TRAM" in flags:
          self.assertIn("TRAM", table)
          self.assertIn("31.2", table)
          self.assertNotIn("31.25", table)
        if "--group-by" not in flags or "TCPU" in flags:
          self.assertIn("16.0", table)
          self.assertNotIn("16.0000", table)
        if "--group-by" not in flags:
          self.assertEqual(result["PCPU"].iloc[0], 1.26)
          self.assertEqual(result["PRAM"].iloc[0], 1)
          header = table.splitlines()[0].split()
          start = header.index("TCPU")
          self.assertEqual(header[start:start + 6], RESOURCE_COLUMNS)
          self.assertRegex(table, r"16\.0\s+1\.3\s+31\.2\s+1\.0\s+500\.0\s+2\.0")
          self.assertRegex(table, r"16\.0\s+-\s+31\.2\s+-\s+500\.0\s+-")
          self.assertIn("500.0", table)
          if flags:
            self.assertIn("0.1234", table)


if __name__ == "__main__":
  unittest.main()
