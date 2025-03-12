"""

TODO: 
  - config precedence when starting a session - env vs manually provided data
  - add support for remaining commands from EE


"""

import json
import os
import traceback
import pandas as pd

from collections import deque, OrderedDict
from datetime import datetime as dt
from threading import Lock, Thread
from time import sleep
from time import time as tm

from ..base_decentra_object import BaseDecentrAIObject
from ..bc import DefaultBlockEngine, _DotDict, EE_VPN_IMPL
from ..const import (
  COMMANDS, ENVIRONMENT, HB, PAYLOAD_DATA, STATUS_TYPE, 
  PLUGIN_SIGNATURES, DEFAULT_PIPELINES,
  BLOCKCHAIN_CONFIG, SESSION_CT, NET_CONFIG
)
from ..const import comms as comm_ct
from ..io_formatter import IOFormatterWrapper
from ..logging import Logger
from ..utils import load_dotenv
from .payload import Payload
from .pipeline import Pipeline
from .webapp_pipeline import WebappPipeline
from .transaction import Transaction
from ..utils.config import (
  load_user_defined_config, get_user_config_file, get_user_folder, 
  seconds_to_short_format, log_with_color, set_client_alias,
  EE_SDK_ALIAS_ENV_KEY, EE_SDK_ALIAS_DEFAULT
)

# from ..default.instance import PLUGIN_TYPES # circular import



DEBUG_MQTT_SERVER = "r9092118.ala.eu-central-1.emqxsl.com"
SDK_NETCONFIG_REQUEST_DELAY = 300
SHOW_PENDING_THRESHOLD = 3600



class GenericSession(BaseDecentrAIObject):
  """
  A Session is a connection to a communication server which provides the channel to interact with nodes from the ratio1 Edge Protocol network.
  A Session manages `Pipelines` and handles all messages received from the communication server.
  The Session handles all callbacks that are user-defined and passed as arguments in the API calls.
  """
  
  START_TIMEOUT = 30
  
  
  default_config = {
      "CONFIG_CHANNEL": {
          "TOPIC": "{}/{}/config"
      },
      "CTRL_CHANNEL": {
          "TOPIC": "{}/ctrl"
      },
      "NOTIF_CHANNEL": {
          "TOPIC": "{}/notif"
      },
      "PAYLOADS_CHANNEL": {
          "TOPIC": "{}/payloads"
      },
      "QOS": 0,
      "CERT_PATH": None,
  }


  def __init__(
              self, *,
              host=None,
              port=None,
              user=None,
              pwd=None,
              secured=None,
              name=None,
              encrypt_comms=True,
              config={},
              filter_workers=None,
              log: Logger = None,
              on_payload=None,
              on_notification=None,
              on_heartbeat=None,
              debug_silent=True,
              debug=1,      # TODO: debug or verbosity - fix this
              verbosity=1,
              silent=False,
              dotenv_path=None,
              show_commands=False,
              blockchain_config=BLOCKCHAIN_CONFIG,
              bc_engine=None,
              formatter_plugins_locations=['plugins.io_formatters'],
              root_topic="naeural",
              local_cache_base_folder=None,
              local_cache_app_folder='_local_cache',
              use_home_folder=True,
              eth_enabled=True,
              auto_configuration=True,
              debug_env=False,              
              **kwargs
            ) -> None:
    """
    A Session is a connection to a communication server which provides the channel to interact with nodes from the ratio1 Edge Protocol network.
    A Session manages `Pipelines` and handles all messages received from the communication server.
    The Session handles all callbacks that are user-defined and passed as arguments in the API calls.

    Parameters
    ----------
    host : str, optional
        The hostname of the server. If None, it will be retrieved from the environment variable AIXP_HOSTNAME
        
    port : int, optional
        The port. If None, it will be retrieved from the environment variable AIXP_PORT
        
    user : str, optional
        The user name. If None, it will be retrieved from the environment variable AIXP_USERNAME
        
    pwd : str, optional
        The password. If None, it will be retrieved from the environment variable AIXP_PASSWORD
        
    secured: bool, optional
        True if connection is secured, by default None
        
    name : str, optional
        The name of this connection, used to identify owned pipelines on a specific ratio1 Edge Protocol edge node.
        The name will be used as `INITIATOR_ID` and `SESSION_ID` when communicating with ratio1 Edge Protocol edge nodes, by default 'pySDK'
        
    config : dict, optional
        Configures the names of the channels this session will connect to.
        If using a Mqtt server, these channels are in fact topics.
        Modify this if you are absolutely certain of what you are doing.
        By default {}
        
    filter_workers: list, optional
        If set, process the messages that come only from the nodes from this list.
        Defaults to None
        
    show_commands : bool
        If True, will print the commands that are being sent to the ratio1 Edge Protocol edge nodes.
        Defaults to False
        
    log : Logger, optional
        A logger object which implements basic logging functionality and some other utils stuff. Can be ignored for now.
        In the future, the documentation for the Logger base class will be available and developers will be able to use
        custom-made Loggers.
        
    on_payload : Callable[[Session, str, str, str, str, dict], None], optional
        Callback that handles all payloads received from this network.
        As arguments, it has a reference to this Session object, the node name, the pipeline, signature and instance, and the payload.
        This callback acts as a default payload processor and will be called even if for a given instance
        the user has defined a specific callback.
        
    on_notification : Callable[[Session, str, dict], None], optional
        Callback that handles notifications received from this network.
        As arguments, it has a reference to this Session object, the node name and the notification payload.
        This callback acts as a default payload processor and will be called even if for a given instance
        the user has defined a specific callback.
        This callback will be called when there are notifications related to the node itself, e.g. when the node runs
        low on memory.
        Defaults to None.
        
    on_heartbeat : Callable[[Session, str, dict], None], optional
        Callback that handles heartbeats received from this network.
        As arguments, it has a reference to this Session object, the node name and the heartbeat payload.
        Defaults to None.
        
    debug_silent : bool, optional 
        This flag will disable debug logs, set to 'False` for a more verbose log, by default True
        Observation: Obsolete, will be removed
        
    debug : bool or int, optional
        This flag will enable debug logs, set to 'True` or 2 for a more verbose log, by default 1
        - 0 or False will disable debug logs
        - 1 will enable level 1
        - 2 will enable full debug
        
        
        
    silent : bool, optional
        This flag will disable all logs, set to 'False` for a more verbose log, by default False
        The logs will still be recored in the log file even if this flag is set to True.
        
    dotenv_path : str, optional
        Path to the .env file, by default None. If None, the path will be searched in the current working directory and in the directories of the files from the call stack.
    root_topic : str, optional
        This is the root of the topics used by the SDK. It is used to create the topics for the communication channels.
        Defaults to "ratio1"
        
    auto_configuration : bool, optional
        If True, the SDK will attempt to complete the dauth process automatically.
        Defaults to True.
        
        
    use_home_folder : bool, optional
        If True, the SDK will use the home folder as the base folder for the local cache.
        NOTE: if you need to use development style ./_local_cache, set this to False.
    """
    
    # TODO: clarify verbosity vs debug
    
    debug = debug or not debug_silent
    if isinstance(debug, bool):
      debug = 2 if debug else 0
      
    if verbosity > 1 and debug <=1:
      debug = 2
    
    self.__debug = int(debug) > 0
    self._verbosity = verbosity
    
    if self.__debug:
      if not silent:
        log_with_color(f"Debug mode enabled: {debug=}, {verbosity=}", color='y')
    
    ### END verbosity fix needed
    
    self.__debug_env = debug_env
    
    self.__at_least_one_node_peered = False
    self.__at_least_a_netmon_received = False
    
    # TODO: maybe read config from file?
    self._config = {**self.default_config, **config}
    
    
    
    self.comms_root_topic = root_topic
    
    self.__auto_configuration = auto_configuration

    self.log = log
          
    
    self.name = name
    self.silent = silent

    self._eth_enabled = eth_enabled

    self.encrypt_comms = encrypt_comms

    self._dct_online_nodes_pipelines: dict[str, Pipeline] = {}
    self._dct_online_nodes_last_heartbeat: dict[str, dict] = {}
    self._dct_node_whitelist: dict[str, list] = {}
    self._dct_can_send_to_node: dict[str, bool] = {}
    self._dct_node_last_seen_time = {} # key is node address
    self.__dct_node_address_to_alias = {}
    self.__dct_node_eth_addr_to_node_addr = {}

    self._dct_netconfig_pipelines_requests = {}
    
    self.online_timeout = 60
    self.filter_workers = filter_workers
    self.__show_commands = show_commands
    
    # this is used to store data received from net-mon instances
    self.__current_network_statuses = {} 

    self.__pwd = pwd or kwargs.get('password', kwargs.get('pass', None))
    self.__user = user or kwargs.get('username', None)
    self.__host = host or kwargs.get('hostname', None)
    self.__port = port
    self.__secured = secured
    

    self.custom_on_payload = on_payload
    self.custom_on_heartbeat = on_heartbeat
    self.custom_on_notification = on_notification

    self.own_pipelines = []

    self.__running_callback_threads = False
    self.__running_main_loop_thread = False
    self.__closed_everything = False

    self.__formatter_plugins_locations = formatter_plugins_locations

    self.__blockchain_config = blockchain_config
    
    self.__dotenv_path = dotenv_path
    
    self.__bc_engine : DefaultBlockEngine = bc_engine
    self.bc_engine : DefaultBlockEngine = None 
    
    

    self.__open_transactions: list[Transaction] = []
    self.__open_transactions_lock = Lock()

    self.__create_user_callback_threads()
    
    if local_cache_app_folder is None:
      local_cache_app_folder = '_local_cache'
    #

    if os.path.exists(os.path.join(".", local_cache_app_folder)) and local_cache_base_folder is None:
      local_cache_base_folder = '.'
    # end if
    
    if local_cache_base_folder is None or use_home_folder:
      # use_home_folder allows us to use the home folder as the base folder
      local_cache_base_folder = str(get_user_folder())
    # end if

    ## 1st config step before anything else - we prepare config via ~/.ratio1/config or .env
    self.__load_user_config(dotenv_path=self.__dotenv_path)
    
      
    super(GenericSession, self).__init__(
      log=log, 
      DEBUG=int(debug) > 1, 
      create_logger=True,
      silent=self.silent,
      local_cache_base_folder=local_cache_base_folder,
      local_cache_app_folder=local_cache_app_folder,
    )
    return
  
  def Pd(self, *args, verbosity=1, **kwargs):
    if self.__debug and verbosity <= self._verbosity:
      kwargs["color"] = 'd' if kwargs.get("color") != 'r' else 'r'
      kwargs['forced_debug'] = True
      self.D(*args, **kwargs)
    return
  

  def startup(self):        

    # TODO: needs refactoring - suboptimal design
    # start the blockchain engine assuming config is already set
    
    self.__start_blockchain(
      self.__bc_engine, self.__blockchain_config, 
      user_config=self.__user_config_loaded,
    )
    
    # this next call will attempt to complete the dauth process
    dct_env = self.bc_engine.dauth_autocomplete(
      dauth_endp=None, # get from consts or env
      add_env=self.__auto_configuration,
      debug=False,
      sender_alias=self.name
    )
    # end bc_engine
    # END TODO
    
    
    str_topic = os.environ.get(ENVIRONMENT.EE_ROOT_TOPIC_ENV_KEY, self.comms_root_topic)    
    
    if str_topic != self.comms_root_topic:
      self.P(f"Changing root topic from '{self.comms_root_topic}' to '{str_topic}'", color='y')
      self.comms_root_topic = str_topic

    if self.comms_root_topic is not None:
      for key in self._config.keys():
        if isinstance(self._config[key], dict) and 'TOPIC' in self._config[key]:
          if isinstance(self._config[key]["TOPIC"], str) and self._config[key]["TOPIC"].startswith("{}"):
            nr_empty = self._config[key]["TOPIC"].count("{}")
            self._config[key]["TOPIC"] = self._config[key]["TOPIC"].format(self.comms_root_topic, *(["{}"] * (nr_empty - 1)))
    # end if root_topic

    
    ## last config step
    self.__fill_config(
      host=self.__host, 
      port=self.__port, 
      user=self.__user,
      pwd=self.__pwd, 
      secured=self.__secured,
    )
    ## end config
        
    self.formatter_wrapper = IOFormatterWrapper(
      self.log, plugin_search_locations=self.__formatter_plugins_locations
    )
    
    obfuscated_pass = self._config[comm_ct.PASS][:3] + '*' * (len(self._config[comm_ct.PASS]) - 3) 

    msg = f"Connection to {self._config[comm_ct.USER]}:{obfuscated_pass}@{self._config[comm_ct.HOST]}:{self._config[comm_ct.PORT]} {'<secured>' if self._config[comm_ct.SECURED] else '<UNSECURED>'}"
    self.P(msg, color='y')
    self._connect()

    msg = f"Created comms session '{self.name}'"
    msg += f"\n - SDK:     {self.log.version}"
    msg += f"\n - Address: {self.bc_engine.address}"
    msg += f"\n - ETH:     {self.bc_engine.eth_address}"
    msg += f"\n - Network: {self.bc_engine.evm_network}"
    msg += f"\n - Server:  {self._config[comm_ct.HOST]}:{self._config[comm_ct.PORT]}"
    msg += f"\n - Secured: {self._config[comm_ct.SECURED]}"
    msg += f"\n - User:    {self._config[comm_ct.USER]}"
    msg += f"\n - Pass:    {obfuscated_pass}"
    msg += f"\n - Root:    {self.comms_root_topic}"
    msg += f"\n - Encrypt: {'YES' if self.encrypt_comms else 'NO'}"
    self.P(msg, color='g')
    
    if not self.encrypt_comms:
      self.P(
        "Warning: Emitted messages will not be encrypted.\n"
        "This is not recommended for production environments.\n"
        "\n"
        "Please set `encrypt_comms` to `True` when creating the `Session` object.",
        color='r',
        verbosity=1,
        boxed=True,
        box_char='*',
      )

    self.__start_main_loop_thread()
    super(GenericSession, self).startup()


  def _shorten_addr(self, addr: str) -> str:
    if not isinstance(addr, str) or len(addr) < 15 or '...' in addr:
      return addr
    return addr[:11] + '...' + addr[-4:]


  # Message callbacks
  if True:
    def __create_user_callback_threads(self):
      self._payload_messages = deque()
      self._payload_thread = Thread(
        target=self.__handle_messages,
        args=(self._payload_messages, self.__on_payload),
        daemon=True
      )

      self._notif_messages = deque()
      self._notif_thread = Thread(
        target=self.__handle_messages,
        args=(self._notif_messages, self.__on_notification),
        daemon=True
      )

      self._hb_messages = deque()
      self._hb_thread = Thread(
        target=self.__handle_messages,
        args=(self._hb_messages, self.__on_heartbeat),
        daemon=True
      )

      self.__running_callback_threads = True
      self._hb_thread.start()
      self._notif_thread.start()
      self._payload_thread.start()
      return

    def __parse_message(self, dict_msg: dict):
      """
      Get the formatter from the payload and decode the message
      """
      # check if payload is encrypted
      if dict_msg.get(PAYLOAD_DATA.EE_IS_ENCRYPTED, False):
        destination = dict_msg.get(PAYLOAD_DATA.EE_DESTINATION, [])
        if not isinstance(destination, list):
          destination = [destination]
        if self.bc_engine.contains_current_address(destination):

          encrypted_data = dict_msg.get(PAYLOAD_DATA.EE_ENCRYPTED_DATA, None)
          sender_addr = dict_msg.get(comm_ct.COMM_SEND_MESSAGE.K_SENDER_ADDR, None)

          str_data = self.bc_engine.decrypt(encrypted_data, sender_addr)

          if str_data is None:
            self.D("Cannot decrypt message, dropping..\n{}".format(str_data), verbosity=2)
            return None

          try:
            dict_data = json.loads(str_data)
          except Exception as e:
            self.P("Error while decrypting message: {}".format(e), color='r', verbosity=1)
            self.D("Message: {}".format(str_data), verbosity=2)
            return None

          dict_msg = {**dict_data, **dict_msg}
          dict_msg.pop(PAYLOAD_DATA.EE_ENCRYPTED_DATA, None)
        else:
          payload_path = dict_msg.get(PAYLOAD_DATA.EE_PAYLOAD_PATH, None)
          self.D(f"Message {payload_path} is encrypted but not for this address.", verbosity=2)
        # endif message for us
      # end if encrypted

      formatter = self.formatter_wrapper \
          .get_required_formatter_from_payload(dict_msg)
      if formatter is not None:
        return formatter.decode_output(dict_msg)
      else:
        return None

    def __on_message_default_callback(self, message, message_callback) -> None:
      """
      Default callback for all messages received from the communication server.

      Parameters
      ----------
      message : str
          The message received from the communication server
      message_callback : Callable[[dict, str, str, str, str], None]
          The callback that will handle the message.
      """
      dict_msg = json.loads(message)
      # parse the message
      dict_msg_parsed = self.__parse_message(dict_msg)
      if dict_msg_parsed is None:
        return

      try:
        msg_path = dict_msg.get(PAYLOAD_DATA.EE_PAYLOAD_PATH, [None] * 4)
        # TODO: in the future, the EE_PAYLOAD_PATH will have the address, not the id
        msg_node_id, msg_pipeline, msg_signature, msg_instance = msg_path
        msg_node_addr = dict_msg.get(PAYLOAD_DATA.EE_SENDER, None)
      except:
        self.D("Message does not respect standard: {}".format(dict_msg), verbosity=2)
        return

      message_callback(dict_msg_parsed, msg_node_addr, msg_pipeline, msg_signature, msg_instance)
      return

    def __handle_messages(self, message_queue, message_callback):
      """
      Handle messages from the communication server.
      This method is called in a separate thread.

      Parameters
      ----------
      message_queue : deque
          The queue of messages received from the communication server
      message_callback : Callable[[dict, str, str, str, str], None]
          The callback that will handle the message.
      """
      while self.__running_callback_threads:
        if len(message_queue) == 0:
          sleep(0.01)
          continue
        current_msg = message_queue.popleft()
        self.__on_message_default_callback(current_msg, message_callback)
      # end while self.running

      # process the remaining messages before exiting
      while len(message_queue) > 0:
        current_msg = message_queue.popleft()
        self.__on_message_default_callback(current_msg, message_callback)
      return

    def __maybe_ignore_message(self, node_addr):
      """
      Check if the message should be ignored.
      A message should be ignored if the `filter_workers` attribute is set and the message comes from a node that is not in the list.

      Parameters
      ----------
      node_addr : str
          The address of the ratio1 Edge Protocol edge node that sent the message.

      Returns
      -------
      bool
          True if the message should be ignored, False otherwise.
      """
      return self.filter_workers is not None and node_addr not in self.filter_workers

    def __track_online_node(self, node_addr, node_id, node_eth_address=None):
      """
      Track the last time a node was seen online.

      Parameters
      ----------
      node_id : str
          The alias of the Ratio1 edge node that sent the message.
      node_addr : str
          The address of the Ratio1 edge node that sent the message.
      node_eth_address : str, optional
          The Ethereum address of the Ratio1 edge node that sent the message, by
      """
      self._dct_node_last_seen_time[node_addr] = tm()
      self.__dct_node_address_to_alias[node_addr] = node_id
      if node_eth_address is not None:
        self.__dct_node_eth_addr_to_node_addr[node_eth_address] = node_addr
      # endif node_eth address not provided - this is just for safety and it should not happen!
      return

    def __track_allowed_node_by_hb(self, node_addr, dict_msg):
      """
      Track if this session is allowed to send messages to node using hb data

      Parameters
      ----------
      node_addr : str
          The address of the ratio1 Edge Protocol edge node that sent the message.

      dict_msg : dict
          The message received from the communication server as a heartbeat of the object from netconfig
      """
      node_whitelist = dict_msg.get(HB.EE_WHITELIST, [])
      node_secured = dict_msg.get(HB.SECURED, False)
      
      client_is_allowed = self.bc_engine.contains_current_address(node_whitelist)

      self._dct_can_send_to_node[node_addr] = not node_secured or client_is_allowed or self.bc_engine.address == node_addr
      return

    def send_encrypted_payload(self, node_addr, payload, **kwargs):
      """
      TODO: move in BlockChainEngine
      Send an encrypted payload to a node.

      Parameters
      ----------
      node_addr : str or list
          The address or list of the edge node(s) that will receive the message.
          
      payload : dict
          The payload dict to be sent.
          
      **kwargs : dict
          Additional data to be sent to __prepare_message.
      """
      msg_to_send = self.__prepare_message(
        msg_data=payload,
        encrypt_message=True,
        destination=node_addr,
        **kwargs
      )
      self.bc_engine.sign(msg_to_send)
      self.P(f'Sending encrypted payload to <{self._shorten_addr(node_addr)}>', color='d')
      self._send_payload(msg_to_send)
      return

    def __request_pipelines_from_net_config_monitor(self, node_addr=None):
      """
      Request the pipelines for a node sending the payload to the 
      the net-config monitor plugin instance of that given node or nodes.
      
      
      Parameters
      ----------
      node_addr : str or list (optional)
          The address or list of the edge node(s) that sent the message.
          If None, the request will be sent to all nodes that are allowed to receive messages.
          
      OBSERVATION: 
        This method should be called without node_addr(s) as it will get all the known peered nodes
        and request the pipelines from them. Formely, this method was called following a netmon message
        however, this was not the best approach as the netmon message might contain limited amount of
        peer information is some cases.

      """
      if node_addr is None:
        node_addr = [k for k, v in self._dct_can_send_to_node.items() if v]
      # end if
      assert node_addr is not None, "Node address cannot be None"
      payload = {
        NET_CONFIG.NET_CONFIG_DATA: {
          NET_CONFIG.OPERATION: NET_CONFIG.REQUEST_COMMAND,
          NET_CONFIG.DESTINATION: node_addr,
        }
      }
      additional_data = {
        PAYLOAD_DATA.EE_PAYLOAD_PATH: [self.bc_engine.address, DEFAULT_PIPELINES.ADMIN_PIPELINE, PLUGIN_SIGNATURES.NET_CONFIG_MONITOR, None]
      }
      if isinstance(node_addr, str):
        node_addr = [node_addr]
      
      # now we filter only the nodes that have not been requested recently
      node_addr = [x for x in node_addr if self.__needs_netconfig_request(x)]
                  
      if len(node_addr) > 0:
        dest = [
          f"<{x}> '{self.__dct_node_address_to_alias.get(x, None)}'"  for x in node_addr 
        ]
        self.D(f"<NC> Sending request to:\n{json.dumps(dest, indent=2)}")    
            
        self.send_encrypted_payload(
          node_addr=node_addr, payload=payload,
          additional_data=additional_data
        )
        for node in node_addr:
          self._dct_netconfig_pipelines_requests[node] = tm()   
      # end if   
      return
    


    def __needs_netconfig_request(self, node_addr : str) -> bool:
      """
      Check if a net-config request is needed for a node.

      Parameters
      ----------
      node_addr : str
          The address of the edge node.

      Returns
      -------
      bool
          True if a net-config request is needed, False otherwise
      """
      short_addr = self._shorten_addr(node_addr)
      last_requested_by_netmon = self._dct_netconfig_pipelines_requests.get(node_addr, 0)
      elapsed = tm() - last_requested_by_netmon
      str_elapsed = f"{elapsed:.0f}s ago" if elapsed < 9999999 else "never"
      needs_netconfig_request = elapsed > SDK_NETCONFIG_REQUEST_DELAY
      if needs_netconfig_request:
        self.D(f"<NC> Node <{short_addr}> needs update as last request was {str_elapsed} > {SDK_NETCONFIG_REQUEST_DELAY}")
      else:
        self.D(f"<NC> Node <{short_addr}> does NOT need update as last request was {str_elapsed} < {SDK_NETCONFIG_REQUEST_DELAY}")
      return needs_netconfig_request

    

    def __track_allowed_node_by_netmon(self, node_addr, dict_msg):
      """
      Track if this session is allowed to send messages to node using net-mon data

      Parameters
      ----------
      node_addr : str
          The address of the edge node that sent the message.

      dict_msg : dict
          The message received from the communication server as a heartbeat of the object from netconfig
      """
      needs_netconfig = False
      node_whitelist = dict_msg.get(PAYLOAD_DATA.NETMON_WHITELIST, [])
      node_secured = dict_msg.get(PAYLOAD_DATA.NETMON_NODE_SECURED, False)
      node_online = dict_msg.get(PAYLOAD_DATA.NETMON_STATUS_KEY) == PAYLOAD_DATA.NETMON_STATUS_ONLINE
      node_alias = dict_msg.get(PAYLOAD_DATA.NETMON_EEID, None)
      node_eth_address = dict_msg.get(PAYLOAD_DATA.NETMON_ETH_ADDRESS, None)
      
      if isinstance(node_whitelist, list) and len(node_whitelist) > 0:
        self._dct_node_whitelist[node_addr] = node_whitelist
      # end if whitelist present
      
      if node_online:
        self.__track_online_node(
          node_addr=node_addr,
          node_id=node_alias,
          node_eth_address=node_eth_address
        )
      
      client_is_allowed = self.bc_engine.contains_current_address(node_whitelist)
      can_send = not node_secured or client_is_allowed or self.bc_engine.address == node_addr      
      self._dct_can_send_to_node[node_addr] = can_send
      short_addr = self._shorten_addr(node_addr)
      if can_send:
        if node_online:
          # only attempt to request pipelines if the node is online and if not recently requested
          needs_netconfig= self.__needs_netconfig_request(node_addr)
        else:
          self.D(f"<NC> Node <{short_addr}> is OFFLINE thus NOT sending net-config request")
      # endif node seen for the first time
      return needs_netconfig
    
    
    def __process_node_pipelines(
      self, 
      node_addr : str, 
      pipelines : list, 
      plugins_statuses : list
    ):
      """
      Given a list of pipeline configurations, create or update the pipelines for a node
      including the liveness of the plugins required for app monitoring      
      """
      new_pipelines = []
      if node_addr not in self._dct_online_nodes_pipelines:
        self._dct_online_nodes_pipelines[node_addr] = {}
      for config in pipelines:
        pipeline_name = config[PAYLOAD_DATA.NAME]
        pipeline: Pipeline = self._dct_online_nodes_pipelines[node_addr].get(
          pipeline_name, None
        )
        if pipeline is not None:
          pipeline._sync_configuration_with_remote(
            config={k.upper(): v for k, v in config.items()},
            plugins_statuses=plugins_statuses,
          )
        else:
          pipeline : Pipeline = self.__create_pipeline_from_config(
            node_addr=node_addr, config=config, plugins_statuses=plugins_statuses
          )
          self._dct_online_nodes_pipelines[node_addr][pipeline_name] = pipeline
          new_pipelines.append(pipeline)
      return new_pipelines

    def __on_heartbeat(self, dict_msg: dict, msg_node_addr, msg_pipeline, msg_signature, msg_instance):
      """
      Handle a heartbeat message received from the communication server.

      Parameters
      ----------
      dict_msg : dict
          The message received from the communication server

      msg_node_addr : str
          The address of the ratio1 Edge Protocol edge node that sent the message.

      msg_pipeline : str
          The name of the pipeline that sent the message.

      msg_signature : str
          The signature of the plugin that sent the message.

      msg_instance : str
          The name of the instance that sent the message.
      """
      # extract relevant data from the message

      if dict_msg.get(HB.HEARTBEAT_VERSION) == HB.V2:
        str_data = self.log.decompress_text(dict_msg[HB.ENCODED_DATA])
        data = json.loads(str_data)
        dict_msg = {**dict_msg, **data}

      self._dct_online_nodes_last_heartbeat[msg_node_addr] = dict_msg

      msg_node_id = dict_msg[PAYLOAD_DATA.EE_ID]
      msg_node_eth_addr = dict_msg.get(PAYLOAD_DATA.EE_ETH_ADDR, None)
      # track the node based on heartbeat - a normal heartbeat means the node is online
      # however this can lead to long wait times for the first heartbeat for all nodes
      self.__track_online_node(
        node_addr=msg_node_addr,
        node_id=msg_node_id,
        node_eth_address=msg_node_eth_addr
      )

      msg_active_configs = dict_msg.get(HB.CONFIG_STREAMS)
      whitelist = dict_msg.get(HB.EE_WHITELIST, [])
      if isinstance(whitelist, list) and len(whitelist) > 0:
        self._dct_node_whitelist[msg_node_addr] = whitelist
      is_allowed = self.bc_engine.contains_current_address(whitelist)
      if msg_active_configs is None:
        msg_active_configs = []      
      # at this point we dont return if no active configs are present
      # as the protocol should NOT send a heartbeat with active configs to
      # the entire network, only to the interested parties via net-config
      short_addr = self._shorten_addr(msg_node_addr)
      self.D("<HB> Received {} with {} pipelines (wl: {}, allowed: {})".format(
          short_addr, len(msg_active_configs), len(whitelist), is_allowed
        ), verbosity=2
      )

      if len(msg_active_configs) > 0:
        # this is for legacy and custom implementation where heartbeats still contain
        # the pipeline configuration.
        pipeline_names = [x.get(PAYLOAD_DATA.NAME, None) for x in msg_active_configs]
        received_plugins = dict_msg.get(HB.ACTIVE_PLUGINS, [])
        self.D(f'<HB> Processing pipelines from <{short_addr}>:{pipeline_names}', color='y')
        new_pipeliens = self.__process_node_pipelines(
          node_addr=msg_node_addr, pipelines=msg_active_configs,
          plugins_statuses=received_plugins,
        )

      # TODO: move this call in `__on_message_default_callback`
      if self.__maybe_ignore_message(msg_node_addr):
        return

      # pass the heartbeat message to open transactions
      with self.__open_transactions_lock:
        open_transactions_copy = self.__open_transactions.copy()
      # end with
      for transaction in open_transactions_copy:
        transaction.handle_heartbeat(dict_msg)

      self.__track_allowed_node_by_hb(msg_node_addr, dict_msg)

      # call the custom callback, if defined
      if self.custom_on_heartbeat is not None:
        self.custom_on_heartbeat(self, msg_node_addr, dict_msg)

      return

    def __on_notification(self, dict_msg: dict, msg_node_addr, msg_pipeline, msg_signature, msg_instance):
      """
      Handle a notification message received from the communication server.

      Parameters
      ----------
      dict_msg : dict
          The message received from the communication server
      msg_node_addr : str
          The address of the ratio1 Edge Protocol edge node that sent the message.
      msg_pipeline : str
          The name of the pipeline that sent the message.
      msg_signature : str
          The signature of the plugin that sent the message.
      msg_instance : str
          The name of the instance that sent the message.
      """
      # extract relevant data from the message
      notification_type = dict_msg.get(STATUS_TYPE.NOTIFICATION_TYPE)
      notification = dict_msg.get(PAYLOAD_DATA.NOTIFICATION)

      if self.__maybe_ignore_message(msg_node_addr):
        return

      color = None
      if notification_type != STATUS_TYPE.STATUS_NORMAL:
        color = 'r'
      self.D("Received notification {} from <{}/{}>: {}"
             .format(
                notification_type,
                self._shorten_addr(msg_node_addr),
                msg_pipeline,
                notification),
             color=color,
             verbosity=2,
             )

      # call the pipeline and instance defined callbacks
      for pipeline in self.own_pipelines:
        if msg_node_addr == pipeline.node_addr and msg_pipeline == pipeline.name:
          pipeline._on_notification(msg_signature, msg_instance, Payload(dict_msg))
          # since we found the pipeline, we can stop searching
          # because the pipelines have unique names
          break

      # pass the notification message to open transactions
      with self.__open_transactions_lock:
        open_transactions_copy = self.__open_transactions.copy()
      # end with
      for transaction in open_transactions_copy:
        transaction.handle_notification(dict_msg)
      # call the custom callback, if defined
      if self.custom_on_notification is not None:
        self.custom_on_notification(self, msg_node_addr, Payload(dict_msg))

      return
    
    
    def __maybe_process_net_mon(
      self, 
      dict_msg: dict,  
      msg_pipeline : str, 
      msg_signature : str,
      sender_addr: str,
    ):
      REQUIRED_PIPELINE = DEFAULT_PIPELINES.ADMIN_PIPELINE
      REQUIRED_SIGNATURE = PLUGIN_SIGNATURES.NET_MON_01
      if msg_pipeline.lower() == REQUIRED_PIPELINE.lower() and msg_signature.upper() == REQUIRED_SIGNATURE.upper():
        # handle net mon message
        sender_addr = dict_msg.get(PAYLOAD_DATA.EE_SENDER, None)
        path = dict_msg.get(PAYLOAD_DATA.EE_PAYLOAD_PATH, [None, None, None, None])
        ee_id = dict_msg.get(PAYLOAD_DATA.EE_ID, None)
        current_network = dict_msg.get(PAYLOAD_DATA.NETMON_CURRENT_NETWORK, {})        
        if current_network:
          self.__at_least_a_netmon_received = True
          self.__current_network_statuses[sender_addr] = current_network
          online_addresses = []
          all_addresses = []
          lst_netconfig_request = []
          short_addr = self._shorten_addr(sender_addr)
          self.D(f"<NM> Processing {len(current_network)} from <{short_addr}> `{ee_id}`")
          for _ , node_data in current_network.items():
            needs_netconfig = False
            node_addr = node_data.get(PAYLOAD_DATA.NETMON_ADDRESS, None)
            all_addresses.append(node_addr)
            is_online = node_data.get(PAYLOAD_DATA.NETMON_STATUS_KEY) == PAYLOAD_DATA.NETMON_STATUS_ONLINE
            node_alias = node_data.get(PAYLOAD_DATA.NETMON_EEID, None)
            if is_online:
              # no need to call here __track_online_node as it is already called 
              # in below in __track_allowed_node_by_netmon
              online_addresses.append(node_addr)
            # end if is_online
            if node_addr is not None:
              needs_netconfig = self.__track_allowed_node_by_netmon(node_addr, node_data)
            # end if node_addr
            if needs_netconfig:
              lst_netconfig_request.append(node_addr)
          # end for each node in network map
          self.Pd(f"<NM> <{short_addr}> `{ee_id}`:  {len(online_addresses)} online of total {len(all_addresses)} nodes")
          first_request = len(self._dct_netconfig_pipelines_requests) == 0
          if len(lst_netconfig_request) > 0 or first_request:
            str_msg = "First request for" if first_request else "Requesting"
            msg = f"<NC> {str_msg} pipelines from at least {len(lst_netconfig_request)} nodes"
            if first_request:
              self.P(msg, color='y')
            else:
              self.Pd(msg, verbosity=2)            
            self.__request_pipelines_from_net_config_monitor()
          # end if needs netconfig
          nr_peers = sum(self._dct_can_send_to_node.values())
          if nr_peers > 0 and not self.__at_least_one_node_peered:                
            self.__at_least_one_node_peered = True
            self.P(
              f"<NM> Received {PLUGIN_SIGNATURES.NET_MON_01} from {sender_addr}, so far {nr_peers} peers that allow me: {json.dumps(self._dct_can_send_to_node, indent=2)}", 
              color='g'
            )
          # end for each node in network map
        # end if current_network is valid
      # end if NET_MON_01
      return

    def __maybe_process_net_config(
      self, 
      dict_msg: dict,  
      msg_pipeline : str, 
      msg_signature : str,
      sender_addr: str,
    ):
      # TODO: bleo if session is in debug mode then for each net-config show what pipelines have
      # been received
      REQUIRED_PIPELINE = DEFAULT_PIPELINES.ADMIN_PIPELINE
      REQUIRED_SIGNATURE = PLUGIN_SIGNATURES.NET_CONFIG_MONITOR
      if msg_pipeline.lower() == REQUIRED_PIPELINE.lower() and msg_signature.upper() == REQUIRED_SIGNATURE.upper():
        # extract data
        sender_addr = dict_msg.get(PAYLOAD_DATA.EE_SENDER, None)
        short_sender_addr = sender_addr[:8] + '...' + sender_addr[-4:]
        if self.client_address == sender_addr:
          self.D("<NC> Ignoring message from self", color='d')
          return
        receiver = dict_msg.get(PAYLOAD_DATA.EE_DESTINATION, None)
        if not isinstance(receiver, list):
          receiver = [receiver]
        path = dict_msg.get(PAYLOAD_DATA.EE_PAYLOAD_PATH, [None, None, None, None])
        ee_id = dict_msg.get(PAYLOAD_DATA.EE_ID, None)
        op = dict_msg.get(NET_CONFIG.NET_CONFIG_DATA, {}).get(NET_CONFIG.OPERATION, "UNKNOWN")
        # drop any incoming request as we are not a net-config provider just a consumer
        if op == NET_CONFIG.REQUEST_COMMAND:
          self.Pd(f"<NC> Dropping request from <{short_sender_addr}> `{ee_id}`")
          return
        
        # check if I am allowed to see this payload
        if not self.bc_engine.contains_current_address(receiver):
          self.P(f"<NC> Received `{op}` from <{short_sender_addr}> `{ee_id}` but I am not in the receiver list: {receiver}", color='d')
          return                

        # encryption check. By now all should be decrypted
        is_encrypted = dict_msg.get(PAYLOAD_DATA.EE_IS_ENCRYPTED, False)
        if not is_encrypted:
          self.P(f"<NC> Received from <{short_sender_addr}> `{ee_id}` but it is not encrypted", color='r')
          return
        net_config_data = dict_msg.get(NET_CONFIG.NET_CONFIG_DATA, {})
        received_pipelines = net_config_data.get(NET_CONFIG.PIPELINES, [])
        received_plugins = net_config_data.get(NET_CONFIG.PLUGINS_STATUSES, [])
        self.D(f"<NC> Received {len(received_pipelines)} pipelines from <{sender_addr}> `{ee_id}`")
        if self._verbosity > 2:
          self.D(f"<NC> {ee_id} Netconfig data:\n{json.dumps(net_config_data, indent=2)}")
        new_pipelines = self.__process_node_pipelines(
          node_addr=sender_addr, pipelines=received_pipelines,
          plugins_statuses=received_plugins
        )
        pipeline_names = [x.name for x in new_pipelines]
        if len(new_pipelines) > 0:
          self.P(f'<NC>   Received NEW pipelines from <{sender_addr}> `{ee_id}`:{pipeline_names}', color='y')
      return True
      

    # TODO: maybe convert dict_msg to Payload object
    #       also maybe strip the dict from useless info for the user of the sdk
    #       Add try-except + sleep
    def __on_payload(
      self, 
      dict_msg: dict, 
      msg_node_addr, 
      msg_pipeline, 
      msg_signature, 
      msg_instance
    ) -> None:
      """
      Handle a payload message received from the communication server.

      Parameters
      ----------
      dict_msg : dict
          The message received from the communication server
          
      msg_node_addr : str
          The address of the ratio1 Edge Protocol edge node that sent the message.
          
      msg_pipeline : str
          The name of the pipeline that sent the message.
          
      msg_signature : str
          The signature of the plugin that sent the message.
          
      msg_instance : str
          The name of the instance that sent the message.
      """
      # extract relevant data from the message
      msg_data = dict_msg

      if self.__maybe_ignore_message(msg_node_addr):
        return
      
      self.__maybe_process_net_mon(
        dict_msg=dict_msg, 
        msg_pipeline=msg_pipeline, 
        msg_signature=msg_signature, 
        sender_addr=msg_node_addr
      )

      self.__maybe_process_net_config(
        dict_msg=dict_msg, 
        msg_pipeline=msg_pipeline, 
        msg_signature=msg_signature, 
        sender_addr=msg_node_addr
      )

      # call the pipeline and instance defined callbacks
      for pipeline in self.own_pipelines:
        if msg_node_addr == pipeline.node_addr and msg_pipeline == pipeline.name:
          pipeline._on_data(msg_signature, msg_instance, Payload(dict_msg))
          # since we found the pipeline, we can stop searching
          # because the pipelines have unique names
          break

      # pass the payload message to open transactions
      with self.__open_transactions_lock:
        open_transactions_copy = self.__open_transactions.copy()
      # end with
      for transaction in open_transactions_copy:
        transaction.handle_payload(dict_msg)
      if self.custom_on_payload is not None:
        self.custom_on_payload(
          self,  # session
          msg_node_addr,    # node_addr
          msg_pipeline,     # pipeline
          msg_signature,    # plugin signature
          msg_instance,     # plugin instance name
          Payload(msg_data) # the actual payload
        )

      return

  # Main loop
  if True:
    def __start_blockchain(self, bc_engine, blockchain_config, user_config=False):
      if bc_engine is not None:
        self.bc_engine = bc_engine        
        return

      try:
        if EE_VPN_IMPL and self._eth_enabled:
          self.P("Disabling ETH for VPN implementation", color='r')
          self._eth_enabled = False
        
        self.bc_engine = DefaultBlockEngine(
          log=self.log,
          name=self.name,
          config=blockchain_config,
          verbosity=self._verbosity,
          user_config=user_config,
          eth_enabled=self._eth_enabled, 
        )
      except:
        raise ValueError("Failure in private blockchain setup:\n{}".format(traceback.format_exc()))
      
      # extra setup flag for re-connections with same multiton instance
      self.bc_engine.set_eth_flag(self._eth_enabled)
      return

    def __start_main_loop_thread(self):
      self._main_loop_thread = Thread(target=self.__main_loop, daemon=True)

      self.__running_main_loop_thread = True
      self._main_loop_thread.start()
      
      start_wait = tm()
      while not self.__at_least_a_netmon_received:
        if (tm() - start_wait) > self.START_TIMEOUT:
          msg = "Timeout waiting for NET_MON_01 message. No connections. Exiting..."
          self.P(msg, color='r', show=True)
          break
        sleep(0.1)
      if self.__at_least_a_netmon_received:
        self.P("Received at least one NET_MON_01 message. Resuming the main thread...", color='g')
      return

    def __handle_open_transactions(self):
      with self.__open_transactions_lock:
        solved_transactions = [i for i, transaction in enumerate(self.__open_transactions) if transaction.is_solved()]
        solved_transactions.reverse()

        for idx in solved_transactions:
          self.__open_transactions[idx].callback()
          self.__open_transactions.pop(idx)
      return

    @property
    def _connected(self):
      """
      Check if the session is connected to the communication server.
      """
      raise NotImplementedError

    def __maybe_reconnect(self) -> None:
      """
      Attempt reconnecting to the communication server if an unexpected disconnection ocurred,
      using the credentials provided when creating this instance.

      This method should be called in a user-defined main loop.
      This method is called in `run` method, in the main loop.
      """
      if self._connected == False:
        self._connect()
      return

    def __close_own_pipelines(self, wait=True):
      """
      Close all pipelines that were created by or attached to this session.

      Parameters
      ----------
      wait : bool, optional
          If `True`, will wait for the transactions to finish. Defaults to `True`
      """
      # iterate through all CREATED pipelines from this session and close them
      transactions = []

      for pipeline in self.own_pipelines:
        transactions.extend(pipeline._close())

      self.P("Closing own pipelines: {}".format([p.name for p in self.own_pipelines]))

      if wait:
        self.wait_for_transactions(transactions)
        self.P("Closed own pipelines.")
      return

    def _communication_close(self):
      """
      Close the communication server connection.
      """
      raise NotImplementedError

    def close(self, close_pipelines=False, wait_close=True, **kwargs):
      """
      Close the session, releasing all resources and closing all threads
      Resources are released in the main loop thread, so this method will block until the main loop thread exits.
      This method is blocking.

      Parameters
      ----------
      close_pipelines : bool, optional
          close all the pipelines created by or attached to this session (basically calling `.close_own_pipelines()` for you), by default False
      wait_close : bool, optional
          If `True`, will wait for the main loop thread to exit. Defaults to `True`
      """

      if close_pipelines:
        self.__close_own_pipelines(wait=wait_close)

      self.__running_main_loop_thread = False

      # wait for the main loop thread to exit
      while not self.__closed_everything and wait_close:
        sleep(0.1)

      return


    def close_pipeline(self, node_addr : str, pipeline_name : str):
      """
      Close a pipeline created by this session.

      Parameters
      ----------
      node_addr : str
          The address of the edge node that owns the pipeline.
          
      pipeline_name : str
          The name of the pipeline to close.
      """
      pipeline : Pipeline = self._dct_online_nodes_pipelines.get(node_addr, {}).get(pipeline_name, None)
      if pipeline is not None:
        self.P(
          f"Closing known pipeline <{pipeline_name}> from <{node_addr}>",
          color='y'
        )
        pipeline.close()
      else:
        self.P(
          "No known pipeline found. Sending close to <{}> for <{}>".format(
            node_addr, pipeline_name
          ),
          color='y'
        )
        self._send_command_archive_pipeline(node_addr, pipeline_name)        
      return


    def _connect(self) -> None:
      """
      Connect to the communication server using the credentials provided when creating this instance.
      """
      raise NotImplementedError

    def _send_raw_message(self, to, msg, communicator='default'):
      """
      Send a message to a node.

      Parameters
      ----------
      to : str
          The name of the ratio1 Edge Protocol edge node that will receive the message.
      msg : dict or str
          The message to send.
      """
      raise NotImplementedError

    def _send_command(self, to, command):
      """
      Send a command to a node.

      Parametersc
      ----------
      to : str
          The name of the ratio1 Edge Protocol edge node that will receive the command.
      command : str or dict
          The command to send.
      """
      raise NotImplementedError

    def _send_payload(self, payload):
      """
      Send a payload to a node.
      Parameters
      ----------
      payload : dict or str
          The payload to send.
      """
      raise NotImplementedError

    def __release_callback_threads(self):
      """
      Release all resources and close all threads
      """
      self.__running_callback_threads = False

      self._payload_thread.join()
      self._notif_thread.join()
      self._hb_thread.join()
      return

    def __main_loop(self):
      """
      The main loop of this session. This method is called in a separate thread.
      This method runs on a separate thread from the main thread, and it is responsible for handling all messages received from the communication server.
      We use it like this to avoid blocking the main thread, which is used by the user.
      """
      self.__start_main_loop_time = tm()
      while self.__running_main_loop_thread:
        self.__maybe_reconnect()
        self.__handle_open_transactions()
        sleep(0.1)
      # end while self.running

      self.P("Main loop thread exiting...", verbosity=2)
      self.__release_callback_threads()

      self.P("Comms closing...", verbosity=2)
      self._communication_close()
      self.__closed_everything = True
      return

    def run(self, wait=True, close_session=True, close_pipelines=False):
      """
      This simple method will lock the main thread in a loop.

      Parameters
      ----------
      wait : bool, float, callable
          If `True`, will wait forever.
          If `False`, will not wait at all
          If type `float` and > 0, will wait said amount of seconds
          If type `float` and == 0, will wait forever
          If type `callable`, will call the function until it returns `False`
          Defaults to `True`
      close_session : bool, optional
          If `True` will close the session when the loop is exited.
          Defaults to `True`
      close_pipelines : bool, optional
          If `True` will close all pipelines initiated by this session when the loop is exited.
          This flag is ignored if `close_session` is `False`.
          Defaults to `False`
      """
      _start_timer = tm()
      try:
        bool_loop_condition = isinstance(wait, bool) and wait
        number_loop_condition = isinstance(wait, (int, float)) and (wait == 0 or (tm() - _start_timer) < wait)
        callable_loop_condition = callable(wait) and wait()
        while (bool_loop_condition or number_loop_condition or callable_loop_condition) and not self.__closed_everything:
          sleep(0.1)
          bool_loop_condition = isinstance(wait, bool) and wait
          number_loop_condition = isinstance(wait, (int, float)) and (wait == 0 or (tm() - _start_timer) < wait)
          callable_loop_condition = callable(wait) and wait()
        self.P("Exiting loop...", verbosity=2)
      except KeyboardInterrupt:
        self.P("CTRL+C detected. Stopping loop.", color='r', verbosity=1)

      if close_session:
        self.close(close_pipelines, wait_close=True)

      return

    def sleep(self, wait=True, close_session=True, close_pipelines=False):
      """
      Sleep for a given amount of time.

      Parameters
      ----------
      wait : bool, float, callable
          If `True`, will wait forever.
          If `False`, will not wait at all
          If type `float` and > 0, will wait said amount of seconds
          If type `float` and == 0, will wait forever
          If type `callable`, will call the function until it returns `False`
          Defaults to `True`
      """
      _start_timer = tm()
      try:
        bool_loop_condition = isinstance(wait, bool) and wait
        number_loop_condition = isinstance(wait, (int, float)) and (wait == 0 or (tm() - _start_timer) < wait)
        callable_loop_condition = callable(wait) and wait()
        while (bool_loop_condition or number_loop_condition or callable_loop_condition):
          sleep(0.1)
          bool_loop_condition = isinstance(wait, bool) and wait
          number_loop_condition = isinstance(wait, (int, float)) and (wait == 0 or (tm() - _start_timer) < wait)
          callable_loop_condition = callable(wait) and wait()
        self.P("Exiting loop...", verbosity=2)
      except KeyboardInterrupt:
        self.P("CTRL+C detected. Stopping loop.", color='r', verbosity=1)
        
      if close_session:
        self.close(close_pipelines, wait_close=True)        
      return
    
    def wait(
      self, 
      seconds=10, 
      close_session_on_timeout=True, 
      close_pipeline_on_timeout=False,
      **kwargs,
    ):
      """
      Wait for a given amount of time.

      Parameters
      ----------
      seconds : int, float, optional
          The amount of time to wait, by default 10
          
      close_session_on_timeout : bool, optional
          If `True`, will close the session when the time is up, by default True
          
      close_pipeline_on_timeout : bool, optional
          If `True`, will close the pipelines when the time is up, by default False
          
      **kwargs : dict
          Additional or replacement parameters to be passed to the `run` method:
            `close_session` : bool - If `True` will close the session when the loop is exited.
            `close_pipelines` : bool - If `True` will close all pipelines initiated by this session when the loop is exited.
          
      """
      if "close_pipelines" in kwargs:
        close_pipeline_on_timeout = kwargs.get("close_pipelines")
      if "close_session" in kwargs:
        close_session_on_timeout = kwargs.get("close_session")
      self.run(
        wait=seconds, 
        close_session=close_session_on_timeout, 
        close_pipelines=close_pipeline_on_timeout,
      )
      return    

  # Utils
  if True:
    
    def __load_user_config(self, dotenv_path):
      # if the ~/.ratio1/config file exists, load the credentials from there else try to load them from .env
      if not load_user_defined_config(verbose=not self.silent):        
        # this method will search for the credentials in the environment variables
        # the path to env file, if not specified, will be search in the following order:
        #  1. current working directory
        #  2-N. directories of the files from the call stack
        load_dotenv(dotenv_path=dotenv_path, verbose=self.__debug_env)
        if not self.silent:
          keys = [k for k in os.environ if k.startswith("EE_")]
          if not self.silent:
            log_with_color(f"Loaded credentials from environment variables: {keys}", color='y')
        self.__user_config_loaded = False
      else:
        if not self.silent:
          keys = [k for k in os.environ if k.startswith("EE_")]
          if not self.silent:
            log_with_color(f"Loaded credentials from `{get_user_config_file()}`: {keys}.", color='y')
          if self.__debug_env:
            for k, v in os.environ.items():
              if k.startswith("EE_"):
                log_with_color(f"{k}={v}", color='y')
        self.__user_config_loaded = True
      # endif config loading from ~ or ./.env      
      
      if self.name is None:
        from ratio1.logging.logger_mixins.utils_mixin import _UtilsMixin
        random_name = _UtilsMixin.get_random_name()
        default = EE_SDK_ALIAS_DEFAULT + '-' + random_name
        self.name = os.environ.get(EE_SDK_ALIAS_ENV_KEY, default)
        if EE_SDK_ALIAS_ENV_KEY not in os.environ:
          if not self.silent:
            log_with_color(f"Using default SDK alias: {self.name}. Writing the user config file...", color='y')
            set_client_alias(self.name)
          #end with
        else:
          if not self.silent:
            log_with_color(f"SDK Alias (from env): {self.name}.", color='y')
        #end if
      #end name is None      
      return self.__user_config_loaded
    
    def __fill_config(self, host, port, user, pwd, secured):
      """
      Fill the configuration dictionary with the ceredentials provided when creating this instance.


      Parameters
      ----------
      host : str
          The hostname of the server.
          Can be retrieved from the environment variables AIXP_HOSTNAME, AIXP_HOST
          
      port : int
          The port.
          Can be retrieved from the environment variable AIXP_PORT
          
      user : str
          The user name.
          Can be retrieved from the environment variables AIXP_USERNAME, AIXP_USER
          
      pwd : str
          The password.
          Can be retrieved from the environment variables AIXP_PASSWORD, AIXP_PASS, AIXP_PWD
          
      dotenv_path : str, optional
          Path to the .env file, by default None. If None, the path will be searched in the current working directory and in the directories of the files from the call stack.

      Raises
      ------
      ValueError
          Missing credentials
      """      


      possible_user_values = [
        user,
        os.getenv(ENVIRONMENT.AIXP_USERNAME),
        os.getenv(ENVIRONMENT.AIXP_USER),
        os.getenv(ENVIRONMENT.EE_USERNAME),
        os.getenv(ENVIRONMENT.EE_USER),
        os.getenv(ENVIRONMENT.EE_MQTT_USER),
        self._config.get(comm_ct.USER),
      ]

      user = next((x for x in possible_user_values if x is not None), None)

      if user is None:
        env_error = "Error: No user specified for ratio1 Edge Protocol network connection. Please make sure you have the correct credentials in the environment variables within the .env file or provide them as params in code (not recommended due to potential security issue)."
        raise ValueError(env_error)
      if self._config.get(comm_ct.USER, None) is None:
        self._config[comm_ct.USER] = user

      possible_password_values = [
        pwd,
        os.getenv(ENVIRONMENT.AIXP_PASSWORD),
        os.getenv(ENVIRONMENT.AIXP_PASS),
        os.getenv(ENVIRONMENT.AIXP_PWD),
        os.getenv(ENVIRONMENT.EE_PASSWORD),
        os.getenv(ENVIRONMENT.EE_PASS),
        os.getenv(ENVIRONMENT.EE_PWD),
        os.getenv(ENVIRONMENT.EE_MQTT),
        self._config.get(comm_ct.PASS),
      ]

      pwd = next((x for x in possible_password_values if x is not None), None)

      if pwd is None:
        raise ValueError("Error: No password specified for ratio1 Edge Protocol network connection")
      if self._config.get(comm_ct.PASS, None) is None:
        self._config[comm_ct.PASS] = pwd

      possible_host_values = [
        host,
        os.getenv(ENVIRONMENT.AIXP_HOSTNAME),
        os.getenv(ENVIRONMENT.AIXP_HOST),
        os.getenv(ENVIRONMENT.EE_HOSTNAME),
        os.getenv(ENVIRONMENT.EE_HOST),
        os.getenv(ENVIRONMENT.EE_MQTT_HOST),
        self._config.get(comm_ct.HOST),
        DEBUG_MQTT_SERVER,
      ]

      host = next((x for x in possible_host_values if x is not None), None)

      if host is None:
        raise ValueError("Error: No host specified for ratio1 Edge Protocol network connection")
      if self._config.get(comm_ct.HOST, None) is None:
        self._config[comm_ct.HOST] = host

      possible_port_values = [
        port,
        os.getenv(ENVIRONMENT.AIXP_PORT),
        os.getenv(ENVIRONMENT.EE_PORT),
        os.getenv(ENVIRONMENT.EE_MQTT_PORT),
        self._config.get(comm_ct.PORT),
        8883,
      ]

      port = next((x for x in possible_port_values if x is not None), None)

      if port is None:
        raise ValueError("Error: No port specified for ratio1 Edge Protocol network connection")
      if self._config.get(comm_ct.PORT, None) is None:
        self._config[comm_ct.PORT] = int(port)

      possible_cert_path_values = [
        os.getenv(ENVIRONMENT.AIXP_CERT_PATH),
        os.getenv(ENVIRONMENT.EE_CERT_PATH),
        self._config.get(comm_ct.CERT_PATH),
      ]

      cert_path = next((x for x in possible_cert_path_values if x is not None), None)
      if cert_path is not None and self._config.get(comm_ct.CERT_PATH, None) is None:
        self._config[comm_ct.CERT_PATH] = cert_path

      possible_secured_values = [
        secured,
        os.getenv(ENVIRONMENT.AIXP_SECURED),
        os.getenv(ENVIRONMENT.EE_SECURED),
        self._config.get(comm_ct.SECURED),
        False,
      ]

      secured = next((x for x in possible_secured_values if x is not None), None)
      if secured is not None and self._config.get(comm_ct.SECURED, None) is None:
        secured = str(secured).strip().upper() in ['TRUE', '1']
        self._config[comm_ct.SECURED] = secured
        
      return

    def __aliases_to_addresses(self):
      """
      Convert the aliases to addresses.
      """
      dct_aliases = {v: k for k, v in self.__dct_node_address_to_alias.items()}
      return dct_aliases

    def __get_node_address(self, node):
      """
      Get the address of a node. If node is an address, return it. Else, return the address of the node.
      This method is used to convert the alias of a node to its address if needed however it is 
      not recommended to use it as it was created for backward compatibility reasons.

      Parameters
      ----------
      node : str
          Address or Name of the node.

      Returns
      -------
      str
          The address of the node.
      """
      result = None
      if node in self._dct_node_last_seen_time.keys():
        # node seems to be already an address
        result = node
      elif node in self.__dct_node_eth_addr_to_node_addr.keys():
        # node is an eth address
        result = self.__dct_node_eth_addr_to_node_addr.get(node, None)
      else:
        # maybe node is a name
        aliases = self.__aliases_to_addresses()
        result = aliases.get(node, None)
      return result

    def __prepare_message(
        self, msg_data, encrypt_message: bool = True,
        destination: str = None, destination_id: str = None,
        session_id: str = None, additional_data: dict = None
    ):
      """
      Prepare and maybe encrypt a message for sending.
      Parameters
      ----------
      msg_data : dict
          The message to send.
          
      encrypt_message : bool
          If True, will encrypt the message.
          
      destination : str or list, optional
          The destination address or list of addresses, by default None
          
      destination_id : str, optional
          The destination id, by default None
          IMPORTANT: this will be deprecated soon in favor of the direct use of the address
          
      additional_data : dict, optional
          Additional data to send, by default None
          This has to be dict!

      Returns
      -------
      msg_to_send : dict
          The message to send.
      """
      if destination is None and destination_id is not None:
        # Initial code `str_enc_data = self.bc_engine.encrypt(str_data, destination_id)` could not work under any
        # circumstances due to the fact that encrypt requires the public key of the receiver not the alias
        # of the receiver. The code below is a workaround to encrypt the message
        # TODO: furthermore the code will be migrated to the use of the address of the worker
        destination = self.get_addr_by_name(destination_id)
        assert destination is not None, f"Unknown address for id: {destination_id}"
      # endif only destination_id provided

      # TODO: apply self.__get_node_address on all destination addresses
      # This part is duplicated with the creation of payloads
      if encrypt_message and destination is not None:
        str_data = json.dumps(msg_data)
        str_enc_data = self.bc_engine.encrypt(
          plaintext=str_data, receiver_address=destination
        )
        msg_data = {
          comm_ct.COMM_SEND_MESSAGE.K_EE_IS_ENCRYPTED: True,
          comm_ct.COMM_SEND_MESSAGE.K_EE_ENCRYPTED_DATA: str_enc_data,
        }
      else:
        msg_data[comm_ct.COMM_SEND_MESSAGE.K_EE_IS_ENCRYPTED] = False
        if encrypt_message:
          msg_data[comm_ct.COMM_SEND_MESSAGE.K_EE_ENCRYPTED_DATA] = "Error! No receiver address found!"
      # endif encrypt_message and destination available
      msg_to_send = {
        **msg_data,
        PAYLOAD_DATA.EE_DESTINATION: destination,
        comm_ct.COMM_SEND_MESSAGE.K_EE_ID: destination_id,
        comm_ct.COMM_SEND_MESSAGE.K_SESSION_ID: session_id or self.name,
        comm_ct.COMM_SEND_MESSAGE.K_INITIATOR_ID: self.name,
        comm_ct.COMM_SEND_MESSAGE.K_SENDER_ADDR: self.bc_engine.address,
        comm_ct.COMM_SEND_MESSAGE.K_TIME: dt.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
      }
      if additional_data is not None and isinstance(additional_data, dict):
        msg_to_send.update(additional_data)
      # endif additional_data provided
      return msg_to_send

    def _send_command_to_box(self, command, worker, payload, show_command=True, session_id=None, **kwargs):
      """
      Send a command to a node.

      Parameters
      ----------
      command : str
          The command to send.
          
      worker : str
          The name of the ratio1 Edge Protocol edge node that will receive the command.
          
          Observation: this approach will be deprecated soon in favor of the direct use of 
          the address that will not require the node to be already "seen" by the session.
          
      payload : dict
          The payload to send.
      show_command : bool, optional
          If True, will print the complete command that is being sent, by default False
      
          
      """

      show_command = show_command or self.__show_commands

      if len(kwargs) > 0:
        self.D("Ignoring extra kwargs: {}".format(kwargs), verbosity=2)

      critical_data = {
        comm_ct.COMM_SEND_MESSAGE.K_ACTION: command,
        comm_ct.COMM_SEND_MESSAGE.K_PAYLOAD: payload,
      }

      msg_to_send = self.__prepare_message(
        msg_data=critical_data,
        encrypt_message=self.encrypt_comms,
        destination_id=worker,
        session_id=session_id,
      )
      self.bc_engine.sign(msg_to_send, use_digest=True)
      if show_command:
        self.Pd(
          "Sending command '{}' to '{}':\n{}".format(command, worker, json.dumps(msg_to_send, indent=2)),
          color='y',
          verbosity=1
        )
      self._send_command(worker, msg_to_send)
      return

    def _send_command_create_pipeline(self, worker, pipeline_config, **kwargs):
      self._send_command_to_box(COMMANDS.UPDATE_CONFIG, worker, pipeline_config, **kwargs)
      return

    def _send_command_delete_pipeline(self, worker, pipeline_name, **kwargs):
      # TODO: remove this command calls from examples
      self._send_command_to_box(COMMANDS.DELETE_CONFIG, worker, pipeline_name, **kwargs)
      return

    def _send_command_archive_pipeline(self, worker, pipeline_name, **kwargs):
      self._send_command_to_box(COMMANDS.ARCHIVE_CONFIG, worker, pipeline_name, **kwargs)
      return

    def _send_command_update_pipeline_config(self, worker, pipeline_config, **kwargs):
      self._send_command_to_box(COMMANDS.UPDATE_CONFIG, worker, pipeline_config, **kwargs)
      return

    def _send_command_update_instance_config(self, worker, pipeline_name, signature, instance_id, instance_config, **kwargs):
      payload = {
        PAYLOAD_DATA.NAME: pipeline_name,
        PAYLOAD_DATA.SIGNATURE: signature,
        PAYLOAD_DATA.INSTANCE_ID: instance_id,
        PAYLOAD_DATA.INSTANCE_CONFIG: {k.upper(): v for k, v in instance_config.items()}
      }
      self._send_command_to_box(COMMANDS.UPDATE_PIPELINE_INSTANCE, worker, payload, **kwargs)
      return

    def _send_command_batch_update_instance_config(self, worker, lst_updates, **kwargs):
      for update in lst_updates:
        assert isinstance(update, dict), "All updates must be dicts"
        assert PAYLOAD_DATA.NAME in update, "All updates must have a pipeline name"
        assert PAYLOAD_DATA.SIGNATURE in update, "All updates must have a plugin signature"
        assert PAYLOAD_DATA.INSTANCE_ID in update, "All updates must have a plugin instance id"
        assert PAYLOAD_DATA.INSTANCE_CONFIG in update, "All updates must have a plugin instance config"
        assert isinstance(update[PAYLOAD_DATA.INSTANCE_CONFIG], dict), \
            "All updates must have a plugin instance config as dict"
      self._send_command_to_box(COMMANDS.BATCH_UPDATE_PIPELINE_INSTANCE, worker, lst_updates, **kwargs)

    def _send_command_pipeline_command(self, worker, pipeline_name, command, payload=None, command_params=None, **kwargs):
      if isinstance(command, str):
        command = {command: True}
      if payload is not None:
        command.update(payload)
      if command_params is not None:
        command[COMMANDS.COMMAND_PARAMS] = command_params

      pipeline_command = {
        PAYLOAD_DATA.NAME: pipeline_name,
        COMMANDS.PIPELINE_COMMAND: command,
      }
      self._send_command_to_box(COMMANDS.PIPELINE_COMMAND, worker, pipeline_command, **kwargs)
      return

    def _send_command_instance_command(self, worker, pipeline_name, signature, instance_id, command, payload=None, command_params=None, **kwargs):
      if command_params is None:
        command_params = {}
      if isinstance(command, str):
        command_params[command] = True
        command = {}
      if payload is not None:
        command = {**command, **payload}

      command[COMMANDS.COMMAND_PARAMS] = command_params

      instance_command = {COMMANDS.INSTANCE_COMMAND: command}
      self._send_command_update_instance_config(
        worker, pipeline_name, signature, instance_id, instance_command, **kwargs)
      return

    def _send_command_stop_node(self, worker, **kwargs):
      self._send_command_to_box(COMMANDS.STOP, worker, None, **kwargs)
      return

    def _send_command_restart_node(self, worker, **kwargs):
      self._send_command_to_box(COMMANDS.RESTART, worker, None, **kwargs)
      return

    def _send_command_request_heartbeat(self, worker, full_heartbeat=False, **kwargs):
      command = COMMANDS.FULL_HEARTBEAT if full_heartbeat else COMMANDS.TIMERS_ONLY_HEARTBEAT
      self._send_command_to_box(command, worker, None, **kwargs)

    def _send_command_reload_from_disk(self, worker, **kwargs):
      self._send_command_to_box(COMMANDS.RELOAD_CONFIG_FROM_DISK, worker, None, **kwargs)
      return

    def _send_command_archive_all(self, worker, **kwargs):
      self._send_command_to_box(COMMANDS.ARCHIVE_CONFIG_ALL, worker, None, **kwargs)
      return

    def _send_command_delete_all(self, worker, **kwargs):
      self._send_command_to_box(COMMANDS.DELETE_CONFIG_ALL, worker, None, **kwargs)
      return

    def _register_transaction(self, session_id: str, lst_required_responses: list = None, timeout=0, on_success_callback: callable = None, on_failure_callback: callable = None) -> Transaction:
      """
      Register a new transaction.

      Parameters
      ----------
      session_id : str
          The session id.
      lst_required_responses : list[Response], optional
          The list of required responses, by default None
      timeout : int, optional
          The timeout, by default 0
      on_success_callback : _type_, optional
          The on success callback, by default None
      on_failure_callback : _type_, optional
          The on failure callback, by default None
      Returns
      -------
      Transaction
          The transaction object
      """
      transaction = Transaction(
        log=self.log,
        session_id=session_id,
        lst_required_responses=lst_required_responses or [],
        timeout=timeout,
        on_success_callback=on_success_callback,
        on_failure_callback=on_failure_callback,
      )

      with self.__open_transactions_lock:
        self.__open_transactions.append(transaction)
      return transaction

    def __create_pipeline_from_config(
      self, 
      node_addr : str, 
      config : dict,
      plugins_statuses : list = None,
    ):
      pipeline_config = {k.lower(): v for k, v in config.items()}
      name = pipeline_config.pop('name', None)
      plugins = pipeline_config.pop('plugins', None)

      pipeline = Pipeline(
        is_attached=True,
        session=self,
        log=self.log,
        node_addr=node_addr,
        name=name,
        plugins=plugins,
        existing_config=pipeline_config,
        plugins_statuses=plugins_statuses,
      )

      return pipeline

  # API
  if True:
    @ property
    def server(self):
      """
      The hostname of the server.
      """
      return self._config[comm_ct.HOST]

    def create_pipeline(self, *,
                        node,
                        name,
                        data_source="Void",
                        config={},
                        plugins=[],
                        on_data=None,
                        on_notification=None,
                        max_wait_time=0,
                        pipeline_type=None,
                        debug=False,
                        **kwargs) -> Pipeline:
      """
      Create a new pipeline on a node. A pipeline is the equivalent of the "config file" used by the ratio1 Edge Protocol edge node team internally.

      A `Pipeline` is a an object that encapsulates a one-to-many, data acquisition to data processing, flow of data.

      A `Pipeline` contains one thread of data acquisition (which does not mean only one source of data), and many
      processing units, usually named `Plugins`.

      An `Instance` is a running thread of a `Plugin` type, and one may want to have multiple `Instances`, because each can be configured independently.

      As such, one will work with `Instances`, by referring to them with the unique identifier (Pipeline, Plugin, Instance).

      In the documentation, the following refer to the same thing:
        `Pipeline` == `Stream`

        `Plugin` == `Signature`

      This call can busy-wait for a number of seconds to listen to heartbeats, in order to check if an ratio1 Edge Protocol edge node is online or not.
      If the node does not appear online, a warning will be displayed at the stdout, telling the user that the message that handles the
      creation of the pipeline will be sent, but it is not guaranteed that the specific node will receive it.

      Parameters
      ----------
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that will handle this pipeline.
      name : str
          Name of the pipeline. This is good to be kept unique, as it allows multiple parties to overwrite each others configurations.
      data_source : str, optional
          This is the name of the DCT plugin, which resembles the desired functionality of the acquisition. Defaults to Void.
      config : dict, optional
          This is the dictionary that contains the configuration of the acquisition source, by default {}
      plugins : list, optional
          List of dictionaries which contain the configurations of each plugin instance that is desired to run on the box.
          Defaults to []. Should be left [], and instances should be created with the api.
      on_data : Callable[[Pipeline, str, str, dict], None], optional
          Callback that handles messages received from any plugin instance.
          As arguments, it has a reference to this Pipeline object, the signature and the instance of the plugin
          that sent the message and the payload itself.
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
      on_notification : Callable[[Pipeline, dict], None], optional
          Callback that handles notifications received from any plugin instance.
          As arguments, it has a reference to this Pipeline object, along with the payload itself.
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
      max_wait_time : int, optional
          The maximum time to busy-wait, allowing the Session object to listen to node heartbeats
          and to check if the desired node is online in the network, by default 0.
      **kwargs :
          The user can provide the configuration of the acquisition source directly as kwargs.

      Returns
      -------
      Pipeline
          A `Pipeline` object.

      """

      found = self.wait_for_node(node, timeout=max_wait_time, verbose=False)

      if not found:
        raise Exception("Unable to attach to pipeline. Node does not exist")

      node_addr = self.__get_node_address(node)
      pipeline_type = pipeline_type or Pipeline
      pipeline = pipeline_type(
          self,
          self.log,
          node_addr=node_addr,
          name=name,
          type=data_source,
          config=config,
          plugins=plugins,
          on_data=on_data,
          on_notification=on_notification,
          is_attached=False,
          debug=debug,
          **kwargs
      )
      self.own_pipelines.append(pipeline)
      return pipeline
    
    def get_addr_by_name(self, name):
      """
      Get the address of a node by its name.
      This function should be used with caution and it was created for backward compatibility reasons.
      
      Parameters
      ----------
      
      name : str
          The name of the node.
          
      Returns
      -------
      str
          The address of the node.      
      """
      return self.__get_node_address(name)      
      

    def get_node_alias(self, node_addr):
      """
      Get the alias of a node.

      Parameters
      ----------
      node_addr : str
          The address of the node.

      Returns
      -------
      str
          The name of the node.
      """
      return self.__dct_node_address_to_alias.get(node_addr, None)

    def get_addr_by_eth_address(self, eth_address):
      """
      Get the address of a node by its eth address.

      Parameters
      ----------
      eth_address : str
          The eth address of the node.

      Returns
      -------
      str
          The address of the node.
      """
      return self.__dct_node_eth_addr_to_node_addr.get(eth_address, None)

    def get_eth_address_by_addr(self, node_addr):
      """
      Get the eth address of a node by its address.

      Parameters
      ----------
      node_addr : str
          The address of the node.

      Returns
      -------
      str
          The eth address of the node.
      """
      return self.bc_engine.node_address_to_eth_address(node_addr)

    def get_active_nodes(self):
      """
      Get the list of all ratio1 Edge Protocol edge nodes addresses that sent a message since this 
      session was created, and that are considered online.

      Returns
      -------
      list
          List of addresses of all the ratio1 Edge Protocol edge nodes that are considered online

      """
      return [k for k, v in self._dct_node_last_seen_time.items() if (tm() - v) < self.online_timeout]

    def get_allowed_nodes(self):
      """
      Get the list of all active ratio1 Edge Protocol edge nodes to whom this 
      ssion can send messages. This is based on the last heartbeat received from each individual node.

      Returns
      -------
      list[str]
          List of names of all the active ratio1 Edge Protocol edge nodes to whom this session can send messages
      """
      active_nodes = self.get_active_nodes()
      return [node for node in self._dct_can_send_to_node if self._dct_can_send_to_node[node] and node in active_nodes]

    def get_active_pipelines(self, node):
      """
      Get a dictionary with all the pipelines that are active on this ratio1 Edge Protocol edge node

      Parameters
      ----------
      node : str
          Address or Name of the ratio1 Edge Protocol edge node

      Returns
      -------
      dict
          The key is the name of the pipeline, and the value is the entire config dictionary of that pipeline.

      """
      node_address = self.__get_node_address(node)
      return self._dct_online_nodes_pipelines.get(node_address, None)

    def get_active_supervisors(self):
      """
      Get the list of all active supervisors

      Returns
      -------
      list
          List of names of all the active supervisors
      """
      active_nodes = self.get_active_nodes()

      active_supervisors = []
      for node in active_nodes:
        last_hb = self._dct_online_nodes_last_heartbeat.get(node, None)
        if last_hb is None:
          continue

        if last_hb.get(PAYLOAD_DATA.IS_SUPERVISOR, False):
          active_supervisors.append(node)

      return active_supervisors

    def attach_to_pipeline(self, *,
                           node,
                           name,
                           on_data=None,
                           on_notification=None,
                           max_wait_time=0) -> Pipeline:
      """
      Create a Pipeline object and attach to an existing pipeline on an ratio1 Edge Protocol edge node.
      Useful when one wants to treat an existing pipeline as one of his own,
      or when one wants to attach callbacks to various events (on_data, on_notification).

      A `Pipeline` is a an object that encapsulates a one-to-many, data acquisition to data processing, flow of data.

      A `Pipeline` contains one thread of data acquisition (which does not mean only one source of data), and many
      processing units, usually named `Plugins`.

      An `Instance` is a running thread of a `Plugin` type, and one may want to have multiple `Instances`, because each can be configured independently.

      As such, one will work with `Instances`, by reffering to them with the unique identifier (Pipeline, Plugin, Instance).

      In the documentation, the following reffer to the same thing:
        `Pipeline` == `Stream`

        `Plugin` == `Signature`

      This call can busy-wait for a number of seconds to listen to heartbeats, in order to check if an ratio1 Edge Protocol edge node is online or not.
      If the node does not appear online, a warning will be displayed at the stdout, telling the user that the message that handles the
      creation of the pipeline will be sent, but it is not guaranteed that the specific node will receive it.


      Parameters
      ----------
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that handles this pipeline.
      name : str
          Name of the existing pipeline.
      on_data : Callable[[Pipeline, str, str, dict], None], optional
          Callback that handles messages received from any plugin instance.
          As arguments, it has a reference to this Pipeline object, the signature and the instance of the plugin
          that sent the message and the payload itself.
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
      on_notification : Callable[[Pipeline, dict], None], optional
          Callback that handles notifications received from any plugin instance.
          As arguments, it has a reference to this Pipeline object, along with the payload itself.
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
      max_wait_time : int, optional
          The maximum time to busy-wait, allowing the Session object to listen to node heartbeats
          and to check if the desired node is online in the network, by default 0.

      Returns
      -------
      Pipeline
          A `Pipeline` object.

      Raises
      ------
      Exception
          Node does not exist (it is considered offline because the session did not receive any heartbeat)
      Exception
          Node does not host the desired pipeline
      """

      found = self.wait_for_node(node, timeout=max_wait_time, verbose=False)

      if not found:
        raise Exception("Unable to attach to pipeline. Node does not exist")

      node_addr = self.__get_node_address(node)

      if name not in self._dct_online_nodes_pipelines[node_addr]:
        raise Exception("Unable to attach to pipeline. Pipeline does not exist")

      pipeline: Pipeline = self._dct_online_nodes_pipelines[node_addr][name]

      if on_data is not None:
        pipeline._add_on_data_callback(on_data)
      if on_notification is not None:
        pipeline._add_on_notification_callback(on_notification)

      self.own_pipelines.append(pipeline)

      return pipeline

    def create_or_attach_to_pipeline(self, *,
                                     node,
                                     name,
                                     data_source="Void",
                                     config={},
                                     plugins=[],
                                     on_data=None,
                                     on_notification=None,
                                     max_wait_time=0,
                                     **kwargs) -> Pipeline:
      """
      Create a new pipeline on a node, or attach to an existing pipeline on an ratio1 Edge Protocol edge node.

      Parameters
      ----------
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that will handle this pipeline.
          
      name : str
          Name of the pipeline. This is good to be kept unique, as it allows multiple parties to overwrite each others configurations.
          
      data_source : str
          This is the name of the DCT plugin, which resembles the desired functionality of the acquisition.
          Defaults to "Void" - no actual data acquisition.
          
      config : dict, optional
          This is the dictionary that contains the configuration of the acquisition source, by default {}
          
      plugins : list
          List of dictionaries which contain the configurations of each plugin instance that is desired to run on the box. 
          Defaults to []. Should be left [], and instances should be created with the api.
          
      on_data : Callable[[Pipeline, str, str, dict], None], optional
          Callback that handles messages received from any plugin instance. 
          As arguments, it has a reference to this Pipeline object, the signature and the instance of the plugin
          that sent the message and the payload itself.
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
          
      on_notification : Callable[[Pipeline, dict], None], optional
          Callback that handles notifications received from any plugin instance. 
          As arguments, it has a reference to this Pipeline object, along with the payload itself. 
          This callback acts as a default payload processor and will be called even if for a given instance
          the user has defined a specific callback.
          Defaults to None.
          
      max_wait_time : int, optional
          The maximum time to busy-wait, allowing the Session object to listen to node heartbeats
          and to check if the desired node is online in the network, by default 0.
          
      **kwargs :
          The user can provide the configuration of the acquisition source directly as kwargs.

      Returns
      -------
      Pipeline
          A `Pipeline` object.
      """

      pipeline = None
      try:
        pipeline = self.attach_to_pipeline(
          node=node,
          name=name,
          on_data=on_data,
          on_notification=on_notification,
          max_wait_time=max_wait_time,
        )

        possible_new_configuration = {
          **config,
          **{k.upper(): v for k, v in kwargs.items()}
        }

        if len(plugins) > 0:
          possible_new_configuration['PLUGINS'] = plugins

        if len(possible_new_configuration) > 0:
          pipeline.update_full_configuration(config=possible_new_configuration)
      except Exception as e:
        self.D("Failed to attach to pipeline: {}".format(e))
        pipeline = self.create_pipeline(
          node=node,
          name=name,
          data_source=data_source,
          config=config,
          plugins=plugins,
          on_data=on_data,
          on_notification=on_notification,
          **kwargs
        )

      return pipeline

    def wait_for_transactions(self, transactions: list[Transaction]):
      """
      Wait for the transactions to be solved.

      Parameters
      ----------
      transactions : list[Transaction]
          The transactions to wait for.
      """
      while not self.are_transactions_finished(transactions):
        sleep(0.1)
      return

    def are_transactions_finished(self, transactions: list[Transaction]):
      if transactions is None:
        return True
      return all([transaction.is_finished() for transaction in transactions])

    def wait_for_all_sets_of_transactions(self, lst_transactions: list[list[Transaction]]):
      """
      Wait for all sets of transactions to be solved.

      Parameters
      ----------
      lst_transactions : list[list[Transaction]]
          The list of sets of transactions to wait for.
      """
      all_finished = False
      while not all_finished:
        all_finished = all([self.are_transactions_finished(transactions) for transactions in lst_transactions])
      return

    def wait_for_any_set_of_transactions(self, lst_transactions: list[list[Transaction]]):
      """
      Wait for any set of transactions to be solved.

      Parameters
      ----------
      lst_transactions : list[list[Transaction]]
          The list of sets of transactions to wait for.
      """
      any_finished = False
      while not any_finished:
        any_finished = any([self.are_transactions_finished(transactions) for transactions in lst_transactions])
      return

    def wait_for_any_node(self, timeout=15, verbose=True):
      """
      Wait for any node to appear online.

      Parameters
      ----------
      timeout : int, optional
          The timeout, by default 15

      Returns
      -------
      bool
          True if any node is online, False otherwise.
      """
      if verbose:
        self.P("Waiting for any node to appear online...")

      _start = tm()
      found = len(self.get_active_nodes()) > 0
      while (tm() - _start) < timeout and not found:
        sleep(0.1)
        found = len(self.get_active_nodes()) > 0
      # end while

      if verbose:
        if found:
          self.P("Found nodes {} online.".format(self.get_active_nodes()))
        else:
          self.P("No nodes found online in {:.1f}s.".format(tm() - _start), color='r')
      return found

    def wait_for_node(self, node, /, timeout=15, verbose=True):
      """
      Wait for a node to appear online.

      Parameters
      ----------
      node : str
          The address or name of the ratio1 Edge Protocol edge node.
      timeout : int, optional
          The timeout, by default 15

      Returns
      -------
      bool
          True if the node is online, False otherwise.
      """
      short_addr = self._shorten_addr(node)
      if verbose:
        self.Pd("Waiting for node '{}' to appear online...".format(short_addr))

      _start = tm()
      found = self.check_node_online(node)
      while (tm() - _start) < timeout and not found:
        sleep(0.1)
        found = self.check_node_online(node)
      # end while

      if verbose:
        if found:
          self.P("Node '{}' is online.".format(short_addr))
        else:
          self.P("Node '{}' did not appear online in {:.1f}s.".format(short_addr, tm() - _start), color='r')
      return found

    def wait_for_node_configs(
      self, node, /, 
      timeout=15, verbose=True, 
      attempt_additional_requests=True
    ):
      """
      Wait for the node to have its configurations loaded.

      Parameters
      ----------
      node : str
          The address or name of the ratio1 Edge Protocol edge node.
      timeout : int, optional
          The timeout, by default 15
      attempt_additional_requests : bool, optional
          If True, will attempt to send additional requests to the node to get the configurations, by default True

      Returns
      -------
      bool
          True if the node has its configurations loaded, False otherwise.
      """
      short_addr = self._shorten_addr(node)
      self.P("Waiting for node '{}' to have its configurations loaded...".format(short_addr))

      _start = tm()
      found = self.check_node_config_received(node)
      additional_request_sent = False
      request_time_thr = timeout / 2
      while (tm() - _start) < timeout and not found:
        sleep(0.1)
        found = self.check_node_config_received(node)
        if not found and not additional_request_sent and (tm() - _start) > request_time_thr and attempt_additional_requests:
          self.P("Re-requesting configurations of node '{}'...".format(short_addr), show=True)
          node_addr = self.__get_node_address(node)
          self.__request_pipelines_from_net_config_monitor(node_addr)
          additional_request_sent = True
      # end while

      if verbose:
        if found:
          self.P(f"Received configurations of node '{short_addr}'.")
        else:
          self.P(f"Node '{short_addr}' did not send configs in {(tm() - _start)}. Client might not be authorized!", color='r')
      return found

    def check_node_config_received(self, node):
      """
      Check if the SDK received the configuration of the specified node.
      Parameters
      ----------
      node : str
          The address or name of the Ratio1 edge node.

      Returns
      -------
      bool
          True if the configuration of the node was received, False otherwise.
      """
      node = self.__get_node_address(node)
      return node in self._dct_online_nodes_pipelines

    def is_peered(self, node):
      """
      Public method for checking if a node is peered with the current session.
      Parameters
      ----------
      node : str
          The address or name of the Ratio1 edge node.

      Returns
      -------
      bool
          True if the node is peered, False otherwise.
      """
      node = self.__get_node_address(node)
      return self._dct_can_send_to_node.get(node, False)

    def get_last_seen_time(self, node, *, default_value=0):
      """
      Get the last time the node was seen.
      Parameters
      ----------
      node : str
          The address or name of the Ratio1 edge node.

      default_value : float, optional
          The default value to return if the node was not seen, by default 0.
          In case the user needs a specific default value, it can be provided here.

      Returns
      -------
      float or type(default_value)
          The last time the node was seen.
      """
      node = self.__get_node_address(node)
      return self._dct_node_last_seen_time.get(node, default_value)

    def check_node_online(self, node, /):
      """
      Check if a node is online.

      Parameters
      ----------
      node : str
          The address or name of the Ratio1 edge node.

      Returns
      -------
      bool
          True if the node is online, False otherwise.
      """
      node = self.__get_node_address(node)
      return node in self.get_active_nodes()

    def create_chain_dist_custom_job(
      self,
      main_node_process_real_time_collected_data,
      main_node_finish_condition,
      main_node_finish_condition_kwargs,
      main_node_aggregate_collected_data,
      worker_node_code,
      nr_remote_worker_nodes,
      node=None,
      worker_node_plugin_config={},
      worker_node_pipeline_config={},
      on_data=None,
      on_notification=None,
      deploy=False,
    ):

      pipeline: Pipeline = self.create_pipeline(
        node=node,
        name=self.log.get_unique_id(),
        data_source="Void"
      )

      instance = pipeline.create_chain_dist_custom_plugin_instance(
        main_node_process_real_time_collected_data=main_node_process_real_time_collected_data,
        main_node_finish_condition=main_node_finish_condition,
        finish_condition_kwargs=main_node_finish_condition_kwargs,
        main_node_aggregate_collected_data=main_node_aggregate_collected_data,
        worker_node_code=worker_node_code,
        nr_remote_worker_nodes=nr_remote_worker_nodes,
        worker_node_plugin_config=worker_node_plugin_config,
        worker_node_pipeline_config=worker_node_pipeline_config,
        on_data=on_data,
        on_notification=on_notification,
      )

      if deploy:
        pipeline.deploy()

      return pipeline, instance

    def create_web_app(
      self,
      *,
      node,
      name="Ratio1 Web App",
      signature=PLUGIN_SIGNATURES.CUSTOM_WEBAPI_01,
      ngrok_edge_label=None,
      endpoints=None,
      use_ngrok=True,
      extra_debug=False,
      summary="Ratio1 WebApp created via SDK",
      description=None,
      **kwargs
    ):
      """
      Create a new web app on a node.
      
      Parameters
      ----------
      
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that will handle this web app.
          
      name : str
          Name of the web app.
          
      signature : str, optional
          The signature of the plugin that will be used. Defaults to PLUGIN_SIGNATURES.CUSTOM_WEBAPI_01.
          
      endpoints : list[dict], optional
          A list of dictionaries defining the endpoint configuration. Defaults to None.
          
      use_ngrok : bool, optional
          If True, will use ngrok to expose the web app. Defaults to True.
          
      
      """

      ngrok_use_api = True
      
      pipeline_name = name.replace(" ", "_").lower()

      pipeline: WebappPipeline = self.create_pipeline(
        node=node,
        name=pipeline_name,
        pipeline_type=WebappPipeline,
        extra_debug=extra_debug,
        # default TYPE is "Void"
      )

      instance = pipeline.create_plugin_instance(
        signature=signature,
        instance_id=self.log.get_unique_id(),
        use_ngrok=use_ngrok,
        ngrok_edge_label=ngrok_edge_label,
        ngrok_use_api=ngrok_use_api,
        api_title=name,
        api_summary=summary,
        api_description=description,
        **kwargs
      )
      
      if endpoints is not None:
        for endpoint in endpoints:
          assert isinstance(endpoint, dict), "Each endpoint must be a dictionary defining the endpoint configuration."
          instance.add_new_endpoint(**endpoint)
        # end for
      # end if we have endpoints defined in the call

      return pipeline, instance
    
    
    def create_and_deploy_balanced_web_app(
      self,
      *,
      nodes,
      name,
      signature,
      ngrok_edge_label,
      endpoints=None,
      extra_debug=False,
      **kwargs
    ):
      """
      Create a new web app on a list of nodes.
      
      IMPORTANT: 
        The web app will be exposed using ngrok from multiple nodes that all will share the 
        same edge label so the ngrok_edge_label is mandatory.
      
      Parameters
      ----------
      
      nodes : list
          List of addresses or Names of the ratio1 Edge Protocol edge nodes that will handle this web app.
          
      name : str
          Name of the web app.
          
      signature : str
          The signature of the plugin that will be used. Defaults to PLUGIN_SIGNATURES.CUSTOM_WEBAPI_01.

      ngrok_edge_label : str
          The label of the edge node that will be used to expose the web app. This is mandatory due to the fact
          that the web app will be exposed using ngrok from multiple nodes that all will share the same edge label.
          
      endpoints : list[dict], optional
          A list of dictionaries defining the endpoint configuration. Defaults to None.
          
          
      
      """

      ngrok_use_api = kwargs.pop('ngrok_use_api', True)
      use_ngrok = True
      kwargs.pop('use_ngrok', None)
      
      if ngrok_edge_label is None:
        raise ValueError("The `ngrok_edge_label` parameter is mandatory when creating a balanced web app, in order for all instances to respond to the same URL.")

      pipelines, instances = [], []
      
      for node in nodes:
        self.P("Creating web app on node {}...".format(node), color='b')
        pipeline: WebappPipeline = self.create_pipeline(
          node=node,
          name=name,
          pipeline_type=WebappPipeline,
          extra_debug=extra_debug,
          # default TYPE is "Void"
        )

        instance = pipeline.create_plugin_instance(
          signature=signature,
          instance_id=self.log.get_unique_id(),
          use_ngrok=use_ngrok,
          ngrok_edge_label=ngrok_edge_label,
          ngrok_use_api=ngrok_use_api,
          **kwargs
        )
        
        if endpoints is not None:
          for endpoint in endpoints:
            assert isinstance(endpoint, dict), "Each endpoint must be a dictionary defining the endpoint configuration."
            instance.add_new_endpoint(**endpoint)
          # end for
        # end if we have endpoints defined in the call

        pipeline.deploy()
        pipelines.append(pipeline)
        instances.append(instance)
      # end for
      return pipelines, instances
      
    

    def create_telegram_simple_bot(
      self,
      *,
      node,
      name,
      signature=PLUGIN_SIGNATURES.TELEGRAM_BASIC_BOT_01,
      message_handler=None,
      processor_handler=None,
      telegram_bot_token=None,
      telegram_bot_token_env_key=ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY,
      telegram_bot_name=None,
      telegram_bot_name_env_key=ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY,
      **kwargs
    ):
      """
      Create a new basic Telegram bot on a node.
      
      Parameters
      ----------
      
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that will handle this Telegram bot.
          
      name : str
          Name of the Telegram bot. 
          
      signature : str, optional 
          The signature of the plugin that will be used. Defaults to PLUGIN_SIGNATURES.TELEGRAM_BASIC_BOT_01.
          
      message_handler : callable, optional  
          The message handler function that will be called when a message is received. Defaults to None.
          
      processor_handler : callable, optional
          The processor handler function that will be called in a processing loop within the 
          Telegram bot plugin in parallel with the message handler. Defaults to None.
          
      telegram_bot_token : str, optional  
          The Telegram bot token. Defaults to None.
          
      telegram_bot_token_env_key : str, optional
          The environment variable key that holds the Telegram bot token. Defaults to ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY.
          
      telegram_bot_name : str, optional
          The Telegram bot name. Defaults to None.
          
      telegram_bot_name_env_key : str, optional 
          The environment variable key that holds the Telegram bot name. Defaults to ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY.
          
      Returns
      -------
      tuple 
          `Pipeline` and a `Instance` objects tuple.
      """
      assert callable(message_handler), "The `message_handler` method parameter must be provided."
      
      if telegram_bot_token is None:
        telegram_bot_token = os.getenv(telegram_bot_token_env_key)
        if telegram_bot_token is None:
          message = f"Warning! No Telegram bot token provided as via env '{telegram_bot_token_env_key}' or explicitly as `telegram_bot_token` param."
          raise ValueError(message)
        
      if telegram_bot_name is None:
        telegram_bot_name = os.getenv(telegram_bot_name_env_key, name)
        if telegram_bot_name is None:
          message = f"Warning! No Telegram bot name provided as via env '{telegram_bot_name_env_key}' or explicitly as `telegram_bot_name` param."
          raise ValueError(message)
      

      pipeline: Pipeline = self.create_pipeline(
        node=node,
        name=name,
        # default TYPE is "Void"
      )
      
      func_name, func_args, func_base64_code = pipeline._get_method_data(message_handler)
      
      proc_func_args, proc_func_base64_code =[], None
      if processor_handler is not None:
        _, proc_func_args, proc_func_base64_code = pipeline._get_method_data(processor_handler)
      
      if len(func_args) != 2:
        raise ValueError("The message handler function must have exactly 3 arguments: `plugin`, `message` and `user`.")
      
      obfuscated_token = telegram_bot_token[:4] + "*" * (len(telegram_bot_token) - 4)      
      self.P(f"Creating telegram bot {telegram_bot_name} with token {obfuscated_token}...", color='b')      
      instance = pipeline.create_plugin_instance(
        signature=signature,
        instance_id=self.log.get_unique_id(),
        telegram_bot_token=telegram_bot_token,
        telegram_bot_name=telegram_bot_name,
        message_handler=func_base64_code,
        message_handler_args=func_args, # mandatory message and user
        message_handler_name=func_name, # not mandatory
        processor_handler=proc_func_base64_code, # not mandatory
        processor_handler_args=proc_func_args, # not mandatory
        **kwargs
      )      
      return pipeline, instance
    
    
    def create_telegram_conversational_bot(
      self,
      *,
      node,
      name,
      signature=PLUGIN_SIGNATURES.TELEGRAM_CONVERSATIONAL_BOT_01,
      telegram_bot_token=None,
      telegram_bot_token_env_key=ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY,
      telegram_bot_name=None,
      telegram_bot_name_env_key=ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY,      
      processor_handler=None,            
      system_prompt=None,
      agent_type="API",
      api_token_env_key=ENVIRONMENT.TELEGRAM_API_AGENT_TOKEN_ENV_KEY,
      api_token=None,
      rag_source_url=None,
      **kwargs
    ):
      
      """
      Create a new conversational Telegram bot on a node.
      
      Parameters
      ----------
      
      node : str
          Address or Name of the ratio1 Edge Protocol edge node that will handle this Telegram bot.
          
      name : str
          Name of the Telegram bot. 
          
      signature : str, optional 
          The signature of the plugin that will be used. Defaults to PLUGIN_SIGNATURES.TELEGRAM_BASIC_BOT_01.
          
      telegram_bot_token : str, optional  
          The Telegram bot token. Defaults to None.
          
      telegram_bot_token_env_key : str, optional
          The environment variable key that holds the Telegram bot token. Defaults to ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY.
          
      telegram_bot_name : str, optional
          The Telegram bot name. Defaults to None.
          
      telegram_bot_name_env_key : str, optional 
          The environment variable key that holds the Telegram bot name. Defaults to ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY.
          
      system_prompt : str, optional
          The system prompt. Defaults to None.
          
      agent_type : str, optional
          The agent type. Defaults to "API".
          
      api_token_env_key : str, optional
          The environment variable key that holds the API token. Defaults to ENVIRONMENT.TELEGRAM_API_AGENT_TOKEN_ENV_KEY.
          
      api_token : str, optional 
          The API token. Defaults to None.
          
      rag_source_url : str, optional
          The RAG database source URL upon which the bot will be able to generate responses. Defaults to None.
          
      Returns
      -------
      tuple 
          `Pipeline` and a `Instance` objects tuple.
      """      
      if agent_type == "API":
        if api_token is None:
          api_token = os.getenv(api_token_env_key)
          if api_token is None:
            message = f"Warning! No API token provided as via env {ENVIRONMENT.TELEGRAM_API_AGENT_TOKEN_ENV_KEY} or explicitly as `api_token` param."
            raise ValueError(message)
      
      if telegram_bot_token is None:
        telegram_bot_token = os.getenv(telegram_bot_token_env_key)
        if telegram_bot_token is None:
          message = f"Warning! No Telegram bot token provided as via env {ENVIRONMENT.TELEGRAM_BOT_TOKEN_ENV_KEY} or explicitly as `telegram_bot_token` param."
          raise ValueError(message)
        
      if telegram_bot_name is None:
        telegram_bot_name = os.getenv(telegram_bot_name_env_key)
        if telegram_bot_name is None:
          message = f"Warning! No Telegram bot name provided as via env {ENVIRONMENT.TELEGRAM_BOT_NAME_ENV_KEY} or explicitly as `telegram_bot_name` param."
          raise ValueError(message)

      

      pipeline: Pipeline = self.create_pipeline(
        node=node,
        name=name,
        # default TYPE is "Void"
      )

      proc_func_args, proc_func_base64_code =[], None
      if processor_handler is not None:
        _, proc_func_args, proc_func_base64_code = pipeline._get_method_data(processor_handler)
      
      
      obfuscated_token = telegram_bot_token[:4] + "*" * (len(telegram_bot_token) - 4)      
      self.P(f"Creating telegram bot {telegram_bot_name} with token {obfuscated_token}...", color='b')      
      instance = pipeline.create_plugin_instance(
        signature=signature,
        instance_id=self.log.get_unique_id(),

        telegram_bot_token=telegram_bot_token,
        telegram_bot_name=telegram_bot_name,

        processor_handler=proc_func_base64_code, # not mandatory
        processor_handler_args=proc_func_args, # not mandatory

        system_prompt=system_prompt,
        agent_type=agent_type,
        api_token=api_token,
        rag_source_url=rag_source_url,
        **kwargs
      )      
      return pipeline, instance    
    

    def broadcast_instance_command_and_wait_for_response_payload(
      self,
      instances,
      require_responses_mode="any",
      command={},
      payload=None,
      command_params=None,
      timeout=10,
      response_params_key="COMMAND_PARAMS"
    ):
      # """
      # Send a command to multiple instances and wait for the responses.
      # This method can wait until any or all of the instances respond.

      # """
      """
      Send a command to multiple instances and wait for the responses.
      This method can wait until any or all of the instances respond.

      Parameters
      ----------

      instances : list[Instance]
          The list of instances to send the command to.
      require_responses_mode : str, optional
          The mode to wait for the responses. Can be 'any' or 'all'.
          Defaults to 'any'.
      command : str | dict, optional
          The command to send. Defaults to {}.
      payload : dict, optional
          The payload to send. This contains metadata, not used by the Edge Node. Defaults to None.
      command_params : dict, optional
          The command parameters. Can be instead of `command`. Defaults to None.
      timeout : int, optional
          The timeout in seconds. Defaults to 10.
      response_params_key : str, optional
          The key in the response that contains the response parameters.
          Defaults to 'COMMAND_PARAMS'.

      Returns
      -------
      response_payload : Payload
          The response payload.
      """

      if len(instances) == 0:
        self.P("Warning! No instances provided.", color='r', verbosity=1)
        return None

      lst_result_payload = [None] * len(instances)
      uid = self.log.get_uid()

      def wait_payload_on_data(pos):
        def custom_func(pipeline, data):
          nonlocal lst_result_payload, pos
          if response_params_key in data and data[response_params_key].get("SDK_REQUEST") == uid:
            lst_result_payload[pos] = data
          return
        # end def custom_func
        return custom_func
      # end def wait_payload_on_data

      lst_attachment_instance = []
      for i, instance in enumerate(instances):
        attachment = instance.temporary_attach(on_data=wait_payload_on_data(i))
        lst_attachment_instance.append((attachment, instance))
      # end for

      if payload is None:
        payload = {}
      payload["SDK_REQUEST"] = uid

      lst_instance_transactions = []
      for instance in instances:
        instance_transactions = instance.send_instance_command(
          command=command,
          payload=payload,
          command_params=command_params,
          wait_confirmation=False,
          timeout=timeout,
        )
        lst_instance_transactions.append(instance_transactions)
      # end for send commands

      if require_responses_mode == "all":
        self.wait_for_all_sets_of_transactions(lst_instance_transactions)
      elif require_responses_mode == "any":
        self.wait_for_any_set_of_transactions(lst_instance_transactions)

      start_time = tm()

      condition_all = any([x is None for x in lst_result_payload]) and require_responses_mode == "all"
      condition_any = all([x is None for x in lst_result_payload]) and require_responses_mode == "any"
      while tm() - start_time < 3 and (condition_all or condition_any):
        sleep(0.1)
        condition_all = any([x is None for x in lst_result_payload]) and require_responses_mode == "all"
        condition_any = all([x is None for x in lst_result_payload]) and require_responses_mode == "any"
      # end while

      for attachment, instance in lst_attachment_instance:
        instance.temporary_detach(attachment)
      # end for detach

      return lst_result_payload

    def get_client_address(self):
      return self.bc_engine.address
    
    @property
    def client_address(self):
      return self.get_client_address()

    
    def get_node_whitelist(self, node):
      """
      Get the whitelist of a node.
      Parameters
      ----------
      node : str
          The address or name of the Ratio1 edge node.

      Returns
      -------
      list[str]
          The whitelist of the node.
      """
      node = self.__get_node_address(node)
      wl = self._dct_node_whitelist.get(node, [])
      res = []
      for addr in wl:
        alias = self.get_node_alias(addr)
        paddr = self.bc_engine.maybe_add_prefix(addr)
        res.append(paddr + '  ' + str(alias))
      return res


    def __wait_for_supervisors_net_mon_data(
      self, 
      supervisor=None, 
      timeout=10, 
      min_supervisors=2
    ):
      # the following loop will wait for the desired number of supervisors to appear online
      # for the current session
      start = tm()      
      result = False
      while (tm() - start) < timeout:
        if supervisor is not None:
          if supervisor in self.__current_network_statuses:
            result = True
            break
        elif len(self.__current_network_statuses) >= min_supervisors:
          result = True
          break
        sleep(0.1)
      elapsed = tm() - start      
      # end while
      # done waiting for supervisors
      return result, elapsed
      
      
    def get_all_nodes_pipelines(self):
      # TODO: Bleo inject this function in __on_hb and maybe_process_net_config and dump result
      return self._dct_online_nodes_pipelines

    
    def get_network_known_nodes(
      self, 
      timeout=10, 
      online_only=False, 
      supervisors_only=False,
      min_supervisors=2,
      allowed_only=False,
      supervisor=None,
      df_only=False,
      debug=False,
      eth=False,
      all_info=False,
    ):
      """
      This function will return a Pandas dataframe  known nodes in the network based on
      all the net-mon messages received so far.
      
      Parameters
      ----------
      
      timeout : int, optional
          The maximum time to wait for the desired number of supervisors to appear online.
          Defaults to 10.
          
      online_only : bool, optional  
          If True, will return only the online nodes. Defaults to False.
      
      supervisors_only : bool, optional
          If True, will return only the supervisors. Defaults to False.
          
      min_supervisors : int, optional 
          The minimum number of supervisors to wait for. Defaults to 2.
          
      allowed_only : bool, optional 
          If True, will return only the allowed nodes. Defaults to False.
          
      supervisor : str, optional  
          The supervisor to wait for. Defaults to None.
          
      df_only : bool, optional
          If True, will return only the Pandas dataframe. Defaults to False.
          
          
      eth: bool, optional
          If True, will use the nodes eth addresses instead of internal. Defaults to False.
          It will also display extra info about node wallets (ETH and $R1 balances)
          
      all_info: bool, optional
          If True, will return all the information. Defaults to False.
          
      Returns
      -------
      
      dict
          A "doct-dict" dictionary containing the report, the reporter and the number of supervisors.
            .report : DataFrame - The report containing the known nodes in the network.
            .reporter : str - The reporter of the report.
            .reporter_alias : str - The alias of the reporter.
            .nr_super : int - The number of supervisors.
            .elapsed : float - The elapsed time.
          

      
      """
      mapping = OrderedDict({
        'Address': PAYLOAD_DATA.NETMON_ADDRESS,
        'Alias'  : PAYLOAD_DATA.NETMON_EEID,
        'Seen ago' : PAYLOAD_DATA.NETMON_LAST_SEEN,
        'Version' : PAYLOAD_DATA.NETMON_NODE_VERSION,
        'State': PAYLOAD_DATA.NETMON_STATUS_KEY,
        'Uptime' : PAYLOAD_DATA.NETMON_UPTIME,
        'Last probe' : PAYLOAD_DATA.NETMON_LAST_REMOTE_TIME,
        'Zone' : PAYLOAD_DATA.NETMON_NODE_UTC,
        'Oracle' : PAYLOAD_DATA.NETMON_IS_SUPERVISOR,
        'Peered' : PAYLOAD_DATA.NETMON_WHITELIST,
      })
      if all_info:
        mapping = OrderedDict({
          # we assign dummy integer values to the computed columns 
          # and we will filter them 
          'ETH Address': 1,
          **mapping
        })
      if eth or all_info:
        mapping = OrderedDict({
          **mapping,
          'ETH' : 2,
          '$R1' : 3,
        })        
      # end if eth or all_info
      res = OrderedDict()
      for k in mapping:
        res[k] = []

      reverse_mapping = {v: k for k, v in mapping.items()}

      result, elapsed = self.__wait_for_supervisors_net_mon_data(
        supervisor=supervisor,
        timeout=timeout,
        min_supervisors=min_supervisors,
      )
      best_super = 'ERROR'
      best_super_alias = 'ERROR'
      
      if len(self.__current_network_statuses) > 0:
        best_info = {}
        for supervisor, net_info in self.__current_network_statuses.items():
          if len(net_info) > len(best_info):
            best_info = net_info
            best_super = supervisor
        best_super_alias = None
        # done found best supervisor
        for _, node_info in best_info.items():
          is_online = node_info.get(PAYLOAD_DATA.NETMON_STATUS_KEY, None) == PAYLOAD_DATA.NETMON_STATUS_ONLINE
          is_supervisor = node_info.get(PAYLOAD_DATA.NETMON_IS_SUPERVISOR, False)
          # the following will get the whitelist for the current inspected  node
          # without calling self.get_allowed_nodes but instead using the netmon data
          whitelist = node_info.get(PAYLOAD_DATA.NETMON_WHITELIST, [])
          version = node_info.get(PAYLOAD_DATA.NETMON_NODE_VERSION, '0.0.0')
          client_is_allowed = self.bc_engine.contains_current_address(whitelist)          
          if allowed_only and not client_is_allowed:
            continue
          if online_only and not is_online:
            continue
          if supervisors_only and not is_supervisor:
            continue
          for key, column in reverse_mapping.items():
            if isinstance(key, int):
              # if the key is an integer, then it is a computed column
              continue
            val = node_info.get(key, None)
            if key == PAYLOAD_DATA.NETMON_LAST_REMOTE_TIME:
              # val hols a string '2024-12-23 23:50:16.462155' and must be converted to a datetime
              val = dt.strptime(val, '%Y-%m-%d %H:%M:%S.%f')              
              val = val.replace(microsecond=0) # strip the microseconds
            elif key == PAYLOAD_DATA.NETMON_LAST_SEEN:
              # convert val (seconds) to a human readable format
              val = seconds_to_short_format(val)
            elif key == PAYLOAD_DATA.NETMON_ADDRESS:
              if self.bc_engine._remove_prefix(val) == self.bc_engine._remove_prefix(best_super):
                # again self.get_node_alias(best_super) might not work if using the hb data
                best_super_alias = node_info.get(PAYLOAD_DATA.NETMON_EEID, None)
              val = self.bc_engine._add_prefix(val)
              add_balance = False
              if all_info:
                val_eth = self.bc_engine.node_address_to_eth_address(val)
                res['ETH Address'].append(val_eth)
                eth_addr = val_eth
                add_balance = True
              elif eth:
                val = self.bc_engine.node_address_to_eth_address(val)
                eth_addr = val
                add_balance = True
              if add_balance:
                eth_balance = self.bc_engine.web3_get_balance_eth(eth_addr)
                r1_balance = self.bc_engine.web3_get_balance_r1(eth_addr)
                res['ETH'].append(round(eth_balance,4))
                res['$R1'].append(round(r1_balance,4))
            elif key == PAYLOAD_DATA.NETMON_WHITELIST:
              val = client_is_allowed
            elif key in [PAYLOAD_DATA.NETMON_STATUS_KEY, PAYLOAD_DATA.NETMON_NODE_VERSION]:
              val = val.split(' ')[0]
            res[column].append(val)                        
        # end for
      # end if
      pd.options.display.float_format = '{:.1f}'.format
      df_res = pd.DataFrame(res)
      if not all_info:
        df_res = df_res.drop(
          columns=['State', 'Last probe']
        )
      dct_result = _DotDict({
        SESSION_CT.NETSTATS_REPORT : df_res,
        SESSION_CT.NETSTATS_REPORTER : best_super,
        SESSION_CT.NETSTATS_REPORTER_ALIAS : best_super_alias,
        SESSION_CT.NETSTATS_NR_SUPERVISORS : len(self.__current_network_statuses),
        SESSION_CT.NETSTATS_ELAPSED : elapsed,
      })
      if debug:
        self.P(f"Peering:\n{json.dumps(self._dct_can_send_to_node, indent=2)}", color='y')
        self.P(f"Used netmon data from {best_super} ({best_super_alias}):\n{json.dumps(best_info, indent=2)}", color='y')
      if df_only:
        return dct_result[SESSION_CT.NETSTATS_REPORT]
      return dct_result


  def date_to_readable(self, date, check_none=False, start_time=None, pending_threshold=SHOW_PENDING_THRESHOLD):
    """
    Convert a date to a human-readable format.

    Parameters
    ----------

    date : str
        The date to convert.
    check_none : bool, optional
        If True, and the date is None it will check if too much time passed from the start time.
        If too much time passed, it will return 'Error!', otherwise, it will return 'Pending'.
        If False, it will return 'Never' if the date is None.
        Defaults to False.
    start_time : str, optional
        The start time to compare with the date in case it is None. Defaults to None.
    pending_threshold : int, optional
        The threshold in seconds to consider a date as pending. Defaults to SHOW_PENDING_THRESHOLD.
        If the time passed since start_time is greater than pending_threshold and
        check_none is set to True, it will return 'Error!'.

    Returns
    -------

    str
        The human-readable date.
    """
    if date is None:
      if not check_none or start_time is None:
        return 'Never'
      # endif not check_none
      start_dt = self.log.str_to_date(start_time, fmt='%Y-%m-%d %H:%M:%S.%f')
      since_start = (dt.now() - start_dt).total_seconds()
      if since_start > pending_threshold:
        return 'Error!'
      return 'Pending'
    # endif date is None
    if date.startswith('1970'):
      return 'Never'
    if '.' in date:
      date = date.split('.')[0]
    return date


  def get_nodes_apps(
    self, 
    node=None, 
    owner=None, 
    show_full=False, 
    as_json=False, 
    show_errors=False, 
    as_df=False
  ):
    """
    Get the workload status of a node.
    
    Parameters
    ----------

    node : str, optional
        The address or name of the ratio1 Edge Protocol edge node. Defaults to None.
    
    owner : str, optional
        The owner of the apps to filter. Defaults to None.
        
    show_full : bool, optional  
        If True, will show the full configuration of the apps. Defaults to False.
        
    as_json : bool, optional
        If True, will return the result as a JSON. Defaults to False.
        
    show_errors : bool, optional 
        If True, will show the errors. Defaults to False.
    
    as_df : bool, optional  
        If True, will return the result as a Pandas DataFrame. Defaults to False.
 

    Returns
    -------

    list
        A list of dictionaries containing the workload status
        of the specified node.
        
        
    """
    lst_plugin_instance_data = []    
    if node is None:
      nodes = self.get_active_nodes()
    else:
      nodes = [node]
    found_nodes = []
    for node in nodes:
      short_addr = self._shorten_addr(node)      
      # 2. Wait for node to appear online    
      node_found = self.wait_for_node(node)
      if node_found:
        found_nodes.append(node)
      
      # 3. Check if the node is peered with the client
      is_allowed = self.is_peered(node)
      if not is_allowed:
        if show_errors:
          log_with_color(f"Node {short_addr} is not peered with this client. Skipping..", color='r')
        continue
      
      # 4. Wait for node to send the configuration.
      self.wait_for_node_configs(node)
      apps = self.get_active_pipelines(node)
      if apps is None:
        if show_errors:
          log_with_color(f"No apps found on node {short_addr}. Client might not be authorized", color='r')
        continue
      
      # 5. Maybe exclude admin application.
      if not show_full:
        apps = {k: v for k, v in apps.items() if str(k).lower() != 'admin_pipeline'}
        
      # 6. Show the apps
      if as_json:
        # Will print a big JSON with all the app configurations.
        lst_plugin_instance_data.append({k: v.get_full_config() for k, v in apps.items()})
      else:
        for pipeline_name, pipeline in apps.items():
          pipeline_owner = pipeline.config.get("INITIATOR_ADDR")
          if owner is not None and owner != pipeline_owner:
            continue
          pipeline_alias = pipeline.config.get("INITIATOR_ID")
          for instance in pipeline.lst_plugin_instances:
            instance_status = instance.get_status()
            if len(instance_status) == 0:
              # this instance is only present in config but is NOT loaded so ignore it
              continue
            start_time = instance_status.get(HB.ACTIVE_PLUGINS_INFO.INIT_TIMESTAMP)
            last_probe = instance_status.get(HB.ACTIVE_PLUGINS_INFO.EXEC_TIMESTAMP)
            last_data = instance_status.get(HB.ACTIVE_PLUGINS_INFO.LAST_PAYLOAD_TIME)
            dates = [start_time, last_data]
            error_dates = [
              instance_status.get(HB.ACTIVE_PLUGINS_INFO.FIRST_ERROR_TIME),
              instance_status.get(HB.ACTIVE_PLUGINS_INFO.LAST_ERROR_TIME),
            ]
            dates = [self.date_to_readable(x, check_none=False) for x in dates]
            error_dates = [self.date_to_readable(x, check_none=False) for x in error_dates]
            last_probe = self.date_to_readable(last_probe, check_none=True, start_time=start_time)

            lst_plugin_instance_data.append({
              'Node'  : node,
              'Owner' : pipeline_owner,
              'Alias' : pipeline_alias,
              'App': pipeline_name,
              'Plugin': instance.signature,
              'Id': instance.instance_id,
              'Start' : dates[0],
              'Probe' : last_probe,
              'Data' : dates[1],
              'LastError': error_dates[1],
            })
          # endfor instances in app
        # endfor apps
      # endif as_json or as dict-for-df
    # endfor nodes  
    if len(found_nodes) == 0:
      log_with_color(f'Node(s) {nodes} not found. Please check the configuration.', color='r')
      return 
    if as_df:
      color_condition = lambda x: (x['LastError'] != 'Never' or x['Probe'] == 'Error!')
      df = self.log.colored_dataframe(lst_plugin_instance_data, color_condition=color_condition)
      if not (df.empty or df.shape[0] == 0):
        df['Node'] = df['Node'].apply(lambda x: self._shorten_addr(x))
        df['Owner'] = df['Owner'].apply(lambda x: self._shorten_addr(x))
      # end if not empty
      return df
    return lst_plugin_instance_data
  
