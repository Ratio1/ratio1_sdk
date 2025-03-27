
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
  
  
  sign = eng.eth_sign_payload(payload=request)
  
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
  
  addr = receiver.eth_check_payload_signature(payload=request)
  valid = addr == known_sender
  l.P(
    f"Received {'valid' if valid else 'invalid'} and expected request from {addr}",
    color='g' if valid else 'r'
  )
  
  