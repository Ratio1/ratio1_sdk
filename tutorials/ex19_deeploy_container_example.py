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
- DEEPLOY_JOB_ID, DEEPLOY_CREATE_REQUEST_ID and DEEPLOY_DELETE_REQUEST_ID configured
  in the environment; reuse the same request IDs after uncertain acceptance

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
1. Submit the configured paid job and poll until the deployment is ready
2. Wait for 60 seconds to allow testing
3. Submit whole-job deletion and poll until stops and cleanup are confirmed

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
import os
import time

from ratio1.logging import Logger
from ratio1.const import DEEPLOY_CT

from ratio1 import Session

if __name__ == '__main__':
  # Configure these once before submission; retain the same IDs after timeout/restart.
  job_id = int(os.environ['DEEPLOY_JOB_ID'])
  create_request_id = os.environ['DEEPLOY_CREATE_REQUEST_ID']
  delete_request_id = os.environ['DEEPLOY_DELETE_REQUEST_ID']
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
    request_id=create_request_id,
    job_id=job_id,
  )

  session.P(json.dumps(launch_result))
  accepted = launch_result['result']
  print('Deployment accepted; waiting for node readiness and any required recovery.')
  api_url, auth = session.deeploy_get_read_auth(logger, private_key_path)
  while True:
    progress = session.deeploy_get_deployment_status(
      api_url, auth, operation_id=accepted['operation_id'],
    )['result']
    if progress.get('phase') == 'completed':
      settlement = progress.get('settlement', {}).get('status')
      if progress['outcome'] != 'succeeded' or settlement in ('confirmed', 'failed'):
        break
    time.sleep(progress.get('poll_after_ms', 2000) / 1000)
  if progress['outcome'] != 'succeeded' or progress.get('settlement', {}).get('status') != 'confirmed':
    raise RuntimeError('Deployment failed; inspect the operation recovery details.')
  print('Deployment ready. Keeping it running for 60 seconds before whole-job deletion.')
  session.sleep(60)
  close_result = session.deeploy_close(
    app_id=accepted['app_id'], job_id=job_id,
    request_id=delete_request_id, expected_revision=accepted['revision'],
    signer_private_key_path=private_key_path, logger=logger,
  )
  session.P(json.dumps(close_result))
  while True:
    progress = session.deeploy_get_deployment_status(
      api_url, auth, operation_id=close_result['result']['operation_id'],
    )['result']
    if progress.get('phase') == 'completed':
      break
    time.sleep(progress.get('poll_after_ms', 2000) / 1000)
  if progress['outcome'] != 'succeeded':
    raise RuntimeError('Deletion did not complete successfully; inspect operation details.')
  print('Whole-job deletion confirmed.')
  session.close()
