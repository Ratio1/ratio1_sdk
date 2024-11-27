import os
from pathlib import Path
import shutil

ENV_TEMPLATE = """

EE_MQTT_HOST=r9092118.ala.eu-central-1.emqxsl.com
EE_MQTT_PORT=8883
EE_MQTT_USER=
EE_MQTT=

EE_SECURED=true

TARGET_NODE=
"""

def log_with_color(s, color='n'):
  """
  Prints the string `s` to the console in the specified color.

  Parameters
  ----------
  s : str
      The string to be logged.
  color : str, optional
      The color code: 
      'r' for red, 'g' for green, 'y' for yellow, 
      'b' for blue, 'w' for light white, 'n' for dark white (default).
  """
  color_codes = {
      'r': '\033[31m',  # Red
      'g': '\033[32m',  # Green
      'y': '\033[33m',  # Yellow
      'b': "\x1b[1;34m",  # bright blue
      'w': '\033[97m',  # Light white
      'c': "\x1b[1;36m",  # bright cyan
      'n': '\033[37m',  # Dark white (default)
  }

  reset_code = '\033[0m'  # Reset color
  color_code = color_codes.get(color, color_codes['n'])
  print(f"{color_code}{s}{reset_code}", flush=True)


def get_user_folder():
  """
  Returns the user folder.
  """
  return Path.home() / ".naeural"

def get_user_config_file():
  """
  Returns the user configuration file.
  """
  return get_user_folder() / "config"

def reset_config(args):
  """
  Resets the configuration by creating a ~/.naeural folder and populating
  ~/.naeural/config with values from a local .env file, if it exists.
  """
  # Define the target config folder and file
  config_dir = get_user_folder()
  config_file = get_user_config_file()
  
  # Create the ~/.naeural folder if it doesn't exist
  config_dir.mkdir(parents=True, exist_ok=True)

  # Check if the current folder has a .env file
  current_env_file = Path(".env")
  if current_env_file.exists():
    # Copy .env content to ~/.naeural/config
    shutil.copy(current_env_file, config_file)
    log_with_color(f"Configuration has been reset using {current_env_file} into {config_file}", color='y')
  else:
    # Create an empty config file
    with config_file.open("wt") as file:
      file.write(ENV_TEMPLATE)
    log_with_color(f"Configuration has been reset to default in {config_file}:\n{ENV_TEMPLATE}", color='y')


def show_config(args):
  """
  Displays the current configuration from ~/.naeural/config.
  """
  config_file = get_user_config_file()

  if config_file.exists():
    log_with_color(f"Current configuration ({config_file}):")
    with config_file.open("r") as file:
      log_with_color(file.read())
  else:
    log_with_color(f"No configuration found at {config_file}. Please run `reset_config` first.", color="r")
  return
    

def load_user_defined_config(verbose=False):
  """
  Loads the ~/.naeural/config file into the current environment.
  """
  config_file = get_user_config_file()
  result = False

  if config_file.exists():
    with config_file.open("r") as file:
      for line in file:
        # Ignore comments and empty lines
        if line.strip() and not line.strip().startswith("#"):
          key, value = line.strip().split("=", 1)
          value = value.strip()
          # if at least one key-value pair is found, set the result to True
          if value != "":
            result = True
          os.environ[key.strip()] = value
    if verbose:
      log_with_color(f"Configuration from {config_file} has been loaded into the environment.", color='b')
  else:
    if verbose:
      log_with_color(f"No configuration file found at {config_file}. Please run `reset_config` first.", color="r")
  return result
  

def maybe_init_config():
  """
  Initializes the configuration if it doesn't exist yet.
  """
  config_file = get_user_config_file()

  if not config_file.exists():
    reset_config()
  load_user_defined_config()
