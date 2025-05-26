#!/usr/bin/env python3

"""
ex19_deeploy_example.py
---------------------

This tutorial demonstrates how to interact with the Deeploy API using the ratio1 SDK.
It shows how to:
- Build and sign messages for Deeploy API requests
- Send authenticated requests to the Deeploy API
- Handle responses

The example includes a CLI client that can be used to:
- Create pipelines
- Delete pipelines
- Get apps

Example Usage:
-------------
1. Get list of apps:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --endpoint get_apps > res.json
   ```

2. Create a pipeline:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint create_pipeline
   ```
   
   Example request.json for pipeline creation:
   ```json
   {
     "request": {
       "app_alias": "app_deployed_from_tutorials",
       "plugin_signature": "PLUGIN_SIGNATURE",
       "target_nodes": [
         "0xai_target_node_1"
       ],
       "target_nodes_count": 0
       "pipeline_input_type": "void"
     }
   }
   ```

3. Delete a pipeline:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint delete_pipeline
   ```

   Example request.json for pipeline deletion:
   ```json
   {
     "request": {
       "app_id": "target_app_name_id_returned_by_get_apps_or_create_pipeline",
       "target_nodes": [
         "0xai_target_node_1"
       ]
     }
   }
   ```

4. Send app command:
    ```bash
    python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint send_app_command
    ```

    Example request.json for sending app command:
    ```json
    {
      "request": {
        "app_id": "target_app_name_id_returned_by_get_apps_or_create_pipeline",
        "app_command": "RESTART"
      }
    }
    ```

5. Send instance command:
    ```bash
    python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint send_instance_command
    ```
    Example request.json for sending instance command:
    ```json
    {
      "request": {
        "app_id": "target_app_name_id_returned_by_get_apps_or_create_pipeline",
        "target_nodes": [
          "0xai_target_node_1"
        ],
        "plugin_signature": "PLUGIN_SIGNATURE",
        "instance_id": "PLUGIN_INSTANCE_ID",
        "instance_command": "RESTART"
      }
    }
    ```

Note: The private key file should be in PEM format (typically with .pem extension) and contain your Ethereum private key.
The request JSON file should contain the appropriate request data for the endpoint you're calling.



```python

from ratio1 import Session

if __name__ == '__main__':
  # we do not setup any node as we will not use direct SDK deployment but rather the Deeploy API
  sess = Session()

  launch_result = sess.deeploy_launch_container_app(
    image="tvitalii/flask-docker-app:latest",
    name="ratio1_simple_container_webapp",
    port=5000,  
    # signer_key_path="../../path/to/private-key.pem",
    # signer_key_password=None,  # if your private key has a password, set it here
    signer_key_string=str_metamask_key,  # if you want to use a private key string instead of a file
    target_nodes=["0xai_target_node_1"],  # replace with your target node address
    # target_nodes_count=0,  # if you want to deploy to all nodes, set this to 0
  )

  # no neeed for further `sess.deploy()` as the `deeploy_*` methods handle the deployment automatically
  # now we interpret the launch_result and extract app-id, etc
  # ...

  # if all ok sleep for a while to allow app testing (say 60 seconds)

  # finally use deeploy close

  close_result = sess.deeploy_close(
    ... # use `launch_result` to get the necessary parameters
  )
  
  # log the result
```

"""

import json
import os
import time
import argparse

import requests

from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine
from ratio1.const.base import BCct

API_BASE_URL = "https://devnet-deeploy-api.ratio1.ai"


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Deeploy CLI client')
  parser.add_argument('--private-key', type=str, required=True, help='Path to PEM private key file')
  parser.add_argument('--key-password', type=str, required=False, help='Private key password (if PK has any).',
                      default=None)
  parser.add_argument('--request', type=str, required=False, help='Path to request JSON file',
                      default=None)
  parser.add_argument('--endpoint', type=str, default='create_pipeline',
                      choices=['create_pipeline', 'delete_pipeline', 'get_apps', 'send_app_command', 'send_instance_command'],
                      help='API endpoint to call')

  args = parser.parse_args()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="ex_19_deeploy_example")

  private_key_path = args.private_key
  private_key_password = args.key_password
  endpoint = args.endpoint

  # Check if PK exists
  if not os.path.isfile(args.private_key):
    print("Error: Private key file does not exist.")
    exit(1)

  # Read request data if provided or use default empty request
  if args.request:
    with open(args.request, 'r') as f:
      request_data = json.load(f)
  else:
    request_data = {'request': {}}

  try:
    # Set the nonce for the request
    nonce = f"0x{int(time.time() * 1000):x}"
    request_data['request']['nonce'] = nonce

    # Create a block engine instance with the private key
    block_engine = DefaultBlockEngine(
      log=logger,
      name="default",
      config={
        BCct.K_PEM_FILE: f"../../{private_key_path}",
        BCct.K_PASSWORD: private_key_password,
      }
    )

    # Sign the payload using eth_sign_payload
    signature = block_engine.eth_sign_payload(
      payload=request_data['request'],
      indent=1,
      no_hash=True,
      message_prefix="Please sign this message for Deeploy: "
    )

    # Send request
    response = requests.post(f"{API_BASE_URL}/{endpoint}", json=request_data)
    response = response.json()

    print(json.dumps(response, indent=2))
  except Exception as e:
    print(f"Error: {str(e)}")
    exit(1)
