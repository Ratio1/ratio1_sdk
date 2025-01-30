
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine



if __name__ == '__main__' :
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, name="default", 
    config={
        
      }
  )
  
  for _ in range(2):
    d = eng1.dauth_autocomplete(
      add_env=False,
      debug=True,
      max_tries=1,
      sender_alias='test1',
    )
    
    l.P(f"Result: {json.dumps(d, indent=2)}", color='b')  