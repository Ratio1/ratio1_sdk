import json

from ...base import GenericSession
from ...comm import MQTTWrapper
from ...const import comms as comm_ct


class MqttSession(GenericSession):
  def startup(self):
    self._default_communicator = MQTTWrapper(
        log=self.log,
        config=self._config,
        send_channel_name=comm_ct.COMMUNICATION_PAYLOADS_CHANNEL,
        recv_channel_name=comm_ct.COMMUNICATION_PAYLOADS_CHANNEL,
        comm_type=comm_ct.COMMUNICATION_DEFAULT,
        recv_buff=self._payload_messages,
        connection_name=self.name,
        verbosity=self._verbosity,
    )

    self._heartbeats_communicator = MQTTWrapper(
        log=self.log,
        config=self._config,
        send_channel_name=comm_ct.COMMUNICATION_CONFIG_CHANNEL,
        recv_channel_name=comm_ct.COMMUNICATION_CTRL_CHANNEL,
        comm_type=comm_ct.COMMUNICATION_HEARTBEATS,
        recv_buff=self._hb_messages,
        connection_name=self.name,
        verbosity=self._verbosity,
    )

    self._notifications_communicator = MQTTWrapper(
        log=self.log,
        config=self._config,
        recv_channel_name=comm_ct.COMMUNICATION_NOTIF_CHANNEL,
        comm_type=comm_ct.COMMUNICATION_NOTIFICATIONS,
        recv_buff=self._notif_messages,
        connection_name=self.name,
        verbosity=self._verbosity,
    )
    self.__communicators = {
      'default': self._default_communicator,
      'heartbeats': self._heartbeats_communicator,
      'notifications': self._notifications_communicator,
    }
    return super(MqttSession, self).startup()

  @property
  def _connected(self):
    """
    Check if the session is connected to the communication server.
    """
    return self._default_communicator.connected and self._heartbeats_communicator.connected and self._notifications_communicator.connected

  def _connect(self) -> None:
    if self._default_communicator.connection is None:
      self._default_communicator.server_connect()
      self._default_communicator.subscribe()
    if self._heartbeats_communicator.connection is None:
      self._heartbeats_communicator.server_connect()
      self._heartbeats_communicator.subscribe()
    if self._notifications_communicator.connection is None:
      self._notifications_communicator.server_connect()
      self._notifications_communicator.subscribe()
    return

  def _communication_close(self, **kwargs):
    self._default_communicator.release()
    self._heartbeats_communicator.release()
    self._notifications_communicator.release()
    return

  def __process_receiver_for_subtopic(self, to):
    """
    Process the receiver address to ensure it has the correct value for subtopic.
    Parameters
    ----------
    to : str
        The receiver address or id to process.

    Returns
    -------
    str
        The processed receiver address with the correct subtopic.
    """
    if to is None:
      return None
    if not isinstance(to, str):
      # TODO: review if this is the right way to handle this in case of multiple receivers.
      return to
    to_addr = self.get_addr_by_name(name=to)
    subtopic = self._config.get(comm_ct.SUBTOPIC, comm_ct.DEFAULT_SUBTOPIC_VALUE)
    if subtopic == 'alias':
      to_alias = self.get_node_alias(to_addr)
      return to_alias
    return to_addr

  def _send_raw_message(self, to, msg, communicator='default'):
    payload = json.dumps(msg)
    communicator_obj = self.__communicators.get(communicator, self._default_communicator)
    # communicator_obj._send_to = to
    processed_to = self.__process_receiver_for_subtopic(to)
    # This does not support multiple receivers for now.
    communicator_obj.send(payload, send_to=processed_to)
    return

  def _send_payload(self, payload):
    # `to` parameter will be added after migrating to segregated payloads.
    self._send_raw_message(to=None, msg=payload, communicator='default')
    return

  def _send_command(self, to, command):
    self._send_raw_message(to=to, msg=command, communicator='heartbeats')
    return