import os
import json


from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  
  NETWORKS = [
    "mainnet",
    "testnet",
    "devnet",
  ]
  
  network = NETWORKS[2]

  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True
  )
  
  eng.reset_network(network)

  oracles = eng.web3_get_oracles(debug=True)
  l.P("\nOracles for {}:\n {}".format(
      network, json.dumps(oracles, indent=2)
    ), 
    color='b', show=True
  )
  
  eng.reset_network("devnet")
  
  NODE = "0xED5BE902866855caabF1Acb558209FC40E62524A"
  
  info = eng.web3_get_node_info(node_address=NODE)
  l.P(f"Node info for {NODE}:\n{json.dumps(info, indent=2)}", color='m')
  
  WALLET = "0x464579c1Dc584361e63548d2024c2db4463EdE48"
  
  nodes = eng.web3_get_wallet_nodes(address=WALLET)
  l.P(f"Nodes for {WALLET}:")
  for n in nodes:
    if n in oracles:
      l.P(f"  {n} (oracle)", color='g')
    else:
      l.P(f"  {n}")
  
  
  
