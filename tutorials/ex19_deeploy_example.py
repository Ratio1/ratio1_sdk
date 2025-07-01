#!/usr/bin/env python3

"""
ex19_deeploy_example.py
---------------------

This tutorial demonstrates how to interact with the Deeploy API using the ratio1 SDK.
"""
import json

from ratio1.logging import Logger

from ratio1 import Session

if __name__ == '__main__':
  # we do not set up any node as we will not use direct SDK deployment but rather the Deeploy API
  session = Session()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="deeploy_launch_container_app")

  private_key_path = '' # The path to your Private Key
  target_nodes = ["0xai_AzMjCS6GuOV8Q3O-XvQfkvy9J-9F20M_yCGDzLFOd4mn"]  # replace with your target node address
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
    target_nodes=target_nodes
    # target_nodes_count=0,  # if you want to deploy to all nodes, set this to 0
    logger=logger,
  )

  session.P(json.dumps(launch_result))

  if launch_result and launch_result['result'].get('status') == 'fail':
    session.P("Deeploy app launch failed:", launch_result['result'].get('error', 'Unknown error'))
    exit(1)
  print("Deeploy app launched successfully.")

  session.sleep(60)

  # no neeed for further `sess.deploy()` as the `deeploy_*` methods handle the deployment automatically
  # now we interpret the launch_result and extract app-id, etc
  # ...

  # if all ok sleep for a while to allow app testing (say 60 seconds)

  # finally use deeploy close

  close_result = session.deeploy_close(
    app_id=launch_result['result']['app_id'],
    target_nodes=launch_result['result']['request']['target_nodes'],
    signer_private_key_path=private_key_path,
    logger=logger
  )

  session.P(json.dumps(close_result))

  if close_result['result'] and close_result['result'].get('status') == 'fail':
    session.P(f"Closing deployed container faild. {close_result['result'].get('error', 'Unknown error')}")
    exit(2)

  session.P("Demo run successfully!")

  session.close()
