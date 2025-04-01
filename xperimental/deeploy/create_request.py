
import json

from time import time
from copy import deepcopy

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine
from uuid import uuid4



if __name__ == '__main__' :
  l = Logger("ENC", base_folder='.', app_folder='_local_cache')
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        # "PEM_FILE": "aid01.pem",
      }
  )
  
  _time = time()  #- 25 * 3600
  
  hex_time = hex(int(_time * 1000))
  app_name = "app_" + str(uuid4())[:8]
  
  NODES = [
    "0x4bc05c6d0856ea0F437C640B77415e8fCaB09Bd0",    
    "0x4Bb528D985f11e2530ADb3eaB22F4c5AA028Fe13"
  ]
  
  CREATE_REQUEST = {
    "app_name" : app_name,
    "plugin_signature" : "A_SIMPLE_PLUGIN",
    "nonce" : hex_time, # recoverable via int(nonce, 16)
    "target_nodes" : NODES,
    "target_nodes_count" : 0,
    "app_params" : {
      "IMAGE" : "repo/image:tag",
      "CR" : "docker.io",
      "CR_USERNAME" : "user",
      "CR_PASSWORD" : "password",
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
    },
    "pipeline_input_type"  : "ExampleDatastream",
    "pipeline_input_uri" : None,       
  }
  
  GET_APPS_REQUEST = {
    "nonce" : hex_time, # recoverable via int(nonce, 16)    
  }
  
  DELETE_REQUEST = {
    "app_name" : app_name,
    "target_nodes" : NODES,
    "nonce" : hex_time, # recoverable via int(nonce, 16)    
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
    create_request["app_params"].get("CR", ""),
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
  
  delete_request["app_name"] = "app_d526764c"
  
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
    payload=create_request, verbose=True
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
    payload=get_apps_request, verbose=True
  )
  
  delete_sign = eng.eth_sign_message(
    values=delete_values, types=delete_types, 
    payload=delete_request, verbose=True
  )
  
  l.P("Create request nonce {}:\n{}".format(
      l.time_to_str(_time),
      json.dumps({'request':create_request}, indent=2)
    ), color='y'
  )
  
  l.P("Get apps request nonce {}:\n{}".format(
      l.time_to_str(_time),
      json.dumps({'request':get_apps_request}, indent=2)
    ), color='g'
  )
  
  l.P("Delete request nonce {}:\n{}".format(
      l.time_to_str(_time),
      json.dumps({'request':delete_request}, indent=2)
    ), color='m'
  )
  
  
  