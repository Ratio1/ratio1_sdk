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
  
  data = {
    "test1" : " ".join([f"data1-{x}" for x in range(1, 1000)]),
    "test2" : [f"data2-{x}" for x in range(1, 1000)],
  }   
  
  l.P("Non compressed test", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1._encrypt(plaintext=str_data, receiver_address=eng2.address, compressed=False, embed_compressed=False)
  l.P(f"Encrypted data (size: {len(encdata)})")  
  decdata = eng2._decrypt(encrypted_data_b64=encdata, sender_address=eng1.address, decompress=False, embed_compressed=False) 
  if decdata == str_data:
    l.P("Decrypted data matches original data", color='g')
  else:
    l.P("Decrypted data does not match original data", color='r')
  
  l.P("Compressed test", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address)
  l.P(f"Encrypted data (size: {len(encdata)})")  
  decdata = eng2.decrypt(encrypted_data_b64=encdata, sender_address=eng1.address)
  if decdata == str_data:
    l.P("Decrypted data matches original data", color='g')
  else:
    l.P("Decrypted data does not match original data", color='r')
