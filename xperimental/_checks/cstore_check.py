import requests
import json
import pandas as pd

if __name__ == "__main__":

  CHECK_STATUS = False
  CHECK_VALUE  = True

  if CHECK_STATUS:
    N = 4

    # the provided url, note: if this does not return json directly, it might need adjustment
    url_status = "https://cstore-ratio1.ngrok.app/get_status"
    server_alias_counts = {}

    for i in range(N):
      try:
        response = requests.get(url_status)
        response.raise_for_status()
        data = response.json()
      except Exception as e:
        print(f"error occurred during request {i+1}: {e}, response: {response.text}")
        continue

      # extract nodes data from the json response
      result = data.get("result", {})
      server_alias = result.get("server_alias")
      ver = result.get("server_version")
      if server_alias:
        server_alias_counts[server_alias] = server_alias_counts.get(server_alias, 0) + 1
      keys = result.get("keys", {})
      # create and display the pand
      print(f"Response #{i+1} from {server_alias} v{ver} with {len(keys)} keys")
      # update the server_alias counts

    print("\nserver_alias counts: {server_alias_counts}\n\n")
    
  if CHECK_VALUE:
    N = 2    
    KEY_TO_CHECK = "K3-nen-aid03-2fb8"

    # the provided url, note: if this does not return json directly, it might need adjustment
    url_value = "https://cstore-ratio1.ngrok.app/get_value"
    server_alias_counts = {}

    bearer_token = "admin"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    
    params = {"cstore_key": KEY_TO_CHECK}

    for i in range(N):
      try:
        response = requests.get(url_value, headers=headers, params=params)        
        response.raise_for_status()
        data = response.json()
      except Exception as e:
        print(f"error occurred during request {i+1}: {e}, response: {response.text}")
        continue

      # extract nodes data from the json response
      result = data.get("result", {})
      server_alias = result.get("server_alias")
      ver = result.get("server_version")
      if server_alias:
        server_alias_counts[server_alias] = server_alias_counts.get(server_alias, 0) + 1      
      # create and display the pand
      print(f"Response #{i+1} from {server_alias} v{ver}: {result}")
      # update the server_alias counts

    print("\nserver_alias counts:", server_alias_counts)
