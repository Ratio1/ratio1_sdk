import json
import os
from pathlib import Path
import shutil

from ratio1.const.base import BCct, dAuth, EE_SDK_ALIAS_DEFAULT, EE_SDK_ALIAS_ENV_KEY 
from ratio1._ver import __VER__ as version

from ratio1.logging.base_logger import SDK_HOME, BaseLogger


CONFIG_FILE = "config"

LOCAL_PEM_PATH = "./_local_cache/_data/" + BCct.DEFAULT_PEM_FILE

ENV_TEMPLATE = """
# Configuration file for the Ratio1 SDK

EE_EVM_NET=testnet
EE_TARGET_NODE=

"""

def _create_bc_engine():
  from ratio1.bc import DefaultBlockEngine
  from ratio1 import Logger
  return DefaultBlockEngine(
    name="default", 
    log=Logger("CLI", silent=True),
    user_config=True, # this is must to use the user config
  )
  

def seconds_to_short_format(seconds):
  """
  Converts a duration in seconds into a short human-readable format: "Xd HH:MM:SS".

  Parameters
  ----------
  seconds : int
      The total duration in seconds.

  Returns
  -------
  str
      Short human-readable duration in "Xd HH:MM:SS" format.
  """
  days = int(seconds / (24 * 3600))
  seconds %= (24 * 3600)
  hours = int(seconds / 3600)
  seconds %= 3600
  minutes = int(seconds / 60)
  seconds %= 60
  seconds = int(seconds)

  # Format the result
  if days > 0:
    return f"{days}d {hours:02}:{minutes:02}:{seconds:02}"
  else:
    return f"{hours:02}:{minutes:02}:{seconds:02}"

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
      # 'b': "\x1b[1;34m",  # bright blue
      'b': "\033[36m",  # bright cyan
      'w': '\033[97m',  # Light white
      'c': "\033[36m",  # bright cyan
      'n': '\033[37m',  # white (default)
      'd': "\033[90m",  # dark gray
      
  }

  reset_code = '\033[0m'  # Reset color
  color_code = color_codes.get(color, color_codes['n'])
  print(f"{color_code}{s}{reset_code}", flush=True)


def get_user_folder():
  """
  Returns the user folder.
  """
  return BaseLogger.get_user_folder(as_str=False, include_sdk_home=True)


def get_user_config_file():
  """
  Returns the user configuration file.
  """
  return get_user_folder() / CONFIG_FILE


def get_network():
  return os.environ.get(dAuth.DAUTH_NET_ENV_KEY, dAuth.DAUTH_SDK_NET_DEFAULT)

def get_alias():
  return os.environ.get(EE_SDK_ALIAS_ENV_KEY, EE_SDK_ALIAS_DEFAULT)

def set_client_alias(alias : str):
  config_file = get_user_config_file()
  # open config_file and update EE_SDK_ALIAS
  with config_file.open("r") as file:
    lines = file.readlines()
  with config_file.open("w") as file:
    found = False
    for line in lines:
      if line.startswith(EE_SDK_ALIAS_ENV_KEY):
        line = f"{EE_SDK_ALIAS_ENV_KEY}={alias}\n"
        found = True
      file.write(line)
    if not found:
      file.write(f"{EE_SDK_ALIAS_ENV_KEY}={alias}\n")
  log_with_color(f"Alias set to {alias}", color='b')
  return 

def get_networks(args):
  """
  Shows the network configuration.
  """
  log_with_color(f"Client v{version} on network: {get_network()}", color='b')
  from ratio1.const.evm_net import EVM_NET_DATA
  log_with_color(f"Available networks:\n{json.dumps(EVM_NET_DATA, indent=2)}", color='w')  
  return


def get_set_network(args):
  net = args.new or args.set
  env_network = get_network()
  if net is None:
    log_with_color(f"Client v{version} on network: {env_network}", color='b')
  else:
    config_file = get_user_config_file()
    # open config_file and update EE_EVM_NET
    with config_file.open("r") as file:
      lines = file.readlines()
    with config_file.open("w") as file:
      found = False
      for line in lines:
        if line.startswith("EE_EVM_NET"):
          line = f"EE_EVM_NET={net}\n"
          found = True
        file.write(line)
      if not found:
        file.write(f"EE_EVM_NET={net}\n")
    log_with_color(f"Network set to {net}", color='b')
  return

def get_set_alias(args):
  alias = args.set
  if alias is None:
    log_with_color(f"Client v{version} alias: {get_alias()}", color='b')
  else:
    set_client_alias(alias)
  return
    
  

def reset_config(*larg, keep_existing=False, **kwargs):
  """
  Resets the configuration by creating a ~/.ratio1 folder and populating
  ~/.ratio1/config with values from a local .env file, if it exists.
  """
  log_with_color(f"Client v{version} resetting the configuration...", color='y')
  # Define the target config folder and file
  config_dir = get_user_folder()
  config_file = get_user_config_file()
  
  local_pem = Path(LOCAL_PEM_PATH)
  target_pem = config_dir / BCct.USER_PEM_FILE
  
  # Create the ~/.ratio1 folder if it doesn't exist
  config_dir.mkdir(parents=True, exist_ok=True)

  # Check if the current folder has a .env file
  current_env_file = Path(".env")
  if current_env_file.exists():
    # Copy .env content to ~/.ratio1/config
    shutil.copy(current_env_file, config_file)
    log_with_color(
      f"Configuration has been reset using {current_env_file} into {config_file}", 
      color='y'
    )
    log_with_color(f"Please REVIEW the configuration in the file {config_file}", color='b')
  else:
    # Create an empty config file
    with config_file.open("wt") as file:
      file.write(ENV_TEMPLATE)
    log_with_color(
      f"Configuration has been reset to default in {config_file}:\n{ENV_TEMPLATE}", 
      color='y'
    )
    log_with_color(f"Please UPDATE the configuration in the file {config_file}", color='b')
  
  if local_pem.exists():
    log_with_color(f"Copying local PEM file {local_pem} to {target_pem}", color='y')
    shutil.copy(local_pem, target_pem)
  else:
    log_with_color(f"No local PEM file found locally {local_pem}.", color='r')
    if target_pem.exists():
      log_with_color(f"Found already existing {target_pem}.", color='y')
      if not keep_existing:
        target_pem.unlink()        
        log_with_color(f"Deleted {target_pem}. A default key will be generated.", color='b')
      #end if
    #endif pem exists
  #end if local pem exists
  show_version()
  return


def show_address(args):
  """
  Displays the current client address.
  """
  from ratio1 import Session
  sess = Session(
    silent=True
  )
  log_with_color(f"{sess.get_client_address()}", color='b')
  return


def show_version(silent=True):
  from ratio1 import Session
  sess = Session(
    silent=silent
  )  
  
  nodes = sess.get_active_nodes()
  oracles = sess.get_active_supervisors()
  
  user_folder = get_user_folder()  
  
  # TODO: get the epoch from the SDK  - AFTER moving get_epoch_id from core
  
  log_with_color(f"Ratio1 client v{version}:\n", color='b')
  log_with_color(f"SDK folder:     {user_folder}", color='b')
  log_with_color(f"Ratio1 network: {get_network()}", color='b')
  log_with_color(f"Network Epoch:  {sess.bc_engine.get_current_epoch()}", color='b')
  log_with_color(f"SDK addr:       {sess.get_client_address()}", color='b')
  log_with_color(f"SDK ETH addr:   {sess.bc_engine.eth_address}", color='b')
  log_with_color(f"SDK alias:      {sess.name}", color='b')
  log_with_color(f"Active oracles: {len(oracles)}", color='b')
  log_with_color(f"Active nodes:   {len(nodes)}", color='b')
  return


  

def show_config(args):
  """
  Displays the current configuration from ~/.ratio1/config.
  """
  show_version(silent=not args.verbose)
  config_file = get_user_config_file()
  if config_file.exists():
    keys = []
    with config_file.open("r") as file:
      lines = file.readlines()
      keys = [line.strip().split("=")[0] for line in lines if "=" in line and not line.strip().startswith("#")]
      commments = [line.strip() for line in lines if line.strip().startswith("#")]
    log_with_color(f"Current config {config_file} has {len(keys)} keys and {len(commments)} comments\n", color='d')
  else:
    log_with_color(f"No configuration found at {config_file}. Please run `reset_config` first.", color="r")
  return



def load_user_defined_config(verbose=False):
  """
  Loads the ~/.ratio1/config file into the current environment.
  """
  config_file = get_user_config_file()
  result = False
  loaded_keys = []
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
          loaded_keys.append(key.strip())
    if verbose:
      log_with_color(f"{config_file} loaded into the env: {loaded_keys}", color='b')
  else:
    if verbose:
      log_with_color(f"No configuration file found at {config_file}. Please run `reset_config` first.", color="r")
  return result
  

def maybe_init_config():
  """
  Initializes the configuration if it doesn't exist yet.
  
  TODO: in v3+ this will be migrated to a online authentication process.
  """
  config_file = get_user_config_file()
  if not config_file.exists():
    BaseLogger.maybe_migrate_user_folder()
    if not config_file.exists():
      log_with_color(f"No configuration file found at {config_file}. Initializing configuration...", color="y")
      reset_config(keep_existing=True)
      return False
    # config_file still does not exist even after attempting the migration.
  return load_user_defined_config()



def get_eth_addr(args):
  """
  Gets the ETH address given a node address.
  """
  node = args.node
  eng = _create_bc_engine()
  eth_addr = eng.get_eth_address(node)
  log_with_color(f"ETH address for node {node}: {eth_addr}", color='b')
  return