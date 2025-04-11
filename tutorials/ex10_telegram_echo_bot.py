"""
ex10_telegram_echo_bot.py
-------------------------

A simple echo bot that replies to the user with the same message it received.
It also keeps track of the number of messages received from each user and the number of times
the processor has been called.

This example leverages the SDK ability to package user defined code and send them as handlers to
the target pipeline. 

"""
import os
import time

from ratio1 import Session, CustomPluginTemplate, PLUGIN_TYPES


def loop_processing(plugin):
  """
  This method will be continously called by the plugin to do any kind of required processing
  without being triggered by a message. This is useful for example to check for new events in
  a particular source or to do some kind of processing that is not directly related to a message
  """
  result = None
  for user in plugin.users:
    # Get or initialize user notification state
    user_cache_key = f"{user}_notification_state"
    user_notification_state = plugin.obj_cache.get(user_cache_key)
    user_stats = plugin.get_user_stats(user)

    plugin.P(f"Processing user {user} with stats {user_stats} and notification state {user_notification_state}")
    if user_notification_state is None:
      user_notification_state = {
        "received_question_notice_at_question": 0
      }
      plugin.obj_cache[user_cache_key] = user_notification_state

    if user_stats and user_stats['questions'] % 5 == 0 and user_notification_state.get(
        "received_question_notice_at_question") != user_stats['questions']:
      plugin.send_message_to_user(user_id=user, text="You have asked quite a few question, ser!")

      user_notification_state = {
        "received_question_notice_at_question": user_stats['questions']
      }
      plugin.obj_cache[user_cache_key] = user_notification_state

      if result is None:
        result = {}
      result[user] = user_stats
  return result


def reply(plugin: CustomPluginTemplate, message: str, user: str):
  """
  This function is used to reply to a message. The given parameters are mandatory
  """
  # for each user message we increase a counter
  plugin.int_cache[user] += 1 # int_cache is a default dict that allows persistence in the plugin
  processor_value = plugin.int_cache["app_counter"]
  plugin.P(f"Replying to the {plugin.int_cache[user]} msg of '{user}' on message '{message}'")
  result = f"Processor at {processor_value}. The answer to your {plugin.int_cache[user]} question is in the question itself: '{message}'"
  return result


if __name__ == "__main__":   
  # Note: in order correctly setup the deployment you have to create the Session
  #       object that will configure the execution environment
  session = Session() 

  # NOTE: When working with SDK please use the nodes internal addresses. While the EVM address of the node
  #       is basically based on the same sk/pk it is in a different format and not directly usable with the SDK
  #       the internal node address is easily spoted as starting with 0xai_ and can be found 
  #       via `docker exec r1node get_node_info` or via the launcher UI

  # this tutorial assumes you have started your own local node for dev-testing purposes
  # you can either supply the node address via env or directly here
  my_node = os.getenv("EE_TARGET_NODE", "0xai_my_own_node_address") 

  session.wait_for_node(my_node) 
    
      
  # now we create a telegram bot pipeline & plugin instance and for that we only need the Telegram token
  # we can chose to use the token directly via `telegram_bot_token` parameter
  # or use the environment key EE_TELEGRAM_BOT_TOKEN 
  # in this case for this simple example we are going to use the token directly
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="telegram_bot_echo",
    # telegram_bot_token="your_token_goes_here",  # we use the token directly
    message_handler=reply,
    processing_handler=loop_processing,
  )
  
  pipeline.deploy() # we deploy the pipeline

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close 
  #   after the pipeline will be sent 
  session.wait(
    seconds=60,            # we wait the session for 120 seconds
    close_pipelines=True,   # we close the pipelines after the session
    close_session=True,     # we close the session after the session
  )
