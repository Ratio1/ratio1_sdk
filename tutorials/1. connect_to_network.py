"""
This is a simple example of how to use the naeural_client SDK.

In this example, we connect to the network, listen for heartbeats from 
  Naeural edge nodes and print the CPU of each node.
"""

from naeural_client import Session


def on_heartbeat(session: Session, node_addr: str, heartbeat: dict):
  session.P("{} ({}) has a {}".format(heartbeat['EE_ID'], node_addr, heartbeat["CPU"]))
  return


if __name__ == '__main__':
  # create a session
  # the network credentials are read from the .env file automatically
  session = Session(
      on_heartbeat=on_heartbeat
  )


  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   in production, you would not need this code as the script can close after the pipeline will be sent
  session.run(
    wait=60, # wait for the user to stop the execution or a given time
    close_pipelines=True # when the user stops the execution, the remote edge-node pipelines will be closed
  )
  session.P("Main thread exiting...")
