"""
ex21_telegram_community_bot.py
-------------------------

A Telegram bot that serves two main purposes for the Ratio1 community:
1. It allows users to watch their Ethereum wallets and receive notifications when their nodes are offline.
2. It sends a summary of the last epoch at epoch change, including node statistics and token supply information.

This example demonstrates how to use multiple sources of data which can be retreived from the Ratio1 plugin,
showcasing the simplicity of the logic to handle Telegram communication.

"""
import os
from ratio1 import Session, CustomPluginTemplate

def loop_processing(plugin: CustomPluginTemplate):
  """
  This method will be continously called by the plugin to do any kind of required processing
  without being triggered by a message. This is useful for example to check for new events in
  a particular source or to do some kind of processing that is not directly related to a message

  In this example, we will check for the last epoch change and send a summary of the last epoch,
  as well as checking for watched wallets and notifying users if their nodes are offline.
  """

  epoch_manager = plugin.netmon.epoch_manager
  last_epoch = epoch_manager.get_last_sync_epoch()

  # Define cache keys and file names for storing epoch review data and watched wallets
  epoch_review_cache_key = f"ratio1_epoch_review"
  watched_wallets_cache_key = f"ratio1_watched_wallets"
  watched_wallets_loops_delay_cache_key = f"ratio1_watched_wallets_loops_delay"
  alert_cache_key = f"ratio1_node_alerts"
  cache_already_read_key = f"ratio1_epoch_review_already_read"
  diskapi_epoch_review_file_name = "ratio1_epoch_review_data.pkl"
  diskapi_watched_wallets_file_name = "ratio1_watched_wallets_data.pkl"

  need_last_epoch_info = "need_last_epoch_info"

  def get_erc721_total_supply(contract_address: str) -> int:
    return int(plugin.requests.post("https://base-mainnet.public.blastapi.io", json={
      "jsonrpc": "2.0",
      "method": "eth_call",
      "params": [
        {
          "to": contract_address,
          "data": "0x18160ddd" # totalSupply()
        },
        "latest"
      ],
      "id": 1
    }).json()["result"], 16)
  
  def get_nodes_details():
    nodes = plugin.netmon.available_nodes_prefixed
    nodes_count = len(nodes)
    last_epoch_nd_mining = 0
    nd_count = 0
    mnd_count = 0
    gnd_count = 0
    for node in nodes:
      node_license_info = plugin.bc.get_node_license_info(node_address=node)

      if node_license_info["licenseType"] == 1:
        nd_count += 1
        if node_license_info["totalClaimedAmount"] < node_license_info["totalAssignedAmount"]:
          node_availability = epoch_manager.get_node_epoch(node_addr=node, epoch_id=last_epoch)
          last_epoch_nd_mining += (node_license_info["totalAssignedAmount"] / 1080) * node_availability / 255

      elif node_license_info["licenseType"] == 2:
        mnd_count += 1

      elif node_license_info["licenseType"] == 3:
        gnd_count += 1
    return (last_epoch_nd_mining / 10**18), nodes_count, nd_count, mnd_count, gnd_count
  
  def get_burned_last_epoch(current_burn: int) -> int:
    if plugin.obj_cache.get(epoch_review_cache_key) is None:
      return current_burn
    if plugin.obj_cache.get(epoch_review_cache_key).get(last_epoch - 1) is None:
      return current_burn
    return current_burn - plugin.obj_cache.get(epoch_review_cache_key).get(last_epoch - 1).get("burned")
  
  def get_poai_burned_last_epoch(current_burn: int) -> int:
    if plugin.obj_cache.get(epoch_review_cache_key) is None:
      return current_burn
    if plugin.obj_cache.get(epoch_review_cache_key).get(last_epoch - 1) is None:
      return current_burn
    return current_burn - plugin.obj_cache.get(epoch_review_cache_key).get(last_epoch - 1).get("poai_burned", 0)

  # If it is the first run, we need to initialize the cache from diskapi
  if plugin.obj_cache.get(cache_already_read_key) is None:
    plugin.obj_cache[epoch_review_cache_key] = plugin.diskapi_load_pickle_from_data(diskapi_epoch_review_file_name) or {}
    plugin.obj_cache[watched_wallets_cache_key] = plugin.diskapi_load_pickle_from_data(diskapi_watched_wallets_file_name) or {}
    plugin.obj_cache[alert_cache_key] = {}
    plugin.obj_cache[watched_wallets_loops_delay_cache_key] = 30
    plugin.obj_cache[cache_already_read_key] = True # We use this flag to read the cache only once at the first run
    

  # Check users' watched wallets and notify if any node is offline
  if plugin.obj_cache.get(watched_wallets_loops_delay_cache_key) == 30:
    watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key)
    if watched_wallets is not None:
      for user, wallets in watched_wallets.items():
        for wallet in wallets:
          wallet_nodes = plugin.bc.get_wallet_nodes(wallet)
          for node in wallet_nodes:
            if node == "0x0000000000000000000000000000000000000000":
              continue

            node_alert_cache_key = f"{user}-{node}"
            node_internal_addr = plugin.bc.eth_addr_to_internal_addr(node)
            node_is_online = plugin.netmon.network_node_is_online(node_internal_addr)
            if node_is_online:
              if plugin.obj_cache[alert_cache_key].get(node_alert_cache_key) is not None:
                # Node was previously offline, now it is back online, we notify the user
                message = f"✅ Node {plugin.netmon.network_node_eeid(node_internal_addr)} ({node}) is back online."
                plugin.send_message_to_user(user_id=user, text=message)
                plugin.obj_cache[alert_cache_key][node_alert_cache_key] = None
            elif plugin.obj_cache[alert_cache_key].get(node_alert_cache_key) is None:
              # Node is offline and we haven't notified the user yet
              plugin.obj_cache[alert_cache_key][node_alert_cache_key] = True
              message = f"⚠️ Node {plugin.netmon.network_node_eeid(node_internal_addr)} ({node}) is offline. Please check your node status."
              plugin.send_message_to_user(user_id=user, text=message)
    plugin.obj_cache[watched_wallets_loops_delay_cache_key] = 0
  else:
    plugin.obj_cache[watched_wallets_loops_delay_cache_key] += 1


  need_info = plugin.obj_cache.get(need_last_epoch_info, False)

  # Check if the epoch review has already been processed for the last epoch
  if plugin.obj_cache.get(epoch_review_cache_key) is not None:
    if plugin.obj_cache.get(epoch_review_cache_key).get(last_epoch) is not None and not need_info:
      return
    else:
      plugin.P("Epoch review not processed for last epoch, continuing with processing.")
  else:
    plugin.P("No epoch review data found, initializing cache.")
    plugin.obj_cache[epoch_review_cache_key] = {}
    plugin.obj_cache[watched_wallets_cache_key] = {}
    
  plugin.obj_cache[need_last_epoch_info] = False # set false no matter wwhat as we display the info

  # Get all the required data for the epoch review
  last_epoch_nd_mining, nodes_count, nd_count, mnd_count, gnd_count = get_nodes_details()
  plugin.P(f"Found {nd_count} ND, {mnd_count} MND, {gnd_count} GND. Last epoch mining: {last_epoch_nd_mining}")

  # We get token details from the Ratio1 API
  tokenDetails = plugin.requests.get("https://dapp-api.ratio1.ai/token/supply?withDecimals=true").json()
  current_burn = float(tokenDetails["burned"])
  nd_current_burn = float(tokenDetails["ndContractBurn"])
  current_poai_burn = current_burn - nd_current_burn
  circulating_supply = float(tokenDetails["circulatingSupply"])
  total_supply = float(tokenDetails["totalSupply"])
  burned_last_epoch = get_burned_last_epoch(current_burn)
  burned_poai_last_epoch = get_poai_burned_last_epoch(current_poai_burn)
  price_url = 'https://api.coingecko.com/api/v3/simple/price?ids=ratio1&vs_currencies=usd'
  r1_usdc = plugin.requests.get(price_url).json().get("ratio1", {}).get("usd", 0)
  poai_usdc_last_epoch = burned_poai_last_epoch / 0.15 * r1_usdc
  burned_nd_last_epoch = burned_last_epoch - burned_poai_last_epoch
  plugin.P(f"Burned last epoch: {burned_last_epoch}, ND burned last epoch: {burned_nd_last_epoch}, PoAI burned last epoch: {burned_poai_last_epoch}, Current burn: {current_burn}, Circulating supply: {circulating_supply}, Total supply: {total_supply}")

  nd_supply = get_erc721_total_supply("0xE658DF6dA3FB5d4FBa562F1D5934bd0F9c6bd423")
  mnd_supply = get_erc721_total_supply("0x0C431e546371C87354714Fcc1a13365391A549E2")
  total_licenses = nd_supply + mnd_supply
  plugin.P(f"Total ND supply: {nd_supply}, Total MND supply: {mnd_supply}, Total Licenses: {total_licenses}")  

  # Prepare the message to send to the group chat
  message = f"📆 Epoch {last_epoch} Summary\n\n"
  message += f"🛰️ Active Nodes: {nodes_count} ({nd_count} ND, {mnd_count} MND, {gnd_count} GND)\n"
  message += f"🪪 Total Licenses: {total_licenses}\n"
  message += f"🔄 Circulating R1 Supply: {circulating_supply:,.0f} R1\n"
  message += f"💎 Total R1 Supply: {total_supply:,.0f} R1\n"
  message += f"🎁 Last Epoch PoA Mining: {(last_epoch_nd_mining):,.2f} R1\n"
  if burned_nd_last_epoch > 0:
    message += f"🔥 Last Epoch License Sales Burn: {(burned_nd_last_epoch):,.2f} R1\n"
  if burned_poai_last_epoch > 0:
    message += f"🎁 Last Epoch PoAI Rewards: {(poai_usdc_last_epoch):,.2f} USDC\n"
    message += f"🔥 Last Epoch PoAI Burn: {(burned_poai_last_epoch):,.2f} R1\n"
  message += f"🔥 Total Burn: {(current_burn):,.2f} R1\n"
  plugin.send_message_to_user(user_id=plugin.cfg_chat_id, text=message)

  # Save the epoch review data to the cache and diskapi
  plugin.obj_cache[epoch_review_cache_key][last_epoch] = {
    "burned": current_burn,
    "poai_burned": current_poai_burn
  }
  plugin.P(f"Saving epoch review data to diskapi file {diskapi_epoch_review_file_name}...")
  plugin.diskapi_save_pickle_to_data(plugin.obj_cache.get(epoch_review_cache_key), diskapi_epoch_review_file_name)
  return


def reply(plugin: CustomPluginTemplate, message: str, user: str, chat_id: str):
  """
  This function is used to reply to a message. The given parameters are mandatory.
  It handles commands to watch and unwatch Ethereum wallets
  """
  watched_wallets_cache_key = f"ratio1_watched_wallets"
  diskapi_watched_wallets_file_name = "ratio1_watched_wallets_data.pkl"
  
  def handle_watch():
    user_watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key).get(chat_id, [])
    message_parts = message.split(" ")
    if len(message_parts) != 2:
      response = "Please provide your Ethereum Wallet address after the /watch command. Example: /watch 0xYourWalletAddress\n"
      if len(user_watched_wallets) > 0:
        response += "You are already watching the following wallets:\n"
        for wallet in user_watched_wallets:
          response += f"- {wallet}\n"
      else:
        response += "You are not watching any wallet currently."
      return response
    wallet_address = message_parts[1]
    if not plugin.bc.is_valid_eth_address(wallet_address):
      return f"Invalid node address: {wallet_address}. Please provide a valid Ethereum Wallet address."
    wallet_address = plugin.bc.eth_addr_to_checksum_address(wallet_address)
    if wallet_address in user_watched_wallets:
      return f"You are already watching the wallet {wallet_address}."
    
    user_watched_wallets.append(wallet_address)
    plugin.obj_cache[watched_wallets_cache_key][chat_id] = user_watched_wallets
    plugin.diskapi_save_pickle_to_data(plugin.obj_cache.get(watched_wallets_cache_key), diskapi_watched_wallets_file_name)
    return f"You are now watching the wallet {wallet_address}. You will receive notifications when your nodes are offline."

  def handle_unwatch():
    message_parts = message.split(" ")
    if len(message_parts) != 2:
      return "Please provide your Ethereum Wallet address after the /unwatch command. Example: /unwatch 0xYourWalletAddress"
    wallet_address = message_parts[1]
    wallet_address = plugin.bc.eth_addr_to_checksum_address(wallet_address)
    user_watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key).get(chat_id, [])

    if wallet_address not in user_watched_wallets:
      return f"You are not watching the wallet {wallet_address}."
    user_watched_wallets.remove(wallet_address)
    plugin.obj_cache[watched_wallets_cache_key][chat_id] = user_watched_wallets
    plugin.diskapi_save_pickle_to_data(plugin.obj_cache.get(watched_wallets_cache_key), diskapi_watched_wallets_file_name)
    return f"You are no longer watching the wallet {wallet_address}. You will not receive notifications for this wallet anymore."
  
  def handle_unwatchall():
    user_watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key).get(chat_id, [])
    if not user_watched_wallets:
      return "You are not watching any wallet."
    plugin.obj_cache[watched_wallets_cache_key][chat_id] = []
    plugin.diskapi_save_pickle_to_data(plugin.obj_cache.get(watched_wallets_cache_key), diskapi_watched_wallets_file_name)
    return "You have stopped watching all wallets."
  
  def handle_watchlist():
    user_watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key).get(chat_id, [])
    if not user_watched_wallets:
      return "You are not watching any wallet. Use /watch <wallet_address> to start watching a wallet."
    message = "You are currently watching the following wallets:\n"
    for wallet in user_watched_wallets:
      message += f"- {wallet}\n"
    return message
  
  def handle_network_status():
    nodes = plugin.netmon.available_nodes_prefixed
    if not nodes:
      return "No nodes are currently online."
    message = f"Total {len(nodes)} online  Ratio1 nodes reported by `{plugin.ee_id}`"
    return message
  
  def handle_nodes():
    user_watched_wallets = plugin.obj_cache.get(watched_wallets_cache_key).get(chat_id, [])
    if not user_watched_wallets:
      return "You are not watching any wallet. Use /watch <wallet_address> to start watching a wallet."
    message = "You are currently watching the following wallets and their nodes:\n"
    for wallet in user_watched_wallets:
      wallet_nodes = plugin.bc.get_wallet_nodes(wallet)
      message += f"{wallet}\n"
      for node in wallet_nodes:
        if node == "0x0000000000000000000000000000000000000000":
          continue
        node_internal_addr = plugin.bc.eth_addr_to_internal_addr(node)
        node_alias = plugin.netmon.network_node_eeid(node_internal_addr)
        node_is_online = plugin.netmon.network_node_is_online(node_internal_addr)
        short_node = node[:6] + "..." + node[-4:]
        message += f"  - {'🟢' if node_is_online else '🔴'} {node_alias} ({short_node})\n"
    return message
  
  def handle_start():
    return "Welcome to the Ratio1 Bot! Use /watch <wallet_address> to start watching your nodes. You will receive notifications when your nodes are offline."
  
  def hands_last_epoch_info():
    need_last_epoch_info = "need_last_epoch_info"
    if user in plugin.cfg_admins:
      plugin.obj_cache[need_last_epoch_info] = True
      msg = f"Hi Master {user}! Forcing last epoch info display."
    else:
      msg = f"Sorry {user}, you are not authorized to force last epoch info display."
    return msg

  # We do not want to reply to messages in the Ratio1 Community Group
  if str(chat_id) == str(plugin.cfg_chat_id):
    return
  
  # Handle the supported commands
  if message.startswith("/watchlist"):
    return handle_watchlist()
  if message.startswith("/watch"):
    return handle_watch()
  if message.startswith("/unwatchall"):
    return handle_unwatchall()
  if message.startswith("/unwatch"):
    return handle_unwatch()
  if message.startswith("/nodes"):
    return handle_nodes()
  if message.startswith("/network_status"):
    return handle_network_status()
  if message.startswith("/start"):    
    return handle_start()
  if message.startswith("/last_epoch_info"):    
    return hands_last_epoch_info()

  return "Please use the /watch command followed by your Ethereum Wallet address to start watching the nodes on your wallet."

if __name__ == "__main__":   
  PIPELINE_NAME = "ratio1_telegram_bot"

  session = Session() 

  node = os.getenv("RATIO1_NODE")
  chat_id = os.getenv("TELEGRAM_CHAT_ID")
  telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
  finished_with_error = False
  try:
    if chat_id is None or telegram_bot_token is None:
      raise ValueError("Please set the TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN environment variables.")
    else:
      session.P("Using environment variables for chat_id and telegram_bot_token.")

    session.P(f"Connecting to node: {node}")
    session.wait_for_node(node)
    
    COMMAND = "START" # "START" or "STOP"
    
    if COMMAND == "START":
      pipeline, _ = session.create_telegram_simple_bot(
        node=node,
        name=PIPELINE_NAME,
        telegram_bot_token=telegram_bot_token,
        chat_id=chat_id,
        message_handler=reply,
        processing_handler=loop_processing,
        admins=['401110073', '683223680'],
      )
      pipeline.deploy()
    elif COMMAND == "STOP":
      session.P("Stopping the bot from target node...")
      session.close_pipeline(node_addr=node, pipeline_name=PIPELINE_NAME)
    else:
      session.P("Invalid command. Use 'START' or 'STOP'.")
  except Exception as e:
    session.P(f"An error occurred: {e}", color="red")
    finished_with_error = True
  if not finished_with_error:
    session.P("Bot started successfully. Waiting for messages...")
    # Keep the session alive to process messages
    session.wait(seconds=10, close_session_on_timeout=True)
  else:
    session.P("Bot failed to start. Please check the logs for more details.", color="red")
    session.close()