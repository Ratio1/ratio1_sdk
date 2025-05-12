#!/usr/bin/env python3

import json
import time
import argparse
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
from typing import Dict, Any
import hashlib

API_BASE_URL = "https://devnet-deeploy-api.ratio1.ai"

def deep_sort(obj: Any) -> Any:
  if isinstance(obj, list):
    return [deep_sort(item) for item in obj]
  elif isinstance(obj, dict):
    return {k: deep_sort(v) for k, v in sorted(obj.items())}
  return obj


def build_message(data: Dict[str, Any]) -> str:
  cleaned = data.copy()
  # Remove signature-related fields
  cleaned.pop('EE_ETH_SIGN', None)
  cleaned.pop('EE_ETH_SENDER', None)
  cleaned.pop('address', None)
  cleaned.pop('signature', None)

  sorted_data = deep_sort(cleaned)
  json_str = json.dumps(sorted_data, sort_keys=True, indent=1)
  json_str = json_str.replace('": ', '":')
  return f"Please sign this message for Deeploy: {json_str}"


def sign_message(private_key: str, message: str) -> str:
  account = Account.from_key(private_key)
  message_encoded = encode_defunct(text=message)
  signed_message = account.sign_message(message_encoded)
  return signed_message.signature.hex()


def send_request(endpoint: str, request_data: Dict[str, Any], private_key: str, debug: bool = False) -> Dict[str, Any]:
  # Generate nonce
  nonce = f"0x{int(time.time() * 1000):x}"
  request_data['request']['nonce'] = nonce

  # Get the account address first
  account = Account.from_key(private_key)
  sender_address = account.address

  # Build and sign message
  message = build_message(request_data['request'])
  signature = sign_message(private_key, message)

  # Add signature and sender to request
  request_data['request']['EE_ETH_SIGN'] = signature
  request_data['request']['EE_ETH_SENDER'] = sender_address

  # Print debug information only if debug flag is enabled
  if debug:
    print("Debug information:")
    print(f"Message to sign: {message}")
    print(f"Message hash: {hashlib.sha256(message.encode()).hexdigest()}")
    print(f"Sender address: {sender_address}")
    print(f"Signature: {signature}")

  # Send request
  response = requests.post(f"{API_BASE_URL}{endpoint}", json=request_data)
  return response.json()

def main():
  parser = argparse.ArgumentParser(description='Deeploy CLI client')
  parser.add_argument('--private-key', type=str, required=True, help='Path to private key file')
  parser.add_argument('--request', type=str, required=True, help='Path to request JSON file')
  parser.add_argument('--endpoint', type=str, default='/create_pipeline',
                      choices=['/create_pipeline', '/delete_pipeline', '/get_apps'],
                      help='API endpoint to call')
  parser.add_argument('--debug', action='store_true', help='Enable debug output')

  args = parser.parse_args()

  # Read private key
  with open(args.private_key, 'r') as f:
    private_key = f.read().strip()

  # Read request
  with open(args.request, 'r') as f:
    request_data = json.load(f)

  try:
    response = send_request(args.endpoint, request_data, private_key, args.debug)
    print(json.dumps(response, indent=2))
  except Exception as e:
    print(f"Error: {str(e)}")
    exit(1)


if __name__ == "__main__":
  main()