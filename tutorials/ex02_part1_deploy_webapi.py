"""
ex02_part1_deploy_webapi.py
---------------------

This is a basic example of how to use the ratio1 SDK for a simple web API deployment that uses Ratio1
Edge Node shallow machine learning internal (API) capabilities.

"""
from ratio1 import Session, CustomPluginTemplate, PLUGIN_TYPES

def run_predict(plugin: CustomPluginTemplate, inputs: list[int], nr_steps: int) -> list:
  """
  Here we use the Ratio1 build in basic ML internal API
  """
  
  preds = plugin.basic_ts_fit_predict(inputs, nr_steps)
  # now we apply some simple heuristic to get the lower and upper bounds
  lower_bound = []
  upper_bound = []
  heuristic_factor = 0.1
  for pred in preds:
    lower_bound.append(int(pred - abs(pred * heuristic_factor)))
    upper_bound.append(int(pred + abs(pred * heuristic_factor)))
  #endfor
  result = {
    "server" : plugin.e2_addr,
    "predictions": [round(x,1) for x in preds],
    "lower_bound": lower_bound,
    "upper_bound": upper_bound
  }
  return result


if __name__ == '__main__':
  
  session = Session(silent=False)

  my_nodes = [
    "0xai_A74xZKZJa4LekjvJ6oJz29qxOOs5nLClXAZEhYv59t3Z",
    "0xai_AgnygSlY8BwnmaCj6mItg36JHlG_Lh3UqqFaTPbuNzy0",
  ]

  # NOTE: When working with SDK please use the nodes internal addresses. While the EVM address of the node
  #       is basically based on the same sk/pk it is in a different format and not directly usable with the SDK
  #       the internal node address is easily spoted as starting with 0xai_ and can be found 
  #       via `docker exec r1node get_node_info` or via the launcher UI
  for i, node in enumerate(my_nodes):
    app, _ = session.create_custom_webapi(
      node=node,
      name="ratio1_simple_predict_webapp",
      tunnel_engine="cloudflare", # set this to "cloudflare" or "ngrok"
      # assume tokens are either
      endpoints=[
        {
          "function": run_predict,
          "method": "post",
        },        
      ]
    )
    try:
      url = app.deploy()
      print(f"Webapp deployed on node {i+1}/{len(my_nodes)} at: {url}")
    except Exception as e:
      print("Error deploying webapp: ", e)
  
  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close 
  #   after the pipeline will be sent 
  session.wait(
    seconds=300,            # we wait the session for 60 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )