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
  
  # Shop items configuration
  SHOP_ITEMS = {
    "health_potion": {
      "name": "Health Potion 🧪",
      "description": "Restores 5 health points",
      "price": 5,
      "type": "consumable"
    },
    "sword": {
      "name": "Sword ⚔️",
      "description": "Increases your attack by 1 (reduces monster damage)",
      "price": 15,
      "type": "weapon",
      "attack_bonus": 1
    },
    "shield": {
      "name": "Shield 🛡️",
      "description": "Adds 10% damage reduction",
      "price": 20,
      "type": "armor",
      "damage_reduction_bonus": 0.1
    },
    "amulet": {
      "name": "Magic Amulet 🔮",
      "description": "Increases max health by 3",
      "price": 25,
      "type": "accessory",
      "max_health_bonus": 3
    },
    "boots": {
      "name": "Speed Boots 👢",
      "description": "5% chance to avoid all damage",
      "price": 30,
      "type": "accessory",
      "dodge_chance": 0.05
    },
    "map_scroll": {
      "name": "Map Scroll 📜",
      "description": "Reveals more of the map when used",
      "price": 10,
      "type": "consumable"
    }
  }

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
        "damage_reduction": 0,
        "attack": 0,
        "dodge_chance": 0,
        "inventory": {
            "health_potion": 0,
            "map_scroll": 0
        },
        "equipment": {
            "weapon": None,
            "armor": None,
            "accessory": []
        }
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
          
  def reveal_extended_map(player, game_map):
    """Reveals a larger portion of the map (used by map scroll)."""
    x, y = player["position"]
    for dy in range(-3, 4):
      for dx in range(-3, 4):
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
      # Check for dodge chance from equipment
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
          msg += "You nimbly avoided a trap! "
      else:
          base_damage = plugin.np.random.randint(1, 3)
          # Apply damage reduction from level and equipment
          damage = max(1, int(base_damage * (1 - player["damage_reduction"])))
          player["health"] -= damage
          msg += f"You triggered a trap! Health -{damage}. "
      
    elif tile["type"] == "MONSTER":
      monster_level = tile["monster_level"]
      
      # Check for dodge chance from equipment
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
          msg += f"You dodged the monster's attack! "
      else:
          # Monster deals damage based on its level, reduced by player's attack
          effective_monster_level = max(1, monster_level - player["attack"])
          base_damage = plugin.np.random.randint(1, 2 + effective_monster_level)
          
          # Apply damage reduction from player level and equipment
          damage = max(1, int(base_damage * (1 - player["damage_reduction"])))
          player["health"] -= damage
          
          # Include attack info in message
          if player["attack"] > 0:
              msg += f"Your attack reduced monster effectiveness! "
              
          msg += f"A level {monster_level} monster attacked you! Health -{damage}. "
      
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
          
      msg += f"You killed a level {monster_level} monster {monster_emoji}! You gained {xp_gained} XP!"
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

  def display_shop(player):
    """Displays the shop menu with available items."""
    shop_text = "🏪 SHOP 🏪\n\n"
    shop_text += f"Your coins: {player['coins']} 💰\n\n"
    shop_text += "Available Items:\n"
    
    for item_id, item in SHOP_ITEMS.items():
      can_afford = "✅" if player["coins"] >= item["price"] else "❌"
      shop_text += f"{item['name']} - {item['price']} coins {can_afford}\n"
      shop_text += f"  {item['description']}\n"
    
    shop_text += "\nTo purchase an item, use /buy <item_name>"
    shop_text += "\nAvailable items: health_potion, sword, shield, amulet, boots, map_scroll"
    return shop_text
    
  def buy_item(player, item_id):
    """Process the purchase of an item."""
    if item_id not in SHOP_ITEMS:
      return f"Item '{item_id}' not found in the shop."
    
    item = SHOP_ITEMS[item_id]
    
    # Check if player has enough coins
    if player["coins"] < item["price"]:
      return f"You don't have enough coins. You need {item['price']} coins but only have {player['coins']}."
    
    # Process the purchase based on item type
    if item["type"] == "consumable":
      player["inventory"][item_id] += 1
      msg = f"You purchased {item['name']}. It's in your inventory."
    
    elif item["type"] == "weapon":
      # Replace existing weapon
      old_weapon = player["equipment"]["weapon"]
      if old_weapon:
        # Remove old weapon bonuses
        player["attack"] -= SHOP_ITEMS[old_weapon]["attack_bonus"]
      
      player["equipment"]["weapon"] = item_id
      player["attack"] += item["attack_bonus"]
      msg = f"You equipped {item['name']}! Your attack is now {player['attack']}."
    
    elif item["type"] == "armor":
      # Replace existing armor
      old_armor = player["equipment"]["armor"]
      if old_armor:
        # Remove old armor bonuses
        player["damage_reduction"] -= SHOP_ITEMS[old_armor]["damage_reduction_bonus"]
      
      player["equipment"]["armor"] = item_id
      player["damage_reduction"] += item["damage_reduction_bonus"]
      msg = f"You equipped {item['name']}! Your damage reduction is now {int(player['damage_reduction'] * 100)}%."
    
    elif item["type"] == "accessory":
      # Add to accessories (allowing multiple)
      if item_id in player["equipment"]["accessory"]:
        return f"You already have {item['name']}."
      
      player["equipment"]["accessory"].append(item_id)
      
      # Apply accessory bonuses
      if "max_health_bonus" in item:
        player["max_health"] += item["max_health_bonus"]
        msg = f"You equipped {item['name']}! Your max health is now {player['max_health']}."
      elif "dodge_chance" in item:
        player["dodge_chance"] += item["dodge_chance"]
        msg = f"You equipped {item['name']}! Your dodge chance is now {int(player['dodge_chance'] * 100)}%."
      else:
        msg = f"You equipped {item['name']}!"
    
    # Deduct coins
    player["coins"] -= item["price"]
    
    return f"{msg}\nYou have {player['coins']} coins remaining."
    
  def use_item(player, item_id, game_map):
    """Use a consumable item from inventory."""
    if item_id not in player["inventory"] or player["inventory"][item_id] <= 0:
      return f"You don't have any {item_id} in your inventory."
    
    if item_id == "health_potion":
      if player["health"] >= player["max_health"]:
        return "Your health is already full!"
      
      # Use health potion
      heal_amount = 5
      old_health = player["health"]
      player["health"] = min(player["max_health"], player["health"] + heal_amount)
      player["inventory"][item_id] -= 1
      
      return f"You used a Health Potion. Health: {old_health} → {player['health']}"
    
    elif item_id == "map_scroll":
      # Use map scroll to reveal a larger area
      reveal_extended_map(player, game_map)
      player["inventory"][item_id] -= 1
      
      map_view = visualize_map(player, game_map)
      return f"You used a Map Scroll and revealed more of the map!\n\n{map_view}"
    
    return f"Cannot use {item_id}."

  def display_help():
    """Returns extended help instructions."""
    help_text = ("Welcome to the Ratio1 Roguelike!\n"
                 "Instructions:\n"
                 "- Explore the dungeon using /move (or WSAD keys).\n"
                 "- Check your stats with /status to see health, coins, XP, level, attack, and equipment.\n"
                 "- Defeat monsters to earn XP and level up.\n"
                 "- Collect coins and visit the shop (/shop) to buy upgrades using /buy.\n"
                 "- Use consumable items from your inventory with /use.\n"
                 "- View the map with /map.\n"
                 "\nAvailable Commands:\n"
                 "1. /start  - Restart the game and begin your epic adventure.\n"
                 "2. /move <up|down|left|right> - Move your character (WSAD keys supported).\n"
                 "3. /status - Display your current stats.\n"
                 "4. /map    - View your surroundings on the map.\n"
                 "5. /shop   - Browse the shop and buy upgrades/items.\n"
                 "6. /buy <item_name> - Purchase an item from the shop.\n"
                 "7. /use <item_name> - Use a consumable from your inventory.\n"
                 "8. /help   - Display this help message.")
    return help_text

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
            "1. /start  - Restart the game and begin your epic adventure.\n" 
            "2. /move <up|down|left|right> - Move your character in the specified direction (WSAD keys supported).\n" 
            "3. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n" 
            "4. /map    - View the map of your surroundings.\n" 
            "5. /shop   - Visit the shop to browse and buy upgrades/items.\n" 
            "6. /buy <item_name> - Purchase an item from the shop.\n" 
            "7. /use <item_name> - Use a consumable item from your inventory (e.g., health_potion, map_scroll).\n" 
            "8. /help   - Display help information.")

  command = parts[0]

  if command == "/start":
    # Generate new map for new game
    plugin.obj_cache["shared_map"] = generate_map()
    plugin.obj_cache[user_id] = create_new_player()
    map_view = visualize_map(plugin.obj_cache[user_id], plugin.obj_cache["shared_map"])
    return ("Welcome to the Ratio1 Roguelike!\n" 
            "This is an epic roguelike adventure where you explore a dangerous dungeon, defeat monsters, collect coins, earn XP, and purchase upgrades from the shop.\n" 
            "Use /move <up|down|left|right> to explore, /status to check your stats, and /shop to buy upgrades.\n" 
            "For more detailed instructions, use /help.\n\n" 
            f"{map_view}")

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
    status = f"Position: ({x},{y})\n" \
           f"Health: {player['health']}/{player['max_health']}\n" \
           f"Coins: {player['coins']}\n" \
           f"Level: {player['level']} ({player['xp']}/{player['next_level_xp']} XP)\n"
    
    # Add combat stats
    status += f"Attack: {player['attack']}\n" \
             f"Damage Reduction: {int(player['damage_reduction'] * 100)}%\n"
    
    if player["dodge_chance"] > 0:
      status += f"Dodge Chance: {int(player['dodge_chance'] * 100)}%\n"
    
    status += f"Kills: {player['kills']}\n\n"
    
    # Equipment
    status += "Equipment:\n"
    if player["equipment"]["weapon"]:
      status += f"- Weapon: {SHOP_ITEMS[player['equipment']['weapon']]['name']}\n"
    else:
      status += "- Weapon: None\n"
      
    if player["equipment"]["armor"]:
      status += f"- Armor: {SHOP_ITEMS[player['equipment']['armor']]['name']}\n"
    else:
      status += "- Armor: None\n"
    
    if player["equipment"]["accessory"]:
      status += "- Accessories:\n"
      for acc in player["equipment"]["accessory"]:
        status += f"  - {SHOP_ITEMS[acc]['name']}\n"
    else:
      status += "- Accessories: None\n"
    
    # Inventory
    status += "\nInventory:\n"
    has_items = False
    for item_id, count in player["inventory"].items():
      if count > 0:
        status += f"- {SHOP_ITEMS[item_id]['name']}: {count}\n"
        has_items = True
    
    if not has_items:
      status += "No items\n"
      
    status += "\nUse /shop to buy equipment and items!"
    
    return status

  elif command == "/map":
    map_view = visualize_map(player, game_map)
    return f"Your surroundings:\n{map_view}"
    
  elif command == "/shop":
    return display_shop(player)
    
  elif command == "/buy":
    if len(parts) < 2:
      return "Usage: /buy <item_name>\nUse /shop to see available items."
    
    item_id = parts[1].lower()
    return buy_item(player, item_id)
    
  elif command == "/use":
    if len(parts) < 2:
      return "Usage: /use <item_name>\nItems you can use: health_potion, map_scroll"
    
    item_id = parts[1].lower()
    return use_item(player, item_id, game_map)

  elif command == "/help":
    return display_help()

  else:
    return ("Commands:\n"
            "/start  - Restart the game and start a new adventure\n" 
            "/move <up|down|left|right> - Move your character (WSAD keys also supported)\n" 
            "/status - Display your current stats: position, health, coins, level, XP, damage reduction, and kills\n" 
            "/map    - Reveal the map of your surroundings\n"
            "/shop   - Visit the shop to buy upgrades and items\n" 
            "/buy <item_name> - Purchase an item from the shop\n" 
            "/use <item_name> - Use a consumable item from your inventory\n" 
            "/help   - Display this help message")

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

