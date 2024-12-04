
import json
from copy import deepcopy

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
  
  
  data = {
    "name" : "John",
    "age" : 22,
    "address" : "123 Main St",
    "information"   : {
      "phone" : "123-456-7890",
      "email" : "something@something",
      "history" : [
        {
          "date" : "2020-01-01",
          "event" : "something happened"
        },
        {
          "date" : "2020-01-02",
          "event" : "something else happened"
        }
      ]
    }
  }
  
  TRIALS = 50
  for _ in range(TRIALS):
    _data = deepcopy(data)
    l.start_timer("normal")
    eng1.sign(_data, add_data=True, eth_sign=False)
    l.end_timer("normal")
  
  l.P(json.dumps(_data, indent=2))
  
  for _ in range(TRIALS):
    _data = deepcopy(data)
    l.start_timer("eth")
    eng1.sign(_data, add_data=True, eth_sign=True)
    l.end_timer("eth")
  
  l.P(json.dumps(_data, indent=2))
  
  difference = l.get_timer_mean("eth") - l.get_timer_mean("normal")  
  l.P(f"Difference: {difference:.4f} sec")
  l.show_timers()
  
  l.P(eng2.verify(_data, return_full_info=True))
  
  
