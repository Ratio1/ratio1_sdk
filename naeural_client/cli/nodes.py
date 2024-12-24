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
  if args.all:
    df, supervisor = sess.get_network_known_nodes(supervisor=supervisor_addr)
    log_with_color(f"Network full map reported by <{supervisor}>:", color='b')
    log_with_color(f"{df}")    
  elif args.online:
    df, supervisor = sess.get_network_known_nodes(
      online_only=True, supervisor=supervisor_addr
    )
    log_with_color(f"Online nodes reported by <{supervisor}>:", color='b')
    log_with_color(f"{df}")    
  else:
    df, supervisor = sess.get_network_known_nodes(
      online_only=True, supervisor=supervisor_addr
    )
    log_with_color(f"Online nodes reported by <{supervisor}>:", color='b')
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
  df, supervisor = sess.get_network_known_nodes(online_only=True, supervisors_only=True)
  log_with_color(f"Supervisors reported by <{supervisor}>", color='b')
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