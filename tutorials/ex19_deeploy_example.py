#!/usr/bin/env python3

"""
ex19_deeploy_example.py
---------------------

This tutorial demonstrates how to interact with the Deeploy API using the ratio1 SDK.
It shows how to:
- Build and sign messages for Deeploy API requests
- Send authenticated requests to the Deeploy API
- Handle responses and debug information

The example includes a CLI client that can be used to:
- Create pipelines
- Delete pipelines
- Get apps

Example Usage:
-------------
1. Get list of apps:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint get_apps > res.json
   ```

2. Create a pipeline:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint create_pipeline
   ```

3. Delete a pipeline:
   ```bash
   python3 ex19_deeploy_example.py --private-key path/to/private-key.pem --request path/to/request.json --endpoint delete_pipeline
   ```

Note: The private key file should be in PEM format (typically with .pem extension) and contain your Ethereum private key.
The request JSON file should contain the appropriate request data for the endpoint you're calling.
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
  parser.add_argument('--request', type=str, required=True, help='Path to request JSON file')
  parser.add_argument('--endpoint', type=str, default='create_pipeline',
                      choices=['create_pipeline', 'delete_pipeline', 'get_apps'],
                      help='API endpoint to call')
  parser.add_argument('--debug', action='store_true', help='Enable debug output')

  args = parser.parse_args()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="ex_19_deeploy_example")

  private_key_path = args.private_key
  private_key_password = args.key_password
  endpoint = args.endpoint

  # check if PK exists
  if not os.path.isfile(args.private_key):
    print("Error: Private key file does not exist.")
    exit(1)

  # Read request
  with open(args.request, 'r') as f:
    request_data = json.load(f)

  try:
    nonce = f"0x{int(time.time() * 1000):x}"
    request_data['request']['nonce'] = nonce

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

    # Add signature and sender to request
    request_data['request']['EE_ETH_SIGN'] = signature
    request_data['request']['EE_ETH_SENDER'] = block_engine.eth_address

    # Send request
    response = requests.post(f"{API_BASE_URL}/{endpoint}", json=request_data)
    response = response.json()

    print(json.dumps(response, indent=2))
  except Exception as e:
    print(f"Error: {str(e)}")
    exit(1)
