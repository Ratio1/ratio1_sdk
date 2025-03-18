import os
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  
  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True
  )
  
  eng.reset_network("devnet")
  
  token1 = eng.create_r1_token()
  
  l.P(f"Token1: {token1}")
  
  addr1 = eng.check_r1_token(token1)  
  
  l.P(f"Token1 recovered address: {addr1}")
