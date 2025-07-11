"""


NOTE: if any of oracles return  data["result"]["oracle"]["manager"]["valid"] != True then
  - ommit that oracle from the list of oracles shown
  - display red warning containing the issue and the "certainty" 

>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8

Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6 on 8 rounds:
  Oracle #1:
    Address:   0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH
    ETH Addr:  0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
    Alias:     nen-aid01
    Responses: 3
    Epochs:    [   4,    5,    6]
    Avails:    [   3,  254,  127]
    Cartainty: [0.99, 0.99, 0.99]
  Oracle #2:
    Address:   0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6
    ETH Addr:  0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0
    Alias:     nen-2
    Responses: 2
    Epochs:    [   4,    5,    6]
    Avails:    [   3,  254,  127]
    Cartainty: [0.99, 0.99, 0.99]
  Oracle #3: [RED due to not data["result"]["oracle"]["manager"]["valid"]]
    WARNING:   Oracle returned invalid data due to uncertainity
    Address:   0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL
    ETH Addr:  0x93B04EF1152D81A0847C2272860a8a5C70280E14
    Alias:     nen-aid02
    Responses: 3
    Epochs:    [   4,    5,    6]
    Avails:    [   3,    0,  127]
    Cartainty: [0.99, 0.41, 0.99]


>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8

Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6 on 8 rounds:
  Oracle #1:
    Address:   0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH
    ETH Addr:  0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
    Alias:     nen-aid01
    Responses: 3
    Avails:    [3, 254, 127]
  Oracle #2:
    Address:   0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6
    ETH Addr:  0x129a21A78EBBA79aE78B8f11d5B57102950c1Fc0
    Alias:     nen-2
    Responses: 3
    Avails:    [3, 254, 127]
  Oracle #3:
    Address:   0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL
    ETH Addr:  0x93B04EF1152D81A0847C2272860a8a5C70280E14
    Alias:     nen-aid02
    Responses: 3
    Avails:    [3, 254, 127]



>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --rounds 8
[if same oracle returns different avail dump the two confligting json with RED and stop command]    

>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 --full
[just dump json]


>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 --start 4 --end 6 
Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 4 to epoch 6:
Oracle address: 0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
Oracle alias:   nen-aid01
Oracle report:
  - Epoch #4: 127 ( 50%)
  - Epoch #5: 254 (100%)
  - Epoch #6:   3 (  1%)
  
>nepctl get avail 0x693369781001bAC65F653856d0C00fA62129F407 # assuming current epoch is 10
Availability of node <0x693369781001bAC65F653856d0C00fA62129F407> from epoch 1 to epoch 9:
Oracle address: 0xE486F0d594e9F26931fC10c29E6409AEBb7b5144
Oracle alias:   nen-aid01
Oracle report:
  - Epoch #1: 127 ( 50%)
  - Epoch #2: 127 ( 50%)
  - Epoch #3: 127 ( 50%)
  - Epoch #4: 127 ( 50%)
  - Epoch #5: 254 (100%)
  - Epoch #6:   3 (  1%)
  - Epoch #7:  64 ( 25%)
  - Epoch #8:  33 ( 13%)
  - Epoch #9: 254 (100%)  
  
  
TODO: (future)
  - check ETH signature of the oracle data

"""
from ratio1.const.base import LocalInfo
from ratio1.const.evm_net import EVM_NET_CONSTANTS, EvmNetConstants
from ratio1.utils.config import log_with_color
from ratio1.utils.oracle_sync.oracle_tester import oracle_tester_init, handle_command_results
from ratio1.cli.nodes import restart_node, get_nodes
from ratio1.utils.config import log_with_color
from ratio1 import Session

from random import randint
from time import sleep
from argparse import Namespace

def get_availability(args):
  """
  This function is used to get the availability of the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  
  node = args.node
  start = args.start or 1
  end = args.end
  full = args.json
  rounds = args.rounds or 1
  if str(rounds).isnumeric() and int(rounds) > 0:
    rounds = int(rounds)
  else:
    log_with_color("`rounds` must be a positive integer. Setting rounds to 1.", color='r')
    rounds = 1
  # endif rounds

  if isinstance(rounds, int) and rounds > 10:
    log_with_color("Rounds exceed the maximum limit of 10. Setting rounds to 10.", color='r')
    rounds = min(rounds, 10)

  if full:
    if rounds > 1:
      log_with_color("Cannot generate full JSON oracle network output in 'rounds' mode.", color='r')
      full = False
  # endif full

  tester = oracle_tester_init()
  
  if not tester.bc.is_valid_eth_address(node):
    node = tester.bc.node_address_to_eth_address(node)
  
  log_with_color("Checking {}availability of node <{}> from {} to {}.".format(
    "(DEBUG MODE) " if rounds > 1 else "", node, start,
    end if end else "last epoch"
    ), color='b'
  )
    
  
  res = tester.execute_command(
    node_eth_addr=node,
    start=start,
    end=end,
    rounds=rounds,
    debug=full
  )
  handle_command_results(res)
  return

if True:
  def _get_seed_nodes(current_network):
    """Gets the seed nodes and returns them in an array."""
    return EVM_NET_CONSTANTS[current_network][EvmNetConstants.SEED_NODES_ADDRESSES_KEY]


  def _get_all_online_nodes():
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


  def _send_restart_command(session, nodes, timeout_min=0, timeout_max=0, verbose=True):
    """
    Send a restart command to the specified nodes.

    Parameters:
      session (Session): Session object.
      nodes (list): List of node addresses to send the restart command to.
      timeout_min (int): Minimum timeout in seconds for the command to complete.
      timeout_max (int): Maximum timeout in seconds for the command to complete.
      verbose (bool): Whether to enable verbose output.
    """
    for node in nodes:
      # Create an args object that restart_node expects
      session._send_command_restart_node(node)
      timeout = randint(timeout_min, timeout_max)
      log_with_color("".join([f"Restarting {node} | ",
                              f"Waiting {timeout} seconds before next restart..."]),
                     color='y')
      sleep(timeout)
    return


  def oracle_rollout(args):
    """
    This function performs an oracle rollout by restarting seed nodes, oracle nodes, and edge nodes in sequence.
    It first restarts the seed nodes, waits for a specified time, then restarts all oracle nodes except the seed nodes,
    waits again, and finally restarts all remaining edge nodes.

    This function is needed in order to ensure that all nodes in the network receive the new configuration defined on the seed nodes.
    """
    silent = not args.verbose
    session = Session(
      silent=True
    )
    current_network = session.bc_engine.current_evm_network
    session.close()

    log_with_color(f"ATTENTION! Current network: {current_network}", color='y')
    log_with_color(f"Are you sure you want to restart ALL nodes on the network {current_network}?", color='b')
    user_confirmation = input(f"Write down 'RESTART ALL on {current_network}' in order to proceed...\n >")

    if user_confirmation != f"RESTART ALL on {current_network}":
      log_with_color("Aborted by user...", color='y')
      return

    session = Session(
      silent=silent
    )

    seed_nodes_addresses = _get_seed_nodes(current_network)

    all_online_nodes = _get_all_online_nodes()
    remaining_nodes = [
      node
      for node in all_online_nodes
      if node['address'] not in seed_nodes_addresses
    ]

    # 1. Send restart command to Seed Nodes.
    log_with_color(f"Sending restart commands to {len(seed_nodes_addresses)} seed nodes: {seed_nodes_addresses}", color='b')
    _send_restart_command(session=session, nodes=seed_nodes_addresses)

    # Remove seed node addresses from all_nodes_addresses
    log_with_color(
      f"Seed nodes restarted. Waiting 30 seconds before sending restart commands to all Oracle nodes, except seed nodes.",
      color='g')
    sleep(30)

    # 2. Send restart commands to all Oracle nodes, except seed nodes.
    oracle_nodes_addresses = [
      node['address']
      for node in remaining_nodes
      if node['oracle'] == True
    ]

    log_with_color(f"Sending restart commands to {len(oracle_nodes_addresses)} Non-Seed Oracle nodes, except seed nodes: {remaining_nodes}", color='b')

    _send_restart_command(session=session, nodes=oracle_nodes_addresses)

    # Remove oracle node addresses from all_nodes_addresses
    remaining_nodes_addresses = [
      node['address']
      for node in remaining_nodes
      if node['address'] not in oracle_nodes_addresses
    ]

    log_with_color(
      f"Oracles restarted. Waiting 30 seconds before sending restart commands to all Oracle nodes, except seed nodes.",
      color='g')
    sleep(30)

    # 3. Send restart command to all remaining edge nodes.
    log_with_color(f"Sending restart commands to {len(remaining_nodes_addresses)} remaining edge nodes: {remaining_nodes_addresses}", color='b')

    _send_restart_command(session=session, nodes=remaining_nodes_addresses, timeout_min=5, timeout_max=25)

    restarted_seed_nodes_count = len(seed_nodes_addresses)
    restarted_oracle_nodes_count = len(oracle_nodes_addresses)
    restarted_edge_nodes_count = len(remaining_nodes_addresses)
    total_restarted_nodes_count = restarted_seed_nodes_count + restarted_oracle_nodes_count + restarted_edge_nodes_count
    log_with_color(f"All nodes restarted successfully.", color='g')
    log_with_color("======================================================", color='b')
    log_with_color(f"Total restarted {total_restarted_nodes_count} Nodes", color='b')
    log_with_color(f"Restarted {restarted_seed_nodes_count} Seed Oracle Nodes", color='b')
    log_with_color(f"Restarted {restarted_oracle_nodes_count} Non-Seed Oracle Nodes", color='b')
    log_with_color(f"Restarted {restarted_edge_nodes_count} Edge Nodes", color='b')

    session.close()
    return


if __name__ == "__main__":
  log_with_color(f"Starting oracle rollout...", color='b')
  oracle_rollout()
  log_with_color(f"Oracle rollout completed.", color='g')
