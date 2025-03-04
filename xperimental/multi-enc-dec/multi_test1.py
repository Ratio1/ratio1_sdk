import json

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine



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
  
  receivers = [
    DefaultBlockEngine(
      log=l, name=f"test{x}", 
      config={
          "PEM_FILE"     : f"test{x}.pem",
          "PASSWORD"     : None,      
          "PEM_LOCATION" : "data"
        }
    ) for x in range(2, 7)
  ]
  
  
  bandit = DefaultBlockEngine( # bandit
    log=l, name="bandit", 
    config={
        "PEM_FILE"     : "bandit.pem",
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
  enc_data1s = eng1.encrypt(
    plaintext=str_data, 
    receiver_address=receivers[0].address, debug=True
  )
  enc_data1m = eng1.encrypt(
    plaintext=str_data,
    receiver_address=[x.address for x in receivers]
  )
  l.P("Encrypted data size: {}".format(len(enc_data1m)), color='b')
  receivers.append(bandit) # bandit inserts itself into the list of receivers
  single = receivers[0]
  bandit = receivers[-1]
  
  decdata = single.decrypt(
    encrypted_data_b64=enc_data1s, 
    sender_address=eng1.address,
    debug=False,
  )
  if decdata == str_data:
    l.P(f"Data (single) successfully decrypted by {single.name}", color='g')
  else:
    l.P(f"Data (single) decryption failed by {single.name}", color='r')

  decdata = bandit.decrypt(
    encrypted_data_b64=enc_data1s, 
    sender_address=eng1.address,
    debug=False,
  )
  if decdata == str_data:
    l.P(f"Data (single) successfully decrypted by {bandit.name}", color='g')
  else:
    l.P(f"Data (single) decryption failed by {bandit.name}", color='r')
  
  
  for receiver in receivers:
    decdata = receiver.decrypt(
      encrypted_data_b64=enc_data1m, 
      sender_address=eng1.address,
      debug=False,
    )
    if decdata == str_data:
      l.P("Data (multi) successfully decrypted by {}".format(receiver.name), color='g')
    else:
      l.P("Data (multi) decryption failed by {}".format(receiver.name), color='r')
      
