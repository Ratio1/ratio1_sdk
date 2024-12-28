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
from ..bc import DefaultBlockEngine, _DotDict
from ..const import (
  COMMANDS, ENVIRONMENT, HB, PAYLOAD_DATA, STATUS_TYPE, 
  PLUGIN_SIGNATURES, DEFAULT_PIPELINES,
  BLOCKCHAIN_CONFIG
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
  load_user_defined_config, get_user_config_file, get_user_folder, seconds_to_short_format
)

# from ..default.instance import PLUGIN_TYPES # circular import

# TODO: add support for remaining commands from EE

DEBUG_MQTT_SERVER = "r9092118.ala.eu-central-1.emqxsl.com"


class GenericSession(BaseDecentrAIObject):
  """
  A Session is a connection to a communication server which provides the channel to interact with nodes from the Naeural Edge Protocol network.
  A Session manages `Pipelines` and handles all messages received from the communication server.
  The Session handles all callbacks that are user-defined and passed as arguments in the API calls.
  """
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
              name='pySDK',
              encrypt_comms=True,
              config={},
              filter_workers=None,
              log: Logger = None,
              on_payload=None,
              on_notification=None,
              on_heartbeat=None,
              debug_silent=True,
              silent=False,
              verbosity=1,
              dotenv_path=None,
              show_commands=False,
              blockchain_config=BLOCKCHAIN_CONFIG,
              bc_engine=None,
              formatter_plugins_locations=['plugins.io_formatters'],
              root_topic="naeural",
              local_cache_base_folder=None,
              local_cache_app_folder='_local_cache',
              use_home_folder=False,
              **kwargs
            ) -> None:
    """
    A Session is a connection to a communication server which provides the channel to interact with nodes from the Naeural Edge Protocol network.
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
        The name of this connection, used to identify owned pipelines on a specific Naeural Edge Protocol edge node.
        The name will be used as `INITIATOR_ID` and `SESSION_ID` when communicating with Naeural Edge Protocol edge nodes, by default 'pySDK'
    config : dict, optional
        Configures the names of the channels this session will connect to.
        If using a Mqtt server, these channels are in fact topics.
        Modify this if you are absolutely certain of what you are doing.
        By default {}
    filter_workers: list, optional
        If set, process the messages that come only from the nodes from this list.
        Defaults to None
    show_commands : bool
        If True, will print the commands that are being sent to the Naeural Edge Protocol edge nodes.
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
        
    silent : bool, optional
        This flag will disable all logs, set to 'False` for a more verbose log, by default False
        The logs will still be recored in the log file even if this flag is set to True.
        
    dotenv_path : str, optional
        Path to the .env file, by default None. If None, the path will be searched in the current working directory and in the directories of the files from the call stack.
    root_topic : str, optional
        This is the root of the topics used by the SDK. It is used to create the topics for the communication channels.
        Defaults to "naeural"
    """

    # TODO: maybe read config from file?
    self._config = {**self.default_config, **config}

    if root_topic is not None:
      for key in self._config.keys():
        if isinstance(self._config[key], dict) and 'TOPIC' in self._config[key]:
          if isinstance(self._config[key]["TOPIC"], str) and self._config[key]["TOPIC"].startswith("{}"):
            nr_empty = self._config[key]["TOPIC"].count("{}")
            self._config[key]["TOPIC"] = self._config[key]["TOPIC"].format(root_topic, *(["{}"] * (nr_empty - 1)))
    # end if root_topic

    self.log = log
    self.name = name
    self.silent = silent

    self._verbosity = verbosity
    self.encrypt_comms = encrypt_comms

    self._dct_online_nodes_pipelines: dict[str, Pipeline] = {}
    self._dct_online_nodes_last_heartbeat: dict[str, dict] = {}
    self._dct_can_send_to_node: dict[str, bool] = {}
    self._dct_node_last_seen_time = {}
    self._dct_node_addr_name = {}
    self.online_timeout = 60
    self.filter_workers = filter_workers
    self.__show_commands = show_commands
    
    # this is used to store data received from net-mon instances
    self.__current_network_statuses = {} 

    pwd = pwd or kwargs.get('password', kwargs.get('pass', None))
    user = user or kwargs.get('username', None)
    host = host or kwargs.get('hostname', None)
    
    ## now we prepare config via ~/.naeural/config or .env
    self.__fill_config(host, port, user, pwd, secured, dotenv_path)
    ## end config

    self.custom_on_payload = on_payload
    self.custom_on_heartbeat = on_heartbeat
    self.custom_on_notification = on_notification

    self.own_pipelines = []

    self.__running_callback_threads = False
    self.__running_main_loop_thread = False
    self.__closed_everything = False

    self.sdk_main_loop_thread = Thread(target=self.__main_loop, daemon=True)
    self.__formatter_plugins_locations = formatter_plugins_locations

    self.__bc_engine = bc_engine
    self.__blockchain_config = blockchain_config

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
    
      
    super(GenericSession, self).__init__(
      log=log, 
      DEBUG=not debug_silent, 
      create_logger=True,
      silent=self.silent,
      local_cache_base_folder=local_cache_base_folder,
      local_cache_app_folder=local_cache_app_folder,
    )
    return

  def startup(self):
    # start the blockchain engine assuming config is already set
    self.__start_blockchain(
      self.__bc_engine, self.__blockchain_config, 
      user_config=self.__user_config_loaded,
    )
    # end bc_engine
    self.formatter_wrapper = IOFormatterWrapper(self.log, plugin_search_locations=self.__formatter_plugins_locations)

    self._connect()

    self.P("Created {} comms session '{}' from <{}> SDKv{}.".format(
      "decrypted" if not self.encrypt_comms else "encrypted", 
      self.name, self.bc_engine.address, self.log.version
    ))
    
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
          The address of the Naeural Edge Protocol edge node that sent the message.

      Returns
      -------
      bool
          True if the message should be ignored, False otherwise.
      """
      return self.filter_workers is not None and node_addr not in self.filter_workers

    def __track_online_node(self, node_addr, node_id):
      """
      Track the last time a node was seen online.

      Parameters
      ----------
      node_addr : str
          The address of the Naeural Edge Protocol edge node that sent the message.
      """
      self._dct_node_last_seen_time[node_addr] = tm()
      self._dct_node_addr_name[node_addr] = node_id
      return

    def __track_allowed_node(self, node_addr, dict_msg):
      """
      Track if this session is allowed to send messages to node.

      Parameters
      ----------
      node_addr : str
          The address of the Naeural Edge Protocol edge node that sent the message.
      dict_msg : dict
          The message received from the communication server.
      """
      node_whitelist = dict_msg.get(HB.EE_WHITELIST, [])
      node_secured = dict_msg.get(HB.SECURED, False)

      self._dct_can_send_to_node[node_addr] = not node_secured or self.bc_engine.address_no_prefix in node_whitelist or self.bc_engine.address == node_addr
      return

    def __on_heartbeat(self, dict_msg: dict, msg_node_addr, msg_pipeline, msg_signature, msg_instance):
      """
      Handle a heartbeat message received from the communication server.

      Parameters
      ----------
      dict_msg : dict
          The message received from the communication server
      msg_node_addr : str
          The address of the Naeural Edge Protocol edge node that sent the message.
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
      # track the node based on heartbeat - a normal heartbeat means the node is online
      # however this can lead to long wait times for the first heartbeat for all nodes
      self.__track_online_node(msg_node_addr, msg_node_id)

      msg_active_configs = dict_msg.get(HB.CONFIG_STREAMS)
      if msg_active_configs is None:
        return

      # default action
      if msg_node_addr not in self._dct_online_nodes_pipelines:
        self._dct_online_nodes_pipelines[msg_node_addr] = {}
      for config in msg_active_configs:
        pipeline_name = config[PAYLOAD_DATA.NAME]
        pipeline: Pipeline = self._dct_online_nodes_pipelines[msg_node_addr].get(pipeline_name, None)
        if pipeline is not None:
          pipeline._sync_configuration_with_remote({k.upper(): v for k, v in config.items()})
        else:
          self._dct_online_nodes_pipelines[msg_node_addr][pipeline_name] = self.__create_pipeline_from_config(
            msg_node_addr, config)

      # TODO: move this call in `__on_message_default_callback`
      if self.__maybe_ignore_message(msg_node_addr):
        return

      # pass the heartbeat message to open transactions
      with self.__open_transactions_lock:
        open_transactions_copy = self.__open_transactions.copy()
      # end with
      for transaction in open_transactions_copy:
        transaction.handle_heartbeat(dict_msg)

      self.D("Received hb from: {}".format(msg_node_addr), verbosity=2)

      self.__track_allowed_node(msg_node_addr, dict_msg)

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
          The address of the Naeural Edge Protocol edge node that sent the message.
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
                msg_node_addr,
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
      msg_signature : str
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
          all_addresses = [
            x[PAYLOAD_DATA.NETMON_ADDRESS] for x in current_network.values()
          ]
          online_addresses = [
            x[PAYLOAD_DATA.NETMON_ADDRESS] for x in current_network.values() 
            if x[PAYLOAD_DATA.NETMON_STATUS_KEY] == PAYLOAD_DATA.NETMON_STATUS_ONLINE
          ] 
          self.P(f"Net config from <{sender_addr}> `{ee_id}`:  {len(online_addresses)}/{len(all_addresses)}", color='y')
          self.__current_network_statuses[sender_addr] = current_network
        # end if current_network is valid
      # end if NET_MON_01
      return
      

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
          The address of the Naeural Edge Protocol edge node that sent the message.
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
      
      self.__maybe_process_net_mon(dict_msg, msg_pipeline, msg_signature)

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
        self.bc_engine = DefaultBlockEngine(
          log=self.log,
          name=self.name,
          config=blockchain_config,
          verbosity=self._verbosity,
          user_config=user_config,
        )
      except:
        raise ValueError("Failure in private blockchain setup:\n{}".format(traceback.format_exc()))
      return

    def __start_main_loop_thread(self):
      self._main_loop_thread = Thread(target=self.__main_loop, daemon=True)

      self.__running_main_loop_thread = True
      self._main_loop_thread.start()
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

    def close(self, close_pipelines=False, wait_close=False, **kwargs):
      """
      Close the session, releasing all resources and closing all threads
      Resources are released in the main loop thread, so this method will block until the main loop thread exits.
      This method is blocking.

      Parameters
      ----------
      close_pipelines : bool, optional
          close all the pipelines created by or attached to this session (basically calling `.close_own_pipelines()` for you), by default False
      wait_close : bool, optional
          If `True`, will wait for the main loop thread to exit. Defaults to `False`
      """

      if close_pipelines:
        self.__close_own_pipelines(wait=wait_close)

      self.__running_main_loop_thread = False

      # wait for the main loop thread to exit
      while not self.__closed_everything and wait_close:
        sleep(0.1)

      return

    def _connect(self) -> None:
      """
      Connect to the communication server using the credentials provided when creating this instance.
      """
      raise NotImplementedError

    def _send_payload(self, to, payload):
      """
      Send a payload to a node.

      Parameters
      ----------
      to : str
          The name of the Naeural Edge Protocol edge node that will receive the payload.
      payload : dict
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
      except KeyboardInterrupt:
        self.P("CTRL+C detected. Stopping loop.", color='r', verbosity=1)

      if close_session:
        self.close(close_pipelines, wait_close=True)

      return

    def sleep(self, wait=True):
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
      except KeyboardInterrupt:
        self.P("CTRL+C detected. Stopping loop.", color='r', verbosity=1)
      return

  # Utils
  if True:
    def __fill_config(self, host, port, user, pwd, secured, dotenv_path):
      """
      Fill the configuration dictionary with the credentials provided when creating this instance.


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

      # if the ~/.naeural/config file exists, load the credentials from there else try to load them from .env
      if not load_user_defined_config():        
        # this method will search for the credentials in the environment variables
        # the path to env file, if not specified, will be search in the following order:
        #  1. current working directory
        #  2-N. directories of the files from the call stack
        load_dotenv(dotenv_path=dotenv_path, verbose=False)
        if not self.silent:
          print("Loaded credentials from environment variables.", flush=True)
        self.__user_config_loaded = False
      else:
        if not self.silent:
          print(f"Loaded credentials from `{get_user_config_file()}`.", flush=True)
        self.__user_config_loaded = True
      # endif config loading from ~ or ./.env

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
        env_error = "Error: No user specified for Naeural Edge Protocol network connection. Please make sure you have the correct credentials in the environment variables within the .env file or provide them as params in code (not recommended due to potential security issue)."
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
        raise ValueError("Error: No password specified for Naeural Edge Protocol network connection")
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
        raise ValueError("Error: No host specified for Naeural Edge Protocol network connection")
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
        raise ValueError("Error: No port specified for Naeural Edge Protocol network connection")
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

    def __get_node_address(self, node):
      """
      Get the address of a node. If node is an address, return it. Else, return the address of the node.

      Parameters
      ----------
      node : str
          Address or Name of the node.

      Returns
      -------
      str
          The address of the node.
      """
      if node not in self.get_active_nodes():
        node = next((key for key, value in self._dct_node_addr_name.items() if value == node), node)
      return node

    def _send_command_to_box(self, command, worker, payload, show_command=False, session_id=None, **kwargs):
      """
      Send a command to a node.

      Parameters
      ----------
      command : str
          The command to send.
      worker : str
          The name of the Naeural Edge Protocol edge node that will receive the command.
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

      # This part is duplicated with the creation of payloads
      encrypt_payload = self.encrypt_comms
      if encrypt_payload and worker is not None:
        # TODO: use safe_json_dumps
        str_data = json.dumps(critical_data)
        str_enc_data = self.bc_engine.encrypt(str_data, worker)
        critical_data = {
          comm_ct.COMM_SEND_MESSAGE.K_EE_IS_ENCRYPTED: True,
          comm_ct.COMM_SEND_MESSAGE.K_EE_ENCRYPTED_DATA: str_enc_data,
        }
      else:
        critical_data[comm_ct.COMM_SEND_MESSAGE.K_EE_IS_ENCRYPTED] = False
        if encrypt_payload:
          critical_data[comm_ct.COMM_SEND_MESSAGE.K_EE_ENCRYPTED_DATA] = "Error! No receiver address found!"

      # endif
      msg_to_send = {
          **critical_data,
          comm_ct.COMM_SEND_MESSAGE.K_EE_ID: worker,
          comm_ct.COMM_SEND_MESSAGE.K_SESSION_ID: session_id or self.name,
          comm_ct.COMM_SEND_MESSAGE.K_INITIATOR_ID: self.name,
          comm_ct.COMM_SEND_MESSAGE.K_SENDER_ADDR: self.bc_engine.address,
          comm_ct.COMM_SEND_MESSAGE.K_TIME: dt.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
      }
      self.bc_engine.sign(msg_to_send, use_digest=True)
      if show_command:
        self.P("Sending command '{}' to '{}':\n{}".format(command, worker, json.dumps(msg_to_send, indent=2)),
               color='y',
               verbosity=1
               )
      self._send_payload(worker, msg_to_send)
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

    def __create_pipeline_from_config(self, node_addr, config):
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
                        **kwargs) -> Pipeline:
      """
      Create a new pipeline on a node. A pipeline is the equivalent of the "config file" used by the Naeural Edge Protocol edge node team internally.

      A `Pipeline` is a an object that encapsulates a one-to-many, data acquisition to data processing, flow of data.

      A `Pipeline` contains one thread of data acquisition (which does not mean only one source of data), and many
      processing units, usually named `Plugins`.

      An `Instance` is a running thread of a `Plugin` type, and one may want to have multiple `Instances`, because each can be configured independently.

      As such, one will work with `Instances`, by referring to them with the unique identifier (Pipeline, Plugin, Instance).

      In the documentation, the following refer to the same thing:
        `Pipeline` == `Stream`

        `Plugin` == `Signature`

      This call can busy-wait for a number of seconds to listen to heartbeats, in order to check if an Naeural Edge Protocol edge node is online or not.
      If the node does not appear online, a warning will be displayed at the stdout, telling the user that the message that handles the
      creation of the pipeline will be sent, but it is not guaranteed that the specific node will receive it.

      Parameters
      ----------
      node : str
          Address or Name of the Naeural Edge Protocol edge node that will handle this pipeline.
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
          **kwargs
      )
      self.own_pipelines.append(pipeline)
      return pipeline

    def get_node_name(self, node_addr):
      """
      Get the name of a node.

      Parameters
      ----------
      node_addr : str
          The address of the node.

      Returns
      -------
      str
          The name of the node.
      """
      return self._dct_node_addr_name.get(node_addr, None)

    def get_active_nodes(self):
      """
      Get the list of all Naeural Edge Protocol edge nodes that sent a message since this session was created, and that are considered online

      Returns
      -------
      list
          List of names of all the Naeural Edge Protocol edge nodes that are considered online

      """
      return [k for k, v in self._dct_node_last_seen_time.items() if tm() - v < self.online_timeout]

    def get_allowed_nodes(self):
      """
      Get the list of all active Naeural Edge Protocol edge nodes to whom this 
      ssion can send messages. This is based on the last heartbeat received from each individual node.

      Returns
      -------
      list[str]
          List of names of all the active Naeural Edge Protocol edge nodes to whom this session can send messages
      """
      active_nodes = self.get_active_nodes()
      return [node for node in self._dct_can_send_to_node if self._dct_can_send_to_node[node] and node in active_nodes]

    def get_active_pipelines(self, node):
      """
      Get a dictionary with all the pipelines that are active on this Naeural Edge Protocol edge node

      Parameters
      ----------
      node : str
          Address or Name of the Naeural Edge Protocol edge node

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
      Create a Pipeline object and attach to an existing pipeline on an Naeural Edge Protocol edge node.
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

      This call can busy-wait for a number of seconds to listen to heartbeats, in order to check if an Naeural Edge Protocol edge node is online or not.
      If the node does not appear online, a warning will be displayed at the stdout, telling the user that the message that handles the
      creation of the pipeline will be sent, but it is not guaranteed that the specific node will receive it.


      Parameters
      ----------
      node : str
          Address or Name of the Naeural Edge Protocol edge node that handles this pipeline.
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
      Create a new pipeline on a node, or attach to an existing pipeline on an Naeural Edge Protocol edge node.

      Parameters
      ----------
      node : str
          Address or Name of the Naeural Edge Protocol edge node that will handle this pipeline.
          
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
          The address or name of the Naeural Edge Protocol edge node.
      timeout : int, optional
          The timeout, by default 15

      Returns
      -------
      bool
          True if the node is online, False otherwise.
      """

      if verbose:
        self.P("Waiting for node '{}' to appear online...".format(node))

      _start = tm()
      found = self.check_node_online(node)
      while (tm() - _start) < timeout and not found:
        sleep(0.1)
        found = self.check_node_online(node)
      # end while

      if verbose:
        if found:
          self.P("Node '{}' is online.".format(node))
        else:
          self.P("Node '{}' did not appear online in {:.1f}s.".format(node, tm() - _start), color='r')
      return found

    def check_node_online(self, node, /):
      """
      Check if a node is online.

      Parameters
      ----------
      node : str
          The address or name of the Naeural Edge Protocol edge node.

      Returns
      -------
      bool
          True if the node is online, False otherwise.
      """
      return node in self.get_active_nodes() or node in self._dct_node_addr_name.values()

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
      name,
      signature,
      ngrok_edge_label=None,
      endpoints=None,
      use_ngrok=True,
      extra_debug=False,
      **kwargs
    ):
      """
      Create a new web app on a node.
      
      Parameters
      ----------
      
      node : str
          Address or Name of the Naeural Edge Protocol edge node that will handle this web app.
          
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
          List of addresses or Names of the Naeural Edge Protocol edge nodes that will handle this web app.
          
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

      ngrok_use_api = True
      use_ngrok = True
      kwargs.pop('use_ngrok', None)
      kwargs.pop('ngrok_use_api', None)
      
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
          Address or Name of the Naeural Edge Protocol edge node that will handle this Telegram bot.
          
      name : str
          Name of the Telegram bot. 
          
      signature : str, optional 
          The signature of the plugin that will be used. Defaults to PLUGIN_SIGNATURES.TELEGRAM_BASIC_BOT_01.
          
      message_handler : callable, optional  
          The message handler function that will be called when a message is received. Defaults to None.
          
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
      
      func_name, func_args, func_base64_code = pipeline._get_method_data(message_handler)
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
          Address or Name of the Naeural Edge Protocol edge node that will handle this Telegram bot.
          
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
      
      
      obfuscated_token = telegram_bot_token[:4] + "*" * (len(telegram_bot_token) - 4)      
      self.P(f"Creating telegram bot {telegram_bot_name} with token {obfuscated_token}...", color='b')      
      instance = pipeline.create_plugin_instance(
        signature=signature,
        instance_id=self.log.get_unique_id(),
        telegram_bot_token=telegram_bot_token,
        telegram_bot_name=telegram_bot_name,
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
    
    def get_network_known_nodes(
      self, 
      timeout=10, 
      online_only=False, 
      supervisors_only=False,
      min_supervisors=2,
      allowed_only=False,
      supervisor=None,
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
        'Last state': PAYLOAD_DATA.NETMON_STATUS_KEY,
        'Last probe' : PAYLOAD_DATA.NETMON_LAST_REMOTE_TIME,
        'Zone' : PAYLOAD_DATA.NETMON_NODE_UTC,
        'Supervisor' : PAYLOAD_DATA.NETMON_IS_SUPERVISOR,
        'Peered' : PAYLOAD_DATA.NETMON_WHITELIST,
      })
      reverse_mapping = {v: k for k, v in mapping.items()}
      res = OrderedDict()
      for k in mapping:
        res[k] = []

      # the following loop will wait for the desired number of supervisors to appear online
      # for the current session
      start = tm()      
      while (tm() - start) < timeout:
        if supervisor is not None:
          if supervisor in self.__current_network_statuses:
            break
        elif len(self.__current_network_statuses) >= min_supervisors:
          break
        sleep(0.1)
      elapsed = tm() - start
      # end while
      # done waiting for supervisors
      
      if len(self.__current_network_statuses) > 0:
        best_info = {}
        best_super = None
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
          client_is_allowed = self.bc_engine.contains_current_address(whitelist)          
          if allowed_only and not client_is_allowed:
            continue
          if online_only and not is_online:
            continue
          if supervisors_only and not is_supervisor:
            continue
          for key, column in reverse_mapping.items():
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
                # again self.get_node_name(best_super) might not work if using the hb data
                best_super_alias = node_info.get(PAYLOAD_DATA.NETMON_EEID, None)
              val = self.bc_engine._add_prefix(val)
            elif key == PAYLOAD_DATA.NETMON_WHITELIST:
              val = client_is_allowed
            res[column].append(val)          
        # end for
      # end if
      pd.options.display.float_format = '{:.1f}'.format
      dct_result = _DotDict({
        'report' : pd.DataFrame(res),
        'reporter' : best_super,
        'reporter_alias' : best_super_alias,
        'nr_super' : len(self.__current_network_statuses),
        'elapsed' : elapsed,
      })
      return dct_result
