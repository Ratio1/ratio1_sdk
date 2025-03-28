
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
  
  CREATE_REQUEST = {
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
  
  GET_APPS_REQUEST = {
    "nonce" : hex(int(time() * 1000)), # recoverable via int(nonce, 16)    
  }
  
  DELETE_REQUEST = {
    "app_name" : "SOME_APP_NAME",
    "target_nodes" : [
      "0xai_node_1",
        "0xai_node_2",
    ],
    "nonce" : hex(int(time() * 1000)), # recoverable via int(nonce, 16)    
  }  
  
  
  create_request = deepcopy(CREATE_REQUEST)
  get_apps_request = deepcopy(GET_APPS_REQUEST)
  delete_request = deepcopy(DELETE_REQUEST)
  
  create_values = [
    create_request["app_name"],
    create_request["plugin_signature"],
    create_request["nonce"],
    create_request["target_nodes"],
    create_request["target_nodes_count"],
    create_request["app_params"].get("IMAGE",""),
    create_request["app_params"].get("REGISTRY", ""),
  ]
  
  create_types = [
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_ARRAY_STR,
    eng.eth_types.ETH_INT,
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_STR,    
  ]
  
  get_apps_values  = [
    get_apps_request["nonce"],
  ]
  
  get_apps_types  = [
    eng.eth_types.ETH_STR,
  ]
  
  delete_values = [
    delete_request["app_name"],
    delete_request["target_nodes"],
    delete_request["nonce"],
  ]
  
  delete_types = [
    eng.eth_types.ETH_STR,
    eng.eth_types.ETH_ARRAY_STR,
    eng.eth_types.ETH_STR,
  ]
  
  # Now the sign-and-check process
  
  sign = eng.eth_sign_message(
    values=create_values, types=create_types, 
    payload=create_request
  )
  
  l.P(f"Result:\n{json.dumps(create_request, indent=2)}")
  l.P(f"Signature:\n{sign}")
  known_sender = eng.eth_address
  
  receiver = DefaultBlockEngine(
    log=l, name="test", 
    config={
        "PEM_FILE"     : "test.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  addr = receiver.eth_verify_message_signature(
    values=create_values, types=create_types, 
    signature=create_request[const.BASE_CT.BCctbase.ETH_SIGN]
  )
  valid = addr == known_sender
  l.P(
    f"Received {'valid' if valid else 'invalid'} and expected request from {addr}",
    color='g' if valid else 'r'
  )
  
  # get-apps and delete
  
  get_apps_sign = eng.eth_sign_message(
    values=get_apps_values, types=get_apps_types, 
    payload=get_apps_request
  )
  
  delete_sign = eng.eth_sign_message(
    values=delete_values, types=delete_types, 
    payload=delete_request
  )
  
  l.P("REQUESTS:\nCreate request:\n{}\nGet apps request:\n{}\nDelete request:\n{}".format(
    json.dumps(create_request, indent=2),
    json.dumps(get_apps_request, indent=2),
    json.dumps(delete_request, indent=2)
  ))
  
  
  