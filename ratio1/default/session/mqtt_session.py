import json

from ...base import GenericSession
from ...comm import MQTTWrapper
from ...const import PAYLOAD_DATA
from ...const import comms as comm_ct


class MqttSession(GenericSession):
  def startup(self):
    """
    Create the MQTT communicators used by the session.

    Notes
    -----
    The default communicator handles payload traffic, while the heartbeat and
    notification communicators keep their dedicated channels. Topic resolution,
    including addressed payload routing, is delegated to the wrapper layer.

    Returns
    -------
    None
    """
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
    Resolve one receiver value into the topic token expected by the communicator.

    Parameters
    ----------
    to : str
      Receiver address or alias.

    Returns
    -------
    str
      Address-based or alias-based topic token, depending on the configured
      subtopic mode.

    Notes
    -----
    The receiver is first resolved to a node address. In `alias` subtopic mode,
    the address is then converted back to the node alias so publishes land on
    the alias-formatted topic.
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

  def __normalize_destinations(self, to):
    """
    Normalize one-or-many payload destinations for MQTT topic routing.

    Parameters
    ----------
    to : str or collection or None
      Requested destination or destinations.

    Returns
    -------
    list
      Ordered unique destination tokens ready to be used as topic-format values.
      A single `None` entry represents the broadcast path. An empty list means
      an explicit addressed send could not be resolved and should fail closed.
    """
    if to is None:
      return [None]
    if isinstance(to, str):
      destinations = [to]
    elif isinstance(to, (list, tuple, set)):
      destinations = list(to)
    else:
      destinations = [to]
    processed_destinations = [self.__process_receiver_for_subtopic(dest) for dest in destinations]
    processed_destinations = [dest for dest in processed_destinations if dest is not None]
    if len(processed_destinations) == 0:
      return []
    # Preserve first-seen destination order while removing duplicates.
    return list(dict.fromkeys(processed_destinations))

  def _send_raw_message(self, to, msg, communicator='default', debug=False, **kwargs):
    """Serialize one message and publish it to one or many destinations.

    Parameters
    ----------
    to : str or collection or None
      Requested destination or destinations.
    msg : dict
      Message payload to serialize.
    communicator : str, optional
      Communicator key used to select the underlying wrapper.
    debug : bool, optional
      When `True`, log the normalized destination list before publish.
    **kwargs : dict
      Reserved for compatibility with the session send interface.

    Returns
    -------
    bool
      ``True`` when the message was published to every resolved destination.
      ``False`` when an explicit addressed send resolved no valid destinations
      and the method failed closed instead of broadcasting.
    """
    payload = json.dumps(msg)
    communicator_obj = self.__communicators.get(communicator, self._default_communicator)
    processed_destinations = self.__normalize_destinations(to)
    if debug:
      self.log.P(f"Processed destination: {to} -> {processed_destinations}")
    if to is not None and len(processed_destinations) == 0:
      self.log.P(f"No valid payload destinations resolved from {to}. Skipping publish.", color='r')
      return False
    for processed_to in processed_destinations:
      communicator_obj.send(payload, send_to=processed_to)
    return True


  def _send_payload(self, payload):
    """
    Send one payload message through the default communicator.

    Parameters
    ----------
    payload : dict
      Outgoing payload dictionary. When ``EE_DESTINATION`` is present and the
      payload channel supports addressed routing through ``TARGETED_TOPIC`` or a
      templated ``TOPIC``, the payload is routed to the corresponding addressed
      topic or topics. Otherwise the payload is sent once on the broadcast
      topic.
    """
    destination = payload.get(PAYLOAD_DATA.EE_DESTINATION)
    if destination is not None:
      payload_cfg = self._default_communicator._config[self._default_communicator.send_channel_name]
      has_targeted_topic = bool(payload_cfg.get(comm_ct.TARGETED_TOPIC))
      has_templated_topic = '{}' in str(payload_cfg.get(comm_ct.TOPIC, ''))
      if not (has_targeted_topic or has_templated_topic):
        # Maybe show this log only for debug settings in the future, but for now it will remain
        self.log.P(
          f"Payload channel '{self._default_communicator.send_channel_name}' has no addressed topic template. Falling back to one broadcast publish for destination {destination}.",
          color='r'
        )
        destination = None
    self._send_raw_message(to=destination, msg=payload, communicator='default')
    return


  def _send_command(self, to, command, debug=False, **kwargs):
    self._send_raw_message(
      to=to, msg=command,
      communicator='heartbeats',
      debug=debug, **kwargs
    )
    return