import json

# BC Consts:
from ..bc.base import BCct as BC_CT
from . import heartbeat as HB

TLBR_POS = 'TLBR_POS'
PROB_PRC = 'PROB_PRC'
TYPE = 'TYPE'
COLOR_TAG = 'COLOR_TAG'

NOTIFICATION_TYPE = 'NOTIFICATION_TYPE'
STATUS_TYPE_KEY = NOTIFICATION_TYPE

# Notification types


class STATUS_TYPE:
  NOTIFICATION_TYPE = NOTIFICATION_TYPE
  STATUS_NORMAL = 'NORMAL'
  STATUS_EXCEPTION = 'EXCEPTION'
  STATUS_EMAIL = 'EMAIL'
  STATUS_ABNORMAL_FUNCTIONING = 'ABNORMAL FUNCTIONING'


class NOTIFICATION_CODES:
  # pipelines from 1 to 99
  PIPELINE_OK = 1  # basic config is ok
  PIPELINE_FAILED = -PIPELINE_OK

  PIPELINE_DATA_OK = PIPELINE_OK + 1  # data seems to flow
  PIPELINE_DATA_FAILED = -PIPELINE_DATA_OK

  PIPELINE_DCT_CONFIG_OK = PIPELINE_DATA_OK + 1  # dct config is ok
  PIPELINE_DCT_CONFIG_FAILED = -PIPELINE_DCT_CONFIG_OK

  PIPELINE_ARCHIVE_OK = PIPELINE_DCT_CONFIG_OK + 1  # archiving is ok
  PIPELINE_ARCHIVE_FAILED = -PIPELINE_ARCHIVE_OK

  # plugins from 100 to 999
  PLUGIN_CONFIG_OK = 100
  PLUGIN_CONFIG_FAILED = -PLUGIN_CONFIG_OK

  PLUGIN_INSTANCE_COMMAND_OK = 101
  PLUGIN_INSTANCE_COMMAND_FAILED = -PLUGIN_INSTANCE_COMMAND_OK

  PLUGIN_PAUSE_OK = 110
  PLUGIN_PAUSE_FAILED = -PLUGIN_PAUSE_OK

  PLUGIN_RESUME_OK = 111
  PLUGIN_RESUME_FAILED = -PLUGIN_RESUME_OK

  PLUGIN_WORKING_HOURS_SHIFT_START = 112
  PLUGIN_WORKING_HOURS_SHIFT_START_FAILED = -PLUGIN_WORKING_HOURS_SHIFT_START

  PLUGIN_WORKING_HOURS_SHIFT_END = 113
  PLUGIN_WORKING_HOURS_SHIFT_END_FAILED = -PLUGIN_WORKING_HOURS_SHIFT_END

  PLUGIN_CONFIG_IN_PAUSE_OK = 120
  PLUGIN_CONFIG_IN_PAUSE_FAILED = -PLUGIN_CONFIG_IN_PAUSE_OK

  # BUSINESS NOTIFICATIONS FROM 500 to 899

  # Example:
  # PLUGIN_SOMETHING_OK = 610
  # PLUGIN_SOMETHING_FAILED = -PLUGIN_SOMETHING_OK

  # END BUSINESS NOTIFICATIONS FROM 500 to 899

  PLUGIN_DELAYED = -999

  # comms from 1000
  COMMS_OK = 1000
  
  COMM_RECEIVED_BAD_COMMAND = -5000

  # serving from 10000
  SERVING_START_OK = 10000
  SERVING_START_FAILED = -SERVING_START_OK
  SERVING_START_FATAL_FAIL = -99999
  
  
  

  TAGS = {
    PIPELINE_OK: "PIPELINE_OK",
    PIPELINE_FAILED: "PIPELINE_FAILED",
    PIPELINE_DATA_OK: "PIPELINE_DATA_OK",
    PIPELINE_DATA_FAILED: "PIPELINE_DATA_FAILED",
    PIPELINE_DCT_CONFIG_OK: "PIPELINE_DCT_CONFIG_OK",
    PIPELINE_DCT_CONFIG_FAILED: "PIPELINE_DCT_CONFIG_FAILED",
    PIPELINE_ARCHIVE_OK: "PIPELINE_ARCHIVE_OK",
    PIPELINE_ARCHIVE_FAILED: "PIPELINE_ARCHIVE_FAILED",

    PLUGIN_CONFIG_OK: "PLUGIN_CONFIG_OK",
    PLUGIN_CONFIG_FAILED: "PLUGIN_CONFIG_FAILED",
    PLUGIN_INSTANCE_COMMAND_OK: "PLUGIN_INSTANCE_COMMAND_OK",
    PLUGIN_INSTANCE_COMMAND_FAILED: "PLUGIN_INSTANCE_COMMAND_FAILED",
    PLUGIN_PAUSE_OK: "PLUGIN_PAUSE_OK",
    PLUGIN_PAUSE_FAILED: "PLUGIN_PAUSE_FAILED",
    PLUGIN_RESUME_OK: "PLUGIN_RESUME_OK",
    PLUGIN_RESUME_FAILED: "PLUGIN_RESUME_FAILED",
    PLUGIN_DELAYED: "PLUGIN_DELAYED",
    PLUGIN_WORKING_HOURS_SHIFT_START: "PLUGIN_WORKING_HOURS_SHIFT_START",
    PLUGIN_WORKING_HOURS_SHIFT_START_FAILED: "PLUGIN_WORKING_HOURS_SHIFT_START_FAILED",
    PLUGIN_WORKING_HOURS_SHIFT_END: "PLUGIN_WORKING_HOURS_SHIFT_END",
    PLUGIN_WORKING_HOURS_SHIFT_END_FAILED: "PLUGIN_WORKING_HOURS_SHIFT_END_FAILED",

    PLUGIN_CONFIG_IN_PAUSE_OK: "PLUGIN_CONFIG_IN_PAUSE_OK",
    PLUGIN_CONFIG_IN_PAUSE_FAILED: "PLUGIN_CONFIG_IN_PAUSE_FAILED",

    SERVING_START_OK: "SERVING_START_OK",
    SERVING_START_FAILED: "SERVING_START_FAILED",
    SERVING_START_FATAL_FAIL: "SERVING_START_FATAL_FAIL",
    
    COMM_RECEIVED_BAD_COMMAND: "COMM_RECEIVED_BAD_COMMAND",

  }
  CODES = {v: k for k, v in TAGS.items()}

  # next section could be missing
  PIPELINE_OK_TAG = TAGS[PIPELINE_OK]
  PIPELINE_FAILED_TAG = TAGS[PIPELINE_FAILED]

  PLUGIN_CONFIG_OK_TAG = TAGS[PLUGIN_CONFIG_OK]
  PLUGIN_CONFIG_FAILED_TAG = TAGS[PLUGIN_CONFIG_FAILED]


class COMMANDS:
  COMMANDS = 'COMMANDS'
  RESTART = 'RESTART'
  STATUS = 'STATUS'
  STOP = 'STOP'
  UPDATE_CONFIG = 'UPDATE_CONFIG'
  DELETE_CONFIG = 'DELETE_CONFIG'
  UPDATE_PIPELINE_INSTANCE = 'UPDATE_PIPELINE_INSTANCE'
  BATCH_UPDATE_PIPELINE_INSTANCE = 'BATCH_UPDATE_PIPELINE_INSTANCE'
  PIPELINE_COMMAND = 'PIPELINE_COMMAND'
  ARCHIVE_CONFIG = 'ARCHIVE_CONFIG'
  DELETE_CONFIG_ALL = 'DELETE_CONFIG_ALL'
  ARCHIVE_CONFIG_ALL = 'ARCHIVE_CONFIG_ALL'
  ACTIVE_PLUGINS = 'ACTIVE_PLUGINS'
  RELOAD_CONFIG_FROM_DISK = 'RELOAD_CONFIG_FROM_DISK'
  FULL_HEARTBEAT = 'FULL_HEARTBEAT'
  TIMERS_ONLY_HEARTBEAT = 'TIMERS_ONLY_HEARTBEAT'
  SIMPLE_HEARTBEAT = 'SIMPLE_HEARTBEAT'
  INSTANCE_COMMAND = 'INSTANCE_COMMAND'
  COMMAND_PARAMS = 'COMMAND_PARAMS'

  FINISH_ACQUISITION = 'FINISH_ACQUISITION'


class PAYLOAD_DATA:
  EE_ENCRYPTED_DATA = 'EE_ENCRYPTED_DATA'
  EE_IS_ENCRYPTED = 'EE_IS_ENCRYPTED'
  INITIATOR_ID = 'INITIATOR_ID'
  INITIATOR_ADDR = 'INITIATOR_ADDR'
  MODIFIED_BY_ID = 'MODIFIED_BY_ID'
  MODIFIED_BY_ADDR = 'MODIFIED_BY_ADDR'
  SESSION_ID = 'SESSION_ID'
  STREAM_NAME = 'STREAM_NAME'
  NAME = 'NAME'
  INSTANCE_CONFIG = 'INSTANCE_CONFIG'
  SIGNATURE = 'SIGNATURE'
  INSTANCE_ID = 'INSTANCE_ID'
  TIME = 'TIME'
  EE_TIMESTAMP = 'EE_TIMESTAMP'
  EE_TIMEZONE = 'EE_TIMEZONE'
  EE_TZ = 'EE_TZ'
  SB_TIMESTAMP = EE_TIMESTAMP
  EE_MESSAGE_ID = 'EE_MESSAGE_ID'
  EE_MESSAGE_SEQ = 'EE_MESSAGE_SEQ'
  SB_MESSAGE_ID = EE_MESSAGE_ID
  EE_TOTAL_MESSAGES = 'EE_TOTAL_MESSAGES'
  SB_TOTAL_MESSAGES = EE_TOTAL_MESSAGES
  EE_FORMATTER = 'EE_FORMATTER'
  SB_IMPLEMENTATION = 'SB_IMPLEMENTATION'
  EE_EVENT_TYPE = 'EE_EVENT_TYPE'
  SB_EVENT_TYPE = 'SB_EVENT_TYPE'
  EE_PAYLOAD_PATH = 'EE_PAYLOAD_PATH'
  EE_PAYLOAD_INFO = 'EE_PAYLOAD_INFO'
  EE_VERSION = 'EE_VERSION'
  EE_ID = 'EE_ID'
  EE_PIPELINE_NAME = 'EE_PIPELINE_NAME'
  EE_SENDER = BC_CT.SENDER
  EE_HASH = BC_CT.HASH
  EE_SIGN = BC_CT.SIGN
  
  EE_ETH_ADDR = 'EE_ETH_SENDER'
  EE_ETH_SIGN = 'EE_ETH_SIGN'
  
  EE_DESTINATION = "EE_DEST" # can be either single address or list of addresses
  EE_DESTINATION_ID = "EE_DEST_ID" # can be either single alias or list of aliases

  NOTIFICATION = 'NOTIFICATION'
  INFO = 'INFO'

  TAGS = 'TAGS'

  ID_TAGS = 'ID_TAGS'
  
  NETMON_CURRENT_NETWORK = 'CURRENT_NETWORK'
  NETMON_STATUS_KEY = "working"
  NETMON_STATUS_ONLINE = "ONLINE"
  NETMON_ADDRESS = "address"
  NETMON_ETH_ADDRESS = "eth_address"
  NETMON_EEID = "eeid"
  NETMON_LAST_REMOTE_TIME = 'last_remote_time'
  NETMON_UPTIME = 'uptime'
  NETMON_NODE_UTC = 'node_utc'
  NETMON_LAST_SEEN = 'last_seen_sec'
  NETMON_IS_SUPERVISOR = 'is_supervisor'
  NETMON_WHITELIST = 'whitelist'
  NETMON_WHITELIST_MAP = 'WHITELIST_MAP'
  NETMON_NODE_SECURED = 'secured'
  NETMON_NODE_VERSION = 'version'
  NETMON_NODE_R1FS_ID = 'r1fs_id'
  NETMON_NODE_R1FS_ONLINE = 'r1fs_online'
  NETMON_NODE_R1FS_RELAY = 'r1fs_relay'
  NETMON_NODE_COMM_RELAY = 'comm_relay'
  NETMON_VERSION = 'NETMON_VERSION'
  NETMON_VERSION_V2 = 'v2'

  NETMON_TOP_LEVEL_KEEP_KEYS = {
    STREAM_NAME,
    SIGNATURE,
    INSTANCE_ID,
    SESSION_ID,
    INITIATOR_ID,
    INITIATOR_ADDR,
    MODIFIED_BY_ID,
    MODIFIED_BY_ADDR,
    TAGS,
    ID_TAGS,
    'USE_LOCAL_COMMS_ONLY',
    'PLUGIN_CATEGORY',
  }

  @staticmethod
  def maybe_encode_netmon_payload(full_payload: dict, log=None) -> dict:
    """
    Encode a NET_MON payload into the v2 wire format when possible.

    Parameters
    ----------
    full_payload : dict
      Candidate NET_MON payload already shaped like the normal wire dictionary.
    log : object, optional
      Logger-like object that must provide ``compress_text`` for the heartbeat
      zlib+base64 codec used by the NETMON compression plan.

    Returns
    -------
    dict
      The original payload when encoding is not applicable, or a new payload
      where ``EE_*`` and routing keys remain top-level and the NET_MON business
      body is moved into ``ENCODED_DATA`` under ``NETMON_VERSION='v2'``.

    Notes
    -----
    The helper is intentionally conservative:
    - non-dict inputs are returned unchanged
    - already-encoded v2 payloads are returned unchanged
    - serialization or compression capability failures fall back to the
      original payload instead of raising
    """
    if not isinstance(full_payload, dict):
      return full_payload

    if (
      full_payload.get(PAYLOAD_DATA.NETMON_VERSION) == PAYLOAD_DATA.NETMON_VERSION_V2
      and HB.ENCODED_DATA in full_payload
    ):
      return full_payload

    if log is None or not hasattr(log, 'compress_text'):
      return full_payload

    dct_top_level = {}
    dct_body = {}
    for key, value in full_payload.items():
      if key.startswith('EE_') or key in PAYLOAD_DATA.NETMON_TOP_LEVEL_KEEP_KEYS:
        dct_top_level[key] = value
      else:
        dct_body[key] = value

    if len(dct_body) == 0:
      return full_payload

    try:
      body_text = json.dumps(dct_body, ensure_ascii=True, separators=(",", ":"))
    except Exception:
      return full_payload

    return {
      **dct_top_level,
      PAYLOAD_DATA.NETMON_VERSION: PAYLOAD_DATA.NETMON_VERSION_V2,
      HB.ENCODED_DATA: log.compress_text(body_text),
    }
  
  @staticmethod
  def maybe_convert_netmon_whitelist(full_payload : dict) -> dict:
    """
    This function will convert each node individual whitelist from the compressed index-based
    version to the full address version if needed (EVM-based implementations only).    
    """
    current_network = full_payload.get(PAYLOAD_DATA.NETMON_CURRENT_NETWORK, {})
    dct_whitelist = full_payload.get(PAYLOAD_DATA.NETMON_WHITELIST_MAP, {})
    if len(dct_whitelist) == 0:
      return full_payload
    # now lets decompress the whitelists
    dct_idx_to_addr = {str(v): k for k, v in dct_whitelist.items()}
    for node_info in current_network.values():
      wl_indexes = node_info.get(PAYLOAD_DATA.NETMON_WHITELIST, [])
      if not isinstance(wl_indexes, list):
        wl_indexes = []
      full_wl = []
      for idx in wl_indexes:
        addr = dct_idx_to_addr.get(str(idx), None)
        if addr is not None:
          full_wl.append(addr)
      node_info[PAYLOAD_DATA.NETMON_WHITELIST] = full_wl
    return full_payload

  @staticmethod
  def maybe_decode_netmon_payload(full_payload: dict, log=None) -> dict:
    """
    Expand a NET_MON v2 payload back to the legacy business dictionary shape.

    Parameters
    ----------
    full_payload : dict
      Incoming payload dictionary that may contain ``NETMON_VERSION='v2'`` and
      heartbeat-style ``ENCODED_DATA``.
    log : object, optional
      Logger-like object that must provide ``decompress_text`` for the shared
      zlib+base64 decode path.

    Returns
    -------
    dict
      The same dictionary instance after an in-place merge of the decoded body,
      or the unchanged dictionary when the payload is not a NET_MON v2 message
      or the body cannot be decoded safely.

    Notes
    -----
    The helper is idempotent and fail-closed:
    - if ``CURRENT_NETWORK`` is already a dictionary, no work is done
    - malformed compressed bodies are ignored instead of raising
    - downstream readers continue to decide whether the normalized payload is
      valid for NET_MON handling
    """
    if not isinstance(full_payload, dict):
      return full_payload

    current_network = full_payload.get(PAYLOAD_DATA.NETMON_CURRENT_NETWORK)
    if isinstance(current_network, dict):
      return full_payload

    if full_payload.get(PAYLOAD_DATA.NETMON_VERSION) != PAYLOAD_DATA.NETMON_VERSION_V2:
      return full_payload

    encoded_data = full_payload.get(HB.ENCODED_DATA)
    if not encoded_data or log is None or not hasattr(log, 'decompress_text'):
      return full_payload

    decoded_text = log.decompress_text(encoded_data)
    if not decoded_text:
      return full_payload

    try:
      decoded_body = json.loads(decoded_text)
    except Exception:
      return full_payload

    if not isinstance(decoded_body, dict):
      return full_payload

    full_payload.update(decoded_body)
    return full_payload
  
  
class NET_CONFIG:
  STORE_COMMAND = "SET_CONFIG"
  REQUEST_COMMAND = "GET_CONFIG"
  NET_CONFIG_DATA = 'NET_CONFIG_DATA'
  OPERATION = 'OP'
  DESTINATION = 'DEST'
  DATA = 'DATA'
  
  PIPELINES = "PIPELINES"
  PLUGINS_STATUSES = "PLUGIN_STATUSES"
