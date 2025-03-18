from ...default.instance import CustomWebapi01
from ...const import PLUGIN_SIGNATURES


class GenericHttp01(CustomWebapi01):
  signature = PLUGIN_SIGNATURES.GENERIC_HTTP_SERVER
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.P("GenericHttp01 plugin initialized.")
    return

