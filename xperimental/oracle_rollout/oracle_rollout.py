from random import randint
from time import sleep
from argparse import Namespace

from setuptools.command.alias import alias

from ratio1 import Session
from ratio1.cli.nodes import restart_node, get_nodes
from ratio1.utils.config import log_with_color


def get_seed_nodes():
  return ['0xai_Aznthe4sDsCSzExKM9PV7GN5UQF2CAwLEfagFuR8VQ5N']


def get_all_online_nodes():
  """Gets all online nodes and returns them in an array."""
  args = Namespace(supervisor=None, online_only=True, allowed_only=False, alias_filter=None, wide=True, eth=False,
                   all_info=True, wait_for_node=None, alias=None, online=False, verbose=False, peered=True)
  all_online_nodes_df = get_nodes(args)

  all_online_nodes = []
  # Transform DataFrame to array of node info with multiple fields
  if all_online_nodes_df is not None and not all_online_nodes_df.empty:
    # Extract multiple fields into structured data
    for _, row in all_online_nodes_df.iterrows():
      node_info = {
        'address': row['Address'],
        'eth_address': row['ETH Address'],
        'oracle': row['Oracle']
      }
      all_online_nodes.append(node_info)

  return all_online_nodes


def send_restart_command(nodes, timeout_min=0, timeout_max=0, verbose=True):
  """
  Send a restart command to the specified nodes.

  Parameters:
    nodes (list): List of node addresses to send the restart command to.
    timeout_min (int): Minimum timeout in seconds for the command to complete.
    timeout_max (int): Maximum timeout in seconds for the command to complete.
    verbose (bool): Whether to enable verbose output.
  """
  for node in nodes:
    # Create an args object that restart_node expects
    args = Namespace(node=node, verbose=verbose)
    restart_node(args)
    timeout = randint(timeout_min, timeout_max)
    log_with_color(f"Waiting {timeout} seconds before next restart...", color='y')
    sleep(timeout)
  return

def oracle_rollout():
  seed_nodes_addresses = get_seed_nodes()

  all_online_nodes = get_all_online_nodes()
  remaining_nodes_addresses = [node['address'] for node in all_online_nodes]

  # 1. Send restart command to Seed Nodes.
  log_with_color(f"Sending restart commands to seed nodes: {seed_nodes_addresses}", color='b')
  send_restart_command(seed_nodes_addresses)

  # Remove seed node addresses from all_nodes_addresses
  remaining_nodes_addresses = [address for address in remaining_nodes_addresses if address not in seed_nodes_addresses]

  log_with_color(
    f"Seed nodes restarted. Waiting 30 seconds before sending restart commands to all Oracle nodes, except seed nodes.",
    color='g')
  sleep(30)

  # 2. Send restart commands to all Oracle nodes, except seed nodes.
  log_with_color(f"Sending restart commands to all Oracle nodes, except seed nodes: {remaining_nodes_addresses}", color='b')
  oracle_nodes_addresses = [node['address'] for node in all_online_nodes if node['oracle'] == True]
  send_restart_command(nodes=oracle_nodes_addresses)

  # Remove oracle node addresses from all_nodes_addresses
  remaining_nodes_addresses = [address for address in remaining_nodes_addresses if address not in oracle_nodes_addresses]

  log_with_color(
    f"Oracles restarted. Waiting 30 seconds before sending restart commands to all Oracle nodes, except seed nodes.",
    color='g')
  sleep(30)

  # 3. Send restart command to all remaining edge nodes.
  log_with_color(f"Sending restart commands to all remaining edge nodes: {remaining_nodes_addresses}", color='b')

  send_restart_command(nodes=remaining_nodes_addresses, timeout_min=5, timeout_max=15)

  log_with_color(f"All nodes restarted successfully.", color='g')

  return


if __name__ == "__main__":
  log_with_color(f"Starting oracle rollout...", color='b')
  oracle_rollout()
  log_with_color(f"Oracle rollout completed.", color='g')
