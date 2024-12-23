from naeural_client.utils.config import log_with_color


def get_nodes(args):
  """
  This function is used to get the information about the nodes and it will perform the following:
  
  1. Create a Session object.
  2. Wait for the first net mon message via Session and show progress. 
  3. Wait for the second net mon message via Session and show progress.  
  4. Get the active nodes union via Session and display the nodes marking those peered vs non-peered.
  """
  from naeural_client import Session
  sess = Session(silent=True)
  if args.all:
    df, supervisor = sess.get_network_known_nodes()
    log_with_color(f"Network historical map as seen by <{supervisor}>:", color='b')
    log_with_color(f"{df}")    
  elif args.online:
    df, supervisor = sess.get_network_known_nodes(online_only=True)
    log_with_color(f"Online nodes as seen by <{supervisor}>:", color='b')
    log_with_color(f"{df}")    
  else:
    df, supervisor = sess.get_network_known_nodes(online_only=True)
    log_with_color(f"Online nodes as seen by <{supervisor}>:", color='b')
    log_with_color(f"{df}")    
  return
  
  
def get_supervisors(args):
  """
  This function is used to get the information about the supervisors.
  """
  from naeural_client import Session
  sess = Session(silent=True)
  df, supervisor = sess.get_network_known_nodes(online_only=True, supervisors_only=True)
  log_with_color(f"Supervisors reported by <{supervisor}>:\n{df}")
  return


def restart_node(args):
  """
  This function is used to restart the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  log_with_color(f"Restarting node {args.node}", color='b')
  return


def shutdown_node(args):
  """
  This function is used to shutdown the node.
  
  Parameters
  ----------
  args : argparse.Namespace
      Arguments passed to the function.
  """
  log_with_color(f"Shutting down node {args.node}", color='b')
  return