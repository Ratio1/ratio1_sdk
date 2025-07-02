#!/usr/bin/env python3

import json

from ratio1.logging import Logger
from ratio1.const import DEEPLOY_CT
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


if __name__ == '__main__':
  # we do not set up any node as we will not use direct SDK deployment but rather the Deeploy API
  session = Session()
  logger = Logger("DEEPLOY", base_folder=".", app_folder="deeploy_launch_container_app")

  telegram_bot_token = ''
  private_key_path = ''  # The path to your Private Key
  target_nodes = [""]  # replace with your target node address

  launch_result = session.deeploy_simple_telegram_bot(
    name="r1_deeploy_tg_bot",
    signer_private_key_path=private_key_path,
    target_nodes=target_nodes,
    # target_nodes_count=0,  # if you want to deploy to all nodes, set this to 0
    logger=logger,

    telegram_bot_token=telegram_bot_token,  # we use the token directly
    message_handler=reply,
    processing_handler=loop_processing,
  )

  session.P(json.dumps(launch_result))

  if launch_result and launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P("Deeploy telegram bot launch failed:", launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error'))
    exit(1)
  print("Deeploy telegram bot launched successfully.")

  session.sleep(60)

  # no neeed for further `sess.deploy()` as the `deeploy_*` methods handle the deployment automatically
  # now we interpret the launch_result and extract app-id, etc
  # ...

  # if all ok sleep for a while to allow app testing (say 60 seconds)

  # finally use deeploy close

  close_result = session.deeploy_close(
    app_id=launch_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT][DEEPLOY_CT.DEEPLOY_KEYS.APP_ID],
    signer_private_key_path=private_key_path,
    target_nodes=target_nodes,
    logger=logger,
  )

  session.P(json.dumps(close_result))

  if close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT] and close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.STATUS) == DEEPLOY_CT.DEEPLOY_STATUS.FAIL:
    session.P(f"Closing deployed telegram bot failed. {close_result[DEEPLOY_CT.DEEPLOY_KEYS.RESULT].get(DEEPLOY_CT.DEEPLOY_KEYS.ERROR, 'Unknown error')}")
    exit(2)

  session.P("Demo run successfully!")

  session.close()
