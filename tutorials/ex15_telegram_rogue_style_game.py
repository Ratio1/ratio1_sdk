#!/usr/bin/env python3

import os
import logging
from ratio1 import Session, CustomPluginTemplate

"""
Telegram roguelike bot using the same pipeline approach as Blackjack:
- Uses `plugin.obj_cache` to store user data in memory.
- No persistent storage (resets on bot restart).
- Requires three-argument `reply(plugin, message, user)`, as per the Blackjack example.
"""


# --------------------------------------------------
# CREATE RATIO1 SESSION & TELEGRAM BOT
# --------------------------------------------------
session = Session()  # Uses .ratio1 config or env variables

def reply(plugin: CustomPluginTemplate, message: str, user: str):
  # --------------------------------------------------
  # GAME CONSTANTS
  # --------------------------------------------------
  GRID_WIDTH = 10
  GRID_HEIGHT = 10

  # --------------------------------------------------
  # HELPER FUNCTIONS
  # --------------------------------------------------
  def generate_map():
    """Creates a 5x5 map with random 'COIN', 'TRAP', 'MONSTER', or 'EMPTY' tiles."""
    seed = sum(ord(char) for char in user)  # Create a seed based on user_id
    new_map = []
    for _ in plugin.np.arange(0, GRID_HEIGHT):
      row = []
      for _ in plugin.np.arange(0, GRID_WIDTH):
        tile_type = ["COIN", "EMPTY", "TRAP", "MONSTER", "EMPTY"][plugin.np.random.randint(0, 5)]
        row.append({"type": tile_type})
      new_map.append(row)
    return new_map
  print(generate_map())
  def create_new_player():
    """Creates a new player dict with default stats."""
    return {"position": (0, 0), "coins": 0, "health": 5}

  def move_player(player, direction, game_map):
    """
    Moves the player, applies tile effects, and returns a response message.
    """
    x, y = player["position"]

    if direction == "up" and y > 0:
      y -= 1
    elif direction == "down" and y < GRID_HEIGHT - 1:
      y += 1
    elif direction == "left" and x > 0:
      x -= 1
    elif direction == "right" and x < GRID_WIDTH - 1:
      x += 1
    else:
      return "You cannot move that way!"

    player["position"] = (x, y)
    tile = game_map[y][x]
    tile_type = tile["type"]

    msg = f"You moved {direction} to ({x},{y}). "
    if tile_type == "COIN":
      player["coins"] += 1
      tile["type"] = "EMPTY"
      msg += "You found a coin! "
    elif tile_type == "TRAP":
      player["health"] -= 1
      msg += "You triggered a trap! Health -1. "
    elif tile_type == "MONSTER":
      player["health"] -= 2
      msg += "A monster attacked you! Health -2. "

    msg += f"Coins: {player['coins']}, Health: {player['health']}."
    return msg
  # --------------------------------------------------
  try:
    a = plugin.np.arange(0, GRID_HEIGHT)
    print(a)
  except Exception as e:
    print(e)

  text = (message or "").strip().lower()
  user_id = str(user)

  # ---------------------------
  # Ensure shared game map exists
  # ---------------------------
  if "shared_map" not in plugin.obj_cache:
    plugin.obj_cache["shared_map"] = generate_map()

  game_map = plugin.obj_cache["shared_map"]

  # ---------------------------
  # Ensure player data exists
  # ---------------------------
  if user_id not in plugin.obj_cache or plugin.obj_cache[user_id] is None:
    plugin.obj_cache[user_id] = create_new_player()

  player = plugin.obj_cache[user_id]

  # ---------------------------
  # Command Handling
  # ---------------------------
  parts = text.split()
  if not parts:
    return "Commands:\n/start - Start the game\n/move <up|down|left|right>\n/status - Show stats"

  command = parts[0]

  if command == "/start":
    plugin.obj_cache[user_id] = create_new_player()
    return "Welcome to the Ratio1 Roguelike!\nUse /move <up|down|left|right> to explore.\nUse /status to check your stats."

  elif command == "/move":
    if len(parts) < 2:
      return "Usage: /move <up|down|left|right>"
    direction = parts[1]
    return move_player(player, direction, game_map)

  elif command == "/status":
    x, y = player["position"]
    return f"Position: ({x},{y})\nCoins: {player['coins']}\nHealth: {player['health']}"

  else:
    return "Commands:\n/start - Start the game\n/move <up|down|left|right>\n/status - Show stats"


# --------------------------------------------------
# MAIN FUNCTION (BOT STARTUP)
# --------------------------------------------------
if __name__ == "__main__":
  session = Session()

  # assume .env is available and will be used for the connection and tokens
  # NOTE: When working with SDK please use the nodes internal addresses. While the EVM address of the node
  #       is basically based on the same sk/pk it is in a different format and not directly usable with the SDK
  #       the internal node address is easily spoted as starting with 0xai_ and can be found
  #       via `docker exec r1node get_node_info` or via the launcher UI
  my_node = os.getenv("EE_TARGET_NODE")  # we can specify a node here, if we want to connect to a specific
  telegram_bot_token = os.getenv("EE_TELEGRAM_BOT_TOKEN")  # we can specify a node here, if we want to connect to a specific

  assert my_node is not None, "Please provide the target edge node identifier"
  assert telegram_bot_token is not None, "Please provide the telegram bot token"

  session.wait_for_node(my_node)  # wait for the node to be active

  # unlike the previous example, we are going to use the token from the environment
  # and deploy the app on the target node and leave it there
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="roguelike_bot",
    message_handler=reply,
    telegram_bot_token=telegram_bot_token,
  )

  pipeline.deploy()  # we deploy the pipeline

  # Observation:
  #   next code is not mandatory - it is used to keep the session open and cleanup the resources
  #   due to the fact that this is a example/tutorial and maybe we dont want to keep the pipeline
  #   active after the session is closed we use close_pipelines=True
  #   in production, you would not need this code as the script can close
  #   after the pipeline will be sent
  session.wait(
    seconds=600,  # we wait the session for 10 minutes
    close_pipelines=True,  # we close the pipelines after the session
    close_session=True,  # we close the session after the session
  )

