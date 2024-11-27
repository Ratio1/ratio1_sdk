from naeural_client.utils.config import log_with_color


def get_nodes():
  """
  This function is used to get the information about the nodes and it will perform the following:
  
  1. Create a Session object.
  2. Wait for the first net mon message via Session and show progress. 
  3. Wait for the second net mon message via Session and show progress.  
  4. Get the active nodes union via Session and display the nodes marking those peered vs non-peered.
  """
  log_with_color("Getting nodes information", color="b")
  return
  
  
def get_supervisors():
  """
  This function is used to get the information about the supervisors.
  """
  log_with_color("Getting supervisors information", color='b')
  return