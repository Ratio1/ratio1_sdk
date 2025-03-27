
import json

from time import time
from copy import deepcopy

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder='.', app_folder='_local_cache')
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        # "PEM_FILE": "aid01.pem",
      }
  )
  
  REQUEST = {
    "app_name" : "SOME_APP_NAME", 
    "plugin_signature" : "SOME_PLUGIN_01",
    "nonce" : hex(int(time() * 1000)), # recoverable via int(nonce, 16)
    "target_nodes" : [
      "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",
      "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-7",
    ],
    "target_nodes_count" : 0,
    "app_params" : {
      "IMAGE" : "repo/image:tag",
      "REGISTRY" : "docker.io",
      "USERNAME" : "user",
      "PASSWORD" : "password",
      "PORT" : 5000,
      "OTHER_PARAM1" : "value1",
      "OTHER_PARAM2" : "value2",
      "OTHER_PARAM3" : "value3",
      "OTHER_PARAM4" : "value4",
      "OTHER_PARAM5" : "value5",
      "ENV" : {
        "ENV1" : "value1",
        "ENV2" : "value2",
        "ENV3" : "value3",
        "ENV4" : "value4",
      }
    }    
  }
  
  request = deepcopy(REQUEST)
  
  values = [
    request["app_name"],
    request["plugin_signature"],
    request["nonce"],
    request["target_nodes"],
    request["target_nodes_count"],
    request["app_params"].get("IMAGE",""),
    request["app_params"].get("REGISTRY", ""),
  ]
  
  types = [
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_ARRAY_STR,
    eng.eth_types.ETH_INT,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,    
  ]
  
  sign = eng.eth_sign_message(values=values, types=types, payload=request)
  
  l.P(f"Result:\n{json.dumps(request, indent=2)}")
  l.P(f"Signature:\n{sign}")
  known_sender = eng.eth_address
  
  receiver = DefaultBlockEngine(
    log=l, name="default", 
    config={
        "PEM_FILE"     : "test.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  addr = receiver.eth_verify_message_signature(
    values=values, types=types, signature=request[const.BASE_CT.BCctbase.ETH_SIGN]
  )
  valid = addr == known_sender
  l.P(
    f"Received {'valid' if valid else 'invalid'} and expected request from {addr}",
    color='g' if valid else 'r'
  )
  
  