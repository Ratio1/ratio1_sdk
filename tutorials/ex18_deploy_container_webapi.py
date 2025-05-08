"""
ex18_deploy_container_webapi.py
---------------------

This is a basic example of how to use the ratio1 SDK for a containerized web API deployment

The example further extends ex02_part1_deploy_webapi.py and shows how to deploy a containerized web API rather than
a web API that uses Ratio1 Edge Node shallow machine learning internal (API) capabilities.

"""
from ratio1 import Session, CustomPluginTemplate, PLUGIN_TYPES

if __name__ == '__main__':
  
  session = Session(silent=True)

  my_node = "0xai_ApM1AbzLq1VtsLIidmvzt1Nv4Cyl5Wed0fHNMoZv9u4X"

  # NOTE: When working with SDK please use the nodes internal addresses. While the EVM address of the node
  #       is basically based on the same sk/pk it is in a different format and not directly usable with the SDK
  #       the internal node address is easily spoted as starting with 0xai_ and can be found 
  #       via `docker exec r1node get_node_info` or via the launcher UI
  
  app, _ = session.create_container_web_app( # this uses CONTAINER_APP_RUNNER
    node=my_node,
    name="ratio1_simple_container_webapp",
    image="tvitalii/flask-docker-app:latest",
    port=5000,
    # container_resources={},
    # cr="docker.io",
  )

  try:
    url = app.deploy()
    print("Webapp deployed at: ", url)
  except Exception as e:
    print("Error deploying webapp: ", e)

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close 
  #   after the pipeline will be sent 
  session.wait(
    seconds=120,            # we wait the session for 60 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )