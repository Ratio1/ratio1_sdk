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
   python3 ex19_deeploy_example.py --private-key path/to/private-key --request path/to/request.json --endpoint get_apps > res.json
   ```

2. Create a pipeline:
   ```bash
   python3 ex19_deeploy_example.py private-key path/to/private-key --request path/to/request.json --endpoint create_pipeline
   ```

3. Delete a pipeline:
   ```bash
   python3 ex19_deeploy_example.py private-key path/to/private-key --request path/to/request.json --endpoint delete_pipeline
   ```

Note: The private key file should contain your Ethereum private key, and the request JSON file should contain
the appropriate request data for the endpoint you're calling.
"""

import json
import time
import argparse

import requests
from typing import Dict, Any

from ratio1 import Logger
from ratio1.bc import DefaultBlockEngine
from ratio1.const.base import BCct

API_BASE_URL = "https://devnet-deeploy-api.ratio1.ai"


def deep_sort(obj: Any) -> Any:
  """Recursively sort dictionaries and lists to ensure consistent ordering.

  Args:
      obj: Any object to be sorted (dict, list, or primitive type)

  Returns:
      A new object with all dictionaries and lists sorted
  """
  if isinstance(obj, list):
    return [deep_sort(item) for item in obj]
  elif isinstance(obj, dict):
    return {k: deep_sort(v) for k, v in sorted(obj.items())}
  return obj


def build_message(data: Dict[str, Any]) -> str:
  """Build a message string for signing by cleaning and formatting the input data.

  Args:
      data: Dictionary containing the request data

  Returns:
      A formatted string ready for signing, with signature-related fields removed
      and data sorted consistently
  """
  sorted_data = deep_sort(data)
  json_str = json.dumps(sorted_data, sort_keys=True, indent=1)
  json_str = json_str.replace('": ', '":')
  return f"Please sign this message for Deeploy: {json_str}"


def send_request(endpoint: str, request_data: Dict[str, Any], private_key: str,
                 logger: Logger, debug: bool = False) -> Dict[str, Any]:
  """Send a signed request to the Deeploy API.

  Args:
      endpoint: The API endpoint to send the request to
      request_data: The request data to send
      private_key: The Ethereum private key to sign the request with
      debug: Whether to print debug information

  Returns:
      The JSON response from the API

  Note:
      This function will automatically add a nonce and sign the request
      before sending it to the API.
  """
  # Generate nonce
  nonce = f"0x{int(time.time() * 1000):x}"
  request_data['request']['nonce'] = nonce

  # Get the account address first
  account = Account.from_key(private_key)
  sender_address = account.address

  # Build and sign message
  message = build_message(request_data['request'])

  block_engine = DefaultBlockEngine(
        log=logger,
        name="default",
    config={
      BCct.K_PEM_FILE: '../../ex19/private_key.pem',
      BCct.K_PASSWORD: None,
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
  # request_data['request']['EE_ETH_SENDER'] = sender_address

  # Print debug information only if debug flag is enabled
  if debug:
    print("Debug information:")
    print(f"Message to sign: {message}")
    # print(f"Sender address: {sender_address}")
    print(f"Signature: {signature}")

  # Send request
  response = requests.post(f"{API_BASE_URL}/{endpoint}", json=request_data)
  return response.json()


def main():
  """Main entry point for the Deeploy CLI client.

  This function parses command line arguments and sends the request to the Deeploy API.
  It requires a private key file and a request JSON file to be specified.
  """
  parser = argparse.ArgumentParser(description='Deeploy CLI client')
  parser.add_argument('--private-key', type=str, required=True, help='Path to private key file')
  parser.add_argument('--request', type=str, required=True, help='Path to request JSON file')
  parser.add_argument('--endpoint', type=str, default='create_pipeline',
                      choices=['create_pipeline', 'delete_pipeline', 'get_apps'],
                      help='API endpoint to call')
  parser.add_argument('--debug', action='store_true', help='Enable debug output')

  args = parser.parse_args()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="ex_19_deeploy_example")

  # check if PK exists
  # Read private key
  with open('ex19/private_key', 'r') as f:
    private_key = f.read().strip()

  # Read request
  with open(args.request, 'r') as f:
    request_data = json.load(f)

  try:
    response = send_request(args.endpoint, request_data, private_key, logger, args.debug)
    print(json.dumps(response, indent=2))
  except Exception as e:
    print(f"Error: {str(e)}")
    exit(1)


if __name__ == "__main__":
  main()
