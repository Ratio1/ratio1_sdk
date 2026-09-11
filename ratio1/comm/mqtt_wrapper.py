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
from threading import Event, Lock
from time import sleep

import paho.mqtt.client as mqtt
from paho.mqtt import __version__ as mqtt_version

from ..const import BASE_CT, COLORS, COMMS, PAYLOAD_CT
from ..utils import resolve_domain_or_ip

from importlib import resources as impresources
from .. import certs
from ..comm.base_comm_wrapper import BaseCommWrapper


class MQTTWrapper(BaseCommWrapper):
  def __init__(self,
               log,
               config,
               recv_buff=None,
               send_channel_name=None,
               recv_channel_name=None,
               comm_type=None,
               on_message=None,
               post_default_on_message=None,  # callback that gets called after custom or default rcv callback
               debug_errors=False,
               connection_name='MqttWrapper',
               verbosity=1,
               **kwargs):
    self._mqttc = None
    self.debug_errors = debug_errors if verbosity <=1 else True
    self._thread_name = None
    self.connected = False
    self.disconnected = False
    self._nr_full_retries = 0
    self.__nr_dropped_messages = 0
    self.__nr_stale_messages = 0
    # Nest state locks only under _client_lock, never across Paho calls or waits.
    self._client_lock = Lock()
    self._subscription_lock = Lock()
    self._pending_subacks = {}
    self._early_subacks = {}
    self._subscription_status = {
      'ready': False,
      'acknowledged_topics': [],
      'rejected_topics': [],
      'timed_out_topics': [],
      'stale_callbacks': 0,
    }
    self.__lifecycle_lock = Lock()
    self.__pending_publishes = {}
    self.__early_publish_callbacks = set()
    self.__pending_subscriptions = {}
    self.__early_subscribe_callbacks = {}
    self.__active_subscriptions = {}
    self.__retired_client_ids = set()
    self.__lifecycle = {
      'publish_attempts': 0,
      'publish_handoff_accepted': 0,
      'publish_handoff_rejected': 0,
      'publish_completed': 0,
      'broker_acknowledged': 0,
      'publish_abandoned': 0,
      'stale_publish_callbacks': 0,
      'subscribe_attempts': 0,
      'subscribe_handoff_accepted': 0,
      'subscribe_handoff_rejected': 0,
      'subscribe_requested': 0,
      'subscribe_confirmed': 0,
      'subscribe_rejected': 0,
      'subscribe_downgraded': 0,
      'subscribe_abandoned': 0,
      'stale_subscribe_callbacks': 0,
      'stale_connect_callbacks': 0,
      'stale_disconnect_callbacks': 0,
      'intentional_disconnect_callbacks': 0,
    }
    self._disconnected_log = deque(maxlen=10)
    self._disconnected_counter = 0
    self._custom_on_message = on_message
    self._post_default_on_message = post_default_on_message
    self._connection_name = connection_name
    self.last_disconnect_log = ''

    self.DEBUG = False

    super(MQTTWrapper, self).__init__(
      log=log,
      config=config,
      recv_buff=recv_buff,
      send_channel_name=send_channel_name,
      recv_channel_name=recv_channel_name,
      comm_type=comm_type,
      verbosity=verbosity,
      **kwargs
    )

    if self.recv_channel_name is not None and on_message is None:
      assert self._recv_buff is not None

    self.P(f"Initializing MQTTWrapper using Paho MQTT v{mqtt_version}")
    return

  @property
  def comm_log_prefix(self):
    return 'MQTWRP'

  @property
  def nr_dropped_messages(self):
    return self.__nr_dropped_messages

  @property
  def nr_stale_messages(self):
    """Return messages ignored from retired MQTT client objects.

    Returns
    -------
    int
      Lifetime count of stale message callbacks.
    """
    return self.__nr_stale_messages

  @property
  def receive_ready(self):
    """Return whether this communicator's receive path is ready.

    Returns
    -------
    bool
      ``True`` for disabled receive paths or after all configured topics have
      been accepted according to the wrapper's SUBACK policy.
    """
    if self.recv_channel_name is None or len(self.get_recv_channel_topics()) == 0:
      return True
    with self._subscription_lock:
      return self._subscription_status['ready']

  def get_delivery_lifecycle_status(self):
    """Return transport lifecycle counters without claiming edge execution.

    Returns
    -------
    dict
      Publish and subscription handoff, completion, abandonment, and
      conservation state for the current wrapper lifetime.
    """
    with self.__lifecycle_lock:
      status = dict(self.__lifecycle)
      publish_in_call = (
        self.__lifecycle['publish_attempts']
        - self.__lifecycle['publish_handoff_accepted']
        - self.__lifecycle['publish_handoff_rejected']
      )
      subscribe_in_call = (
        self.__lifecycle['subscribe_attempts']
        - self.__lifecycle['subscribe_handoff_accepted']
        - self.__lifecycle['subscribe_handoff_rejected']
      )
      status.update({
        'publish_pending': len(self.__pending_publishes),
        'publish_in_call': publish_in_call,
        'subscribe_pending': len(self.__pending_subscriptions),
        'subscribe_in_call': subscribe_in_call,
        'active_subscriptions': len(self.__active_subscriptions),
        'publish_conserved': publish_in_call == 0 and self.__lifecycle['publish_attempts'] == (
          self.__lifecycle['publish_handoff_rejected']
          + self.__lifecycle['publish_handoff_accepted']
        ) and self.__lifecycle['publish_handoff_accepted'] == (
          self.__lifecycle['publish_completed']
          + self.__lifecycle['publish_abandoned']
          + len(self.__pending_publishes)
        ),
        'subscribe_conserved': subscribe_in_call == 0 and self.__lifecycle['subscribe_attempts'] == (
          self.__lifecycle['subscribe_handoff_rejected']
          + self.__lifecycle['subscribe_handoff_accepted']
        ) and self.__lifecycle['subscribe_handoff_accepted'] == (
          self.__lifecycle['subscribe_confirmed']
          + self.__lifecycle['subscribe_rejected']
          + self.__lifecycle['subscribe_abandoned']
          + len(self.__pending_subscriptions)
        ),
        'application_execution_known': False,
      })
      return status

  @staticmethod
  def __client_mid_key(client, mid):
    return id(client), mid

  def __complete_publish_locked(self, qos):
    self.__lifecycle['publish_completed'] += 1
    if qos > 0:
      self.__lifecycle['broker_acknowledged'] += 1

  @staticmethod
  def __normalize_granted_qos(granted_qos):
    if not isinstance(granted_qos, (list, tuple)):
      granted_qos = [granted_qos]
    result = []
    for value in granted_qos:
      normalized = getattr(value, 'value', value)
      try:
        normalized = int(normalized)
      except Exception:
        normalized = 128 if getattr(value, 'is_failure', True) else 0
      result.append(normalized)
    return result

  def __complete_subscription_locked(self, request, granted_qos):
    granted_qos = self.__normalize_granted_qos(granted_qos)
    if not granted_qos or any(value >= 128 for value in granted_qos):
      self.__lifecycle['subscribe_rejected'] += 1
      return
    granted = min(granted_qos)
    self.__lifecycle['subscribe_confirmed'] += 1
    if granted < request['qos']:
      self.__lifecycle['subscribe_downgraded'] += 1
    self.__active_subscriptions[request['topic']] = granted

  def __register_publish_handoff(self, client, mid, qos):
    """Account for an accepted handoff even if its client retired in the call."""
    key = self.__client_mid_key(client, mid)
    with self._client_lock, self.__lifecycle_lock:
      self.__lifecycle['publish_handoff_accepted'] += 1
      if client is not self._mqttc:
        self.__lifecycle['publish_abandoned'] += 1
      elif key in self.__early_publish_callbacks:
        self.__early_publish_callbacks.discard(key)
        self.__complete_publish_locked(qos)
      else:
        self.__pending_publishes[key] = qos

  def __register_subscription_request(self, client, mid, topic, qos):
    """Account for a subscription handoff without reviving retired state."""
    key = self.__client_mid_key(client, mid)
    request = {'topic': topic, 'qos': qos}
    with self._client_lock, self.__lifecycle_lock:
      self.__lifecycle['subscribe_handoff_accepted'] += 1
      self.__lifecycle['subscribe_requested'] += 1
      if client is not self._mqttc:
        self.__lifecycle['subscribe_abandoned'] += 1
        return
      early_granted = self.__early_subscribe_callbacks.pop(key, None)
      if early_granted is None:
        self.__pending_subscriptions[key] = request
      else:
        self.__complete_subscription_locked(request, early_granted)

  def __abandon_client_lifecycle(self, client):
    if client is None:
      return
    client_id = id(client)
    with self.__lifecycle_lock:
      publish_keys = [
        key for key in self.__pending_publishes if key[0] == client_id
      ]
      for key in publish_keys:
        self.__pending_publishes.pop(key, None)
      self.__lifecycle['publish_abandoned'] += len(publish_keys)

      subscribe_keys = [
        key for key in self.__pending_subscriptions if key[0] == client_id
      ]
      for key in subscribe_keys:
        self.__pending_subscriptions.pop(key, None)
      self.__lifecycle['subscribe_abandoned'] += len(subscribe_keys)
      self.__active_subscriptions.clear()

      self.__early_publish_callbacks = {
        key for key in self.__early_publish_callbacks if key[0] != client_id
      }
      self.__early_subscribe_callbacks = {
        key: value
        for key, value in self.__early_subscribe_callbacks.items()
        if key[0] != client_id
      }


  @property
  def cfg_qos(self):
    return self._config[COMMS.QOS]

  @property
  def cfg_cert_path(self):
    return self._config.get(COMMS.CERT_PATH)

  def get_recv_channel_def(self):
    """
    Return the MQTT receive channel definition with all subscribed topics.

    Returns
    -------
    dict or None
      Receive channel configuration containing the concrete list of MQTT topics,
      or `None` when no receive channel is configured.
    """
    if self.recv_channel_name is None:
      return

    cfg = self._config[self.recv_channel_name].copy()
    lst_topics = self.get_recv_channel_topics()

    if len(lst_topics) == 0:
      return None

    cfg[COMMS.TOPIC] = lst_topics
    return cfg

  @property
  def connection(self):
    with self._client_lock:
      return self._mqttc

  def __get_client_id(self):
    mqttc = self._mqttc
    client_id = str(mqttc._client_id) if mqttc is not None else 'None'
    return client_id

  def __maybe_set_mqtt_tls(self, mqttc: mqtt.Client):
    if self.is_secured:  # no need to set TLS if not configured with "SECURED" : 1
      self.P("Setting up secured comms on PORT: {}".format(self.cfg_port))
      cert_path = str(self.cfg_cert_path)

      if cert_path.upper() in ["", "NONE", "NULL"]:
        cert_file_name = self.cfg_host + ".crt"
        cert_file = impresources.files(certs).joinpath(cert_file_name)

        if cert_file.exists():
          self.P("Using certificate file: {}".format(cert_file))
          mqttc.tls_set(cert_file)
        else:
          self.P("No certificate provided, using default TLS")
          mqttc.tls_set()
      # end if certificate not provided
      else:
        if os.path.exists(cert_path):
          self.P("Using certificate file path: {}".format(cert_path))
          mqttc.tls_set(cert_path)
        else:
          self.P("Certificate file not found: {}".format(cert_path), color='r', verbosity=1)
          self.P("Using default TLS", verbosity=1)
          mqttc.tls_set()
      # end if certificate provided
    else:
      self.P("Communication is not secured. SECURED: {}, PORT: {}".format(
          self.cfg_secured, self.cfg_port), color='r'
      )
    # end if secured
    return

  def __create_mqttc_object(self, comtype, client_uid):
    if self.verbosity > 1:
      self.P(f"Creating MQTT client: {self._connection_name} - {comtype} - {client_uid}")
    client_id = self._connection_name + '_' + comtype + '_' + client_uid
    if mqtt_version.startswith('2'):
      mqttc = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
      )
    else:
      mqttc = mqtt.Client(
        client_id=client_id,
        clean_session=True
      )

    mqttc.username_pw_set(
      username=self.cfg_user,
      password=self.cfg_pass
    )

    self.__maybe_set_mqtt_tls(mqttc)

    mqttc.on_connect = self._callback_on_connect
    mqttc.on_disconnect = self._callback_on_disconnect
    mqttc.on_message = self._callback_on_message
    mqttc.on_publish = self._callback_on_publish
    mqttc.on_subscribe = self._callback_on_subscribe

    return mqttc

  def __sleep_until_connected(self, max_sleep, sleep_time):
    for sleep_iter in range(1, int(max_sleep / sleep_time) + 1):
      sleep(sleep_time)
      if self.connected:
        break
    # endfor
    return sleep_iter

  def _callback_on_connect(self, client, userdata, flags, rc, *args, **kwargs):
    """Record connection state only for the current transport generation."""
    with self._client_lock:
      is_stale = client is not self._mqttc
      if not is_stale:
        self.connected = rc == 0
    if is_stale:
      self._record_stale_transport_callback('connect', client)
      return
    if rc == 0:
      self.P("Conn ok clntid '{}' with code: {}".format(
        self.__get_client_id(), rc), color='g', verbosity=1)
    return

  def _callback_on_disconnect(self, client, userdata, rc, *args, **kwargs):
    """
    Tricky callback

    we can piggy-back ride the client with flags:
      client.connected_flag = False
      client.disconnect_flag = True
    """

    if client is not self._mqttc:
      self._record_stale_transport_callback('disconnect', client)
      return

    if mqtt_version.startswith('2'):
      # In version 2, on_disconnect has a different order of parameters, and rc is passed as the 4th parameter
      # check https://eclipse.dev/paho/files/paho.mqtt.python/html/migrations.html for more info
      rc = args[0]
    if rc == 0:
      self.P('Graceful disconnect (reason_code={})'.format(rc), color='m', verbosity=1)
      str_error = "Graceful disconnect."
    else:
      str_error = mqtt.error_string(rc) + ' (reason_code={})'.format(rc)
      self.P("Unexpected disconnect for client id '{}': {}".format(
        self.__get_client_id(), str_error), color='r', verbosity=1)

    if self._disconnected_counter > 0:
      self.P("Trying to determine IP of target server...", verbosity=1)
      ok, str_ip, str_domain = resolve_domain_or_ip(self.cfg_host)
      msg = '  Multiple conn loss ({} disconnects so far), showing previous 10:\n{}'.format(
        self._disconnected_counter, self.last_disconnect_log
      )
      server_port = "*****  Please check server connection: {}:{} {} *****".format(
        self.cfg_host, self.cfg_port,
        "({}:{})".format(str_ip, self.cfg_port) if (ok and str_ip != str_domain) else ""
      )
      msg += "\n\n{}\n{}\n{}".format("*" * len(server_port), server_port, "*" * len(server_port))
      self.P(msg, color='r', verbosity=1)
    # endif multiple disconnects
    self._disconnected_log.append((self.log.time_to_str(), str_error))
    self._disconnected_counter += 1
    self.last_disconnect_log = '\n'.join([f"* Comm error '{x2}' occurred at {x1}" for x1, x2 in self._disconnected_log])
    # we need to stop the loop otherwise the client thread will keep working
    # so we call release->loop_stop

    self.release(expected_client=client)
    return

  def _callback_on_publish(self, client, userdata, mid, *args, **kwargs):
    """Complete one publish only for the active MQTT client generation."""
    with self._client_lock:
      if client is not self._mqttc:
        self._record_stale_transport_callback('publish', client)
        return

      key = self.__client_mid_key(client, mid)
      with self.__lifecycle_lock:
        qos = self.__pending_publishes.pop(key, None)
        if qos is None:
          if len(self.__early_publish_callbacks) >= 1024:
            self.__early_publish_callbacks.pop()
          self.__early_publish_callbacks.add(key)
        else:
          self.__complete_publish_locked(qos)
    return

  def _record_stale_transport_callback(self, callback_name, client=None):
    """Account for a callback from a non-current MQTT client generation."""
    with self._subscription_lock:
      self._subscription_status['stale_callbacks'] += 1
    lifecycle_key = 'stale_{}_callbacks'.format(callback_name)
    with self.__lifecycle_lock:
      if callback_name == 'disconnect' and id(client) in self.__retired_client_ids:
        self.__retired_client_ids.discard(id(client))
        self.__lifecycle['intentional_disconnect_callbacks'] += 1
      elif lifecycle_key in self.__lifecycle:
        self.__lifecycle[lifecycle_key] += 1
    return

  def _callback_on_subscribe(
      self,
      client,
      userdata,
      mid,
      granted_qos,
      *args,
      **kwargs
    ):
    """Capture one broker SUBACK for the matching active subscribe request.

    Parameters
    ----------
    client : paho.mqtt.client.Client
      Client that emitted the callback.
    userdata : object
      Paho user data, unused.
    mid : int
      MQTT message identifier returned by ``subscribe``.
    granted_qos : sequence
      Granted QoS values or reason codes.
    *args : tuple
      Paho-version-specific trailing callback values.
    **kwargs : dict
      Paho-version-specific named callback values.

    Returns
    -------
    None
    """
    grants = list(granted_qos or [])
    key = self.__client_mid_key(client, mid)
    normalized_grants = self.__normalize_granted_qos(grants)
    with self._client_lock:
      if client is not self._mqttc:
        self._record_stale_transport_callback('subscribe', client)
        return
      with self.__lifecycle_lock:
        request = self.__pending_subscriptions.pop(key, None)
        if request is None:
          if len(self.__early_subscribe_callbacks) >= 1024:
            self.__early_subscribe_callbacks.pop(
              next(iter(self.__early_subscribe_callbacks))
            )
          self.__early_subscribe_callbacks[key] = normalized_grants
        else:
          self.__complete_subscription_locked(request, normalized_grants)
      with self._subscription_lock:
        pending = self._pending_subacks.get(key)
        if pending is None:
          # A SUBACK may precede waiter registration; keep its client identity.
          self._early_subacks[key] = grants
        else:
          pending['grants'] = grants
          pending['event'].set()
    return

  def _callback_on_message(self, client, userdata, message, *args, **kwargs):
    """Admit one active-client message without blocking the Paho loop."""
    if client is not self._mqttc:
      self.__nr_stale_messages += 1
      return
    if self._custom_on_message is not None:
      self._custom_on_message(client, userdata, message)
    else:
      try:
        msg = message.payload.decode('utf-8')
        try_append = getattr(self._recv_buff, 'try_append', None)
        if callable(try_append):
          admitted = try_append(msg)
        else:
          self._recv_buff.append(msg)
          admitted = True
        if not admitted:
          self.__nr_dropped_messages += 1
      except:
        # DEBUG TODO: enable here a debug show of the message.payload if
        # the number of dropped messages rises
        # TODO: add also to ANY OTHER wrapper
        self.__nr_dropped_messages += 1
    # now call the "post-process" callback
    if self._post_default_on_message is not None:
      self._post_default_on_message()
    return

  def get_connection_issues(self):
    return {x1: x2 for x1, x2 in self._disconnected_log}

  def server_connect(self, max_retries=5):
    max_sleep = 2
    sleep_time = 0.01
    nr_retry = 1
    has_connection = False
    exception = None
    sleep_iter = None
    comtype = self._comm_type[:7] if self._comm_type is not None else 'CUSTOM'

    while nr_retry <= max_retries:
      try:
        # 1. create a unique client id
        client_uid = self.log.get_unique_id()

        # 2. create the mqtt client object (with callbacks set)
        mqttc = self.__create_mqttc_object(comtype, client_uid)
        with self._client_lock:
          self._mqttc = mqttc
          self.connected = False
          self._reset_subscription_attempt()

        # TODO: more verbose logging including when there is no actual exception
        # 3. connect to the server
        mqttc.connect(host=self.cfg_host, port=self.cfg_port)

        # 4. start the loop in another thread
        if self.connection is mqttc:
          mqttc.loop_start()  # start loop in another thread

        # 5. wait until connected
        sleep_iter = self.__sleep_until_connected(max_sleep=max_sleep, sleep_time=sleep_time)

        has_connection = self.connection is mqttc and self.connected
      except Exception as e:
        exception = e
        if self.debug_errors:
          self.P(exception, color='r', verbosity=1)
          self.P(traceback.format_exc(), color='r', verbosity=1)

      # end try-except

      if has_connection:
        break

      nr_retry += 1
    # endwhile

    # set thread name ; useful for debugging
    mqttc = self._mqttc
    if mqttc is not None and hasattr(mqttc, '_thread') and mqttc._thread is not None:
      mqttc._thread.name = self._connection_name + '_' + comtype + '_' + client_uid
      self._thread_name = mqttc._thread.name

    if has_connection:
      msg = "MQTT conn ok by '{}' in {:.1f}s - {}:{} with subtopic {}".format(
        self._thread_name,
        sleep_iter * sleep_time,
        self.cfg_host,
        self.cfg_port,
        self.cfg_subtopic
      )
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_NORMAL
      self._nr_full_retries = 0

      self.P(msg)

    else:
      reason = exception
      if reason is None:
        reason = " max retries in {:.1f}s".format(sleep_iter * sleep_time)

      self._nr_full_retries += 1
      msg = 'MQTT (Paho) conn to {}:{} failed after {} retr ({} trials) (reason:{})'.format(
        self.cfg_host,
        self.cfg_port,
        nr_retry,
        self._nr_full_retries,
        reason
      )
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION
      self.P(msg, color='r', verbosity=1)

    # endif

    dct_ret = {
      'has_connection': has_connection,
      'msg': msg,
      'msg_type': msg_type
    }

    # if release was not called from on_disconnect, basically
    # this method of checking self._mqttc is not None is not
    # very reliable, as race conditions can occur
    if not has_connection and self.connection is mqttc:
      self.release(expected_client=mqttc)

    return dct_ret

  def get_thread_name(self):
    return self._thread_name

  def _reset_subscription_attempt(self):
    """Clear per-attempt topic outcomes while retaining stale-callback history."""
    with self._subscription_lock:
      stale_callbacks = self._subscription_status['stale_callbacks']
      for pending in self._pending_subacks.values():
        pending['grants'] = [128]
        pending['event'].set()
      self._pending_subacks.clear()
      self._early_subacks.clear()
      self._subscription_status = {
        'ready': False,
        'acknowledged_topics': [],
        'rejected_topics': [],
        'timed_out_topics': [],
        'stale_callbacks': stale_callbacks,
      }
    return

  def _record_topic_status(self, key, topic, client):
    """Append a topic outcome only while its MQTT client is still active."""
    with self._client_lock, self._subscription_lock:
      if client is not self._mqttc:
        return
      if topic not in self._subscription_status[key]:
        self._subscription_status[key].append(topic)
    return

  def _wait_for_suback(self, mid, topic, ack_timeout, client):
    """Wait, without state locks held, for this client's topic acknowledgment."""
    pending = {
      'event': Event(),
      'topic': topic,
      'grants': None,
    }
    key = self.__client_mid_key(client, mid)
    with self._client_lock, self._subscription_lock:
      if client is not self._mqttc:
        return False, 'disconnected'
      self._pending_subacks[key] = pending
      early_grants = self._early_subacks.pop(key, None)
      if early_grants is not None:
        pending['grants'] = early_grants
        pending['event'].set()
    acknowledged = pending['event'].wait(timeout=ack_timeout)
    with self._subscription_lock:
      self._pending_subacks.pop(key, None)
      grants = pending['grants']
    if not acknowledged:
      return False, 'timeout'
    if not grants or any(self._suback_is_failure(grant) for grant in grants):
      return False, 'rejected'
    return True, None

  @staticmethod
  def _suback_is_failure(grant):
    """Return whether one Paho v1/v2 SUBACK value denotes rejection."""
    if getattr(grant, 'is_failure', False):
      return True
    value = getattr(grant, 'value', grant)
    try:
      return int(value) >= 128
    except (TypeError, ValueError):
      return True

  def get_subscription_status(self):
    """Return a copy of current receive-subscription outcomes.

    Returns
    -------
    dict
      Readiness, acknowledged, rejected, timed-out, and stale-callback state.
    """
    with self._subscription_lock:
      return {
        key: list(value) if isinstance(value, list) else value
        for key, value in self._subscription_status.items()
      }

  def subscribe(self, max_retries=5, ack_timeout=2.0, should_continue=None):
    """Subscribe to each configured topic and optionally require its SUBACK.

    Parameters
    ----------
    max_retries : int, optional
      Maximum local subscribe attempts per exact topic.
    ack_timeout : float, optional
      Maximum seconds to wait for each required broker SUBACK.
    should_continue : callable, optional
      Session-liveness predicate checked before each broker handoff retry.

    Returns
    -------
    dict
      Existing communicator result shape with ``has_connection`` readiness.
    """

    with self._client_lock:
      subscribe_client = self._mqttc
      self._reset_subscription_attempt()

    channel_def = self.get_recv_channel_def()
    if channel_def is None:
      with self._subscription_lock:
        self._subscription_status['ready'] = True
      return {
        'has_connection': True,
        'msg': 'MQTT receive disabled for this communicator.',
        'msg_type': PAYLOAD_CT.STATUS_TYPE.STATUS_NORMAL,
      }

    has_connection = True
    failure_msg = None
    lst_topics = channel_def[COMMS.TOPIC]
    qos = self.get_channel_qos(channel_def=channel_def)
    for topic in lst_topics:
      nr_retry = 1
      current_topic_connection = False
      exception = None
      while nr_retry <= max_retries:
        if self.connection is not subscribe_client:
          exception = 'MQTT client changed during subscription'
          break
        if should_continue is not None and not should_continue():
          exception = 'MQTT subscription cancelled by session shutdown'
          break
        with self.__lifecycle_lock:
          self.__lifecycle['subscribe_attempts'] += 1
        handoff_recorded = False
        try:
          if subscribe_client is not None:
            subscribe_result = subscribe_client.subscribe(
              topic=topic,
              qos=qos
            )
            result_code = subscribe_result[0] if isinstance(subscribe_result, tuple) else None
            if result_code in (None, mqtt.MQTT_ERR_SUCCESS):
              mid = (
                subscribe_result[1]
                if isinstance(subscribe_result, tuple) and len(subscribe_result) > 1
                else None
              )
              if mid is None:
                with self.__lifecycle_lock:
                  self.__lifecycle['subscribe_handoff_rejected'] += 1
                exception = 'MQTT subscribe did not return a message id'
              else:
                self.__register_subscription_request(
                  client=subscribe_client,
                  mid=mid,
                  topic=topic,
                  qos=qos,
                )
                handoff_recorded = True
                if self.require_suback:
                  current_topic_connection, suback_error = self._wait_for_suback(
                    mid=mid,
                    topic=topic,
                    ack_timeout=ack_timeout,
                    client=subscribe_client,
                  )
                  if suback_error == 'timeout':
                    self._record_topic_status('timed_out_topics', topic, subscribe_client)
                    exception = 'MQTT SUBACK timed out'
                  elif suback_error == 'rejected':
                    self._record_topic_status('rejected_topics', topic, subscribe_client)
                    exception = 'MQTT SUBACK rejected the topic'
                else:
                  current_topic_connection = True
            else:
              with self.__lifecycle_lock:
                self.__lifecycle['subscribe_handoff_rejected'] += 1
              exception = "MQTT client returned subscribe rc={}".format(result_code)
          else:
            with self.__lifecycle_lock:
              self.__lifecycle['subscribe_handoff_rejected'] += 1
            exception = "MQTT client is not initialized"
        except Exception as e:
          if not handoff_recorded:
            with self.__lifecycle_lock:
              self.__lifecycle['subscribe_handoff_rejected'] += 1
          exception = e

        if self.connection is not subscribe_client:
          current_topic_connection = False
          exception = 'MQTT client changed during subscription'
          break
        if current_topic_connection:
          break

        if nr_retry < max_retries:
          sleep(1)
        nr_retry += 1
      # endwhile

      if current_topic_connection:
        self._record_topic_status('acknowledged_topics', topic, subscribe_client)
        if self.require_suback:
          msg = "MQTT (Paho) subscribed to topic '{}' (QoS={})".format(topic, qos)
        else:
          msg = "MQTT (Paho) subscription request accepted for topic '{}' (QoS={})".format(
            topic,
            qos,
          )
        msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_NORMAL
      else:
        msg = "MQTT (Paho) subscribe to '{}' FAILED after {} retries (reason:{})".format(topic, max_retries, exception)
        msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION
        has_connection = False
        failure_msg = msg
        break
      # endif

    if not has_connection:
      msg = failure_msg
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION

    with self._client_lock:
      if subscribe_client is None or subscribe_client is not self._mqttc:
        has_connection = False
        msg = 'MQTT client changed during subscription'
        msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION
      else:
        with self._subscription_lock:
          self._subscription_status['ready'] = has_connection

    dct_ret = {
      'has_connection': has_connection,
      'msg': msg,
      'msg_type': msg_type
    }

    return dct_ret

  def receive(self):
    return

  def send(self, message, send_to=None):
    """Hand one message to Paho or raise before claiming transport admission.

    Parameters
    ----------
    message : str or bytes
      Serialized MQTT payload.
    send_to : str, optional
      Address used to resolve an addressed channel topic.

    Returns
    -------
    dict
      Paho handoff metadata. This does not claim application execution.

    Raises
    ------
    RuntimeError
      If no client exists or Paho rejects the publish before handoff.
    """
    mqttc = self._mqttc
    if mqttc is None:
      with self.__lifecycle_lock:
        self.__lifecycle['publish_attempts'] += 1
        self.__lifecycle['publish_handoff_rejected'] += 1
      raise RuntimeError('MQTT client is not initialized')

    channel_def = self.get_send_channel_def(send_to=send_to)
    qos = self.get_channel_qos(channel_def=channel_def)
    topic = channel_def[self.channel_key]
    with self.__lifecycle_lock:
      self.__lifecycle['publish_attempts'] += 1

    try:
      result = mqttc.publish(
        topic=topic,
        payload=message,
        qos=qos
      )
    except Exception as exc:
      with self.__lifecycle_lock:
        self.__lifecycle['publish_handoff_rejected'] += 1
      raise RuntimeError('MQTT publish raised before handoff: {}'.format(exc)) from exc

    ####
    self.D("Sent message (QoS {})'{}'".format(qos, message))
    ####

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
      with self.__lifecycle_lock:
        self.__lifecycle['publish_handoff_rejected'] += 1
      raise RuntimeError(
        'MQTT publish was rejected before handoff (rc={}): {}'.format(
          result.rc,
          mqtt.error_string(result.rc),
        )
      )

    mid = getattr(result, 'mid', None)
    if mid is None:
      with self.__lifecycle_lock:
        self.__lifecycle['publish_handoff_rejected'] += 1
      raise RuntimeError('MQTT publish returned success without a message id')

    self.__register_publish_handoff(mqttc, mid, qos)
    return {
      'paho_accepted': True,
      'mid': mid,
      'qos': qos,
      'topic': topic,
    }

  def release(self, expected_client=None):
    release_errors = []

    with self._client_lock:
      mqttc = self._mqttc
      if expected_client is not None and mqttc is not expected_client:
        mqttc = None
      else:
        self._mqttc = None
        self.connected = False
        if expected_client is not None:
          self.disconnected = True
        try:
          with self._subscription_lock:
            self._subscription_status['ready'] = False
            for pending in self._pending_subacks.values():
              pending['grants'] = [128]
              pending['event'].set()
            self._early_subacks.clear()
        except Exception as exc:
          release_errors.append(exc)

        if mqttc is not None:
          # Clear this generation's lifecycle before a replacement can appear.
          # Paho disconnect/loop_stop remain outside every state lock.
          try:
            with self.__lifecycle_lock:
              if len(self.__retired_client_ids) >= 1024:
                self.__retired_client_ids.pop()
              self.__retired_client_ids.add(id(mqttc))
            self.__abandon_client_lifecycle(mqttc)
          except Exception as exc:
            release_errors.append(exc)

    if expected_client is not None and mqttc is None:
      self._record_stale_transport_callback('disconnect', expected_client)
      return {'msgs': ['MQTT client generation was already replaced.']}

    if mqttc is not None:
      try:
        mqttc.disconnect()
      except Exception as exc:
        release_errors.append(exc)
      try:
        mqttc.loop_stop()  # stop the loop thread
      except Exception as exc:
        release_errors.append(exc)

    if release_errors:
      msg = 'MQTT (Paho) exception while releasing connection: `{}`'.format(
        '; '.join(str(exc) for exc in release_errors),
      )
    else:
      msg = 'MQTT (Paho) connection released.'

    self.P(msg)

    # TODO: method should return None; update code in core to reflect this
    dct_ret = {'msgs': [msg]}

    return dct_ret
