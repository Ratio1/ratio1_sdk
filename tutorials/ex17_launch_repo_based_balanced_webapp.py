"""
ex17_launch_repo_based_balanced_webapp.py
-------------------------------

This script is a continuation of ex13_launch_repo_based_webapp.py and is used to create and deploy a webapp
on multiple nodes in a balanced manner. It uses the Ratio1 Python SDK to interact with the Ratio1 Edge Nodes and deploy
the webapp. The script is designed to be run in a Python environment with the Ratio1 SDK installed.

Note: This script will need a valid Ngrok edge label to be provided in order for a single unified url to work.
"""
from os import environ
from ratio1 import Session


if __name__ == "__main__":
  session = Session()

  nodes = [
    environ.get("EE_TARGET_NODE_1", "INSERT_YOUR_NODE_ADDRESS_HERE"),
    environ.get("EE_TARGET_NODE_2", "INSERT_YOUR_NODE_ADDRESS_HERE")
  ]

  if isinstance(nodes, str):
    nodes = [nodes]

  for node in nodes:
    session.wait_for_node(node)

  # This is mandatory for the webapp to work on multiple nodes.
  # If the edge label were to be set to None, the webapp will be deployed
  # with a different temporary URL on each node.
  # In case of this the user will need to handle the URL redirection for now.
  ngrok_edge_label = environ.get("NGROK_EDGE_LABEL", None)

  # Defining the environment variables for the webapp.
  # Here we can pass anything we want to the webapp.
  env_vars = {
    'LOCAL_ADDRESS': '/edge_node/_local_cache/_data/local_info.json',
    "VAR_NAME_1": "value1",
    "VAR_NAME_2": "value2",
  }

  # Defining the webapp setup commands.
  setup_commands = [
    "npm install"
  ]

  # Defining the assets of the application.
  assets = {
    'operation': "clone",
    "url": "https://github.com/ratio1/demo-deploy-nodejs",
    # The below are only necessary for private repos
    "username": "<username>",
    "token": "<user_git_token>",
  }

  # Defining the webapp run commands.
  run_command = "npm start"

  # instance: PLUGIN_TYPES.CUSTOM_WEBAPI_01
  session.create_and_deploy_balanced_web_app(
    nodes=nodes,
    name="Ratio1_WebApp_tutorial",
    env_vars=env_vars,
    setup_commands=setup_commands,
    run_command=run_command,
    ngrok_edge_label=ngrok_edge_label,
    assets=assets
  )

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   in production, you would not need this code as the script can close after the pipeline will be sent
  session.run(
    wait=True,  # wait for the user to stop the execution
    close_pipelines=True  # when the user stops the execution, the remote edge-node pipelines will be closed
  )
