
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        
      }
  )
  
  network = 'testnet'
  addresses = [
    "0x93B04EF1152D81A0847C2272860a8a5C70280E14",
    "0x1Fe3222f6a2844364E2BDc796e0Df547ea26B815",    
    
    "0x99Ac885B00a150cFc93EA1A51FcC035C17aCB02c",
    "0x49943d72CF93B69AE22c7194093804635a99eF2B",
    "0x64A4C148FDa4a0D900daB9417cd65968993d30b3",
    "0x4B50d4ac46c3ba0F463603587d41c67213A0a091",

    
    "0x1351504af17BFdb80491D9223d6Bcb6BB964DCeD",
    "0x2539fDD57f93b267E58d5f2E6F77063C0230F6F4",
        
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
    "0xai_AwxGtRVqRlUrUoZNvf827uOswFmCkFXXguRmkpnyJBhQ",
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
 
    