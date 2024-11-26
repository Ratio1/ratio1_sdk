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
    "test": "data1 data2 data3 data4 data5 data6 data7 data8 data9 data10",
    "test2": "data21 data22 data23 data24 data25 data26 data27 data28 data29 data210",
    "test3": "data31 data32 data33 data34 data35 data36 data37 data38 data39 data310",
    "test4" : {
      "test5": "data5 data6 data7 data8 data9 data10 data11 data12 data13 data14",
      "test6": "data6 data7 data8 data9 data10 data11 data12 data13 data14 data15",
      "test7": [
        "data7",
        {
          "test9": "data91 data92 data93 data94 data95 data96 data97 data98 data99 data910",
          "test10": "data10 data11 data12 data13 data14 data15 data16 data17 data18 data19 data110",
        }
      ]
    }
  }
  
  l.P("Non compressed test", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address, compressed=False, embed_compressed=False)
  l.P(f"Encrypted data (size: {len(encdata)}): {encdata}")  
  decdata = eng2.decrypt(encrypted_data_b64=encdata, sender_address=eng1.address, decompress=False, embed_compressed=False) 
  l.P(f"Decrypted data:\n {json.dumps(json.loads(decdata), indent=2)}")
  
  l.P("Compressed test", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address, compressed=True, embed_compressed=False)
  l.P(f"Encrypted data (size: {len(encdata)}): {encdata}")  
  decdata = eng2.decrypt(encrypted_data_b64=encdata, sender_address=eng1.address, decompress=True, embed_compressed=False)
  l.P(f"Decrypted data:\n {json.dumps(json.loads(decdata), indent=2)}")  
  
  l.P("Compressed test with embed", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address, compressed=True, embed_compressed=True)
  l.P(f"Encrypted data (size: {len(encdata)}): {encdata}")  
  decdata = eng2.decrypt(encrypted_data_b64=encdata, sender_address=eng1.address, embed_compressed=True) # decompress does not matter
  l.P(f"Decrypted data:\n {json.dumps(json.loads(decdata), indent=2)}")    
  
  l.P("Default test", color='g')  
  str_data = json.dumps(data)
  l.P(f"Data size: {len(str_data)}")  
  encdata = eng1.encrypt(plaintext=str_data, receiver_address=eng2.address)
  l.P(f"Encrypted data (size: {len(encdata)}): {encdata}")  
  decdata = eng2.decrypt(encrypted_data_b64=encdata, sender_address=eng1.address)
  l.P(f"Decrypted data:\n {json.dumps(json.loads(decdata), indent=2)}")      