
import json

from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder='.', app_folder='_local_cache')
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        # "PEM_FILE": "aid01.pem",
      }
  )
  
  TEXT = "a"
  
  sign = "0x1000cef4193c06b53feadb52c1fad1563f78690e19be38dbc91a9ed42d1ef2db29f1e47e7f25c820331b41bdff479812a156f076a5b9e766b40d2efc6ff17e391b"
  
  vals = [TEXT]  
  types = [eng.eth_types.ETH_STR]
  
  addr = eng.eth_verify_message_signature(
    values=vals, types=types, 
    signature=sign
  )
  l.P(f"{addr}")
