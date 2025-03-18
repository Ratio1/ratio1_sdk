"""
ex16_launch_repo_based_http_server.py
-------------------------------

This script demonstrates how to create and deploy a http server based on a public repository using ngrok
edge definition. The script will create a webapp based on a public repository containing some static assets
and deploy it to the target Ratio1 Edge Node and assign it the same ngrok edge label.

TODO:
This will be modified so that it will start a generic http server that will generate a dynamic URL which can
be used to access the webapp. For this demo, we will use a custom webapp that resides at a
public repository location.

"""
import os
from ratio1 import Session


if __name__ == "__main__":
  # 1. Create the Ratio1 Session object.
  sess = Session()
  
  # 2. Wait for the target node to be seen as active.
  nodes = [
    os.environ.get("EE_TARGET_NODE_1")
  ]
  for node in nodes:
    sess.wait_for_node(node)
  # endfor node in nodes

  # 3. Retrieve the Ngrok edge label. (optional)
  # In case this is not provided and create_and_deploy_balanced_http_server is used an exception will be raised.
  # In case this is not provided by the user, but create_http_server method is used,
  # a unique URL will be generated by the ngrok service.
  # Warning! create_http_server method does not support multiple nodes.
  ngrok_edge_label = os.environ.get("NGROK_EDGE_LABEL", None)

  # 4. Define the assets of the web application
  assets = {
    # This will specify that the target node(s) need(s) to download
    # the assets from the provided repository.
    # It will also periodically check for updates.
    "operation": "release_asset",
    # This is the asset that needs to be downloaded.
    # If this is a zip it will be unzipped on the target node(s).
    "asset_filter": "asset1_from_my_release.zip",
    # The repository from which the asset will be downloaded.
    "url": "<github_repo_url>",
    # The following 2 fields are necessary only if the repository is private.
    "username": "<git_user>",
    "token": "<git_token>"
  }

  # 5. Define the environment variables for the http server.
  port = 32600
  env_vars = {
    "PORT": port,
  }
  # This is the directory where the assets will be searched for.
  # If, for example, index.html is in <zip_root>/dist/index.html,
  # the static_directory should be "dist".
  # If this is not provided, the root of the zip will be used.
  static_directory = "dist"

  # This will be used instead of a not found error in case the user accesses a non-existing route.
  # If this is not provided, a not found error will be returned.
  default_route = "/"

  # 6. Define endpoints if necessary.
  endpoints = [
    {
      "endpoint_type": "html",
      "web_app_file_name": "index.html",
      "endpoint_route": "/",
    }
  ]

  # 7. Create and deploy the http server.
  # This will create a webapp based on the provided assets and deploy it to the target node(s).
  sess.create_and_deploy_balanced_http_server(
    nodes=nodes,
    name="Ratio1 HTTP Server Deploy Tutorial",
    env_vars=env_vars,
    assets=assets,
    static_directory=static_directory,
    default_route=default_route,
    endpoints=endpoints,
    ngrok_edge_label=ngrok_edge_label,
    # Additional parameters.
    # For example, if the launched http server needs a certain port to be exposed,
    # it will need to also be provided here.
    port=port,
  )

  # Observations:
  #   Next code is not mandatory - it is used to keep the session open and cleanup the resources.
  #   In production, you would not need this code as the script can close after the pipeline will be sent
  sess.run(
    wait=True,  # wait for the user to stop the execution
    close_pipelines=True  # when the user stops the execution, the remote edge-node pipelines will be closed
  )



