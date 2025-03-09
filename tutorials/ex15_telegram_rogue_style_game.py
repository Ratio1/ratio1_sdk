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
  START_HEALTH = 10  # Increased from 5 for better gameplay

  # --------------------------------------------------
  # HELPER FUNCTIONS
  # --------------------------------------------------
  def generate_map():
    """Creates a 10x10 map with random 'COIN', 'TRAP', 'MONSTER', 'HEALTH', or 'EMPTY' tiles."""
    plugin.np.random.seed(sum(ord(char) for char in user))  # Create a seed based on user_id
    new_map = []
    for _ in plugin.np.arange(0, GRID_HEIGHT):
      row = []
      for _ in plugin.np.arange(0, GRID_WIDTH):
        # Add HEALTH potions and adjust probabilities
        tile_type = plugin.np.random.choice(["COIN", "EMPTY", "TRAP", "MONSTER", "HEALTH", "EMPTY", "EMPTY"], 
                                           p=[0.15, 0.4, 0.1, 0.1, 0.05, 0.2, 0.0])
        row.append({"type": tile_type, "visible": False})
      new_map.append(row)
    # Starting position is always safe
    new_map[0][0] = {"type": "EMPTY", "visible": True}
    return new_map

  def create_new_player():
    """Creates a new player dict with default stats."""
    return {"position": (0, 0), "coins": 0, "health": START_HEALTH, "level": 1, "kills": 0}

  def check_health(player):
    """Checks if the player's health is below 0 and returns a restart message if true."""
    if player["health"] <= 0:
      return True, "You have died! Game over.\nUse /start to play again."
    return False, ""

  def reveal_surroundings(player, game_map):
    """Reveals the tiles around the player."""
    x, y = player["position"]
    for dy in range(-1, 2):
      for dx in range(-1, 2):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
          game_map[ny][nx]["visible"] = True

  def visualize_map(player, game_map):
    """Creates a visual representation of the nearby map."""
    x, y = player["position"]
    view_distance = 2
    map_view = ""
    
    for ny in range(max(0, y - view_distance), min(GRID_HEIGHT, y + view_distance + 1)):
      for nx in range(max(0, x - view_distance), min(GRID_WIDTH, x + view_distance + 1)):
        if (nx, ny) == (x, y):
          map_view += "🧙 "  # Player
        elif game_map[ny][nx]["visible"]:
          tile_type = game_map[ny][nx]["type"]
          if tile_type == "COIN":
            map_view += "💰 "
          elif tile_type == "TRAP":
            map_view += "🔥 "
          elif tile_type == "MONSTER":
            map_view += "👹 "
          elif tile_type == "HEALTH":
            map_view += "❤️ "
          else:
            map_view += "⬜ "  # Empty
        else:
          map_view += "⬛ "  # Unexplored
      map_view += "\n"
    
    return map_view

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
    tile["visible"] = True
    reveal_surroundings(player, game_map)

    msg = f"You moved {direction} to ({x},{y}). "
    if tile["type"] == "COIN":
      coins_found = plugin.np.random.randint(1, 3)
      player["coins"] += coins_found
      tile["type"] = "EMPTY"
      msg += f"You found {coins_found} coin(s)! "
    elif tile["type"] == "TRAP":
      damage = plugin.np.random.randint(1, 3)
      player["health"] -= damage
      msg += f"You triggered a trap! Health -{damage}. "
    elif tile["type"] == "MONSTER":
      monster_level = min(player["level"] + plugin.np.random.randint(-1, 2), 1)
      damage = plugin.np.random.randint(1, 2 + monster_level)
      player["health"] -= damage
      player["kills"] += 1
      if player["kills"] % 3 == 0:
        player["level"] += 1
        msg += f"Level up! You are now level {player['level']}. "
      msg += f"A level {monster_level} monster attacked you! Health -{damage}. "
      tile["type"] = "EMPTY"
    elif tile["type"] == "HEALTH":
      heal_amount = plugin.np.random.randint(2, 5)
      player["health"] += heal_amount
      msg += f"You found a health potion! Health +{heal_amount}. "
      tile["type"] = "EMPTY"

    is_dead, death_msg = check_health(player)
    if is_dead:
      return death_msg

    map_view = visualize_map(player, game_map)
    stats = f"Coins: {player['coins']}, Health: {player['health']}, Level: {player['level']}"
    return f"{map_view}\n{msg}\n{stats}"

  # --------------------------------------------------
  try:
    # Remove debug code
    pass
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
    return ("Available Commands:\n" 
            "/start  - Restart the game\n" 
            "/move <up|down|left|right> - Move your character in a direction (or use WSAD keys)\n" 
            "/status - Display your current stats (position, health, coins, level, kills)\n" 
            "/map    - Reveal your current surroundings on the map")

  command = parts[0]

  if command == "/start":
    # Generate new map for new game
    plugin.obj_cache["shared_map"] = generate_map()
    plugin.obj_cache[user_id] = create_new_player()
    map_view = visualize_map(plugin.obj_cache[user_id], plugin.obj_cache["shared_map"])
    return f"Welcome to the Ratio1 Roguelike!\nUse /move <up|down|left|right> to explore.\nUse /status to check your stats.\n\n{map_view}"

  elif command == "/move":
    if len(parts) < 2:
      return "Usage: /move <up|down|left|right> (or you can use WSAD keys)"
    direction_input = parts[1]
    if direction_input in ["w", "a", "s", "d"]:
      mapping = {"w": "up", "a": "left", "s": "down", "d": "right"}
      direction = mapping[direction_input]
    else:
      direction = direction_input
    return move_player(player, direction, game_map)

  elif command in ["w", "a", "s", "d"]:
    mapping = {"w": "up", "a": "left", "s": "down", "d": "right"}
    return move_player(player, mapping[command], game_map)

  elif command == "/status":
    x, y = player["position"]
    return f"Position: ({x},{y})\nCoins: {player['coins']}\nHealth: {player['health']}\nLevel: {player['level']}\nKills: {player['kills']}"

  elif command == "/map":
    map_view = visualize_map(player, game_map)
    return f"Your surroundings:\n{map_view}"

  else:
    return ("Commands:\n"
            "/start  - Restart the game\n"
            "/move <up|down|left|right> - Move your character (or use WSAD keys)\n"
            "/status - Show your stats\n"
            "/map    - Show your surroundings")

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

