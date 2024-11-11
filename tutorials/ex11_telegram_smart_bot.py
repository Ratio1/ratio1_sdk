import os

from naeural_client import Session, CustomPluginTemplate, PLUGIN_TYPES

if __name__ == "__main__":
  # TELEGRAM_BOT_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN" # we can specify the token here
  MY_NODE = None # we can specify a node here, if we want to connect to a specific
  
  SYSTEM_PROMPT = """
  Hi! I am a simple echo bot. I will repeat everything you say to me.
  """
    
  session = Session() # assume .env is available and will be used for the connection and tokens

  if MY_NODE:
    node = MY_NODE
  else:
    session.wait_for_any_node() # we wait for any node to present itself as active
    node = session.get_active_nodes()[0] # we get the first active node
  
      
  # now we create a telegram bot pipeline & plugin instance
  # we can chose to use the token directly or use the environment key
  # instance: PLUGIN_TYPES.BASIC_TELEGRAM_BOT_01
  pipeline, _ = session.create_telegram_conversational_bot(
    node=node,
    name="telegram_bot_echo",
    # telegram_bot_token_env_key=TELEGRAM_BOT_TOKEN_ENV_KEY, # this is not mandatory
    system_prompt=SYSTEM_PROMPT, # simple bot based on system prompt only
    # rag_source=rag_db_url,    # advanced 
    # bot_type="API" # "API", "HOSTED"
    # api_token_env_key="BOT_API_TOKEN", # if bot_type is "API" - this is a default
  )
  
  pipeline.deploy() # we deploy the pipeline

  # # Observation:
  # #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  # #   in production, you would not need this code as the script can close after the pipeline will be sent  
  # session.run(
  #   wait=60,  # we run the session for 60 seconds
  #   close_pipelines=True,  # we close the pipelines after the session
  #   close_session=True,  # we close the session after the session
  # )
