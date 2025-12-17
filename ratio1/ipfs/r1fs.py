"""
R1FS - Ratio1 base IPFS utility functions.


NOTE: 
  - Following the bootstrapping of this module, it takes a few minutes for the relay
    to be connected and the IPFS daemon to be fully operational so sometimes, after
    the start of the engine, the first few `get` operations may fail.


Installation:

1. On the dev node or seed node run ifps_keygen and generate `swarm_key_base64.txt` then
   save this key to the environment variable `EE_SWARM_KEY_CONTENT_BASE64` on the seed 
   oracles as well as in a file.
     
2. On seed node create `ipfs_setup`, copy the files from the `ipfs_setup` including the
  key file.
  
3. Run `setup.sh` on the seed node or:

    ```bash
    #!/bin/bash
    wget https://dist.ipfs.tech/kubo/v0.32.1/kubo_v0.32.1_linux-amd64.tar.gz && \
      tar -xvzf kubo_v0.32.1_linux-amd64.tar.gz && \
      cd kubo && \
      bash install.sh
    ipfs init
    ipfs config --json Swarm.EnableRelayHop true

    ./write_key.sh
    ```
  The `write_key.sh` script should contain the following:
  
    ```bash 
    cat swarm_key_base64.txt | base64 -d > /root/.ipfs/swarm.key
    cat /root/.ipfs/swarm.key
    ```
  
4. Continue on the seed node and run either manually (NOT recommended) or via a systemd
   the ifps daemon using `./launch_service.sh` that basically does:
   
    ```bash
    cp ipfs.service /etc/systemd/system/ipfs.service
    sudo systemctl daemon-reload
    sudo systemctl enable ipfs
    sudo systemctl start ipfs
    ./show.sh
    ```
    
Documentation url: https://docs.ipfs.tech/reference/kubo/cli/#ipfs

"""
import subprocess
import json
from datetime import datetime
import base64
import time
import os
import tempfile
import uuid
import requests
import hashlib
import shutil
import gzip
from io import BytesIO
import ssl
from requests.auth import HTTPBasicAuth
import tempfile
import random

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_SECRET = "ratio1"
DEFAULT_FILENAME_JSON = "data.json"

from threading import Lock

__VER__ = "0.2.2"

# empirically determined minimum connection age for IPFS relay
DEFAULT_MIN_CONNECTION_AGE = 0 # seconds


class IPFSCt:
  EE_IPFS_RELAY_ENV_KEY = "EE_IPFS_RELAY"
  EE_SWARM_KEY_CONTENT_BASE64_ENV_KEY = "EE_SWARM_KEY_CONTENT_BASE64"
  EE_IPFS_RELAY_API_KEY = "EE_IPFS_RELAY_API"
  EE_IPFS_API_KEY_BASE64_KEY = "EE_IPFS_API_KEY_BASE64"
  EE_IPFS_CERTIFICATE_BASE64_KEY = "EE_IPFS_CERTIFICATE_BASE64"
  R1FS_DOWNLOADS = "ipfs_downloads"
  R1FS_UPLOADS = "ipfs_uploads"
  CACHE_ROOT = "_local_cache"
  TEMP_DOWNLOAD = os.path.join(f"./{CACHE_ROOT}/_output", R1FS_DOWNLOADS)
  TEMP_UPLOAD = os.path.join(f"./{CACHE_ROOT}/_output", R1FS_UPLOADS)
  
  TIMEOUT = 90 # seconds
  REPROVIDER = "1m"


ERROR_TAG = "Unknown"

COLOR_CODES = {
  "g": "\033[92m",
  "r": "\033[91m",
  "b": "\033[94m",
  "y": "\033[93m",
  "m": "\033[95m",
  'd': "\033[90m", # dark gray
  "reset": "\033[0m"
}

def log_info(msg: str, color="reset", **kwargs):
  timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  color_code = COLOR_CODES.get(color, COLOR_CODES["reset"])
  reset_code = COLOR_CODES["reset"]
  print(f"{color_code}[{timestamp}] {msg}{reset_code}", flush=True)
  return

class SimpleLogger:
  def P(self, *args, **kwargs):
    log_info(*args, **kwargs)
    return
  
def require_ipfs_started(method):
  """
  decorator to ensure the IPFS is started before executing the method.
  
  parameters
  ----------
  method : callable
      the method to be decorated.
  
  returns
  -------
  callable
      the wrapped method that checks the 'started' attribute.
  
  raises
  ------
  RuntimeError
      if the instance's 'started' attribute is False.
  """
  def wrapper(self, *args, **kwargs):
    if not self.ipfs_started:
      msg = f"R1FS ERROR: {method.__name__} FAILED. R1FS.ipfs_started=={self.ipfs_started}"
      raise RuntimeError(msg)
    return method(self, *args, **kwargs)
  return wrapper  



class R1FSEngine:
  
  _lock: Lock = Lock()
  __instances = {}

  def __new__(
    cls, 
    name: str = "default", 
    logger: any = None, 
    downloads_dir: str = None,
    uploads_dir: str = None,
    base64_swarm_key: str = None,
    ipfs_relay_api: str = None,
    ipfs_api_key_username: str = None,
    ipfs_api_key_password: str = None,
    ipfs_certificate_path: str = None,
    ipfs_relay: str = None,   
    debug=False,     
    min_connection_age: int = DEFAULT_MIN_CONNECTION_AGE,
  ):
    with cls._lock:
      if name not in cls.__instances:
        instance = super(R1FSEngine, cls).__new__(cls)
        instance._build(
          name=name, logger=logger,
          downloads_dir=downloads_dir,
          uploads_dir=uploads_dir,
          base64_swarm_key=base64_swarm_key,
          ipfs_relay=ipfs_relay,
          ipfs_relay_api=ipfs_relay_api,
          ipfs_api_key_username=ipfs_api_key_username,
          ipfs_api_key_password=ipfs_api_key_password,
          ipfs_certificate_path=ipfs_certificate_path,
          debug=debug,
          min_connection_age=min_connection_age,
        )
        cls.__instances[name] = instance
      else:
        instance = cls.__instances[name]
    return instance
  
  
  # base
  if True:
      
    def _build(
      self, 
      name: str = "default",
      logger: any = None, 
      downloads_dir: str = None,
      uploads_dir: str = None,
      base64_swarm_key: str = None, 
      ipfs_relay: str = None,
      ipfs_relay_api: str = None,
      ipfs_api_key_username: str = None,
      ipfs_api_key_password: str = None,
      ipfs_certificate_path: str = None,
      min_connection_age: int = DEFAULT_MIN_CONNECTION_AGE,
      debug=False,     
    ):
      """
      Initialize the IPFS wrapper with a given logger function.
      By default, it uses the built-in print function for logging.
      
      
      """
      self.__DEFAULT_SECRET = DEFAULT_SECRET
      self.__name = name
      if logger is None:
        logger = SimpleLogger()

      self.logger = logger

      self.__ipfs_started = False
      self.__ipfs_address = None
      self.__ipfs_id = None
      self.__ipfs_id_result = None
      self.__min_connection_age = min_connection_age
      self.__connected_at = None
      self.__ipfs_agent = None
      self.__uploaded_files = {}
      self.__downloaded_files = {}
      self.__base64_swarm_key = base64_swarm_key
      self.__ipfs_relay = ipfs_relay
      self.__ipfs_relay_api = ipfs_relay_api
      self.__ipfs_api_key_username = ipfs_api_key_username
      self.__ipfs_api_key_password = ipfs_api_key_password
      self.__ipfs_certificate_path = ipfs_certificate_path
      self.__ipfs_home = None
      self.__downloads_dir = downloads_dir
      self.__uploads_dir = uploads_dir    
      self.__debug = debug
      self.__relay_check_cnt = 0
      
      self.startup()
      return
    
    def startup(self):
      
      if self.__downloads_dir is None:
        if hasattr(self.logger, "get_output_folder"):
          output_folder = self.logger.get_output_folder()
          self.Pd("Using output folder as base: {}".format(output_folder))
          self.__downloads_dir = os.path.join(
            output_folder,
            IPFSCt.R1FS_DOWNLOADS
          )
        else:
          self.__downloads_dir = IPFSCt.TEMP_DOWNLOAD
      #end if downloads_dir    
      os.makedirs(self.__downloads_dir, exist_ok=True)    
      
      if self.__uploads_dir is None:
        if hasattr(self.logger, "get_output_folder"):
          self.__uploads_dir = os.path.join(
            self.logger.get_output_folder(),
            IPFSCt.R1FS_UPLOADS
          )
        else:
          self.__uploads_dir = IPFSCt.TEMP_UPLOAD
      os.makedirs(self.__uploads_dir, exist_ok=True)    

      self.maybe_reset_ipfs()

      self.maybe_start_ipfs(
        base64_swarm_key=self.__base64_swarm_key,
        ipfs_relay=self.__ipfs_relay,
        ipfs_relay_api=self.__ipfs_relay_api,
        ipfs_api_key_username=self.__ipfs_api_key_username,
        ipfs_api_key_password=self.__ipfs_api_key_password,
        ipfs_certificate_path=self.__ipfs_certificate_path
      )
      return
      
      
    def P(self, s, *args, **kwargs):
      s = "[R1FS] " + s
      color = kwargs.pop("color", "d")
      kwargs["color"] = color
      self.logger.P(s, *args, **kwargs)
      return
    
    def Pd(self, s, *args, **kwargs):
      if self.__debug:
        s = "[R1FS][DEBUG] " + s
        color = kwargs.pop("color", "d")
        color = "d" if color != 'r' else "r"
        kwargs["color"] = color
        self.logger.P(s, *args, **kwargs)
      return

    def _hash_secret(self, secret: str) -> bytes:
      secret = str(secret) # to be sure that the passed secret is of string type.
      # Convert text to bytes, then hash with SHA-256 => 32-byte key
      return hashlib.sha256(secret.encode("utf-8")).digest()

  # Private, yet visible (public) helpers.
  if True:
    def _set_debug(self):
      """
      Force debug mode on.
      """
      self.__debug = True
      return

    def _set_min_connection_age(self, min_connection_age: int):
      """
      @Deprecated: Don't use this method anymore, Warm up is not used anymore.
      Set the minimum connection age for IPFS to be considered warmed up.
      """
      return

  # Public properties
  if True:
    @property
    def ipfs_id(self):
      return self.__ipfs_id
    
    @property
    def ipfs_address(self):
      return self.__ipfs_address
    
    @property
    def ipfs_relay(self):
      return self.__ipfs_relay
    
    @property
    def ipfs_agent(self):
      return self.__ipfs_agent
    
    @property
    def ipfs_started(self):
      return self.__ipfs_started

    @property
    def ipfs_connected(self):
      return self.ipfs_started and self.__connected_at is not None

    @property
    def download_folder(self):
      return self.__downloads_dir
    
    
    @property
    def peers(self):
      return self.__peers
    
    @property
    def swarm_peers(self):
      return self.peers
    
    @property
    def uploaded_files(self):
      return self.__uploaded_files
    
    @property
    def downloaded_files(self):
      return self.__downloaded_files
        
    @property
    def connected_at(self):
      return self.__connected_at
    
    @property
    def ipfs_home(self):
      """ return the IPFS home directory from the environment variable IPFS_PATH """
      return os.environ.get("IPFS_PATH")
  
  # boilerplate methods
  if True:
    def _get_unique_name(self, prefix="r1fs", suffix=""):
      str_id = str(uuid.uuid4()).replace("-", "")[:8]
      return f"{prefix}_{str_id}{suffix}"
    
    def _get_unique_upload_name(self, prefix="r1fs", suffix=""):
      return os.path.join(self.__uploads_dir, self._get_unique_name(prefix, suffix))
    
    def _get_unique_or_complete_upload_name(self, fn=None, prefix="r1fs", suffix=""):
      if fn is not None and os.path.dirname(fn) == "":
        # Don't add suffix if filename already ends with it
        if suffix and fn.endswith(suffix):
          return os.path.join(self.__uploads_dir, fn)
        return os.path.join(self.__uploads_dir, f"{fn}{suffix}")
      return self._get_unique_upload_name(prefix, suffix=suffix)
    

    def _get_swarm_peers(self):
      peer_lines = []
      try:
        out = subprocess.run(
          ["ipfs", "swarm", "peers"],
          capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
          peer_lines = out.stdout.strip().split("\n")
          peer_lines = [line.strip() for line in peer_lines if line.strip()]
          self.Pd(f"Swarm peers: {peer_lines}")
          self.__peers = peer_lines
        else:
          self.__peers = []
        # found = len(self.__peers) > 0
      except Exception as e:
        self.P(f"Error getting swarm peers: {e}", color='r')
      return peer_lines


    def _check_and_record_relay_connection(
      self, 
      max_check_age : int = 3600, 
      debug=False
    ) -> bool:
      """
      Checks if we're connected to the relay_peer_id by parsing 'ipfs swarm peers'.
      If connected and we haven't recorded connected_at yet, we set it.
      """
      log_func = self.P if debug else self.Pd
      relay_found = False
      try:
        if self.connected_at is not None:
          # Already connected, lets see if last check was recent enough:
          elapsed_time = time.time() - self.connected_at
          if elapsed_time < max_check_age:
            relay_found = True
            log_func(f"Relay check #{self.__relay_check_cnt}: Already connected to relay peer for {elapsed_time:.1f}s, skipping check.")
            # If we are connected and the last check was recent enough, return True:
          else:
            log_func(f"Relay check #{self.__relay_check_cnt}: Last connection check was {elapsed_time:.1f}s ago, checking again...")
            # If we are connected but the last check was too long ago, check again:
          #end if needs recheck or not
        #end if connected_at is not None
        if not relay_found:         
          self.__relay_check_cnt += 1
          log_func(f"Relay check #{self.__relay_check_cnt}: Checking IPFS relay connection and swarm peers...")
          peer_lines = self._get_swarm_peers()
          if len(peer_lines) > 0:
            log_func(f"Relay check  #{self.__relay_check_cnt}: {len(peer_lines)} swarm peers.")
            self.__peers = peer_lines
            for line in peer_lines:
              # If the line contains the relay peer ID, we consider ourselves connected:
              if self.__ipfs_relay in line:
                # Record the time if not already set
                relay_found = True
                log_func(f"Relay check #{self.__relay_check_cnt}: Relay ok: {line.strip()}")
                break
              #end if
            #end for
            # now reset the connected_at time if we found the relay peer
            if relay_found:
              # TODO: maybe add first & last connected time
              if self.__connected_at is None:
                # If we found the relay peer and connected_at was not set, set it now:
                self.__connected_at = time.time()
              str_connected = self.logger.time_to_str(self.connected_at)
              self.P(f"Relay check #{self.__relay_check_cnt}: Connected to relay peer recorded at {str_connected}.")
            else:              
              # TODO: maybe add first & last connected time
              # self.__connected_at = None # this is already None or the first connection
              log_func("Relay check #{}: FAIL: relay {} not found in swarm peers:\n{}".format(
                self.__relay_check_cnt, self.__ipfs_relay.split('/')[2],
                json.dumps(peer_lines, indent=2)
                ), color='r'\
              )
            #end if relay_found or not
          #end if len(peer_lines) > 0
      except subprocess.TimeoutExpired:
        self.P(f"Relay check #{self.__relay_check_cnt}: Timeout checking swarm peers.", color='r')
        relay_found = False
      except Exception as e:
        self.P(f"Relay check #{self.__relay_check_cnt}: Error checking swarm peers: {e}", color='r')
        relay_found = False
      #end try
      return relay_found


    def __set_reprovider_interval(self):
      # Command to set the Reprovider.Interval to 1 minute
      cmd = ["ipfs", "config", "--json", "Reprovider.Interval", f'"{IPFSCt.REPROVIDER}"']
      result = self.__run_command(cmd)
      return result


    # TODO: Create a function for setting variables below.
    def __disable_auto_tls(self):
      result = self.__run_command(
        ["ipfs", "config", "--json", "AutoTLS.Enabled", "false"]
      )
      return result

    def __set_routing_type_dht(self):
      result = self.__run_command(
        ["ipfs", "config", "--json", "Routing.Type", '"dht"']
      )
      return result

    def __disable_ws_transport(self):
      result = self.__run_command(
        ["ipfs", "config", "--json", "Swarm.Transports.Network.Websocket", "false"]
      )
      return result

    def __bootstrap_add(self, ipfs_relay):
      result = self.__run_command(
        ["ipfs", "bootstrap", "add", ipfs_relay]
      )
      return result

    # PUBLIC COMMAND
    def get_ipfs_id_data(self) -> dict:
      """
      Get the IPFS peer ID via 'ipfs id' (JSON output).
      Returns the ipfs ID object.
      """
      data = {}
      output = self.__run_command(["ipfs", "id"])  # this will raise an exception if the command fails
      try:
        data = json.loads(output)
      except json.JSONDecodeError:
        raise Exception("Failed to parse JSON from 'ipfs id' output.")
      except Exception as e:
        msg = f"Error getting IPFS ID: {e}. `ipfs id`:\n{data}"
        self.P(msg, color='r')
        raise Exception(f"Error getting IPFS ID: {e}") from e
      return data

    # END PUBLIC COMMANS

    def __run_command(
      self, 
      cmd_list: list, 
      raise_on_error=True,
      timeout=IPFSCt.TIMEOUT,
      verbose=False,
      return_errors=False,
      show_logs=True,
    ):
      """
      Run a shell command using subprocess.run with a timeout.
      Logs the command and its result. If verbose is enabled,
      prints command details. Raises an exception on error if raise_on_error is True.
      """
      failed = False
      output = ""
      errors = ""
      cmd_str = " ".join(cmd_list)
      if show_logs:
        self.Pd(f"Running command: {cmd_str}", color='d')
      try:
        result = subprocess.run(
          cmd_list, 
          capture_output=True, 
          text=True, 
          timeout=timeout,
        )
      except subprocess.TimeoutExpired as e:
        failed = True
        if show_logs:
          self.P(f"Command timed out after {timeout} seconds: {cmd_str}", color='r')
        if raise_on_error:
          raise Exception(f"Timeout expired for '{cmd_str}'") from e
      except Exception as e:
        failed = True
        msg = f"Error running command `{cmd_str}`: {e}"
        if show_logs:
          self.P(msg, color='r')
        if raise_on_error:
          raise Exception(msg) from e
      
      if result.returncode != 0:
        errors = result.stderr.strip()
        failed = True
        if show_logs:
          self.P(f"Command error `{cmd_str}`: {errors}", color='r')
        if raise_on_error:
          raise Exception(f"Error while running '{cmd_str}': {result.stderr.strip()}")
      
      if not failed:
        if show_logs:
          if verbose:
            self.Pd(f"Command output: {result.stdout.strip()}")
        output = result.stdout.strip()
      if return_errors:
        return output, errors
      return output
    

    def __get_id(self) -> str:
      """
      Get the IPFS peer ID via 'ipfs id' (JSON output).
      Returns the 'ID' field as a string.
      """
      data = self.get_ipfs_id_data()
      self.__ipfs_id_result = data
      self.__ipfs_id = data.get("ID", ERROR_TAG)
      self.__ipfs_agent = data.get("AgentVersion", ERROR_TAG)
      addrs = data.get("Addresses", [])
      if not addrs:
        self.__ipfs_address = None
      else:
        self.__ipfs_address = addrs[1] if len(addrs) > 1 else addrs[0] if len(addrs) else ERROR_TAG
      return self.__ipfs_id
    


    @require_ipfs_started
    def __pin_add(self, cid: str) -> str:
      """
      Explicitly pin a CID (and fetch its data) so it appears in the local pinset.
      """
      res = self.__run_command(["ipfs", "pin", "add", cid])
      self.Pd(f"{res}")
      return res  

  # Public R1FS API calls
  if True:
 
    def add_json(
      self, 
      data, 
      fn=None, 
      secret: str = None,
      nonce: int = None,
      use_tempfile=False,
      show_logs=True,
      raise_on_error=False,
    ) -> str:
      """
      Add a JSON object to IPFS.
      
      Parameters
      ----------
      data : any
          JSON-serializable data to add to IPFS.
          
      fn : str, optional
          Filename to use for the JSON data. If None, uses DEFAULT_FILENAME_JSON
          in a unique temporary directory.
          
      secret : str, optional
          Passphrase for AES-GCM encryption. Defaults to 'ratio1'.
          
      nonce : int, optional
          Nonce for encryption. If None, a random nonce will be generated.
          
      use_tempfile : bool, optional
          If True, use a system temporary file with random name. If False, use specified filename in unique directory.
          
      show_logs : bool, optional
          Whether to show logs via self.P / self.Pd. Default is True.
          
      raise_on_error : bool, optional
          If True, raise an Exception on command errors. Otherwise, logs them. Default is False.
          
      Returns
      -------
      str
          The CID of the added JSON file.
      """
      unique_dir = None
      try:
        json_data = json.dumps(data, sort_keys=True, separators=(',', ':'))
        self.P(f"JSON data: {json_data}")
        
        if use_tempfile:
          if show_logs:
            self.Pd("Using tempfile for JSON")
          with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
          ) as f:
            f.write(json_data)
          fn = f.name
        else:
          # Use default filename if none specified
          if fn is None:
            fn = DEFAULT_FILENAME_JSON
            
          # Create unique temporary directory for the file
          unique_dir = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex)
          os.makedirs(unique_dir, exist_ok=True)
          fn = os.path.join(unique_dir, fn)
          
          if show_logs:
            self.Pd(f"Using unique directory for JSON: {fn}")
          with open(fn, "w") as f:
            f.write(json_data)
        #end if tempfile
        
        if show_logs:
          self.Pd(f"About to call add_file with: file_path={fn}, nonce={nonce}, secret={secret[:10] if secret else 'None'}...")
        
        cid = self.add_file(
          file_path=fn,
          secret=secret,
          nonce=nonce,
          show_logs=show_logs,
          raise_on_error=raise_on_error
        )
        
        if show_logs:
          self.Pd(f"add_file returned CID: {cid}")
        
        return cid
        
      except Exception as e:
        if show_logs:
          self.P(f"Error adding JSON to IPFS: {e}", color='r')
        if raise_on_error:
          raise
        return None
        
      finally:
        # Clean up temporary files and directories
        if fn and os.path.exists(fn):
          os.remove(fn)
          if show_logs:
            self.Pd(f"Cleaned up temporary JSON file: {fn}")
            
        if unique_dir and os.path.exists(unique_dir):
          os.rmdir(unique_dir)
          if show_logs:
            self.Pd(f"Cleaned up temporary directory: {unique_dir}")
      
      
    def add_yaml(
      self, 
      data, 
      fn=None, 
      secret: str = None,
      nonce: int = None,
      tempfile=False,
      show_logs=True,
      raise_on_error=False,
    ) -> str:
      """
      Add a YAML object to IPFS.
      """
      try:
        import yaml
        yaml_data = yaml.dump(data)
        if tempfile:
          if show_logs:
            self.Pd("Using tempfile for YAML")
          with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_data)
          fn = f.name
        else:
          fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".yaml")
          if show_logs:
            self.Pd(f"Using unique name for YAML: {fn}")
          with open(fn, "w") as f:
            f.write(yaml_data)
        cid = self.add_file(
          file_path=fn,
          secret=secret,
          nonce=nonce,
          show_logs=show_logs,
          raise_on_error=raise_on_error
        )
        return cid
      except Exception as e:
        if show_logs:
          self.P(f"Error adding YAML to IPFS: {e}", color='r')
        return None
      
      
    def add_pickle(
      self, 
      data, 
      fn=None, 
      secret: str = None,
      nonce: int = None,
      use_tempfile=False,
      show_logs=True,
      raise_on_error=False,
    ) -> str:
      """
      Add a Pickle object to IPFS.
      
      Parameters
      ----------
      data : any
          Python object to pickle and add to IPFS.
          
      fn : str, optional
          Filename to use for the pickle data. If None, generates a unique filename.
          
      secret : str, optional
          Passphrase for AES-GCM encryption. Defaults to 'ratio1'.
          
      nonce : int, optional
          Nonce for encryption. If None, a random nonce will be generated.
          
      use_tempfile : bool, optional
          If True, use a system temporary file with random name. If False, use specified filename.
          
      show_logs : bool, optional
          Whether to show logs via self.P / self.Pd. Default is True.
          
      raise_on_error : bool, optional
          If True, raise an Exception on command errors. Otherwise, logs them. Default is False.
          
      Returns
      -------
      str
          The CID of the added pickle file.
      """
      try:
        import pickle
        if show_logs:
          self.Pd(f"Pickling data of type: {type(data)}")
        
        if use_tempfile:
          if show_logs:
            self.Pd("Using tempfile for Pickle")
          with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
            pickle.dump(data, f)
          fn = f.name
        else:
          if fn is None:
            fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".pkl")
            if show_logs:
              self.Pd(f"Using unique name for pkl: {fn}")
          else:
            if show_logs:
              self.Pd(f"Using provided filename: {fn}")
          with open(fn, "wb") as f:
            pickle.dump(data, f)
        
        if show_logs:
          self.Pd(f"About to call add_file with: file_path={fn}, nonce={nonce}, secret={secret[:10] if secret else 'None'}...")
        
        cid = self.add_file(
          file_path=fn,
          secret=secret,
          nonce=nonce,
          show_logs=show_logs,
          raise_on_error=raise_on_error
        )
        
        if show_logs:
          self.Pd(f"add_file returned CID: {cid}")
        
        return cid
        
      except Exception as e:
        if show_logs:
          self.P(f"Error adding Pickle to IPFS: {e}", color='r')
        if raise_on_error:
          raise
        return None
        
      finally:
        # Clean up temporary files
        if 'fn' in locals() and fn and os.path.exists(fn):
          os.remove(fn)
          if show_logs:
            self.Pd(f"Cleaned up temporary pickle file: {fn}")


    @require_ipfs_started
    def add_file(
      self,
      file_path: str,
      nonce: int = None,
      secret: str = None,
      raise_on_error: bool = False,
      show_logs: bool = True,
    ) -> str:
      """
      Add a file to R1FS with default encryption. The secret parameter is mandatory,
      defaulting to 'ratio1'. Each encryption run is chunked for large files, and
      the original filename is stored in JSON metadata.


      Parameters
      ----------
      file_path : str
        Path to the local plaintext file.

      secret : str, optional
        Mandatory passphrase, defaulting to 'ratio1'. Must not be empty.
        
      raise_on_error : bool, optional
        If True, raise an Exception on command errors. Otherwise logs them. Default is False.

      show_logs : bool, optional
        Whether to show logs via self.P / self.Pd. Default is True.

      Returns
      -------
      str
        The folder CID of the wrapped IPFS directory containing the ciphertext.

      Raises
      ------
      FileNotFoundError
        If file_path does not exist.

      ValueError
        If secret is empty.

      RuntimeError
        If the 'ipfs add' command yields no output.

      Examples
      --------
      >>> cid = engine.add_file("/data/large_model.bin")
      >>> print(cid)
      QmFolder123ABC
      """
      add_time, remove_time, pin_time = 0.0, 0.0, 0.0
      start_time = time.time()

      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
      
      if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

      # Check file size and throw an error if larger than 5 GB.
      file_size = os.path.getsize(file_path)
      if file_size > 5 * 1024 * 1024 * 1024:
        raise ValueError(f"File {file_path} is too large ({file_size} bytes). Maximum allowed size is 2 GB.")

      key = self._hash_secret(secret)  # mandatory passphrase

      if nonce is None:
        nonce_bytes = os.urandom(12)           # recommended for GCM
        if show_logs:
          self.Pd(f"Generated random nonce: {nonce_bytes.hex()}")
      else:
        original_nonce = nonce
        nonce_bytes = random.Random(nonce).randbytes(12)

      original_basename = os.path.basename(file_path)

      # JSON metadata storing the original filename
      meta_dict = {"filename": original_basename}
      meta_bytes = json.dumps(meta_dict).encode("utf-8")
      
      if show_logs:
        self.Pd(f"Original basename: {original_basename}")
        self.Pd(f"Metadata: {meta_dict}")
        self.Pd(f"Secret hash (first 16 bytes): {key[:16].hex()}")

      tmp_cipher_path = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex + ".bin")
      
      folder_cid = None
      try:
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce_bytes)).encryptor()

        chunk_size = 1024 * 1024  # 1 MB chunks
        with open(file_path, "rb") as fin, open(tmp_cipher_path, "wb") as fout:
          # [nonce][4-byte-len][metadata][ciphertext][16-byte GCM tag]
          fout.write(nonce_bytes)
          meta_len = len(meta_bytes)
          fout.write(meta_len.to_bytes(4, "big"))
          # encrypt the metadata and save
          enc_meta_data = encryptor.update(meta_bytes)
          fout.write(enc_meta_data)

          while True:
            chunk = fin.read(chunk_size)
            if not chunk:
              break
            fout.write(encryptor.update(chunk))
          #end while there are still bytes to read
          final_ct = encryptor.finalize()
          fout.write(final_ct)
          # Append 16-byte GCM tag
          tag = encryptor.tag
          fout.write(tag)
        #end with fin, fout

        # Now we IPFS-add the ciphertext
        output = self.__run_command(["ipfs", "add", "-q", "-w", tmp_cipher_path], show_logs=show_logs)
        lines = output.strip().split("\n")
        self.P("output lines: ", json.dumps(lines))

        if not lines:
          raise RuntimeError("No output from 'ipfs add -w -q' for ciphertext.")
        folder_cid = lines[-1].strip()
      except Exception as e:
        msg = f"Error encrypting file {file_path}: {e}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          self.P(msg, color='r')
      #end try
      add_time = time.time() - start_time
      
      remove_start_time = time.time()
      # Cleanup temp file
      os.remove(tmp_cipher_path)
      remove_time = time.time() - remove_start_time
      
      if folder_cid is not None:
        # Now we notify the relay (if any) about the new CID
        pin_start_time = time.time()
        if self.__ipfs_relay_api is not None:
          #  Notifying the Relay about a new CID.
          try:
            request_url = f"{self.__ipfs_relay_api}/api/v0/pin/add?arg={folder_cid}"
            response = requests.post(request_url,
                                     auth=HTTPBasicAuth(self.__ipfs_api_key_username, self.__ipfs_api_key_password),
                                     verify=self.__ipfs_certificate_path)
            if response.status_code == 200:
              self.Pd(f"Relay successfully notified about CID={folder_cid}.")
            else:
              msg = f"Failed to notify relay about CID {folder_cid}: {response.text}"
              if raise_on_error:
                raise RuntimeError(msg)
              else:
                self.P(msg, color='r')
            #end if response status code
          except requests.RequestException as e:
            msg = f"Error notifying relay about CID {folder_cid}: {e}"
            if raise_on_error:
              raise RuntimeError(msg)
            else:
              self.P(msg, color='r')
          #end try

        self.__uploaded_files[folder_cid] = file_path
        # now we pin the folder
        res = self.__pin_add(folder_cid)
        pin_time = time.time() - pin_start_time
        #end if show_logs
      #end if folder_cid is not None
      total_time = time.time() - start_time
      if show_logs:
        self.P(
          f"Added file {file_path} as <{folder_cid}> in {total_time:.2f}s: add_time={add_time:.2f}s, remove_time={remove_time:.2f}s, pin_time={pin_time:.2f}s")
      return folder_cid


    @require_ipfs_started
    def get_file(
      self,
      cid: str,
      local_folder: str = None,
      secret: str = None,
      timeout: int = None,
      pin: bool = True,
      raise_on_error: bool = False,
      show_logs: bool = True,
      return_absolute_path: bool = True,
    ) -> str:
      """
      Retrieve an encrypted file from R1FS by CID, decrypt with AES-GCM in streaming mode.
      The secret parameter is mandatory (default 'ratio1'). The original filename is
      restored from JSON metadata.

      R1FS get can time out if it stalls. If the timeout is None, we use IPFSCt.TIMEOUT.

      Parameters
      ----------
      cid : str
        The folder CID (wrapped single file).

      local_folder : str, optional
        Destination folder. If None, we default to something like self.__downloads_dir/<CID>.

      secret : str, optional
        Passphrase for AES-GCM. Must not be empty. Defaults to 'ratio1'.

      timeout : int, optional
        Maximum seconds for the IPFS get. If None, use IPFSCt.TIMEOUT.

      pin : bool, optional
        If True, we optionally pin the folder. Default True.

      raise_on_error : bool, optional
        If True, raise an Exception on command errors/timeouts. Otherwise logs them. Default False.

      show_logs : bool, optional
        If True, logs steps via self.P / self.Pd. Default True.

      return_absolute_path : bool, optional
        If True, return the absolute path to the restored plaintext file.

      Returns
      -------
      str
        The full path to the restored plaintext file.

      Raises
      ------
      ValueError
        If the secret is empty.

      RuntimeError
        If multiple or zero files are found in the downloaded folder,
        or if we fail to parse the JSON metadata.

      Exception
        If the GCM tag is invalid or the IPFS command times out
        and raise_on_error=True.

      Examples
      --------
      >>> # Simple usage with default passphrase
      >>> local_file = engine.get_file("QmEncFolderXYZ")
      >>> print(local_file)
      /app/downloads/QmEncFolderXYZ/original_filename.bin
      
      """
      # Validate CID parameter
      if cid in [None, ""]:
        msg = "CID parameter cannot be None or empty"
        if raise_on_error:
          raise ValueError(msg)
        else:
          if show_logs:
            self.P(msg, color='r')
          return None
      
      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
        
      key = self._hash_secret(secret)

      if pin:
        try:
          pin_result = self.__pin_add(cid)
        except Exception as e:
          msg = f"Error pinning CID {cid}: {e}"
          if raise_on_error:
            raise RuntimeError(msg)
          else:
            self.P(msg, color='r')
            return None
          # end if
        #end try
      #end if pin

      if local_folder is None:
        local_folder = self.__downloads_dir # default downloads directory
      
      os.makedirs(local_folder, exist_ok=True)
      
      local_folder = os.path.join(local_folder, cid) # add the CID as a subfolder
      
      # if the folder exists cleanup the content 
      if os.path.exists(local_folder):
        if os.path.isdir(local_folder):
          if show_logs:
            files = os.listdir(local_folder)
            self.Pd(f"Cleaning up {local_folder} with {files}")
          #end if show_logs
          shutil.rmtree(local_folder)
        else:
          # If it's a file, just remove it
          if show_logs:
            self.Pd(f"Removing existing file {local_folder}")
          #end if show_logs
          os.remove(local_folder)
        #end if isdir
      #end if local_folder exists

      
      if show_logs:
        self.Pd(f"Downloading file {cid} to {local_folder}")
      # IPFS get the single ciphertext file
      ipfs_timeout = timeout if timeout else 90  # or IPFSCt.TIMEOUT
      start_time = time.time()
      self.__run_command(
        ["ipfs", "get", cid, "-o", local_folder],
        timeout=ipfs_timeout,
        raise_on_error=raise_on_error,
        show_logs=show_logs
      )
      download_elapsed_time = time.time() - start_time

      # Expect exactly one file
      if not os.path.isdir(local_folder):
        msg = f"Expected {local_folder} to be a directory after IPFS download, but it's not"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          self.P(msg, color='r')
          return

      contents = os.listdir(local_folder)
      if len(contents) != 1:
        msg = f"Expected 1 file in {local_folder}, found {contents}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          self.P(msg, color='r')
          return

      cipher_path = os.path.join(local_folder, contents[0])
      
      out_path = None

      # Decrypt with AES-GCM
      start_time = time.time()
      try:
        with open(cipher_path, "rb") as fin:
          nonce = fin.read(12)
          meta_len_bytes = fin.read(4)
          meta_len = int.from_bytes(meta_len_bytes, "big")

          decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).decryptor()
          
          # Read the metadata and decrypt it
          enc_meta_data = fin.read(meta_len)
          meta_data = decryptor.update(enc_meta_data) # TODO: verify if this is correct
          meta_dict = json.loads(meta_data.decode("utf-8"))

          original_filename = meta_dict.get("filename", "restored_file.bin")

          # File size + chunk logic to isolate last 16 bytes as GCM tag
          fin.seek(0, os.SEEK_END)
          total_size = fin.tell()
          data_start = 12 + 4 + meta_len
          tag_size = 16
          content_size = total_size - data_start - tag_size
          fin.seek(data_start, os.SEEK_SET)

          out_path = os.path.join(local_folder, original_filename)
          if return_absolute_path:
            out_path = os.path.abspath(out_path)
          chunk_size = 1024 * 1024

          with open(out_path, "wb") as fout:
            remaining = content_size
            while remaining > 0:
              read_len = min(chunk_size, remaining)
              chunk = fin.read(read_len)
              if not chunk:
                break
              fout.write(decryptor.update(chunk))
              remaining -= read_len
            #end while there are still bytes to read
            # Final 16 bytes => GCM tag
            tag = fin.read(16)
            # decryptor.authenticate_tag(tag)
            # final_pt = decryptor.finalize()
            final_pt = decryptor.finalize_with_tag(tag)
            if final_pt:
              fout.write(final_pt)
          #end with fout 
        #end with fin
        decrypt_elapsed_time = time.time() - start_time
      except Exception as e:
        out_path = None
        msg = f"Error decrypting file {cipher_path}: {e}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          self.P(msg, color='r')
      #end try

      # Optionally remove the ciphertext
      os.remove(cipher_path)      

      if out_path:
        if show_logs:
          self.P(f"Downloaded/descrypted in {download_elapsed_time:.1f}s/{decrypt_elapsed_time:.1f}s <{cid}> to {out_path}")
        self.__downloaded_files[cid] = out_path      
      #end if out_path is not None
      return out_path

    @require_ipfs_started
    def get_pickle(
      self,
      cid: str,
      local_folder: str = None,
      secret: str = None,
      timeout: int = None,
      pin: bool = True,
      raise_on_error: bool = False,
      show_logs: bool = True,
    ):
      """
      Retrieve and deserialize a pickle file from R1FS by CID.
      Uses get_file under the hood to download and decrypt the file, then loads it with pickle.

      Parameters
      ----------
      cid : str
        The folder CID (wrapped single file).

      local_folder : str, optional
        Destination folder. If None, we default to something like self.__downloads_dir/<CID>.

      secret : str, optional
        Passphrase for AES-GCM. Must not be empty. Defaults to 'ratio1'.

      timeout : int, optional
        Maximum seconds for the IPFS get. If None, use IPFSCt.TIMEOUT.

      pin : bool, optional
        If True, we optionally pin the folder. Default True.

      raise_on_error : bool, optional
        If True, raise an Exception on command errors/timeouts. Otherwise logs them. Default False.

      show_logs : bool, optional
        If True, logs steps via self.P / self.Pd. Default True.

      Returns
      -------
      any
        The deserialized Python object from the pickle file.

      Raises
      ------
      ValueError
        If the secret is empty.

      RuntimeError
        If multiple or zero files are found in the downloaded folder,
        or if we fail to parse the JSON metadata.

      Exception
        If the GCM tag is invalid or the IPFS command times out
        and raise_on_error=True.

      Examples
      --------
      >>> # Simple usage with default passphrase
      >>> data = engine.get_pickle("QmEncFolderXYZ")
      >>> print(data)
      {'key': 'value', 'list': [1, 2, 3]}
      
      """
      import pickle
      
      # Use get_file to download and decrypt the file
      file_path = self.get_file(
        cid=cid,
        local_folder=local_folder,
        secret=secret,
        timeout=timeout,
        pin=pin,
        raise_on_error=raise_on_error,
        show_logs=show_logs,
        return_absolute_path=True
      )
      
      if file_path is None:
        if raise_on_error:
          raise RuntimeError(f"Failed to retrieve file for CID {cid}")
        else:
          if show_logs:
            self.P(f"Failed to retrieve file for CID {cid}", color='r')
          return None
      
      # Load the pickle file
      try:
        with open(file_path, "rb") as f:
          data = pickle.load(f)
        
        if show_logs:
          self.Pd(f"Successfully loaded pickle data from {file_path}")
        
        # Clean up the temporary file
        os.remove(file_path)
        if show_logs:
          self.Pd(f"Cleaned up temporary pickle file: {file_path}")
        
        return data
        
      except Exception as e:
        msg = f"Error loading pickle file {file_path}: {e}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          if show_logs:
            self.P(msg, color='r')
          return None

    @require_ipfs_started
    def get_json(
      self,
      cid: str,
      local_folder: str = None,
      secret: str = None,
      timeout: int = None,
      pin: bool = True,
      raise_on_error: bool = False,
      show_logs: bool = True,
    ):
      """
      Retrieve and deserialize a JSON file from R1FS by CID.
      Uses get_file under the hood to download and decrypt the file, then loads it with json.

      Parameters
      ----------
      cid : str
        The folder CID (wrapped single file).

      local_folder : str, optional
        Destination folder. If None, we default to something like self.__downloads_dir/<CID>.

      secret : str, optional
        Passphrase for AES-GCM. Must not be empty. Defaults to 'ratio1'.

      timeout : int, optional
        Maximum seconds for the IPFS get. If None, use IPFSCt.TIMEOUT.

      pin : bool, optional
        If True, we optionally pin the folder. Default True.

      raise_on_error : bool, optional
        If True, raise an Exception on command errors/timeouts. Otherwise logs them. Default False.

      show_logs : bool, optional
        If True, logs steps via self.P / self.Pd. Default True.

      Returns
      -------
      any
        The deserialized JSON object from the file.

      Raises
      ------
      ValueError
        If the secret is empty.

      RuntimeError
        If multiple or zero files are found in the downloaded folder,
        or if we fail to parse the JSON metadata.

      Exception
        If the GCM tag is invalid or the IPFS command times out
        and raise_on_error=True.

      Examples
      --------
      >>> # Simple usage with default passphrase
      >>> data = engine.get_json("QmEncFolderXYZ")
      >>> print(data)
      {'key': 'value', 'list': [1, 2, 3]}
      
      """
      # Use get_file to download and decrypt the file
      file_path = self.get_file(
        cid=cid,
        local_folder=local_folder,
        secret=secret,
        timeout=timeout,
        pin=pin,
        raise_on_error=raise_on_error,
        show_logs=show_logs,
        return_absolute_path=True
      )
      
      if file_path is None:
        if raise_on_error:
          raise RuntimeError(f"Failed to retrieve file for CID {cid}")
        else:
          if show_logs:
            self.P(f"Failed to retrieve file for CID {cid}", color='r')
          return None
      
      # Load the JSON file
      try:
        with open(file_path, "r", encoding="utf-8") as f:
          data = json.load(f)
        
        if show_logs:
          self.Pd(f"Successfully loaded JSON data from {file_path}")
        
        # Clean up the temporary file
        os.remove(file_path)
        if show_logs:
          self.Pd(f"Cleaned up temporary JSON file: {file_path}")
        
        return data
        
      except Exception as e:
        msg = f"Error loading JSON file {file_path}: {e}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          if show_logs:
            self.P(msg, color='r')
          return None


    @require_ipfs_started
    def list_pins(self):
      """
      List pinned CIDs via 'ipfs pin ls --type=recursive'.
      Returns a list of pinned CIDs.
      """
      output = self.__run_command(["ipfs", "pin", "ls", "--type=recursive"])
      pinned_cids = []
      for line in output.split("\n"):
        line = line.strip()
        if not line:
          continue
        parts = line.split()
        if len(parts) > 0:
          pinned_cids.append(parts[0])
      return pinned_cids
    
    
    @require_ipfs_started
    def is_cid_available(self, cid: str, max_wait=3) -> bool:
      """
      Check if a CID is available on IPFS.
      Returns True if the CID is available, False otherwise.
      
      Parameters
      ----------
      cid : str
          The CID to check.
          
      max_wait : int
          The maximum time to wait for the CID to be found.
          
      """
      CMD = ["ipfs", "block", "stat", cid]  
      result = True
      try:
        res = self.__run_command(CMD, timeout=max_wait)
        self.Pd(f"{cid} is available:\n{res}")
      except Exception as e:
        result = False
      return result


    ########## START DELETE METHODS ##########
    if True:
      def is_pinned(self, cid: str, show_logs: bool = False) -> bool:
        """
        Check if a CID is pinned locally.

        Parameters
        ----------
        cid : str
            The CID to check.

        show_logs : bool, optional
            Whether to show logs. Default is False.

        Returns
        -------
        bool
            True if the CID is pinned, False otherwise.

        Examples
        --------
        >>> if engine.is_pinned("QmHash123..."):
        >>>   print("File is pinned")
        """
        try:
          output = self.__run_command(
            ["ipfs", "pin", "ls", "--type=recursive", cid],
            raise_on_error=False,
            show_logs=False
          )
          is_pinned = cid in output
          if show_logs:
            self.Pd(f"CID {cid} pinned: {is_pinned}")
          return is_pinned
        except Exception as e:
          if show_logs:
            self.Pd(f"Error checking if CID {cid} is pinned: {e}")
          return False

      def unpin_file(
        self,
        cid: str,
        unpin_remote: bool = True,
        show_logs: bool = True,
        raise_on_error: bool = False
      ) -> bool:
        """
        Unpin a file from R1FS locally and optionally on the relay.
        This marks the file for garbage collection but does not immediately delete it.

        Parameters
        ----------
        cid : str
            The CID to unpin.

        unpin_remote : bool, optional
            Whether to also unpin from the relay. Default is True.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        raise_on_error : bool, optional
            If True, raise an Exception on errors. Otherwise logs them. Default is False.

        Returns
        -------
        bool
            True if unpinning was successful, False otherwise.

        Examples
        --------
        >>> # Unpin locally and on relay
        >>> engine.unpin_file("QmHash123...")

        >>> # Unpin only locally
        >>> engine.unpin_file("QmHash123...", unpin_remote=False)
        """
        if cid in [None, ""]:
          msg = "CID parameter cannot be None or empty"
          if raise_on_error:
            raise ValueError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False

        success = True

        try:
          # First, unpin locally
          result = self.__run_command(
            ["ipfs", "pin", "rm", cid],
            raise_on_error=raise_on_error,
            show_logs=False
          )

          if show_logs:
            self.Pd(f"Unpinned CID locally: {cid}")

        except Exception as e:
          msg = f"Error unpinning CID {cid} locally: {e}"
          success = False
          if raise_on_error:
            raise RuntimeError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False

        # Then, notify the relay to unpin (mirrors add_file behavior)
        if unpin_remote and self.__ipfs_relay_api is not None:
          try:
            request_url = f"{self.__ipfs_relay_api}/api/v0/pin/rm?arg={cid}"
            response = requests.post(
              request_url,
              auth=HTTPBasicAuth(self.__ipfs_api_key_username, self.__ipfs_api_key_password),
              verify=self.__ipfs_certificate_path
            )

            if response.status_code == 200:
              if show_logs:
                self.Pd(f"Relay successfully notified to unpin CID={cid}")
            else:
              msg = f"Failed to notify relay to unpin CID {cid}: {response.text}"
              if raise_on_error:
                raise RuntimeError(msg)
              else:
                if show_logs:
                  self.P(msg, color='r')
                success = False
            #end if response status code
          except requests.RequestException as e:
            msg = f"Error notifying relay to unpin CID {cid}: {e}"
            if raise_on_error:
              raise RuntimeError(msg)
            else:
              if show_logs:
                self.P(msg, color='r')
              success = False
          #end try
        #end if relay API exists

        # Remove from tracking dicts if present
        if success:
          self.__uploaded_files.pop(cid, None)
          self.__downloaded_files.pop(cid, None)

        return success

      def delete_file(
        self,
        cid: str,
        unpin_remote: bool = True,
        run_gc: bool = False,
        cleanup_local_files: bool = False,
        show_logs: bool = True,
        raise_on_error: bool = False
      ) -> bool:
        """
        Delete a file from R1FS by unpinning it locally and optionally on the relay,
        then optionally running garbage collection.

        Note: Unpinning removes the file from your local node and (optionally) the relay.
        However, if other nodes have pinned this content, it may remain accessible on the network.

        Parameters
        ----------
        cid : str
            The CID to delete.

        unpin_remote : bool, optional
            Whether to also unpin from the relay. Default is True.
            Set to False if you only want to free local storage.

        run_gc : bool, optional
            Whether to run garbage collection immediately after unpinning.
            Default is False (GC runs automatically with --enable-gc flag on daemon).
            Set to True for immediate disk space reclamation.

        cleanup_local_files : bool, optional
            Whether to also remove local downloaded files from the downloads directory.
            Default is False.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        raise_on_error : bool, optional
            If True, raise an Exception on errors. Otherwise logs them. Default is False.

        Returns
        -------
        bool
            True if deletion was successful, False otherwise.

        Examples
        --------
        >>> # Simple delete (unpin locally and on relay)
        >>> engine.delete_file("QmHash123...")

        >>> # Delete with immediate garbage collection
        >>> engine.delete_file("QmHash123...", run_gc=True)

        >>> # Delete only locally, keep on relay
        >>> engine.delete_file("QmHash123...", unpin_remote=False)

        >>> # Full cleanup: unpin everywhere, GC, and remove local files
        >>> engine.delete_file("QmHash123...", run_gc=True, cleanup_local_files=True)
        """
        if cid in [None, ""]:
          msg = "CID parameter cannot be None or empty"
          if raise_on_error:
            raise ValueError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False

        try:
          # Unpin the file (locally and optionally on relay)
          success = self.unpin_file(
            cid=cid,
            unpin_remote=unpin_remote,
            show_logs=show_logs,
            raise_on_error=raise_on_error
          )

          if not success:
            return False

          # Optional: clean up local downloaded files
          if cleanup_local_files:
            local_folder = os.path.join(self.__downloads_dir, cid)
            if os.path.exists(local_folder):
              try:
                if os.path.isdir(local_folder):
                  shutil.rmtree(local_folder)
                else:
                  os.remove(local_folder)
                if show_logs:
                  self.Pd(f"Removed local files for CID {cid}")
              except Exception as e:
                msg = f"Error removing local files for CID {cid}: {e}"
                if show_logs:
                  self.P(msg, color='r')
                # Don't fail the whole operation if local cleanup fails

          # Optional: run garbage collection immediately
          if run_gc:
            if show_logs:
              self.Pd("Running garbage collection...")
            try:
              gc_result = self.__run_command(
                ["ipfs", "repo", "gc"],
                raise_on_error=False,
                show_logs=False  # GC output can be very verbose
              )
              if show_logs:
                self.P(f"Deleted file {cid} and ran garbage collection", color='g')
            except Exception as e:
              msg = f"Error running garbage collection: {e}"
              if show_logs:
                self.P(msg, color='r')
              # Don't fail if GC fails - the unpin was successful
          else:
            if show_logs:
              location = "local + relay" if unpin_remote else "local only"
              self.P(f"Unpinned file {cid} ({location})", color='g')

          return True

        except Exception as e:
          msg = f"Error deleting file {cid}: {e}"
          if raise_on_error:
            raise RuntimeError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False

      def delete_files(
        self,
        cids: list,
        unpin_remote: bool = True,
        run_gc_after_all: bool = True,
        cleanup_local_files: bool = False,
        show_logs: bool = True,
        raise_on_error: bool = False,
        continue_on_error: bool = True
      ) -> dict:
        """
        Delete multiple files from R1FS in bulk.
        More efficient than calling delete_file repeatedly as it can run GC once at the end.

        Parameters
        ----------
        cids : list
            List of CIDs to delete.

        unpin_remote : bool, optional
            Whether to also unpin from the relay. Default is True.

        run_gc_after_all : bool, optional
            Whether to run garbage collection once after all deletions.
            Default is True. More efficient than running GC for each file.

        cleanup_local_files : bool, optional
            Whether to also remove local downloaded files. Default is False.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        raise_on_error : bool, optional
            If True, raise an Exception on first error. Default is False.

        continue_on_error : bool, optional
            Whether to continue deleting remaining files if one fails.
            Only used if raise_on_error is False. Default is True.

        Returns
        -------
        dict
            Dictionary with keys:
            - 'success': list of successfully deleted CIDs
            - 'failed': list of CIDs that failed to delete
            - 'total': total number of CIDs processed
            - 'success_count': number of successful deletions
            - 'failed_count': number of failed deletions

        Examples
        --------
        >>> # Delete multiple files efficiently
        >>> cids = ["QmHash1...", "QmHash2...", "QmHash3..."]
        >>> result = engine.delete_files(cids)
        >>> print(f"Deleted {result['success_count']} of {result['total']} files")

        >>> # Delete locally only, no GC
        >>> result = engine.delete_files(cids, unpin_remote=False, run_gc_after_all=False)

        >>> # Full cleanup
        >>> result = engine.delete_files(
        >>>   cids,
        >>>   cleanup_local_files=True,
        >>>   run_gc_after_all=True
        >>> )
        """
        if not isinstance(cids, list):
          msg = "cids parameter must be a list"
          if raise_on_error:
            raise ValueError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return {
              'success': [],
              'failed': cids if isinstance(cids, list) else [cids],
              'total': 0,
              'success_count': 0,
              'failed_count': 0
            }

        if len(cids) == 0:
          if show_logs:
            self.Pd("No CIDs provided for deletion")
          return {
            'success': [],
            'failed': [],
            'total': 0,
            'success_count': 0,
            'failed_count': 0
          }

        if show_logs:
          self.P(f"Deleting {len(cids)} files from R1FS...", color='m')

        success_list = []
        failed_list = []

        for i, cid in enumerate(cids):
          if show_logs:
            self.Pd(f"Processing {i+1}/{len(cids)}: {cid}")

          try:
            # Delete without running GC for each file (we'll do it once at the end)
            result = self.delete_file(
              cid=cid,
              unpin_remote=unpin_remote,
              run_gc=False,  # Don't GC per file
              cleanup_local_files=cleanup_local_files,
              show_logs=False,  # Reduce log spam
              raise_on_error=raise_on_error
            )

            if result:
              success_list.append(cid)
            else:
              failed_list.append(cid)
              if not continue_on_error:
                break
          except Exception as e:
            failed_list.append(cid)
            if show_logs:
              self.P(f"Error deleting CID {cid}: {e}", color='r')
            if raise_on_error:
              raise
            if not continue_on_error:
              break

        # Run garbage collection once at the end (more efficient)
        if run_gc_after_all and len(success_list) > 0:
          if show_logs:
            self.P("Running garbage collection for all deleted files...", color='m')
          try:
            gc_result = self.__run_command(
              ["ipfs", "repo", "gc"],
              raise_on_error=False,
              show_logs=False
            )
            if show_logs:
              self.Pd("Garbage collection completed")
          except Exception as e:
            if show_logs:
              self.P(f"Warning: Garbage collection failed: {e}", color='r')
            # Don't fail the whole operation if GC fails

        result = {
          'success': success_list,
          'failed': failed_list,
          'total': len(cids),
          'success_count': len(success_list),
          'failed_count': len(failed_list)
        }

        if show_logs:
          location = "local + relay" if unpin_remote else "local only"
          self.P(
            f"Bulk delete completed: {result['success_count']}/{result['total']} succeeded ({location})",
            color='g' if result['failed_count'] == 0 else 'y'
          )
          if result['failed_count'] > 0:
            self.P(f"Failed to delete {result['failed_count']} files", color='r')

        return result

      def garbage_collect(self, show_logs: bool = True, raise_on_error: bool = False) -> bool:
        """
        Manually run IPFS garbage collection to reclaim disk space from unpinned files.

        Note: The IPFS daemon runs with --enable-gc flag, so GC happens automatically.
        This method is useful for immediate disk space reclamation.

        Parameters
        ----------
        show_logs : bool, optional
            Whether to show logs. Default is True.

        raise_on_error : bool, optional
            If True, raise an Exception on errors. Default is False.

        Returns
        -------
        bool
            True if garbage collection succeeded, False otherwise.

        Examples
        --------
        >>> # Run garbage collection manually
        >>> engine.garbage_collect()
        """
        try:
          if show_logs:
            self.P("Running IPFS garbage collection...", color='m')

          result = self.__run_command(
            ["ipfs", "repo", "gc"],
            raise_on_error=raise_on_error,
            show_logs=False  # GC output can be very verbose
          )

          if show_logs:
            # Count lines in output to show how many blocks were freed
            lines = result.strip().split('\n') if result else []
            blocks_removed = len([l for l in lines if l.strip()])
            self.P(f"Garbage collection completed (~{blocks_removed} blocks processed)", color='g')

          return True

        except Exception as e:
          msg = f"Error running garbage collection: {e}"
          if raise_on_error:
            raise RuntimeError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False

      def cleanup_downloads(
        self,
        cid: str = None,
        show_logs: bool = True
      ) -> int:
        """
        Clean up downloaded files from the local downloads directory.
        This does NOT unpin files from IPFS, only removes local file copies.

        Parameters
        ----------
        cid : str, optional
            Specific CID to clean up. If None, cleans all downloads.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        Returns
        -------
        int
            Number of items cleaned up.

        Examples
        --------
        >>> # Clean up all downloaded files
        >>> count = engine.cleanup_downloads()
        >>> print(f"Cleaned up {count} files")

        >>> # Clean up specific CID's downloads
        >>> engine.cleanup_downloads(cid="QmHash123...")
        """
        count = 0

        try:
          if not os.path.exists(self.__downloads_dir):
            if show_logs:
              self.Pd(f"Downloads directory does not exist: {self.__downloads_dir}")
            return 0

          if cid is not None:
            # Clean up specific CID
            target_path = os.path.join(self.__downloads_dir, cid)
            if os.path.exists(target_path):
              try:
                if os.path.isdir(target_path):
                  shutil.rmtree(target_path)
                else:
                  os.remove(target_path)
                count = 1
                if show_logs:
                  self.P(f"Cleaned up local files for CID: {cid}", color='g')
                # Remove from tracking dict
                self.__downloaded_files.pop(cid, None)
              except Exception as e:
                if show_logs:
                  self.P(f"Error cleaning up CID {cid}: {e}", color='r')
            else:
              if show_logs:
                self.Pd(f"No local files found for CID: {cid}")
          else:
            # Clean up all downloads
            for item in os.listdir(self.__downloads_dir):
              item_path = os.path.join(self.__downloads_dir, item)
              try:
                if os.path.isdir(item_path):
                  shutil.rmtree(item_path)
                else:
                  os.remove(item_path)
                count += 1
              except Exception as e:
                if show_logs:
                  self.P(f"Error removing {item_path}: {e}", color='r')

            if show_logs:
              self.P(f"Cleaned up {count} items from downloads directory", color='g')

            # Clear all tracking
            self.__downloaded_files.clear()

        except Exception as e:
          if show_logs:
            self.P(f"Error during cleanup: {e}", color='r')

        return count

    ######## END DELETE METHODS #########

    def calculate_file_cid(
      self,
      file_path: str,
      nonce: int,
      secret: str = None,
      show_logs: bool = True
    ) -> str:
      """
      Calculate the CID (Content Identifier) of a file without adding it to IPFS.
      This method encrypts the file the same way as add_file and computes the CID
      that would be generated if the encrypted file were added to IPFS.
      
      Parameters
      ----------
      file_path : str
          Path to the local file to calculate CID for.
          
      nonce : int
          Nonce for encryption. Required parameter for deterministic CID calculation.
          
      secret : str, optional
          Passphrase for AES-GCM encryption. Defaults to 'ratio1'.
          
      show_logs : bool, optional
          Whether to show logs via self.P / self.Pd. Default is True.
          
      Returns
      -------
      str
          The CID of the encrypted file (e.g., "QmHash...")
          
      Raises
      ------
      FileNotFoundError
          If file_path does not exist.
          
      ImportError
          If IPFS is not available or not running.
          
      ValueError
          If nonce is None or invalid.
          
      Examples
      --------
      >>> cid = engine.calculate_file_cid("/path/to/file.txt", nonce=12345)
      >>> print(cid)
      QmHash123ABC...
      """
      if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
        
      # Validate nonce parameter
      if nonce is None:
        raise ValueError("nonce parameter is required for deterministic CID calculation")
        
      # Check file size and throw an error if larger than 2 GB.
      file_size = os.path.getsize(file_path)
      if file_size > 2 * 1024 * 1024 * 1024:
        raise ValueError(f"File {file_path} is too large ({file_size} bytes). Maximum allowed size is 2 GB.")

      key = self._hash_secret(secret)
      nonce_bytes = random.Random(nonce).randbytes(12)

      original_basename = os.path.basename(file_path)

      # JSON metadata storing the original filename
      meta_dict = {"filename": original_basename}
      meta_bytes = json.dumps(meta_dict).encode("utf-8")

      if show_logs:
        self.Pd(f"Calculating CID for encrypted file: {file_path}")
        self.Pd(f"Nonce input: {nonce}, Generated nonce bytes: {nonce_bytes.hex()}")
        self.Pd(f"Original basename: {original_basename}")
        self.Pd(f"Metadata: {meta_dict}")
        self.Pd(f"Secret hash (first 16 bytes): {key[:16].hex()}")

      # Create temporary encrypted file (same as in add_file)
      tmp_cipher_path = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex + ".bin")

      try:
        # Encrypt the file content (same as in add_file)
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce_bytes)).encryptor()

        chunk_size = 1024 * 1024  # 1 MB chunks
        with open(file_path, "rb") as fin, open(tmp_cipher_path, "wb") as fout:
          # [nonce][4-byte-len][metadata][ciphertext][16-byte GCM tag]
          fout.write(nonce_bytes)
          meta_len = len(meta_bytes)
          fout.write(meta_len.to_bytes(4, "big"))
          # encrypt the metadata and save
          enc_meta_data = encryptor.update(meta_bytes)
          fout.write(enc_meta_data)

          while True:
            chunk = fin.read(chunk_size)
            if not chunk:
              break
            fout.write(encryptor.update(chunk))
          #end while there are still bytes to read
          final_ct = encryptor.finalize()
          fout.write(final_ct)
          # Append 16-byte GCM tag
          tag = encryptor.tag
          fout.write(tag)
        #end with fin, fout

        # Use IPFS to calculate the hash without adding the file
        output = self.__run_command(["ipfs", "add", "--only-hash", "-q", "-w", tmp_cipher_path], show_logs=show_logs)
        lines = output.strip().split("\n")
        self.P("output lines: ", json.dumps(lines))
        if not lines:
          raise RuntimeError("No output from 'ipfs add --only-hash -q -w' for ciphertext.")

        # Get the CID from IPFS
        file_cid = lines[0].strip()
        if show_logs:
          self.Pd(f"IPFS calculated CID: {file_cid}")
        
        return file_cid
        
      finally:
        # Clean up temporary encrypted file
        if os.path.exists(tmp_cipher_path):
          os.remove(tmp_cipher_path)

    def calculate_json_cid(
      self,
      data,
      nonce: int,
      fn: str = None,
      secret: str = None,
      show_logs: bool = True
    ) -> str:
      """
      Calculate the CID (Content Identifier) of JSON data without adding it to IPFS.
      This method saves the JSON data to a temporary file, then uses calculate_file_cid
      to compute the CID that would be generated if the encrypted file were added to IPFS.
      
      Parameters
      ----------
      data : any
          JSON-serializable data to calculate CID for.
          
      nonce : int
          Nonce for encryption. Required parameter for deterministic CID calculation.
          
      fn : str, optional
          Filename to use for the JSON data. If None, uses DEFAULT_FILENAME_JSON.
          This affects the CID calculation as the filename is included in the metadata.
          
      secret : str, optional
          Passphrase for AES-GCM encryption. Defaults to 'ratio1'.
          
      show_logs : bool, optional
          Whether to show logs via self.P / self.Pd. Default is True.
          
      Returns
      -------
      str
          The CID of the encrypted JSON file (e.g., "QmHash...")
          
      Raises
      ------
      ImportError
          If IPFS is not available or not running.
          
      ValueError
          If nonce is None or invalid, or if data cannot be JSON serialized.
          
      Examples
      --------
      >>> data = {"name": "test", "value": 123}
      >>> cid = engine.calculate_json_cid(data, nonce=12345)
      >>> print(cid)
      QmHash123ABC...
      
      >>> # Use custom filename
      >>> cid = engine.calculate_json_cid(data, nonce=12345, fn="config.json")
      >>> print(cid)
      QmHash456DEF...
      """
      # Serialize JSON data
      try:
        json_data = json.dumps(data, sort_keys=True, separators=(',', ':'))
      except (TypeError, ValueError) as e:
        raise ValueError(f"Data cannot be JSON serialized: {e}")
      
      self.P(f"JSON data: {json_data}")

      # Use custom filename or default
      if fn is None:
        fn = DEFAULT_FILENAME_JSON

      if show_logs:
        self.Pd(f"Calculating CID for JSON data with {len(json_data)} characters, filename: {fn}")
      
      # Create temporary file for JSON data with the desired filename in a unique directory
      unique_dir = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex)
      os.makedirs(unique_dir, exist_ok=True)
      tmp_json_path = os.path.join(unique_dir, fn)
      
      file_cid = None
      try:
        # Write JSON data to temporary file
        with open(tmp_json_path, "w") as f:
          f.write(json_data)
        
        if show_logs:
          self.Pd(f"About to call calculate_file_cid with: file_path={tmp_json_path}, nonce={nonce}, secret={secret[:10] if secret else 'None'}...")
        
        # Use calculate_file_cid to get the CID
        file_cid = self.calculate_file_cid(
          file_path=tmp_json_path,
          nonce=nonce,
          secret=secret,
          show_logs=True  # Don't show logs from calculate_file_cid
        )
        
        if show_logs:
          self.Pd(f"calculate_file_cid returned CID: {file_cid}")
        
      finally:
        # Clean up temporary JSON file and directory
        if os.path.exists(tmp_json_path):
          os.remove(tmp_json_path)
        if os.path.exists(unique_dir):
          os.rmdir(unique_dir)
      
      return file_cid

    def calculate_pickle_cid(
      self,
      data,
      nonce: int,
      fn: str = None,
      secret: str = None,
      show_logs: bool = True
    ) -> str:
      """
      Calculate the CID (Content Identifier) of pickle data without adding it to IPFS.
      This method saves the pickle data to a temporary file, then uses calculate_file_cid
      to compute the CID that would be generated if the encrypted file were added to IPFS.
      
      Parameters
      ----------
      data : any
          Python object to pickle and calculate CID for.
          
      nonce : int
          Nonce for encryption. Required parameter for deterministic CID calculation.
          
      fn : str, optional
          Filename to use for the pickle data. If None, generates a unique filename.
          This affects the CID calculation as the filename is included in the metadata.
          
      secret : str, optional
          Passphrase for AES-GCM encryption. Defaults to 'ratio1'.
          
      show_logs : bool, optional
          Whether to show logs via self.P / self.Pd. Default is True.
          
      Returns
      -------
      str
          The CID of the encrypted pickle file (e.g., "QmHash...")
          
      Raises
      ------
      ImportError
          If IPFS is not available or not running.
          
      ValueError
          If nonce is None or invalid, or if data cannot be pickled.
          
      Examples
      --------
      >>> data = {"name": "test", "value": 123}
      >>> cid = engine.calculate_pickle_cid(data, nonce=12345)
      >>> print(cid)
      QmHash123ABC...
      
      >>> # Use custom filename
      >>> cid = engine.calculate_pickle_cid(data, nonce=12345, fn="model.pkl")
      >>> print(cid)
      QmHash456DEF...
      """
      # Serialize pickle data
      try:
        import pickle
        pickle_data = pickle.dumps(data)
      except (TypeError, ValueError, pickle.PicklingError) as e:
        raise ValueError(f"Data cannot be pickled: {e}")
      
      if show_logs:
        self.Pd(f"Pickled data of type: {type(data)}, size: {len(pickle_data)} bytes")

      # Use custom filename or generate unique one
      if fn is None:
        fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".pkl")

      if show_logs:
        self.Pd(f"Calculating CID for pickle data with {len(pickle_data)} bytes, filename: {fn}")
      
      # Create temporary file for pickle data with the desired filename in a unique directory
      unique_dir = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex)
      os.makedirs(unique_dir, exist_ok=True)
      tmp_pickle_path = os.path.join(unique_dir, fn)
      
      file_cid = None
      try:
        # Write pickle data to temporary file
        with open(tmp_pickle_path, "wb") as f:
          f.write(pickle_data)
        
        if show_logs:
          self.Pd(f"About to call calculate_file_cid with: file_path={tmp_pickle_path}, nonce={nonce}, secret={secret[:10] if secret else 'None'}...")
        
        # Use calculate_file_cid to get the CID
        file_cid = self.calculate_file_cid(
          file_path=tmp_pickle_path,
          nonce=nonce,
          secret=secret,
          show_logs=True  # Don't show logs from calculate_file_cid
        )
        
        if show_logs:
          self.Pd(f"calculate_file_cid returned CID: {file_cid}")
        
      finally:
        # Clean up temporary pickle file and directory
        if os.path.exists(tmp_pickle_path):
          os.remove(tmp_pickle_path)
        if os.path.exists(unique_dir):
          os.rmdir(unique_dir)
      
      return file_cid
      

  # Start/stop IPFS methods (R1FS API)
  if True:
    @property
    def is_ipfs_warmed(self) -> bool:
      """
      @Deprecated:
      This method is deprecated and will be removed in future versions.
      Check if IPFS is warmed up (connected to the relay and has been for a while).
      """
      return True

    def is_ipfs_daemon_running(
      self,
      host="127.0.0.1",
      port=5001,
      method="POST",
      timeout=3
    ) -> bool:
      """
      Checks if an IPFS daemon is running by calling /api/v0/version
      on the specified host and port. Some configurations require
      POST instead of GET, so we allow a method argument.

      Returns:
          bool: True if the IPFS daemon responds successfully; False otherwise.
      """
      url = f"http://{host}:{port}/api/v0/version"
      result = False
      output = None
      try:
        if method.upper() == "POST":
          response = requests.post(url, timeout=timeout)
        else:
          response = requests.get(url, timeout=timeout)

        if response.status_code == 200:
          data = response.json()
          output = str(data)
          if "Version" in data:
            result = True
          else:
            result = False
        else:
          result = False
          output = f"Status code: {response.status_code}"

      except Exception as e:
        result = False
        output = str(e)
      self.P(f"IPFS daemon run-check: {result} ({output})")
      return result        
    
    def is_ipfs_daemon_ready(self, max_wait=30, step=1):
      """ Check with timeout if the IPFS daemon is running and ready to accept requests."""
      waited = 0
      while waited < max_wait:
        if self.is_ipfs_daemon_running():
          return True
        time.sleep(step)
        waited += step
      return False    
    
    def maybe_reset_ipfs(self):
      """ Reset the IPFS repository if needed, remove swarm key and ipfs home."""
      

    def maybe_start_ipfs(
      self, 
      base64_swarm_key: str = None, 
      ipfs_relay: str = None,
      ipfs_relay_api: str = None,
      ipfs_api_key_username: str = None,
      ipfs_api_key_password: str = None,
      ipfs_certificate_path: str = None,
    ) -> bool:
      """
      This method initializes the IPFS repository if needed, connects to a relay, and starts the daemon.
      TODO: (Vitalii) Split this into smaller methods.
      """
      if self.ipfs_started:
        return
      
      self.P("Starting R1FS...", color='m')
      
      if base64_swarm_key is None:
        base64_swarm_key = os.getenv(IPFSCt.EE_SWARM_KEY_CONTENT_BASE64_ENV_KEY)
        if base64_swarm_key is not None:
          self.P(f"Found env IPFS swarm key: {str(base64_swarm_key)[:4]}...", color='d')
          if len(base64_swarm_key) < 10:
            self.P(f"Invalid IPFS swarm key: `{base64_swarm_key}`", color='r')
            return False
        
      if ipfs_relay is None:
        ipfs_relay = os.getenv(IPFSCt.EE_IPFS_RELAY_ENV_KEY)
        if ipfs_relay is not None:
          self.P(f"Found env IPFS relay: {ipfs_relay}", color='d')
          if len(ipfs_relay) < 10:
            self.P(f"Invalid IPFS relay: `{ipfs_relay}`", color='r')
            return False

      if ipfs_relay_api is None:
        ipfs_relay_api = os.getenv(IPFSCt.EE_IPFS_RELAY_API_KEY)
        if ipfs_relay_api is not None:
          self.P(f"Found env IPFS relay API: {ipfs_relay_api}", color='d')

      # Set up IPFS API key username and password.
      if ipfs_api_key_username is None or ipfs_api_key_password is None:
        try:
          ipfs_api_key_base64 = os.getenv(IPFSCt.EE_IPFS_API_KEY_BASE64_KEY)
          ipfs_api_key_b = base64.b64decode(ipfs_api_key_base64)
          ipfs_api_key = str(ipfs_api_key_b, 'utf-8')
          split_api_key = ipfs_api_key.split(":")
          ipfs_api_key_username = split_api_key[0]
          ipfs_api_key_password = split_api_key[1]
        except Exception as e:
          self.P(f"An error occurred while extracting IPFS Relay username and password {e}", color='r')


      # Set up certificate
      if ipfs_certificate_path is None:
        try:
          certificate_encoded = os.getenv(IPFSCt.EE_IPFS_CERTIFICATE_BASE64_KEY)
          decoded = self.__decode_base64_gzip_to_text(certificate_encoded)

          with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.crt') as f:
            f.write(decoded)
            ipfs_certificate_path = f.name

          if not os.path.isfile(ipfs_certificate_path):
            raise FileNotFoundError(f"Could not create certificate file : {ipfs_certificate_path}")
        except Exception as e:
          self.P(f"Error reading the certificate file: {e}", color='r')

      if not base64_swarm_key or not ipfs_relay:
        self.P("Missing env values EE_SWARM_KEY_CONTENT_BASE64 and EE_IPFS_RELAY.", color='r')
        return False
      
      self.__base64_swarm_key = base64_swarm_key
      self.__ipfs_relay = ipfs_relay
      self.__ipfs_relay_api = ipfs_relay_api
      self.__ipfs_api_key_username = ipfs_api_key_username
      self.__ipfs_api_key_password = ipfs_api_key_password
      self.__ipfs_certificate_path = ipfs_certificate_path
      hidden_base64_swarm_key = base64_swarm_key[:8] + "..." + base64_swarm_key[-8:]
      
      existing_ipfs_home = os.getenv("IPFS_PATH")
      home_ready = False
      if existing_ipfs_home:
        self.P(f"Found existing IPFS home: {existing_ipfs_home}", color='d')
        if IPFSCt.CACHE_ROOT in existing_ipfs_home and os.path.isdir(existing_ipfs_home):
          self.__ipfs_home = os.path.abspath(existing_ipfs_home)
          home_ready = True
        else:
          self.P(f"Invalid IPFS home: {existing_ipfs_home}", color='r')
        #endif
      #endif 
      if not home_ready:
        self.P("No existing IPFS home found, creating a new one.", color='d')
        ipfs_home = os.path.join(self.logger.base_folder, ".ipfs/")        
        os.makedirs(ipfs_home, exist_ok=True)
        self.__ipfs_home = os.path.abspath(ipfs_home)
        os.environ["IPFS_PATH"] = self.__ipfs_home
      
      config_path = os.path.join(self.__ipfs_home, "config")
      swarm_key_path = os.path.join(self.__ipfs_home, "swarm.key")

      msg = f"Starting R1FS <{self.__name}>:"
      msg += f"\n  IPFS Home: {self.__ipfs_home}"
      msg += f"\n  Relay:    {self.__ipfs_relay}"
      msg += f"\n  Download: {self.__downloads_dir}"
      msg += f"\n  Upload:   {self.__uploads_dir}"
      msg += f"\n  SwarmKey: {hidden_base64_swarm_key}"
      msg += f"\n  Debug:    {self.__debug}"
      msg += f"\n  Repo:     {self.ipfs_home}"
      self.P(msg, color='d')
      
      # Write the swarm key at every start.
      try:
        decoded_key = base64.b64decode(base64_swarm_key)
        with open(swarm_key_path, "wb") as f:
          f.write(decoded_key)
        os.chmod(swarm_key_path, 0o600)
        self.P("Swarm key written successfully.", color='g')
      except Exception as e:
        self.P(f"Error writing swarm.key: {e}", color='r')
        return False

      if not os.path.isfile(config_path):
        # Repository is not initialized; init.
        try:
          self.P("Initializing IPFS repository...")
          self.__run_command(["ipfs", "init"])
        except Exception as e:
          self.P(f"Error during IPFS init: {e}", color='r')
          return False
      else:
        self.P(f"IPFS repository already initialized in {config_path}.", color='g')


      # Check if daemon is already running by attempting to get the node id.
      try:
        self.P("Trying to see if IPFS daemon is running...", color='d')
        n_ipfs_daemon_checks = 3
        for attempt in range(1, n_ipfs_daemon_checks + 1):
          ipfs_daemon_running = self.is_ipfs_daemon_running()
          if ipfs_daemon_running:
            break
          else:
            self.P(f"Check {attempt}/{n_ipfs_daemon_checks} IPFS started: {ipfs_daemon_running}", color='d')
            time.sleep(2)
        #end for
        
        if ipfs_daemon_running:
          self.P("IPFS daemon already running", color='g')
        else:
          # If not running, start the daemon in the background.
          self.P("IPFS daemon not running. Trying to start...", color='r')     
          ###################################################
          #######             CLEANUP PHASE            ######
          ###################################################                            
          # we start by removing any existing bootstrap nodes
          try:
            self.P("Removing public IPFS bootstrap nodes...")
            self.__run_command(["ipfs", "bootstrap", "rm", "--all"])
          except Exception as e:
            self.P(f"Error removing bootstrap nodes: {e}", color='r')
               
          # then delete the repository lock file if it exists
          lock_file = os.path.join(self.__ipfs_home, "repo.lock")
          if os.path.isfile(lock_file):
            self.P(f"Deleting lock file {lock_file}...")
            os.remove(lock_file)
          else:
            self.P(f"Lock file {lock_file} not found.")
          # next check if the api is zero-length - if so, delete it
          api_file = os.path.join(self.__ipfs_home, "api")
          if os.path.isfile(api_file) and os.path.getsize(api_file) == 0:
            self.P(f"Deleting zero-length api file {api_file}...")
            os.remove(api_file)
          #endif            
          # now we can start the daemon
          ###################################################
          #######        END OF CLEANUP PHASE        ########
          ###################################################
          self.__set_reprovider_interval()
          self.__disable_auto_tls()
          self.__set_routing_type_dht()
          self.__disable_ws_transport()
          self.__bootstrap_add(self.__ipfs_relay)
          self.P("Starting IPFS daemon in background...")
          subprocess.Popen(["ipfs", "daemon", "--enable-gc", "--migrate=true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
          max_attempts = 10
          sleep_time = 2
          for attempt in range(max_attempts):
            ipfs_daemon_running = self.is_ipfs_daemon_running()
            if ipfs_daemon_running:
              self.P("IPFS daemon started successfully.", color='g')
              break
            else:
              self.P(f"Check {attempt + 1}/{max_attempts} IPFS running: {ipfs_daemon_running}", color='r')
              time.sleep(sleep_time)
          #end for
          if not ipfs_daemon_running:
            self.P("Failed to start IPFS daemon after multiple attempts.", color='r')
            return False
        #end if daemon running
      except Exception as e:
        self.P(f"Error starting IPFS daemon: {e}", color='r')
        return

      # last phase: connect to the relay      
      try:
        relay_ip = ipfs_relay.split("/")[2]
        self.P("Getting the IPFS ID...")
        my_id = self.__get_id()
        assert my_id != ERROR_TAG, "Failed to get IPFS ID."
        self.P("Checking swarm peers...")
        swarm_peers = self._get_swarm_peers()
        if len(swarm_peers) > 0:
          self.P(f"{len(swarm_peers)} swarm peers detected. Checking for relay connection...")
          relay_found = self._check_and_record_relay_connection(debug=True)
          if relay_found:
            self.__ipfs_started = True
            self.P(f"{my_id} connected to: {relay_ip}", color='g', boxed=True)
          else:
            self.P("No relay connection found in swarm peers.", color='r')
            self.__ipfs_started = False
          #end if relay_found
        
        if not self.__ipfs_started:
          msg =  f"Connecting to R1FS relay"
          msg += f"\n  IPFS Home:  {self.ipfs_home}"
          msg += f"\n  IPFS ID:    {my_id}"
          msg += f"\n  IPFS Addr:  {self.__ipfs_address}"
          msg += f"\n  IPFS Agent: {self.__ipfs_agent}"
          msg += f"\n  Relay:      {ipfs_relay}"
          self.P(msg, color='m')
          result = self.__run_command(["ipfs", "swarm", "connect", ipfs_relay])
          if "connect" in result.lower() and "success" in result.lower():
            self.P(f"{my_id} connected to: {relay_ip}", color='g', boxed=True)
            self.__ipfs_started = True
            self.P("Re-checking swarm peers...")
            swarm_peers = self._get_swarm_peers()
            self.P(f"Swarm peers:\n {json.dumps(swarm_peers, indent=2)}")
            self._check_and_record_relay_connection(debug=True)
          else:
            self.P("Relay connection result did not indicate success.", color='r')
      except Exception as e:
        self.P(f"Error connecting to relay: {e}", color='r')
      #end try
      return self.ipfs_started

  def __decode_base64_gzip_to_text(self, encoded_str):
    try:
      # Step 1: Decode base64
      compressed_data = base64.b64decode(encoded_str)
      # Step 2: Decompress gzip
      with gzip.GzipFile(fileobj=BytesIO(compressed_data)) as f:
        decompressed_data = f.read()
      # Step 3: Convert bytes to string
      return decompressed_data.decode('utf-8')
    except Exception as e:
      self.P(f"Error decoding base64 string: {e}")
    return ''

if __name__ == '__main__':
  from ratio1 import Logger
  log = Logger("IPFST")
  # eng = R1FSEngine()