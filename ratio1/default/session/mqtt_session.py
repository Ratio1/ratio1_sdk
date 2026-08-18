import json
import os

from ...base import GenericSession
from ...comm import MQTTWrapper
from ...comm.heartbeat_observation import (
  HEARTBEAT_MODE_SELECTED_NODES,
  HEARTBEAT_MODE_SUMMARY_DISCOVERY,
)
from ...const import ENVIRONMENT, PAYLOAD_DATA
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

    heartbeat_wrapper_kwargs = self._heartbeat_wrapper_kwargs()
    self._heartbeats_communicator = MQTTWrapper(
        log=self.log,
        config=self._config,
        send_channel_name=comm_ct.COMMUNICATION_CONFIG_CHANNEL,
        recv_channel_name=comm_ct.COMMUNICATION_CTRL_CHANNEL,
        comm_type=comm_ct.COMMUNICATION_HEARTBEATS,
        recv_buff=self._hb_messages,
        connection_name=self.name,
        verbosity=self._verbosity,
        **heartbeat_wrapper_kwargs,
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
    communicators = [
      self._default_communicator,
      self._heartbeats_communicator,
      self._notifications_communicator,
    ]
    return all(
      communicator.connected and communicator.receive_ready
      for communicator in communicators
    )

  def _heartbeat_wrapper_kwargs(self):
    """Return reduced-mode constructor arguments for the heartbeat wrapper.

    Returns
    -------
    dict
      Empty for compatibility-preserving full-network mode, or an explicit
      immutable receive-topic set for a reduced mode.
    """
    observation = getattr(self, "_heartbeat_observation_config", None)
    if observation is None:
      return {}
    if observation.mode == HEARTBEAT_MODE_SUMMARY_DISCOVERY:
      return {
        "recv_topics": [],
        "require_suback": False,
      }
    if observation.mode != HEARTBEAT_MODE_SELECTED_NODES:
      return {}

    channel_config = dict(
      self._config[comm_ct.COMMUNICATION_CTRL_CHANNEL]
    )
    targeted_topic = channel_config.get(comm_ct.TARGETED_TOPIC)
    if isinstance(targeted_topic, str) and targeted_topic.startswith("{}"):
      root_topic = os.environ.get(
        ENVIRONMENT.EE_ROOT_TOPIC_ENV_KEY,
        getattr(self, "comms_root_topic", "naeural"),
      )
      placeholder_count = targeted_topic.count("{}")
      channel_config[comm_ct.TARGETED_TOPIC] = targeted_topic.format(
        root_topic,
        *(["{}"] * (placeholder_count - 1)),
      )
    return {
      "recv_topics": list(observation.heartbeat_topics(channel_config)),
      "require_suback": True,
    }

  def _refresh_heartbeat_subscription_topics(self):
    """Refresh exact topics after GenericSession finalizes root templates.

    Returns
    -------
    None
    """
    observation = self._heartbeat_observation_config
    if observation.mode == HEARTBEAT_MODE_SELECTED_NODES:
      topics = observation.heartbeat_topics(
        self._config[comm_ct.COMMUNICATION_CTRL_CHANNEL]
      )
      self._heartbeats_communicator._explicit_recv_topics = tuple(topics)
      self._heartbeats_communicator._require_suback = True
    elif observation.mode == HEARTBEAT_MODE_SUMMARY_DISCOVERY:
      self._heartbeats_communicator._explicit_recv_topics = ()
      self._heartbeats_communicator._require_suback = False
    return

  def _connect(self) -> None:
    """Connect and establish the exact immutable receive subscriptions.

    Returns
    -------
    None
    """
    for communicator in [
      self._default_communicator,
      self._heartbeats_communicator,
      self._notifications_communicator,
    ]:
      if communicator.connection is None:
        communicator.server_connect()
      if communicator.connection is not None and not communicator.receive_ready:
        result = communicator.subscribe()
        if communicator is self._heartbeats_communicator:
          self._update_heartbeat_subscription_status(result)
    return

  def _update_heartbeat_subscription_status(self, subscribe_result):
    """Project broker subscription evidence into observation readiness.

    Parameters
    ----------
    subscribe_result : dict
      MQTT wrapper subscribe result.

    Returns
    -------
    None
    """
    observation = getattr(self, "_heartbeat_observation_config", None)
    monitor = getattr(self, "_heartbeat_observation_monitor", None)
    if (
      observation is None
      or monitor is None
      or observation.mode != HEARTBEAT_MODE_SELECTED_NODES
    ):
      return
    subscription = self._heartbeats_communicator.get_subscription_status()
    ready = bool(subscribe_result.get("has_connection")) and subscription["ready"]
    reason = None if ready else "targeted_subscription_failed"
    monitor.set_subscription_status(
      ready=ready,
      topics=subscription["acknowledged_topics"],
      reason=reason,
    )
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
