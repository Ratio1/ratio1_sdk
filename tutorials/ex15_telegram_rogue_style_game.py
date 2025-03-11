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
  # Dungeon progression
  EXPLORATION_THRESHOLD = 70  # Percentage of map that needs to be explored for exit to appear
  COIN_RETENTION = 0.7  # Percentage of coins kept when advancing to next dungeon
  # Multiplayer constants
  MAX_PLAYERS_PER_ROOM = 4
  ROOM_ID_LENGTH = 6

  # --------------------------------------------------
  # ROOM MANAGEMENT FUNCTIONS
  # --------------------------------------------------
  def generate_room_id():
    """Generates a random alphanumeric room ID."""
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    room_id = ''
    for _ in range(ROOM_ID_LENGTH):
        room_id += chars[plugin.np.random.randint(0, len(chars))]
    return room_id

  def create_room(creator_id):
    """Creates a new multiplayer room with the given creator as first player."""
    # Initialize room structure
    room_id = generate_room_id()

    # Check if room_id already exists (very unlikely but possible)
    while f"room_{room_id}" in plugin.obj_cache:
      room_id = generate_room_id()

    # Create shared game state for the room
    plugin.obj_cache[f"room_{room_id}"] = {
      "map": generate_map(),
      "players": {creator_id: create_new_player()},
      "creator": creator_id,
      "created_at": plugin.np.datetime64('now'),
      "messages": [],  # For in-game communication between players
      "dungeon_level": 1,
      "dungeon_completion": 0
    }

    # Track which room each player is in
    if "player_rooms" not in plugin.obj_cache:
      plugin.obj_cache["player_rooms"] = {}

    plugin.obj_cache["player_rooms"][creator_id] = room_id

    return room_id

  def join_room(player_id, room_id):
    """Adds a player to an existing room."""
    room_key = f"room_{room_id}"

    # Check if room exists
    if room_key not in plugin.obj_cache:
      return False, "Room not found. Please check the room code and try again."

    room = plugin.obj_cache[room_key]

    # Check if room is full
    if len(room["players"]) >= MAX_PLAYERS_PER_ROOM:
      return False, f"Room is full (max {MAX_PLAYERS_PER_ROOM} players)."

    # Add player to room
    if player_id not in room["players"]:
      room["players"][player_id] = create_new_player()

    # Update player's room reference
    if "player_rooms" not in plugin.obj_cache:
      plugin.obj_cache["player_rooms"] = {}

    plugin.obj_cache["player_rooms"][player_id] = room_id

    # Notify other players that someone joined
    room["messages"].append(f"Player has joined the room.")

    return True, f"Joined room {room_id} successfully! There are {len(room['players'])} players in this room."

  def leave_room(player_id):
    """Removes a player from their current room."""
    if "player_rooms" not in plugin.obj_cache or player_id not in plugin.obj_cache["player_rooms"]:
      return "You are not in any room."

    room_id = plugin.obj_cache["player_rooms"][player_id]
    room_key = f"room_{room_id}"

    if room_key in plugin.obj_cache:
      room = plugin.obj_cache[room_key]

      # Remove player from room
      if player_id in room["players"]:
        del room["players"][player_id]

      # Notify other players
      room["messages"].append(f"Player has left the room.")

      # If room is empty, delete it
      if len(room["players"]) == 0:
        del plugin.obj_cache[room_key]
      # If creator left, assign a new creator
      elif player_id == room["creator"] and len(room["players"]) > 0:
        room["creator"] = next(iter(room["players"].keys()))

    # Remove player's room reference
    del plugin.obj_cache["player_rooms"][player_id]

    return f"Left room {room_id}."

  def get_player_room(player_id):
    """Returns the room ID that the player is currently in, or None."""
    if "player_rooms" not in plugin.obj_cache or player_id not in plugin.obj_cache["player_rooms"]:
      return None
    return plugin.obj_cache["player_rooms"][player_id]

  def get_room_and_player_data(player_id):
    """Returns the room and player data for the given player ID."""
    room_id = get_player_room(player_id)
    if room_id is None:
      return None, None

    room_key = f"room_{room_id}"
    if room_key not in plugin.obj_cache:
      # Room doesn't exist but player thinks they're in it
      if "player_rooms" in plugin.obj_cache and player_id in plugin.obj_cache["player_rooms"]:
        del plugin.obj_cache["player_rooms"][player_id]
      return None, None

    room = plugin.obj_cache[room_key]
    player = room["players"].get(player_id)
    return room, player

  def list_players_in_room(room):
    """Returns a formatted string with the list of players in the room."""
    if not room or not room["players"]:
      return "No players in this room."

    result = "Players in this room:\n"
    for pid, p in room["players"].items():
      result += f"• Player at {p['position']} (Level {p['level']}, HP: {p['health']}/{p['max_health']})\n"
    return result

  def send_room_message(player_id, message):
    """Sends a message to all players in the room."""
    room_id = get_player_room(player_id)
    if room_id is None:
      return "You're not in a room. Join or create a room first."

    room_key = f"room_{room_id}"
    if room_key not in plugin.obj_cache:
      return "Room not found."

    room = plugin.obj_cache[room_key]
    # Truncate message history to last 20 messages
    if len(room["messages"]) > 20:
      room["messages"] = room["messages"][max(0, len(room["messages"]) - 20):]
      # room["messages"] = room["messages"][-20:]

    room["messages"].append(f"Player: {message}")
    return "Message sent to room."

  def get_room_messages(room):
    """Returns the message history for the room."""
    if not room or "messages" not in room:
      return "No messages."

    if not room["messages"]:
      return "No messages yet."

    result = "Recent messages:\n"
    # for msg in room["messages"][-5:]:  # Show last 5 messages
    for msg in room["messages"][max(0, len(room["messages"]) - 5):]:
      result += f"• {msg}\n"
    return result

  # --------------------------------------------------
  # MULTIPLAYER GAME MECHANICS
  # --------------------------------------------------
  def visualize_multiplayer_map(room, player_id):
    """Visualizes the map with all players' positions."""
    if not room or "map" not in room or player_id not in room["players"]:
      return "Map not available."

    game_map = room["map"]
    current_player = room["players"][player_id]
    
    # Get player position
    current_x, current_y = current_player["position"]
    
    # Rather than modifying an existing map, let's build it from scratch with proper alignment
    map_view = "Your surroundings:\n"
    
    # Count players on each cell for consistent display
    player_positions = {}
    
    # First, gather all player positions
    for pid, p in room["players"].items():
      x, y = p["position"]
      pos_key = f"{x},{y}"
      
      # Only track if visible
      if y < len(game_map) and x < len(game_map[0]) and game_map[y][x].get("visible", False):
        if pos_key not in player_positions:
          player_positions[pos_key] = []
        player_positions[pos_key].append(pid)
    
    # Now build the map
    view_distance = 2  # Same as in visualize_map
    
    for y in range(max(0, current_y - view_distance), min(len(game_map), current_y + view_distance + 1)):
      for x in range(max(0, current_x - view_distance), min(len(game_map[0]), current_x + view_distance + 1)):
        # Check if this tile is visible
        if not game_map[y][x].get("visible", False):
          map_view += "⬛"  # Unexplored
          continue
          
        # Check if there are players here
        pos_key = f"{x},{y}"
        if pos_key in player_positions and len(player_positions[pos_key]) > 0:
          # Calculate how many players are here
          player_count = len(player_positions[pos_key])
          
          # Check if current player is among them
          is_current_player_here = player_id in player_positions[pos_key]
          
          # Determine correct symbol
          if is_current_player_here and player_count > 2:
            # Current player plus others
            map_view += "⚡"  # Lightning for player encounter (narrower than sword)
          elif is_current_player_here:
            # Just current player - use the character icon
            map_view += "🧙"  # Character/player icon
          elif player_count == 1:
            map_view += "👤"  # Single other player
          elif player_count == 2:
            map_view += "👥"  # Two other players
          else:
            # 3+ other players - use number
            map_view += str(min(9, player_count))  # Cap at 9 for display
        else:
          # No players here, just show the tile
          tile_type = game_map[y][x]["type"]
          if tile_type == "COIN":
            map_view += "💰"
          elif tile_type == "TRAP":
            map_view += "🔥"
          elif tile_type == "MONSTER":
            # Different monster emoji based on level
            monster_level = game_map[y][x]["monster_level"]
            if monster_level <= 2:
              map_view += "👹"  # Regular monster
            elif monster_level <= 4:
              map_view += "👺"  # Stronger monster
            else:
              map_view += "👿"  # Boss monster
          elif tile_type == "HEALTH":
            map_view += "❤️"
          elif tile_type == "PORTAL":
            map_view += "🌀"  # Portal to next dungeon
          else:
            map_view += "⬜"  # Empty
      
      map_view += "\n"  # End of row
    
    # Add exploration info
    exploration = check_exploration_progress(game_map)
    has_portal = any(tile["type"] == "PORTAL" for row in game_map for tile in row)
    
    portal_msg = ""
    if has_portal:
      portal_msg = "\n🌀 Portal to next dungeon is visible on the map!"
    elif exploration >= EXPLORATION_THRESHOLD:
      portal_msg = "\n🌀 A portal to the next dungeon has appeared somewhere!"
    
    # Add player count info
    player_count_msg = f"\nPlayers in room: {len(room['players'])}"
    
    # Add a legend for the multiplayer symbols
    legend = "\n🧙 - You  👤 - Other player  👥 - Two players  ⚡ - Shared tile  3-9 - Multiple players"
    
    return f"{map_view}Exploration: {int(exploration)}%{portal_msg}{player_count_msg}{legend}"

  def multiplayer_move_player(room, player_id, direction):
    """Moves a player and handles interactions with the environment and other players."""
    if not room or "map" not in room or player_id not in room["players"]:
      return "Cannot move - not in a valid room."

    player = room["players"][player_id]
    game_map = room["map"]

    # Use the regular move_player function but with the room's map
    result = move_player(player, direction, game_map)

    # Check if player has encountered other players
    x, y = player["position"]
    player_encounters = []

    for pid, p in room["players"].items():
      if pid != player_id and p["position"] == (x, y):
        player_encounters.append(f"You encountered another player at {x}, {y}!")

    if player_encounters:
      result += "\n" + "\n".join(player_encounters)
    
    # Check if exit portal exists anywhere in the map
    has_portal = any(tile["type"] == "PORTAL" for row in game_map for tile in row)
    
    # If portal exists, count players at exit and show advancement status after every move
    if has_portal:
      # Find the portal position
      portal_pos = None
      for y_idx in range(len(game_map)):
        for x_idx in range(len(game_map[y_idx])):
          if game_map[y_idx][x_idx]["type"] == "PORTAL":
            portal_pos = (x_idx, y_idx)
            break
        if portal_pos:
          break
      
      if portal_pos:
        # Count players at the portal
        players_on_exit = 0
        total_players = len(room["players"])
        player_names_on_exit = []
        
        for pid, p in room["players"].items():
          if p["position"] == portal_pos:
            players_on_exit += 1
            player_names_on_exit.append(f"Player at {portal_pos}")
        
        # Always show portal status after each move when portal exists
        if players_on_exit == total_players:
          # All players are on the exit, advance to next dungeon
          for p in room["players"].values():
            enter_next_dungeon(p, game_map)

          # Generate new map for the next dungeon
          room["map"] = generate_map()
          room["dungeon_level"] += 1
          room["dungeon_completion"] = 0

          result += f"\nAll players have reached the exit portal! Advancing to dungeon level {room['dungeon_level']}."

          # Update everyone's map view
          map_view = visualize_multiplayer_map(room, player_id)
          result += f"\n\n{map_view}"
        else:
          # Show portal status info
          if players_on_exit > 0:
            players_at_exit_str = ", ".join(player_names_on_exit)
            result += f"\n🌀 Portal Status: {players_on_exit}/{total_players} players at the exit."
            result += f"\n   Players at exit: {players_at_exit_str}"
            result += f"\n   All players must reach the exit portal at ({portal_pos[0]}, {portal_pos[1]}) to advance!"
          else:
            result += f"\n🌀 Portal Status: Nobody has reached the exit portal yet."
            result += f"\n   All players must reach the exit portal at ({portal_pos[0]}, {portal_pos[1]}) to advance!"

    return result

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
        },
        "dungeon_level": 1,
        "dungeons_completed": 0
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

  def check_exploration_progress(game_map):
    """Calculates the percentage of the map that has been explored."""
    total_tiles = GRID_WIDTH * GRID_HEIGHT
    visible_tiles = sum(1 for row in game_map for tile in row if tile["visible"])
    return (visible_tiles / total_tiles) * 100

  def create_exit_portal(game_map):
    """Creates an exit portal at the furthest unexplored point from the start."""
    # Find the farthest point from the start (0,0)
    max_distance = 0
    portal_pos = (GRID_WIDTH-1, GRID_HEIGHT-1)  # Default to bottom-right

    for y in range(GRID_HEIGHT):
      for x in range(GRID_WIDTH):
        distance = ((x)**2 + (y)**2)**0.5
        if distance > max_distance and game_map[y][x]["type"] != "PORTAL":
          max_distance = distance
          portal_pos = (x, y)

    # Place the portal
    game_map[portal_pos[1]][portal_pos[0]] = {
      "type": "PORTAL",
      "visible": True,  # Make it immediately visible
      "monster_level": 0
    }

    return portal_pos

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
          elif tile_type == "PORTAL":
            map_view += "🌀 "  # Portal to next dungeon
          else:
            map_view += "⬜ "  # Empty
        else:
          map_view += "⬛ "  # Unexplored
      map_view += "\n"

    return map_view

  def enter_next_dungeon(player, game_map):
    """Advances the player to the next dungeon level."""
    # Save player progress
    old_dungeon_level = player["dungeon_level"]
    player["dungeon_level"] += 1
    player["dungeons_completed"] += 1

    # Reset player position
    player["position"] = (0, 0)

    # Retain a percentage of coins
    player["coins"] = int(player["coins"] * COIN_RETENTION)

    # Heal player to full
    player["health"] = player["max_health"]

    # Generate a new, more difficult map
    new_map = generate_map()

    # Scale monster difficulty based on dungeon level
    for y in range(GRID_HEIGHT):
      for x in range(GRID_WIDTH):
        if new_map[y][x]["type"] == "MONSTER":
          # Increase monster level based on dungeon level
          base_level = new_map[y][x]["monster_level"]
          level_bonus = max(0, player["dungeon_level"] - 1)
          new_map[y][x]["monster_level"] = base_level + level_bonus

    # Start point is always visible and safe
    new_map[0][0] = {"type": "EMPTY", "visible": True, "monster_level": 0}

    return new_map, f"You entered dungeon level {player['dungeon_level']}! Monsters will be stronger, but rewards will be greater."

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
      # Increase coin rewards based on dungeon level
      dungeon_bonus = (player["dungeon_level"] - 1) * 0.5  # 50% more coins per dungeon level
      base_coins = plugin.np.random.randint(1, 3 + player["level"] // 2)
      coins_found = int(base_coins * (1 + dungeon_bonus))
      player["coins"] += coins_found
      tile["type"] = "EMPTY"
      msg += f"You found {coins_found} coin(s)! "

    elif tile["type"] == "TRAP":
      # Check for dodge chance from equipment
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
          msg += "You nimbly avoided a trap! "
      else:
        # Traps get stronger in higher dungeons
        dungeon_factor = 1 + (player["dungeon_level"] - 1) * 0.3  # 30% stronger per dungeon
        base_damage = plugin.np.random.randint(1, 3)
        base_damage = int(base_damage * dungeon_factor)
        # Apply damage reduction from level and equipment
        damage = max(1, int(base_damage * (1 - player["damage_reduction"])))
        player["health"] -= damage
        msg += f"You triggered a trap! Health -{damage}. "

    elif tile["type"] == "MONSTER":
      monster_level = tile["monster_level"]

      # Calculate XP based on monster level and dungeon level
      base_xp = 5 + (monster_level * 2)
      dungeon_bonus = (player["dungeon_level"] - 1) * 0.2  # 20% more XP per dungeon level
      xp_gained = int(base_xp * (1 + dungeon_bonus))
      player["xp"] += xp_gained
      player["kills"] += 1

      # Calculate damage based on monster level, with damage reduction
      dungeon_factor = 1 + (player["dungeon_level"] - 1) * 0.3  # 30% stronger per dungeon
      base_damage = plugin.np.random.randint(1, 3) + monster_level
      base_damage = int(base_damage * dungeon_factor)
      
      # Player attack reduces monster damage
      damage_after_attack = max(1, base_damage - player["attack"])
      
      # Apply damage reduction from level and equipment
      final_damage = max(1, int(damage_after_attack * (1 - player["damage_reduction"])))
      
      # Check for dodge
      if player["dodge_chance"] > 0 and plugin.np.random.random() < player["dodge_chance"]:
        msg += f"You dodged the monster's attack! "
        final_damage = 0
        
      # Apply damage if not dodged
      if final_damage > 0:
        player["health"] -= final_damage
        msg += f"You took {final_damage} damage. "

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

    elif tile["type"] == "PORTAL":
      # Create a new dungeon level and move the player there
      new_map, dungeon_msg = enter_next_dungeon(player, game_map)
      plugin.obj_cache["shared_map"] = new_map
      map_view = visualize_map(player, new_map)
      return f"{dungeon_msg}\n\n{map_view}\n"

    is_dead, death_msg = check_health(player)
    if is_dead:
      return death_msg

    # Check exploration progress and portal status
    exploration = check_exploration_progress(game_map)
    
    # Check for existing portal
    has_portal = any(tile["type"] == "PORTAL" for row in game_map for tile in row)
    
    # If no portal yet but we've hit the threshold, create one
    if exploration >= EXPLORATION_THRESHOLD and not has_portal:
      portal_pos = create_exit_portal(game_map)
      msg += f"\n🌀 A portal to the next dungeon has appeared in the distance! Find it to advance to a more challenging area with better rewards."
      has_portal = True  # We just created a portal
    
    # If there's a portal, always show its status
    if has_portal:
      # Find the portal position
      portal_pos = None
      for y_idx in range(len(game_map)):
        for x_idx in range(len(game_map[y_idx])):
          if game_map[y_idx][x_idx]["type"] == "PORTAL":
            portal_pos = (x_idx, y_idx)
            break
        if portal_pos:
          break
      
      if portal_pos:
        # Check if the portal is visible to the player
        if game_map[portal_pos[1]][portal_pos[0]].get("visible", False):
          portal_status = f"\n🌀 Portal Status: Exit portal is located at ({portal_pos[0]}, {portal_pos[1]}). Reach it to advance to the next dungeon!"
        else:
          portal_status = f"\n🌀 Portal Status: A portal has appeared somewhere on the map. Keep exploring to find it!"
        
        # Add portal status to the message
        msg += portal_status

    map_view = visualize_map(player, game_map)
    stats = f"Health: {player['health']}/{player['max_health']}, Coins: {player['coins']}\n" \
           f"Level: {player['level']}, XP: {player['xp']}/{player['next_level_xp']}"
    # Add dungeon level info
    stats += f"\nDungeon Level: {player['dungeon_level']}, Exploration: {int(exploration)}%"
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
    help_text = ("Welcome to Shadowborn!\n"
                 "Instructions:\n"
                 "- Explore the dungeon using /move (or WSAD keys).\n"
                 "- Check your stats with /status to see health, coins, XP, level, attack, and equipment.\n"
                 "- Defeat monsters to earn XP and level up.\n"
                 "- Collect coins and visit the shop (/shop) to buy upgrades using /buy.\n"
                 "- Use consumable items from your inventory with /use.\n"
                 "- View the map with /map.\n"
                 "- Explore the map to find the portal (🌀) to the next dungeon level.\n"
                 "- Each new dungeon has tougher monsters but better rewards.\n"
                 "\nMultiplayer Mode:\n"
                 "- Create a new room with /create_room and share the code with friends.\n"
                 "- Join a friend's room with /join_room <code>.\n"
                 "- Chat with teammates using /room_chat <message>.\n"
                 "- See who's in your room with /room_status.\n"
                 "- Leave your current room with /leave_room.\n"
                 "- In multiplayer mode, all players in the room must reach the exit portal to advance to the next level!\n"
                 "- Players can see each other on the map if they're in visible areas (👤 symbol).\n"
                 "- Work together to explore faster and defeat challenging monsters!\n"
                 "\nAvailable Commands:\n"
                 "1. /start  - Restart the game and begin your epic adventure.\n"
                 "2. /move <up|down|left|right> - Move your character (WSAD keys supported).\n"
                 "3. /status - Display your current stats.\n"
                 "4. /map    - View your surroundings on the map.\n"
                 "5. /shop   - Browse the shop and buy upgrades/items.\n"
                 "6. /buy <item_name> - Purchase an item from the shop.\n"
                 "7. /use <item_name> - Use a consumable from your inventory.\n"
                 "8. /create_room - Create a new multiplayer room and get a room code.\n"
                 "9. /join_room <code> - Join an existing multiplayer room.\n"
                 "10. /leave_room - Leave your current multiplayer room.\n"
                 "11. /room_status - See who's in your current room.\n"
                 "12. /room_chat <message> - Send a message to all players in your room.\n"
                 "13. /help   - Display this help message.")
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
            "8. /create_room - Create a new multiplayer room.\n"
            "9. /join_room <code> - Join an existing multiplayer room.\n"
            "10. /leave_room - Leave your current room.\n"
            "11. /room_status - Check who's in your room.\n"
            "12. /room_chat <message> - Send a message to everyone in your room.\n"
            "13. /help   - Display help information.")

  command = parts[0]

  # ---------------------------
  # Get multiplayer room data if player is in a room
  # ---------------------------
  room, player = get_room_and_player_data(user_id)

  # ---------------------------
  # WASD Controls Processing
  # ---------------------------
  # Check if this is a single-letter WASD command
  if command in ["w", "a", "s", "d"]:
    # Map WASD to directions
    direction_map = {"w": "up", "a": "left", "s": "down", "d": "right"}
    direction = direction_map[command]

    # Use the multiplayer move function if in a room, otherwise use the regular move function
    if room and player:
      return multiplayer_move_player(room, user_id, direction)
    else:
      return move_player(plugin.obj_cache[user_id], direction, plugin.obj_cache["shared_map"])

  if command == "/start":
    # Generate new map for new game
    plugin.obj_cache["shared_map"] = generate_map()
    plugin.obj_cache[user_id] = create_new_player()
    map_view = visualize_map(plugin.obj_cache[user_id], plugin.obj_cache["shared_map"])
    return ("Welcome to Shadowborn!\n" 
            "This is an epic roguelike adventure where you explore a dangerous dungeon, defeat monsters, collect coins, earn XP, and purchase upgrades from the shop.\n" 
            "Your goal is to explore the dungeon, find the portal to the next level, and see how deep you can go!\n"
            "Use /move <up|down|left|right> to explore, /status to check your stats, and /shop to buy upgrades.\n\n"
            "MULTIPLAYER MODE:\n"
            "• Create a room with /create_room\n"
            "• Join a room with /join_room <code>\n"
            "• Chat with teammates using /room_chat <message>\n"
            "• All players must reach the exit portal to advance to the next level!\n\n"
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

    # If the player is in a multiplayer room, use the multiplayer move function
    if room and player:
      return multiplayer_move_player(room, user_id, direction)
    else:
      return move_player(plugin.obj_cache[user_id], direction, plugin.obj_cache["shared_map"])

  # ---------------------------
  # Multiplayer Room Commands
  # ---------------------------
  elif command == "/create_room":
    # Check if player is already in a room
    if get_player_room(user_id):
      return "You're already in a room. Use /leave_room first before creating a new room."

    # Create a new room with this player as creator
    room_id = create_room(user_id)

    # Return room info
    return (f"Created a new multiplayer room!\n"
            f"Your room code is: {room_id}\n"
            f"Share this code with friends so they can join using /join_room {room_id}\n"
            f"You are the only player in this room currently.\n"
            f"Use /room_status to see who joins.")

  elif command == "/join_room":
    if len(parts) < 2:
      return "Usage: /join_room <room_code>"

    # Check if player is already in a room
    if get_player_room(user_id):
      return "You're already in a room. Use /leave_room first before joining another room."

    room_code = parts[1].upper()
    success, message = join_room(user_id, room_code)

    if success:
      room, player = get_room_and_player_data(user_id)
      map_view = visualize_multiplayer_map(room, user_id)
      player_list = list_players_in_room(room)
      return f"{message}\n\n{player_list}\n\n{map_view}"
    else:
      return message

  elif command == "/leave_room":
    if not get_player_room(user_id):
      return "You're not in any room."

    result = leave_room(user_id)

    # Show the regular solo map after leaving
    map_view = visualize_map(plugin.obj_cache[user_id], plugin.obj_cache["shared_map"])
    return f"{result}\nYou are now playing solo.\n\n{map_view}"

  elif command == "/room_status":
    if not room:
      return "You're not in a multiplayer room. Use /create_room to create one or /join_room <code> to join one."

    player_list = list_players_in_room(room)
    messages = get_room_messages(room)

    return (f"Room Code: {get_player_room(user_id)}\n"
            f"Dungeon Level: {room['dungeon_level']}\n"
            f"{player_list}\n\n{messages}")

  elif command == "/room_chat":
    if not room:
      return "You're not in a multiplayer room. Use /create_room to create one or /join_room <code> to join one."

    if len(parts) < 2:
      return "Usage: /room_chat <your message>"

    chat_message = " "#.join(parts[1:])
    send_room_message(user_id, chat_message)

    return f"Message sent: {chat_message}\n\n{get_room_messages(room)}"

  elif command == "/status":
    # If in a multiplayer room, use the player data from the room
    if room and player:
      p = player
    else:
      p = plugin.obj_cache[user_id]

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

    # Get room info if in multiplayer
    room_info = ""
    if room:
      room_id = get_player_room(user_id)
      room_info = f"\n🏠 Room: {room_id} (Dungeon Level {room['dungeon_level']})"

    status_message = (f"📊 STATUS 📊\n"
                     f"🗺️ Position: ({x}, {y}){room_info}\n"
                     f"❤️ Health: {p['health']}/{total_max_health}\n"
                     f"💰 Coins: {p['coins']}\n"
                     f"⚔️ Attack: {total_attack}\n"
                     f"🛡️ Damage Reduction: {damage_reduction_percent}%\n"
                     f"👟 Dodge Chance: {dodge_percent}%\n"
                     f"📈 Level: {p['level']} (XP: {p['xp']}/{p['next_level_xp']})\n"
                     f"💀 Kills: {p['kills']}\n\n"
                     f"🎒 INVENTORY:\n{inventory_str}\n\n"
                     f"🧥 EQUIPMENT:\n{equipment_str}")

    return status_message

  elif command == "/map":
    # If in a multiplayer room, use the multiplayer map view
    if room and player:
      return visualize_multiplayer_map(room, user_id)
    else:
      return visualize_map(plugin.obj_cache[user_id], plugin.obj_cache["shared_map"])

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
            "\nMultiplayer Commands:\n"
            "/create_room - Create a new multiplayer room\n"
            "/join_room <code> - Join an existing multiplayer room\n"
            "/leave_room - Leave your current room\n"
            "/room_status - Check who's in your room\n"
            "/room_chat <message> - Send a message to everyone in your room\n"
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
    name="shadowborn_bot",
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

