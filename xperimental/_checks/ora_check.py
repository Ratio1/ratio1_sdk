import requests
import json
import pandas as pd

if __name__ == "__main__":
  N = 4
  DEBUG = False

  # the provided url, note: if this does not return json directly, it might need adjustment
  url = "https://devnet-oracle.ratio1.ai/active_nodes_list"
  server_alias_counts = {}

  for i in range(N):
    try:
      response = requests.get(url)
      response.raise_for_status()
      data = response.json()
    except Exception as e:
      print(f"error occurred during request {i+1}: {e}")
      continue
    
    if DEBUG:
      print(f"\nResponse #{i+1}:\n{json.dumps(data, indent=2)}")

    # extract nodes data from the json response
    result = data.get("result", {})
    server_alias = result.get("server_alias")
    if server_alias:
      server_alias_counts[server_alias] = server_alias_counts.get(server_alias, 0) + 1
    nodes = result.get("nodes", {})
    node_list = []
    for node_addr, node_data in nodes.items():
      if not isinstance(node_data, dict):
        continue
      eth_addr = node_data.get("eth_addr")
      alias = node_data.get("alias")
      node_list.append({
        "Node alias": alias,
        "Node ETH": eth_addr,
        "Node addr": node_addr
      })

    # create and display the pandas dataframe for this request
    df = pd.DataFrame(node_list)
    ver = result.get("server_version")
    print(f"\nResponse #{i+1} from {server_alias} v{ver}:")
    print(df)

    # update the server_alias counts

  print("\nserver_alias counts:", server_alias_counts)
