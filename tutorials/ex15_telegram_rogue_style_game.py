#!/usr/bin/env python3
"""
Telegram roguelike bot using the same pipeline approach as Blackjack:
- Uses `plugin.obj_cache` to store user data in memory.
- No persistent storage (resets on bot restart).
- Requires three-argument `reply(plugin, message, user)`, as per the Blackjack example.


TODO:
1. reduce `ex15_telegram_rogue_style_game.py` to 20% of current features
2. move `ex15_telegram_rogue_style_game.py` full as a plugin in Edge Node
3. add `ex15_telegram_rogue_style_game_ext.py` that launches a pipeline with the plugin from (2)
"""


import os
import logging
from ratio1 import Session, CustomPluginTemplate



# --------------------------------------------------
# CREATE RATIO1 SESSION & TELEGRAM BOT
# --------------------------------------------------
session = Session()  # Uses .ratio1 config or env variables

def reply(plugin: CustomPluginTemplate, message: str, user: str):
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
      "min_level": 4,
      "max_level": 7,
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
      "min_level": 8,
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
    },
    "energy_drink": {
      "name": "Energy Drink 🧃",
      "description": "Restores 10 energy points",
      "price": 7,
      "type": "consumable"
    },
    "bomb": {
      "name": "Bomb 💣",
      "description": "Deals 5 damage to a monster before combat starts",
      "price": 15,
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
    
    # Define biomes and their specifications
    biomes = {
      "FOREST": {
        "emoji": "🌲",
        "description": "A dense forest with healing herbs",
        "tile_probs": {
          "COIN": 0.10,
          "TRAP": 0.05,   # Fewer traps in forest
          "MONSTER": 0.10,
          "HEALTH": 0.15, # More health tiles in forest
          "EMPTY": 0.60
        }
      },
      "LAVA_CAVES": {
        "emoji": "🌋",
        "description": "Hot caves with dangerous traps but valuable treasures",
        "tile_probs": {
          "COIN": 0.15,   # More treasures in caves
          "TRAP": 0.20,   # More traps in caves
          "MONSTER": 0.15,
          "HEALTH": 0.05,
          "EMPTY": 0.45
        }
      },
      "ICE_WASTES": {
        "emoji": "❄️",
        "description": "Frozen wasteland that slows movement",
        "tile_probs": {
          "COIN": 0.10,
          "TRAP": 0.10,
          "MONSTER": 0.15,
          "HEALTH": 0.05,
          "EMPTY": 0.60
        },
        "energy_multiplier": 1.5  # Movement costs more energy here
      },
      "PLAINS": {  # Default biome
        "emoji": "🌾",
        "description": "Flat plains with balanced features",
        "tile_probs": {
          "COIN": 0.10,
          "TRAP": 0.10,
          "MONSTER": 0.10,
          "HEALTH": 0.05,
          "EMPTY": 0.65
        }
      }
    }
    
    # Generate biome regions using noise (simplified with basic division)
    plugin.P("Generating biome regions...")
    
    new_map = []
    plugin.P("Starting to populate map rows...")
    
    # Track tile distribution for logging
    tile_counts = {"COIN": 0, "TRAP": 0, "MONSTER": 0, "HEALTH": 0, "EMPTY": 0}
    biome_counts = {biome: 0 for biome in biomes}
    monster_level_counts = {}
    
    for y in plugin.np.arange(0, GRID_HEIGHT):
      if y % 10 == 0:
        plugin.P(f"Generating row {y}/{GRID_HEIGHT}...")
        
      row = []
      for x in plugin.np.arange(0, GRID_WIDTH):
        # Determine biome based on location in the map (simple division into quadrants)
        if x < GRID_WIDTH/2 and y < GRID_HEIGHT/2:
          biome_type = "FOREST"
        elif x >= GRID_WIDTH/2 and y < GRID_HEIGHT/2:
          biome_type = "LAVA_CAVES"
        elif x < GRID_WIDTH/2 and y >= GRID_HEIGHT/2:
          biome_type = "ICE_WASTES"
        else:
          biome_type = "PLAINS"
        
        biome_counts[biome_type] += 1
        biome_data = biomes[biome_type]
        
        # Use biome-specific tile probabilities
        probs = biome_data["tile_probs"]
        tile_type = plugin.np.random.choice(
            ["COIN", "TRAP", "MONSTER", "HEALTH", "EMPTY"],
            p=[probs["COIN"], probs["TRAP"], probs["MONSTER"], probs["HEALTH"], probs["EMPTY"]]
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
            "monster_level": monster_level if tile_type == "MONSTER" else 0,
            "monster_type": get_monster_type_for_level(monster_level) if tile_type == "MONSTER" else "",
            "biome": biome_type,
            "biome_emoji": biome_data["emoji"]
        })
      new_map.append(row)
    
    # Set starting point to empty and visible
    new_map[0][0] = {"type": "EMPTY", "visible": True, "monster_level": 0, "biome": "PLAINS", "biome_emoji": biomes["PLAINS"]["emoji"]}
    
    # Log tile distribution statistics
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    plugin.P(f"Map generation complete! Generated {total_tiles} tiles in {plugin.time() - start_time:.2f} seconds")
    plugin.P(f"Tile distribution summary:")
    for tile_type, count in tile_counts.items():
      percentage = (count / total_tiles) * 100
      plugin.P(f"  {tile_type}: {count} tiles ({percentage:.2f}%)")
    
    # Log biome distribution
    plugin.P(f"\nBiome distribution:")
    for biome_type, count in biome_counts.items():
      percentage = (count / total_tiles) * 100
      plugin.P(f"  {biome_type}: {count} tiles ({percentage:.2f}%)")
    
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
    
    # Make spawn location and surroundings visible
    plugin.obj_cache["shared_map"][spawn_y][spawn_x]["visible"] = True
    
    # Reveal surroundings around the spawn point
    for dy in range(-1, 2):
      for dx in range(-1, 2):
        nx, ny = spawn_x + dx, spawn_y + dy
        if 0 <= nx < GRID_WIDTH and 0 <= ny < GRID_HEIGHT:
          plugin.obj_cache["shared_map"][ny][nx]["visible"] = True
    
    return {
        "position": (spawn_x, spawn_y),
        "previous_position": (spawn_x, spawn_y),  # Initialize previous position
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
        "last_message_time": plugin.time(),  # Track when the player last sent a message
        "status": "exploring",  # Player's current state: exploring, fighting, recovering
        "status_since": plugin.time(),  # When the current status was set
        "inventory": {
            "health_potion": 0,
            "map_scroll": 0,
            "energy_drink": 0,
            "bomb": 0
        },
        "equipment": {
            "weapon": None,
            "armor": None,
            "accessory": []
        }
    }

  def handle_fight_command(player, game_map):
    """
    Handles the /fight command when a player decides to fight a monster.
    Initiates combat with a monster at the player's current position.
    """
    # Only allow fighting if the player is in "prepare_to_fight" status
    if player["status"] != "prepare_to_fight":
      return "There's nothing to fight here!"
    
    # Get player's position and monster level
    x, y = player["position"]
    monster_level = game_map[y][x]["monster_level"]
    
    # Get or generate monster type
    if "monster_type" not in game_map[y][x]:
      game_map[y][x]["monster_type"] = get_monster_type_for_level(monster_level)
    
    monster_type = game_map[y][x]["monster_type"]
    monster_name = MONSTER_TYPES[monster_type]["name"]
    
    # Store the monster_type in player data for combat consistency
    player["current_monster_type"] = monster_type
    
    # Consume energy for combat
    player["energy"] -= ENERGY_COSTS["attack"]
    
    # Set player status to fighting to prevent the timer-based combat initiation
    player = update_player_status(player, "fighting")
    
    # Initialize combat session manually
    # Find user_id by looking for this player object in the users cache
    user_id = None
    for uid, p in plugin.obj_cache.get("users", {}).items():
      if p is player:
        user_id = uid
        break
    
    if user_id and "combat" not in plugin.obj_cache:
      plugin.obj_cache["combat"] = {}
      
    if user_id:
      plugin.obj_cache["combat"][user_id] = {
        "monster": create_monster_of_type(monster_type, monster_level),
        "last_round_time": plugin.time(),
        "round_number": 0,
        "initial_player_health": player["health"]
      }
    
    return f"⚔️ You decide to fight the {monster_name}!\nCombat will proceed automatically."

  def handle_flee_command(player, game_map):
    """
    Handles the /flee command when a player decides to flee from a monster.
    Moves player back to previous position and sets status to exploring.
    """
    # Allow fleeing if player is in prepare_to_fight or fighting status
    if player["status"] != "prepare_to_fight" and player["status"] != "fighting":
      return "You're not in danger! No need to flee."
    
    # Get monster info at current position
    x, y = player["position"]
    monster_level = game_map[y][x]["monster_level"]
    
    # Get or generate monster type
    if "monster_type" not in game_map[y][x]:
      game_map[y][x]["monster_type"] = get_monster_type_for_level(monster_level)
    
    monster_type = game_map[y][x]["monster_type"]
    monster_name = MONSTER_TYPES[monster_type]["name"]
    
    # Get biome information for energy cost
    biome_type = game_map[y][x].get("biome", "PLAINS")
    
    # Small energy cost for fleeing, adjusted by biome
    flee_energy_cost = 1
    
    # Define biomes and their energy multipliers (reference)
    biomes = {
      "FOREST": { "energy_multiplier": 1.0 },
      "LAVA_CAVES": { "energy_multiplier": 1.2 },
      "ICE_WASTES": { "energy_multiplier": 1.5 },
      "PLAINS": { "energy_multiplier": 1.0 }
    }
    
    # Apply biome-specific energy multiplier
    if biome_type in biomes:
      energy_multiplier = biomes[biome_type].get("energy_multiplier", 1.0)
      flee_energy_cost = int(flee_energy_cost * energy_multiplier)
    
    # Apply flee action
    if player["energy"] < flee_energy_cost:
      # If not enough energy, player still flees but with consequences
      player["energy"] = 0
      player = update_player_status(player, "recovering")
    else:
      player["energy"] -= flee_energy_cost
      player = update_player_status(player, "exploring")
    
    # Move player back to previous position
    old_pos = player["position"]
    player["position"] = player["previous_position"]
    
    # Ensure the monster remains on the tile player fled from
    # (this is important to preserve the game state)
    if game_map[old_pos[1]][old_pos[0]]["type"] == "MONSTER":
      # Monster remains on the tile
      pass
    
    # Reveal surroundings at the new position
    reveal_surroundings(player, game_map)
    
    # Generate map view from new position
    map_view = visualize_map(player, game_map)
    
    return f"{map_view}\n\n💨 You wisely decide to flee from the {monster_name}!\nYou return to your previous position at {player['position']}.\nEnergy: -{flee_energy_cost}"

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
    elif player["status"] == "prepare_to_fight":
      player_emoji = "⚠️"  # Warning emoji for prepare_to_fight
    
    # Get player's current biome
    current_tile = game_map[y][x]
    current_biome = current_tile.get("biome", "PLAINS")
    biome_emoji = current_tile.get("biome_emoji", "🌾")
      
    map_view = f"🗺️ Your location: ({x}, {y}) | Status: {player_emoji} {player['status'].capitalize()}\n"
    map_view += f"Biome: {biome_emoji} {current_biome.replace('_', ' ')}\n\n"

    for ny in range(max(0, y - view_distance), min(GRID_HEIGHT, y + view_distance + 1)):
      for nx in range(max(0, x - view_distance), min(GRID_WIDTH, x + view_distance + 1)):
        if (nx, ny) == (x, y):
          map_view += f"{player_emoji} "  # Player with status-specific emoji
        elif game_map[ny][nx]["visible"]:
          tile_type = game_map[ny][nx]["type"]
          # Get biome information
          biome_type = game_map[ny][nx].get("biome", "PLAINS")
          biome_emoji = game_map[ny][nx].get("biome_emoji", "")
          
          # Add a small indicator of biome to the background
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
            # For empty tiles, show the biome background
            map_view += f"{biome_emoji} "
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

    # Check if player is in prepare_to_fight state
    if player["status"] == "prepare_to_fight":
      return "You are facing a monster! Use /fight to engage or /flee to retreat."

    # Check if player is recovering
    if player["status"] == "recovering":
      return "You cannot move while recovering! Wait until you are fully healed and energized."

    # Check if player is not exploring
    if player["status"] != "exploring":
      return "You can only move while exploring!"

    # Store current position as previous position before moving
    prev_x, prev_y = player["position"]
    player["previous_position"] = (prev_x, prev_y)
    
    # Get the current biome of the player before moving
    prev_biome_type = game_map[prev_y][prev_x].get("biome", "PLAINS")
    
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

    # Check what's on the tile we're moving to
    new_tile = game_map[y][x]
    
    # Calculate energy cost for this move
    energy_cost = ENERGY_COSTS["move"]
    
    # Adjust energy cost based on biome
    biome_type = new_tile.get("biome", "PLAINS")
    biome_message = ""
    
    # Define biomes and their specifications (reference to match generate_map)
    biomes = {
      "FOREST": {
        "emoji": "🌲",
        "description": "A dense forest with healing herbs",
        "energy_multiplier": 1.0
      },
      "LAVA_CAVES": {
        "emoji": "🌋",
        "description": "Hot caves with dangerous traps but valuable treasures",
        "energy_multiplier": 1.2  # Slightly more energy in hot caves
      },
      "ICE_WASTES": {
        "emoji": "❄️",
        "description": "Frozen wasteland that slows movement",
        "energy_multiplier": 1.5  # Movement costs more energy here
      },
      "PLAINS": {  # Default biome
        "emoji": "🌾",
        "description": "Flat plains with balanced features",
        "energy_multiplier": 1.0
      }
    }
    
    # Apply biome-specific energy multiplier
    if biome_type in biomes:
      biome_data = biomes[biome_type]
      energy_multiplier = biome_data.get("energy_multiplier", 1.0)
      energy_cost = int(energy_cost * energy_multiplier)
      
      # Add biome message ONLY if the player is entering a different biome
      if biome_type != prev_biome_type:
        biome_message = f"\nYou've entered {biome_data['emoji']} {biome_type.replace('_', ' ')}! {biome_data['description']}."
    
    # Check if player has enough energy for the move
    if player["energy"] < energy_cost:
      # Set player status to recovering if they're too exhausted to move
      player = update_player_status(player, "recovering")
      return f"You are too exhausted to move! Energy: {int(player['energy'])}/{player['max_energy']}\nWait for your energy to regenerate."
    
    # Consume energy
    player["energy"] -= energy_cost
    
    # Actually move the player
    player["position"] = (x, y)
    tile = game_map[y][x]
    tile["visible"] = True
    reveal_surroundings(player, game_map)

    # Basic movement message
    msg = f"You moved {direction} to ({x},{y}). Energy: -{energy_cost} "
    
    if biome_message:
      msg += biome_message
    
    if tile["type"] == "COIN":
      base_coins = plugin.np.random.randint(1, 3)
      player["coins"] += base_coins
      tile["type"] = "EMPTY"
      msg += f"\nYou found {base_coins} coin(s)! "

    elif tile["type"] == "TRAP":
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
        msg += "\nYou nimbly avoided a trap! "
      else:
        base_damage = plugin.np.random.randint(1, 3)
        damage = max(1, base_damage)
        player["health"] -= damage
        msg += f"\nYou triggered a trap! Health -{damage}. "

    elif tile["type"] == "MONSTER":
      # Instead of instant combat, initiate prepare_to_fight state
      monster_level = tile["monster_level"]
      monster_type = tile.get("monster_type", get_monster_type_for_level(monster_level))
      
      # Store the monster type in the tile for consistency
      tile["monster_type"] = monster_type
      
      # Get monster info based on type
      monster_info = MONSTER_TYPES[monster_type]
      monster_name = monster_info["name"]
      
      # Calculate monster stats
      hp = monster_info["base_hp"] + (monster_level - 1) * monster_info["hp_per_level"]
      min_damage = monster_info["min_damage"] + (monster_level - 1) * monster_info["damage_per_level"]
      max_damage = monster_info["max_damage"] + (monster_level - 1) * monster_info["damage_per_level"]
      
      # Store the monster type for combat consistency
      player["current_monster_type"] = monster_type
      
      # Set player status to prepare_to_fight
      player = update_player_status(player, "prepare_to_fight")


      msg += f"\n⚠️⚠️⚠️ You encountered a level {monster_level} {monster_name}!⚠️⚠️⚠️\n\n"
      msg += f"Monster Stats:\n"
      msg += f"❤️ HP: {hp}\n"
      msg += f"⚔️ Damage: {min_damage}-{max_damage}\n"
      msg += f"✨ XP Reward: {monster_info['xp_reward'] * monster_level}\n"
      msg += f"💰 Coin Reward: {monster_info['coin_reward'][0] * monster_level}-{monster_info['coin_reward'][1] * monster_level}\n\n"
      msg += f"You have 5 seconds to decide:\n"
      msg += f"/fight - Attack the monster\n"
      msg += f"/flee - Return to your previous position"

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
    shop_text += "\nYou can use spaces or underscores in item names (e.g., 'map scroll' or 'map_scroll')"
    shop_text += "\nAvailable items: health_potion, sword, shield, amulet, boots, map_scroll, energy_drink, bomb"
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

    elif item_id == "energy_drink":
      # Use energy drink to restore energy
      player["energy"] += 10
      player["inventory"][item_id] -= 1
      return "You used an Energy Drink. Energy: +10"

    elif item_id == "bomb":
      # Check if player is in combat or about to enter combat
      x, y = player["position"]

      # Store the bomb usage flag for use in the combat session
      player["bomb_used"] = True
      player["inventory"][item_id] -= 1
      return "You set a Bomb that will deal 5 damage to the monster when combat starts!"

    return f"Cannot use {item_id}."

  def display_help():
    """Returns extended help instructions."""
    help_text = ("Welcome to Shadowborn!\n"
                 "Instructions:\n"
                 "- All players explore the SAME dungeon map together!\n"
                 "- Explore the dungeon using movement commands:\n"
                 "  • N or north - Move North\n"
                 "  • S or south - Move South\n"
                 "  • W or west - Move West\n"
                 "  • E or east - Move East\n"
                 "  • 'go north', 'go south', etc. - Move in specified direction\n"
                 "- Check your stats with /status to see health, coins, XP, level, attack, and equipment.\n"
                 "- Defeat monsters to earn XP and level up.\n"
                 "- Collect coins and visit the shop (/shop) to buy upgrades using /buy.\n"
                 "- Use consumable items from your inventory with /use.\n"
                 "- View the map with /map.\n"
                 "- Complete quests and explore the vast map with other players.\n"
                 "\nMap Biomes:\n"
                 "The world is divided into distinct regions, each with unique characteristics:\n"
                 "- 🌲 Forest: Dense woods with abundant health pickups. Normal movement cost.\n"
                 "- 🌋 Lava Caves: Dangerous areas with more traps but valuable treasures. Slightly increased movement cost.\n"
                 "- ❄️ Ice Wastes: Frozen lands where movement is difficult, requiring 50% more energy to traverse.\n"
                 "- 🌾 Plains: Balanced areas with no special effects. Standard movement cost.\n"
                 "\nMonster Encounters:\n"
                 "- When encountering a monster, you have 5 seconds to decide what to do.\n"
                 "- Use /fight to engage in battle, or /flee to return to your previous position.\n"
                 "- If you don't respond within 5 seconds, battle starts automatically.\n"
                 "- Use a Bomb before combat to deal initial damage to the monster.\n"
                 "\nPlayer Status System:\n"
                 "Your character can be in one of four states that affect gameplay:\n"
                 "- Exploring: Normal movement with standard regeneration rates.\n"
                 "- Prepare to Fight: You've encountered a monster and must decide to fight or flee.\n"
                 "- Fighting: Engaged in combat with reduced health regeneration.\n"
                 "- Recovering: Resting with increased health and energy regeneration.\n"
                 "Your status changes automatically based on your actions, but you can also set it manually.\n"
                 "\nConsumable Items:\n"
                 "- Health Potion (🧪): Restores 5 health points\n"
                 "- Map Scroll (📜): Reveals a larger area of the map\n"
                 "- Energy Drink (🧃): Restores 10 energy points\n"
                 "- Bomb (💣): Deals 5 damage to a monster before combat starts\n"
                 "\nAvailable Commands:\n"
                 "Note: All commands can be used both with and without the leading slash.\n"
                 "1. /start  - Restart your character (keeps the shared map).\n"
                 "2. N/S/W/E or north/south/west/east - Move your character in the specified direction.\n"
                 "3. 'go north', 'go south', etc. - Alternative way to move in the specified direction.\n"
                 "4. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n"
                 "5. /map    - View the map of your surroundings.\n"
                 "6. /shop   - Visit the shop to browse and buy upgrades/items.\n"
                 "7. /buy <item_name> - Purchase an item from the shop. You can use spaces in item names (e.g., 'map scroll').\n"
                 "8. /use <item_name> - Use a consumable item from your inventory. You can use spaces in item names (e.g., 'energy drink').\n"
                 "9. /fight  - Engage in combat with a monster you've encountered.\n"
                 "10. /flee   - Retreat from a monster encounter back to your previous position.\n"
                 "11. /help   - Display help information.\n"
                 "12. /wiki   - Access the game's knowledge base with additional information and tips.\n"
                 "\nGame Initialization:\n"
                 "The game world needs to be initialized before anyone can play.\n"
                 "- /init   - Initialize the game world (admin only, can only be used once).")
    return help_text

  def update_player_status(player, new_status):
    """
    Updates a player's status and records when it changed.
    """
    if new_status not in ["exploring", "fighting", "recovering", "prepare_to_fight"]:
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

  def get_monster_id_for_level(level):
    """
    Returns an appropriate monster type name for the given level.
    This function is kept for backward compatibility but now returns
    the monster type name directly instead of an ID.
    """
    return get_monster_type_for_level(level)

  
  def create_monster_of_type(monster_type, level):
    """
    Creates a new monster of a specific type with appropriate level.
    """
    # Fallback if monster_type doesn't exist in MONSTER_TYPES
    if monster_type not in MONSTER_TYPES:
      return create_monster(level)

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

  # --------------------------------------------------
  text = (message or "").strip().lower()
  user_id = str(user)

  # ---------------------------
  # Ensure bot status tracking exists
  # ---------------------------
  current_time = plugin.time()
  if "bot_status" not in plugin.obj_cache:
    # Initialize bot status tracking
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
            "Note: All commands can be used both with and without the leading slash.\n"
            "1. /start  - Restart your character (keeps the shared map).\n" 
            "2. N/S/W/E or north/south/west/east - Move your character in the specified direction.\n" 
            "3. 'go north', 'go south', etc. - Alternative way to move in the specified direction.\n" 
            "4. /status - Display your current stats (health, coins, level, XP, attack, and equipment).\n" 
            "5. /map    - View the map of your surroundings.\n" 
            "6. /shop   - Visit the shop to browse and buy upgrades/items.\n" 
            "7. /buy <item_name> - Purchase an item from the shop. You can use spaces in item names (e.g., 'map scroll').\n" 
            "8. /use <item_name> - Use a consumable item from your inventory. You can use spaces in item names (e.g., 'energy drink').\n"
            "9. /fight  - Engage in combat with a monster you've encountered.\n"
            "10. /flee   - Retreat from a monster encounter back to your previous position.\n"
            "11. /help   - Display help information.\n"
            "12. /wiki   - Access the game's knowledge base with additional information and tips.")
    else:
      return ("⚠️ GAME NOT INITIALIZED ⚠️\n\n"
             "The game world hasn't been created yet!\n"
             "An administrator needs to use the /init command to generate the game world before anyone can play.\n\n"
             "Available Commands:\n"
             "1. /init   - Initialize the game world (admin only, first-time setup)\n"
             "2. /help   - Display help information\n"
             "3. /botstatus - View technical information about the bot")

  command = parts[0]

  # Now strip the slash from command if it exists - this allows commands to work both with and without slash
  command_without_slash = command.lstrip('/')

  # Handle initialization command
  if command_without_slash == "init":
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
  
  # Update the last message time for the player
  player["last_message_time"] = current_time

  # ---------------------------
  # NSEW Controls Processing
  # ---------------------------
  # Check if this is a single-letter NSEW command
  if command in ["n", "s", "e", "w"]:
    # Map NSEW to directions
    direction_map = {"n": "up", "s": "down", "e": "right", "w": "left"}
    direction = direction_map[command]
    return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])

  # ---------------------------
  # Full compass direction commands (north, south, east, west)
  # ---------------------------
  if command in ["north", "south", "east", "west"]:
    # Map compass directions to up/down/left/right
    direction_map = {"north": "up", "south": "down", "east": "right", "west": "left"}
    direction = direction_map[command]
    return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])

  # ---------------------------
  # 'Go direction' commands (go north, go south, go east, go west)
  # ---------------------------
  if command == "go" and len(parts) > 1:
    compass_direction = parts[1].lower()
    if compass_direction in ["north", "south", "east", "west"]:
      direction_map = {"north": "up", "south": "down", "east": "right", "west": "left"}
      direction = direction_map[compass_direction]
      return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])
    elif compass_direction in ["n", "s", "e", "w"]:
      direction_map = {"n": "up", "s": "down", "e": "right", "w": "left"}
      direction = direction_map[compass_direction]
      return move_player(plugin.obj_cache["users"][user_id], direction, plugin.obj_cache["shared_map"])
    else:
      return f"Invalid direction: {compass_direction}. Use north, south, east, or west."

  # Process commands with or without slash
  if command_without_slash == "start":
    # First send welcome message and initialization notification
    welcome_message = ("Welcome to Shadowborn!\n" 
                      "This is an epic roguelike adventure where you explore a dangerous dungeon, defeat monsters, collect coins, earn XP, and purchase upgrades from the shop.\n" 
                      "Your goal is to explore the vast map and complete quests.\n"
                      "All players share the same map - you'll see changes made by other players!\n\n"
                      "⏳ Initializing your character... Please wait a moment as your hero materializes in the world... ⏳\n\n"
                      "Use N/S/E/W, north/south/east/west, 'go north', 'go south', 'go east', 'go west'. to move around, status to check your stats, and shop to buy upgrades.\n"
                      "Commands can be used with or without the leading slash (e.g., /status or status).\n\n"
                      "For more detailed instructions, use help or /help."
                      "To discover our world use wiki or /wiki.")

    # Send the welcome message first
    plugin.send_message_to_user(user_id, welcome_message)

    # Now create the player
    plugin.obj_cache["users"][user_id] = create_new_player()

    # Generate the map view
    map_view = visualize_map(plugin.obj_cache["users"][user_id], plugin.obj_cache["shared_map"])

    # Return the map view as a separate message
    return f"✅ Character initialization complete! Your adventure begins now!\n\n{map_view}"

  elif command_without_slash == "status":
    p = plugin.obj_cache["users"][user_id]
    x, y = p["position"]
    
    # Get biome information for current position
    current_tile = game_map[y][x]
    current_biome = current_tile.get("biome", "PLAINS")
    biome_emoji = current_tile.get("biome_emoji", "🌾")

    # Calculate total stats including equipment bonuses
    total_attack = p["attack"]
    total_damage_reduction = p["damage_reduction"]
    total_max_health = 0
    total_dodge = p["dodge_chance"]

    # Get equipment bonuses
    for slot, item_id in p["equipment"].items():
      if slot == "accessory":
        # Handle multiple accessories
        for acc_id in item_id:
          if acc_id and acc_id in SHOP_ITEMS:
            item = SHOP_ITEMS[acc_id]
            if "attack_bonus" in item:
              total_attack += item["attack_bonus"]
            if "damage_reduction" in item:
              total_damage_reduction += item["damage_reduction"]
            if "max_health_bonus" in item:
              total_max_health += item["max_health_bonus"]
            if "dodge_chance" in item:
              total_dodge += item["dodge_chance"]
      else:
        # Handle single equipment items (weapon, armor)
        if item_id and item_id in SHOP_ITEMS:
          item = SHOP_ITEMS[item_id]
          if "attack_bonus" in item:
            total_attack += item["attack_bonus"]
          if "damage_reduction" in item:
            total_damage_reduction += item["damage_reduction"]
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
    
    # Get status emoji and formatted status name
    status_emoji = "🔍"
    status_display = "Exploring"
    
    if p["status"] == "fighting":
      status_emoji = "⚔️"
      status_display = "Fighting"
    elif p["status"] == "recovering":
      status_emoji = "💤"
      status_display = "Recovering"
    elif p["status"] == "prepare_to_fight":
      status_emoji = "⚠️"
      status_display = "Deciding to Fight"
    
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

    # Define biomes and their specifications (reference)
    biomes = {
      "FOREST": {
        "emoji": "🌲",
        "description": "A dense forest with healing herbs",
        "energy_multiplier": 1.0
      },
      "LAVA_CAVES": {
        "emoji": "🌋",
        "description": "Hot caves with dangerous traps but valuable treasures",
        "energy_multiplier": 1.2
      },
      "ICE_WASTES": {
        "emoji": "❄️",
        "description": "Frozen wasteland that slows movement",
        "energy_multiplier": 1.5
      },
      "PLAINS": {
        "emoji": "🌾",
        "description": "Flat plains with balanced features",
        "energy_multiplier": 1.0
      }
    }
    
    # Get biome effects description
    biome_effects = ""
    if current_biome in biomes:
      biome_data = biomes[current_biome]
      if biome_data.get("energy_multiplier", 1.0) > 1.0:
        biome_effects = f"(Movement Energy: x{biome_data['energy_multiplier']})"

    status_message = (f"📊 STATUS 📊\n"
                     f"🗺️ Position: ({x}, {y})\n"
                     f"🌍 Biome: {biome_emoji} {current_biome.replace('_', ' ')} {biome_effects}\n"
                     f"👤 Status: {status_emoji} {status_display} ({minutes}m {seconds}s)\n"
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

  elif command_without_slash == "map":
    return visualize_map(plugin.obj_cache["users"][user_id], plugin.obj_cache["shared_map"])

  elif command_without_slash == "shop":
    return display_shop(player)

  elif command_without_slash == "buy":
    if len(parts) < 2:
      return "Usage: /buy <item_name>\nUse /shop to see available items.\nYou can use spaces in item names (e.g., 'map scroll')"

    # Join all words after 'buy' and convert spaces to underscores to match item_id format
    item_id = '_'.join(parts[1:]).lower()
    return buy_item(player, item_id)

  elif command_without_slash == "use":
    if len(parts) < 2:
      return "Usage: /use <item_name>\nItems you can use: health_potion, map_scroll, energy_drink, bomb\nYou can use spaces in item names (e.g., 'energy drink')"

    # Join all words after 'use' and convert spaces to underscores to match item_id format
    item_id = '_'.join(parts[1:]).lower()
    return use_item(player, item_id, game_map)

  elif command_without_slash == "help":
    return display_help()

  elif command in ["/wiki", "wiki"]:
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
      "• Map Scroll (📜): Reveals larger area\n"
      "• Energy Drink (🧃): Restores 10 energy points\n"
      "• Bomb (💣): Deals 5 damage to a monster before combat starts\n\n"
      "🛍️ SHOP ITEMS:\n"
      "• Health Potion: 5 coins\n"
      "• Sword (⚔️): +1 Attack, 15 coins\n"
      "• Shield (🛡️): +10% Damage Reduction, 20 coins\n"
      "• Magic Amulet (🔮): +3 Max Health, 25 coins\n"
      "• Speed Boots (👢): +5% Dodge Chance, 30 coins\n"
      "• Map Scroll: 10 coins\n"
      "• Energy Drink: 7 coins\n"
      "• Bomb: 15 coins\n\n"
      "💡 TIPS:\n"
      "• Use /status to check your stats\n"
      "• Use /map to view your surroundings\n"
      "• Higher level monsters give better rewards\n"
      "• Always keep some health potions for emergencies\n"
      "• Use map scrolls to plan your route\n"
      "• Consider your energy before engaging in combat"
    )
    return wiki_text

  elif command_without_slash == "botstatus":
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

  elif command_without_slash == "fight":
    response = handle_fight_command(player, game_map)
    # Make sure we save the updated player state back to the cache
    plugin.obj_cache["users"][user_id] = player
    return response

  elif command_without_slash == "flee":
    response = handle_flee_command(player, game_map)
    
    # Clean up combat session if user was in combat
    if user_id in plugin.obj_cache.get("combat", {}):
      del plugin.obj_cache["combat"][user_id]
    
    return response
    
  else:
    return ("Commands:\n"
            "/start or start - Restart your character (keeps the shared map)\n" 
            "N/S/W/E or north/south/west/east - Move your character in the specified direction\n"
            "'go north', 'go south', etc. - Alternative way to move in the specified direction\n"
            "/status or status - Display your current stats: position, health, coins, level, XP, damage reduction, and kills\n" 
            "/map or map - Reveal the map of your surroundings\n"
            "/shop or shop - Visit the shop to buy upgrades and items\n" 
            "/buy or buy <item_name> - Purchase an item from the shop. You can use spaces in item names (e.g., 'map scroll')\n" 
            "/use or use <item_name> - Use a consumable item from your inventory. You can use spaces in item names (e.g., 'energy drink')\n"
            "/fight or fight - Engage in combat with a monster you've encountered\n"
            "/flee or flee - Retreat from a monster encounter back to your previous position\n"
            "/wiki or wiki - Access the game's knowledge base with additional information and tips\n"
            "/help or help - Display this help message"
            + ("\n/init or init - Initialize the game world (admin only)" if not plugin.obj_cache["bot_status"]["initialized"] else ""))

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
  COMBAT_DECISION_TIME = 5  # Seconds player has to decide to fight or flee

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
      "min_level": 4,
      "max_level": 7,
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
      "min_level": 8,
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

  def check_level_up(player):
    """Check if player has leveled up and apply level up benefits."""
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

        level_up_msg = (f"🌟 LEVEL UP!\n"
                        f"You are now level {new_level}!\n"
                        f"Max Health: {player['max_health']}\n"
                        f"Max Energy: {player['max_energy']}\n"
                        f"🌟 You can continue exploring the dungeon! Use /map to see your surroundings.")
        return True, level_up_msg
    return False, ""

  def check_exploration_progress(game_map):
    """Calculates the percentage of the map that has been explored (for informational purposes only)."""
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    visible_tiles = sum(1 for row in game_map for tile in row if tile["visible"])
    return (visible_tiles / total_tiles) * 100

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
    if new_status not in ["exploring", "fighting", "recovering", "prepare_to_fight"]:
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
    - "prepare_to_fight": slower regeneration like fighting
    """
    # Apply status modifiers to regeneration rates
    status_modifiers = {
      "recovering": {"health": 1.5, "energy": 1.5},
      "exploring": {"health": 1.0, "energy": 1.0},
      "fighting": {"health": 0.5, "energy": 1.0},
      "prepare_to_fight": {"health": 0.5, "energy": 1.0}  # Same as fighting
    }
    
    # Default to exploring modifiers if status is invalid
    modifiers = status_modifiers.get(player["status"], status_modifiers["exploring"])
    
    # Convert per-minute rates to per-second for calculations
    hp_regen_per_second = (player["hp_regen_rate"] / 60.0) * modifiers["health"]
    energy_regen_per_second = (player["energy_regen_rate"] / 60.0) * modifiers["energy"]

    # Store old health and energy for checking recovery completion
    old_health = player["health"]
    old_energy = player["energy"]
    
    # Was fully recovered before this update
    was_fully_recovered = (old_health >= player["max_health"] and old_energy >= player["max_energy"])

    # Regenerate health 
    if player["health"] < player["max_health"]:
      hp_gain = hp_regen_per_second * time_elapsed
      player["health"] = min(player["max_health"], player["health"] + hp_gain)

    # Regenerate energy 
    if player["energy"] < player["max_energy"]:
      energy_gain = energy_regen_per_second * time_elapsed
      player["energy"] = min(player["max_energy"], player["energy"] + energy_gain)
      
    # Is fully recovered after this update
    is_fully_recovered = (player["health"] >= player["max_health"] and player["energy"] >= player["max_energy"])
    
    # Check if player just recovered (health and energy are both full)
    just_recovered = (is_fully_recovered and not was_fully_recovered)
    
    # Check if player has been in recovery long enough (5 minutes = 300 seconds)
    current_time = plugin.time()
    recovery_duration = current_time - player.get("status_since", current_time)
    sufficient_recovery_time = recovery_duration >= 300  # 5 minutes
    
    # If player was recovering and is now fully recovered, set to exploring
    if player["status"] == "recovering" and is_fully_recovered:
      # Check if at least 5 minutes have passed since the last message
      time_since_last_message = current_time - player.get("last_message_time", 0)
      
      player = update_player_status(player, "exploring")
      
      # Return a notification if player is fully recovered and sufficient time has passed
      if sufficient_recovery_time and time_since_last_message >= 300:  # 5 minutes
        return player, "🌟 You have fully recovered and can now continue your adventure! Your health and energy are at maximum."
      
      # Return a simple notification for recovery with less time passed
      if just_recovered:
        return player, "You have recovered and can continue your adventure."

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

  def create_monster_of_type(monster_type, level):
    """
    Creates a new monster of a specific type with appropriate level.
    """
    # Fallback if monster_type doesn't exist in MONSTER_TYPES
    if monster_type not in MONSTER_TYPES:
      return create_monster(level)
      
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
    
    # Increment round counter
    combat_session["round_number"] += 1
    round_number = combat_session["round_number"]
    
    # Add round start message with combat status
    messages.append(f"⚔️ COMBAT ROUND {round_number} ⚔️")
    messages.append(f"Fighting {monster['name']} (Level {monster['level']})")
    
    # Apply bomb damage in first round if player used a bomb
    if round_number == 1 and player.get("bomb_used", False):
      bomb_damage = 5
      monster["hp"] -= bomb_damage
      messages.append(f"\n💣 BOMB DAMAGE:")
      messages.append(f"Your bomb explodes, dealing {bomb_damage} damage to the {monster['name']}!")
      # Reset the bomb usage flag
      player["bomb_used"] = False
      
      # Check if monster died from the bomb
      if monster["hp"] <= 0:
        # Award XP and coins
        coin_reward = plugin.np.random.randint(monster["coin_reward"][0], monster["coin_reward"][1] + 1)
        player["coins"] += coin_reward
        player["xp"] += monster["xp_reward"]
        
        # Calculate combat summary
        total_rounds = combat_session["round_number"]
        total_health_lost = combat_session["initial_player_health"] - player["health"]
        
        # Clear the monster tile
        x, y = player["position"]
        game_map[y][x]["type"] = "EMPTY"
        game_map[y][x]["monster_level"] = 0
        
        # Set player back to exploring
        player = update_player_status(player, "exploring")
        
        messages.append(f"\n🎯 VICTORY!")
        messages.append(f"The {monster['name']} was defeated by your bomb!")
        messages.append(f"Rewards: {coin_reward} coins, {monster['xp_reward']} XP")
        
        # Add combat summary
        messages.append(f"\n📈 COMBAT SUMMARY:")
        messages.append(f"Total Rounds: {total_rounds}")
        messages.append(f"Health Lost: {total_health_lost:.1f}")
        
        # Check for level up
        leveled_up, level_up_msg = check_level_up(player)
        if leveled_up:
          messages.append(f"\n{level_up_msg}")
        
        # Check exploration progress
        progress = check_exploration_progress(game_map)
        messages.append(f"\n🌍 Map Exploration: {progress}% complete")
        
        return True, "\n".join(messages)
    
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
      
      # Calculate combat summary
      total_rounds = combat_session["round_number"]
      total_health_lost = combat_session["initial_player_health"] - player["health"]
      
      # Clear the monster tile
      x, y = player["position"]
      game_map[y][x]["type"] = "EMPTY"
      game_map[y][x]["monster_level"] = 0
      
      # Set player back to exploring
      player = update_player_status(player, "exploring")
      
      messages.append(f"\n🎯 VICTORY!")
      messages.append(f"You defeated the {monster['name']}!")
      messages.append(f"Rewards: {coin_reward} coins, {monster['xp_reward']} XP")
      
      # Add combat summary
      messages.append(f"\n📈 COMBAT SUMMARY:")
      messages.append(f"Total Rounds: {total_rounds}")
      messages.append(f"Health Lost: {total_health_lost:.1f}")
      
      # Check for level up
      leveled_up, level_up_msg = check_level_up(player)
      if leveled_up:
        messages.append(f"\n{level_up_msg}")
      
      # Check exploration progress
      progress = check_exploration_progress(game_map)
      messages.append(f"\n🌍 Map Exploration: {progress}% complete")
      
      return True, "\n".join(messages)
    
    # Monster's attack
    monster_min_damage = max(1, monster["min_damage"] - player["attack"])
    monster_max_damage = max(2, monster["max_damage"])
    monster_damage = plugin.np.random.randint(monster_min_damage, monster_max_damage + 1)
    messages.append(f"\n🐾 Monster's attack:")
    
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
        
        # Calculate combat summary for defeat
        total_rounds = combat_session["round_number"]
        total_health_lost = combat_session["initial_player_health"] - 0  # Player lost all health
        
        messages.append(f"\n📈 COMBAT SUMMARY:")
        messages.append(f"Total Rounds: {total_rounds}")
        messages.append(f"Health Lost: {total_health_lost:.1f}")
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
      
      # Check for players in "prepare_to_fight" status
      if player["status"] == "prepare_to_fight" and user_id not in plugin.obj_cache.get("combat", {}):
        time_in_status = current_time - player["status_since"]
        
        # If 5 seconds have passed, automatically start combat
        if time_in_status >= COMBAT_DECISION_TIME:
          # Send timeout message
          plugin.send_message_to_user(user_id, "⏱️ Time's up! You couldn't decide in time. The monster attacks!")
          
          # Get player position and create monster for combat
          x, y = player["position"]
          monster_level = plugin.obj_cache["shared_map"][y][x]["monster_level"]
          
          # Set player to fighting status
          update_player_status(player, "fighting")
          
          # Create combat session
          if "current_monster_type" in player:
            # Use stored monster type if available
            monster_type = player["current_monster_type"]
            plugin.obj_cache["combat"][user_id] = {
              "monster": create_monster_of_type(monster_type, monster_level),
              "last_round_time": current_time,
              "round_number": 0,
              "initial_player_health": player["health"]
            }
          else:
            # Fallback to old behavior if no stored monster type
            plugin.obj_cache["combat"][user_id] = {
              "monster": create_monster(monster_level),
              "last_round_time": current_time,
              "round_number": 0,
              "initial_player_health": player["health"]
            }
      
      # Process combat if player is fighting
      elif player["status"] == "fighting":
        # Initialize or get combat session
        if user_id not in plugin.obj_cache["combat"]:
          # Get player's position and monster level
          x, y = player["position"]
          monster_level = plugin.obj_cache["shared_map"][y][x]["monster_level"]
          
          # Create new combat session using the stored monster type if available
          if "current_monster_type" in player:
            monster_type = player["current_monster_type"]
            plugin.obj_cache["combat"][user_id] = {
              "monster": create_monster_of_type(monster_type, monster_level),
              "last_round_time": current_time,
              "round_number": 0,
              "initial_player_health": player["health"]
            }
          else:
            # Fallback to old behavior if no stored monster type
            plugin.obj_cache["combat"][user_id] = {
              "monster": create_monster(monster_level),
              "last_round_time": current_time,
              "round_number": 0,
              "initial_player_health": player["health"]
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

