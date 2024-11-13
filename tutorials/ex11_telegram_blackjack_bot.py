import os
import time

from naeural_client import Session, CustomPluginTemplate

def reply(plugin, message: str, user: str):
  # Define the deck of cards and their values
  cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10',
           'Jack', 'Queen', 'King', 'Ace']
  card_values = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, '10': 10,
    'Jack': 10, 'Queen': 10, 'King': 10,
    'Ace': 11  # Ace is treated as 11 initially; we'll adjust as needed
  }

  # Initialize user state if not already present
  if user not in plugin.obj_cache or plugin.obj_cache[user] is None:
    plugin.obj_cache[user] = {
      'state': 'NOT_STARTED',
      'wins': 0,
      'losses': 0
    }

  # Retrieve the user's game state
  user_cache = plugin.obj_cache[user]
  message = message.strip().lower()  # Normalize the input message

  if user_cache.get('state') == 'NOT_STARTED':
    if message == 'card' or message == 'start':
      # Start a new game
      user_cache['hand'] = []  # Initialize player's hand
      user_cache['state'] = 'PLAYING'

      # Deal the first card
      card = plugin.np.random.choice(cards)
      user_cache['hand'].append(card)

      # Calculate hand value
      total = 0
      aces = 0  # Count of aces in hand
      for c in user_cache['hand']:
        if c == 'Ace':
          aces += 1
        else:
          total += card_values[c]
      # Adjust for aces
      for _ in range(aces):
        if total + 11 <= 21:
          total += 11  # Count ace as 11 if it doesn't cause bust
        else:
          total += 1   # Otherwise, count ace as 1

      # Return the initial game message
      return (f"Welcome to a new game of Black Jack, you have a {card}. "
              f"Your total is {total}. Type 'card' to get another card, or 'stop' to hold.")
    else:
      # Prompt user to start a new game
      return "Welcome to Black Jack. Type 'card' to start a new game."

  elif user_cache.get('state') == 'PLAYING':
    if message == 'card':
      # Player chooses to draw another card
      card = plugin.np.random.choice(cards)
      user_cache['hand'].append(card)

      # Recalculate hand value
      total = 0
      aces = 0
      for c in user_cache['hand']:
        if c == 'Ace':
          aces += 1
        else:
          total += card_values[c]
      for _ in range(aces):
        if total + 11 <= 21:
          total += 11
        else:
          total += 1

      hand_str = ', '.join(user_cache['hand'])  # Format hand as a string

      if total > 21:
        # Player busts
        user_cache['state'] = 'BUST'
        user_cache['losses'] += 1  # Increment losses
        return (f"You are given a {card}. Your hand: {hand_str}. "
                f"Your total is {total}. Bust! You lose.\n"
                f"Total Wins: {user_cache['wins']}, Total Losses: {user_cache['losses']}")
      elif total == 21:
        # Player hits Black Jack
        user_cache['state'] = 'BLACKJACK'
        user_cache['wins'] += 1  # Increment wins
        return (f"You are given a {card}. Black Jack! Congratulations, you win! "
                f"Your hand: {hand_str}.\n"
                f"Total Wins: {user_cache['wins']}, Total Losses: {user_cache['losses']}")
      else:
        # Continue playing
        return (f"You are given a {card}. Your hand: {hand_str}. "
                f"Your total is {total}. Type 'card' to get another card, or 'stop' to hold.")
    elif message == 'stop':
      # Player chooses to hold; dealer's turn
      dealer_hand = []
      dealer_total = 0
      dealer_aces = 0

      # Dealer draws cards until total >= 17
      while True:
        dealer_card = plugin.np.random.choice(cards)
        dealer_hand.append(dealer_card)

        # Update dealer's total
        if dealer_card == 'Ace':
          dealer_aces += 1
        else:
          dealer_total += card_values[dealer_card]

        # Calculate dealer's total considering aces
        temp_total = dealer_total
        aces = dealer_aces
        for _ in range(aces):
          if temp_total + 11 <= 21:
            temp_total += 11
          else:
            temp_total += 1

        dealer_total_with_aces = temp_total

        # Dealer stops hitting when total >= 17
        if dealer_total_with_aces >= 17:
          dealer_total = dealer_total_with_aces
          break
        else:
          dealer_total = dealer_total_with_aces

      # Calculate player's total
      player_total = 0
      player_aces = 0
      for c in user_cache['hand']:
        if c == 'Ace':
          player_aces += 1
        else:
          player_total += card_values[c]
      for _ in range(player_aces):
        if player_total + 11 <= 21:
          player_total += 11
        else:
          player_total += 1

      user_cache['state'] = 'GAME_OVER'  # Update game state

      # Determine the outcome
      if dealer_total > 21:
        result = "Dealer busts! You win!"
        user_cache['wins'] += 1
      elif player_total > dealer_total:
        result = "You win!"
        user_cache['wins'] += 1
      elif player_total == dealer_total:
        result = "It's a tie!"
        # Ties are not counted as wins or losses
      else:
        result = "You lose!"
        user_cache['losses'] += 1

      player_hand_str = ', '.join(user_cache['hand'])
      dealer_hand_str = ', '.join(dealer_hand)

      # Return the game result with total wins and losses
      return (f"You stopped with {player_total}. Your hand: {player_hand_str}.\n"
              f"Dealer's hand: {dealer_hand_str} (Total: {dealer_total}).\n"
              f"{result}\nTotal Wins: {user_cache['wins']}, Total Losses: {user_cache['losses']}")
    else:
      # Invalid input during playing
      return "Invalid input. Please type 'card' to get another card, or 'stop' to hold."

  elif user_cache.get('state') in ['BUST', 'BLACKJACK', 'GAME_OVER']:
    # Game is over; reset state for a new game
    user_cache['state'] = 'NOT_STARTED'
    return "Game over. Type 'card' to start a new game."

  else:
    # Catch-all for unexpected state
    return "An error occurred. Please start a new game."



if __name__ == "__main__":
  my_node = os.getenv("TARGET_NODE") # we can specify a node here, if we want to connect to a specific
    
  session = Session() # assume .env is available and will be used for the connection and tokens
  session.wait_for_node(my_node) # wait for the node to be active
    
      
  pipeline, _ = session.create_telegram_simple_bot(
    node=my_node,
    name="telegram_bot_blackjack",
    message_handler=reply,
  )
  
  pipeline.deploy() # we deploy the pipeline

 
