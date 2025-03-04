import os
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine
from ratio1.utils.config import get_user_folder



if __name__ == '__main__' :
  
  NETWORKS = [
    "mainnet",
    "testnet",
    "devnet",
  ]
  
  for network in NETWORKS:
    os.environ["EE_EVM_NET"] = network
    
    l = Logger(
      "ENC", base_folder=str(get_user_folder()), 
      app_folder="_local_cache",
      silent=True,
    )
    eng = DefaultBlockEngine(
      log=l, name="default", 
    )
      
    oracles = eng.web3_get_oracles(debug=True)
    l.P("\nOracles for {}:\n {}".format(network, json.dumps(oracles, indent=2)), 
      color='b', show=True
    )
