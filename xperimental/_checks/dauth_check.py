
import json
from collections import defaultdict


from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine
from ratio1.utils.config import get_user_folder



if __name__ == '__main__' :
  l = Logger("ENC", base_folder='.', app_folder='_local_cache')
  eng = DefaultBlockEngine(
    log=l, name="default", 
    config={
        "PEM_FILE": "aid01.pem",
      }
  )
  
  responders = {}
  
  eng.reset_network("devnet")
  
  for _ in range(1):
    d = eng.dauth_autocomplete(
      # dauth_endp='N/Adhstrgredshtfnfnhgm',
      add_env=False,
      debug=True,
      max_tries=1,
      sender_alias='test1',
      return_full_data=True,      
    )
    try:
      server_alias = d['result']['server_alias']
      server_eth_addr = d['result']['EE_ETH_SENDER']
      server_node_addr = d['server_node_addr']
      auth_len = len(d['result']['auth'])
      if server_node_addr not in responders:
        responders[server_node_addr] = {
          'alias': server_alias, 'count': 0,
          'eth_addr' : server_eth_addr,
          'auth_data' : auth_len,
        }
      responders[server_node_addr]['count'] += 1
    except:
      pass
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
  
  print(f"Responders: {json.dumps(responders, indent=2)}")