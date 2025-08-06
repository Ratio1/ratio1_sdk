from ratio1 import Session, Payload
import json
import time


class PayloadHandler:
  def __init__(self):
    self.processed = False
    self.data = None
  
  def on_data(
    self,
    session: Session, 
    node_addr : str, 
    pipeline_name : str, 
    plugin_signature : str, 
    plugin_instance : str,  
    data : Payload      
  ):
    
    if plugin_signature == 'NET_MON_01':
      session.P(
        f"Data from {pipeline_name} ({plugin_signature}, {plugin_instance}) on {node_addr}: {data}",
        color='g'
      )
      with open('./xperimental/netmon/netmon_data.json', 'wt') as f:
        json.dump(data.data, f, indent=2)
        self.data = data.data
        self.processed = True
        
    

if __name__ == '__main__':
  handler_engine = PayloadHandler()  
  
  sess = Session(
    silent=False,
    verbosity=3,
    on_payload=handler_engine.on_data,
    evm_network='mainnet',  # Specify the EVM network if needed
  )
  
  
  while not handler_engine.processed:
    time.sleep(1)
    
  sess.P("Data processing complete.", color='g')
  
  sess.close()  
  