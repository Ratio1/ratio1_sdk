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

from threading import Lock

__VER__ = "0.2.2"

# empirically determined minimum connection age for IPFS relay
DEFAULT_MIN_CONNECTION_AGE = 3600 # seconds


class IPFSCt:
  EE_IPFS_RELAY_ENV_KEY = "EE_IPFS_RELAY"
  EE_SWARM_KEY_CONTENT_BASE64_ENV_KEY = "EE_SWARM_KEY_CONTENT_BASE64"
  R1FS_DOWNLOADS = "ipfs_downloads"
  R1FS_UPLOADS = "ipfs_uploads"
  TEMP_DOWNLOAD = os.path.join("./_local_cache/_output", R1FS_DOWNLOADS)
  TEMP_UPLOAD = os.path.join("./_local_cache/_output", R1FS_UPLOADS)
  
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
      raise RuntimeError(f"{method.__name__} FAILED. R1FS.ipfs_started=={self.ipfs_started}")
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
    ipfs_relay: str = None,   
    debug=False,     
    min_connection_age: int = DEFAULT_MIN_CONNECTION_AGE,
  ):
    with cls._lock:
      if name not in cls.__instances:
        instance = super(R1FSEngine, cls).__new__(cls)
        instance._build(
          name=name, logger=logger, downloads_dir=downloads_dir, uploads_dir=uploads_dir,
          base64_swarm_key=base64_swarm_key, ipfs_relay=ipfs_relay, debug=debug,
          min_connection_age=min_connection_age,
        )
        cls.__instances[name] = instance
      else:
        instance = cls.__instances[name]
    return instance
    
  def _build(
    self, 
    name: str = "default",
    logger: any = None, 
    downloads_dir: str = None,
    uploads_dir: str = None,
    base64_swarm_key: str = None, 
    ipfs_relay: str = None,   
    min_connection_age: int = DEFAULT_MIN_CONNECTION_AGE,
    debug=False,     
  ):
    """
    Initialize the IPFS wrapper with a given logger function.
    By default, it uses the built-in print function for logging.
    
    
    """
    self.__name = name
    if logger is None:
      logger = SimpleLogger()

    self.logger = logger

    self.__ipfs_started = False
    self.__ipfs_address = None
    self.__ipfs_id = None
    self.__min_connection_age = min_connection_age
    self.__connected_at = None
    self.__ipfs_agent = None
    self.__uploaded_files = {}
    self.__downloaded_files = {}
    self.__base64_swarm_key = base64_swarm_key
    self.__ipfs_relay = ipfs_relay
    self.__ipfs_home = None
    self.__downloads_dir = downloads_dir
    self.__uploads_dir = uploads_dir    
    self.__debug = debug
    
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
    
    self.maybe_start_ipfs(
      base64_swarm_key=self.__base64_swarm_key,
      ipfs_relay=self.__ipfs_relay,
    )
    return
    
    
  def P(self, s, *args, **kwargs):
    s = "[R1FS] " + s
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
  
  def _set_debug(self):
    """
    Force debug mode on.
    """
    self.__debug = True
    return
    
  @property
  def ipfs_id(self):
    return self.__ipfs_id
  
  @property
  def ipfs_address(self):
    return self.__ipfs_address
  
  @property
  def ipfs_agent(self):
    return self.__ipfs_agent
  
  @property
  def ipfs_started(self):
    return self.__ipfs_started
  
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
    return os.environ.get("IPFS_PATH")
  
  
  def _get_unique_name(self, prefix="r1fs", suffix=""):
    str_id = str(uuid.uuid4()).replace("-", "")[:8]
    return f"{prefix}_{str_id}{suffix}"
  
  def _get_unique_upload_name(self, prefix="r1fs", suffix=""):
    return os.path.join(self.__uploads_dir, self._get_unique_name(prefix, suffix))
  
  def _get_unique_or_complete_upload_name(self, fn=None, prefix="r1fs", suffix=""):
    if fn is not None and os.path.dirname(fn) == "":
      return os.path.join(self.__uploads_dir, f"{fn}{suffix}")
    return self._get_unique_upload_name(prefix, suffix=suffix)
  

  def _check_and_record_relay_connection(self, max_check_age : int = 3600):
    """
    Checks if we're connected to the relay_peer_id by parsing 'ipfs swarm peers'.
    If connected and we haven't recorded connected_at yet, we set it.
    """
    relay_found = False
    try:
      if self.connected_at is not None:
        # Already connected, lets see if last check was recent enough:
        elapsed_time = time.time() - self.connected_at
        if elapsed_time < max_check_age:
          relay_found = True
          self.Pd(f"Already connected to relay peer for {elapsed_time:.1f}s, skipping check.")
          # If we are connected and the last check was recent enough, return True:
        else:
          self.Pd(f"Last connection check was {elapsed_time:.1f}s ago, checking again...")
          # If we are connected but the last check was too long ago, check again:
        #end if needs recheck or not
      #end if connected_at is not None
      else:          
        self.Pd("Checking IPFS relay connection and swarm peers...")
        out = subprocess.run(
          ["ipfs", "swarm", "peers"],
          capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
          peer_lines = out.stdout.strip().split("\n")
          self.Pd(f"Swarm peers:\n{json.dumps(peer_lines, indent=4)}")
          self.__peers = peer_lines
          for line in peer_lines:
            # If the line contains the relay peer ID, we consider ourselves connected:
            if self.__ipfs_relay in line:
              # Record the time if not already set
              relay_found = True
              self.Pd(f"Found relay peer in swarm peers: {line.strip()}")
            #end if
          #end for
          # now reset the connected_at time if we found the relay peer
          if relay_found:
            self.__connected_at = time.time()
            str_connected = self.logger.time_to_str(self.__connected_at)
            self.P(f"Connected to relay peer recorded at {str_connected}.")
          else:
            self.__connected_at = None
            self.Pd(f"Relay peer not found in swarm peers: {self.__ipfs_relay}", color='r')
        else:
          self.P(f"Error checking swarm peers: {out.stderr.strip()}", color='r')
    except subprocess.TimeoutExpired:
      self.P("Timeout checking swarm peers.", color='r')
      relay_found = False
    except Exception as e:
      self.P(f"Error checking swarm peers: {e}", color='r')
      relay_found = False
    #end try
    return relay_found


  def __set_reprovider_interval(self):
    # Command to set the Reprovider.Interval to 1 minute
    cmd = ["ipfs", "config", "--json", "Reprovider.Interval", f'"{IPFSCt.REPROVIDER}"']
    result = self.__run_command(cmd)
    return result

  
  def __set_relay(self):
    # Command to enable the IPFS relay
    result = self.__run_command(
      ["ipfs", "config", "--json", "Swarm.DisableRelay", "false"]
    )
    return result


  def __run_command(
    self, 
    cmd_list: list, 
    raise_on_error=True,
    timeout=IPFSCt.TIMEOUT,
    verbose=False,
  ):
    """
    Run a shell command using subprocess.run with a timeout.
    Logs the command and its result. If verbose is enabled,
    prints command details. Raises an exception on error if raise_on_error is True.
    """
    failed = False
    output = ""
    cmd_str = " ".join(cmd_list)
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
      self.P(f"Command timed out after {timeout} seconds: {cmd_str}", color='r')
      if raise_on_error:
        raise Exception(f"Timeout expired for '{cmd_str}'") from e
    
    if result.returncode != 0:
      failed = True
      self.P(f"Command error: {result.stderr.strip()}", color='r')
      if raise_on_error:
        raise Exception(f"Error while running '{cmd_str}': {result.stderr.strip()}")
    
    if not failed:
      if verbose:
        self.Pd(f"Command output: {result.stdout.strip()}")
      output = result.stdout.strip()
    return output
  

  def __get_id(self) -> str:
    """
    Get the IPFS peer ID via 'ipfs id' (JSON output).
    Returns the 'ID' field as a string.
    """
    output = self.__run_command(["ipfs", "id"])
    try:
      data = json.loads(output)
      self.__ipfs_id = data.get("ID", ERROR_TAG)
      addrs = data.get("Addresses", [])
      self.__ipfs_address = addrs[1] if len(addrs) > 1 else addrs[0] if len(addrs) else ERROR_TAG
      self.__ipfs_agent = data.get("AgentVersion", ERROR_TAG)
      return data.get("ID", ERROR_TAG)
    except json.JSONDecodeError:
      raise Exception("Failed to parse JSON from 'ipfs id' output.")


  @require_ipfs_started
  def __pin_add(self, cid: str) -> str:
    """
    Explicitly pin a CID (and fetch its data) so it appears in the local pinset.
    """
    res = self.__run_command(["ipfs", "pin", "add", cid])
    self.Pd(f"{res}")
    return res  

  
  # Public methods
  
  def add_json(self, data, fn=None, tempfile=False) -> bool:
    """
    Add a JSON object to IPFS.
    """
    try:
      json_data = json.dumps(data)
      if tempfile:
        self.Pd("Using tempfile for JSON")
        with tempfile.NamedTemporaryFile(
          mode='w', suffix='.json', delete=False
        ) as f:
          f.write(json_data)
        fn = f.name
      else:
        fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".json")
        self.Pd(f"Using unique name for JSON: {fn}")
        with open(fn, "w") as f:
          f.write(json_data)
      #end if tempfile
      cid = self.add_file(fn)
      return cid
    except Exception as e:
      self.P(f"Error adding JSON to IPFS: {e}", color='r')
      return None
    
    
  def add_yaml(self, data, fn=None, tempfile=False) -> bool:
    """
    Add a YAML object to IPFS.
    """
    try:
      import yaml
      yaml_data = yaml.dump(data)
      if tempfile:
        self.Pd("Using tempfile for YAML")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
          f.write(yaml_data)
        fn = f.name
      else:
        fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".yaml")
        self.Pd(f"Using unique name for YAML: {fn}")
        with open(fn, "w") as f:
          f.write(yaml_data)
      cid = self.add_file(fn)
      return cid
    except Exception as e:
      self.P(f"Error adding YAML to IPFS: {e}", color='r')
      return None
    
    
  def add_pickle(self, data, fn=None, tempfile=False) -> bool:
    """
    Add a Pickle object to IPFS.
    """
    try:
      import pickle
      if tempfile:
        self.Pd("Using tempfile for Pickle")
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
          pickle.dump(data, f)
        fn = f.name
      else:
        fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".pkl")
        self.Pd(f"Using unique name for pkl: {fn}")
        with open(fn, "wb") as f:
          pickle.dump(data, f)
      cid = self.add_file(fn)
      return cid
    except Exception as e:
      self.P(f"Error adding Pickle to IPFS: {e}", color='r')
      return None


  @require_ipfs_started
  def add_file(self, file_path: str) -> str:
    """
    This method adds a file to IPFS and returns the CID of the wrapped folder.
    
    Parameters
    ----------
    file_path : str
        The path to the file to be added.
    
    Returns
    -------
    str
        The CID of the wrapped folder
      
    """
    assert os.path.isfile(file_path), f"File not found: {file_path}"
    
    output = self.__run_command(["ipfs", "add", "-q", "-w", file_path])
    # "ipfs add -w <file>" typically prints two lines:
    #   added <hash_of_file> <filename>
    #   added <hash_of_wrapped_folder> <foldername?>
    # We want the *last* line's CID (the wrapped folder).
    lines = output.strip().split("\n")
    if not lines:
      raise Exception("No output from 'ipfs add -w -q'")
    folder_cid = lines[-1].strip()
    self.__uploaded_files[folder_cid] = file_path
    # now we pin the folder
    res = self.__pin_add(folder_cid)
    self.P(f"Added file {file_path} as <{folder_cid}>")
    return folder_cid


  @require_ipfs_started
  def get_file(
    self, 
    cid: str, 
    local_folder: str = None, 
    timeout: int = None,
    pin=True, 
    raise_on_error: bool = False
  ) -> str:
    """
    Get a file from IPFS by CID and save it to a local folder.
    If no local folder is provided, the default downloads directory is used.
    Returns the full path of the downloaded file.
    
    Parameters
    ----------
    cid : str
        The CID of the file to download.
        
    local_folder : str
        The local folder to save the
        
    timeout : int
        The maximum time to wait for the download to complete.
        Default `None` means the timeout is set by the IPFSCt.TIMEOUT (90s by default)
            
    """
    if pin:
      pin_result = self.__pin_add(cid)
      
    if local_folder is None:
      local_folder = self.__downloads_dir # default downloads directory
      os.makedirs(local_folder, exist_ok=True)
      local_folder = os.path.join(local_folder, cid) # add the CID as a subfolder
      
    self.Pd(f"Downloading file {cid} to {local_folder}")
    start_time = time.time()
    self.__run_command(["ipfs", "get", cid, "-o", local_folder], timeout=timeout)
    elapsed_time = time.time() - start_time
    # now we need to get the file from the folder
    folder_contents = os.listdir(local_folder)
    if len(folder_contents) != 1:
      msg = f"Expected one file in {local_folder}, found {folder_contents}"
      if raise_on_error:
        raise Exception(msg)
      else:
        self.P(msg, color='r')
    # get the full path of the file
    out_local_filename = os.path.join(local_folder, folder_contents[0])
    self.P(f"Downloaded in {elapsed_time:.1f}s <{cid}> to {out_local_filename}")
    self.__downloaded_files[cid] = out_local_filename
    return out_local_filename





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

  

  def maybe_start_ipfs(
    self, 
    base64_swarm_key: str = None, 
    ipfs_relay: str = None
  ) -> bool:
    """
    This method initializes the IPFS repository if needed, connects to a relay, and starts the daemon.
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
      
    
    if not base64_swarm_key or not ipfs_relay:
      self.P("Missing env values EE_SWARM_KEY_CONTENT_BASE64 and EE_IPFS_RELAY.", color='r')
      return False
    
    self.__base64_swarm_key = base64_swarm_key
    self.__ipfs_relay = ipfs_relay
    hidden_base64_swarm_key = base64_swarm_key[:8] + "..." + base64_swarm_key[-8:]
        
    ipfs_home = os.path.join(self.logger.base_folder, ".ipfs/")
    
    os.makedirs(ipfs_home, exist_ok=True)
    self.__ipfs_home = os.path.abspath(ipfs_home)
    os.environ["IPFS_PATH"] = self.__ipfs_home
    
    config_path = os.path.join(self.__ipfs_home, "config")
    swarm_key_path = os.path.join(self.__ipfs_home, "swarm.key")

    msg = f"Starting R1FS <{self.__name}>:"
    msg += f"\n  Relay:    {self.__ipfs_relay}"
    msg += f"\n  Download: {self.__downloads_dir}"
    msg += f"\n  Upload:   {self.__uploads_dir}"
    msg += f"\n  SwarmKey: {hidden_base64_swarm_key}"
    msg += f"\n  Debug:    {self.__debug}"
    msg += f"\n  Repo:     {self.ipfs_home}"
    self.P(msg, color='d')
    

    if not os.path.isfile(config_path):
      # Repository is not initialized; write the swarm key and init.
      try:
        decoded_key = base64.b64decode(base64_swarm_key)
        with open(swarm_key_path, "wb") as f:
          f.write(decoded_key)
        os.chmod(swarm_key_path, 0o600)
        self.P("Swarm key written successfully.", color='g')
      except Exception as e:
        self.P(f"Error writing swarm.key: {e}", color='r')
        return False

      try:
        self.P("Initializing IPFS repository...")
        self.__run_command(["ipfs", "init"])
      except Exception as e:
        self.P(f"Error during IPFS init: {e}", color='r')
        return False
    else:
      self.P(f"IPFS repository already initialized in {config_path}.", color='g')

    try:
      self.P("Removing public IPFS bootstrap nodes...")
      self.__run_command(["ipfs", "bootstrap", "rm", "--all"])
    except Exception as e:
      self.P(f"Error removing bootstrap nodes: {e}", color='r')

    # Check if daemon is already running by attempting to get the node id.
    try:
      # explicit run no get_id
      result = self.__run_command(["ipfs", "id"])
      self.__ipfs_id = json.loads(result)["ID"]
      self.__ipfs_address = json.loads(result)["Addresses"][1]
      self.__ipfs_agent = json.loads(result)["AgentVersion"]
      self.P("IPFS daemon running", color='g')
            
    except Exception:
      self.Pd("ipfs id failed, starting daemon...")
      try:
        self.__set_reprovider_interval()
        self.__set_relay()
        self.P("Starting IPFS daemon in background...")        
        subprocess.Popen(["ipfs", "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
      except Exception as e:
        self.P(f"Error starting IPFS daemon: {e}", color='r')
        return

    try:
      my_id = self.__get_id()
      assert my_id != ERROR_TAG, "Failed to get IPFS ID."
      msg =  f"Connecting to R1FS relay"
      msg += f"\n  IPFS Home:  {self.ipfs_home}"
      msg += f"\n  IPFS ID:    {my_id}"
      msg += f"\n  IPFS Addr:  {self.__ipfs_address}"
      msg += f"\n  IPFS Agent: {self.__ipfs_agent}"
      msg += f"\n  Relay:      {ipfs_relay}"
      self.P(msg, color='m')
      result = self.__run_command(["ipfs", "swarm", "connect", ipfs_relay])
      relay_ip = ipfs_relay.split("/")[2]
      if "connect" in result.lower() and "success" in result.lower():
        self.P(f"{my_id} connected to: {relay_ip}", color='g', boxed=True)
        self.__ipfs_started = True
      else:
        self.P("Relay connection result did not indicate success.", color='r')
    except Exception as e:
      self.P(f"Error connecting to relay: {e}", color='r')
      
    return self.ipfs_started
    
  
  def check_ipfs_warmed(self) -> bool:
    """
    1) Checks if we appear to be connected to the relay at all.
    2) If so, checks how long we've been connected. If it's >= min_connection_age, returns True.
    """
    if not self.ipfs_started:
      # Not ipfs_started no need for further checks
      return False
    connected = self._check_and_record_relay_connection()
    if not connected:
      # Not connected to the relay yet
      
      return False    
    # If we have a connection, see how old it is:
    connection_age = time.time() - self.connected_at
    is_connection_aged =  connection_age >= self.__min_connection_age  
    if is_connection_aged:
      self.Pd(f"IPFS connection age {connection_age:.1f}s, >= {self.__min_connection_age}s")
    else:
      self.Pd(f"IPFS connection age {connection_age:.1f}s, < {self.__min_connection_age}s")
    return is_connection_aged
  
  @property
  def is_ipfs_warmed(self) -> bool:
    """
    Check if IPFS is warmed up (connected to the relay and has been for a while).
    """
    return self.check_ipfs_warmed()  