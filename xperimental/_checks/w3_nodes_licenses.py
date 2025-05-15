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
  
  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True,verbosity=10,
  )

  for network in NETWORKS:  
    eng.reset_network(network)

    oracles = eng.web3_get_oracles(debug=True)
    l.P("\nOracles for {}:\n {}".format(
        network, json.dumps(oracles, indent=2)
      ), 
      color='b', show=True
    )  
  
    NODE = "0xED5BE902866855caabF1Acb558209FC40E62524A"
    
    info = eng.web3_get_node_info(node_address=NODE)
    l.P(f"Node info for {NODE}:\n{json.dumps(info, indent=2)}", color='m')
    
    WALLET = "0x464579c1Dc584361e63548d2024c2db4463EdE48"
    try:
      nodes = eng.web3_get_wallet_nodes(address=WALLET)
      l.P(f"Nodes for {WALLET} ({len(nodes)}):")
      for n in nodes:
        if n in oracles:
          l.P(f"  {n} (oracle)", color='g')
        else:
          l.P(f"  {n}")
    except Exception as e:
      l.P(f"Error getting nodes for {WALLET}: {e}", color='r')
  
  
  
