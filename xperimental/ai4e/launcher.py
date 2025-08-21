import os
from ratio1 import Session


if __name__ == "__main__":
  AI4E_TUNNEL_ENGINE = "cloudflare"
  APP_NAME = "devnet-ai4e-api"

  target_node = os.getenv("AI4E_NODE")
  ai4e_token = os.getenv("AI4E_TOKEN")
  

  print(f"Using {AI4E_TUNNEL_ENGINE=} and {target_node=}", flush=True)

  assert target_node, "AI4E_NODE must be set in .env file"
  assert ai4e_token, "AI4E_TOKEN must be set in .env file"

  session = Session(
    evm_network='devnet'
  )
  

  pipeline, _ = session.create_web_app(
    name=APP_NAME,
    node=target_node,
    data_source="NetworkListener",
    signature="AI4EVERYONE",
    tunnel_engine=AI4E_TUNNEL_ENGINE,
    cloudflare_token=ai4e_token
  )
  
  pipeline.deploy()
  
  session.wait(
    seconds=10,
    close_session_on_timeout=True,
    close_pipeline_on_timeout=False
  )