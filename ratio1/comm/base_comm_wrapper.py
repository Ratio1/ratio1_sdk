# PAHO
# TODO: implement config validation and base config format
# TODO: add queue for to_send messages

# TODO: adding a lock for accessing self._mqttc should solve some of the bugs, but it introduces a new one
# basically, when a user thread calls send, they should acquire the lock for the self._mqttc object
# and use it to send messages. However, if the mqttc has loop started but did not connect, the lock will
# prevent the client from ever connecting.

import os
import traceback
from collections import deque
from threading import Lock
from time import sleep

from ..const import BASE_CT, COLORS, COMMS, PAYLOAD_CT
from ..utils import resolve_domain_or_ip

from importlib import resources as impresources
from .. import certs


class BaseCommWrapper(object):
  def __init__(
      self,
      log,
      config,
      recv_buff=None,
      send_channel_name=None,
      recv_channel_name=None,
      comm_type=None,
      verbosity=1,
      **kwargs
  ):
    self.log = log
    self._config = config
    self._recv_buff = recv_buff
    self._send_to = None
    self.send_channel_name = send_channel_name
    self.recv_channel_name = recv_channel_name
    self._comm_type = comm_type
    self.__verbosity = verbosity
    super(BaseCommWrapper, self).__init__(**kwargs)
    return

  @property
  def comm_log_prefix(self):
    return 'COMMWRP'

  @property
  def verbosity(self):
    return self.__verbosity

  def P(self, s, color=None, verbosity=1, **kwargs):
    if verbosity > self.verbosity:
      return
    if color is None or (isinstance(color, str) and color[0] not in ['e', 'r']):
      color = COLORS.COMM
    comtype = self._comm_type[:7] if self._comm_type is not None else 'CUSTOM'
    self.log.P(f"[{self.comm_log_prefix}][{comtype}] {s}", color=color, **kwargs)
    return

  def D(self, s, t=False):
    _r = -1
    if self.DEBUG:
      if self.show_prefixes:
        msg = "[DEBUG] {}: {}".format(self.__name__, s)
      else:
        if self.prefix_log is None:
          msg = "[D] {}".format(s)
        else:
          msg = "[D]{} {}".format(self.prefix_log, s)
        # endif
      # endif
      _r = self.log.P(msg, show_time=t, color='yellow')
    # endif
    return _r

  @property
  def is_secured(self):
    val = self.cfg_secured
    if isinstance(val, str):
      val = val.upper() in ["1", "TRUE", "YES"]
    return val

  @property
  def send_channel_name(self):
    return self._send_channel_name

  @property
  def recv_channel_name(self):
    return self._recv_channel_name

  @send_channel_name.setter
  def send_channel_name(self, x):
    if isinstance(x, tuple):
      self._send_channel_name, self._send_to = x
    else:
      self._send_channel_name = x
    return

  @recv_channel_name.setter
  def recv_channel_name(self, x):
    self._recv_channel_name = x
    return

  @property
  def cfg_node_id(self):
    return self._config.get(COMMS.EE_ID, self._config.get(COMMS.SB_ID, None))

  @property
  def cfg_node_addr(self):
    return self._config.get(COMMS.EE_ADDR)

  @property
  def cfg_user(self):
    return self._config[COMMS.USER]

  @property
  def cfg_pass(self):
    return self._config[COMMS.PASS]

  @property
  def cfg_host(self):
    return self._config[COMMS.HOST]

  @property
  def cfg_port(self):
    return self._config[COMMS.PORT]

  @property
  def cfg_qos(self):
    return self._config[COMMS.QOS]

  @property
  def cfg_cert_path(self):
    return self._config.get(COMMS.CERT_PATH)

  @property
  def cfg_secured(self):
    return self._config.get(COMMS.SECURED, 0)  # TODO: make 1 later on

  @property
  def cfg_subtopic(self):
    return self._config.get(COMMS.SUBTOPIC, COMMS.DEFAULT_SUBTOPIC_VALUE)

  def get_subtopic_values(self):
    if self.cfg_subtopic == 'alias':
      # This is done in order for alias to still work with addresses
      return [self.cfg_node_id, self.cfg_node_addr]
    return [self.cfg_node_addr]

  @property
  def channel_key(self):
    """
    Returns the key for the channel in the configuration
    Returns
    -------
    str : The key for the channel in the configuration
    """
    return COMMS.TOPIC

  def extract_channel_from_config(self, cfg):
    """
    Utility function to extract the channel from the configuration
    Parameters
    ----------
    cfg : dict
      The configuration dictionary

    Returns
    -------
    str : The channel
    """
    return cfg[COMMS.TOPIC]

  def get_send_channel_def(self, send_to=None):
    """
    Returns the channel definition for the sender
    Parameters
    ----------
    send_to : str, optional

    Returns
    -------
    dict or None : The channel definition or None if the channel is not defined.
    """
    if self.send_channel_name is None:
      return

    cfg = self._config[self.send_channel_name].copy()
    extracted_channel = self.extract_channel_from_config(cfg)
    if "{}" in extracted_channel:
      if send_to is not None:
        extracted_channel = extracted_channel.format(send_to)
      # TODO: ._send_to seems to be necessary only for the amqp wrapper
      elif self._send_to is not None:
        extracted_channel = extracted_channel.format(self._send_to)
    # endif check for {}

    assert "{}" not in extracted_channel

    cfg[self.channel_key] = extracted_channel
    return cfg

  def server_connect(self, max_retries=5):
    raise NotImplementedError

  def send(self, message):
    raise NotImplementedError

  def receive(self):
    raise NotImplementedError

  def release(self):
    raise NotImplementedError
