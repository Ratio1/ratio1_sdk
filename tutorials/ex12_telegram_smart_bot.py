"""
ex12_telegram_smart_bot.py
==========================


This example demonstrates how to create a simple echo bot using the Ratio SDK.


"""

import os
from ratio1 import Session

if __name__ == "__main__":
  
  # We define the system prompt
  SYSTEM_PROMPT = """
  Hi! I am a simple echo bot. I will repeat everything you say to me.
  """

  session = Session()  # assume .env is available and will be used for the connection and tokens

  # NOTE: When working with SDK please use the nodes internal addresses. While the EVM address of the node
  #       is basically based on the same sk/pk it is in a different format and not directly usable with the SDK
  #       the internal node address is easily spoted as starting with 0xai_ and can be found 
  #       via `docker exec r1node get_node_info` or via the launcher UI

  my_node = os.getenv("EE_TARGET_NODE")  # we specify a node here
  # The node can also be specified directly, without using the environment variable.
  # my_node = "<target_edge_node_identifier>"
  
  assert my_node is not None, "Please provide the target edge node identifier"

  session.wait_for_node(my_node)  # wait for the node to be active

  # Now we create a telegram bot pipeline & plugin instance.
  # For that we must have a telegram bot token and a telegram bot name.
  # We can provide those directly or use the environment keys.
  # In case you need a telegram bot token, you have a guide right here:
  # https://core.telegram.org/bots/tutorial
  pipeline, _ = session.create_telegram_conversational_bot(
    node=my_node,
    name="telegram_chatbot",

    # telegram_bot_token=None,    # not mantatory - can be used to specify the token directly
    # telegram_bot_token_env_key=ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY, # not mandatory - we can use the default
    # telegram_bot_name=None,     # not mandatory - can be used to specify the bot name directly
    # telegram_bot_name_env_key=ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY, # not mandatory - we can use the default

    system_prompt=SYSTEM_PROMPT,  # simple bot based on system prompt only
    agent_type="HOSTED",  # "API", "HOSTED"
    # In case of "API" agent type, we need to provide the API token.
    # api_token_env_key=ENVIRONMENT.TELEGRAM_API_AGENT_TOKEN_ENV_KEY, # not mandatory - we can use the default
    # api_token=None, # not mandatory - can be used to specify the token directly
    rag_source_url=None,  # no rag source for this example
  )
  
  pipeline.deploy()  # we deploy the pipeline

  # # Observation:
  # #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  # #   in production, you would not need this code as the script can close after the pipeline will be sent  
  # session.run(
  #   wait=60,  # we run the session for 60 seconds
  #   close_pipelines=True,  # we close the pipelines after the session
  #   close_session=True,  # we close the session after the session
  # )
