"""
This is a simple example of how to use the naeural_client SDK.

In this example, we connect to the network, listen for heartbeats from 
  Naeural Edge Protocol edge nodes and print the CPU of each node.
  
  
  
New connection algorithm:

1. The client connects to the network.
2. The client waits for the first 2 supervisors payload with network map. 
3. The client reads `partner_peers` - all nodes that recognize the client as allowed - based on supervisor(s) network map.
4. The client sends a pipeline status to all `partner_peers`.
5. The client then knows the `partner_peers` and can send messages to them.
IMPORTANT: Session will WAIT until network map is clarified.

"""
import json

from naeural_client import Session, Payload, PAYLOAD_DATA, HEARTBEAT_DATA


class MessageHandler:  
  def shorten_address(self, address):
    """
    This method is used to shorten the address of the edge node.
    """
    return address[:8] + "..." + address[-6:]
  
  def on_heartbeat(self, session: Session, node_addr: str, heartbeat: dict):
    """
    This method is called when a heartbeat is received from an edge node.
    
    Parameters
    ----------
    session : Session
        The session object that received the heartbeat.
        
    node_addr : str
        The address of the edge node that sent the heartbeat.
        
    heartbeat : dict
        The heartbeat received from the edge node.        
    """
    node_alias = heartbeat[PAYLOAD_DATA.EE_ID]
    short_addr = self.shorten_address(node_addr)
    cpu = heartbeat[HEARTBEAT_DATA.CPU]
    session.P(f"{node_alias} <{short_addr}> has a {cpu}", color='magenta')
    return



if __name__ == '__main__':
  # create a naive message handler   
  filterer = MessageHandler()
  
  # create a session
  # the network credentials are read from the .env file automatically
  session = Session(
      on_heartbeat=filterer.on_heartbeat,
  )

  session.P("Client address is: {}".format(session.get_client_address()), color='m')
  
  # lets see top 5 online nodes
  netinfo = session.get_network_known_nodes(online_only=True)
  session.P(f"Online nodes reported by {netinfo.reporter}:\n{netinfo.report}")

  session.sleep(10) # wait for 10 seconds
  session.P("Closing session...", color='m')
  session.close()
  session.P("Main thread exiting...", color='m')
