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

  eng3 = DefaultBlockEngine(
    log=l, name="test3", 
    config={
        "PEM_FILE"     : "test3.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  eng4 = DefaultBlockEngine( # bandit
    log=l, name="test4", 
    config={
        "PEM_FILE"     : "test4.pem",
        "PASSWORD"     : None,      
        "PEM_LOCATION" : "data"
      }
  )
  
  data = {
    "test1" : " ".join([f"data1-{x}" for x in range(1, 1000)]),
    "test2" : [f"data2-{x}" for x in range(1, 1000)],
  }   
   
  str_data = json.dumps(data)
  l.P("Data size: {}".format(len(str_data)), color='b')
  enc_data1s = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address)
  enc_data1m = eng1.encrypt_for_multi(
    plaintext=str_data,
    receiver_addresses=[eng2.address, eng3.address]
  )
  l.P("Encrypted data size: {}".format(len(enc_data1m)), color='b')
  
  decdata2 = eng2.decrypt(encrypted_data_b64=enc_data1m, sender_address=eng1.address)
  if decdata2 == str_data:
    l.P("Data (multi) successfully decrypted by eng2", color='g')
  else:
    l.P("Data (multi) decryption failed by eng2", color='r')
    
  decdata2s = eng2.decrypt(encrypted_data_b64=enc_data1s, sender_address=eng1.address)
  if decdata2s == str_data:
    l.P("Data (single) successfully decrypted by eng2", color='g')
  else:
    l.P("Data (single) decryption failed by eng2", color='r')
    
  decdata3 = eng3.decrypt(encrypted_data_b64=enc_data1m, sender_address=eng1.address)
  if decdata3 == str_data:
    l.P("Data (multi) successfully decrypted by eng3", color='g')
  else:
    l.P("Data (multi) decryption failed by eng3", color='r')
    
  decdata4 = eng4.decrypt(encrypted_data_b64=enc_data1m, sender_address=eng1.address, debug=True)
  if decdata4 == str_data:
    l.P("Data (multi) successfully decrypted by eng4", color='g')
  else:
    l.P("Data (multi) decryption failed by eng4", color='r')
  
  decdata4s = eng4.decrypt(encrypted_data_b64=enc_data1s, sender_address=eng1.address, debug=True)
  if decdata4s == str_data:
    l.P("Data (single) successfully decrypted by eng4", color='g')
  else:
    l.P("Data (single) decryption failed by eng4", color='r')
    
  