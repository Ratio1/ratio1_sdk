#!/usr/bin/env python3

"""
ex19_deeploy_example.py
---------------------

This tutorial demonstrates how to interact with the Deeploy API using the ratio1 SDK.
It shows how to:
- Launch a containerized application on remote nodes using Deeploy
- Monitor the deployment process
- Close/stop the deployed application when done

The example uses the simplified SDK methods for Deeploy operations:
- `session.deeploy_launch_container_app()` - Launch a Docker container on target nodes
- `session.deeploy_close()` - Stop and remove the deployed application

What you need:
- A PEM private key file for signing requests
- Target node addresses where you want to deploy
- A Docker image to deploy (publicly accessible)

Example Usage:
-------------
1. Prepare your private key:
   - Save your Ethereum private key in PEM format (e.g., private_key.pem)
   - Update the `private_key_path` variable to point to your key file

2. Configure target nodes:
   - Update the `target_nodes` list with your actual node addresses
   - These should be nodes that support Deeploy container deployment

3. Customize the deployment:
   - `docker_image`: Docker image to deploy (must be publicly accessible)
   - `name`: Unique name for your application
   - `port`: Port that your application listens on
   - `container_resources`: CPU, memory, and GPU requirements

4. Run the script:
   ```bash
   python3 ex19_deeploy_example.py
   ```

The script will:
1. Launch the container on the specified nodes
2. Wait for 60 seconds to allow testing
3. Automatically close/stop the deployed application
4. Clean up resources

Container Resources:
------------------
You can specify resource requirements for your container:
- `cpu`: Number of CPU cores (e.g., 1, 2, 0.5)
- `memory`: Memory limit (e.g., "512m", "1g", "2048m")
- `gpu`: Number of GPU units (0 for CPU-only applications)

Example Docker Images:
--------------------
- `tvitalii/flask-docker-app:latest` - Simple Flask web application
- `nginx:alpine` - Nginx web server
- `httpd:alpine` - Apache web server

Note: 
- The private key file should be in PEM format and contain your Ethereum private key
- Target nodes must support Deeploy container deployment
- The Docker image must be publicly accessible (Docker Hub, etc.)
- Make sure your application listens on the specified port
- The deployment will automatically clean up after the demo completes

For production use, you may want to:
- Remove the automatic cleanup (`deeploy_close`) to keep your app running
- Add proper error handling and retry logic
- Monitor application health and logs
- Use environment variables for configuration
"""
import json

from ratio1.logging import Logger
from ratio1.const import DEEPLOY_CT

from ratio1 import Session

if __name__ == '__main__':
  # we do not set up any node as we will not use direct SDK deployment but rather the Deeploy API
  session = Session()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="deeploy_launch_container_app")

  private_key_path = '' # The path to your Private Key
  target_nodes = [""]  # replace with your target node address
  launch_result = session.deeploy_launch_container_app(
    docker_image="tvitalii/flask-docker-app:latest",
    name="ratio1_simple_container_webapp",
    port=5679,
    container_resources={
      "cpu": 1,
      "gpu": 0,
      "memory": "512m"
    },
    signer_private_key_path=private_key_path,
    # signer_key_path="../../path/to/private-key.pem",
    # signer_key_password=None,  # if your private key has a password, set it here
    target_nodes=target_nodes,
    # target_nodes_count=0,  # if you want to deploy to all nodes, set this to 0
    logger=logger,
  )

  session.P(json.dumps(launch_result))

  if launch_result and launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P("Deeploy app launch failed:", launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error'))
    exit(1)
  print("Deeploy app launched successfully.")

  session.sleep(60)

  # no neeed for further `sess.deploy()` as the `deeploy_*` methods handle the deployment automatically
  # now we interpret the launch_result and extract app-id, etc
  # ...

  # if all ok sleep for a while to allow app testing (say 60 seconds)

  # finally use deeploy close

  close_result = session.deeploy_close(
    app_id=launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT][DEEPLOY_CT.DEEPLOY_KEYS.APP_ID],
    target_nodes=launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT][DEEPLOY_CT.DEEPLOY_KEYS.REQUEST][DEEPLOY_CT.DEEPLOY_KEYS.TARGET_NODES],
    signer_private_key_path=private_key_path,
    logger=logger
  )

  session.P(json.dumps(close_result))

  if close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT] and close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P(f"Closing deployed container faild. {close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error')}")
    exit(2)

  session.P("Demo run successfully!")

  session.close()
