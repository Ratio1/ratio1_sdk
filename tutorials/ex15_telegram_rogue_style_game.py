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
  plugin.P('REPLY!!')
  plugin.P(message)
  # --------------------------------------------------
  # GAME CONSTANTS
  # --------------------------------------------------
  GRID_WIDTH = 100
  GRID_HEIGHT = 100
  MAX_LEVEL = 10

  # Player stats for each level
  LEVEL_DATA = {
    # Level: {max_hp, max_energy, next_level_xp, hp_regen_rate, energy_regen_rate, damage_reduction}
    # hp_regen_rate and energy_regen_rate are per minute
    1: {"max_hp": 10, "max_energy": 20, "next_level_xp": 10, "hp_regen_rate": 3, "energy_regen_rate": 6, "damage_reduction": 0.00},
    2: {"max_hp": 12, "max_energy": 22, "next_level_xp": 25, "hp_regen_rate": 3.6, "energy_regen_rate": 7.2, "damage_reduction": 0.05},
    3: {"max_hp": 14, "max_energy": 24, "next_level_xp": 45, "hp_regen_rate": 4.2, "energy_regen_rate": 8.4, "damage_reduction": 0.10},
    4: {"max_hp": 16, "max_energy": 26, "next_level_xp": 70, "hp_regen_rate": 4.8, "energy_regen_rate": 9.6, "damage_reduction": 0.15},
    5: {"max_hp": 18, "max_energy": 28, "next_level_xp": 100, "hp_regen_rate": 5.4, "energy_regen_rate": 10.8, "damage_reduction": 0.20},
    6: {"max_hp": 20, "max_energy": 30, "next_level_xp": 140, "hp_regen_rate": 6, "energy_regen_rate": 12, "damage_reduction": 0.25},
    7: {"max_hp": 22, "max_energy": 32, "next_level_xp": 190, "hp_regen_rate": 6.6, "energy_regen_rate": 13.2, "damage_reduction": 0.30},
    8: {"max_hp": 24, "max_energy": 34, "next_level_xp": 250, "hp_regen_rate": 7.2, "energy_regen_rate": 14.4, "damage_reduction": 0.35},
    9: {"max_hp": 26, "max_energy": 36, "next_level_xp": 320, "hp_regen_rate": 7.8, "energy_regen_rate": 15.6, "damage_reduction": 0.40},
    10: {"max_hp": 28, "max_energy": 40, "next_level_xp": 400, "hp_regen_rate": 9, "energy_regen_rate": 18, "damage_reduction": 0.45},
  }

  # Energy costs for actions
  ENERGY_COSTS = {
    "move": 1,     # Basic movement
    "attack": 3,   # Fighting a monster
    "shop": 0,     # Checking the shop (free)
    "use_item": 2  # Using an item
  }

  # --------------------------------------------------
  # SHOP FUNCTIONS
  # --------------------------------------------------
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
    """Creates a 100x100 map with random 'COIN', 'TRAP', 'MONSTER', 'HEALTH', or 'EMPTY' tiles."""
    plugin.P(f"Starting map generation for a {GRID_WIDTH}x{GRID_HEIGHT} grid")
    start_time = plugin.time()
    
    # Use fixed probabilities for a balanced 100x100 map
    coin_prob = 0.10
    trap_prob = 0.10
    monster_prob = 0.15
    health_prob = 0.05
    empty_prob = 1 - (coin_prob + trap_prob + monster_prob + health_prob)  # 0.60
    
    plugin.P(f"Tile distribution - Coin: {coin_prob*100}%, Trap: {trap_prob*100}%, Monster: {monster_prob*100}%, Health: {health_prob*100}%, Empty: {empty_prob*100}%")

    new_map = []
    plugin.P("Starting to populate map rows...")
    
    # Track tile distribution for logging
    tile_counts = {"COIN": 0, "TRAP": 0, "MONSTER": 0, "HEALTH": 0, "EMPTY": 0}
    
    for y in plugin.np.arange(0, GRID_HEIGHT):
      if y % 10 == 0:
        plugin.P(f"Generating row {y}/{GRID_HEIGHT}...")
        
      row = []
      for x in plugin.np.arange(0, GRID_WIDTH):
        tile_type = plugin.np.random.choice(
            ["COIN", "TRAP", "MONSTER", "HEALTH", "EMPTY"],
            p=[coin_prob, trap_prob, monster_prob, health_prob, empty_prob]
        )
        tile_counts[tile_type] += 1
        
        # For monsters, use a constant level of 1
        monster_level = 1
        row.append({
            "type": tile_type,
            "visible": False,
            "monster_level": monster_level if tile_type == "MONSTER" else 0
        })
      new_map.append(row)
    
    # Set starting point to empty and visible
    new_map[0][0] = {"type": "EMPTY", "visible": True, "monster_level": 0}
    
    # Log tile distribution statistics
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    plugin.P(f"Map generation complete! Generated {total_tiles} tiles in {plugin.time() - start_time:.2f} seconds")
    plugin.P(f"Tile distribution summary:")
    for tile_type, count in tile_counts.items():
      percentage = (count / total_tiles) * 100
      plugin.P(f"  {tile_type}: {count} tiles ({percentage:.2f}%)")
    
    return new_map

  def create_new_player():
    """Creates a new player dict with default stats."""
    level_1_data = LEVEL_DATA[1]
    return {
        "position": (0, 0),
        "coins": 0,
        "health": level_1_data["max_hp"],
        "max_health": level_1_data["max_hp"],
        "energy": level_1_data["max_energy"],
        "max_energy": level_1_data["max_energy"],
        "damage_reduction": level_1_data["damage_reduction"],
        "attack": 0,
        "dodge_chance": 0,
        "level": 1,
        "xp": 0,
        "next_level_xp": level_1_data["next_level_xp"],
        "hp_regen_rate": level_1_data["hp_regen_rate"],
        "energy_regen_rate": level_1_data["energy_regen_rate"],
        "last_update_time": plugin.time(),  # Track last update for regeneration with correct function
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
        old_level = player["level"]
        player["level"] += 1
        new_level = player["level"]
        
        # Get stats for the new level
        if new_level in LEVEL_DATA:
            level_data = LEVEL_DATA[new_level]
            
            # Store old stats for message
            old_max_health = player["max_health"]
            old_max_energy = player["max_energy"]
            old_hp_regen = player["hp_regen_rate"]
            old_energy_regen = player["energy_regen_rate"]
            old_damage_reduction = player["damage_reduction"]
            
            # Update stats based on new level data
            player["max_health"] = level_data["max_hp"]
            player["max_energy"] = level_data["max_energy"]
            player["next_level_xp"] = level_data["next_level_xp"]
            player["hp_regen_rate"] = level_data["hp_regen_rate"]
            player["energy_regen_rate"] = level_data["energy_regen_rate"]
            player["damage_reduction"] = level_data["damage_reduction"]
            
            # Also heal the player on level up (bonus!)
            player["health"] = min(player["health"] + 5, player["max_health"])
            player["energy"] = player["max_energy"]  # Refill energy on level up
            
            return True, f"LEVEL UP! You are now level {player['level']}!\n" \
                        f"Max Health: {old_max_health} → {player['max_health']}\n" \
                        f"Max Energy: {old_max_energy} → {player['max_energy']}\n" \
                        f"HP Regen: {old_hp_regen:.1f}/min → {player['hp_regen_rate']:.1f}/min\n" \
                        f"Energy Regen: {old_energy_regen:.1f}/min → {player['energy_regen_rate']:.1f}/min\n" \
                        f"Damage Reduction: {int(old_damage_reduction * 100)}% → {int(player['damage_reduction'] * 100)}%"
        else:
            # For levels beyond our predefined table
            player["max_health"] += 2
            player["max_energy"] += 2
            player["next_level_xp"] = int(player["next_level_xp"] * 1.3)
            player["hp_regen_rate"] += 0.01
            player["energy_regen_rate"] += 0.02
            
            # Increment damage reduction by 5% for levels beyond our table
            old_damage_reduction = player["damage_reduction"]
            player["damage_reduction"] += 0.05
            
            return True, f"LEVEL UP! You are now level {player['level']}!\n" \
                        f"Max Health +2, Max Energy +2\n" \
                        f"HP Regen +0.01/s, Energy Regen +0.02/s\n" \
                        f"Damage Reduction: {int(old_damage_reduction * 100)}% → {int(player['damage_reduction'] * 100)}%"
            
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

  def check_exploration_progress(game_map):
    """Calculates the percentage of the map that has been explored (for informational purposes only)."""
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    visible_tiles = sum(1 for row in game_map for tile in row if tile["visible"])
    return (visible_tiles / total_tiles) * 100

  def visualize_map(player, game_map):
    """Creates a visual representation of the nearby map."""
    x, y = player["position"]
    view_distance = 2
    map_view = f"🗺️ Your location: ({x}, {y}) | Map size: {GRID_WIDTH}×{GRID_HEIGHT}\n\n"

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

    # Add map exploration stats
    exploration = check_exploration_progress(game_map)
    map_view += f"Map Exploration: {int(exploration)}%"
    
    return map_view

  def move_player(player, direction, game_map):
    """
    Moves the player, applies tile effects, and returns a response message.
    Checks for and consumes energy for different actions.
    """
    # Check if player has enough energy for the basic move
    if player["energy"] < ENERGY_COSTS["move"]:
      return f"You are too exhausted to move! Energy: {int(player['energy'])}/{player['max_energy']}\nWait for your energy to regenerate."

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

    # Calculate energy cost for this move
    energy_cost = ENERGY_COSTS["move"]
    
    # Check what's on the tile we're moving to
    new_tile = game_map[y][x]
    if new_tile["type"] == "MONSTER":
      # Fighting a monster requires more energy
      if player["energy"] < ENERGY_COSTS["move"] + ENERGY_COSTS["attack"]:
        return f"You don't have enough energy to fight the monster at ({x},{y})!\nEnergy: {int(player['energy'])}/{player['max_energy']}\nWait for your energy to regenerate."
      energy_cost += ENERGY_COSTS["attack"]

    # Consume energy
    player["energy"] -= energy_cost
    
    # Actually move the player
    player["position"] = (x, y)
    tile = game_map[y][x]
    tile["visible"] = True
    reveal_surroundings(player, game_map)

    # Basic movement message
    msg = f"You moved {direction} to ({x},{y}). Energy: -{energy_cost} "
    
    level_up_msg = ""
    
    if tile["type"] == "COIN":
      base_coins = plugin.np.random.randint(1, 3)
      player["coins"] += base_coins
      tile["type"] = "EMPTY"
      msg += f"You found {base_coins} coin(s)! "

    elif tile["type"] == "TRAP":
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
        msg += "You nimbly avoided a trap! "
      else:
        base_damage = plugin.np.random.randint(1, 3)
        damage = max(1, base_damage)
        player["health"] -= damage
        msg += f"You triggered a trap! Health -{damage}. "

    elif tile["type"] == "MONSTER":
      monster_level = tile["monster_level"]
      base_damage = plugin.np.random.randint(1, 3) + monster_level
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
        msg += "You dodged the monster's attack! "
        final_damage = 0
      else:
        final_damage = base_damage
      if final_damage > 0:
        player["health"] -= final_damage
        msg += f"You took {final_damage} damage. "

      # Award XP based on monster level
      xp_gained = monster_level * 2
      player["xp"] += xp_gained
      msg += f"You defeated a monster! +{xp_gained} XP!"
      
      # Check for level up
      leveled_up, level_up_msg = check_level_up(player)
      if leveled_up:
        msg += " " + level_up_msg
          
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
    stats = f"Health: {int(player['health'])}/{player['max_health']}, Energy: {int(player['energy'])}/{player['max_energy']}, Coins: {player['coins']}"
    return f"{map_view}\n{msg}\n{stats}"

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
    # Check if player has the item
    if item_id not in player["inventory"] or player["inventory"][item_id] <= 0:
      return f"You don't have any {item_id} in your inventory."
      
    # Check if player has enough energy to use an item
    if player["energy"] < ENERGY_COSTS["use_item"]:
      return f"You don't have enough energy to use this item. Energy: {int(player['energy'])}/{player['max_energy']}"
    
    # Consume energy for using the item
    player["energy"] -= ENERGY_COSTS["use_item"]

    if item_id == "health_potion":
      if player["health"] >= player["max_health"]:
        # Refund energy if potion wasn't used
        player["energy"] += ENERGY_COSTS["use_item"]
        return "Your health is already full!"

      # Use health potion
      heal_amount = 5
      old_health = player["health"]
      player["health"] = min(player["max_health"], player["health"] + heal_amount)
      player["inventory"][item_id] -= 1

      return f"You used a Health Potion. Health: {int(old_health)} → {int(player['health'])}\nEnergy: -{ENERGY_COSTS['use_item']}"

    elif item_id == "map_scroll":
      # Use map scroll to reveal a larger area
      reveal_extended_map(player, game_map)
      player["inventory"][item_id] -= 1

      map_view = visualize_map(player, game_map)
      return f"You used a Map Scroll and revealed more of the map! Energy: -{ENERGY_COSTS['use_item']}\n\n{map_view}"

    return f"Cannot use {item_id}."

  def display_help():
    """Returns extended help instructions."""
    help_text = ("Welcome to Shadowborn!\n"
                 "Instructions:\n"
                 "- All players explore the SAME dungeon map together!\n"
                 "- Explore the dungeon using movement commands: up/down/left/right or W/A/S/D keys.\n"
                 "- Check your stats with /status to see health, coins, XP, level, attack, and equipment.\n"
                 "- Defeat monsters to earn XP and level up.\n"
                 "- Collect coins and visit the shop (/shop) to buy upgrades using /buy.\n"
                 "- Use consumable items from your inventory with /use.\n"
                 "- View the map with /map.\n"
                 "- Complete quests and explore the vast map with other players.\n"
                 "\nAvailable Commands:\n"
                 "1. /start  - Restart your character (keeps the shared map).\n"
                 "2. up, down, left, right (or W, A, S, D) - Move your character in the specified direction.\n"
                 "3. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n"
                 "4. /map    - View the map of your surroundings.\n"
                 "5. /shop   - Visit the shop to browse and buy upgrades/items.\n"
                 "6. /buy <item_name> - Purchase an item from the shop.\n"
                 "7. /use <item_name> - Use a consumable item from your inventory (e.g., health_potion, map_scroll).\n"
                 "8. /botstatus - View technical information about the bot and world statistics.\n" # FIXME: Remove this later
                 "9. /help   - Display help information.")
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
  if "bot_status" not in plugin.obj_cache:
    # Initialize bot status tracking
    current_time = plugin.time()
    plugin.obj_cache["bot_status"] = {
      "status": "initializing",
      "initialized": False,
      "map_generation_time": None,
      "last_activity": current_time,
      "creation_time": current_time,
      "uptime": 0,
      "status_checks": 0
    }
    plugin.P("Initializing bot status tracking")
  else:
    # Make sure creation_time is always set
    if "creation_time" not in plugin.obj_cache["bot_status"]:
      plugin.obj_cache["bot_status"]["creation_time"] = current_time
      plugin.P("Added missing creation_time to bot status tracking in loop_processing")

  if "shared_map" not in plugin.obj_cache:
    plugin.P("Shared map not found, starting map generation...")
    plugin.obj_cache["bot_status"]["status"] = "generating_map"
    
    # Generate the map
    map_generation_start = plugin.time()
    plugin.obj_cache["shared_map"] = generate_map()
    map_generation_time = plugin.time() - map_generation_start
    
    # Update bot status
    plugin.obj_cache["bot_status"]["status"] = "ready"
    plugin.obj_cache["bot_status"]["initialized"] = True
    plugin.obj_cache["bot_status"]["map_generation_time"] = map_generation_time
    plugin.P(f"Map generation completed in {map_generation_time:.2f} seconds. Bot is ready!")
  else:
    # If map exists but bot status tracking was just added
    if plugin.obj_cache["bot_status"]["status"] == "initializing":
      plugin.obj_cache["bot_status"]["status"] = "ready"
      plugin.obj_cache["bot_status"]["initialized"] = True
      plugin.P("Bot status tracking initialized for existing map")

  # Update last activity timestamp
  plugin.obj_cache["bot_status"]["last_activity"] = plugin.time()

  game_map = plugin.obj_cache["shared_map"]

  # ---------------------------
  # Ensure users dictionary exists
  # ---------------------------
  if "users" not in plugin.obj_cache:
    plugin.obj_cache["users"] = {}

  # ---------------------------
  # Ensure player data exists
  # ---------------------------
  if user_id not in plugin.obj_cache["users"] or plugin.obj_cache["users"][user_id] is None:
    plugin.obj_cache["users"][user_id] = create_new_player()

  player = plugin.obj_cache["users"][user_id]

  # ---------------------------
  # Command Handling
  # ---------------------------
  parts = text.split()
  if not parts:
    return ("Available Commands:\n" 
            "1. /start  - Restart your character (keeps the shared map).\n" 
            "2. up, down, left, right - Move your character directly with these commands.\n" 
            "3. /move <up|down|left|right> - Move your character in the specified direction (WSAD keys supported).\n" 
            "4. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n" 
            "5. /map    - View the map of your surroundings.\n" 
            "6. /shop   - Visit the shop to browse and buy upgrades/items.\n" 
            "7. /buy <item_name> - Purchase an item from the shop.\n" 
            "8. /use <item_name> - Use a consumable item from your inventory (e.g., health_potion, map_scroll).\n"
            "9. /help   - Display help information.")

  command = parts[0]

  # ---------------------------
  # WASD Controls Processing
  # ---------------------------
  # Check if this is a single-letter WASD command
  if command in ["w", "a", "s", "d"]:
    # Map WASD to directions
    direction_map = {"w": "up", "a": "left", "s": "down", "d": "right"}
    direction = direction_map[command]
    return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])
      
  # ---------------------------
  # Direct direction commands (up, down, left, right)
  # ---------------------------
  if command in ["up", "down", "left", "right"]:
    direction = command
    return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])

  if command == "/start":
    # Only reset the player's state, not the shared map
    plugin.obj_cache["users"][user_id] = create_new_player()
    map_view = visualize_map(plugin.obj_cache["users"][user_id], plugin.obj_cache["shared_map"])
    return ("Welcome to Shadowborn!\n" 
            "This is an epic roguelike adventure where you explore a dangerous dungeon, defeat monsters, collect coins, earn XP, and purchase upgrades from the shop.\n" 
            "Your goal is to explore the vast map and complete quests along with other players.\n"
            "All players share the same map - you'll see changes made by other players!\n"
            "Use up, down, left, right or W, A, S, D keys to explore, /status to check your stats, and /shop to buy upgrades.\n\n"
            "For more detailed instructions, use /help.\n\n"
            f"{map_view}")

  elif command == "/move":
    if len(parts) < 2:
      return "Usage: /move <up|down|left|right> (or you can use WSAD keys)"

    direction = parts[1].lower()

    # Handle WASD as input for /move command
    if direction in ["w", "a", "s", "d"]:
      direction_map = {"w": "up", "a": "left", "s": "down", "d": "right"}
      direction = direction_map[direction]

    return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])

  elif command == "/status":
    p = plugin.obj_cache["users"][user_id]
    x, y = p["position"]

    # Calculate total stats including equipment bonuses
    total_attack = p["attack"]
    total_damage_reduction = p["damage_reduction"]
    total_max_health = p["max_health"]
    total_dodge = p["dodge_chance"]

    # Add equipment bonuses
    if p["equipment"]["weapon"]:
      item = SHOP_ITEMS[p["equipment"]["weapon"]]
      if "attack_bonus" in item:
        total_attack += item["attack_bonus"]

    if p["equipment"]["armor"]:
      item = SHOP_ITEMS[p["equipment"]["armor"]]
      if "damage_reduction_bonus" in item:
        total_damage_reduction += item["damage_reduction_bonus"]

    for accessory in p["equipment"]["accessory"]:
      item = SHOP_ITEMS[accessory]
      if "max_health_bonus" in item:
        total_max_health += item["max_health_bonus"]
      if "dodge_chance" in item:
        total_dodge += item["dodge_chance"]

    # Format damage reduction and dodge chance as percentages
    damage_reduction_percent = int(total_damage_reduction * 100)
    dodge_percent = int(total_dodge * 100)

    # Build equipment list
    equipment_list = []
    if p["equipment"]["weapon"]:
      equipment_list.append(f"Weapon: {SHOP_ITEMS[p['equipment']['weapon']]['name']}")
    if p["equipment"]["armor"]:
      equipment_list.append(f"Armor: {SHOP_ITEMS[p['equipment']['armor']]['name']}")
    for accessory in p["equipment"]["accessory"]:
      equipment_list.append(f"Accessory: {SHOP_ITEMS[accessory]['name']}")

    equipment_str = "\n".join(equipment_list) if equipment_list else "None"

    # Build inventory list
    inventory_list = []
    for item_id, count in p["inventory"].items():
      if count > 0:
        if item_id in SHOP_ITEMS:
          inventory_list.append(f"{SHOP_ITEMS[item_id]['name']}: {count}")
        else:
          inventory_list.append(f"{item_id}: {count}")

    inventory_str = "\n".join(inventory_list) if inventory_list else "Empty"

    status_message = (f"📊 STATUS 📊\n"
                     f"🗺️ Position: ({x}, {y})\n"
                     f"❤️ Health: {int(p['health'])}/{p['max_health']} (Regen: {p['hp_regen_rate']:.1f}/min)\n"
                     f"⚡ Energy: {int(p['energy'])}/{p['max_energy']} (Regen: {p['energy_regen_rate']:.1f}/min)\n"
                     f"💰 Coins: {p['coins']}\n"
                     f"📊 Level: {p['level']} (XP: {p['xp']}/{p['next_level_xp']})\n"
                     f"⚔️ Attack: {total_attack}\n"
                     f"🛡️ Damage Reduction: {damage_reduction_percent}%\n"
                     f"👟 Dodge Chance: {dodge_percent}%\n\n"
                     f"🎒 INVENTORY:\n{inventory_str}\n\n"
                     f"🧥 EQUIPMENT:\n{equipment_str}")

    return status_message

  elif command == "/map":
    return visualize_map(plugin.obj_cache["users"][user_id], plugin.obj_cache["shared_map"])

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

  elif command == "/botstatus":
    # Show bot status information
    if "bot_status" not in plugin.obj_cache:
      return "Bot status information not available."
    
    status = plugin.obj_cache["bot_status"]
    current_time = plugin.time()
    
    # Calculate uptime
    uptime_seconds = current_time - status.get("creation_time", current_time)
    minutes, seconds = divmod(uptime_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    # Calculate map statistics if available
    map_stats = ""
    if "shared_map" in plugin.obj_cache:
      total_tiles = GRID_WIDTH * GRID_HEIGHT
      visible_tiles = sum(1 for row in plugin.obj_cache["shared_map"] for tile in row if tile["visible"])
      exploration_percentage = (visible_tiles / total_tiles) * 100
      
      # Count different tile types
      tile_counts = {"COIN": 0, "TRAP": 0, "MONSTER": 0, "HEALTH": 0, "EMPTY": 0}
      for row in plugin.obj_cache["shared_map"]:
        for tile in row:
          if tile["type"] in tile_counts:
            tile_counts[tile["type"]] += 1
      
      map_stats = (f"\n\n🗺️ MAP STATISTICS:\n"
                  f"Map Size: {GRID_WIDTH}×{GRID_HEIGHT} ({total_tiles} tiles)\n"
                  f"Explored: {visible_tiles} tiles ({exploration_percentage:.1f}%)\n"
                  f"Coins remaining: {tile_counts['COIN']}\n"
                  f"Monsters remaining: {tile_counts['MONSTER']}\n"
                  f"Health pickups remaining: {tile_counts['HEALTH']}")
    
    # Count users
    user_count = len(plugin.obj_cache.get("users", {}))
    active_users = sum(1 for user in plugin.obj_cache.get("users", {}).values() if user is not None)
    
    # Format status message
    status_message = (f"🤖 BOT STATUS 🤖\n\n"
                     f"Status: {status['status']}\n"
                     f"Initialized: {'Yes' if status.get('initialized', False) else 'No'}\n"
                     f"Uptime: {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
                     f"Map Generation Time: {status.get('map_generation_time', 'N/A'):.2f}s\n\n"
                     f"👥 USERS:\n"
                     f"Total Users: {user_count}\n"
                     f"Active Players: {active_users}"
                     f"{map_stats}")
    
    return status_message

  else:
    return ("Commands:\n"
            "/start  - Restart your character (keeps the shared map)\n" 
            "up, down, left, right (or W, A, S, D) - Move your character\n" 
            "/status - Display your current stats: position, health, coins, level, XP, damage reduction, and kills\n" 
            "/map    - Reveal the map of your surroundings\n"
            "/shop   - Visit the shop to buy upgrades and items\n" 
            "/buy <item_name> - Purchase an item from the shop\n" 
            "/use <item_name> - Use a consumable item from your inventory\n"
            "/botstatus - View technical information about the bot\n"
            "/help   - Display this help message")

# --------------------------------------------------
# PROCESSING HANDLER
# --------------------------------------------------
def loop_processing(plugin):
  """
  This method is continuously called by the plugin approximately every second.
  Used to regenerate health and energy for all users and monitor bot status.
  
  Regeneration rates in LEVEL_DATA are per minute, so we convert them to per-second rates.
  Health and energy values are truncated to whole numbers.
  """
  
  def regenerate_player_stats(player, time_elapsed):
    """
    Regenerates player's health and energy based on their regeneration rates.

    Args:
      player: The player object to update
      time_elapsed: Time in seconds since last update

    Returns:
      Updated player object with regenerated stats
    """
    # Convert per-minute rates to per-second for calculations
    hp_regen_per_second = player["hp_regen_rate"] / 60.0
    energy_regen_per_second = player["energy_regen_rate"] / 60.0

    # Regenerate health 
    if player["health"] < player["max_health"]:
      hp_gain = hp_regen_per_second * time_elapsed
      player["health"] = min(player["max_health"], player["health"] + hp_gain)
      # No integer truncation here anymore

    # Regenerate energy 
    if player["energy"] < player["max_energy"]:
      energy_gain = energy_regen_per_second * time_elapsed
      player["energy"] = min(player["max_energy"], player["energy"] + energy_gain)

    return player

  result = None
  current_time = plugin.time()  # Get current time using the correct method
  
  # Initialize or update bot status tracking
  if "bot_status" not in plugin.obj_cache:
    plugin.obj_cache["bot_status"] = {
      "status": "initializing",
      "initialized": False,
      "map_generation_time": None,
      "last_activity": current_time,
      "creation_time": current_time,
      "uptime": 0,
      "status_checks": 0
    }
    plugin.P("Bot status tracking initialized in loop_processing")
  else:
    # Make sure creation_time is always set
    if "creation_time" not in plugin.obj_cache["bot_status"]:
      plugin.obj_cache["bot_status"]["creation_time"] = current_time
      plugin.P("Added missing creation_time to bot status tracking in loop_processing")
      
    # Update uptime and run periodic status checks
    plugin.obj_cache["bot_status"]["uptime"] = current_time - plugin.obj_cache["bot_status"].get("creation_time", current_time)
    plugin.obj_cache["bot_status"]["status_checks"] += 1
    
    # Log status every 60 checks (approximately every minute)
    if plugin.obj_cache["bot_status"]["status_checks"] % 60 == 0:
      uptime_minutes = plugin.obj_cache["bot_status"]["uptime"] / 60
      plugin.P(f"Bot status update - Status: {plugin.obj_cache['bot_status']['status']}, "
               f"Initialized: {plugin.obj_cache['bot_status']['initialized']}, "
               f"Uptime: {uptime_minutes:.1f} minutes")
      
      # If we have users and a map, log some basic stats
      if 'users' in plugin.obj_cache and 'shared_map' in plugin.obj_cache:
        user_count = len(plugin.obj_cache['users'])
        active_users = sum(1 for user in plugin.obj_cache['users'].values() if user is not None)
        plugin.P(f"Game stats - Users: {user_count}, Active users: {active_users}")
  
  # Make sure users dictionary exists
  if 'users' not in plugin.obj_cache:
    plugin.obj_cache['users'] = {}
  
  for user in plugin.users:
    # Skip if user has no player data yet
    if user not in plugin.obj_cache['users'] or plugin.obj_cache['users'][user] is None:
      continue
      
    player = plugin.obj_cache['users'][user]
    
    # Calculate time elapsed since last update
    time_elapsed = current_time - player.get("last_update_time", current_time)
    player["last_update_time"] = current_time  # Update the timestamp
    
    # Don't process if less than 1 second has passed
    if time_elapsed < 1:
      continue
      
    # Update player stats
    player = regenerate_player_stats(player, time_elapsed)
    
    # Update the player object in cache
    plugin.obj_cache['users'][user] = player
    
  return result



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
  # my_node = os.getenv("EE_TARGET_NODE", "0xai_A7NhKLfFaJd9pOE_YsyePcMmFfxmMBpvMA4mhuK7Si1w")  # we can specify a node here, if we want to connect to a specific
  telegram_bot_token = os.getenv("EE_TELEGRAM_BOT_TOKEN")  # we can specify a node here, if we want to connect to a specific
  my_node='0xai_A7NhKLfFaJd9pOE_YsyePcMmFfxmMBpvMA4mhuK7Si1w'
  assert my_node is not None, "Please provide the target edge node identifier"
  assert telegram_bot_token is not None, "Please provide the telegram bot token"

  session.wait_for_node(my_node)  # wait for the node to be active

  # unlike the previous example, we are going to use the token from the environment
  # and deploy the app on the target node and leave it there
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="shadowborn_bot",
    message_handler=reply,
    processing_handler=loop_processing,
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
    seconds=7200,  # we wait the session for 10 minutes
    close_pipelines=True,  # we close the pipelines after the session !!!FALSE!!!
    close_session=True,  # we close the session after the session
  )

