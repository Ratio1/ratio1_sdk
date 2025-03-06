"""
ex01_part3_adv_filter.py
---------------------
This is a simple example of how to use the ratio1 SDK.

In this example:
  - we connect to the network
  - listen for heartbeats from ratio1 Edge Protocol edge nodes and print the CPU of each node.
  - listen for payloads from ratio1 Edge Protocol edge nodes and print the data of each payload.
"""
import json

from ratio1 import Session, Payload, PAYLOAD_DATA, HEARTBEAT_DATA


class MessageHandler:
  def __init__(self, signature_filter: str = None):
    """
    This class is used to handle the messages received from the edge nodes.
    
    In this class we are defining two callback methods:
      - on_heartbeat: this method is called when a heartbeat is received from an edge node.
      - on_data: this method is called when a payload is received from an edge node.
    """
    if isinstance(signature_filter, str):
      self.signature_filter = [signature_filter.upper()]
    elif isinstance(signature_filter, list):
      self.signature_filter = [sig.upper() for sig in signature_filter]
    else:
      raise ValueError("signature_filter must be a string or a list of strings")
    self.last_data = None # some variable to store the last data received for debugging purposes
    self.last_payload = None # some variable to store the last payload received for debugging purposes
    return
  
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
    whitelist = heartbeat.get(HEARTBEAT_DATA.EE_WHITELIST, [])
    alias = heartbeat.get(HEARTBEAT_DATA.EE_ID)
    cpu = heartbeat.get(HEARTBEAT_DATA.CPU)
    # DELETE:
    allows_me = session.bc_engine.contains_current_address(whitelist)
    # END DELETE
    session.P(
      "{} <{}> {} has {} and allows:\n{}".format(
        alias, self.shorten_address(node_addr), 
        "allows me" if allows_me else "does NOT allow me",
        cpu, json.dumps(whitelist, indent=2)),
      color='b' if allows_me else 'r',
    )
    return

  def on_data(
    self,
    session: Session, 
    node_addr : str, 
    pipeline_name : str, 
    plugin_signature : str, 
    plugin_instance : str,  
    payload : Payload      
  ):
    """
    This method is called when a payload is received from an edge node.
    
    Parameters
    ----------
    
    session : Session
        The session object that received the payload.
        
    node_addr : str
        The address of the edge node that sent the payload.
        
    pipeline_name : str
        The name of the pipeline that sent the payload.
        
    plugin_signature : str
        The signature of the plugin that sent the payload.
        
    plugin_instance : str
        The instance of the plugin that sent the payload.
        
    payload : Payload
        The payload received from the edge node.      
    """
    addr = self.shorten_address(node_addr)
    
    if plugin_signature.upper() not in self.signature_filter:
      # we are not interested in this data but we still want to log it
      message = "Recv from <{}::{}::{}::{}>".format(
        addr, pipeline_name, plugin_signature, plugin_instance
      )
      color = 'dark'
    else:
      self.last_payload = payload # save the full payload for debugging purposes
      # we can also access the "payload path" that matches 
      # the node-alias, pipeline_name, plugin_signature, and plugin_instance
      path = payload.EE_PAYLOAD_PATH 
      # we extract the data from the payload to check for online nodes considering
      # that we are waiting for NET_MON_01 payloads      
      # now we do some low-level processing of the data
      network_map = payload.data.get(PAYLOAD_DATA.NETMON_CURRENT_NETWORK, {})
      all_nodes = list(network_map.keys())
      online_nodes = [
        n for n in all_nodes 
        if network_map[n][PAYLOAD_DATA.NETMON_STATUS_KEY] == PAYLOAD_DATA.NETMON_STATUS_ONLINE
      ]
      whitelists = {
        k : v.get(PAYLOAD_DATA.NETMON_WHITELIST, []) for k, v in network_map.items()
      }
      message = f"{path[0]} Reports {len(online_nodes)} online nodes of {len(all_nodes)} known nodes. Whitelists with {len(whitelists)} peers"
      color = 'g'
    session.P(message, color=color, show=True)  #, noprefix=True)
    return


if __name__ == '__main__':
  # create a naive message handler for network monitoring public messages
  filterer = MessageHandler("NET_MON_01")
  
  # create a session
  # the network credentials are read from the .env file automatically
  session = Session(
      on_heartbeat=filterer.on_heartbeat,
      on_payload=filterer.on_data,
      # silent=True,
      debug=True,
  )

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close 
  #   after the pipeline will be sent 
  session.wait(
    seconds=20,            # we wait the session for 60 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )
  session.P("Main thread exiting...")
  
  netinfo = session.get_network_known_nodes()  
  print(f"Last NET_MON_01 received:\n{json.dumps(filterer.last_payload.data, indent=2)}")
  print(f"Payload size: {len(json.dumps(filterer.last_payload.data))} bytes")
  print(f"Supervisor <{netinfo.reporter}> '{netinfo.reporter_alias}' ({netinfo.nr_super} supervisors total) reports:\n{netinfo.report}")
