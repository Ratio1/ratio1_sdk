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

  # Monster types and their stats
  MONSTER_TYPES = {
    "goblin": {
      "name": "Goblin 👹",
      "min_level": 1,
      "max_level": 3,
      "base_hp": 5,
      "hp_per_level": 2,
      "min_damage": 1,
      "max_damage": 3,
      "damage_per_level": 1,
      "xp_reward": 2,
      "coin_reward": (1, 3)
    },
    "orc": {
      "name": "Orc 👺",
      "min_level": 2,
      "max_level": 5,
      "base_hp": 8,
      "hp_per_level": 3,
      "min_damage": 2,
      "max_damage": 4,
      "damage_per_level": 1,
      "xp_reward": 3,
      "coin_reward": (2, 4)
    },
    "demon": {
      "name": "Demon 👿",
      "min_level": 4,
      "max_level": 10,
      "base_hp": 12,
      "hp_per_level": 4,
      "min_damage": 3,
      "max_damage": 6,
      "damage_per_level": 2,
      "xp_reward": 5,
      "coin_reward": (3, 6)
    }
  }

  # Player stats for each level
  LEVEL_DATA = {
    # Level: {max_hp, max_energy, next_level_xp, hp_regen_rate, energy_regen_rate, damage_reduction}
    # hp_regen_rate and energy_regen_rate are per minute
    1: {"max_hp": 1000, "max_energy": 20, "next_level_xp": 10, "hp_regen_rate": 3, "energy_regen_rate": 6, "damage_reduction": 0.00},
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
    monster_prob = 0.10  # Reduced from 0.15 to 0.10
    health_prob = 0.05
    empty_prob = 1 - (coin_prob + trap_prob + monster_prob + health_prob)  # 0.65
    
    plugin.P(f"Tile distribution - Coin: {coin_prob*100}%, Trap: {trap_prob*100}%, Monster: {monster_prob*100}%, Health: {health_prob*100}%, Empty: {empty_prob*100}%")

    new_map = []
    plugin.P("Starting to populate map rows...")
    
    # Track tile distribution for logging
    tile_counts = {"COIN": 0, "TRAP": 0, "MONSTER": 0, "HEALTH": 0, "EMPTY": 0}
    monster_level_counts = {}
    
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
        
        # For monsters, calculate level with bias towards lower levels
        monster_level = 1
        if tile_type == "MONSTER":
          # Calculate distance from center as a percentage (0-1)
          center_x, center_y = GRID_WIDTH // 2, GRID_HEIGHT // 2
          dx, dy = x - center_x, y - center_y
          distance = plugin.np.sqrt(dx*dx + dy*dy)
          max_distance = plugin.np.sqrt(center_x*center_x + center_y*center_y)
          distance_percent = distance / max_distance
          
          # Apply a pyramid distribution for monster levels
          # Use random number with weighted probability
          rand = plugin.np.random.random()
          
          # Probability weights for each level (must sum to 1.0)
          level_weights = {
            1: 0.30,  # 30% chance for level 1
            2: 0.20,  # 20% chance for level 2
            3: 0.15,  # 15% chance for level 3
            4: 0.10,  # 10% chance for level 4
            5: 0.08,  # 8% chance for level 5
            6: 0.07,  # 7% chance for level 6
            7: 0.05,  # 5% chance for level 7
            8: 0.03,  # 3% chance for level 8
            9: 0.02   # 2% chance for level 9
          }
          
          # Determine monster level based on random number and weights
          cumulative_prob = 0
          monster_level = 1  # Default to level 1
          for level, weight in level_weights.items():
            cumulative_prob += weight
            if rand <= cumulative_prob:
              monster_level = level
              break
          
          # Track monster level distribution
          if monster_level not in monster_level_counts:
            monster_level_counts[monster_level] = 0
          monster_level_counts[monster_level] += 1
        
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
    
    if monster_level_counts:
      plugin.P(f"\nMonster level distribution:")
      total_monsters = tile_counts["MONSTER"]
      for level in sorted(monster_level_counts.keys()):
        count = monster_level_counts[level]
        percentage = (count / total_monsters) * 100
        plugin.P(f"  Level {level}: {count} monsters ({percentage:.2f}%)")
    
    return new_map

  def find_random_empty_spot(game_map):
    """
    Finds a random empty spot on the map.
    Returns tuple of (x, y) coordinates or (0, 0) if no empty spots found.
    """
    empty_spots = []
    for y in range(GRID_HEIGHT):
      for x in range(GRID_WIDTH):
        if game_map[y][x]["type"] == "EMPTY":
          empty_spots.append((x, y))
    
    if empty_spots:
      # Convert empty_spots to numpy array for random choice
      empty_spots_array = plugin.np.array(empty_spots)
      random_index = plugin.np.random.randint(0, len(empty_spots))
      return tuple(empty_spots_array[random_index])
    
    return (0, 0)  # Fallback to origin if no empty spots found

  def create_new_player():
    """Creates a new player dict with default stats."""
    level_1_data = LEVEL_DATA[1]
    
    # Find random empty spot for initial spawn
    spawn_x, spawn_y = find_random_empty_spot(plugin.obj_cache["shared_map"])
    
    # Create the player object
    player = {
        "position": (spawn_x, spawn_y),
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
        "status": "exploring",  # Player's current state: exploring, fighting, recovering
        "status_since": plugin.time(),  # When the current status was set
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
    
    # Make spawn location visible and reveal surroundings
    plugin.obj_cache["shared_map"][spawn_y][spawn_x]["visible"] = True
    reveal_surroundings(player, plugin.obj_cache["shared_map"])
    
    return player

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
                        f"Damage Reduction: {int(old_damage_reduction * 100)}% → {int(player['damage_reduction'] * 100)}%\n\n" \
                        f"🌟 You can continue exploring the dungeon! Use /map to see your surroundings."
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
                        f"Damage Reduction: {int(old_damage_reduction * 100)}% → {int(player['damage_reduction'] * 100)}%\n\n" \
                        f"🌟 You can continue exploring the dungeon! Use /map to see your surroundings."
            
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
    
    # Get status emoji for the player
    player_emoji = "🧙"  # Default player emoji
    if player["status"] == "fighting":
      player_emoji = "⚔️"  # Fighting emoji
    elif player["status"] == "recovering":
      player_emoji = "💤"  # Recovering emoji
      
    map_view = f"🗺️ Your location: ({x}, {y}) | Status: {player_emoji} {player['status'].capitalize()}\n\n"

    for ny in range(max(0, y - view_distance), min(GRID_HEIGHT, y + view_distance + 1)):
      for nx in range(max(0, x - view_distance), min(GRID_WIDTH, x + view_distance + 1)):
        if (nx, ny) == (x, y):
          map_view += f"{player_emoji} "  # Player with status-specific emoji
        elif game_map[ny][nx]["visible"]:
          tile_type = game_map[ny][nx]["type"]
          if tile_type == "COIN":
            map_view += "💰 "
          elif tile_type == "TRAP":
            map_view += "🔥 "
          elif tile_type == "MONSTER":
            # Different monster emoji based on level clusters
            monster_level = game_map[ny][nx]["monster_level"]
            if monster_level <= 3:
                map_view += "👹 "  # Levels 1-3: Goblin
            elif monster_level <= 6:
                map_view += "👺 "  # Levels 4-6: Orc
            elif monster_level <= 9:
                map_view += "👿 "  # Levels 7-9: Demon
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
    # Check if player is in combat
    if player["status"] == "fighting":
      return "You cannot move while in combat! You must defeat the monster first."

    # Check if player is recovering
    if player["status"] == "recovering":
      return "You cannot move while recovering! Wait until you are fully healed and energized."

    # Check if player is not exploring
    if player["status"] != "exploring":
      return "You can only move while exploring!"

    # Check if player has enough energy for the basic move
    if player["energy"] < ENERGY_COSTS["move"]:
      # Set player status to recovering if they're too exhausted to move
      player = update_player_status(player, "recovering")
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
        player = update_player_status(player, "recovering")
        return f"You don't have enough energy to fight the monster at ({x},{y})!\nEnergy: {int(player['energy'])}/{player['max_energy']}\nWait for your energy to regenerate."
      energy_cost += ENERGY_COSTS["attack"]
      # Set player status to fighting
      player = update_player_status(player, "fighting")
    else:
      # Set player status to exploring for normal movement
      player = update_player_status(player, "exploring")

    # Consume energy
    player["energy"] -= energy_cost
    
    # Actually move the player
    player["position"] = (x, y)
    tile = game_map[y][x]
    tile["visible"] = True
    reveal_surroundings(player, game_map)

    # Basic movement message
    msg = f"You moved {direction} to ({x},{y}). Energy: -{energy_cost} "
    
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
      # Instead of instant combat, initiate real-time combat
      monster_level = tile["monster_level"]
      monster_type = get_monster_type_for_level(monster_level)
      monster_name = MONSTER_TYPES[monster_type]["name"]
      msg += f"⚔️ You engage in combat with a level {monster_level} {monster_name}!\n"
      msg += "Combat will proceed automatically. Use /status to check your health and stats."

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
      player = update_player_status(player, "recovering")
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
      
      # Set player status to recovering when using a health potion
      player = update_player_status(player, "recovering")

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
                 "\nPlayer Status System:\n"
                 "Your character can be in one of three states that affect gameplay:\n"
                 "- Exploring: Normal movement with standard regeneration rates.\n"
                 "- Fighting: Engaged in combat with reduced health regeneration.\n"
                 "- Recovering: Resting with increased health and energy regeneration.\n"
                 "Your status changes automatically based on your actions, but you can also set it manually.\n"
                 "\nAvailable Commands:\n"
                 "1. /start  - Restart your character (keeps the shared map).\n"
                 "2. up, down, left, right (or W, A, S, D) - Move your character in the specified direction.\n"
                 "3. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n"
                 "4. /map    - View the map of your surroundings.\n"
                 "5. /shop   - Visit the shop to browse and buy upgrades/items.\n"
                 "6. /buy <item_name> - Purchase an item from the shop.\n"
                 "7. /use <item_name> - Use a consumable item from your inventory (e.g., health_potion, map_scroll).\n"
                 "8. /setstatus <exploring|fighting|recovering> - Manually set your status to affect regeneration rates.\n"
                 "9. /botstatus - View technical information about the bot and world statistics.\n"
                 "10. /help   - Display help information.\n"
                 "\nGame Initialization:\n"
                 "The game world needs to be initialized before anyone can play.\n"
                 "- /init   - Initialize the game world (admin only, can only be used once).")
    return help_text

  def update_player_status(player, new_status):
    """
    Updates a player's status and records when it changed.
    
    Args:
      player: The player object to update
      new_status: The new status string, one of: "exploring", "fighting", "recovering"
      
    Returns:
      Updated player object with new status
    """
    if new_status not in ["exploring", "fighting", "recovering"]:
      plugin.P(f"Warning: Invalid status '{new_status}' being set. Defaulting to 'exploring'")
      new_status = "exploring"
      
    if player["status"] != new_status:
      player["status"] = new_status
      player["status_since"] = plugin.time()
      plugin.P(f"Player status changed to {new_status}")
    
    return player

  def get_monster_type_for_level(level):
    """
    Returns an appropriate monster type for the given level.
    """
    suitable_monsters = [
        monster_type for monster_type, stats in MONSTER_TYPES.items()
        if stats["min_level"] <= level <= stats["max_level"]
    ]
    if not suitable_monsters:
        return "goblin"  # Default to goblin if no suitable monster found
    
    # Use randint instead of choice for selecting from the list
    random_index = plugin.np.random.randint(0, len(suitable_monsters))
    return suitable_monsters[random_index]

  def create_monster(level):
    """
    Creates a new monster of appropriate level.
    """
    monster_type = get_monster_type_for_level(level)
    stats = MONSTER_TYPES[monster_type]
    
    # Calculate monster stats based on level
    hp = stats["base_hp"] + (level - 1) * stats["hp_per_level"]
    min_damage = stats["min_damage"] + (level - 1) * stats["damage_per_level"]
    max_damage = stats["max_damage"] + (level - 1) * stats["damage_per_level"]
    
    return {
      "type": monster_type,
      "name": stats["name"],
      "level": level,
      "hp": hp,
      "max_hp": hp,
      "min_damage": min_damage,
      "max_damage": max_damage,
      "xp_reward": stats["xp_reward"] * level,
      "coin_reward": (stats["coin_reward"][0] * level, stats["coin_reward"][1] * level)
    }

  def process_combat_round(player, combat_session, game_map):
    """
    Process a single round of combat between player and monster.
    Returns a tuple of (combat_ended, message).
    """
    monster = combat_session["monster"]
    messages = []
    
    # Add round start message with combat status
    messages.append(f"⚔️ COMBAT ROUND ⚔️")
    messages.append(f"Fighting {monster['name']} (Level {monster['level']})")
    
    # Player's attack
    player_min_damage = max(1, player["attack"])
    player_max_damage = max(2, player["attack"] * 2)
    player_damage = plugin.np.random.randint(player_min_damage, player_max_damage + 1)
    
    monster["hp"] -= player_damage
    messages.append(f"\n🗡️ Your attack:")
    messages.append(f"You hit the {monster['name']} for {player_damage} damage!")
    
    # Check if monster died
    if monster["hp"] <= 0:
      # Award XP and coins
      coin_reward = plugin.np.random.randint(monster["coin_reward"][0], monster["coin_reward"][1] + 1)
      player["coins"] += coin_reward
      player["xp"] += monster["xp_reward"]
      
      # Clear the monster tile
      x, y = player["position"]
      game_map[y][x]["type"] = "EMPTY"
      game_map[y][x]["monster_level"] = 0
      
      # Set player back to exploring
      player = update_player_status(player, "exploring")
      
      messages.append(f"\n🎯 VICTORY!")
      messages.append(f"You defeated the {monster['name']}!")
      messages.append(f"Rewards: {coin_reward} coins, {monster['xp_reward']} XP")
      
      # Check for level up
      if player["xp"] >= player["next_level_xp"]:
        old_level = player["level"]
        player["level"] += 1
        new_level = player["level"]
        
        if new_level in LEVEL_DATA:
          level_data = LEVEL_DATA[new_level]
          player["max_health"] = level_data["max_hp"]
          player["max_energy"] = level_data["max_energy"]
          player["next_level_xp"] = level_data["next_level_xp"]
          player["hp_regen_rate"] = level_data["hp_regen_rate"]
          player["energy_regen_rate"] = level_data["energy_regen_rate"]
          player["damage_reduction"] = level_data["damage_reduction"]
          
          messages.append(f"\n🌟 LEVEL UP!")
          messages.append(f"You are now level {new_level}!")
          messages.append(f"Max Health: {player['max_health']}")
          messages.append(f"Max Energy: {player['max_energy']}")
          messages.append(f"\n🌟 You can continue exploring the dungeon! Use /map to see your surroundings.")
      
      return True, "\n".join(messages)
    
    # Monster's counterattack
    messages.append(f"\n👿 Monster's attack:")
    monster_damage = plugin.np.random.randint(monster["min_damage"], monster["max_damage"] + 1)
    
    # Check for dodge
    if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
      messages.append(f"You nimbly dodged the {monster['name']}'s attack!")
    else:
      # Apply damage reduction
      final_damage = max(1, int(monster_damage * (1 - player["damage_reduction"])))
      player["health"] -= final_damage
      
      # Add damage reduction info if player has any
      if player["damage_reduction"] > 0:
        reduced_amount = monster_damage - final_damage
        messages.append(f"The {monster['name']} attacks for {monster_damage} damage")
        messages.append(f"Your armor reduces it by {reduced_amount} ({int(player['damage_reduction'] * 100)}%)")
        messages.append(f"You take {final_damage} damage!")
      else:
        messages.append(f"The {monster['name']} hits you for {final_damage} damage!")
      
      # Check if player died
      if player["health"] <= 0:
        # Reset player stats and respawn at a random empty location
        player["health"] = 1  # Start with 1 HP
        player["energy"] = 0  # No energy
        
        # Find random empty spot for respawn
        respawn_x, respawn_y = find_random_empty_spot(game_map)
        player["position"] = (respawn_x, respawn_y)
        game_map[respawn_y][respawn_x]["visible"] = True
        reveal_surroundings(player, game_map)
        
        # Set status to recovering
        player = update_player_status(player, "recovering")
        messages.append(f"\n💀 DEFEAT!")
        messages.append("You have been defeated and respawned at a random location!")
        messages.append("You must rest until fully healed before continuing your adventure...")
        return True, "\n".join(messages)
    
    # Add combat status at the end of each round
    messages.append(f"\n📊 Combat Status:")
    messages.append(f"Your HP: {int(player['health'])}/{player['max_health']}")
    messages.append(f"Monster HP: {monster['hp']}/{monster['max_hp']}")
    
    return False, "\n".join(messages)

  # --------------------------------------------------
  try:
    # Remove debug code
    pass
  except Exception as e:
    print(e)

  text = (message or "").strip().lower()
  user_id = str(user)

  # ---------------------------
  # Ensure bot status tracking exists
  # ---------------------------
  if "bot_status" not in plugin.obj_cache:
    # Initialize bot status tracking
    current_time = plugin.time()
    plugin.obj_cache["bot_status"] = {
      "status": "uninitialized", 
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

  # Update last activity timestamp
  plugin.obj_cache["bot_status"]["last_activity"] = plugin.time()

  # ---------------------------
  # Check initialization and handle /init command
  # ---------------------------
  parts = text.split()
  if not parts:
    if plugin.obj_cache["bot_status"]["initialized"]:
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
    else:
      return ("⚠️ GAME NOT INITIALIZED ⚠️\n\n"
             "The game world hasn't been created yet!\n"
             "An administrator needs to use the /init command to generate the game world before anyone can play.\n\n"
             "Available Commands:\n"
             "1. /init   - Initialize the game world (admin only, first-time setup)\n"
             "2. /help   - Display help information\n"
             "3. /botstatus - View technical information about the bot")

  command = parts[0]

  # Handle initialization command
  if command == "/init":
    # Only allow /init when not initialized
    if plugin.obj_cache["bot_status"]["initialized"]:
      return "Game is already initialized! The world exists and players can join."
    
    plugin.P("Initialization command received, starting map generation...")
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
    
    return (f"🌍 GAME WORLD INITIALIZED! 🌍\n\n"
           f"Map generation completed in {map_generation_time:.2f} seconds.\n"
           f"The game world is now ready for players to join!\n"
           f"Players can use /start to begin their adventure.")

  # Check if game is initialized before processing any other commands
  if not plugin.obj_cache["bot_status"]["initialized"] or "shared_map" not in plugin.obj_cache:
    return ("⚠️ GAME NOT INITIALIZED ⚠️\n\n"
           "The game world hasn't been created yet!\n"
           "An administrator needs to use the /init command to generate the game world before anyone can play.")

  # Now that we've confirmed initialization, we can access the game map
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

    # Calculate how long the player has been in their current status
    status_duration = int(plugin.time() - p["status_since"])
    minutes, seconds = divmod(status_duration, 60)
    
    # Get status emoji
    status_emoji = "🔍" if p["status"] == "exploring" else "⚔️" if p["status"] == "fighting" else "💤"
    
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
                     f"👤 Status: {status_emoji} {p['status'].capitalize()} ({minutes}m {seconds}s)\n"
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

  elif command == "/wiki":
    wiki_text = (
      "📚 SHADOWBORN WIKI 📚\n\n"
      "🎯 MONSTER TYPES & LEVELS:\n"
      "1. 👹 Goblin (Levels 1-3)\n"
      "   • Base HP: 5\n"
      "   • Damage: 1-3\n"
      "   • XP Reward: 2\n"
      "   • Coin Reward: 1-3\n\n"
      "2. 👺 Orc (Levels 4-6)\n"
      "   • Base HP: 8\n"
      "   • Damage: 2-4\n"
      "   • XP Reward: 3\n"
      "   • Coin Reward: 2-4\n\n"
      "3. 👿 Demon (Levels 7-9)\n"
      "   • Base HP: 12\n"
      "   • Damage: 3-6\n"
      "   • XP Reward: 5\n"
      "   • Coin Reward: 3-6\n\n"
      "📊 MONSTER LEVEL DISTRIBUTION:\n"
      "• Level 1: 30% (Most Common)\n"
      "• Level 2: 20%\n"
      "• Level 3: 15%\n"
      "• Level 4: 10%\n"
      "• Level 5: 8%\n"
      "• Level 6: 7%\n"
      "• Level 7: 5%\n"
      "• Level 8: 3%\n"
      "• Level 9: 2% (Rarest)\n\n"
      "⚔️ COMBAT MECHANICS:\n"
      "• Combat starts automatically when moving onto a monster tile\n"
      "• Each combat round takes 5 seconds\n"
      "• Energy cost for combat: 3\n"
      "• Dodge chance reduces incoming damage to 0\n"
      "• Damage reduction reduces incoming damage by percentage\n\n"
      "💫 PLAYER STATUS EFFECTS:\n"
      "1. Exploring (🔍)\n"
      "   • Normal health and energy regeneration\n"
      "   • Standard movement speed\n\n"
      "2. Fighting (⚔️)\n"
      "   • Reduced health regeneration (50%)\n"
      "   • Normal energy regeneration\n"
      "   • Cannot move until combat ends\n\n"
      "3. Recovering (💤)\n"
      "   • Increased health regeneration (150%)\n"
      "   • Increased energy regeneration (150%)\n"
      "   • Cannot move until fully healed\n\n"
      "🎒 INVENTORY ITEMS:\n"
      "• Health Potion (🧪): Restores 5 HP\n"
      "• Map Scroll (📜): Reveals larger area\n\n"
      "🛍️ SHOP ITEMS:\n"
      "• Health Potion: 5 coins\n"
      "• Sword (⚔️): +1 Attack, 15 coins\n"
      "• Shield (🛡️): +10% Damage Reduction, 20 coins\n"
      "• Magic Amulet (🔮): +3 Max Health, 25 coins\n"
      "• Speed Boots (👢): +5% Dodge Chance, 30 coins\n"
      "• Map Scroll: 10 coins\n\n"
      "💡 TIPS:\n"
      "• Use /status to check your stats\n"
      "• Use /map to view your surroundings\n"
      "• Use /setstatus to manually change your status\n"
      "• Higher level monsters give better rewards\n"
      "• Always keep some health potions for emergencies\n"
      "• Use map scrolls to plan your route\n"
      "• Consider your energy before engaging in combat"
    )
    return wiki_text

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
    
    # Check if the world is initialized
    initialization_status = "✅ Initialized" if status.get("initialized", False) else "❌ Not Initialized"
    
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
                     f"Initialization: {initialization_status}\n"
                     f"Uptime: {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
                     f"Map Generation Time: {status.get('map_generation_time', 'N/A'):.2f}s\n\n"
                     f"👥 USERS:\n"
                     f"Total Users: {user_count}\n"
                     f"Active Players: {active_users}"
                     f"{map_stats}")
    
    return status_message

  elif command == "/setstatus":
    if len(parts) < 2:
      return "Usage: /setstatus <exploring|fighting|recovering>\nThis allows you to manually set your status."
      
    requested_status = parts[1].lower()
    if requested_status not in ["exploring", "fighting", "recovering"]:
      return f"Invalid status: '{requested_status}'. Valid statuses are: exploring, fighting, recovering"
      
    old_status = player["status"]
    player = update_player_status(player, requested_status)
    
    if requested_status == "exploring":
      status_desc = "You're now actively exploring the dungeon. Normal health and energy regeneration."
    elif requested_status == "fighting":
      status_desc = "You're now in combat mode. Reduced health regeneration but normal energy regeneration."
    elif requested_status == "recovering":
      status_desc = "You're now recovering. Increased health and energy regeneration rates!"
      
    return f"Status changed from {old_status} to {requested_status}.\n{status_desc}"

  else:
    return ("Commands:\n"
            "/start  - Restart your character (keeps the shared map)\n" 
            "up, down, left, right (or W, A, S, D) - Move your character\n" 
            "/status - Display your current stats: position, health, coins, level, XP, damage reduction, and kills\n" 
            "/map    - Reveal the map of your surroundings\n"
            "/shop   - Visit the shop to buy upgrades and items\n" 
            "/buy <item_name> - Purchase an item from the shop\n" 
            "/use <item_name> - Use a consumable item from your inventory\n"
            "/setstatus <exploring|fighting|recovering> - Manually set your status\n"
            "/botstatus - View technical information about the bot\n"
            "/help   - Display this help message"
            + ("\n/init   - Initialize the game world (admin only)" if not plugin.obj_cache["bot_status"]["initialized"] else ""))

# --------------------------------------------------
# PROCESSING HANDLER
# --------------------------------------------------
def loop_processing(plugin):
  """
  This method is continuously called by the plugin approximately every second.
  Used to regenerate health and energy for all users and monitor bot status.
  Also handles real-time combat rounds for players in combat.
  """
  # --------------------------------------------------
  # GAME CONSTANTS
  # --------------------------------------------------
  GRID_WIDTH = 100
  GRID_HEIGHT = 100
  MAX_LEVEL = 10

  # Monster types and their stats
  MONSTER_TYPES = {
    "goblin": {
      "name": "Goblin 👹",
      "min_level": 1,
      "max_level": 3,
      "base_hp": 5,
      "hp_per_level": 2,
      "min_damage": 1,
      "max_damage": 3,
      "damage_per_level": 1,
      "xp_reward": 2,
      "coin_reward": (1, 3)
    },
    "orc": {
      "name": "Orc 👺",
      "min_level": 2,
      "max_level": 5,
      "base_hp": 8,
      "hp_per_level": 3,
      "min_damage": 2,
      "max_damage": 4,
      "damage_per_level": 1,
      "xp_reward": 3,
      "coin_reward": (2, 4)
    },
    "demon": {
      "name": "Demon 👿",
      "min_level": 4,
      "max_level": 10,
      "base_hp": 12,
      "hp_per_level": 4,
      "min_damage": 3,
      "max_damage": 6,
      "damage_per_level": 2,
      "xp_reward": 5,
      "coin_reward": (3, 6)
    }
  }

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
  
  def reveal_surroundings(player, game_map):
    """Reveals the tiles around the player."""
    x, y = player["position"]
    for dy in range(-1, 2):
      for dx in range(-1, 2):
        nx, ny = x + dx, y + dy
        if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
          game_map[ny][nx]["visible"] = True

  
  def update_player_status(player, new_status):
    """
    Updates a player's status and records when it changed.
    """
    if new_status not in ["exploring", "fighting", "recovering"]:
      plugin.P(f"Warning: Invalid status '{new_status}' being set. Defaulting to 'exploring'")
      new_status = "exploring"

    if player["status"] != new_status:
      player["status"] = new_status
      player["status_since"] = plugin.time()
      plugin.P(f"Player status changed to {new_status}")

    return player

  def regenerate_player_stats(player, time_elapsed):
    """
    Regenerates player's health and energy based on their regeneration rates.
    Status affects regeneration rate:
    - "recovering": faster regeneration (1.5x)
    - "exploring": normal regeneration
    - "fighting": slower health regeneration (0.5x) but normal energy regeneration
    """
    # Apply status modifiers to regeneration rates
    status_modifiers = {
      "recovering": {"health": 1.5, "energy": 1.5},
      "exploring": {"health": 1.0, "energy": 1.0},
      "fighting": {"health": 0.5, "energy": 1.0}
    }
    
    # Default to exploring modifiers if status is invalid
    modifiers = status_modifiers.get(player["status"], status_modifiers["exploring"])
    
    # Convert per-minute rates to per-second for calculations
    hp_regen_per_second = (player["hp_regen_rate"] / 60.0) * modifiers["health"]
    energy_regen_per_second = (player["energy_regen_rate"] / 60.0) * modifiers["energy"]

    # Store old health for checking recovery completion
    old_health = player["health"]

    # Regenerate health 
    if player["health"] < player["max_health"]:
      hp_gain = hp_regen_per_second * time_elapsed
      player["health"] = min(player["max_health"], player["health"] + hp_gain)
      
      # If health is fully regenerated and player was recovering, set status back to exploring
      if player["health"] >= player["max_health"] and player["status"] == "recovering":
        player = update_player_status(player, "exploring")
        # Return a notification that the player has recovered
        return player, "🌟 You have fully recovered and can now continue your adventure!"

    # Regenerate energy 
    if player["energy"] < player["max_energy"]:
      energy_gain = energy_regen_per_second * time_elapsed
      player["energy"] = min(player["max_energy"], player["energy"] + energy_gain)
      
      # If energy is fully regenerated and player was recovering, set status back to exploring
      if player["energy"] >= player["max_energy"] and player["status"] == "recovering" and player["health"] >= player["max_health"]:
        player = update_player_status(player, "exploring")

    return player, None

  def get_monster_type_for_level(level):
    """
    Returns an appropriate monster type for the given level.
    """
    suitable_monsters = [
        monster_type for monster_type, stats in MONSTER_TYPES.items()
        if stats["min_level"] <= level <= stats["max_level"]
    ]
    if not suitable_monsters:
        return "goblin"  # Default to goblin if no suitable monster found
    
    # Use randint instead of choice for selecting from the list
    random_index = plugin.np.random.randint(0, len(suitable_monsters))
    return suitable_monsters[random_index]

  def create_monster(level):
    """
    Creates a new monster of appropriate level.
    """
    monster_type = get_monster_type_for_level(level)
    stats = MONSTER_TYPES[monster_type]
    
    # Calculate monster stats based on level
    hp = stats["base_hp"] + (level - 1) * stats["hp_per_level"]
    min_damage = stats["min_damage"] + (level - 1) * stats["damage_per_level"]
    max_damage = stats["max_damage"] + (level - 1) * stats["damage_per_level"]
    
    return {
      "type": monster_type,
      "name": stats["name"],
      "level": level,
      "hp": hp,
      "max_hp": hp,
      "min_damage": min_damage,
      "max_damage": max_damage,
      "xp_reward": stats["xp_reward"] * level,
      "coin_reward": (stats["coin_reward"][0] * level, stats["coin_reward"][1] * level)
    }

  def process_combat_round(player, combat_session, game_map):
    """
    Process a single round of combat between player and monster.
    Returns a tuple of (combat_ended, message).
    """
    monster = combat_session["monster"]
    messages = []
    
    # Add round start message with combat status
    messages.append(f"⚔️ COMBAT ROUND ⚔️")
    messages.append(f"Fighting {monster['name']} (Level {monster['level']})")
    
    # Player's attack
    player_min_damage = max(1, player["attack"])
    player_max_damage = max(2, player["attack"] * 2)
    player_damage = plugin.np.random.randint(player_min_damage, player_max_damage + 1)
    
    monster["hp"] -= player_damage
    messages.append(f"\n🗡️ Your attack:")
    messages.append(f"You hit the {monster['name']} for {player_damage} damage!")
    
    # Check if monster died
    if monster["hp"] <= 0:
      # Award XP and coins
      coin_reward = plugin.np.random.randint(monster["coin_reward"][0], monster["coin_reward"][1] + 1)
      player["coins"] += coin_reward
      player["xp"] += monster["xp_reward"]
      
      # Clear the monster tile
      x, y = player["position"]
      game_map[y][x]["type"] = "EMPTY"
      game_map[y][x]["monster_level"] = 0
      
      # Set player back to exploring
      player = update_player_status(player, "exploring")
      
      messages.append(f"\n🎯 VICTORY!")
      messages.append(f"You defeated the {monster['name']}!")
      messages.append(f"Rewards: {coin_reward} coins, {monster['xp_reward']} XP")
      
      # Check for level up
      if player["xp"] >= player["next_level_xp"]:
        old_level = player["level"]
        player["level"] += 1
        new_level = player["level"]
        
        if new_level in LEVEL_DATA:
          level_data = LEVEL_DATA[new_level]
          player["max_health"] = level_data["max_hp"]
          player["max_energy"] = level_data["max_energy"]
          player["next_level_xp"] = level_data["next_level_xp"]
          player["hp_regen_rate"] = level_data["hp_regen_rate"]
          player["energy_regen_rate"] = level_data["energy_regen_rate"]
          player["damage_reduction"] = level_data["damage_reduction"]
          
          messages.append(f"\n🌟 LEVEL UP!")
          messages.append(f"You are now level {new_level}!")
          messages.append(f"Max Health: {player['max_health']}")
          messages.append(f"Max Energy: {player['max_energy']}")
          messages.append(f"\n🌟 You can continue exploring the dungeon! Use /map to see your surroundings.")
      
      return True, "\n".join(messages)
    
    # Monster's counterattack
    messages.append(f"\n👿 Monster's attack:")
    monster_damage = plugin.np.random.randint(monster["min_damage"], monster["max_damage"] + 1)
    
    # Check for dodge
    if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
      messages.append(f"You nimbly dodged the {monster['name']}'s attack!")
    else:
      # Apply damage reduction
      final_damage = max(1, int(monster_damage * (1 - player["damage_reduction"])))
      player["health"] -= final_damage
      
      # Add damage reduction info if player has any
      if player["damage_reduction"] > 0:
        reduced_amount = monster_damage - final_damage
        messages.append(f"The {monster['name']} attacks for {monster_damage} damage")
        messages.append(f"Your armor reduces it by {reduced_amount} ({int(player['damage_reduction'] * 100)}%)")
        messages.append(f"You take {final_damage} damage!")
      else:
        messages.append(f"The {monster['name']} hits you for {final_damage} damage!")
      
      # Check if player died
      if player["health"] <= 0:
        # Reset player stats and respawn at a random empty location
        player["health"] = 1  # Start with 1 HP
        player["energy"] = 0  # No energy
        
        # Find random empty spot for respawn
        respawn_x, respawn_y = find_random_empty_spot(game_map)
        player["position"] = (respawn_x, respawn_y)
        game_map[respawn_y][respawn_x]["visible"] = True
        reveal_surroundings(player, game_map)
        
        # Set status to recovering
        player = update_player_status(player, "recovering")
        messages.append(f"\n💀 DEFEAT!")
        messages.append("You have been defeated and respawned at a random location!")
        messages.append("You must rest until fully healed before continuing your adventure...")
        return True, "\n".join(messages)
    
    # Add combat status at the end of each round
    messages.append(f"\n📊 Combat Status:")
    messages.append(f"Your HP: {int(player['health'])}/{player['max_health']}")
    messages.append(f"Monster HP: {monster['hp']}/{monster['max_hp']}")
    
    return False, "\n".join(messages)

  result = None
  current_time = plugin.time()
  
  # Initialize or update bot status tracking
  if "bot_status" not in plugin.obj_cache:
    plugin.obj_cache["bot_status"] = {
      "status": "uninitialized",
      "initialized": False,
      "map_generation_time": None,
      "last_activity": current_time,
      "creation_time": current_time,
      "uptime": 0,
      "status_checks": 0
    }
    plugin.P("Bot status tracking initialized in loop_processing")
  else:
    if "creation_time" not in plugin.obj_cache["bot_status"]:
      plugin.obj_cache["bot_status"]["creation_time"] = current_time
      plugin.P("Added missing creation_time to bot status tracking in loop_processing")
      
    plugin.obj_cache["bot_status"]["uptime"] = current_time - plugin.obj_cache["bot_status"].get("creation_time", current_time)
    plugin.obj_cache["bot_status"]["status_checks"] += 1
    
    if plugin.obj_cache["bot_status"]["status_checks"] % 60 == 0:
      uptime_minutes = plugin.obj_cache["bot_status"]["uptime"] / 60
      plugin.P(f"Bot status update - Status: {plugin.obj_cache['bot_status']['status']}, "
               f"Initialized: {plugin.obj_cache['bot_status']['initialized']}, "
               f"Uptime: {uptime_minutes:.1f} minutes")
      
      if plugin.obj_cache["bot_status"]["initialized"] and 'users' in plugin.obj_cache and 'shared_map' in plugin.obj_cache:
        user_count = len(plugin.obj_cache['users'])
        active_users = sum(1 for user in plugin.obj_cache['users'].values() if user is not None)
        plugin.P(f"Game stats - Users: {user_count}, Active users: {active_users}")
  
  # Skip player updates if game isn't initialized yet
  if not plugin.obj_cache["bot_status"]["initialized"] or "shared_map" not in plugin.obj_cache:
    return result
  
  # Initialize combat tracking if it doesn't exist
  if "combat" not in plugin.obj_cache:
    plugin.obj_cache["combat"] = {}
  
  # Make sure users dictionary exists
  if 'users' not in plugin.obj_cache:
    plugin.obj_cache['users'] = {}
  
  for user_id in plugin.obj_cache['users']:
    # Skip if user has no player data yet
    if user_id not in plugin.obj_cache['users'] or plugin.obj_cache['users'][user_id] is None:
      continue
      
    player = plugin.obj_cache['users'][user_id]
    
    # Calculate time elapsed since last update
    time_elapsed = current_time - player.get("last_update_time", current_time)
    player["last_update_time"] = current_time
    
    # Don't process if less than 1 second has passed
    if time_elapsed < 1:
      continue
      
    # Update player stats
    player, recovery_message = regenerate_player_stats(player, time_elapsed)
    
    # Process combat if player is fighting
    if player["status"] == "fighting":
      # Initialize or get combat session
      if user_id not in plugin.obj_cache["combat"]:
        # Get player's position and monster level
        x, y = player["position"]
        monster_level = plugin.obj_cache["shared_map"][y][x]["monster_level"]
        
        # Create new combat session
        plugin.obj_cache["combat"][user_id] = {
          "monster": create_monster(monster_level),
          "last_round_time": current_time
        }
      
      combat_session = plugin.obj_cache["combat"][user_id]
      
      # Check if enough time has passed for next combat round (5 seconds)
      time_since_last_round = current_time - combat_session["last_round_time"]
      if time_since_last_round >= 5:
        # Process combat round
        combat_ended, message = process_combat_round(player, combat_session, plugin.obj_cache["shared_map"])
        
        # Send combat message to player
        plugin.send_message_to_user(user_id, message)
        
        if combat_ended:
          # Clean up combat session
          del plugin.obj_cache["combat"][user_id]
        else:
          # Update last round time
          combat_session["last_round_time"] = current_time
    
    # Update the player object in cache
    plugin.obj_cache['users'][user_id] = player
    
    # Send recovery message if player has fully recovered
    if recovery_message:
      plugin.send_message_to_user(user_id, recovery_message)
    
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

