from naeural_client.utils.config import log_with_color


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
  from naeural_client import Session
  sess = Session(silent=not args.verbose)
  online_only = args.online or args.peered
  allowed_only = args.peered
  
  dct_info = sess.get_network_known_nodes(
    online_only=online_only, allowed_only=allowed_only, supervisor=supervisor_addr
  )
  df = dct_info['report']
  supervisor = dct_info['reporter']
  super_alias = dct_info['reporter_alias']
  nr_supers = dct_info['nr_super']
  elapsed = dct_info['elapsed']
  prefix = "Online n" if online_only else "N"
  log_with_color(f"{prefix}odes reported by <{supervisor}> '{super_alias}' in {elapsed:.1f}s ({nr_supers} supervisors seen):", color='b')
  log_with_color(f"{df}")    
  return
  
  
def get_supervisors(args):
  """
  This function is used to get the information about the supervisors.
  """
  if args.verbose:
    log_with_color("Getting supervisors...", color='b')
  from naeural_client import Session  
  sess = Session(silent=not args.verbose)
  dct_info = sess.get_network_known_nodes(online_only=True, supervisors_only=True)
  df = dct_info['report']
  supervisor = dct_info['reporter']
  super_alias = dct_info['reporter_alias']
  elapsed = dct_info['elapsed']  
  log_with_color(f"Supervisors reported by <{supervisor}> '{super_alias}' in {elapsed:.1f}s", color='b')
  log_with_color(f"{df}")
  return


def restart_node(args):
  """
  This function is used to restart the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  log_with_color(f"Restarting node {args.node} NOT IMPLEMENTED", color='r')
  return


def shutdown_node(args):
  """
  This function is used to shutdown the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  log_with_color(f"Shutting down node {args.node} NOT IMPLEMENTED", color='r')
  return