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
  # XP requirements for each level
  LEVEL_XP_REQUIREMENTS = [0, 10, 25, 45, 70, 100, 140, 190, 250, 320]
  # Stats increase per level
  HEALTH_PER_LEVEL = 2
  DAMAGE_REDUCTION_PER_LEVEL = 0.05  # 5% damage reduction per level
  MAX_LEVEL = 10

  # --------------------------------------------------
  # HELPER FUNCTIONS
  # --------------------------------------------------
  def generate_map():
    """Creates a 10x10 map with random 'COIN', 'TRAP', 'MONSTER', 'HEALTH', or 'EMPTY' tiles."""
    plugin.np.random.seed(sum(ord(char) for char in user))  # Create a seed based on user_id
    new_map = []
    for y in plugin.np.arange(0, GRID_HEIGHT):
      row = []
      for x in plugin.np.arange(0, GRID_WIDTH):
        # Deeper parts of the map have stronger monsters and better rewards
        distance_from_start = ((x)**2 + (y)**2)**0.5
        depth_factor = min(distance_from_start / 14, 1.0)  # Normalized 0-1
        
        # Adjust probabilities based on depth
        coin_prob = 0.15 + (0.05 * depth_factor)  # More coins deeper
        trap_prob = 0.1 + (0.05 * depth_factor)  # More traps deeper
        monster_prob = 0.1 + (0.1 * depth_factor)  # More monsters deeper
        health_prob = 0.05
        empty_prob = 1 - (coin_prob + trap_prob + monster_prob + health_prob)
        
        tile_type = plugin.np.random.choice(
            ["COIN", "TRAP", "MONSTER", "HEALTH", "EMPTY"], 
            p=[coin_prob, trap_prob, monster_prob, health_prob, empty_prob]
        )
        
        # Set monster level based on map depth
        monster_level = 1
        if tile_type == "MONSTER":
            base_level = max(1, int(depth_factor * 5))
            variation = plugin.np.random.randint(-1, 2)
            monster_level = max(1, base_level + variation)
        
        row.append({
            "type": tile_type, 
            "visible": False, 
            "monster_level": monster_level if tile_type == "MONSTER" else 0
        })
      new_map.append(row)
    # Starting position is always safe
    new_map[0][0] = {"type": "EMPTY", "visible": True, "monster_level": 0}
    return new_map

  def create_new_player():
    """Creates a new player dict with default stats."""
    return {
        "position": (0, 0), 
        "coins": 0, 
        "health": START_HEALTH, 
        "level": 1, 
        "max_health": START_HEALTH,
        "xp": 0,
        "next_level_xp": LEVEL_XP_REQUIREMENTS[1],
        "kills": 0,
        "damage_reduction": 0
    }

  def check_health(player):
    """Checks if the player's health is below 0 and returns a restart message if true."""
    if player["health"] <= 0:
      return True, "You have died! Game over.\nUse /start to play again."
    return False, ""
    
  def check_level_up(player):
    """Checks if player has enough XP to level up and applies level up benefits."""
    if player["level"] >= MAX_LEVEL:
        return False, ""
        
    if player["xp"] >= player["next_level_xp"]:
        player["level"] += 1
        old_max_health = player["max_health"]
        player["max_health"] += HEALTH_PER_LEVEL
        player["health"] += HEALTH_PER_LEVEL  # Heal on level up
        player["damage_reduction"] += DAMAGE_REDUCTION_PER_LEVEL
        
        # Set next level XP requirement
        if player["level"] < len(LEVEL_XP_REQUIREMENTS):
            player["next_level_xp"] = LEVEL_XP_REQUIREMENTS[player["level"]]
        else:
            # For levels beyond our predefined table, increase by 30%
            player["next_level_xp"] = int(player["next_level_xp"] * 1.3)
            
        return True, f"LEVEL UP! You are now level {player['level']}!\n" \
                    f"Max Health: {old_max_health} → {player['max_health']}\n" \
                    f"Damage Reduction: {int((player['damage_reduction'] - DAMAGE_REDUCTION_PER_LEVEL) * 100)}% → {int(player['damage_reduction'] * 100)}%"
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
            # Different monster emoji based on level
            monster_level = game_map[ny][nx]["monster_level"]
            if monster_level <= 2:
                map_view += "👹 "  # Regular monster
            elif monster_level <= 4:
                map_view += "👺 "  # Stronger monster
            else:
                map_view += "👿 "  # Boss monster
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
    level_up_msg = ""
    
    if tile["type"] == "COIN":
      coins_found = plugin.np.random.randint(1, 3 + player["level"] // 2)
      player["coins"] += coins_found
      tile["type"] = "EMPTY"
      msg += f"You found {coins_found} coin(s)! "
      
    elif tile["type"] == "TRAP":
      base_damage = plugin.np.random.randint(1, 3)
      # Apply damage reduction from level
      damage = max(1, int(base_damage * (1 - player["damage_reduction"])))
      player["health"] -= damage
      msg += f"You triggered a trap! Health -{damage}. "
      
    elif tile["type"] == "MONSTER":
      monster_level = tile["monster_level"]
      # Monster deals damage based on its level
      base_damage = plugin.np.random.randint(1, 2 + monster_level)
      # Apply damage reduction from player level
      damage = max(1, int(base_damage * (1 - player["damage_reduction"])))
      player["health"] -= damage
      
      # XP gained based on monster level
      xp_gained = monster_level * 3 + plugin.np.random.randint(0, 3)
      player["xp"] += xp_gained
      player["kills"] += 1
      
      # Check for level up
      did_level_up, level_up_message = check_level_up(player)
      if did_level_up:
          level_up_msg = level_up_message + "\n"
      
      monster_emoji = "👹"
      if monster_level > 2 and monster_level <= 4:
          monster_emoji = "👺"
      elif monster_level > 4:
          monster_emoji = "👿"
          
      msg += f"A level {monster_level} monster {monster_emoji} attacked you! Health -{damage}. " \
             f"You gained {xp_gained} XP!"
      tile["type"] = "EMPTY"
      
    elif tile["type"] == "HEALTH":
      heal_amount = plugin.np.random.randint(2, 5)
      player["health"] = min(player["max_health"], player["health"] + heal_amount)
      msg += f"You found a health potion! Health +{heal_amount}. "
      tile["type"] = "EMPTY"

    is_dead, death_msg = check_health(player)
    if is_dead:
      return death_msg

    map_view = visualize_map(player, game_map)
    stats = f"Health: {player['health']}/{player['max_health']}, Coins: {player['coins']}\n" \
           f"Level: {player['level']}, XP: {player['xp']}/{player['next_level_xp']}"
    return f"{map_view}\n{level_up_msg}{msg}\n{stats}"

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
            "/start  - Restart the game and start a new adventure\n" 
            "/move <up|down|left|right> - Move your character (WSAD keys also supported)\n" 
            "/status - Display your current stats: position, health, coins, level, XP, damage reduction, and kills\n" 
            "/map    - Reveal the map of your surroundings")

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
    return f"Position: ({x},{y})\n" \
           f"Health: {player['health']}/{player['max_health']}\n" \
           f"Coins: {player['coins']}\n" \
           f"Level: {player['level']} ({player['xp']}/{player['next_level_xp']} XP)\n" \
           f"Damage Reduction: {int(player['damage_reduction'] * 100)}%\n" \
           f"Kills: {player['kills']}"

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

