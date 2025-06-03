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
  return
  
  
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
  )
  df, supervisor, super_alias, nr_supers, elapsed, sess = res
  FILTERED = ['Oracle', 'State']
  df = df[[c for c in df.columns if c not in FILTERED]]
  
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
  node = args.node
  silent = not args.verbose   

  
  t1 = time()
  df, _, _, _, _, sess = _get_netstats(
    silent=silent, online_only=True, return_session=True, all_info=True,
    wait_for_node=node
  )
  
  peered = None
  selection = (df.Alias == node) | (df.Address == node)
  if 'ETH Address' in df.columns:
    selection = selection | (df['ETH Address'] == node)
  found = selection.any()
  node_addr = None
  alias = None
  df_found =  df[selection]
  if found:
    alias = df_found.Alias.values[0]
    peered = df_found.Peered.values[0]
    node_addr = df_found.Address.values[0]   
    log_with_color(f"{df_found}")
  else:
    log_with_color("Node '{}' <{}> not found in network (toal {} nodes, {} peered).".format(
      node, node_addr, df.shape[0], df.Peered.sum()), color='r'
    )
    node_addr = node
    
  if not peered:
    if found:
      log_with_color(f"Node '{node}' <{node_addr}> is not peered.", color='r')
    else:
      log_with_color(f"Node '{node}' <{node_addr}> may not accept this command.", color='r')
    
  # TODO: currently this is based on node alias, but we should be based on node address
  #       and maybe even node alias
  if (found and peered) or ignore_not_found:
    if found and peered:
      log_with_color(f"Sending '{command}' to node '{alias}' <{node_addr}>", color='b')
    else:
      log_with_color(f"Sending blind '{command}' to node '{alias}' <{node_addr}>", color='b')      
    if command == COMMANDS.RESTART:
      sess._send_command_restart_node(node_addr)
    elif command == COMMANDS.STOP:
      sess._send_command_stop_node(node_addr)
    else:
      log_with_color(f"Command '{command}' not supported.", color='r')
      return
  elapsed = time() - t1  
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

