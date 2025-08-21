"""
This script is used in tandem with launcher.py script and performs pipeline deletion on target nodes

"""
import os
from ratio1 import Session


if __name__ == "__main__":
  APP_NAME = "devnet-ai4e-api"
  target_node = os.getenv("AI4E_NODE")

  session = Session(
    evm_network='devnet'
  )

  
  session.close_pipeline(
    node_addr=target_node,
    pipeline_name=APP_NAME,
  )
  
  session.wait(
    seconds=10,
    close_session_on_timeout=True,
  )
