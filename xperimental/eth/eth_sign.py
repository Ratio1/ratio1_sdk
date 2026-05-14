
import json


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, name="default", 
  )
  eng2 = DefaultBlockEngine(
    log=l, name="test2", 
    config={
        "PEM_FILE"     : "test.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
    
  l.P(eng1.eth_address)
  l.P(eng1.eth_account.address)
  l.P(eng1.eth_address == eng1.eth_account.address)

  private_key = eng1.eth_account.key


   
  node = "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6"
  node_eth = eng1.node_address_to_eth_address(node)
  l.P("Node: {}\nNode Eth: {}".format(node, node_eth))
  epochs = [245, 246, 247, 248, 249, 250]
  epochs_vals = [124, 37, 30, 6, 19, 4]
  from_epoch, to_epoch = eng1.validate_epoch_availability_range(epochs, epochs_vals)
  packed_availabilities = eng1.pack_epoch_availabilities(epochs_vals)
  USE_ETH_ADDR = True
  
  if USE_ETH_ADDR:  
    types = ["address", "uint256", "uint256", "bytes"]
    node_data = node_eth
  else:
    types = ["string", "uint256", "uint256", "bytes"]
    node_data = node
    
  values = [node_data, from_epoch, to_epoch, packed_availabilities]
  
 
  s2 = eng1.eth_sign_message(types, values)
  l.P("Results:\n{}".format(json.dumps(s2, indent=2)))
  
  res = eng1.eth_sign_node_epochs(node_data, epochs, epochs_vals, signature_only=False, use_evm_node_addr=USE_ETH_ADDR)
  eth_signature = res["signature"]
  inputs = res["eth_signed_data"]
  l.P(f"Results:\n  Signature: {eth_signature}\n  Inputs: {inputs}")
  
  # check if the signature is valid
  invalid_packed_availabilities = eng2.pack_epoch_availabilities(
    [124, 37, 30, 6, 19, 1]
  )
  sender = eng2.eth_check_signature(
    values=[node_data, from_epoch, to_epoch, invalid_packed_availabilities],
    types=types,
    signature=eth_signature,
  )
  valid = sender == eng1.eth_address
  l.P(f"Signature from {sender} {'valid' if valid else 'invalid'}", color='g' if valid else 'r')
  
  sender = eng2.eth_check_signature(
    values=values,
    types=types,
    signature=eth_signature,
  )
  valid = sender == eng1.eth_address
  l.P(f"Signature from {sender} {'valid' if valid else 'invalid'}", color='g' if valid else 'r')
