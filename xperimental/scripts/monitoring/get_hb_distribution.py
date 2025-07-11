import json

from collections import defaultdict
import matplotlib.pyplot as plt

from ratio1 import Session, Payload, PAYLOAD_DATA, HEARTBEAT_DATA


class MessageHandler:
  def __init__(self):
    self.notifications = []
    self.heartbeats = []
    self.payloads = []

  def on_heartbeat(self, session: Session, node_addr: str, heartbeat: dict):
    self.heartbeats.append(heartbeat)
    return

  def on_payload(
      self,
      session: Session,
      node_addr: str,
      pipeline_name: str,
      plugin_signature: str,
      plugin_instance: str,
      payload: Payload
  ):
    self.payloads.append(payload.data)
    return

  def on_notification(self, session, address, notification):
    self.notifications.append(notification.data)
    return

  def get_messages_count_volume(self):
    messages_count = defaultdict(int)
    messages_volume = defaultdict(int)

    messages_sizes = defaultdict(list)

    node_messages_volume = defaultdict(int)
    node_messages_count = defaultdict(int)

    signature = 'Notifications'
    for notification in self.notifications:
      messages_count[signature] += 1
      message_size = len(json.dumps(notification))

      messages_volume[signature] += message_size
      messages_sizes[signature].append(message_size)

      node_address = notification.get('EE_ID', 'no-addr')
      node_messages_count[node_address] += 1
      node_messages_volume[node_address] += message_size


    signature = 'Heartbeats'
    for heartbeat in self.heartbeats:
      messages_count[signature] += 1
      message_size = len(json.dumps(heartbeat))

      messages_volume[signature] += message_size
      messages_sizes[signature].append(message_size)

      node_address = heartbeat.get('EE_ID', 'no-addr')
      node_messages_count[node_address] += 1
      node_messages_volume[node_address] += message_size


    for payload in self.payloads:
      signature = payload.get('SIGNATURE', 'no-signature')
      message_size = len(json.dumps(payload))

      messages_count[signature] += 1
      messages_volume[signature] += message_size
      messages_sizes[signature].append(message_size)

      node_address = payload.get('EE_ID', 'no-addr')
      node_messages_count[node_address] += 1
      node_messages_volume[node_address] += message_size

    return messages_count, messages_volume, messages_sizes, node_messages_count, node_messages_volume


  def get_messages_count_volume_per_node(self):
    nodes_stats = defaultdict(int)

    return


def plot_results(xlabel: [], ylabel: [], xdata: str, ydata: str, title: str):
  plt.figure(figsize=(10, 8))  # Width=10, Height=6

  plt.bar(xdata, ydata, color='b')

  plt.xlabel(xlabel)
  plt.ylabel(ylabel)

  plt.xticks(rotation=35)

  plt.title(title)
  plt.show()


def visualize_distribution_with_step(signature, messages_sizes, step=100):
    bins = list(range(min(messages_sizes), int(max(messages_sizes)) + step, step))

    plt.figure(figsize=(10, 6))
    plt.hist(messages_sizes, bins=bins, color='skyblue', edgecolor='black')
    plt.xlabel('Message Size Ranges')
    plt.ylabel('Frequency')
    plt.title(f'Message Size Distribution for {signature} with step {step}')
    plt.xticks(bins, rotation=45)
    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
  COLLECTION_PERIOD_SECONDS = 120
  # create a naive message handler
  filterer = MessageHandler()

  # create a session
  session = Session(
    on_heartbeat=filterer.on_heartbeat,
    on_payload=filterer.on_payload,
    on_notification=filterer.on_notification,
    verbosity=3,
  )

  session.wait(seconds=COLLECTION_PERIOD_SECONDS, close_session=True)
  session.P("Session finished successfully!", color='g')

  message_count, messages_volume, messages_sizes, node_messages_count, node_messages_volume = filterer.get_messages_count_volume()

  for key, value in messages_sizes.items():
    visualize_distribution_with_step(key, value, step=500)

  categories = list(message_count.keys())

  plot_results(xlabel='Message Type', ylabel='Messages Count', xdata=categories, ydata=list(message_count.values()), title=f'Messages Count in {COLLECTION_PERIOD_SECONDS}')
  plot_results(xlabel='Message Type', ylabel='Messages Volume', xdata=categories, ydata=list(messages_volume.values()), title=f"Messages Volume in {COLLECTION_PERIOD_SECONDS}")

  categories = list(node_messages_count.keys)


  plot_results(xlabel='Message Type', ylabel='Messages Count', xdata=categories, ydata=list(node_messages_count.values()),
               title=f'Messages Count by node in {COLLECTION_PERIOD_SECONDS}')
  plot_results(xlabel='Message Type', ylabel='Messages Volume', xdata=categories, ydata=list(node_messages_volume.values()),
               title=f'Messages Volume by node in {COLLECTION_PERIOD_SECONDS}')

  session.P("Script run successfully!")
  session.close()
