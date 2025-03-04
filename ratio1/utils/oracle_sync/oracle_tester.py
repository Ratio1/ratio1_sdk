"""
TODO: add signature check for the oracle data

"""

import requests
import time
import json
from collections import defaultdict

from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine
from ratio1.utils.config import log_with_color, get_user_folder
from ratio1.const.evm_net import EvmNetData


class OracleTesterConstants:
  TEST_ENDPOINT = "/node_epochs_range"
  CURRENT_EPOCH_ENDPOINT = "/current_epoch"
  ACTIVE_NODES_ENDPOINT = "/active_nodes_list"
  DEFAULT_INTERVAL_SECONDS = 5
  DEFAULT_COMMAND_INTERVAL_SECONDS = 1
  MAX_REQUEST_ROUNDS = 10
  FREQUENCY = "frequency"
  ORACLE_DATA = "oracle_data"
  DEFAULT_MIN_CERTAINTY_PRC = 0.98


ct = OracleTesterConstants


class OracleTester:
  def __init__(
      self, bce, log,
      max_requests_rounds=ct.MAX_REQUEST_ROUNDS,
      interval_seconds=ct.DEFAULT_INTERVAL_SECONDS
  ):
    self.bc = bce
    self.log = log
    self.TEST_ENDPOINT = ct.TEST_ENDPOINT
    self.CURRENT_EPOCH_ENDPOINT = ct.CURRENT_EPOCH_ENDPOINT
    self.ACTIVE_NODES_ENDPOINT = ct.ACTIVE_NODES_ENDPOINT
    self.request_rounds = 0
    self.max_request_rounds = max_requests_rounds
    self.interval_seconds = interval_seconds

    self.node_addr_to_alias = {}
    self.alias_to_node_addr = {}
    self.node_eth_addr_to_alias = {}
    self.alias_to_node_eth_addr = {}
    self.node_addr_to_node_eth_addr = {}
    self.node_eth_addr_to_node_addr = {}
    return

  """UTILS"""
  if True:
    def get_base_url(self, network=None):
      """
      Get the base URL for the oracle API server.
      Parameters
      ----------
      network : str or None
          The network for which to get the base URL. Default None.
          If None, the network from the user config will be used.

      Returns
      -------
      str
          The base URL for the oracle API server.
      """
      network = network or self.bc.evm_network
      res = self.bc.get_network_data(network=network).get(EvmNetData.EE_ORACLE_API_URL_KEY)
      if res is None:
        msg_end = f" for the network: {network}" if network is not None else ""
        raise ValueError(f"Failed to get the base URL{msg_end}.")
      return res

    def maybe_register_node(self, node_addr: str, eth_address: str, alias: str = None):
      if node_addr is None:
        return
      self.node_addr_to_alias[node_addr] = alias
      self.node_eth_addr_to_alias[eth_address] = alias

      self.node_addr_to_node_eth_addr[node_addr] = eth_address
      self.node_eth_addr_to_node_addr[eth_address] = node_addr

      if alias is None:
        return

      self.alias_to_node_addr[alias] = node_addr
      self.alias_to_node_eth_addr[alias] = eth_address
      return

    def make_request(self, request_url, request_kwargs=None, debug=False):
      request_kwargs = request_kwargs or {}
      try:
        if debug:
          self.P(f"Making request to {request_url} with kwargs: {request_kwargs}")
        response = requests.get(request_url, params=request_kwargs)
        response.raise_for_status()  # Raise an HTTPError if the status is not 2xx
        return response.json()  # Assuming the response is JSON
      except requests.RequestException as e:
        self.P(f"Request failed: {e}")
        return None

    def done(self, rounds=None):
      if rounds is not None:
        return self.request_rounds >= rounds
      return self.request_rounds >= self.max_request_rounds

    def P(self, msg, **kwargs):
      self.log.P(msg, **kwargs)
      return

    def frequency_dict_to_str(self, freq_dict):
      return '\n'.join([
        f"\t{self.node_addr_to_alias.get(node_addr)} ({node_addr}): {freq}"
        for node_addr, freq in freq_dict.items()
      ])
  """END UTILS"""

  """RESPONSE HANDLING"""
  if True:
    def compute_epochs_availability_and_certainty(self, result: dict):
      """
      Compute the availability and certainty for a given result extracted from the response.
      Parameters
      ----------
      result : dict
          The result extracted from the response.

      Returns
      -------
      tuple
          A tuple containing the availability and certainty values.
      """
      epoch_ids = result.get("epochs")
      epoch_vals = result.get("epochs_vals")
      manager_data = result.get("oracle", {}).get("manager", {})
      dict_certainty = manager_data.get("certainty", {})
      is_valid = manager_data.get("valid", False)
      min_certainty_prc = manager_data.get("supervisor_min_avail_prc", ct.DEFAULT_MIN_CERTAINTY_PRC)

      current_epochs, current_avails, current_cert = [], [], []
      for epoch_id, epoch_val in zip(epoch_ids, epoch_vals):
        current_epochs.append(epoch_id)
        current_avails.append(epoch_val)
        current_cert.append(dict_certainty.get(str(epoch_id), 0))
      # endfor epochs
      return current_epochs, current_avails, current_cert, is_valid, min_certainty_prc

    def handle_server_data(
        self, oracle_stats_dict: dict,
        sender: str, sender_eth_addr: str, sender_node_alias: str,
        result: dict
    ):
      """
      Handle the data received from the oracle server.

      Parameters
      ----------
      oracle_stats_dict : dict
          The dictionary containing the oracle data received so far.
      sender : str
          The address of the sender.
      sender_eth_addr : str
          The ETH address of the sender.
      sender_node_alias : str
          The alias of the sender.
      result : dict
          The result extracted from the response.
      """
      if sender not in oracle_stats_dict:
        oracle_stats_dict[sender] = {
          'addr': sender,
          'eth_addr': sender_eth_addr,
          'alias': sender_node_alias,
          'errors': []
        }
      # endif first time for this sender
      current_stats = oracle_stats_dict[sender]
      # TODO: maybe automate this (have only the list of keys to go through).
      current_epochs, current_avails, current_certs, is_valid, min_certainty_prc = self.compute_epochs_availability_and_certainty(result)
      stats_epochs = current_stats.get("epochs", None)
      stats_avails = current_stats.get("avails", None)
      stats_certs = current_stats.get("certs", None)
      stats_is_valid = current_stats.get("is_valid", None)
      stats_min_certainty_prc = current_stats.get("min_certainty_prc", None)
      mismatches = []
      if stats_epochs is not None and current_epochs != stats_epochs:
        mismatches.append(f"epochs: {current_epochs} != {stats_epochs}")
      # endif check for mismatch
      if stats_avails is not None and current_avails != stats_avails:
        mismatches.append(f"avails: {current_avails} != {stats_avails}")
      # endif check for mismatch
      if stats_certs is not None and current_certs != stats_certs:
        mismatches.append(f"certainty: {current_certs} != {stats_certs}")
      # endif check for mismatch
      if stats_is_valid is not None and is_valid != stats_is_valid:
        mismatches.append(f"validity: {is_valid} != {stats_is_valid}")
      # endif check for mismatch
      if stats_min_certainty_prc is not None and min_certainty_prc != stats_min_certainty_prc:
        mismatches.append(f"min_certainty_prc: {min_certainty_prc} != {stats_min_certainty_prc}")
      # endif check for mismatch

      if len(mismatches) > 0:
        current_stats["errors"].append(f"Round {self.request_rounds}: {', '.join(mismatches)}")
      else:
        # Valid data received
        if stats_epochs is None:
          current_stats["epochs"] = current_epochs
        if stats_avails is None:
          current_stats["avails"] = current_avails
        if stats_certs is None:
          current_stats["certs"] = current_certs
        if stats_is_valid is None:
          current_stats["is_valid"] = is_valid
        if stats_min_certainty_prc is None:
          current_stats["min_certainty_prc"] = min_certainty_prc
      # endif valid data received
      return

    def add_to_stats(
        self,
        stats_dict: dict,
        response: dict,
        node_data: dict,
        debug=False
    ):
      node_eth_addr = node_data["eth_address"]
      node_addr = node_data.get("address")
      node_alias = node_data.get("alias")
      self.maybe_register_node(node_addr=node_addr, eth_address=node_eth_addr, alias=node_alias)
      result = response.get("result")
      if not result:
        return
      sender = result.get("EE_SENDER")
      sender_eth_addr = result.get("EE_ETH_SENDER")
      sender_node_alias = result.get("server_alias")
      self.maybe_register_node(node_addr=sender, eth_address=sender_eth_addr, alias=sender_node_alias)
      if node_eth_addr not in stats_dict:
        stats_dict[node_eth_addr] = {
          **node_data,
          ct.FREQUENCY: {},
          ct.ORACLE_DATA: {}
        }
      # endif first time for this node
      stats_dict[node_eth_addr][ct.FREQUENCY][sender] = stats_dict[node_eth_addr][ct.FREQUENCY].get(sender, 0) + 1

      self.handle_server_data(
        oracle_stats_dict=stats_dict[node_eth_addr][ct.ORACLE_DATA],
        sender=sender,
        sender_eth_addr=sender_eth_addr,
        sender_node_alias=sender_node_alias,
        result=result
      )

      return stats_dict
  """END RESPONSE HANDLING"""

  def gather(self, nodes, request_kwargs=None, debug=False, rounds=None, network=None):
    """
    Gather data from the oracle server for the given nodes.

    Parameters
    ----------
    nodes : list[dict] or list[str]
        The list of nodes for which to gather data. Each node can be a dictionary containing the
        address, eth_address, and alias of the node or a string containing the eth_address of the node.
        Either way, the eth_address is required.
    request_kwargs : dict
        The request kwargs to be used for the request. Default None.
    debug : bool
        Whether to enable debug mode or not. If enabled the function will exit after one request round.
    rounds : int
        The number of rounds to be executed. Default None. If None, self.max_request_rounds will be used.
    network : str
        The network for which to gather data. Default None.
        If None, the network from the user config will be used.
        In case the network is not found in the user config, the testnet will be used.

    Returns
    -------
    tuple
        A tuple containing the responses and the stats dictionary.
    """
    responses = []
    request_kwargs = request_kwargs or {}
    stats_dict = {}
    self.request_rounds = 0
    while not self.done(rounds):
      try:
        self.P(f'Starting request round {self.request_rounds + 1} for {len(nodes)} nodes...')
        current_url = self.get_base_url(network=network) + self.TEST_ENDPOINT
        # TODO: maybe shuffle the nodes list in order to avoid
        #  the same order of requests in each round
        #  relevant if the number of nodes is divisible by the number of oracles.
        for node_data in nodes:
          if isinstance(node_data, str):
            node_data = {"eth_address": node_data}
          # endif only eth address provided
          eth_addr = node_data.get("eth_address", "N/A")
          node_alias = node_data.get("alias", eth_addr)
          node_addr = node_data.get("address", eth_addr)
          self.P(f'\tRequesting data for {node_alias}...')
          current_kwargs = {
            "eth_node_addr": eth_addr,
            **request_kwargs
          }
          response = self.make_request(current_url, request_kwargs=current_kwargs, debug=debug)
          if response:
            responses.append(response)
            str_sender = response.get("node_addr")
            self.P(f"Received response from {str_sender} with keys: {response.get('result').keys()}")
            stats_dict = self.add_to_stats(
              stats_dict=stats_dict,
              response=response,
              node_data=node_data,
              debug=debug
            )
            if debug:
              self.P(f'Full response: {response}')
          else:
            self.P(f"Request failed for {node_data['alias']}")
        # endfor nodes
      except Exception as e:
        self.P(f"Request failed: {e}")
      self.request_rounds += 1
      if debug:
        self.P(f'Debug mode was enabled. Exiting after one request round.')
        break
      time.sleep(self.interval_seconds)
    # endwhile
    self.P(f'Finished gathering data for {len(nodes)} nodes and {self.max_request_rounds}.')
    return responses, stats_dict

  def gather_and_compare(self, nodes, request_kwargs=None, debug=False, rounds=None, network=None):
    """
    Gather data from the oracle server for the given nodes and compare the results between oracles.

    Parameters
    ----------
    nodes : list[dict] or list[str]
        The list of nodes for which to gather data. Each node can be a dictionary containing the
        address, eth_address, and alias of the node or a string containing the eth_address of the node.
        Either way, the eth_address is required.
    request_kwargs : dict
        The request kwargs to be used for the request. Default None.
    debug : bool
        Whether to enable debug mode or not. If enabled the function will exit after one request round.
    rounds : int
        The number of rounds to be executed. Default None. If None, self.max_request_rounds will be used.
    network : str
        The network for which to gather data. Default None.
        If None, the network from the user config will be used.
        In case the network is not found in the user config, the testnet will be used.

    Returns
    -------
    tuple
        A tuple containing the responses and the stats dictionary.
    """
    responses, stats_dict = self.gather(
      nodes=nodes,
      request_kwargs=request_kwargs,
      debug=debug,
      rounds=rounds,
      network=network
    )
    # Statistics for each node of each epoch
    epochs_nodes_stats = {}
    # Statistics for each epoch of each node
    nodes_epochs_stats = {}
    for node_eth_addr, node_data in stats_dict.items():
      oracle_data = node_data.get(ct.ORACLE_DATA, {})
      errors = oracle_data.get("errors", [])
      if len(errors) > 0:
        self.P(f'#######################{node_eth_addr} errors########################')
        self.P(f"Errors for {node_eth_addr}:\n" + '\n'.join(errors), color='r')
        self.P(f'#######################{node_eth_addr} errors########################')
      # endif

      if node_eth_addr not in nodes_epochs_stats:
        # This check should not be necessary, but just in case
        nodes_epochs_stats[node_eth_addr] = {}
      # endif first time for this node

      epochs_stats = nodes_epochs_stats[node_eth_addr]
      epochs = oracle_data.get("epochs", []),
      avails = oracle_data.get("avails", []),
      certs = oracle_data.get("certs", [])
      min_certainty_prc = oracle_data.get("stats_min_certainty_prc", ct.DEFAULT_MIN_CERTAINTY_PRC)
      for epoch, avail, cert in zip(epochs, avails, certs):
        if epoch not in epochs_nodes_stats:
          epochs_nodes_stats[epoch] = {}
        # endif epoch not in stats
        if epoch not in epochs_stats:
          epochs_stats[epoch] = {}
        # endif epoch not in stats
        node_stats = epochs_nodes_stats[epoch]

        if cert >= min_certainty_prc:
          if avail not in epochs_stats[epoch]:
            epochs_stats[epoch][avail] = set()
          if avail not in node_stats:
            node_stats[avail] = set()
          # endif first time encountering this availability
          epochs_stats[epoch][avail].add(node_eth_addr)
          node_stats[avail].add(node_eth_addr)
        # endif valid data
      # endfor each epoch


    return responses, stats_dict

  def get_current_epoch(self, network=None):
    epoch_url = self.get_base_url(network=network) + self.CURRENT_EPOCH_ENDPOINT
    response = self.make_request(epoch_url)
    if response:
      return response.get("result", {}).get("current_epoch", 1)
    return None

  def get_active_nodes(self, network=None):
    active_nodes_url = self.get_base_url(network=network) + self.ACTIVE_NODES_ENDPOINT
    response = self.make_request(active_nodes_url)
    result = []
    if response:
      nodes = response.get("result", {}).get("nodes", {})
      for node_addr, node_data in nodes.items():
        eth_addr = node_data.get("eth_addr", None)
        alias = node_data.get("alias", None)
        if eth_addr is not None:
          result.append({
            "address": node_addr,
            "eth_address": eth_addr,
            "alias": alias
          })
        # endif eth address is not None
      # endfor each node
    # endif response
    return result

  """LOGGING"""
  if True:
    def check_data(self, oracle_data: dict, node_eth_addr: str):
      valid, msg = True, ""
      if oracle_data is None:
        # If oracle_data is None, either the address was invalid or the servers are down.
        # Will attempt request for current epoch to check the servers status.
        current_epoch = self.get_current_epoch()
        valid = False
        if current_epoch is None:
          msg = f"Failed to get the current epoch. No oracle available. Please try again later."
        else:
          msg = f"No data available for {node_eth_addr}. Please check the address or contact support."
        # endif servers available
      # endif oracle_data is None
      return valid, msg

    def get_availability_str_for_one_round(
        self, node_eth_addr: str, start: int, end: int, stats_dict: dict
    ):
      oracle_data = stats_dict.get(node_eth_addr, {}).get(ct.ORACLE_DATA, None)
      valid, msg = self.check_data(oracle_data, node_eth_addr)
      if not valid:
        return msg

      msg = f'Availability for <{node_eth_addr}> from epoch {start} to epoch {end}:\n'      
      sender_addr = list(oracle_data.keys())[0]
      sender_data = oracle_data[sender_addr]
      oracle_addr = sender_data.get("addr", None)
      oracle_addr_eth = sender_data.get("eth_addr", None)
      oracle_alias = sender_data.get("alias", None)
      msg += f'  Oracle address:  {oracle_addr}\n'
      msg += f'  Oracle ETH addr: {oracle_addr_eth}\n'
      msg += f'  Oracle alias:    {oracle_alias}\n'
      msg += f'  Oracle responses:\n'
      epochs = sender_data.get("epochs", None)
      avails = sender_data.get("avails", None)
      certs = sender_data.get("certs", None)
      if epochs is None or avails is None or certs is None:
        msg = f"No data available for {node_eth_addr}. Please check the address or contact support."
      else:
        for epoch, avail, cert in zip(epochs, avails, certs):
          msg += f"   - Epoch {f'#{epoch}':>4}: {avail:3} ({cert * 100:5.1f}% certainty)\n"
      # endif data available
      return msg

    def get_availability_str_for_multiple_rounds(
        self,
        node_eth_addr: str, start: int, end: int, stats_dict: dict, rounds: int
    ):
      oracle_data = stats_dict.get(node_eth_addr, {}).get(ct.ORACLE_DATA, None)
      valid, msg = self.check_data(oracle_data, node_eth_addr)
      if not valid:
        return [msg]
      msg_list = [f'Availability for <{node_eth_addr}> from epoch {start} to epoch {end} on {rounds} rounds:\n']
      frequencies = stats_dict.get(node_eth_addr, {}).get(ct.FREQUENCY, {})
      it = 0
      for sender, sender_data in oracle_data.items():
        curr_msg = f'\tOracle #{it + 1}:\n'
        is_valid = sender_data.get("is_valid", False)
        if len(sender_data["errors"]) > 0:
          is_valid = False
          curr_msg += f'\t\t Error!! Same oracle returned different data in different rounds:\n'
          for error in sender_data["errors"]:
            curr_msg += f'\t\t\t {error}\n'
          # endfor errors
        else:
          # No errors
          if not is_valid:
            curr_msg += '\t\t WARNING:   Oracle returned invalid data due to uncertainity\n'
          # endif uncertainty
        # endif errors
        color = None if is_valid else 'r'
        str_epochs = '  '.join([f'{epoch:4}' for epoch in sender_data["epochs"]])
        str_avails = '  '.join([f'{avail:4}' for avail in sender_data["avails"]])
        str_certs  = '  '.join([f'{cert:4.2f}' for cert in sender_data["certs"]])
        curr_msg += f'\t\t Address:   {sender_data["addr"]}\n'
        curr_msg += f'\t\t ETH Addr:  {sender_data["eth_addr"]}\n'
        curr_msg += f'\t\t Alias:     {sender_data["alias"]}\n'
        curr_msg += f'\t\t Responses: {frequencies.get(sender, 0)}\n'
        curr_msg += f'\t\t Epochs:    {str_epochs}\n'
        curr_msg += f'\t\t Avails:    {str_avails}\n'
        curr_msg += f'\t\t Certainty: {str_certs}\n'
        msg_list.append((curr_msg, color))
        it += 1
      # endfor oracles
      return msg_list
  """END LOGGING"""

  def execute_command(
      self, node_eth_addr: str, start: int = 1,
      end: int = None, debug: bool = False,
      rounds: int = 1
  ):
    """
    Execute the command to get the availability of the node on a given epochs interval.
    This can also be used to get the JSON response from the server(with the use of debug=True).
    In case of debug mode, the rounds parameter is ignored(will default to 1).
    In case of multiple rounds, a delay of interval_seconds will be added between each request.
    Parameters
    ----------
    node_eth_addr : str
        The ETH address of the node for which the command will be executed.
    start : int
        The starting epoch for the request.
    end : int
        The ending epoch for the request. If None, the current epoch will be used.
    debug : bool
        Whether to enable debug mode or not. If enabled the rounds parameter is ignored and the
        function will return the JSON response from the server.
    rounds : int
        The number of rounds to be executed. Default 1.

    Returns
    -------
    dict:
        The JSON response from the server if in debug mode.
        The stats summary if not in debug mode.
    """
    rounds = min(rounds, self.max_request_rounds)
    if end is None:
      current_epoch = self.get_current_epoch()
      if current_epoch is None:
        self.P(f"Failed to get the current epoch. No oracle available. Please try again later.", show=True)
        return
      self.P(f'No end epoch provided. Using current epoch: {current_epoch}', show=True)
      end = self.get_current_epoch() - 1
    # endif end is None
    request_kwargs = {
      "start_epoch": start,
      "end_epoch": end
    }
    responses, stats = self.gather(
      nodes=[node_eth_addr],
      request_kwargs=request_kwargs,
      rounds=1 if debug else rounds,
    )
    if debug:
      return responses[0]
    if rounds > 1:
      return self.get_availability_str_for_multiple_rounds(
        node_eth_addr=node_eth_addr, start=start, end=end, stats_dict=stats, rounds=rounds
      )

    return self.get_availability_str_for_one_round(
      node_eth_addr=node_eth_addr, start=start, end=end, stats_dict=stats
    )

# endclass OracleTester

def handle_command_results(res):
  if isinstance(res, dict):
    log_with_color(json.dumps(res, indent=2), color='w')
  elif isinstance(res, list):
    for msg_data in res:
      if isinstance(msg_data, tuple):
        log_with_color(msg_data[0], color=msg_data[1])
      else:
        log_with_color(msg_data, color='w')
    # endfor each message
  else:
    log_with_color(res, color='w')
  return

def oracle_tester_init(silent=True, **kwargs):
  log = Logger(
    "R1CTL",
    base_folder=str(get_user_folder()),
    app_folder="_local_cache",
    silent=silent
  )
  bc = DefaultBlockEngine(name='R1CTL', log=log)

  tester = OracleTester(
    bce=bc,
    log=log,
    **kwargs
  )
  return tester

def test_commands():
  from ratio1.utils.config import load_user_defined_config
  load_user_defined_config()
  tester = oracle_tester_init(max_requests_rounds=30)
  start = 10
  end = 10
  # node_eth_addr = "0x7C07758C23DF14c2fF4b016F0ad58F2D4aF329a7"  # r1s-ssj-1
  # node_eth_addr = "0xdc4fDFd5B86aeA7BaB17d4742B7c39A2728Ff59B"  # r1s-02
  # node_eth_addr = "0x93B04EF1152D81A0847C2272860a8a5C70280E14"  # tr1s-aid02
  node_eth_addr = '0x37379B80c7657620E5631832c4437B51D67A88cB'  # dr1s-db-1

  # Single round
  tester.P(f'Test single round: Epochs {start} to {end}', show=True)
  res = tester.execute_command(node_eth_addr=node_eth_addr, start=start, end=end)
  handle_command_results(res)

  # Multiple rounds
  tester.P(f'Test multiple rounds: Epochs {start} to {end}', show=True)
  res = tester.execute_command(node_eth_addr=node_eth_addr, start=start, end=end, rounds=3)
  handle_command_results(res)

  # Debug mode
  tester.P(f'Test debug mode: Epochs {start} to {end}', show=True)
  res = tester.execute_command(node_eth_addr=node_eth_addr, start=5, end=7, debug=True)
  handle_command_results(res)
  return

def oracle_check(N=10):
  import random
  random.seed(42)

  tester = oracle_tester_init(
    silent=True,
    interval_seconds=0.2,
  )
  current_epoch = tester.get_current_epoch()
  if current_epoch is None:
    current_epoch = 100
  nodes = tester.get_active_nodes()
  rounds = 5
  max_epochs = 10
  max_nodes = 5

  nodes = nodes[:max_nodes]
  for i in range(N):
    start = random.randint(1, current_epoch - 1)
    end = random.randint(start, current_epoch - 1)
    end = min(end, start + max_epochs - 1)

    tester.P(f'Test {i + 1}/{N}: Epochs {start} to {end} with {rounds} rounds:', show=True)
    tester.gather_and_compare(
      nodes=nodes,
      request_kwargs={
        "start_epoch": start,
        "end_epoch": end
      },
    )
    tester.P(f'Finished test {i + 1}/{N}', show=True)
  # endfor each test
  return

def oracle_test(N=10):
  import random

  random.seed(42)

  tester = oracle_tester_init(
    silent=True,
    interval_seconds=0.2,
  )
  current_epoch = tester.get_current_epoch()
  if current_epoch is None:
    current_epoch = 96
  nodes = tester.get_active_nodes()
  rounds = 5
  max_epochs = 10
  max_nodes = 5

  for i in range(N):
    node_list = random.sample(nodes, min(len(nodes), max_nodes))
    start = random.randint(1, current_epoch - 1)
    end = random.randint(start, current_epoch - 1)
    end = min(end, start + max_epochs - 1)

    tester.P(f'Test {i + 1}/{N}: Epochs {start} to {end} with {rounds} rounds:', show=True)
    res = tester.gather(
      nodes=node_list,
      request_kwargs={
        "start_epoch": start,
        "end_epoch": end
      },
      rounds=rounds
    )

    for node_data in node_list:
      msg_list = tester.get_availability_str_for_multiple_rounds(
        node_eth_addr=node_data['eth_address'], start=start, end=end, stats_dict=res[1], rounds=rounds
      )
      for msg_data in msg_list:
        if isinstance(msg_data, tuple):
          tester.P(msg_data[0], color=msg_data[1], show=True)
        else:
          tester.P(msg_data, show=True)
      # endfor each message
    # endfor each node
    tester.P(f'Finished test {i + 1}/{N}', show=True)
  # endfor each test
  return

# Main loop
def main():
  TEST_COMMANDS = True
  TEST_ORACLE = False
  if TEST_COMMANDS:
    test_commands()

  if TEST_ORACLE:
    oracle_test(5)
  return


if __name__ == "__main__":
  main()
