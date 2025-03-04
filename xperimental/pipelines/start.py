import os
import time

from ratio1 import Session, CustomPluginTemplate, PLUGIN_TYPES

def reply(plugin: CustomPluginTemplate, message: str, user: str):
  """
  This function is used to reply to a message. The given parameters are mandatory
  """
  plugin.obj_cache["users"][user] = self.time()
  plugin.int_cache[user] += 1 # int_cache is a default dict that allows persistence in the plugin
  plugin.P(f"Replying to the {plugin.int_cache[user]} msg of '{user}' on message '{message}'")
  result = f"The answer to your {plugin.int_cache[user]} question is in the question itself: {message}"
  return result


if __name__ == "__main__":   
  session = Session() 
  my_node = os.getenv("EE_TARGET_NODE") 
  assert my_node

  session.wait_for_node(my_node) 
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="telegram_bot_echo",
    message_handler=reply,
  )
  
  pipeline.deploy() # we deploy the pipeline
  session.close() # close the session, leave the pipeline on
