import json
from copy import deepcopy


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  
  _DATA = {
    "9": 9,
    "2": 2,
    "3": 3,
    "10": {
      "2": 2,
      "100": 100,
      "1": 1
    },
    
  }
  
  PYTHON_MESSAGE = {
    **_DATA,
    "EE_SIGN": "MEQCIEIz_Nfy9CJ0GYW1V7Iw0uFJAVzu1TnOWkCVYnrt8PNHAiB0JCk_pgzGGIMz-KIvOCC_BzbGB8jxkAb_OwPX7AQTyA==",
    "EE_SENDER": "0xai_AuN2SENcYNzRgbPUHVCFe6W1q-vieUKap2VY9mU_Fljy",
    "EE_HASH": "7d72cf5bd6cda16c86dfb2c2c4983464edda5bf78e1ca3a21139f5037454c6f3"
  }
   
  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )

  eng2_noneth = DefaultBlockEngine(
    eth_enabled=False,
    log=l, name="test1", 
    config={
        "PEM_FILE"     : "test1.pem",
        "PASSWORD"     : None,      
        "PEM_,LOCATION" : "data"
      }    
  )

  eng3_eth = DefaultBlockEngine(
    eth_enabled=True,
    log=l, name="test2", 
    config={
        "PEM_FILE"     : "test2.pem",
        "PASSWORD"     : None,      
        "PEM_,LOCATION" : "data"
      }    
  )
  
  v1 = eng1.verify(PYTHON_MESSAGE)
  l.P(f"check 1: {v1}", color='r' if not v1.valid else 'g')
  
  data = deepcopy(_DATA)
  eng1.sign(data)
  l.P(f"data: {data}")
  
  v2 = eng2_noneth.verify(data)
  l.P(f"check 2.1: {v2}", color='r' if not v2.valid else 'g')
  eng2_noneth.set_eth_flag(True)
  v2 = eng2_noneth.verify(data)
  l.P(f"check 2.2: {v2}", color='r' if not v2.valid else 'g')
  eng2_noneth.set_eth_flag(False)
  
  v3 = eng3_eth.verify(data)
  l.P(f"check 3: {v3}", color='r' if not v3.valid else 'g')  
  
  
  data_noneth = deepcopy(_DATA)
  eng2_noneth.sign(data_noneth)
  l.P(f"data: {data_noneth}")
  
  v4 = eng1.verify(data_noneth)
  l.P(f"check 4: {v4}", color='r' if not v4.valid else 'g')
  
  v5 = eng3_eth.verify(data_noneth)
  l.P(f"check 5: {v5}", color='r' if not v5.valid else 'g')