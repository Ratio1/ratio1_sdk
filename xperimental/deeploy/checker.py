
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
  
  TEXT = "Please sign this message for Deeploy: "
  
  MSG_FROM_JSON =  {"plugin_signature":"SOME_PLUGIN_01","app_name":"app_40b23285","nonce":"0x195f1a86832","target_nodes":["0xai_node_1","0xai_node_2"],"target_nodes_count":0,"app_params":{"CR":"docker.io","CR_PASSWORD":"password","CR_USERNAME":"user","ENV":{"ENV1":"value1","ENV2":"value2","ENV3":"value3","ENV4":"value4"},"IMAGE":"repo/image:tag","OTHER_PARAM1":"value1","OTHER_PARAM2":"value2","OTHER_PARAM3":"value3","OTHER_PARAM4":"value4","OTHER_PARAM5":"value5","PORT":5000},"pipeline_input_type":"void","EE_ETH_SIGN":"0x6bace1de9fc50df081b1ed7dc5c0b5437ad3db2efe46acdcf5c4b93046b1e0b8340af28217eb47bb1c4a62ab8a626516d1d7d0c4a159278754188901419b49601b","EE_ETH_SENDER":"0xE558740FFc65bc73f6EfB07C26C8D587EE22d297"}
  
  sender = MSG_FROM_JSON.pop("EE_ETH_SENDER")
  sign = MSG_FROM_JSON.pop("EE_ETH_SIGN")
  
  str_json = eng.safe_dict_to_json(MSG_FROM_JSON, indent=1)
  l.P(f"Input from {sender}:\n{str_json}")
  
  vals = [TEXT + str_json]  
  types = [eng.eth_types.ETH_STR]
  
  l.P(f"Message to check:\n{vals[0]}")

  addr = eng.eth_verify_message_signature(
    values=vals, types=types, 
    signature=sign
  )
  valid = addr == sender
  if valid:
    l.P(f"Signature valid: {valid}, addr: {addr}")
  else:
    l.P(f"Signature invalid: {valid}, recovered: {addr} != {sender}")
