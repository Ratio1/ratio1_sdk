import os
import time

from naeural_client import Session, CustomPluginTemplate, PLUGIN_TYPES

def reply(plugin: CustomPluginTemplate, message: str, user: str):
  """
  This function is used to reply to a message. The given parameters are mandatory
  """
  # for each user message we increase a counter
  plugin.int_cache[user] += 1 # int_cache is a default dict that allows persistence in the plugin
  plugin.P(f"Replying to the {plugin.int_cache[user]} msg of '{user}' on message '{message}'")
  result = f"The answer to your {plugin.int_cache[user]} question is in the question itself: {message}"
  return result


if __name__ == "__main__":
  # TELEGRAM_BOT_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"  # this is the default - we can specify a env key here
  my_node = os.getenv("TARGET_NODE") # we can specify a node here, if we want to connect to a specific
    
  session = Session() # assume .env is available and will be used for the connection and tokens
  session.wait_for_node(my_node) # wait for the node to be active
    
      
  # now we create a telegram bot pipeline & plugin instance
  # we can chose to use the token directly or use the environment key
  # instance: PLUGIN_TYPES.TELEGRAM_BASIC_BOT_01  
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="telegram_bot_echo",
    # telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),  # we use the token directly
    # telegram_bot_token_env_key=TELEGRAM_BOT_TOKEN_ENV_KEY, # not mandatory - we can use the default
    message_handler=reply,
  )
  
  pipeline.deploy() # we deploy the pipeline

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   in production, you would not need this code as the script can close after the pipeline will be sent  
  session.run(
    wait=120,  # we run the session for 60 seconds
    close_pipelines=True,  # we close the pipelines after the session
    close_session=True,  # we close the session after the session
  )
