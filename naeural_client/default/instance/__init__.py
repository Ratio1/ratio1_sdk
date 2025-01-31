from .net_mon_01_plugin import NetMon01
from .view_scene_01_plugin import ViewScene01
from .custom_webapi_01_plugin import CustomWebapi01
from .chain_dist_custom_job_01_plugin import ChainDistCustomJob01
from .telegram_basic_bot_01_plugin import BasicTelegramBot01


class PLUGIN_TYPES:
  """
  The plugin types that are available in the default instance
  """
  NET_MON_01 = NetMon01
  VIEW_SCENE_01 = ViewScene01
  CUSTOM_WEBAPI_01 = CustomWebapi01
  CHAIN_DIST_CUSTOM_JOB_01 = ChainDistCustomJob01
  TELEGRAM_BASIC_BOT_01 = BasicTelegramBot01
  
  
REVERSE_MAP = {
  x.signature: x for x in PLUGIN_TYPES.__dict__.values() if hasattr(x, "signature")
}