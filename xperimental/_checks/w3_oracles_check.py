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

  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True
  )
  
  for network in NETWORKS:
    eng.reset_network(network)

    oracles = eng.web3_get_oracles(debug=True)
    l.P("\nOracles for {}:\n {}".format(
        network, json.dumps(oracles, indent=2)
      ), 
      color='b', show=True
    )
