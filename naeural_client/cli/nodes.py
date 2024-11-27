from naeural_client.utils.config import log_with_color


def get_nodes(args):
  """
  This function is used to get the information about the nodes and it will perform the following:
  
  1. Create a Session object.
  2. Wait for the first net mon message via Session and show progress. 
  3. Wait for the second net mon message via Session and show progress.  
  4. Get the active nodes union via Session and display the nodes marking those peered vs non-peered.
  """
  if args.all:
    log_with_color("Getting all nodes information", color="b")
  elif args.peered:
    log_with_color("Getting peered nodes information", color="b")
  else:
    log_with_color("Getting default nodes information", color="b")
  return
  
  
def get_supervisors(args):
  """
  This function is used to get the information about the supervisors.
  """
  log_with_color("Getting supervisors information", color='b')
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