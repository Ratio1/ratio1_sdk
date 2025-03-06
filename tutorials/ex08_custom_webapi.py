"""
ex08_custom_webapi.py
---------------------------------

This is a simple example of how to use the ratio1 SDK.
In this example, we connect to the network, choose a node and
    deploy a plugin with custom code that will run in real time.

"""

import os
from ratio1 import CustomPluginTemplate, Session, PLUGIN_TYPES



def hello_world(plugin, name: str = "ratio1_developer"):
  # name is a query parameter
  plugin.P("Running hello endpoint...")
  return f"Hello, {name}! I am {plugin.e2_addr}"


def get_uuid(plugin: CustomPluginTemplate):
  plugin.P("Running get_uuid endpoint...")
  return f"New uuid: {plugin.uuid()}!"


def get_addr(plugin: CustomPluginTemplate):
  plugin.P("Running get_addr endpoint...")
  return plugin.node_addr


def predict(plugin: CustomPluginTemplate, series: list[int], steps: int) -> list:
  """
  This function is used to predict the next `steps` values of the time series `series`.

  Parameters
  ----------
  series : list[int]
      A list of integers representing the time series.
  steps : int
      The number of steps to predict.

  Returns
  -------
  list
      A list of integers representing the predicted values.
  """
  plugin.P("Running predict endpoint...")
  result = plugin.basic_ts_fit_predict(series, steps)
  result = list(map(int, result))
  return result


if __name__ == "__main__":
  session = Session(silent=True)

  node = os.environ.get("EE_TARGET_NODE", "INSERT_YOUR_NODE_ADDRESS_HERE")
  session.P(f"Waiting for node {node} to be available for deployment...")
  session.wait_for_node(node)

  instance: PLUGIN_TYPES.CUSTOM_WEBAPI_01
  pipeline, instance = session.create_web_app(
    node=node,
    name="ratio1_predict_app",   
    signature=PLUGIN_TYPES.CUSTOM_WEBAPI_01, 
    # by default ngrok_edge_label should not be provided as a unique URL will be generated
    # othwerwise, you can provide a custom ngrok_edge_label that should be preconfigured via ngrok dashboard
    # ngrok_edge_label=os.environ.get("NGROK_EDGE_LABEL", None),
    ngrok_edge_label=None, 
    extra_debug=True,
    endpoints=[
      {
        # we omit the "endpoint_type" key, because the default value is "default" ie the "function" type
        "function": hello_world,
        "method": "get",
      },
      {
        "function": get_uuid,
        "method": "get",
      },
      {
        "function": get_addr,
        "method": "get",
      },
      {
        "function": predict,
        "method": "post",
      },
      {
        "endpoint_type": "html",
        "html_path": "tutorials/8. custom_code_fastapi_assets/index.html",
        "web_app_file_name": "index.html",
        "endpoint_route": "/",
      }
    ]
  )

  # we could have added the endpoints one by one
  # # GET request on <domain>/hello_world?name=ratio1_developer
  # instance.add_new_endpoint(hello_world)

  # # GET request on <domain>/get_uuid
  # instance.add_new_endpoint(get_uuid, method="get")

  # # GET request on <domain>/get_addr
  # instance.add_new_endpoint(get_addr, method="get")

  # # POST request on <domain>/forecasting (with body as json with 2 keys: series and steps)
  # instance.add_new_endpoint(predict, method="post")

  # # add an html file to the web app, accessible at <domain>/
  # instance.add_new_html_endpoint(
  #   html_path="tutorials/8. custom_code_fastapi_assets/index.html",
  #   web_app_file_name="index.html",
  #   endpoint_route="/",
  # )

  url = pipeline.deploy(verbose=True)
  
  # print the url of the webapp
  session.P(f"Webapp available at: {url}", color='g', boxed=True, show=True)
  
  # at this point the webapp is deployed and the endpoints are available
  # and we can access the webapp via the url provided

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   in production, you would not need this code as the script can close after the pipeline will be sent
  session.run(
    wait=True, # wait for the user to stop the execution
    close_pipelines=True # when the user stops the execution, the remote edge-node pipelines will be closed
  )
