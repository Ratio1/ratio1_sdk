# PIKA

import uuid
from time import sleep

import pika


from ..const import COLORS, COMMS, BASE_CT, PAYLOAD_CT
from ..comm.base_comm_wrapper import BaseCommWrapper


class AMQPWrapper(BaseCommWrapper):
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
    self._disconnected_log = []

    self._recv_objects = {'queue': None, 'exchange': None}
    self._send_objects = {'queue': None, 'exchange': None}

    self._connection = None
    self._channel = None

    super(AMQPWrapper, self).__init__(
      log=log,
      config=config,
      recv_buff=recv_buff,
      send_channel_name=send_channel_name,
      recv_channel_name=recv_channel_name,
      comm_type=comm_type,
      verbosity=verbosity,
      **kwargs
    )

    if self.recv_channel_name is not None:
      assert self._recv_buff is not None
    return

  @property
  def comm_log_prefix(self):
    return 'AMQWRP'

  @property
  def cfg_broker(self):
    return self._config[COMMS.BROKER]

  @property
  def cfg_vhost(self):
    return self._config[COMMS.VHOST]

  @property
  def cfg_routing_key(self):
    return self._config.get(COMMS.ROUTING_KEY, "")


  def channel_key(self):
    return COMMS.QUEUE

  def extract_channel_from_config(self, cfg):
    return cfg.get(COMMS.QUEUE, cfg[COMMS.EXCHANGE])

  def get_recv_channel_def(self):
    if self.recv_channel_name is None:
      return

    cfg = self._config[self.recv_channel_name].copy()
    queue = cfg.get(COMMS.QUEUE, cfg[COMMS.EXCHANGE])
    cfg[COMMS.QUEUE] = queue
    _queue_device_specific = cfg.pop(COMMS.QUEUE_DEVICE_SPECIFIC, True)
    if _queue_device_specific:
      cfg[COMMS.QUEUE] += '/{}'.format(self.cfg_node_id)
    cfg[COMMS.QUEUE] += '/{}'.format(str(uuid.uuid4())[:8])
    return cfg

  @property
  def connection(self):
    return self._connection

  @property
  def channel(self):
    return self._channel

  @property
  def recv_queue(self):
    return self._recv_objects['queue']

  @property
  def recv_exchange(self):
    return self._recv_objects['exchange']

  @property
  def send_queue(self):
    return self._send_objects['queue']

  @property
  def send_exchange(self):
    return self._send_objects['exchange']

  def server_connect(self, max_retries=5):
    url = 'amqp://{}:{}@{}:{}/{}'.format(self.cfg_user, self.cfg_pass, self.cfg_broker, self.cfg_port, self.cfg_vhost)

    nr_retry = 1
    has_connection = False
    exception = None

    while nr_retry <= max_retries:
      try:
        self._connection = pika.BlockingConnection(parameters=pika.URLParameters(url))
        sleep(1)
        self._channel = self._connection.channel()
        has_connection = True
      except Exception as e:
        exception = e
      # end try-except

      if has_connection:
        break

      nr_retry += 1
    # endwhile

    if has_connection:
      msg = 'AMQP (Pika) SERVER conn ok: {}{}'.format(self.cfg_broker, self.cfg_port)
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_NORMAL
    else:
      msg = 'AMQP (Pika) SERVER connection could not be initialized after {} retries (reason:{})'.format(
        max_retries, exception
      )
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION
    # endif

    dct_ret = {
      'has_connection': has_connection,
      'msg': msg,
      'msg_type': msg_type
    }

    return dct_ret

  def establish_one_way_connection(self, channel_name, max_retries=5):
    cfg = None
    if channel_name.lower() == 'send':
      cfg = self.get_send_channel_def()
    elif channel_name.lower() == 'recv':
      cfg = self.get_recv_channel_def()
    # endif

    if cfg is None:
      return

    exchange = cfg[COMMS.EXCHANGE]
    queue = cfg[COMMS.QUEUE]
    exchange_type = cfg.get(COMMS.EXCHANGE_TYPE, 'fanout')
    queue_durable = cfg.get(COMMS.QUEUE_DURABLE, True)
    queue_exclusive = cfg.get(COMMS.QUEUE_EXCLUSIVE, False)

    nr_retry = 1
    has_connection = False
    exception = None

    while nr_retry <= max_retries:
      try:
        self._channel.exchange_declare(
          exchange=exchange,
          exchange_type=exchange_type
        )
        self._channel.queue_declare(
          queue=queue,
          durable=queue_durable,
          exclusive=queue_exclusive
        )
        self._channel.queue_bind(
          queue=queue,
          exchange=exchange,
          routing_key=self.cfg_routing_key
        )

        has_connection = True
      except Exception as e:
        exception = e
      # end try-except

      if has_connection:
        break

      sleep(1)
      nr_retry += 1
    # endwhile

    if has_connection:
      msg = "AMQP (Pika) '{}' connection successfully established on exchange '{}', queue '{}' with subtopic '{}'".format(
        channel_name.lower(), exchange, queue, self.cfg_subtopic
      )
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_NORMAL
    else:
      msg = "AMQP (Pika) '{}' connection on exchange '{}', queue '{}' could not be initialized after {} retries (reason:{})".format(
        channel_name.lower(), exchange, queue, max_retries, exception
      )
      msg_type = PAYLOAD_CT.STATUS_TYPE.STATUS_EXCEPTION
    # endif

    dct_objects = {'queue': queue, 'exchange': exchange}
    if channel_name.lower() == 'send':
      self._send_objects = dct_objects
    elif channel_name.lower() == 'recv':
      self._recv_objects = dct_objects
    # endif

    dct_ret = {
      'has_connection': has_connection,
      'msg': msg,
      'msg_type': msg_type
    }

    return dct_ret

  def receive(self):
    method_frame, header_frame, body = self._channel.basic_get(queue=self.recv_queue)
    if method_frame:
      msg = body.decode('utf-8')
      self._channel.basic_ack(method_frame.delivery_tag)
      self._recv_buff.append(msg)
    # endif
    return

  def send(self, message, send_to=None):
    prev_send_to = self._send_to
    self._send_to = send_to
    properties = pika.BasicProperties(content_type='application/json')
    self._channel.basic_publish(
      exchange=self.send_exchange,
      routing_key=self.cfg_routing_key,
      body=message,
      properties=properties
    )

    ####
    self.D("Sent message '{}'".format(message))
    ####
    self._send_to = prev_send_to
    return

  def release(self):
    msgs = []

    if self.recv_queue is not None:
      try:
        self._channel.queue_unbind(
          queue=self.recv_queue,
          exchange=self.recv_exchange,
          routing_key=self.cfg_routing_key,
        )

        self._channel.queue_delete(queue=self.recv_queue)
        msgs.append("AMQP (Pika) deleted queue '{}'".format(self.recv_queue))
      except Exception as e:
        msgs.append("AMQP (Pika) exception when deleting queue '{}'".format(self.recv_queue))
      # end try-except
    # endif

    try:
      self._channel.cancel()
      self._channel.close()
      del self._channel
      self._channel = None
      msgs.append('AMQP (Pika) closed channel')
    except Exception as e:
      msgs.append('AMQP (Pika) exception when closing channel: `{}`'.format(str(e)))
    # end try-except

    try:
      self._connection.close()
      del self._connection
      self._connection = None
      msgs.append('AMQP (Pika) disconnected')
    except Exception as e:
      msgs.append('AMQP (Pika) exception when disconnecting: `{}`'.format(str(e)))
    # end try-except

    dct_ret = {
      'msgs': msgs
    }

    return dct_ret
