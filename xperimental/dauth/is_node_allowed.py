
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine
from naeural_client.utils.config import get_user_folder



if __name__ == '__main__' :
  l = Logger(
    "ENC", base_folder=str(get_user_folder()), 
    app_folder="_local_cache"
  )
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        
      }
  )
  
  network = 'mainnet'
  addresses = [
    "0xe240d9cf8893d6bE9fb3Ac4C9CE1E504343b64a0",
    "0x1Fe3222f6a2844364E2BDc796e0Df547ea26B815",    
    "0x7C07758C23DF14c2fF4b016F0ad58F2D4aF329a7",        
  ]
  
  for addr in addresses:
    is_active = eng.web3_is_node_licensed(
      address=addr, network=network
    )
    l.P("{} {}".format(
        addr,
        "has a license" if is_active else "does NOT have a license"
      ), 
      color='g' if is_active else 'r'
    )
    
  oracles = eng.web3_get_oracles(network=network)
  l.P("\nOracles:\n {}".format(json.dumps(oracles, indent=2)), 
    color='b'
  )
  
  supervisors = [
    "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",
    "0xai_Aj1FpPQHISEBelp-tQ8cegwk434Dcl6xaHmuhZQT74if",
    "0xai_A4cZdKZZdj9We5W7T-NJPdQuhH2c8-aMI3-r7XlT0jqn",
    "0xai_AvuUcmXyn6U3z8XRagqG8_d2sKCDZ5FIDpkUlpUz3Iuh"
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
 
    