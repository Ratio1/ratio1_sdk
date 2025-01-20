from time import time
from naeural_client.utils.config import log_with_color
from naeural_client.const import SESSION_CT, COMMANDS


def _get_netstats(
  silent=True,
  online_only=False, 
  allowed_only=False, 
  supervisor=None,
  supervisors_only=False,
  return_session=False,
):
  t1 = time()
  from naeural_client import Session
  sess = Session(silent=silent)
  dct_info = sess.get_network_known_nodes(
    online_only=online_only, allowed_only=allowed_only, supervisor=supervisor,
    supervisors_only=supervisors_only,
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
  if args.verbose:
    log_with_color(f"Getting nodes from supervisor <{supervisor_addr}>...", color='b')

  res = _get_netstats(
    silent=not args.verbose,
    online_only=args.online or args.peered,
    allowed_only=args.peered,
    supervisor=supervisor_addr,
  )
  df, supervisor, super_alias, nr_supers, elapsed = res
  if args.online:
    FILTERED = ['State']
    df = df[[c for c in df.columns if c not in FILTERED]]

  prefix = "Online n" if (args.online or args.peered) else "N"
  if supervisor == "ERROR":
    log_with_color(f"No supervisors or no comms available in {elapsed:.1f}s. Please check your settings.", color='r')
  else:
    log_with_color(f"{prefix}odes reported by <{supervisor}> '{super_alias}' in {elapsed:.1f}s ({nr_supers} supervisors seen):", color='b')
    log_with_color(f"{df}")    
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
  )
  df, supervisor, super_alias, nr_supers, elapsed = res
  FILTERED = ['Oracle', 'State']
  df = df[[c for c in df.columns if c not in FILTERED]]
  
  if supervisor == "ERROR":
    log_with_color(f"No supervisors or no comms available in {elapsed:.1f}s. Please check your settings.", color='r')
  else:
    log_with_color(f"Supervisors reported by <{supervisor}> '{super_alias}' in {elapsed:.1f}s", color='b')
    log_with_color(f"{df}")
  return

def _send_command_to_node(args, command):
  node = args.node
  silent = not args.verbose   
  
  t1 = time()
  df, _, _, _, _, sess = _get_netstats(
    silent=silent, online_only=True, return_session=True    
  )
  peered = None
  selection = df.Alias == node
  found = selection.any()
  node_addr = None
  df_found =  df[selection]
  if found:
    peered = df_found.Peered.values[0]
    node_addr = df_found.Address.values[0]   
    log_with_color(f"{df_found}")
  if not found:
    log_with_color(f"Node '{node}' <{node_addr}> not found in network.", color='r')
    return
  if not peered:
    log_with_color(f"Node '{node}' <{node_addr}> does not accept commands from this SDK.", color='r')
    return
  # TODO: currently this is based on node alias, but we should be based on node address
  #       and maybe even node alias
  if command == COMMANDS.RESTART:
    sess._send_command_restart_node(node)
  elif command == COMMANDS.SHUTDOWN:
    sess._send_command_stop_node(node)
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
  _send_command_to_node(args, COMMANDS.RESTART)
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
  _send_command_to_node(args, COMMANDS.SHUTDOWN)
  return