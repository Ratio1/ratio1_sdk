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

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_SECRET = "ratio1"

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
      
      self.maybe_start_ipfs(
        base64_swarm_key=self.__base64_swarm_key,
        ipfs_relay=self.__ipfs_relay,
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
    
    def _set_debug(self):
      """
      Force debug mode on.
      """
      self.__debug = True
      return
    
    def _hash_secret(self, secret: str) -> bytes:
      # Convert text to bytes, then hash with SHA-256 => 32-byte key
      return hashlib.sha256(secret.encode("utf-8")).digest()  
    
    
  # Public properties
  if True:
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
          self.Pd(f"Swarm peers:\n{json.dumps(peer_lines, indent=4)}")
          self.__peers = peer_lines
        else:
          self.__peers = []
        # found = len(self.__peers) > 0
      except Exception as e:
        self.P(f"Error getting swarm peers: {e}", color='r')
      return peer_lines


    def _check_and_record_relay_connection(self, max_check_age : int = 3600, debug=False) -> bool:
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
            log_func(f"Relay check  #{self.__relay_check_cnt}: Swarm peers:\n{json.dumps(peer_lines, indent=4)}")
            self.__peers = peer_lines
            for line in peer_lines:
              # If the line contains the relay peer ID, we consider ourselves connected:
              if self.__ipfs_relay in line:
                # Record the time if not already set
                relay_found = True
                log_func(f"Relay check #{self.__relay_check_cnt}: Relay ok: {line.strip()}")
              #end if
            #end for
            # now reset the connected_at time if we found the relay peer
            if relay_found:
              self.__connected_at = time.time() # set self.connected_at
              str_connected = self.logger.time_to_str(self.connected_at)
              self.P(f"Relay check #{self.__relay_check_cnt}: Connected to relay peer recorded at {str_connected}.")
            else:
              self.__connected_at = None
              log_func(f"Relay check #{self.__relay_check_cnt}: Relay peer not found in swarm peers: {self.__ipfs_relay}", color='r')
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
        output, errors
      return output
    

    def __get_id(self) -> str:
      """
      Get the IPFS peer ID via 'ipfs id' (JSON output).
      Returns the 'ID' field as a string.
      """
      self.__ipfs_address = None
      output = self.__run_command(["ipfs", "id"]) # this will raise an exception if the command fails
      try:
        data = json.loads(output)
        self.__ipfs_id_result = data
        self.__ipfs_id = data.get("ID", ERROR_TAG)
        self.__ipfs_agent = data.get("AgentVersion", ERROR_TAG)
        addrs = data.get("Addresses", [])
        if not addrs:
          self.__ipfs_address = None
        else:
          self.__ipfs_address = addrs[1] if len(addrs) > 1 else addrs[0] if len(addrs) else ERROR_TAG
      except json.JSONDecodeError:
        raise Exception("Failed to parse JSON from 'ipfs id' output.")
      except Exception as e:
        msg = f"Error getting IPFS ID: {e}. `ipfs id`:\n{data}"
        self.P(msg, color='r')
        raise Exception(f"Error getting IPFS ID: {e}") from e
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
      tempfile=False, 
      show_logs=True,
      raise_on_error=False,
    ) -> bool:
      """
      Add a JSON object to IPFS.
      """
      try:
        json_data = json.dumps(data)
        if tempfile:
          if show_logs:
            self.Pd("Using tempfile for JSON")
          with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
          ) as f:
            f.write(json_data)
          fn = f.name
        else:
          fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".json")
          if show_logs:
            self.Pd(f"Using unique name for JSON: {fn}")
          with open(fn, "w") as f:
            f.write(json_data)
        #end if tempfile
        cid = self.add_file(
          file_path=fn, secret=secret, show_logs=show_logs,
          raise_on_error=raise_on_error
        )
        return cid
      except Exception as e:
        if show_logs:
          self.P(f"Error adding JSON to IPFS: {e}", color='r')
        return None
      
      
    def add_yaml(
      self, 
      data, 
      fn=None, 
      secret: str = None,
      tempfile=False, 
      show_logs=True,
      raise_on_error=False,
    ) -> bool:
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
          file_path=fn, secret=secret, show_logs=show_logs,
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
      tempfile=False, 
      show_logs=True,
      raise_on_error=False,
    ) -> bool:
      """
      Add a Pickle object to IPFS.
      """
      try:
        import pickle
        if tempfile:
          if show_logs:
            self.Pd("Using tempfile for Pickle")
          with tempfile.NamedTemporaryFile(mode='wb', suffix='.pkl', delete=False) as f:
            pickle.dump(data, f)
          fn = f.name
        else:
          fn = self._get_unique_or_complete_upload_name(fn=fn, suffix=".pkl")
          if show_logs:
            self.Pd(f"Using unique name for pkl: {fn}")
          with open(fn, "wb") as f:
            pickle.dump(data, f)
        cid = self.add_file(
          file_path=fn, secret=secret, show_logs=show_logs,
          raise_on_error=raise_on_error
        )
        return cid
      except Exception as e:
        if show_logs:
          self.P(f"Error adding Pickle to IPFS: {e}", color='r')
        return None


    @require_ipfs_started
    def add_file(
      self,
      file_path: str,
      secret: str = None,
      raise_on_error: bool = False,
      show_logs: bool = True
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
      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
      
      if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

      key = self._hash_secret(secret)  # mandatory passphrase
      nonce = os.urandom(12)           # recommended for GCM
      original_basename = os.path.basename(file_path)

      # JSON metadata storing the original filename
      meta_dict = {"filename": original_basename}
      meta_bytes = json.dumps(meta_dict).encode("utf-8")

      tmp_cipher_path = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex + ".bin")
      
      folder_cid = None
      start_time = time.time()
      try:
        encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()

        chunk_size = 1024 * 1024  # 1 MB chunks
        with open(file_path, "rb") as fin, open(tmp_cipher_path, "wb") as fout:
          # [nonce][4-byte-len][metadata][ciphertext][16-byte GCM tag]
          fout.write(nonce)
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
      elapsed_time = time.time() - start_time
      # Cleanup temp file
      os.remove(tmp_cipher_path)
      
      if folder_cid is not None:
        self.__uploaded_files[folder_cid] = file_path
        # now we pin the folder
        res = self.__pin_add(folder_cid)
        if show_logs:
          self.P(f"Added file {file_path} as <{folder_cid}> in {elapsed_time:.1f}s")      
        #end if show_logs
      #end if folder_cid is not None
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
      show_logs: bool = True
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
      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
        
      key = self._hash_secret(secret)

      if pin:
        pin_result = self.__pin_add(cid)

      if local_folder is None:
        local_folder = self.__downloads_dir # default downloads directory
      
      os.makedirs(local_folder, exist_ok=True)
      
      local_folder = os.path.join(local_folder, cid) # add the CID as a subfolder
      
      # if the folder exists cleanup the content 
      if os.path.exists(local_folder):
        if show_logs:
          files = os.listdir(local_folder)
          self.Pd(f"Cleaning up {local_folder} with {files}")
        #end if show_logs
        shutil.rmtree(local_folder)
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
    
  
  # Start/stop IPFS methods (R1FS API)
  if True:
    
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
          # first delete the repository lock file if it exists
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
          self.__set_relay()
          self.P("Starting IPFS daemon in background...")
          subprocess.Popen(["ipfs", "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        self.P("Getting the IPFS ID...")
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
          self.P("Checking swarm peers...")
          swarm_peers = self._get_swarm_peers()
          self.P(f"Swarm peers:\n {json.dumps(swarm_peers, indent=2)}")
          self._check_and_record_relay_connection(debug=True)
        else:
          self.P("Relay connection result did not indicate success.", color='r')
      except Exception as e:
        self.P(f"Error connecting to relay: {e}", color='r')
      #end try
      return self.ipfs_started    
    
    
if __name__ == '__main__':
  eng = R1FSEngine()