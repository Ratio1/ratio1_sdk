
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, name="test1", 
    config={
        "PEM_FILE"     : "test1.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  eng2 = DefaultBlockEngine(
    log=l, name="test2", 
    config={
        "PEM_FILE"     : "test2.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
    
  l.P(eng1.eth_address)
  l.P(eng1.eth_account.address)
  l.P(eng1.eth_address == eng1.eth_account.address)

  private_key = eng1.eth_account.key


  dct_message = {
    "node": "0xai_Amfnbt3N-qg2-qGtywZIPQBTVlAnoADVRmSAsdDhlQ-6",
    "epochs_vals": { "245": 124, "246": 37, "247": 30,"248": 6, "249": 19,"250": 4,}, # epochs ommited for brevity
  }
  
  types = ["string", "uint256[]", "uint8[]"]
  epochs = sorted(list(dct_message["epochs_vals"].keys()))
  epochs_vals = [dct_message["epochs_vals"][epoch] for epoch in epochs]
  epochs = [int(epoch) for epoch in epochs]
  values = [dct_message["node"], epochs, epochs_vals]
  
  # hash1 = eng1.eth_sign_message(types, values)
  
  from web3 import Web3
  from eth_account import Account
  from eth_account.messages import encode_defunct
  
  message_hash = Web3.solidity_keccak(types, values)
  signable_message = encode_defunct(primitive=message_hash)
  signed_message = Account.sign_message(signable_message, private_key=private_key)
  
  
  
  
  
  
  
  
  
  