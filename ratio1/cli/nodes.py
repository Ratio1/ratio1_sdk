import os
import json

from time import time
from ratio1.utils.config import log_with_color
from ratio1.const import SESSION_CT, COMMANDS, BASE_CT
from ratio1._ver import __VER__ as version

from pandas import DataFrame
from datetime import datetime


def _get_netstats(
  silent=True,
  online_only=False, 
  allowed_only=False, 
  supervisor=None,
  alias_filter=None,
  supervisors_only=False,
  return_session=False,
  eth=False,
  all_info=False,
  wait_for_node=None
):
  t1 = time()
  from ratio1 import Session
  sess = Session(silent=silent)
  found = None
  if wait_for_node:
    sess.P("Waiting for node '{}' to appear...".format(wait_for_node), color='y')
    found = sess.wait_for_node(wait_for_node, timeout=30)
    if not found:
      sess.P("Node '{}' not found.".format(wait_for_node), color='r')

  dct_info = sess.get_network_known_nodes(
    online_only=online_only, allowed_only=allowed_only, supervisor=supervisor,
    supervisors_only=supervisors_only,
    alias_filter=alias_filter,
    min_supervisors=1,
    eth=eth,
    all_info=all_info, 
  )
  df = dct_info[SESSION_CT.NETSTATS_REPORT]
  supervisor = dct_info[SESSION_CT.NETSTATS_REPORTER]
  super_alias = dct_info[SESSION_CT.NETSTATS_REPORTER_ALIAS]
  nr_supers = dct_info[SESSION_CT.NETSTATS_NR_SUPERVISORS]
  _elapsed = dct_info[SESSION_CT.NETSTATS_ELAPSED] # computed on call
  elapsed = time() - t1 # elapsed=_elapsed
  if return_session:
    return df, supervisor, super_alias, nr_supers, elapsed, sess  
  return df, supervisor, super_alias, nr_supers, elapsed



def get_nodes(args):
  """
  This function is used to get the information about the nodes and it will perform the following:
  
  1. Create a Session object.
  2. Wait for the first net mon message via Session and show progress. 
  3. Wait for the second net mon message via Session and show progress.  
  4. Get the active nodes union via Session and display the nodes marking those peered vs non-peered.
  """
  supervisor_addr = args.supervisor
  alias_filter = args.alias
  online = args.online
  online = True # always online, flag deprecated
  wide = args.wide
  if args.verbose:
    log_with_color(f"Getting nodes from supervisor <{supervisor_addr}>...", color='b')

  res = _get_netstats(
    silent=not args.verbose,
    online_only=online or args.peered,
    allowed_only=args.peered,
    supervisor=supervisor_addr,
    alias_filter=alias_filter,
    eth=args.eth,
    all_info=wide,
    return_session=True,
  )
  df, supervisor, super_alias, nr_supers, elapsed, sess = res
  if args.online:
    FILTERED = ['State']
    df = df[[c for c in df.columns if c not in FILTERED]]

  prefix = "Online n" if (online or args.peered) else "N"
  # network = os.environ.get(BASE_CT.dAuth.DAUTH_NET_ENV_KEY, BASE_CT.dAuth.DAUTH_SDK_NET_DEFAULT)
  network = sess.bc_engine.evm_network
  addr = sess.bc_engine.address
  if supervisor == "ERROR":
    log_with_color(f"No supervisors or no comms available in {elapsed:.1f}s. Please check your settings.", color='r')
  else:
    log_with_color(f"Ratio1 client v{version}: {addr} \n", color='b')
    log_with_color(
      "{}odes on '{}' reported by <{}> '{}' in {:.1f}s ({} supervisors seen):".format(
      prefix, network, supervisor, super_alias, elapsed, nr_supers), 
      color='b'
    )
    import pandas as pd
    pd.set_option('display.float_format', '{:.4f}'.format)
    log_with_color(f"{df}\n")    
  return df
  
  
def get_supervisors(args):
  """
  This function is used to get the information about the supervisors.
  """
  if args.verbose:
    log_with_color("Getting supervisors...", color='b')

  res = _get_netstats(
    silent=not args.verbose,
    online_only=True,
    supervisors_only=True,
    return_session=True,
    eth=args.eth,
    all_info=args.wide,    
  )
  df, supervisor, super_alias, nr_supers, elapsed, sess = res
  FILTERED = ['Oracle', 'State']
  df = df[[c for c in df.columns if c not in FILTERED]]

  import pandas as pd
  pd.set_option('display.float_format', '{:.4f}'.format)
  
  if supervisor == "ERROR":
    log_with_color(f"No supervisors or no comms available in {elapsed:.1f}s. Please check your settings.", color='r')
  else:
    log_with_color(
      "Supervisors on '{}' reported by <{}> '{}' in {:.1f}s".format(
      sess.bc_engine.evm_network, supervisor, super_alias, elapsed), 
      color='b'
    )
    log_with_color(f"{df}")
  return


def get_apps(args):
  """
  Shows the apps running on a given node, if the client is allowed on that node.
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.

  """
  verbose = args.verbose
  node = args.node
  show_full = args.full
  as_json = args.json
  owner = args.owner

  # 1. Init session
  from ratio1 import Session
  sess = Session(
    silent=not verbose
  )
  
  res = sess.get_nodes_apps(
    node=node, owner=owner, show_full=show_full, 
    as_json=as_json, as_df=not as_json
  )
  if res is not None:
    network = sess.bc_engine.evm_network
    node_alias = sess.get_node_alias(node) if node else None
    if as_json:
      log_with_color(json.dumps(res, indent=2))
    else:
      df_apps = res
      if df_apps.shape[0] == 0:
        log_with_color(
          "No user apps found on node <{}> '{}' of network '{}'".format(
            node, node_alias, network            
          ), 
          color='r'
        )
        return
      # remove Node column
      if node is not None and owner is None:
        df_apps.drop(columns=['Node'], inplace=True)
      
      if node is None and owner is not None:
        df_apps.drop(columns=['Owner'], inplace=True)
      
      if node is not None:
        last_seen = sess.get_last_seen_time(node)
        last_seen_str = datetime.fromtimestamp(last_seen).strftime('%Y-%m-%d %H:%M:%S') if last_seen else None
        is_online = sess.check_node_online(node)    
        node_status = 'Online' if is_online else 'Offline'
      else:
        last_seen_str = "N/A"
        node_status = "N/A"
      #end if node
      if node == None:
        node = "[All available]"
      by_owner = f" by owner <{owner}>" if owner else ""    
      log_with_color(f"Ratio1 client v{version}:\n", color='b')
      log_with_color(
        "Apps on <{}> ({}) [Status: {}| Last seen: {}]{}:".format(
          node, network, node_status, last_seen_str, by_owner
        ), 
        color='b'
      )
      log_with_color(f"{df_apps}\n")
    #end if as_json
  #end if res is not None
  return

def _send_command_to_node(args, command, ignore_not_found=False):
  from ratio1 import Session

  node = args.node
  silent = not args.verbose   
  ignore_peering = args.ignore_peering

  t1 = time()
  sess = Session(silent=silent)

  peered, node_addr = sess.is_peered(node, return_full_address=True)
  found = False

  if not ignore_peering:
    found = sess.wait_for_node(node_addr, timeout=30)
    sess.P(f"Node {node_addr} is online.")

  # Display peering status.
  if not peered:
    if not ignore_peering:
      log_with_color(f"Node <{node_addr}> is not peered. Exiting...", color='r')
      return

    if found:
      log_with_color(f"Node '{node}' <{node_addr}> is not peered.", color='r')
    else:
      log_with_color(f"Node '{node}' <{node_addr}> may not accept this command.", color='r')

  if found and peered:
    log_with_color(f"Sending '{command}' to node <{node_addr}>", color='b')
  else:
    log_with_color(f"Sending blind '{command}' to node <{node_addr}>", color='b')

  if (found and peered) or ignore_not_found or ignore_peering:
    if command == COMMANDS.RESTART:
      sess._send_command_restart_node(node_addr)
    elif command == COMMANDS.STOP:
      sess._send_command_stop_node(node_addr)
    else:
      log_with_color(f"Command '{command}' not supported.", color='r')
      return

  sess.close()
  log_with_color(f"Command successfully sent.")
  elapsed = time() - t1
  if not silent:
    log_with_color(f"Command '{command}' seinging took {elapsed}s.", color='b')
  return  

def restart_node(args):
  """
  This function is used to restart the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  node = args.node

  log_with_color(f"Attempting to restart node <{node}>", color='b')
  _send_command_to_node(args, COMMANDS.RESTART, ignore_not_found=True)
  return


def shutdown_node(args):
  """
  This function is used to shutdown the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  node = args.node

  log_with_color(f"Attempting to shutdown node <{node}>", color='b')
  _send_command_to_node(args, COMMANDS.STOP, ignore_not_found=True)
  return


def inspect_node(args):
  """
  This function is used to inspect the node info.

  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  node = args.node
  wide = args.wide
  silent = not args.verbose

  if not silent:
    log_with_color(f"Inspecting node <{node}>", color='b')

  from ratio1 import Session
  session = Session(
    silent=silent
  )
  try:
    node_address = session.get_node_address(node)
    last_hb = session.get_last_hb()
    node_last_hb = last_hb.get(node_address)

    if not node_last_hb:
      # No last HB was found for specified Address, ETH Address or alias.
      raise ValueError("Could not find a node by provided address/alias.")

    # Display node stats from HB:
    _display_node_stats_for_hb(node_last_hb, wide)

  except Exception as e:
    log_with_color(f"An error occurred while trying to get node info: {e}", color='r')
  finally:
    session.close()
  return


def _display_node_stats_for_hb(node_hb, wide=False):
  """
  Display main system information from node heartbeat data.
  
  Parameters
  ----------
  node_hb : dict
      Node heartbeat data containing system information
  wide: bool
      If True, display all plugins.
  """
  from ratio1 import HEARTBEAT_DATA
  from ratio1.utils.config import log_with_color
  from ratio1.const.base import BCctbase
  from ratio1 import PAYLOAD_DATA

  # Extract basic node info
  ee_id = node_hb.get(HEARTBEAT_DATA.EE_ID, 'Unknown')
  node_addr = node_hb.get(HEARTBEAT_DATA.EE_ADDR, 'Unknown')
  eth_addr = node_hb.get(BCctbase.ETH_SENDER, 'Unknown')
  ee_version = node_hb.get(PAYLOAD_DATA.EE_VERSION, 'Unknown')
  uptime = node_hb.get(HEARTBEAT_DATA.UPTIME, 0)
  
  # Display node header
  log_with_color(f"\n=== Node Information ===", color='b')
  log_with_color(f"Node alias: {ee_id}", color='g')
  log_with_color(f"Address: {node_addr}", color='g')
  log_with_color(f"ETH Address: {eth_addr}", color='g')
  log_with_color(f"Edge Node Version: {ee_version}", color='g')
  log_with_color(f"Uptime: {uptime:.1f} seconds ({uptime/3600:.1f} hours)", color='g')
  
  # CPU Information
  cpu_info = node_hb.get(HEARTBEAT_DATA.CPU, 'Unknown')
  cpu_cores = node_hb.get(HEARTBEAT_DATA.CPU_NR_CORES, 0)
  cpu_used = node_hb.get(HEARTBEAT_DATA.CPU_USED, 0)
  
  log_with_color(f"\n=== CPU Information ===", color='b')
  log_with_color(f"Processor: {cpu_info}", color='y')
  log_with_color(f"Cores: {cpu_cores}", color='y')
  log_with_color(f"Usage: {cpu_used:.1f}%", color='y')
  
  # Memory Information
  total_memory = node_hb.get(HEARTBEAT_DATA.MACHINE_MEMORY, 0)
  available_memory = node_hb.get(HEARTBEAT_DATA.AVAILABLE_MEMORY, 0)
  process_memory = node_hb.get(HEARTBEAT_DATA.PROCESS_MEMORY, 0)
  is_alert_ram = node_hb.get(HEARTBEAT_DATA.IS_ALERT_RAM, False)
  
  used_memory = total_memory - available_memory if total_memory and available_memory else 0
  memory_usage_pct = (used_memory / total_memory * 100) if total_memory > 0 else 0
  
  log_with_color(f"\n=== Memory Information ===", color='b')
  log_with_color(f"Total Memory: {total_memory:.2f} GB", color='y')
  log_with_color(f"Available Memory: {available_memory:.2f} GB", color='y')
  log_with_color(f"Used Memory: {used_memory:.2f} GB ({memory_usage_pct:.1f}%)", color='y')
  log_with_color(f"Process Memory: {process_memory:.2f} GB", color='y')
  if is_alert_ram:
    log_with_color(f"RAM Alert: True", color='r')
  
  # Disk Information
  total_disk = node_hb.get(HEARTBEAT_DATA.TOTAL_DISK, 0)
  available_disk = node_hb.get(HEARTBEAT_DATA.AVAILABLE_DISK, 0)
  
  used_disk = total_disk - available_disk if total_disk and available_disk else 0
  disk_usage_pct = (used_disk / total_disk * 100) if total_disk > 0 else 0
  
  log_with_color(f"\n=== Disk Information ===", color='b')
  log_with_color(f"Total Disk: {total_disk:.2f} GB", color='y')
  log_with_color(f"Available Disk: {available_disk:.2f} GB", color='y')
  log_with_color(f"Used Disk: {used_disk:.2f} GB ({disk_usage_pct:.1f}%)", color='y')
  
  # Active Plugins
  active_plugins = node_hb.get(HEARTBEAT_DATA.ACTIVE_PLUGINS, [])
  log_with_color(f"\n=== Active Plugins ===", color='b')
  log_with_color(f"Number of Active Plugins: {len(active_plugins)}", color='y')
  
  if active_plugins:
    plugins_to_display = 99999 if wide else 5
    for i, plugin in enumerate(active_plugins[:plugins_to_display]):  # Show first 5 plugins
      stream_id = plugin.get(HEARTBEAT_DATA.ACTIVE_PLUGINS_INFO.STREAM_ID, 'Unknown')
      signature = plugin.get(HEARTBEAT_DATA.ACTIVE_PLUGINS_INFO.SIGNATURE, 'Unknown')
      instance_id = plugin.get(HEARTBEAT_DATA.ACTIVE_PLUGINS_INFO.INSTANCE_ID, 'Unknown')
      total_payload = plugin.get(HEARTBEAT_DATA.ACTIVE_PLUGINS_INFO.TOTAL_PAYLOAD_COUNT, 0)
      log_with_color(f"  {i+1}. {stream_id} {signature} ({instance_id}) - {total_payload} payloads", color='w')
    
    if len(active_plugins) > plugins_to_display:
      log_with_color(f"  ... and {len(active_plugins) - plugins_to_display} more plugins", color='w')
  
  log_with_color(f"\n", color='w')  # Add final newline for spacing

  return