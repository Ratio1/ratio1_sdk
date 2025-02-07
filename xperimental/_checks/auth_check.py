
import json


from naeural_client import Logger, const
from naeural_client.bc import DefaultBlockEngine
from naeural_client.utils.config import get_user_folder



if __name__ == '__main__' :
  l = Logger(
    "ENC", base_folder=str(get_user_folder()), app_folder="_local_cache",
    # silent=True,
  )
  eng1 = DefaultBlockEngine(
    log=l, name="default", 
    config={
        
      }
  )

  eng2 = DefaultBlockEngine(
    log=l, name="default", 
    config={
        "PEM_FILE": "r03.pem",
      }
  )
  
  to_use = eng2
  
  for _ in range(3):
    d = to_use.dauth_autocomplete(
      # dauth_endp='N/Adhstrgredshtfnfnhgm',
      add_env=False,
      debug=True,
      max_tries=1,
      sender_alias='test1',
    )
    print(f'Got the response: {d} !')
    # try:
    #   res = dict(
    #     name = d['result']['server_alias'],
    #     wl = d['result']['auth']['whitelist'],
    #     pwd = d['result']['auth']['EE_MQTT'],
    #   )
    #   l.P(f"\n\n{json.dumps(res, indent=2)}", show=True)
    # except:
    #   l.P(f"ERROR: {d}", show=True)
    