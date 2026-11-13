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
from datetime import datetime, timezone
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
import ipaddress
import signal

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEFAULT_SECRET = "ratio1"
DEFAULT_FILENAME_JSON = "data.json"

# Thread runs the relay self-heal and queue retries in a background pass so they never block a read. The pass is
# guarded by a plain Lock: the reader acquires it and the worker releases it, which an RLock does not allow.
from threading import Lock, RLock, Thread

__VER__ = "0.2.2"

# empirically determined minimum connection age for IPFS relay
DEFAULT_MIN_CONNECTION_AGE = 0 # seconds


class IPFSCt:
  EE_IPFS_RELAY_ENV_KEY = "EE_IPFS_RELAY"
  EE_SWARM_KEY_CONTENT_BASE64_ENV_KEY = "EE_SWARM_KEY_CONTENT_BASE64"
  EE_IPFS_RELAY_API_KEY = "EE_IPFS_RELAY_API"
  EE_IPFS_API_KEY_BASE64_KEY = "EE_IPFS_API_KEY_BASE64"
  EE_IPFS_CERTIFICATE_BASE64_KEY = "EE_IPFS_CERTIFICATE_BASE64"
  # This workaround was introduced to prefer the host-local relay path for
  # containers running on the same machine as the relay. In testing, the local
  # path proved good enough for peer connectivity but not consistently safe for
  # block transfer, so it remains opt-in until a stronger data-plane proof is
  # implemented.
  EE_R1FS_SAMEHOST_RELAY_FIX = "EE_R1FS_SAMEHOST_RELAY_FIX"
  R1FS_DOWNLOADS = "ipfs_downloads"
  R1FS_UPLOADS = "ipfs_uploads"
  CACHE_ROOT = "_local_cache"
  TEMP_DOWNLOAD = os.path.join(f"./{CACHE_ROOT}/_output", R1FS_DOWNLOADS)
  TEMP_UPLOAD = os.path.join(f"./{CACHE_ROOT}/_output", R1FS_UPLOADS)
  SAMEHOST_FIX_MARKER = ".r1fs_samehost_relay_fix.json"
  SAMEHOST_FIX_NEGATIVE_TTL_SECONDS = 3600
  RELAY_PIN_TIMEOUT_SECONDS = 15
  RELAY_PIN_RETRY_COUNT = 3
  RELAY_PIN_RETRY_BACKOFF_SECONDS = 2
  RELAY_RETRY_QUEUE_LIMIT = 256
  # Most CIDs that wait for a relay heal at once. The background pass heals all of them before every queued
  # publication, and a heal of a CID the relay cannot fetch costs two pin/add requests (2 x 15 s + 2 s), so 32
  # bounds that wait to about 17 min under a flood of failing reads (256 would allow over 2 h). A heal refused
  # because the set is full is asked again by the next failed read of its CID.
  RELAY_HEAL_PENDING_LIMIT = 32
  # Kubo's error for `pin rm` of a CID with no direct or recursive pin (boxo's pinner ErrNotPinned): the CLI prints
  # it on stderr as "Error: not pinned or pinned indirectly", the relay's HTTP API returns it as its error message.
  NOT_PINNED_ERROR = "not pinned or pinned indirectly"

  TIMEOUT = 90 # seconds
  # The reprovide operation is very heavy and should be done infrequently.
  # The kubo documentation advises on 22h. This was previously on 1m and will be
  # increased to 10h to reduce the load on the relay(s).
  REPROVIDER = "10h"
  REPROVIDER_STRATEGY = "pinned+mfs"


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
  
  # __new__ holds this lock while constructing and starting the singleton instance.
  # Startup may re-enter code paths that need the same class-level guard, so this
  # must stay re-entrant to avoid self-deadlocking the initializing thread.
  _lock: RLock = RLock()
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

      Called once per instance name by ``__new__`` (under the class lock) to set the
      private state of the singleton and then run ``startup()``, which prepares the
      download/upload folders and calls ``maybe_start_ipfs`` to start IPFS and attach
      it to the relay (connection settings left as ``None`` are read from environment
      variables there). Besides the connection settings, it creates the relay bookkeeping: the retry
      queue of CIDs the relay has not accepted yet, the per-CID publication status,
      ``__relay_heal_pending``, the CIDs whose reads failed and that still wait for a
      relay heal, and ``__relay_busy``, the lock that lets only one background relay
      pass run at a time (``get_file`` hands its relay work to that pass instead of
      doing it itself). It also starts the two counters of
      ``__report_relay_data_path``: the failed reads of CIDs the relay had accepted,
      and the time its last line was printed; the per-kind counters of
      ``__report_rate_limited``; and ``__relay_in_flight``, the relay request the
      background pass is sending at the moment, which ``unpin_file`` marks when it
      unpins that CID meanwhile.

      Parameters
      ----------
      name : str, optional
          Instance name; one engine exists per name. Default ``"default"``.
      logger : any, optional
          Object with a ``P`` method used for logging. A ``SimpleLogger`` that
          prints to stdout is used when ``None``.
      downloads_dir : str, optional
          Folder for downloaded files. Resolved in ``startup()`` from the logger
          output folder, or a local cache folder, when ``None``.
      uploads_dir : str, optional
          Folder for files staged for upload. Resolved like ``downloads_dir``.
      base64_swarm_key : str, optional
          Base64-encoded private swarm key, passed to ``maybe_start_ipfs``.
      ipfs_relay : str, optional
          Relay multiaddr, passed to ``maybe_start_ipfs``.
      ipfs_relay_api : str, optional
          Relay HTTP API endpoint used for relay pin/add and pin/rm requests.
      ipfs_api_key_username : str, optional
          Username for the relay API basic auth.
      ipfs_api_key_password : str, optional
          Password for the relay API basic auth.
      ipfs_certificate_path : str, optional
          TLS certificate file used to verify the relay API.
      min_connection_age : int, optional
          Stored on the instance only; the warm-up it once controlled is no
          longer used (see ``_set_min_connection_age``).
      debug : bool, optional
          When ``True``, ``Pd`` debug logs are emitted. Default ``False``.

      Returns
      -------
      None

      Examples
      --------
      >>> # Not called directly; constructing the engine runs it once per name.
      >>> engine = R1FSEngine(name="default", debug=False)
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
      self.__peers = []
      self.__samehost_fix_attempted = False
      self.__relay_retry_queue = {}
      # Only one background relay pass (self-heal plus queue retry) runs at a time; a read that finds
      # it held does not wait and starts no pass (its heal, if any, waits in __relay_heal_pending).
      # A plain Lock because the worker thread releases it.
      self.__relay_busy = Lock()
      # CIDs whose reads failed and that the relay has not been asked to fetch yet. A read adds its CID here
      # before it tries the pass lock, so a heal asked for while a pass runs is kept: that pass heals it before
      # its next queued publication or before it ends, and one added after its last look waits for the next pass.
      self.__relay_heal_pending = set()
      self.__relay_publication_status = {}
      # Failed reads of CIDs the relay had accepted before the read, since start; the printed line carries it.
      self.__relay_data_failures = 0
      # time.time() of the last such line printed; 0 lets the first one print at once.
      self.__relay_data_logged_at = 0
      # Per kind of event, [events since start, time.time() of the last line]: see __report_rate_limited.
      self.__rate_limited_reports = {}
      # The relay pin/add the background pass is sending, as [cid, unpinned], set just before the pass reads the CID's
      # queue entry or takes it from the heal set. A queued publication clears it when its request is over; a heal's
      # token, and that of a CID the pass skipped, stays until the next heal replaces it or the heal round ends and
      # clears it, so a finished request can sit here briefly. unpin_file sets unpinned when it tells the relay to
      # unpin that CID meanwhile (with unpin_remote=False nothing is marked); the request then records nothing, is
      # not queued again and undoes a pin that got through. It lives for one request only: no list of unpinned CIDs
      # is kept, since the same content uploaded again later has the same CID and must be healed and published as
      # usual.
      self.__relay_in_flight = None
      self.__relay_config_warning_flags = set()
      
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
    def relay_publication_status(self):
      """
      Return the latest local-versus-relay publication state for known CIDs.

      Returns
      -------
      dict
          Mapping of CID to a status dictionary describing local upload and
          relay-publication state.
      """
      return self.__relay_publication_status
        
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

    def __refuse_invalid_cid(self, cid, raise_on_error: bool = False, show_logs: bool = True) -> bool:
      """
      Refuse a value that is not a bare CID, through the caller's error convention.

      A bare CID is a non-empty string of at most 255 ASCII letters and digits, the form
      ``ipfs add`` prints (CIDv0 ``Qm...`` in base58btc, 46 characters; CIDv1 in base32 or
      base36). Such a value has no ``/``, ``.``, space, ``-`` prefix, ``&`` or ``?``:
      joined to a folder it names a direct child of that folder, on an ``ipfs`` command
      line it is one CID argument, and in a relay request it is one parameter value. The
      255 is the longest folder name (NAME_MAX), and ``get_file`` makes the CID a folder
      name, so a longer value can never be read here. The public methods that hand a CID
      to the filesystem, to an ``ipfs`` command line or to the relay call this first:
      ``get_file``, ``delete_file``, ``unpin_file``, ``is_pinned``, ``is_cid_available``
      and ``cleanup_downloads`` (``get_json``, ``get_pickle`` and ``delete_files`` go
      through them).

      Parameters
      ----------
      cid : any
          The value the caller passed as a CID.
      raise_on_error : bool, optional
          True raises ``ValueError`` for a refused value; False (default) returns True
          and logs the value in red (``show_logs`` says when it is not logged).
      show_logs : bool, optional
          The caller's ``show_logs``. It gates the red line only for ``None`` and ``""``;
          any other refused value is a caller bug or an attack and is logged whatever
          ``show_logs`` is. Default True.

      Returns
      -------
      bool
          False when ``cid`` is a bare CID. True when it was refused (logged in red,
          except a ``None`` or ``""`` with ``show_logs`` False); the caller then
          returns its own failure value.

      Raises
      ------
      ValueError
          When ``cid`` is refused and ``raise_on_error`` is True. Nothing is logged then.

      Notes
      -----
      ``get_file`` and ``delete_file`` pass ``None`` and ``""`` here too, and refuse them
      as they always did. ``unpin_file`` refuses them with its own message first, and
      ``is_pinned``, ``is_cid_available`` and ``cleanup_downloads`` do not call this for
      them, so what those methods do with ``None`` or ``""`` is unchanged. The refused
      value is shown cut to its first 100 characters, so a huge value gives a short line.

      Examples
      --------
      >>> # in get_file, before the CID is joined to the downloads folder
      >>> if self.__refuse_invalid_cid(cid, raise_on_error=raise_on_error, show_logs=show_logs):
      ...   return None
      """
      # A CID becomes a folder name under the downloads folder, so more than 255 characters (NAME_MAX) can never be a
      # CID this node reads; the bound also keeps such values out of `ipfs` command lines, relay requests and the
      # upload status.
      if isinstance(cid, str) and cid.isascii() and cid.isalnum() and len(cid) <= 255:
        # A bare CID: nothing to refuse, the caller goes on.
        return False
      # Name the refused value in the message, so the log or the ValueError shows what the caller sent; cut to 100
      # characters, so a huge value does not make a line as long as itself.
      msg = f"Invalid CID {cid!r:.100}: a CID must be a non-empty string of at most 255 ASCII letters and digits"
      if raise_on_error:
        # The caller asked for exceptions: the ValueError carries the message to it.
        raise ValueError(msg)
      # A value that is set but is not a CID is a caller bug or an attack, so it is said in red whatever show_logs
      # is; a None or empty CID keeps the caller's show_logs, as before.
      if show_logs or cid not in (None, ""):
        self.P(msg, color='r')
      # Refused: the caller returns its own failure value.
      return True

    def __refuse_unplain_name(self, name, raise_on_error: bool = False) -> bool:
      """
      Refuse a file name that is not a plain file name, through the caller's error convention.

      A plain file name is a non-empty string with no path part (``os.path.basename``
      returns it unchanged, so it has no ``/``) that is not ``.`` or ``..``. Joined to a
      folder, it names a file directly inside that folder: never an absolute path, the
      folder itself or its parent. ``get_file`` checks the name stored in the downloaded
      object's metadata with it; ``add_json``, ``add_pickle``, ``calculate_json_cid`` and
      ``calculate_pickle_cid`` check the caller's ``fn`` before anything is written.

      Parameters
      ----------
      name : any
          The file name to check.
      raise_on_error : bool, optional
          True raises ``ValueError`` for a refused name; False (default) logs it in red,
          whatever ``show_logs`` the caller has, and returns True.

      Returns
      -------
      bool
          False when ``name`` is a plain file name. True when it was refused and logged;
          the caller then returns its own failure value.

      Raises
      ------
      ValueError
          When ``name`` is refused and ``raise_on_error`` is True. Nothing is logged then.

      Notes
      -----
      The refused name is shown cut to its first 100 characters, so a huge value gives a
      short line.

      Examples
      --------
      >>> self.__refuse_unplain_name("data.json")
      False
      >>> # in add_json, before the name is joined to its temporary folder
      >>> if fn is not None and self.__refuse_unplain_name(fn, raise_on_error=raise_on_error):
      ...   return None
      """
      if isinstance(name, str) and name not in ("", ".", "..") and os.path.basename(name) == name:
        # A plain file name: nothing to refuse, the caller goes on.
        return False
      # Name the refused value in the message, so the log or the ValueError shows what the caller sent; cut to 100
      # characters, so a huge value does not make a line as long as itself.
      msg = f"Invalid file name {name!r:.100}: a file name must have no path part and must not be '', '.' or '..'"
      if raise_on_error:
        # The caller asked for exceptions: the ValueError carries the message to it.
        raise ValueError(msg)
      # A name that is not a plain file name is a caller bug or an attack: say it in red whatever show_logs is.
      self.P(msg, color='r')
      # Refused: the caller returns its own failure value.
      return True

    def get_upload_status(self, cid: str) -> dict:
      """
      Return the tracked upload status for one CID.

      Parameters
      ----------
      cid : str
          CID whose status should be returned.

      Returns
      -------
      dict
          A shallow copy of the tracked status. Empty when the CID has not been
          seen by the current process.
      """
      status = self.__relay_publication_status.get(cid, {})
      return dict(status)

    def __utc_now_iso(self) -> str:
      """
      Return the current UTC timestamp in ISO-8601 form.

      Returns
      -------
      str
          Timestamp suffixed with ``Z``.
      """
      return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def __set_upload_status(self, cid: str, **updates):
      """
      Merge new upload-status fields for a CID.

      Parameters
      ----------
      cid : str
          CID whose state is being updated.
      **updates : dict
          Partial state fields to merge into the existing status entry.
      """
      status = dict(self.__relay_publication_status.get(cid, {}))
      status.update(updates)
      status["updated_at"] = self.__utc_now_iso()
      self.__relay_publication_status[cid] = status
      return

    def __warn_missing_relay_api_config(self, context: str, missing_fields: list):
      """
      Emit a one-time warning describing missing relay API configuration.

      Parameters
      ----------
      context : str
          Human-readable operation context such as ``upload`` or
          ``download self-heal``.
      missing_fields : list
          Missing configuration field names.
      """
      missing_key = (context, tuple(sorted(missing_fields)))
      if missing_key in self.__relay_config_warning_flags:
        return
      self.__relay_config_warning_flags.add(missing_key)
      missing = ", ".join(missing_fields)
      self.P(
        f"Relay API configuration incomplete for {context}: missing {missing}. "
        "Local upload/download will continue, but relay publication/self-heal is disabled.",
        color='r'
      )
      return

    def __has_relay_api_config(self, context: str, show_logs: bool = True) -> bool:
      """
      Check whether relay API publication can be attempted safely.

      Parameters
      ----------
      context : str
          Human-readable operation context.
      show_logs : bool, optional
          Whether to emit warnings when configuration is incomplete.

      Returns
      -------
      bool
          ``True`` when the relay API URL and credentials are available.
      """
      missing_fields = []
      if not self.__ipfs_relay_api:
        missing_fields.append(IPFSCt.EE_IPFS_RELAY_API_KEY)
      if not self.__ipfs_api_key_username or not self.__ipfs_api_key_password:
        missing_fields.append(IPFSCt.EE_IPFS_API_KEY_BASE64_KEY)
      if missing_fields and show_logs:
        self.__warn_missing_relay_api_config(context=context, missing_fields=missing_fields)
      return len(missing_fields) == 0

    def __enqueue_relay_retry(self, cid: str, source_path: str = None, reason: str = None):
      """
      Add or refresh a CID in the in-process relay publication retry queue.

      Parameters
      ----------
      cid : str
          CID that still needs relay publication.
      source_path : str, optional
          Local source path when known.
      reason : str, optional
          Last failure description.
      """
      queue_item = dict(self.__relay_retry_queue.get(cid, {}))
      if not queue_item and len(self.__relay_retry_queue) >= IPFSCt.RELAY_RETRY_QUEUE_LIMIT:
        oldest_cid = min(
          self.__relay_retry_queue,
          key=lambda queued_cid: self.__relay_retry_queue[queued_cid].get("queued_at", ""),
        )
        self.__relay_retry_queue.pop(oldest_cid, None)
        self.P(
          f"Relay retry queue full. Dropping oldest queued CID {oldest_cid} to keep space for {cid}.",
          color='r'
        )
      queue_item["cid"] = cid
      if source_path is not None:
        queue_item["source_path"] = source_path
      queue_item["queued_at"] = queue_item.get("queued_at", self.__utc_now_iso())
      queue_item["last_error"] = reason
      queue_item["attempts"] = int(queue_item.get("attempts", 0))
      self.__relay_retry_queue[cid] = queue_item
      self.__set_upload_status(
        cid,
        source_path=queue_item.get("source_path"),
        relay_status="queued",
        relay_published=False,
        relay_queue_attempts=queue_item["attempts"],
        relay_detail=reason,
        relay_queued_at=queue_item["queued_at"],
      )
      return

    def __relay_verify_value(self):
      """
      Resolve the TLS verification argument for relay API requests.

      Returns
      -------
      str | bool
          Certificate path when one is configured, otherwise ``True`` to keep
          requests certificate validation enabled.
      """
      return self.__ipfs_certificate_path if self.__ipfs_certificate_path else True

    def __publish_cid_to_relay(
      self,
      cid: str,
      source_path: str = None,
      context: str = "upload",
      retries: int = None,
      timeout: int = None,
      queue_on_failure: bool = True,
      show_logs: bool = True,
      raise_on_error: bool = False,
      flight: list = None,
    ) -> bool:
      """
      Ask the relay API to pin a CID with bounded retries.

      ``add_file`` calls it on the caller's thread; the background relay pass calls
      it for a queued publication and, through ``__attempt_download_self_heal``, for a
      heal, and then passes ``flight``, the request it shows in ``__relay_in_flight``.

      Parameters
      ----------
      cid : str
          CID to publish to the relay.
      source_path : str, optional
          Local source path when known.
      context : str, optional
          Human-readable context for logs and status updates.
      retries : int, optional
          Number of API attempts. Defaults to
          ``IPFSCt.RELAY_PIN_RETRY_COUNT``.
      timeout : int, optional
          Per-attempt request timeout in seconds. Defaults to
          ``IPFSCt.RELAY_PIN_TIMEOUT_SECONDS``.
      queue_on_failure : bool, optional
          Whether to keep failed publications queued for later retries.
      show_logs : bool, optional
          Whether to emit status logs.
      raise_on_error : bool, optional
          Whether to raise after the final failed attempt.
      flight : list, optional
          ``[cid, unpinned]``, the background pass's token for this request, which
          ``unpin_file`` sets to ``[cid, True]`` when it unpins ``cid`` meanwhile.
          ``None`` (default, ``add_file``) means the request is never marked.

      Returns
      -------
      bool
          ``True`` when the relay accepted the pin request and it was recorded;
          ``False`` when it failed, and also when ``flight`` was marked meanwhile.

      Raises
      ------
      RuntimeError
          After the final failed attempt, when ``raise_on_error`` is True and
          ``flight`` was not marked.

      Notes
      -----
      The request is ``POST <relay api>/api/v0/pin/add`` with ``cid`` passed as the
      ``arg`` query parameter (requests' ``params``), which requests percent-encodes.
      For a bare CID the URL is the one an f-string gave before
      (``.../api/v0/pin/add?arg=<cid>``), so the relay sees the same request; a value
      with ``&`` or ``#`` stays one ``arg`` value instead of adding parameters.

      When ``flight`` is marked, ``unpin_file`` has unpinned the CID on the relay
      while this request ran, and a pin/add that reaches the relay after that
      pin/rm would leave the CID pinned there. So no further attempt is sent, the
      answer is not recorded (no ``published`` or ``failed`` status, no queue entry
      added or removed), the CID is not queued again, and a pin/add the relay
      accepted is undone with one relay pin/rm (``__undo_relay_pin``). The mark is
      read again right after a failed CID is queued: ``unpin_file`` marks before
      its own queue pop, so a mark that comes after the first check is seen there
      or is followed by that pop. When that pin/rm was sent and the CID is pinned
      on this node again by then (the same content uploaded again, whose own relay
      pin/add can have reached the relay before the pin/rm), the CID is published
      once more with this method's defaults; that publication is not tracked, like
      ``add_file``'s. Not undone: a marked pin/add whose attempt got no answer
      (timeout, connection error), since a relay that completes that pin after the
      unpin's pin/rm keeps the CID; and a relay pin/add that ``add_file`` sends on
      another thread at the same time, which is never marked.

      Examples
      --------
      >>> # in add_file, after the local ipfs add
      >>> self.__publish_cid_to_relay(cid=folder_cid, source_path=file_path, context="upload")
      True
      """
      if not self.__has_relay_api_config(context=context, show_logs=show_logs):
        self.__set_upload_status(
          cid,
          source_path=source_path,
          relay_status="not-configured",
          relay_published=False,
          relay_detail="Relay API configuration is missing.",
        )
        return False

      retries = retries or IPFSCt.RELAY_PIN_RETRY_COUNT
      timeout = timeout or IPFSCt.RELAY_PIN_TIMEOUT_SECONDS
      # No CID in the URL text: it goes in params below, which requests percent-encodes, so a value with '&' or
      # '#' cannot add parameters. For a bare CID the relay gets the same URL as before, character for character.
      request_url = f"{self.__ipfs_relay_api}/api/v0/pin/add"
      last_error = None
      for attempt in range(1, retries + 1):
        if flight and flight[1]:
          # Marked by unpin_file before this attempt (before attempt 1, or during or after an earlier one): send no
          # further pin/add (the end of the method records nothing).
          break
        self.__set_upload_status(
          cid,
          source_path=source_path,
          relay_status="publishing",
          relay_published=False,
          relay_attempts=attempt,
        )
        try:
          response = requests.post(
            request_url,
            # The CID as the `arg` query parameter of the relay's pin/add (see request_url above).
            params={"arg": cid},
            auth=HTTPBasicAuth(self.__ipfs_api_key_username, self.__ipfs_api_key_password),
            verify=self.__relay_verify_value(),
            timeout=timeout,
          )
          if response.status_code == 200:
            if flight and flight[1]:
              # unpin_file unpinned the CID while this pin/add ran, so the pin may have reached the relay after its
              # pin/rm: one relay pin/rm undoes it, and nothing is recorded.
              if self.__undo_relay_pin(cid, show_logs=show_logs) and self.is_pinned(cid):
                # Pinned here again while the undo ran (the same content uploaded or read again): its own relay
                # pin/add can have reached the relay before the undo's pin/rm, so ask the relay to pin it once more.
                self.__publish_cid_to_relay(cid=cid, source_path=source_path, context=context, show_logs=show_logs)
              # This marked request is not published: the relay was asked to drop its pin (a publication made
              # just above records its own result).
              return False
            # Success can come from a first-attempt publish or from a later retry
            # of an already-queued CID, so remove any stale queue entry if present.
            self.__relay_retry_queue.pop(cid, None)
            self.__set_upload_status(
              cid,
              source_path=source_path,
              relay_status="published",
              relay_published=True,
              relay_attempts=attempt,
              relay_detail=f"Relay pin/add accepted during {context}.",
              relay_last_success_at=self.__utc_now_iso(),
              relay_queue_attempts=None,
              relay_queued_at=None,
            )
            if show_logs:
              self.P(f"Relay publication succeeded for {cid} during {context} on attempt {attempt}.", color='g')
            return True
          last_error = f"HTTP {response.status_code}: {response.text.strip()}"
        except requests.Timeout as exc:
          last_error = f"timed out after {timeout}s: {exc}"
        except requests.RequestException as exc:
          last_error = str(exc)

        if show_logs:
          self.P(
            f"Relay publication attempt {attempt}/{retries} failed for {cid} during {context}: {last_error}",
            color='r'
          )
        if attempt < retries:
          time.sleep(IPFSCt.RELAY_PIN_RETRY_BACKOFF_SECONDS * attempt)

      if flight and flight[1]:
        # Unpinned while the request ran: the failure is not recorded and the CID is not queued again.
        return False
      if queue_on_failure:
        self.__enqueue_relay_retry(cid=cid, source_path=source_path, reason=last_error)
        if flight and flight[1]:
          # Marked between the check above and the enqueue: take the CID out again. A later mark comes before
          # unpin_file's own queue pop, which then removes it.
          self.__relay_retry_queue.pop(cid, None)
      else:
        self.__set_upload_status(
          cid,
          source_path=source_path,
          relay_status="failed",
          relay_published=False,
          relay_detail=last_error,
        )
      if raise_on_error:
        raise RuntimeError(f"Failed relay publication for {cid} during {context}: {last_error}")
      return False

    def __undo_relay_pin(self, cid: str, show_logs: bool = True):
      """
      Send one relay pin/rm for a CID unpinned while the background pass pinned it on the relay.

      ``__publish_cid_to_relay`` calls this when the relay accepted a pin/add of
      ``cid`` that ``unpin_file`` had marked while it ran: that pin can have reached
      the relay after the unpin's own relay pin/rm and would leave the CID pinned
      there. The request is the one ``unpin_file`` sends (pin/rm, the CID as the
      ``arg`` parameter, ``IPFSCt.RELAY_PIN_TIMEOUT_SECONDS`` timeout).

      Parameters
      ----------
      cid : str
          CID whose relay pin is undone.
      show_logs : bool, optional
          Whether a successful undo is logged. A failed one is logged in red
          whatever ``show_logs`` is. Default ``True``.

      Returns
      -------
      bool
          True when the pin/rm was sent, whatever the relay answered; False when
          nothing was sent because ``cid`` is pinned on this node again.

      Notes
      -----
      Nothing is sent when ``cid`` is pinned on this node again by then (uploaded or
      read again since the unpin): this node then wants it, and the relay keeps the
      pin. Kubo's "not pinned" answer counts as done, since the relay holds no pin
      of the CID either way. The CID can be pinned here again after that check, and
      the relay pin/add of that upload can reach the relay before this pin/rm; the
      caller therefore checks again when True is returned and publishes the CID once
      more if it is pinned here by then.

      Examples
      --------
      >>> # in __publish_cid_to_relay, when a marked pin/add got HTTP 200
      >>> self.__undo_relay_pin(cid, show_logs=show_logs)
      True
      """
      if self.is_pinned(cid):
        # Pinned here again since the unpin (uploaded or read again under the same CID): keep the relay pin.
        return False
      try:
        # The relay pin/rm of unpin_file, bounded the same way.
        response = requests.post(
          f"{self.__ipfs_relay_api}/api/v0/pin/rm",
          # The CID as the `arg` query parameter, as unpin_file sends it.
          params={"arg": cid},
          auth=HTTPBasicAuth(self.__ipfs_api_key_username, self.__ipfs_api_key_password),
          verify=self.__relay_verify_value(),
          timeout=IPFSCt.RELAY_PIN_TIMEOUT_SECONDS,
        )
        if response.status_code == 200 or IPFSCt.NOT_PINNED_ERROR in response.text:
          if show_logs:
            self.P(f"Relay pin of {cid}, unpinned while the relay pinned it, undone: HTTP {response.status_code}.")
          # Sent and done: the caller checks whether the CID was pinned here again meanwhile.
          return True
        # Refused: the relay may still hold the pin; said below.
        error = f"HTTP {response.status_code}: {response.text.strip()}"
      except requests.RequestException as exc:
        # No answer: the relay may still hold the pin; said below.
        error = str(exc)
      self.P(f"Relay pin/rm to undo the pin of {cid}, unpinned while the relay pinned it, failed: {error}", color='r')
      # Sent, though it may not have reached the relay: the caller still checks whether the CID is wanted again.
      return True

    def __retry_queued_relay_publications(self, context: str, show_logs: bool = True):
      """
      Retry any queued relay publications.

      Each queued CID gets its attempt counter bumped and goes through
      ``__publish_cid_to_relay`` again with the default retries and timeout; a CID
      the relay still does not accept stays queued.
      Reads no longer call this before their get: it runs only in the background
      relay pass (``__relay_in_background``), so the time it takes does not count
      against any read.
      The CIDs are taken from a snapshot of the queue, and each entry is read again
      when its turn comes: a CID that has left the queue by then (unpinned by
      ``unpin_file``, published, or evicted) is skipped. The attempt is counted on
      the queued entry itself, so nothing is written back that could return such a
      CID to the queue. Each CID is shown in ``__relay_in_flight`` from just before
      its entry is read until its publication is over: when ``unpin_file`` unpins
      that CID on the relay meanwhile, no further attempt is sent, a failure is not
      queued again, nothing is recorded, and a pin the relay accepted is undone with
      one relay pin/rm (see ``__publish_cid_to_relay``). Before each publication,
      the CIDs in ``__relay_heal_pending`` (reads that failed) are healed first.

      Parameters
      ----------
      context : str
          Human-readable trigger for the retry pass.
      show_logs : bool, optional
          Whether to emit logs for queue processing.

      Returns
      -------
      None

      Examples
      --------
      >>> # on the background "r1fs-relay" thread, inside work() of __relay_in_background
      >>> self.__retry_queued_relay_publications(context="background pass", show_logs=False)
      """
      if not self.__relay_retry_queue:
        return
      # The CIDs queued now; each entry is read again at its turn, so only the names are kept.
      queued_cids = list(self.__relay_retry_queue)
      if show_logs:
        self.P(f"Retrying {len(queued_cids)} queued relay publication(s) before {context}.", color='m')
      # Reads no longer run this drain on their own thread: it runs only in the background
      # "r1fs-relay" pass (see __relay_in_background), so a large queue lengthens that pass, not a read.
      for cid in queued_cids:
        # Heal the CIDs whose reads failed before the next publication, so a long backlog does not hold
        # their heals until the pass ends.
        self.__heal_remembered_cids(show_logs=show_logs)
        # Show unpin_file this publication before its queue entry is read: an unpin drops the entry before it looks
        # here, so either the read below finds no entry or the unpin finds this request and marks it. A skipped
        # CID's token is replaced or cleared by the heals that come next.
        flight = self.__relay_in_flight = [cid, False]
        # Read the live entry, not a snapshot copy: a CID that left the queue meanwhile (unpinned,
        # published or evicted) gets None here and is skipped.
        refreshed_item = self.__relay_retry_queue.get(cid)
        if refreshed_item is None:
          continue
        # Count the attempt on the queued entry itself. Writing a changed copy back, as before, returned a
        # CID to the queue when it had been unpinned between the read above and the write.
        refreshed_item["attempts"] = int(refreshed_item.get("attempts", 0)) + 1
        self.__set_upload_status(
          cid,
          source_path=refreshed_item.get("source_path"),
          relay_status="retrying",
          relay_published=False,
          relay_queue_attempts=refreshed_item["attempts"],
          relay_detail=refreshed_item.get("last_error"),
        )
        self.__publish_cid_to_relay(
          cid=cid,
          source_path=refreshed_item.get("source_path"),
          context=f"retry queue drain ({context})",
          queue_on_failure=True,
          show_logs=show_logs,
          raise_on_error=False,
          # Marked by unpin_file meanwhile: no further attempt, no re-queue, a pin that got through undone.
          flight=flight,
        )
        # The request is over: nothing of this pass is in flight until its next request.
        self.__relay_in_flight = None
      return

    def __heal_remembered_cids(self, show_logs: bool = True):
      """
      Ask the relay to fetch the CIDs whose reads failed.

      Runs on the background relay pass only. It heals the CIDs that are in
      ``__relay_heal_pending`` when it is called and no others: a CID that a read adds
      while these heals run waits for the next call. One call therefore does a bounded
      amount of work, and reads that keep failing cannot keep the pass from its queued
      publications or from ending. Each CID is taken out of the set just before its
      heal; a CID that has left the set since the snapshot (``unpin_file`` drops it)
      is skipped, so an unpin made while earlier heals of the snapshot run is not
      undone by a relay pin/add.

      Parameters
      ----------
      show_logs : bool, optional
          Whether the heals emit logs. Default ``True``.

      Returns
      -------
      None

      Notes
      -----
      Taking a CID out of the set and ``unpin_file`` dropping it are both single set
      operations, so exactly one of them wins: either the unpin comes first and the
      heal is skipped, or the heal has already started. Each heal is shown in
      ``__relay_in_flight`` before its CID is taken out, and ``unpin_file`` drops the
      CID from the set before it looks there, so an unpin that tells the relay
      either makes the heal skip or marks it; a marked heal records nothing and
      undoes a pin that got through (see ``__attempt_download_self_heal``). The slot
      is cleared when the snapshot is done.

      Examples
      --------
      >>> # on the background "r1fs-relay" thread
      >>> self.__heal_remembered_cids(show_logs=False)
      """
      # A snapshot of the set: what reads add from here on is left for the next call.
      for cid in list(self.__relay_heal_pending):
        # Show unpin_file this heal before the CID is taken from the set: an unpin drops the CID from the set before
        # it looks here, so either the remove below fails or the unpin finds this request and marks it.
        flight = self.__relay_in_flight = [cid, False]
        try:
          # Take the CID out before its heal, so a read of it that fails during the heal can ask once more.
          # remove (not discard) fails when unpin_file dropped the CID after the snapshot: the CID is then
          # skipped instead of being pinned on the relay again by the heal.
          self.__relay_heal_pending.remove(cid)
        except KeyError:
          continue
        # Ask the relay to fetch it, so a later read can find it.
        self.__attempt_download_self_heal(cid=cid, flight=flight, show_logs=show_logs)
      # The heals are over: nothing of this pass is in flight now (a skipped CID left its token here).
      self.__relay_in_flight = None
      return

    def __attempt_download_self_heal(self, cid: str, flight: list, show_logs: bool = True) -> bool:
      """
      Ask the relay to fetch a CID whose read failed, so that a later read can find it.

      Sends a relay pin/add for the CID (2 attempts with an
      ``IPFSCt.RELAY_PIN_TIMEOUT_SECONDS`` request timeout, not queued on failure) so
      the relay pulls the data and a later read can find it. It is called only from
      the background relay pass (``__relay_in_background``) after a failed
      ``ipfs get``; the read that failed is not repeated, only later reads benefit.
      It no longer drains the relay retry queue itself. The background pass calls it
      for every CID in ``__relay_heal_pending``: at the start of the pass, before each
      queued publication and before the pass ends, so a heal asked for while a pass
      runs does not wait for the whole backlog.

      Parameters
      ----------
      cid : str
          CID whose ``ipfs get`` failed locally.
      flight : list
          ``[cid, unpinned]``, the token ``__heal_remembered_cids`` shows in
          ``__relay_in_flight`` for this heal; ``unpin_file`` marks it when it
          unpins the CID while the heal runs.
      show_logs : bool, optional
          Whether to emit logs. The final failure of the heal is logged in red
          whatever it is.

      Returns
      -------
      bool
          ``True`` when the relay accepted the self-heal request; ``False`` when it
          failed or when ``unpin_file`` unpinned the CID while it ran.

      Notes
      -----
      When ``unpin_file`` unpins the CID on the relay while the heal runs (``flight``
      marked), the heal records nothing and a pin the relay accepted is undone with
      one relay pin/rm (see ``__publish_cid_to_relay``); that is not a failed heal.
      A heal that fails for good (the relay refused it, did not answer, or its API is
      not configured) is logged in red with the reason whatever ``show_logs`` is:
      most reads pass ``show_logs=False``, which left a relay that is down or
      refusing silent. During a relay outage every failed read ends here, so the line
      is printed at most once per 600 s with the count since start
      (``__report_rate_limited``). A successful heal logs as before.

      Examples
      --------
      >>> # on the background "r1fs-relay" thread, after a read of cid failed
      >>> self.__attempt_download_self_heal(cid=cid, flight=[cid, False], show_logs=False)
      True
      """
      # Ask the relay to fetch the CID, so a later read can find it.
      healed = self.__publish_cid_to_relay(
        cid=cid,
        source_path=None,
        context=f"download self-heal for {cid}",
        retries=2,
        timeout=IPFSCt.RELAY_PIN_TIMEOUT_SECONDS,
        queue_on_failure=False,
        show_logs=show_logs,
        raise_on_error=False,
        # Marked by unpin_file meanwhile: nothing recorded, a pin that got through undone.
        flight=flight,
      )
      if not healed and not flight[1]:
        # A heal that failed for good, said in red whatever show_logs is (most reads pass False), at most once per
        # 600 s. The reason is in the status the failed request wrote; it is gone only when an unpin of this CID
        # ended just now, and the line then says None.
        self.__report_rate_limited(
          "relay heal failed", f"Relay heal of {cid} failed: {self.get_upload_status(cid).get('relay_detail')}"
        )
      # The caller gets whether the relay accepted the heal.
      return healed

    def __relay_in_background(self, heal_cid: str = None, show_logs: bool = True):
      """
      Off the caller's thread, one pass at a time: ask the relay to fetch `heal_cid`, then retry queued publications.

      ``get_file`` calls this once after every ``ipfs get``, failed or not. Relay API
      calls are slow when the relay is busy or hung: with the default settings each
      queued CID costs three 15 s request timeouts plus 2 s and 4 s of backoff (51 s)
      and the self-heal two timeouts plus 2 s (32 s); a requests timeout limits each
      connect or read, not the whole call, so it can take longer. Before this change
      that work ran on the reader's thread, outside its timeout; now it runs on a
      daemon thread named ``"r1fs-relay"``, so it no longer adds to a read's time.
      Nothing starts when no CID waits for a heal and the retry queue is empty, and
      only one pass runs at a time: when ``__relay_busy`` is already held this call
      returns instead of waiting.

      Parameters
      ----------
      heal_cid : str, optional
          CID whose ``ipfs get`` just failed; it is added to ``__relay_heal_pending``
          and the relay is asked to fetch it so a later read can find it, unless the
          set is full (see Notes). ``None`` after a successful get, in which case the
          pass heals only CIDs already remembered and retries the queued
          publications.
      show_logs : bool, optional
          Whether the background pass emits logs. Default ``True``.

      Returns
      -------
      None
          Returns without waiting for the relay; the relay work happens on the
          background thread.

      Notes
      -----
      ``heal_cid`` is remembered before the pass lock is tried, so a heal asked for
      while a pass runs is not dropped: the running pass heals the remembered CIDs
      before each queued publication and once more before it ends. A heal added
      after the pass's last look and before it frees the lock waits in the set
      until the next call, from any read, starts a pass. A remembered heal is
      dropped when ``unpin_file`` unpins its CID before the pass reaches it.
      At most ``IPFSCt.RELAY_HEAL_PENDING_LIMIT`` CIDs wait: the pass heals all of
      them before every queued publication, so failing reads must not grow the set
      without end. When it is full, a new ``heal_cid`` is not remembered (the waiting
      heals keep their turn, and the CID's next failed read asks again) and this is
      logged in red whatever ``show_logs`` is, at most once per 600 s with the count
      since start, since a flood of failed reads would otherwise print a line per
      read (``__report_rate_limited``). A CID that already waits is not refused.
      Reads on several threads at once can overshoot the limit by a few CIDs.
      When the background thread cannot be started (for example the thread limit of
      the container is reached), the failure is logged in red, the pass lock is
      freed and ``heal_cid`` stays remembered for the next pass. The read that
      called this is not failed by it: its own result does not depend on the relay.

      Examples
      --------
      >>> # in get_file, right after the ipfs get
      >>> self.__relay_in_background(heal_cid=cid if download_error else None, show_logs=show_logs)
      """
      if (heal_cid and heal_cid not in self.__relay_heal_pending
          and len(self.__relay_heal_pending) >= IPFSCt.RELAY_HEAL_PENDING_LIMIT):
        # Full: refuse the new heal, so the waiting ones keep their turn; its next failed read asks again. A
        # rate-limited red line, since a flood of failed reads would otherwise print one per read.
        self.__report_rate_limited(
          "relay heal set full",
          f"Relay heal set full ({IPFSCt.RELAY_HEAL_PENDING_LIMIT} CIDs wait): {heal_cid} is not remembered for a "
          f"relay heal; its next failed read asks again"
        )
      elif heal_cid:
        # Remember the heal before trying the pass lock: when a pass is already running, that pass heals it
        # instead of the heal being dropped.
        self.__relay_heal_pending.add(heal_cid)
      if not (self.__relay_heal_pending or self.__relay_retry_queue) or not self.__relay_busy.acquire(blocking=False):
        return
      def work():
        """
        Run one relay pass on the background thread and always free the pass lock.

        Retries every queued relay publication, healing the CIDs whose reads failed
        before each one, then heals the CIDs that are remembered at that moment (all
        of them when the queue was empty, otherwise those added since the heal round
        before the last queued CID took its snapshot). The ``finally`` releases
        ``__relay_busy`` even when a step raises, so a later read can start a new
        pass. It takes no arguments: ``show_logs`` comes from the enclosing
        ``__relay_in_background`` call.

        Returns
        -------
        None

        Examples
        --------
        >>> # started by __relay_in_background on its own thread
        >>> Thread(target=work, name="r1fs-relay", daemon=True).start()
        """
        try:
          # Retry the CIDs the relay has not accepted yet; this drain used to run on the reader's thread
          # before every get. It heals the remembered CIDs before each publication, so a long retry
          # backlog does not hold a heal back.
          self.__retry_queued_relay_publications(context="background pass", show_logs=show_logs)
          # Heal what is remembered now: every CID when the queue was empty (the drain returned at once),
          # otherwise those whose reads failed since the heal round before the last queued CID took its snapshot.
          self.__heal_remembered_cids(show_logs=show_logs)
        finally:
          # Always free the pass lock, even if a step raised, so the next read can start a new pass.
          self.__relay_busy.release()
      try:
        # Run the pass on its own thread so the read returns without waiting for the relay; daemon=True so
        # a long pass (a big queue against a hung relay) does not hold up interpreter exit.
        Thread(target=work, name="r1fs-relay", daemon=True).start()
      except Exception as exc:
        # The thread did not start, so no worker will release the lock; free it here or every later
        # kick would be dropped.
        self.__relay_busy.release()
        # Say it in red instead of passing without a trace. The read that called this keeps its own result,
        # which does not depend on the relay; the next read starts the pass again.
        self.P(f"Background relay pass could not start: {exc}", color='r')

    def __report_rate_limited(self, kind: str, message: str):
      """
      Count one event of ``kind`` and log it in red, at most once per 600 s for that kind.

      The relay heal reports use it: a heal refused because ``__relay_heal_pending``
      is full (``__relay_in_background``) and a heal that failed for good
      (``__attempt_download_self_heal``). Both can happen once per failed read, so a
      flood of failed reads or a relay outage would otherwise print a line per read.
      The first event of a kind is logged at once, whatever ``show_logs`` the read
      had; later ones within 600 s are only counted, and the next line carries the
      count since start. Each kind has its own window, so one cannot hide the other.

      Parameters
      ----------
      kind : str
          Name of the kind of event; it keys the counter and the window.
      message : str
          The line to log for this event, without the count.

      Returns
      -------
      None

      Notes
      -----
      The window is the 600 s of the "RELAY DATA PATH" line
      (``__report_relay_data_path``). Two threads reporting the same kind at the same
      moment can both print, or count one event less.

      Examples
      --------
      >>> self.__report_rate_limited("relay heal failed", f"Relay heal of {cid} failed: HTTP 401")
      """
      # [events since start, time.time() of the last line]; a new kind starts at 0, so its first line prints at once.
      counter = self.__rate_limited_reports.setdefault(kind, [0, 0])
      # Count every event, printed or not, so the next printed line carries the ones in between.
      counter[0] += 1
      # Taken once: it gates the 600 s window and is stored as the time of this line.
      now = time.time()
      if now - counter[1] < 600:
        return
      # The next line of this kind can print 600 s after this one.
      counter[1] = now
      self.P(f"{message} ({counter[0]} since start, at most one such line per 600 s).", color='r')
      return

    def __report_relay_data_path(self, cid: str, read_started_at: float):
      """
      Log in red when a read fails for a CID the relay had already accepted.

      ``get_file`` calls this when its ``ipfs get`` fails, before it hands the CID to
      the background relay pass. A relay pin/add answered with HTTP 200 before the read
      began (``relay_published`` True and ``relay_last_success_at`` earlier than the
      read start) means the relay held every block of the CID when the read started,
      so a read that still got nothing points at the path between this node and the
      relay. Such a success is recorded by this node's own upload and also by the
      background heal of an earlier failed read (``__attempt_download_self_heal``), so
      a node that did not upload the CID can see it too. While a heal runs, the CID is
      marked unpublished and no line is printed.

      The line is printed whatever ``show_logs`` the read had, at most once per 600 s.
      Every such read is counted, and the printed line gives the count since start.
      Only when the line is printed, ``ipfs swarm peers`` and
      ``ipfs bitswap ledger <relay peer id>`` run (5 s timeout each), to tell whether
      the node has a direct connection to the relay (not through a circuit) and what
      its Bitswap ledger with the relay holds. Nothing is repaired or reconnected.

      Parameters
      ----------
      cid : str
          CID whose ``ipfs get`` just failed.
      read_started_at : float
          ``time.time()`` taken just before that ``ipfs get`` started.

      Returns
      -------
      None

      Notes
      -----
      ``relay_last_success_at`` is ISO-8601 text from ``__utc_now_iso``; that text
      has no fraction at a whole second, so text order is wrong inside such a second.
      It is therefore parsed and compared with ``read_started_at`` in seconds; both
      come from the system clock.
      A failed ``ipfs`` command returns empty text and is logged in red by
      ``__run_command``; the line then says ``Direct link: False`` or
      ``Ledger unreadable``. Kubo prints a ledger on five lines (``Ledger for``,
      ``Debt ratio``, ``Exchanges``, ``Bytes sent``, ``Bytes received``); they are
      joined into one.
      ``__parse_multiaddr`` returns None when the relay multiaddr has no tcp port or
      no peer id, and R1FS can still start with such a relay through
      ``ipfs swarm connect``. The two commands are then not run and the line says so.
      Two reads failing at the same moment on different threads can both print, or
      count one read less.

      Examples
      --------
      >>> # in get_file, when the ipfs get raised
      >>> self.__report_relay_data_path(cid, start_time)
      """
      # Only a relay pin/add answered 200 sets relay_published to True. A CID never seen here has an empty status,
      # and an entry that add_file's pin step recreates after an unpin removed it has no relay_published.
      status = self.get_upload_status(cid)
      if status.get("relay_published") is not True:
        return
      # relay_last_success_at is written in the same update that sets relay_published to True. Compare it in
      # seconds, not as text: the text has no fraction at a whole second and then sorts wrong.
      if datetime.fromisoformat(status["relay_last_success_at"].replace("Z", "+00:00")).timestamp() >= read_started_at:
        return
      # Count every such read, printed or not, so the next printed line carries the ones in between.
      self.__relay_data_failures += 1
      # Taken once: it gates the 600 s window and gives the seconds this read waited.
      now = time.time()
      if now - self.__relay_data_logged_at < 600:
        return
      # The next line can print 600 s after this one.
      self.__relay_data_logged_at = now
      # None when the relay multiaddr has no tcp port or no peer id; there is then no peer id to look up.
      relay_info = self.__parse_multiaddr(self.__ipfs_relay)
      # Stays as the answer when relay_info is None.
      checks = "Relay multiaddr has no tcp port or no peer id, so the link and ledger were not checked"
      if relay_info is not None:
        # The relay's peer id, as the swarm and the ledger name it.
        relay_id = relay_info["peer_id"]
        # A direct connection to the relay ends with its peer id; a connection through a circuit has /p2p-circuit.
        direct = any(
          addr.endswith("/p2p/" + relay_id) and "/p2p-circuit" not in addr
          for addr in self.__run_command(["ipfs", "swarm", "peers"], raise_on_error=False, timeout=5).split()
        )
        # Kubo prints the ledger on five lines; join them into one. Empty text means the command failed.
        ledger = " ".join(
          self.__run_command(["ipfs", "bitswap", "ledger", relay_id], raise_on_error=False, timeout=5).split()
        )
        # What the two commands found, for the line below.
        checks = f"Direct link: {direct}. {ledger or 'Ledger unreadable'}"
      self.P(
        f"RELAY DATA PATH: relay {self.__ipfs_relay} accepted {cid} at {status['relay_last_success_at']}, "
        f"but this node got nothing in {now - read_started_at:.0f} s. {checks}. "
        f"{self.__relay_data_failures} such read(s) since start.",
        color='r', boxed=True
      )
      return
    

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
      relay_info = self.__parse_multiaddr(self.__ipfs_relay)
      relay_peer_id = relay_info["peer_id"] if relay_info is not None else None
      try:
        if self.connected_at is not None:
          # Already connected, lets see if last check was recent enough:
          elapsed_time = time.time() - self.connected_at
          if elapsed_time < max_check_age:
            relay_found = True
            log_func(f"Relay check #{self.__relay_check_cnt}: relay peer already recorded for {elapsed_time:.1f}s; skipping recheck.")
            # If we are connected and the last check was recent enough, return True:
          else:
            log_func(f"Relay check #{self.__relay_check_cnt}: last relay check is {elapsed_time:.1f}s old; rechecking swarm peers.")
            # If we are connected but the last check was too long ago, check again:
          #end if needs recheck or not
        #end if connected_at is not None
        if not relay_found:         
          self.__relay_check_cnt += 1
          log_func(f"Relay check #{self.__relay_check_cnt}: scanning swarm peers for relay peer id.")
          peer_lines = self._get_swarm_peers()
          if len(peer_lines) > 0:
            log_func(f"Relay check #{self.__relay_check_cnt}: found {len(peer_lines)} swarm peer(s).")
            self.__peers = peer_lines
            for line in peer_lines:
              # After the workaround is applied, the relay may appear through the
              # local-gateway multiaddr instead of its public address. Matching by
              # peer id keeps the connection check valid in both states.
              if relay_peer_id and relay_peer_id in line:
                # Record the time if not already set
                relay_found = True
                log_func(f"Relay check #{self.__relay_check_cnt}: relay peer present on {line.strip()}")
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
              self.P(f"Relay check #{self.__relay_check_cnt}: relay connection recorded at {str_connected}.")
            else:              
              # TODO: maybe add first & last connected time
              # self.__connected_at = None # this is already None or the first connection
              log_func("Relay check #{}: relay peer {} not present in swarm peers:\n{}".format(
                self.__relay_check_cnt, relay_peer_id or self.__ipfs_relay.split('/')[2],
                json.dumps(peer_lines, indent=2)
                ), color='r'\
              )
            #end if relay_found or not
          else:
            log_func(f"Relay check #{self.__relay_check_cnt}: swarm peer list is empty.", color='r')
          #end if len(peer_lines) > 0
      except subprocess.TimeoutExpired:
        self.P(f"Relay check #{self.__relay_check_cnt}: timed out while reading swarm peers.", color='r')
        relay_found = False
      except Exception as e:
        self.P(f"Relay check #{self.__relay_check_cnt}: failed to inspect swarm peers: {e}", color='r')
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

    def __set_routing_type(self):
      # Routing.Type: "dht" vs "dhtclient"
      # - "dht" lets the node use the DHT and automatically act as a DHT *server* when it seems reachable
      #   (serves/handles other peers' DHT queries → more CPU/bandwidth/connections).
      # - "dhtclient" is lookup-only: it can query the DHT but never serves DHT traffic → lighter and more predictable.
      #   In a private hub-and-spoke setup (single relay), it's usually best to keep clients on "dhtclient" and let only
      #   the relay (or a small set of infra nodes) serve the DHT.
      result = self.__run_command(
        ["ipfs", "config", "--json", "Routing.Type", '"dhtclient"']
      )
      return result

    def __disable_ws_transport(self):
      result = self.__run_command(
        ["ipfs", "config", "--json", "Swarm.Transports.Network.Websocket", "false"]
      )
      return result

    def __disable_mdns_discovery(self):
      # Discovery.MDNS.Enabled: enabled vs disabled
      # mDNS is "LAN auto-discovery": peers on the same local network broadcast/announce themselves and auto-connect.
      # - Enabled: convenient for dev/LAN clusters where multicast works and you want plug-and-play discovery.
      # - Disabled: recommended for most server/relay/container deployments across machines/subnets (mDNS doesn't cross
      #   routers reliably, adds background chatter, and creates less predictable connections). In hub-and-spoke networks
      #   with explicit bootstrap-to-relay, mDNS usually provides little value and can be turned off.
      result = self.__run_command(
        ["ipfs", "config", "--json", "Discovery.MDNS.Enabled", "false"]
      )
      return result

    def __set_reprovider_strategy(self):
      # Reprovider.Strategy: "all" vs "pinned" vs "pinned+mfs"
      # Controls what content this node periodically re-announces ("reprovides") into the DHT (CID → provider records).
      # - "all": advertise *everything* in the local blockstore (includes transient cache) → can be very expensive/noisy.
      # - "pinned": advertise only content explicitly pinned (the data you intend to keep/serve) → usually the best default.
      # - "pinned+mfs": advertise pinned content plus the current MFS tree (IPFS's mutable filesystem workspace) → use if
      #   your app relies on MFS state being discoverable. Prefer avoiding "all" unless you truly want to advertise cache.
      result = self.__run_command(
        ["ipfs", "config", "--json", "Reprovider.Strategy", f'"{IPFSCt.REPROVIDER_STRATEGY}"']
      )
      return result

    def __bootstrap_add(self, ipfs_relay):
      result = self.__run_command(
        ["ipfs", "bootstrap", "add", ipfs_relay]
      )
      return result

    def __bootstrap_remove(self, multiaddr):
      """
      Remove a bootstrap multiaddr when present.

      Parameters
      ----------
      multiaddr : str
          Bootstrap peer multiaddr to remove.

      Returns
      -------
      bool
          ``True`` when the remove command reported success.
      """
      output, errors = self.__run_command(
        ["ipfs", "bootstrap", "rm", multiaddr],
        raise_on_error=False,
        return_errors=True,
      )
      combined = " ".join(part for part in (output, errors) if part).lower()
      return "removed" in combined or "deleted" in combined

    def __set_config_json(self, key, value):
      """
      Set a JSON-valued IPFS config key.

      Parameters
      ----------
      key : str
          IPFS config key path understood by ``ipfs config --json``.
      value : any
          JSON-serializable value to persist.

      Returns
      -------
      str
          Raw stdout returned by the ``ipfs config`` command.
      """
      return self.__run_command(
        ["ipfs", "config", "--json", key, json.dumps(value, separators=(",", ":"))]
      )

    def __get_config_json(self, key, default=None):
      """
      Read and decode a JSON-valued IPFS config key.

      Parameters
      ----------
      key : str
          IPFS config key path understood by ``ipfs config --json``.
      default : any, optional
          Value returned when the key cannot be read or parsed.

      Returns
      -------
      any
          Decoded JSON value or ``default`` when reading/parsing fails.
      """
      if default is None:
        default = []
      output = self.__run_command(
        ["ipfs", "config", "--json", key],
        raise_on_error=False,
        show_logs=False,
      )
      if not output:
        return list(default) if isinstance(default, list) else default
      try:
        parsed = json.loads(output)
        if parsed is None:
          return list(default) if isinstance(default, list) else default
        return parsed
      except Exception:
        self.P(f"Failed to parse config key {key}: {output}", color='r')
        return list(default) if isinstance(default, list) else default

    def __get_bootstrap_list(self):
      """
      Return the current bootstrap peer list.

      Returns
      -------
      list[str]
          Bootstrap multiaddrs currently configured in the local IPFS repo.
      """
      output = self.__run_command(
        ["ipfs", "bootstrap", "list"],
        raise_on_error=False,
        show_logs=False,
      )
      if not output:
        return []
      return [line.strip() for line in output.splitlines() if line.strip()]

    def __ensure_bootstrap_entry(self, multiaddr):
      """
      Ensure a bootstrap multiaddr exists exactly once.

      Parameters
      ----------
      multiaddr : str
          Bootstrap peer multiaddr to add when missing.

      Returns
      -------
      bool
          ``True`` when the bootstrap entry was added, ``False`` when it was
          already present.
      """
      bootstraps = self.__get_bootstrap_list()
      if multiaddr in bootstraps:
        return False
      self.__bootstrap_add(multiaddr)
      return True

    def __merge_unique_values(self, existing, additions):
      """
      Append missing values while preserving original order.

      Parameters
      ----------
      existing : list
          Existing ordered values.
      additions : list
          Candidate values to append when not already present.

      Returns
      -------
      tuple[list, bool]
          Updated ordered list and a flag indicating whether any new value was
          appended.
      """
      merged = list(existing or [])
      changed = False
      for value in additions or []:
        if value and value not in merged:
          merged.append(value)
          changed = True
      return merged, changed

    def __parse_multiaddr(self, multiaddr):
      """
      Extract the relay addressing fields needed by the workaround.

      Parameters
      ----------
      multiaddr : str
          Relay multiaddr such as ``/ip4/<ip>/tcp/<port>/p2p/<peer_id>``.

      Returns
      -------
      dict or None
          Parsed relay metadata or ``None`` when the input does not contain the
          minimum fields required by the workaround.
      """
      if not multiaddr or not isinstance(multiaddr, str):
        return None
      parts = [part for part in multiaddr.split("/") if part]
      parsed = {
        "multiaddr": multiaddr,
        "ip4": None,
        "ip6": None,
        "tcp_port": None,
        "peer_id": None,
      }
      idx = 0
      while idx < len(parts):
        token = parts[idx]
        next_part = parts[idx + 1] if idx + 1 < len(parts) else None
        if token == "ip4":
          parsed["ip4"] = next_part
          idx += 2
          continue
        if token == "ip6":
          parsed["ip6"] = next_part
          idx += 2
          continue
        if token == "tcp":
          parsed["tcp_port"] = next_part
          idx += 2
          continue
        if token in {"p2p", "ipfs"}:
          parsed["peer_id"] = next_part
          idx += 2
          continue
        idx += 1
      if not parsed["tcp_port"] or not parsed["peer_id"]:
        return None
      return parsed

    def __build_peer_multiaddr(self, ip_version, host, port, peer_id):
      """
      Build a peer multiaddr from normalized parts.

      Parameters
      ----------
      ip_version : str
          Multiaddr IP token, usually ``ip4`` or ``ip6``.
      host : str
          Peer host or IP literal.
      port : str
          TCP port.
      peer_id : str
          IPFS peer id.

      Returns
      -------
      str
          Peer multiaddr.
      """
      return f"/{ip_version}/{host}/tcp/{port}/p2p/{peer_id}"

    def __samehost_fix_enabled(self):
      """
      Determine whether the same-host workaround should run.

      Returns
      -------
      bool
          ``True`` only when the environment explicitly enables the workaround.
          The fix is currently opt-in because the local same-host path can pass
          control-plane checks while still failing block transfer.
      """
      value = os.getenv(IPFSCt.EE_R1FS_SAMEHOST_RELAY_FIX)
      if value is None:
        return False
      return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def __get_default_gateway(self):
      """
      Discover the container default gateway from ``ip route``.

      Returns
      -------
      str or None
          Default gateway IP string or ``None`` when it cannot be determined.
      """
      output = self.__run_command(
        ["ip", "route"],
        raise_on_error=False,
        show_logs=False,
        timeout=5,
      )
      if not output:
        return None
      for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == "default":
          try:
            via_idx = parts.index("via")
            return parts[via_idx + 1]
          except Exception:
            continue
      return None

    def __build_addr_filters(self, relay_info):
      """
      Build addrfilter entries that block the relay public addresses.

      Parameters
      ----------
      relay_info : dict
          Parsed relay metadata from :meth:`__parse_multiaddr`.

      Returns
      -------
      list[str]
          Addrfilter entries for the relay public IPs.
      """
      filters = []
      if relay_info.get("ip4"):
        filters.append(f"/ip4/{relay_info['ip4']}/ipcidr/32")
      if relay_info.get("ip6"):
        filters.append(f"/ip6/{relay_info['ip6']}/ipcidr/128")
      return filters

    def __has_all_values(self, existing, required):
      """
      Check whether every required value is already present.

      Parameters
      ----------
      existing : list
          Existing values.
      required : list
          Values that must be present.

      Returns
      -------
      bool
          ``True`` when all required values are already contained in
          ``existing``.
      """
      existing_values = set(existing or [])
      return all(value in existing_values for value in (required or []) if value)

    def __get_samehost_fix_marker_path(self):
      """
      Return the marker path used by the same-host workaround.

      Returns
      -------
      str
          Absolute marker path inside the active IPFS repo.
      """
      return os.path.join(self.__ipfs_home, IPFSCt.SAMEHOST_FIX_MARKER)

    def __read_samehost_fix_marker(self):
      """
      Read the persisted same-host workaround marker.

      Returns
      -------
      dict or None
          Marker payload or ``None`` when the marker is missing or invalid.
      """
      marker_path = self.__get_samehost_fix_marker_path()
      if not os.path.isfile(marker_path):
        return None
      try:
        with open(marker_path, "r") as fd:
          return json.load(fd)
      except Exception as e:
        self.P(f"Failed to read same-host relay marker: {e}", color='r')
        return None

    def __write_samehost_fix_marker(self, marker):
      """
      Persist the same-host workaround marker.

      Parameters
      ----------
      marker : dict
          Marker payload describing the last successful or cached-negative
          same-host decision.
      """
      marker_path = self.__get_samehost_fix_marker_path()
      with open(marker_path, "w") as fd:
        json.dump(marker, fd, indent=2, sort_keys=True)

    def __delete_samehost_fix_marker(self):
      """
      Remove the persisted same-host workaround marker when present.
      """
      marker_path = self.__get_samehost_fix_marker_path()
      if os.path.isfile(marker_path):
        os.remove(marker_path)
      return

    def __marker_matches_samehost_fix(self, marker, relay_info, gateway):
      """
      Check whether a marker describes the current relay/gateway tuple.

      Parameters
      ----------
      marker : dict
          Persisted marker payload.
      relay_info : dict
          Parsed relay metadata from :meth:`__parse_multiaddr`.
      gateway : str
          Current container default gateway.

      Returns
      -------
      bool
          ``True`` when the marker matches the current same-host decision
          inputs.
      """
      if not isinstance(marker, dict):
        return False
      return (
        marker.get("peer_id") == relay_info.get("peer_id") and
        marker.get("relay_ip4") == relay_info.get("ip4") and
        marker.get("relay_ip6") == relay_info.get("ip6") and
        marker.get("gateway") == gateway
      )

    def __get_marker_status(self, marker):
      """
      Return the stored marker status.

      Parameters
      ----------
      marker : dict
          Persisted marker payload.

      Returns
      -------
      str or None
          Marker status or ``None`` when unavailable.
      """
      if not isinstance(marker, dict):
        return None
      return marker.get("status")

    def __parse_marker_timestamp(self, marker):
      """
      Parse the marker timestamp as an aware UTC datetime.

      Parameters
      ----------
      marker : dict
          Persisted marker payload.

      Returns
      -------
      datetime or None
          Parsed timestamp or ``None`` when missing/invalid.
      """
      if not isinstance(marker, dict):
        return None
      timestamp = marker.get("timestamp")
      if not timestamp:
        return None
      try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
      except Exception:
        return None

    def __is_negative_marker_fresh(self, marker):
      """
      Check whether a cached negative proof result is still usable.

      Parameters
      ----------
      marker : dict
          Persisted marker payload.

      Returns
      -------
      bool
          ``True`` when the marker represents a recent failed proof for the
          current relay/gateway tuple.
      """
      if self.__get_marker_status(marker) != "negative":
        return False
      marker_time = self.__parse_marker_timestamp(marker)
      if marker_time is None:
        return False
      age_seconds = (datetime.now(timezone.utc) - marker_time).total_seconds()
      return age_seconds >= 0 and age_seconds < IPFSCt.SAMEHOST_FIX_NEGATIVE_TTL_SECONDS

    def __swarm_connect(self, multiaddr, timeout=IPFSCt.TIMEOUT):
      """
      Attempt an ``ipfs swarm connect`` and normalize success detection.

      Parameters
      ----------
      multiaddr : str
          Peer multiaddr to connect to.
      timeout : int, optional
          Command timeout in seconds.

      Returns
      -------
      tuple[bool, str, str]
          Success flag, stdout, and stderr from the command.
      """
      output, errors = self.__run_command(
        ["ipfs", "swarm", "connect", multiaddr],
        raise_on_error=False,
        return_errors=True,
        timeout=timeout,
      )
      combined = " ".join(part for part in (output, errors) if part).lower()
      success = "success" in combined or "already connected" in combined
      return success, output, errors

    def __swarm_disconnect(self, target, timeout=10):
      """
      Attempt an ``ipfs swarm disconnect`` without treating failures as fatal.

      Parameters
      ----------
      target : str
          Peer multiaddr or peer id to disconnect from.
      timeout : int, optional
          Command timeout in seconds.

      Returns
      -------
      tuple[bool, str, str]
          Success flag, stdout, and stderr from the command.
      """
      output, errors = self.__run_command(
        ["ipfs", "swarm", "disconnect", target],
        raise_on_error=False,
        return_errors=True,
        timeout=timeout,
      )
      combined = " ".join(part for part in (output, errors) if part).lower()
      success = "disconnect" in combined or "success" in combined or "not connected" in combined
      return success, output, errors

    def __peer_uses_multiaddr(self, peer_lines, multiaddr):
      """
      Check whether a peer is currently connected through an exact multiaddr.

      Parameters
      ----------
      peer_lines : list[str]
          Output lines from ``ipfs swarm peers``.
      multiaddr : str
          Expected peer multiaddr.

      Returns
      -------
      bool
          ``True`` when the exact multiaddr is present in ``peer_lines``.
      """
      return multiaddr in (peer_lines or [])

    def __wait_for_peer_disconnect(self, peer_id, timeout=5, step=0.5):
      """
      Wait until a peer id disappears from ``ipfs swarm peers``.

      Parameters
      ----------
      peer_id : str
          Peer id to wait for.
      timeout : int, optional
          Maximum wait in seconds.
      step : float, optional
          Poll interval in seconds.

      Returns
      -------
      bool
          ``True`` when the peer is no longer present in swarm peers.
      """
      waited = 0.0
      while waited < timeout:
        peer_lines = self._get_swarm_peers()
        if not any(peer_id in line for line in peer_lines):
          return True
        time.sleep(step)
        waited += step
      return False

    def __prove_samehost_relay_path(self, relay_info, local_multiaddr):
      """
      Prove that the relay is reachable through the local gateway multiaddr.

      The proof must show an active swarm peer connection on the exact local
      multiaddr after disconnecting any existing relay connection. This avoids
      accepting a stale/public relay connection as evidence that the local path
      works.

      Parameters
      ----------
      relay_info : dict
          Parsed relay metadata from :meth:`__parse_multiaddr`.
      local_multiaddr : str
          Candidate local-gateway relay multiaddr.

      Returns
      -------
      tuple[bool, str]
          Proof success flag and a short diagnostic message.
      """
      peer_id = relay_info["peer_id"]
      public_multiaddrs = []
      if relay_info.get("ip4"):
        public_multiaddrs.append(self.__build_peer_multiaddr("ip4", relay_info["ip4"], relay_info["tcp_port"], peer_id))
      if relay_info.get("ip6"):
        public_multiaddrs.append(self.__build_peer_multiaddr("ip6", relay_info["ip6"], relay_info["tcp_port"], peer_id))

      # Disconnect any existing relay session so a subsequent success must come
      # from the specific local multiaddr under test.
      for public_multiaddr in public_multiaddrs:
        self.__swarm_disconnect(public_multiaddr, timeout=5)
      self.__swarm_disconnect(local_multiaddr, timeout=5)
      self.__wait_for_peer_disconnect(peer_id, timeout=5, step=0.5)

      self.P(
        f"Same-host relay check: probing local gateway path {local_multiaddr} for relay peer {peer_id}.",
        color='d',
      )
      success, output, errors = self.__swarm_connect(local_multiaddr, timeout=5)
      if not success:
        reconnect_target = public_multiaddrs[0] if public_multiaddrs else self.__ipfs_relay
        self.__swarm_connect(reconnect_target, timeout=5)
        return False, errors or output or "local connect failed"

      peer_lines = self._get_swarm_peers()
      if self.__peer_uses_multiaddr(peer_lines, local_multiaddr):
        self.P(f"Same-host relay check: relay peer confirmed on local path {local_multiaddr}.", color='g')
        return True, "connected through local multiaddr"

      reconnect_target = public_multiaddrs[0] if public_multiaddrs else self.__ipfs_relay
      for public_multiaddr in public_multiaddrs:
        self.__swarm_disconnect(public_multiaddr, timeout=5)
      self.__swarm_disconnect(local_multiaddr, timeout=5)
      self.__swarm_connect(reconnect_target, timeout=5)
      return False, "relay peer did not reappear on the expected local multiaddr"

    def __reset_connection_state(self):
      """
      Clear connection-derived state before a daemon restart.
      """
      self.__ipfs_started = False
      self.__connected_at = None
      self.__peers = []

    def __shutdown_daemon(self, timeout=20):
      """
      Stop the local IPFS daemon.

      Parameters
      ----------
      timeout : int, optional
          Grace period in seconds before falling back to signaling daemon PIDs.

      Returns
      -------
      bool
          ``True`` when the daemon is observed stopped.
      """
      if not self.is_ipfs_daemon_running():
        return True
      self.__run_command(
        ["ipfs", "shutdown"],
        raise_on_error=False,
        timeout=10,
      )
      waited = 0
      while waited < timeout:
        if not self.is_ipfs_daemon_running():
          return True
        time.sleep(1)
        waited += 1

      pid_output = self.__run_command(
        ["pgrep", "-f", "ipfs daemon"],
        raise_on_error=False,
        show_logs=False,
        timeout=5,
      )
      if pid_output:
        for pid_text in pid_output.splitlines():
          try:
            os.kill(int(pid_text.strip()), signal.SIGINT)
          except Exception:
            continue
      waited = 0
      while waited < 5:
        if not self.is_ipfs_daemon_running():
          return True
        time.sleep(1)
        waited += 1
      return not self.is_ipfs_daemon_running()

    def __start_daemon(self, max_attempts=10, sleep_time=2):
      """
      Start the local IPFS daemon with an empty Bootstrap list, then dial its bootstrap peers.

      The daemon dials the peers of its Bootstrap list while it is still being built,
      before its block exchange (Bitswap) starts to watch connections. A connection
      opened that early is never used for block requests for as long as it lives:
      the peer answers pings and relays circuits, but this node never asks it for a
      block. A relay on the same host completes the handshake in about a millisecond
      and loses this race on most starts. So the configured peers are held back: the
      list is emptied before the daemon is launched, and once the daemon API answers
      (the block exchange is running by then) each held-back peer is dialed and put
      back in the list.

      Parameters
      ----------
      max_attempts : int, optional
          Number of health-check attempts.
      sleep_time : int, optional
          Delay in seconds between health checks.

      Returns
      -------
      bool
          ``True`` when the daemon becomes reachable. ``False`` when it does not answer
          within ``max_attempts`` checks; the Bootstrap list is then left empty, and the
          next start through ``maybe_start_ipfs`` writes it again.

      Raises
      ------
      Exception
          When ``ipfs bootstrap rm --all`` or ``ipfs bootstrap add`` fails (raised by
          the command runner).

      Notes
      -----
      After the start the repository holds the same Bootstrap list as before, so the
      running daemon re-dials a lost peer exactly as it did. A peer that cannot be
      dialed right after the start is said in red and still put back in the list; the
      relay check in ``maybe_start_ipfs`` then decides whether R1FS is started.

      Examples
      --------
      >>> # in maybe_start_ipfs, after the relay was written to the Bootstrap list
      >>> self.__start_daemon()
      True
      """
      # The peers the daemon would dial while it is still being built (the assigned relay).
      held_back_peers = self.__get_bootstrap_list()
      if not held_back_peers:
        self.P("No bootstrap peer is configured: the daemon is started alone and nothing is dialed after its start.", color='r')
      # Start with an empty Bootstrap list, so no connection exists before the block exchange watches them.
      self.__run_command(["ipfs", "bootstrap", "rm", "--all"])
      self.P("Starting IPFS daemon in background...")
      subprocess.Popen(
        ["ipfs", "daemon", "--enable-gc", "--migrate=true"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
      )
      for attempt in range(max_attempts):
        ipfs_daemon_running = self.is_ipfs_daemon_running()
        if ipfs_daemon_running:
          self.P("IPFS daemon started successfully.", color='g')
          # Only now dial the held-back peers and give them back to the daemon.
          for multiaddr in held_back_peers:
            # The API answers, so the block exchange is running: a connection opened now is one it uses.
            connected, output, errors = self.__swarm_connect(multiaddr)
            if not connected:
              self.P(f"Bootstrap peer {multiaddr} could not be dialed after the daemon start: {errors or output}", color='r')
            # Back in the Bootstrap list, so the running daemon re-dials the peer after a lost connection as before.
            self.__bootstrap_add(multiaddr)
          return True
        self.P(f"Check {attempt + 1}/{max_attempts} IPFS running: {ipfs_daemon_running}", color='r')
        time.sleep(sleep_time)
      return False

    def __restart_daemon(self):
      """
      Restart the local IPFS daemon after config changes.

      Returns
      -------
      bool
          ``True`` when the daemon was stopped and started successfully.
      """
      self.P("Restarting IPFS daemon to apply same-host relay workaround...", color='m')
      self.__reset_connection_state()
      if not self.__shutdown_daemon():
        self.P("Failed to stop IPFS daemon cleanly.", color='r')
        return False
      if not self.__start_daemon():
        self.P("Failed to restart IPFS daemon after applying workaround.", color='r')
        return False
      return True

    def __cleanup_samehost_relay_workaround(self):
      """
      Remove previously applied same-host workaround state from the repo.

      Returns
      -------
      bool
          ``True`` when repo config was changed, otherwise ``False``.
      """
      relay_info = self.__parse_multiaddr(self.__ipfs_relay)
      if relay_info is None:
        return False

      gateway = self.__get_default_gateway()
      local_multiaddr = None
      if gateway:
        try:
          ipaddress.ip_address(gateway)
          local_multiaddr = self.__build_peer_multiaddr(
            "ip4",
            gateway,
            relay_info["tcp_port"],
            relay_info["peer_id"],
          )
        except ValueError:
          local_multiaddr = None

      changed = False
      if local_multiaddr and local_multiaddr in self.__get_bootstrap_list():
        if self.__bootstrap_remove(local_multiaddr):
          self.P(f"Same-host relay workaround cleanup: removed local bootstrap {local_multiaddr}.", color='g')
          changed = True

      addr_filters = self.__get_config_json("Swarm.AddrFilters", default=[])
      desired_filters = set(self.__build_addr_filters(relay_info))
      cleaned_filters = [value for value in addr_filters if value not in desired_filters]
      if cleaned_filters != addr_filters:
        self.__set_config_json("Swarm.AddrFilters", cleaned_filters)
        self.P("Same-host relay workaround cleanup: removed local-path addrfilters from repo config.", color='g')
        changed = True

      marker = self.__read_samehost_fix_marker()
      if marker is not None:
        self.__delete_samehost_fix_marker()
        self.Pd("Same-host relay workaround cleanup: removed persisted marker.")

      return changed

    def __maybe_apply_samehost_relay_workaround(self):
      """
      Reconcile same-host relay bootstrap/filter state.

      The workaround is intended for edge-node containers running on the same
      host as the relay. It uses three progressively more expensive checks:

      1. Marker + live config fast path.
      2. Bounded negative-cache skip for recent failed proofs.
      3. Proof connect to the container gateway before mutating config.

      Returns
      -------
      bool
          ``True`` when config changes required a daemon restart, otherwise
          ``False``.
      """
      if self.__samehost_fix_attempted:
        return False
      self.__samehost_fix_attempted = True

      if not self.__samehost_fix_enabled():
        self.Pd("Same-host relay workaround: disabled by environment.")
        self.__cleanup_samehost_relay_workaround()
        return False

      relay_info = self.__parse_multiaddr(self.__ipfs_relay)
      if relay_info is None:
        self.P("Same-host relay workaround: skipped because relay multiaddr could not be parsed.", color='r')
        return False

      gateway = self.__get_default_gateway()
      if not gateway:
        self.P("Same-host relay workaround: skipped because the container gateway could not be determined.", color='r')
        return False

      try:
        ipaddress.ip_address(gateway)
      except ValueError:
        self.P(f"Same-host relay workaround: skipped because gateway {gateway} is invalid.", color='r')
        return False

      local_multiaddr = self.__build_peer_multiaddr(
        "ip4",
        gateway,
        relay_info["tcp_port"],
        relay_info["peer_id"],
      )

      marker = self.__read_samehost_fix_marker()
      marker_matches = self.__marker_matches_samehost_fix(marker, relay_info, gateway)
      addr_filters = self.__get_config_json("Swarm.AddrFilters", default=[])
      desired_filters = self.__build_addr_filters(relay_info)
      bootstraps = self.__get_bootstrap_list()
      bootstrap_matches = local_multiaddr in bootstraps
      filters_match = self.__has_all_values(addr_filters, desired_filters)
      # Fast path: when both marker and repo config already match the desired
      # same-host state, avoid any extra proof-connect or restart work.
      if marker_matches and bootstrap_matches and filters_match:
        self.Pd("Same-host relay workaround: marker and repo config already match; nothing to do.")
        return False
      # Negative cache: off-host nodes can repeatedly fail the local gateway
      # proof; cache that result for a short TTL to avoid paying the timeout on
      # every process restart.
      if marker_matches and self.__is_negative_marker_fresh(marker):
        self.Pd("Same-host relay workaround: recent negative proof cached for this relay/gateway; skipping probe.")
        return False

      success, proof_reason = self.__prove_samehost_relay_path(relay_info, local_multiaddr)
      if not success:
        self.__write_samehost_fix_marker({
          "peer_id": relay_info.get("peer_id"),
          "relay_ip4": relay_info.get("ip4"),
          "relay_ip6": relay_info.get("ip6"),
          "gateway": gateway,
          "local_multiaddr": local_multiaddr,
          "status": "negative",
          "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        self.P(f"Same-host relay workaround: local gateway path not usable ({proof_reason}); keeping public relay path.", color='d')
        return False

      local_bootstrap_changed = False
      if not bootstrap_matches:
        local_bootstrap_changed = self.__ensure_bootstrap_entry(local_multiaddr)
      merged_filters, filters_changed = self.__merge_unique_values(addr_filters, desired_filters)
      if filters_changed:
        self.__set_config_json("Swarm.AddrFilters", merged_filters)

      new_marker = {
        "peer_id": relay_info.get("peer_id"),
        "relay_ip4": relay_info.get("ip4"),
        "relay_ip6": relay_info.get("ip6"),
        "gateway": gateway,
        "local_multiaddr": local_multiaddr,
        "status": "applied",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      }
      if not marker_matches or filters_changed:
        self.__write_samehost_fix_marker(new_marker)

      if not filters_changed:
        if local_bootstrap_changed:
          self.P(f"Same-host relay workaround: restored local bootstrap {local_multiaddr}; restart not required.", color='g')
        else:
          self.Pd("Same-host relay workaround: proof succeeded but config changes were already present.")
        return False

      self.P(
        "Same-host relay workaround: applying addrfilters {} and restarting daemon.".format(
          json.dumps(desired_filters)
        ),
        color='m',
      )
      return self.__restart_daemon()

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
      result = None
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
      
      if result is not None and result.returncode != 0:
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
    def __pin_add(self, cid: str, timeout: float = IPFSCt.TIMEOUT) -> str:
      """
      Explicitly pin a CID (and fetch its data) so it appears in the local pinset.

      Runs ``ipfs pin add`` with a timeout the caller can now choose. ``get_file``
      calls it after a successful ``ipfs get`` with the time the read has left (at
      least 1 s), so a read is no longer held by a network pin under the fixed
      default before the get. The pin is quick when the blocks the get stored are
      still local; a repository garbage collection between the get and the pin
      removes those unpinned blocks, and the pin then has to fetch them again within
      that time. ``add_file`` keeps the default timeout.

      Parameters
      ----------
      cid : str
          CID to pin in the local IPFS node.
      timeout : float, optional
          Seconds before ``ipfs pin add`` is abandoned. Default ``IPFSCt.TIMEOUT``,
          the value every pin used before this parameter existed.

      Returns
      -------
      str
          Stripped stdout of ``ipfs pin add``.

      Raises
      ------
      Exception
          From ``__run_command`` when the command fails or times out.
      RuntimeError
          From ``require_ipfs_started`` when IPFS has not been started.

      Examples
      --------
      >>> # in get_file, after a successful get, with the time the read has left
      >>> self.__pin_add(cid, timeout=max(1, ipfs_timeout - download_elapsed_time))
      """
      # Pass the timeout through so get_file can bound its pin by the reader's timeout, not the fixed default.
      res = self.__run_command(["ipfs", "pin", "add", cid], timeout=timeout)
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
          in a unique temporary directory. It must be a plain file name (no path
          part, not '', '.' or '..'); it is written in that directory, stored as
          the file's name, and the file is removed afterwards.
          
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
          The CID of the added JSON file, or None when it fails and
          raise_on_error=False (a refused ``fn`` included).

      Raises
      ------
      ValueError
          If ``fn`` is not a plain file name and raise_on_error=True.
      Exception
          With raise_on_error=True, any other error is re-raised as it came: a
          TypeError (or ValueError, for a circular reference) from json.dumps, an
          OSError from making the folder or writing the file, or the error
          ``add_file`` raises.

      Notes
      -----
      ``fn`` is checked before anything is written, whatever ``use_tempfile`` is: an
      absolute or ``..`` name joined to the temporary directory would name a file
      outside it, which would be written and then removed by the cleanup. A refused
      name is logged in red whatever ``show_logs`` is.

      Examples
      --------
      >>> cid = engine.add_json({"plan": 1}, fn="deployment-plan.json", nonce=42)

      >>> # Not a plain file name: refused, nothing is written
      >>> print(engine.add_json({"plan": 1}, fn="../plan.json"))
      None
      """
      # Only a plain file name stays inside the unique folder it is joined to below; an absolute or '..' name would
      # be written, then removed by the cleanup, outside it. None takes the default name.
      if fn is not None and self.__refuse_unplain_name(fn, raise_on_error=raise_on_error):
        # Refused and logged, before anything was written: no CID.
        return None
      unique_dir = None
      try:
        json_data = json.dumps(data, sort_keys=True, separators=(',', ':'))
        if show_logs:
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
          It must be a plain file name (no path part, not '', '.' or '..'); it is
          written in a folder of its own in the uploads directory, stored as the
          file's name, and the file and its folder are removed afterwards.
          
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
          The CID of the added pickle file, or None when it fails and
          raise_on_error=False (a refused ``fn`` included).

      Raises
      ------
      ValueError
          If ``fn`` is not a plain file name and raise_on_error=True.
      Exception
          With raise_on_error=True, any other error is re-raised as it came: a
          pickling error from pickle.dump, an OSError from making the folder or
          writing the file, or the error ``add_file`` raises.

      Notes
      -----
      ``fn`` is checked before anything is written, whatever ``use_tempfile`` is, and
      a refused name is logged in red whatever ``show_logs`` is. A plain ``fn`` is
      written in a new folder of its own in the uploads directory, where the unique
      default name goes too, and not in the process's working directory: there the
      write and the cleanup would replace and then delete any file of that name. The
      folder of its own keeps two calls with the same ``fn`` from writing, encrypting
      or deleting each other's file. The stored name, and so the CID, is ``fn``
      either way.

      Examples
      --------
      >>> cid = engine.add_pickle({"w": [1, 2]}, fn="model.pkl", nonce=42)

      >>> # Not a plain file name: refused, nothing is written
      >>> print(engine.add_pickle({"w": [1, 2]}, fn="/tmp/model.pkl"))
      None
      """
      # Only a plain file name stays inside the uploads folder it is joined to below; an absolute or '..' name would
      # be written, then removed by the cleanup, outside it. None takes a unique name there.
      if fn is not None and self.__refuse_unplain_name(fn, raise_on_error=raise_on_error):
        # Refused and logged, before anything was written: no CID.
        return None
      # The folder of its own that a caller's name gets below; None when there is none to remove.
      unique_dir = None
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
            # A folder of its own in the uploads folder, as add_json does, so two calls with the same name never
            # write, encrypt or delete each other's file there.
            unique_dir = os.path.join(self.__uploads_dir, uuid.uuid4().hex)
            # Made here, removed by the finally below once its file is gone.
            os.makedirs(unique_dir)
            # Put the caller's plain name in that folder. Opened as it was, it named a file in the process's working
            # folder, which the cleanup below then deleted. The stored name is the basename, so the CID does not change.
            fn = os.path.join(unique_dir, fn)
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
        if unique_dir and os.path.exists(unique_dir):
          # The caller's name had a folder of its own; its file is gone by now.
          os.rmdir(unique_dir)


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

      Notes
      -----
      Upload success is tracked separately from relay publication success. Use
      :meth:`get_upload_status` when the caller needs to distinguish:

      - local ciphertext upload and local pin success
      - relay publication success
      - relay publication queued for retry

      Examples
      --------
      >>> cid = engine.add_file("/data/large_model.bin")
      >>> print(cid)
      QmFolder123ABC
      """
      add_time, remove_time, pin_time = 0.0, 0.0, 0.0
      relay_publish_time = 0.0
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
        self.__set_upload_status(
          folder_cid,
          source_path=file_path,
          local_upload_succeeded=True,
          local_pin_succeeded=False,
          relay_status="pending",
          relay_published=None,
          relay_detail="Local IPFS add completed; relay publication pending.",
        )
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
        pin_start_time = time.time()
        self.__uploaded_files[folder_cid] = file_path
        relay_publish_start = time.time()
        self.__publish_cid_to_relay(
          cid=folder_cid,
          source_path=file_path,
          context="upload",
          queue_on_failure=True,
          show_logs=show_logs,
          raise_on_error=False,
        )
        relay_publish_time = time.time() - relay_publish_start
        # Keep the local node pinned even when relay publication is deferred.
        self.__pin_add(folder_cid)
        self.__set_upload_status(
          folder_cid,
          source_path=file_path,
          local_pin_succeeded=True,
          local_pin_completed_at=self.__utc_now_iso(),
        )
        pin_time = time.time() - pin_start_time
        #end if show_logs
      #end if folder_cid is not None
      total_time = time.time() - start_time
      if show_logs:
        upload_status = self.get_upload_status(folder_cid) if folder_cid else {}
        relay_status = upload_status.get("relay_status", "unknown")
        self.P(
          f"Added file {file_path} as <{folder_cid}> in {total_time:.2f}s: "
          f"add_time={add_time:.2f}s, remove_time={remove_time:.2f}s, "
          f"relay_publish_time={relay_publish_time:.2f}s, pin_time={pin_time:.2f}s, "
          f"relay_status={relay_status}"
        )
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
        The folder CID (wrapped single file). It must be a bare CID: a non-empty
        string of at most 255 ASCII letters and digits, as ``ipfs add`` prints it (CIDv0
        ``Qm...`` or CIDv1 in base32 / base36). Path forms such as
        ``/ipfs/<cid>`` or ``<cid>/sub/path`` are refused.

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
        The full path to the restored plaintext file, or None when the read
        fails and raise_on_error=False (an invalid ``cid`` included).

      Raises
      ------
      ValueError
        If ``cid`` is not a bare CID (see ``cid``) and raise_on_error=True.

      RuntimeError
        If multiple or zero files are found in the downloaded folder,
        or if we fail to parse the JSON metadata, or if the file name stored in
        the metadata is not a plain file name, or if the download or its single
        entry is a link or not a regular folder / file, and raise_on_error=True.

      Exception
        If the GCM tag is invalid or the IPFS command times out
        and raise_on_error=True.

      Notes
      -----
      ``cid`` is checked before anything else: ``local_folder/<cid>`` is deleted
      before ``ipfs get`` runs, so a ``cid`` that is not a bare CID could name a
      path outside ``local_folder`` (``/abs/path``, ``..``). Such a ``cid`` is
      refused with no file deleted, no ``ipfs`` command run and no relay heal
      queued. A refused ``cid`` other than None or "" is logged in red whatever
      ``show_logs`` is.

      The output file is named after the ``filename`` stored in the downloaded
      object's own metadata, which whoever added the object chose. It must be a plain
      file name (no path part, not '', '.' or '..'), so the plaintext is written only
      inside ``local_folder/<cid>``; any other name is refused through the decryption
      error path. The GCM tag is checked only after all plaintext was written, so when
      decryption fails (refused name and bad tag included) ``local_folder/<cid>``, which
      this call made and which holds only the ciphertext and that plaintext, is removed
      before the error is raised or logged: no unauthenticated plaintext stays on disk.

      ``ipfs get`` writes a UnixFS symlink as a link that can point anywhere on this
      node, while an R1FS object is one regular file by construction. So when
      ``local_folder/<cid>`` is itself a link (the CID's root is a symlink) the read is
      refused like a download that is not a directory, with nothing read, written or
      deleted through the link; the next read of that CID removes the link when its
      target exists (a dangling link fails ``os.path.exists`` and stays); and an entry
      that is a link or not a regular file is refused before it is opened, through
      the decryption error path, which removes the folder with the link.

      ``ipfs get`` runs first and is bounded by ``timeout``; when ``pin`` is True the
      CID is pinned only after a successful get, with only the time the get left
      (at least 1 s), so the get and the pin together take about ``timeout`` at most,
      about 1 s more when the get used nearly all of it. Starting the ``ipfs``
      commands and decryption are not counted in that time. A failed pin is logged in red and not retried; the read still
      returns the file. Relay work never runs on the caller's thread: after a failed
      get the CID is remembered for the background relay pass (see
      ``__relay_in_background``), which asks the relay to fetch it so a later read
      can find it and also retries the queued relay publications. The failed read
      itself is not retried. A failed get of a CID the relay had accepted before the
      read began also prints a boxed red "RELAY DATA PATH" line, whatever
      ``show_logs`` is, at most once per 600 s (see ``__report_relay_data_path``).

      Examples
      --------
      >>> # Simple usage with default passphrase
      >>> local_file = engine.get_file("QmEncFolderXYZ")
      >>> print(local_file)
      /app/downloads/QmEncFolderXYZ/original_filename.bin
      
      >>> # Not a bare CID: refused, nothing is deleted
      >>> print(engine.get_file("../.."))
      None

      """
      # Accept only a bare CID (see __refuse_invalid_cid). The CID becomes a folder name under local_folder, and
      # that path is deleted below before any `ipfs` command sees the CID (the pin runs after the get), so this
      # is the only check in front of the cleanup. A '/', '.' or '..' would make the path absolute or climb out
      # of local_folder, and the cleanup would delete a path outside it.
      if self.__refuse_invalid_cid(cid, raise_on_error=raise_on_error, show_logs=show_logs):
        # Refused and logged before anything was deleted: the read fails.
        return None
      
      if secret in ["", None]:
        secret = self.__DEFAULT_SECRET
        
      key = self._hash_secret(secret)

      if local_folder is None:
        local_folder = self.__downloads_dir # default downloads directory
      
      os.makedirs(local_folder, exist_ok=True)
      
      local_folder = os.path.join(local_folder, cid) # add the CID as a subfolder
      
      # if the folder exists cleanup the content
      if os.path.exists(local_folder):
        # A link left by a crafted object (see the check after the get) is removed itself by os.remove below, never
        # followed by rmtree, when its target exists; a dangling link fails os.path.exists above and is left in place.
        if os.path.isdir(local_folder) and not os.path.islink(local_folder):
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
      download_error = None
      try:
        self.__run_command(
          ["ipfs", "get", cid, "-o", local_folder],
          timeout=ipfs_timeout,
          raise_on_error=True,
          show_logs=show_logs
        )
      except Exception as e:
        download_error = str(e)
        self.P(f"Initial ipfs get failed for {cid}: {download_error}", color='y')
        # Read the CID's relay status now: the background heal started below marks it unpublished while it runs.
        self.__report_relay_data_path(cid, start_time)
      # Relay work never runs on the reader's thread. A CID this get missed is remembered for the background
      # pass, which asks the relay to fetch it so a later read can find it.
      self.__relay_in_background(heal_cid=cid if download_error else None, show_logs=show_logs)
      if download_error is not None:
        if raise_on_error:
          raise RuntimeError(f"Failed to download CID {cid}: {download_error}")
        self.P(f"Failed to download CID {cid}: {download_error}", color='r')
        return None
      download_elapsed_time = time.time() - start_time
      if pin:
        # Pin after the get, so the caller's timeout (not a fixed 90 s pin) bounds the network fetch. The pin
        # is quick when the blocks the get stored are still local; a repository garbage collection between
        # the get and the pin removes them, and the pin then has to fetch them again.
        try:
          # Give the pin only the time the read has left (at least 1 s), not a second full window, so the get
          # and the pin together take about the caller's timeout at most. A failure only logs: the data is
          # already on disk, so the read goes on.
          self.__pin_add(cid, timeout=max(1, ipfs_timeout - download_elapsed_time))
        except Exception as e:
          # Red, not yellow: the read returns the file, but the pin failed and nothing retries it.
          self.P(f"Pin after download failed for {cid}: {e}", color='r')

      # Expect exactly one file
      # A CID whose root is a symlink makes `ipfs get` write local_folder itself as a link to another folder: refused
      # here, so nothing is read, written or deleted there and the except below never runs rmtree on a link.
      if os.path.islink(local_folder) or not os.path.isdir(local_folder):
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
        # `ipfs get` writes a UnixFS symlink entry as a link to any path of this node, and opening it reads that path
        # (a device or a pipe included). An R1FS object is one regular file: anything else is refused, and the except
        # below removes the folder together with the link.
        if os.path.islink(cipher_path) or not os.path.isfile(cipher_path):
          # Into the except below, before anything is opened.
          raise ValueError(f"{contents[0]!r} is not a regular file")
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
          # Whoever added the object chose this name, and the plaintext is written under it: only a plain file
          # name keeps it inside local_folder. A refused name raises into the error path below.
          self.__refuse_unplain_name(original_filename, raise_on_error=True)

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
        # The tag is checked only after all plaintext was written, so a failed read can leave unauthenticated
        # plaintext next to the ciphertext. This call made local_folder and only those two are in it: remove it,
        # so nothing unverified stays on disk (the ciphertext removal below is then skipped).
        shutil.rmtree(local_folder)
        msg = f"Error decrypting file {cipher_path}: {e}"
        if raise_on_error:
          raise RuntimeError(msg)
        else:
          self.P(msg, color='r')
          return
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
          The CID to check. A value that is set must be a bare CID: a non-empty
          string of at most 255 ASCII letters and digits.

      max_wait : int
          The maximum time to wait for the CID to be found.
          
      Returns
      -------
      bool
          True when ``ipfs block stat`` finds the CID within ``max_wait`` seconds;
          False when it does not, or when ``cid`` is refused.

      Notes
      -----
      A ``cid`` that is set but is not a bare CID (a path such as ``/ipfs/<cid>``, an
      option such as ``--help``) is refused before the ``ipfs`` command runs and
      logged in red. ``None`` and ``""`` are handled as before.

      Examples
      --------
      >>> engine.is_cid_available("QmHash123", max_wait=3)
      True
      """
      # Accept only a bare CID (see __refuse_invalid_cid): the CID goes on the `ipfs block stat` command line.
      # None and "" are left to the command as before.
      if cid not in (None, "") and self.__refuse_invalid_cid(cid):
        # Refused and logged: not available, the method's answer for any failure.
        return False
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
            The CID to check. A value that is set must be a bare CID: a non-empty
            string of at most 255 ASCII letters and digits.

        show_logs : bool, optional
            Whether to show logs. Default is False.

        Returns
        -------
        bool
            True if the CID is pinned, False otherwise (a refused ``cid`` included).

        Notes
        -----
        A ``cid`` that is set but is not a bare CID (a path such as ``/ipfs/<cid>``, an
        option such as ``--help``) is refused before the ``ipfs`` command runs and
        logged in red whatever ``show_logs`` is. ``None`` and ``""`` are handled as
        before.

        Examples
        --------
        >>> if engine.is_pinned("QmHash123..."):
        >>>   print("File is pinned")
        """
        # Accept only a bare CID (see __refuse_invalid_cid): the CID goes on the `ipfs pin ls` command line.
        # None and "" are left to the command as before.
        if cid not in (None, "") and self.__refuse_invalid_cid(cid):
          # Refused and logged: not pinned, the method's answer for any failure.
          return False
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
            The CID to unpin. It must be a bare CID: a non-empty string of at most
            255 ASCII letters and digits (CIDv0 ``Qm...`` or CIDv1 in base32 / base36).

        unpin_remote : bool, optional
            Whether to also unpin from the relay. Default is True.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        raise_on_error : bool, optional
            If True, raise an Exception on errors. Otherwise logs them. Default is False.

        Returns
        -------
        bool
            True if unpinning was successful, a CID that is not pinned on this node
            included; False otherwise (a refused ``cid`` or a failed local
            ``ipfs pin rm`` included, when raise_on_error=False).

        Raises
        ------
        ValueError
            With ``raise_on_error=True``, when ``cid`` is ``None``, empty or not a
            bare CID.
        RuntimeError
            With ``raise_on_error=True``, when the local ``ipfs pin rm`` fails for a
            reason other than Kubo's "not pinned", or the relay pin/rm is refused,
            fails or times out.

        Notes
        -----
        The local ``ipfs pin rm`` has three outcomes. It unpins the CID; or Kubo
        answers "not pinned or pinned indirectly" (``IPFSCt.NOT_PINNED_ERROR``): this
        node holds no direct or recursive pin of it, which is normal for a CID it
        never pinned, so there is nothing to unpin here and the unpin goes on to the
        relay, whatever ``raise_on_error`` is; or it fails (the daemon does not
        answer, a timeout, a lock). A failure is raised as ``RuntimeError`` with
        ``raise_on_error=True``; otherwise it is logged in red whatever ``show_logs``
        is and False is returned. Either way the relay is not told and the CID keeps
        its relay retry queue entry and waiting heal, since it may still be pinned
        here. (Before, with ``raise_on_error=False`` a failure passed as an unpin.)

        The relay pin/rm request is bounded by ``IPFSCt.RELAY_PIN_TIMEOUT_SECONDS``,
        like relay pin/add, so a hung relay API cannot hold the caller forever. A
        timed-out relay request is reported as a failed unpin (or raised as
        ``RuntimeError`` with ``raise_on_error=True``) after the local ``ipfs pin rm``
        has already run. Once the local ``ipfs pin rm`` unpins the CID or answers that
        it is not pinned, the CID leaves the relay retry queue and the set of CIDs
        waiting for a relay heal after a failed read, before the relay call and
        whatever its result, so the background relay pass neither publishes nor heals
        it when its turn comes.

        A relay pin/add of this CID that the background pass is sending at that
        moment (a heal it already took from the set, or a queued publication) could
        reach the relay after this unpin's relay pin/rm. When the relay is told to
        unpin (``unpin_remote`` and a relay API), that request is marked through
        ``__relay_in_flight``: the pass sends no further attempt, records nothing,
        does not queue the CID again, and undoes a pin the relay accepted with one
        relay pin/rm (``__undo_relay_pin``, skipped if the CID is pinned on this node
        again by then, and followed by one more publication if it is pinned here
        again once the pin/rm was sent). The mark lives only while that request runs.
        Still open: a read that fails after the delete asks the relay to fetch the CID
        again (older behaviour, kept because the same content is uploaded again under
        the same CID); a heal waiting on another node cannot be reached from this
        process; a marked pin/add whose attempt got no answer (timeout, connection
        error) is not undone, so a relay that completes that pin after this unpin's
        pin/rm keeps the CID; and a relay pin/add sent by ``add_file`` on another
        thread at the same time is not tracked either.
        With ``unpin_remote=False`` the relay keeps its copy and nothing is marked.

        A ``cid`` that is set but is not a bare CID (``/ipfs/<cid>``, ``-r``,
        ``QmA&arg=QmB``) is refused before the local ``ipfs pin rm`` and the relay
        request, and logged in red whatever ``show_logs`` is; ``None`` and ``""`` are
        refused as before, with their own message. The relay request is
        ``POST <relay api>/api/v0/pin/rm`` with the CID as its ``arg`` query parameter
        (requests' ``params``): for a bare CID the URL is the same as before,
        ``.../api/v0/pin/rm?arg=<cid>``.

        Examples
        --------
        >>> # Unpin locally and on relay
        >>> engine.unpin_file("QmHash123...")

        >>> # Unpin only locally
        >>> engine.unpin_file("QmHash123...", unpin_remote=False)

        >>> # Not a bare CID: refused before any command or relay request
        >>> engine.unpin_file("/ipfs/QmHash123", show_logs=False)
        False
        """
        if cid in [None, ""]:
          msg = "CID parameter cannot be None or empty"
          if raise_on_error:
            raise ValueError(msg)
          else:
            if show_logs:
              self.P(msg, color='r')
            return False
        # Accept only a bare CID (see __refuse_invalid_cid): the CID goes on the `ipfs pin rm` command line and
        # into the relay pin/rm request. None and "" were refused just above with their own message.
        if self.__refuse_invalid_cid(cid, raise_on_error=raise_on_error):
          # Refused and logged before any command or relay request: the unpin fails.
          return False

        success = True

        try:
          # First, unpin locally
          result = self.__run_command(
            ["ipfs", "pin", "rm", cid],
            # Raise on any failure, whatever raise_on_error is: with False a failed command returned "" and a daemon
            # that did not answer passed as an unpin. The except below tells Kubo's "not pinned" apart.
            raise_on_error=True,
            show_logs=False
          )

          if show_logs:
            self.Pd(f"Unpinned CID locally: {cid}")

        except Exception as e:
          msg = f"Error unpinning CID {cid} locally: {e}"
          if IPFSCt.NOT_PINNED_ERROR in str(e):
            # Kubo's answer when this node holds no direct or recursive pin of the CID: nothing to unpin here, a
            # normal call for a CID this node never pinned, so the unpin goes on to the relay as before.
            if show_logs:
              self.Pd(f"CID {cid} was not pinned locally: {e}")
          elif raise_on_error:
            raise RuntimeError(msg)
          else:
            # A real failure (the daemon did not answer, a timeout, a lock): the CID may still be pinned here, so
            # the relay is not told and the queue entry and waiting heal of the CID stay. Said in red whatever
            # show_logs is: most callers pass show_logs=False and look only at the result, if at all.
            self.P(msg, color='r')
            return False

        # The local `ipfs pin rm` unpinned the CID or found no pin of it: drop the CID from the relay retry queue now,
        # before the relay call, so a failed or timed-out relay pin/rm cannot leave it queued for the
        # background pass to publish to the relay again.
        self.__relay_retry_queue.pop(cid, None)
        # Drop a heal that a failed read of this CID left waiting for the background pass, for the same
        # reason: that heal is a relay pin/add and would pin the CID on the relay again after this unpin.
        self.__relay_heal_pending.discard(cid)

        # Then, notify the relay to unpin (mirrors add_file behavior)
        if unpin_remote and self.__ipfs_relay_api is not None:
          # A relay pin/add of this CID that the background pass is sending now (a heal it took from the set, or a
          # queued publication) can reach the relay after the pin/rm below. The pass shows its request here before
          # it reads the queue entry or takes the CID from the set, and the two drops above come before this look:
          # either the pass found the CID gone, or this finds its request.
          flight = self.__relay_in_flight
          if flight is not None and flight[0] == cid:
            # Mark it: the pass then records nothing, does not queue the CID again, and undoes a pin that got through.
            flight[1] = True
          # Drop the CID from the queue once more, after the mark: the pass reads the mark again right after it
          # queues a failed CID, so a CID it queued before seeing the mark is queued before this drop.
          self.__relay_retry_queue.pop(cid, None)
          try:
            # No CID in the URL text: it goes in params below, which requests percent-encodes. For a bare CID the
            # relay gets the same URL as before, character for character.
            request_url = f"{self.__ipfs_relay_api}/api/v0/pin/rm"
            response = requests.post(
              request_url,
              # The CID as the `arg` query parameter of the relay's pin/rm (see request_url above).
              params={"arg": cid},
              auth=HTTPBasicAuth(self.__ipfs_api_key_username, self.__ipfs_api_key_password),
              # Verified with the configured certificate file. When the path is None, requests applies its default
              # certificate check (its CA bundle, or the one REQUESTS_CA_BUNDLE or CURL_CA_BUNDLE names), the same
              # check relay pin/add gets from __relay_verify_value.
              verify=self.__ipfs_certificate_path,
              # Bound the relay pin/rm like relay pin/add: without a timeout a hung relay API holds the caller
              # (delete_file included) forever. The RequestException handler below turns it into a failed unpin.
              timeout=IPFSCt.RELAY_PIN_TIMEOUT_SECONDS,
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
          self.__relay_publication_status.pop(cid, None)
          self.__relay_retry_queue.pop(cid, None)

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
            The CID to delete. It must be a bare CID: a non-empty string of at
            most 255 ASCII letters and digits (CIDv0 ``Qm...`` or CIDv1 in base32 /
            base36). Path forms such as ``/ipfs/<cid>`` are refused.

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
            True if deletion was successful, False otherwise (an invalid
            ``cid`` included, when raise_on_error=False).

        Raises
        ------
        ValueError
            If ``cid`` is not a bare CID and raise_on_error=True.

        RuntimeError
            If unpinning or another step fails and raise_on_error=True.

        Notes
        -----
        ``cid`` is checked before anything else: with ``cleanup_local_files``
        the path ``<downloads dir>/<cid>`` is deleted, so a ``cid`` such as
        ``/abs/path`` or ``..`` would name a path outside the downloads folder.
        Such a ``cid`` is refused with nothing unpinned and nothing deleted, and
        unless it is None or "" it is logged in red whatever ``show_logs`` is.
        ``delete_files`` calls this method for each CID and inherits the check.

        A CID that is not pinned on this node (Kubo's "not pinned or pinned
        indirectly") is not an error: the delete goes on to the relay and the
        cleanup, whatever ``raise_on_error`` is. When the local ``ipfs pin rm``
        fails (the daemon does not answer, a timeout), nothing is cleaned up and no
        GC runs: with raise_on_error=False ``unpin_file`` logs the failure in red
        whatever ``show_logs`` is and False is returned; with raise_on_error=True a
        RuntimeError is raised and nothing is logged.

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

        >>> # Not a bare CID: refused before anything is unpinned or deleted
        >>> engine.delete_file("../..", unpin_remote=False, cleanup_local_files=True)
        False
        """
        # Accept only a bare CID (see __refuse_invalid_cid) before unpinning or cleanup. With cleanup_local_files
        # the CID is joined to the downloads folder and that path is deleted; a '/', '.' or '..' would point it
        # outside the folder.
        if self.__refuse_invalid_cid(cid, raise_on_error=raise_on_error, show_logs=show_logs):
          # Refused and logged before anything was unpinned or deleted: the delete fails.
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
            Specific CID to clean up. If None, cleans all downloads. Any other
            non-empty value must be a bare CID: at most 255 ASCII letters and
            digits.

        show_logs : bool, optional
            Whether to show logs. Default is True.

        Returns
        -------
        int
            Number of items cleaned up (0 for a refused ``cid``).

        Notes
        -----
        The path ``<downloads dir>/<cid>`` is deleted, so a ``cid`` such as
        ``/abs/path`` or ``..`` would name a path outside the downloads folder. A
        ``cid`` that is set but is not a bare CID is refused before anything is
        deleted and logged in red whatever ``show_logs`` is. ``None`` and ``""`` are
        handled as before.

        Examples
        --------
        >>> # Clean up all downloaded files
        >>> count = engine.cleanup_downloads()
        >>> print(f"Cleaned up {count} files")

        >>> # Clean up specific CID's downloads
        >>> engine.cleanup_downloads(cid="QmHash123...")

        >>> # Not a bare CID: refused, nothing is deleted
        >>> engine.cleanup_downloads(cid="../..")
        0
        """
        # Accept only a bare CID (see __refuse_invalid_cid): the CID is joined to the downloads folder and that path
        # is deleted, so a '/', '.' or '..' would delete outside it. None and "" are handled below as before.
        if cid not in (None, "") and self.__refuse_invalid_cid(cid):
          # Refused and logged before anything was deleted: nothing cleaned up.
          return 0
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
          It must be a plain file name (no path part, not '', '.' or '..'): it is
          written in a unique temporary directory and removed afterwards.
          
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
          If nonce is None or invalid, if data cannot be JSON serialized, or if
          ``fn`` is not a plain file name (checked before anything is written).
          
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
      
      if show_logs:
        self.P(f"JSON data: {json_data}")

      if fn is not None:
        # Only a plain file name stays inside the unique folder it is joined to below; an absolute or '..' name
        # would be written, then removed, outside it. Refused with ValueError, like data that cannot be serialized.
        self.__refuse_unplain_name(fn, raise_on_error=True)

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
          show_logs=show_logs,
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
          A name the caller gives must be a plain file name (no path part, not '',
          '.' or '..'): it is written in a unique temporary directory and removed
          afterwards.
          
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
          If nonce is None or invalid, if data cannot be pickled, or if a given
          ``fn`` is not a plain file name (checked before anything is written).

      Notes
      -----
      Only the caller's ``fn`` is checked. The unique name used when ``fn`` is None is
      a full path in the uploads directory, and the file is written there, as before.
          
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

      if fn is not None:
        # Only a plain file name stays inside the unique folder it is joined to below; an absolute or '..' name
        # would be written, then removed, outside it. Checked before the default below, a full path on purpose.
        self.__refuse_unplain_name(fn, raise_on_error=True)

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
      Initialize the local IPFS repo and attach it to the configured relay.
      TODO: (Vitalii) Split this into smaller methods.

      Parameters
      ----------
      base64_swarm_key : str, optional
          Base64-encoded swarm key. Falls back to
          ``EE_SWARM_KEY_CONTENT_BASE64`` when omitted.
      ipfs_relay : str, optional
          Relay multiaddr. Falls back to ``EE_IPFS_RELAY`` when omitted.
      ipfs_relay_api : str, optional
          Relay API endpoint. Falls back to ``EE_IPFS_RELAY_API`` when omitted.
      ipfs_api_key_username : str, optional
          Relay API username. Decoded from ``EE_IPFS_API_KEY_BASE64`` when
          omitted.
      ipfs_api_key_password : str, optional
          Relay API password. Decoded from ``EE_IPFS_API_KEY_BASE64`` when
          omitted.
      ipfs_certificate_path : str, optional
          TLS certificate file path. Materialized from
          ``EE_IPFS_CERTIFICATE_BASE64`` when omitted.

      Returns
      -------
      bool
          ``True`` when the daemon is running and connected to the relay,
          otherwise ``False``.
      """
      if self.ipfs_started:
        return
      self.__samehost_fix_attempted = False
      
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
        else:
          self.P(
            "Relay API endpoint is not configured. Local R1FS uploads will work, "
            "but fresh CID publication and download self-heal cannot use the relay API.",
            color='y'
          )

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
      if not ipfs_api_key_username or not ipfs_api_key_password:
        self.P(
          "Relay API credentials are not configured. Local R1FS uploads will continue, "
          "but relay publication retries and self-heal are disabled.",
          color='y'
        )


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
      if not ipfs_certificate_path:
        self.P(
          "Relay certificate is not configured. Relay API requests will rely on the system trust store.",
          color='y'
        )

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

      if not self.__samehost_fix_enabled():
        self.__cleanup_samehost_relay_workaround()

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
          self.__set_reprovider_strategy()
          self.__disable_auto_tls()
          self.__set_routing_type()
          self.__disable_ws_transport()
          self.__disable_mdns_discovery()
          self.__bootstrap_add(self.__ipfs_relay)
          ipfs_daemon_running = self.__start_daemon()
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
        # endif at least 1 swarm peer
        
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
        # endif ipfs not started

        if self.__ipfs_started and self.__maybe_apply_samehost_relay_workaround():
          self.P("Reconnecting to relay after same-host relay workaround restart...", color='m')
          my_id = self.__get_id()
          relay_found = self._check_and_record_relay_connection(debug=True)
          if not relay_found:
            success, output, errors = self.__swarm_connect(ipfs_relay)
            if not success:
              self.P(f"Error reconnecting to relay after restart: {errors or output}", color='r')
              self.__ipfs_started = False
            else:
              self.__ipfs_started = True
              self._check_and_record_relay_connection(debug=True)
          else:
            self.__ipfs_started = True
          if self.__ipfs_started:
            self.P(f"{my_id} connected to: {relay_ip}", color='g', boxed=True)
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
