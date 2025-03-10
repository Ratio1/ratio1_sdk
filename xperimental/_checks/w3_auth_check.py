import os
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine
from ratio1.utils.config import get_user_folder



if __name__ == '__main__' :
  
  
  l = Logger("ENC")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    user_config=True
  )
  
  eng.reset_network("devnet")
  
  addresses = [
    "0xE486F0d594e9F26931fC10c29E6409AEBb7b5144",
    "0x93B04EF1152D81A0847C2272860a8a5C70280E14",  
    "0x369C7dfc6484528A472897Cae6A98EB05c49c122",
    "0x37379B80c7657620E5631832c4437B51D67A88cB"
  ]
  
  l.P(f"Checking web3 API on {eng.evm_network}", color='b')
  
  for addr in addresses:
    is_active = eng.web3_is_node_licensed(
      address=addr, debug=True
    )
    l.P("{} {}".format(
        addr,
        "has a license" if is_active else f"does NOT have a license on {eng.evm_network}"
      ), 
      color='g' if is_active else 'r'
    )
    
  oracles = eng.web3_get_oracles(debug=True)
  l.P("\nOracles:\n {}".format(json.dumps(oracles, indent=2)), 
    color='b'
  )
  
  supervisors = [
    "0xai_AleLPKqUHV-iPc-76-rUvDkRWW4dFMIGKW1xFVcy65nH",
    "0xai_A-Bn9grkqH1GUMTZUqHNzpX5DA6PqducH9_JKAlBx6YL",
    "0xai_AmT2Tz230aZtNFh3ruOr7rN3KHuAcByOEPmZ-Qa8Km4A"
  ]
  
  for supervisor in supervisors:
    is_supervisor_allowed = eng.is_node_address_in_eth_addresses(
      node_address=supervisor, lst_eth_addrs=oracles
    )
    l.P("Node {} {}".format(
        supervisor,
        "is supervisor" if is_supervisor_allowed else "is NOT supervisor"
      ), 
      color='g' if is_supervisor_allowed else 'r'
    )
 
    