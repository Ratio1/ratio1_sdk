
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine
from naeural_client.utils.config import get_user_folder



if __name__ == '__main__' :
  l = Logger(
    "ENC", base_folder=str(get_user_folder()), 
    app_folder="_local_cache"
  )
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={        
      }
  )
  
  epochs = [
    1,2,3
  ]
  
  values = [
    10, 20, 30
  ]
  
  
  sign = eng.eth_sign_node_epochs(
    node=eng.eth_address, 
    epochs=epochs, 
    epochs_vals=values,
    signature_only=False,
  )
  
  l.P(f"Signature {sign}")