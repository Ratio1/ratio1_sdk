
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
  
  MSG_FROM_JSON = {"app_name":"app_40b23285","app_params":{"CR":"docker.io","CR_PASSWORD":"password","CR_USERNAME":"user","ENV":{"ENV1":"value1","ENV2":"value2","ENV3":"value3","ENV4":"value4"},"IMAGE":"repo/image:tag","OTHER_PARAM1":"value1","OTHER_PARAM2":"value2","OTHER_PARAM3":"value3","OTHER_PARAM4":"value4","OTHER_PARAM5":"value5","PORT":5000},"nonce":"0x195f1a86832","pipeline_input_type":"void","plugin_signature":"SOME_PLUGIN_01","target_nodes":["0xai_node_1","0xai_node_2"],"target_nodes_count":0,"EE_ETH_SIGN":"0x1048b65139affe77dffa59fbe7fd9586c0984fc73b235c7526140c87b2363b6609c0d5ed291ce6bb61756502129df704d5872dd7624ac59b7452a95dbe1a8fdf1b","EE_ETH_SENDER":"0xe558740ffc65bc73f6efb07c26c8d587ee22d297"}


  
  
  payload = deepcopy(MSG_FROM_JSON)
  sender = payload.get("EE_ETH_SENDER")

  addr = eng.eth_verify_payload_signature(
    payload=payload, message_prefix=TEXT,
    no_hash=True, indent=1,
  )
  valid = addr.upper() == sender.upper()
  if valid:
    l.P(f"Signature valid: {valid}, addr: {addr}")
  else:
    l.P(f"Signature invalid: {valid}, recovered: {addr} != {sender}")
