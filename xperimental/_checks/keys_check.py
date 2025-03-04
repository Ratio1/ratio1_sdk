import os

from ratio1 import Logger, const
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")

  
  files = [x for x in os.listdir(l.get_data_folder()) if x.endswith(".pem")]
  
  local_addresses = []  
  results = []
  
  if len(files) > 0:
    l.P("PEM files found: {}".format(files), color='g')
    for pem in files:
      eng = DefaultBlockEngine(
        log=l, name=pem, 
        config={
            "PEM_FILE"     : pem,
            "PASSWORD"     : None,      
            "PEM_LOCATION" : "data"
          }
      )
      local_addresses.append(eng.address)
      results.append("{} - {} - {}".format(eng.address, eng.eth_address, pem))
    l.P("Local addresses:\n{}".format("\n".join(results)), color='g')
  else:
    l.P("No PEM files found.", color='r')
  
  