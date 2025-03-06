"""
ex01_part1_connect.py
---------------------
This is a simple example of how to use the ratio1 SDK.

In this example, we connect to the network, listen for heartbeats from 
  ratio1 Edge Protocol edge nodes and print the CPU of each node.
  
  
  
New connection algorithm:

1. The client connects to the network.
2. The client waits for the first 2 supervisors payload with network map. 
3. The client reads `partner_peers` - all nodes that recognize the client as allowed - based on supervisor(s) network map.
4. The client sends a pipeline status to all `partner_peers`.
5. The client then knows the `partner_peers` and can send messages to them.
IMPORTANT: Session will WAIT until network map is clarified.

"""
import json

from ratio1 import Session, Payload, PAYLOAD_DATA, HEARTBEAT_DATA


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
    cpu_load = heartbeat[HEARTBEAT_DATA.CPU_USED]
    mem = heartbeat[HEARTBEAT_DATA.MACHINE_MEMORY]
    mem_avail = heartbeat[HEARTBEAT_DATA.AVAILABLE_MEMORY]
    disk_avail = heartbeat[HEARTBEAT_DATA.AVAILABLE_DISK]
    disk_total = heartbeat[HEARTBEAT_DATA.TOTAL_DISK]
    disk_load = (disk_total - disk_avail) / disk_total * 100
    mem_load = (mem - mem_avail) / mem * 100
    self.hb = heartbeat # simple storage of the last heartbeat
    plugins = heartbeat[HEARTBEAT_DATA.ACTIVE_PLUGINS] or []
    pipelines = heartbeat[HEARTBEAT_DATA.CONFIG_STREAMS] or []
    session.P(
      "<{}> {} {} Load: {:.1f}% CPU, {:.1f}% RAM, {:.1f}% Disk, {} plugins, {} pipelines".format(
        short_addr, node_alias, cpu, cpu_load, mem_load, disk_load, len(plugins), len(pipelines)
      ),
      color='magenta'
    )
    return



if __name__ == '__main__':
  # create a naive message handler   
  filterer = MessageHandler()
  
  # create a session
  # the network credentials are read from the .env file automatically
  session = Session(
      on_heartbeat=filterer.on_heartbeat,
      verbosity=3
  )

  session.P("Client address is: {}".format(session.get_client_address()), color='m')
  
  # lets see top 5 online nodes
  netinfo = session.get_network_known_nodes(online_only=True)
  session.P(f"Online nodes reported by {netinfo.reporter}:\n{netinfo.report}")

  session.sleep(10) # wait for 10 seconds
  session.P("Closing session...", color='m')
  session.close()
  session.P("Main thread exiting...", color='m')
  print(json.dumps(filterer.hb, indent=2))
