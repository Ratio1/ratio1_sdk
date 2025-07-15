import json
import os
import queue
import threading
from datetime import time, datetime

from ratio1 import Session, Payload, PAYLOAD_DATA, HEARTBEAT_DATA


class MS_TYPE:
  HB = 'hb'
  PL = 'pl'
  NT = 'nt'


class NetworkSniffer:
  """
  A multithreaded network sniffer that collects and writes heartbeat, payload,
  and notification data from a `Session` to separate files in NDJSON format.
  It uses queues to manage incoming data and threads to write data to files
  asynchronously. The sniffer also logs its start and stop times and provides
  a summary of the collected data.
  Note: NDJSON (Newline Delimited JSON) is a format where each line
        in a file is a valid JSON object. It is commonly used for streaming data or
        storing large datasets because it allows processing one JSON object at a time
        without loading the entire file into memory.
  """
  def __init__(self, output_path: str = None, collection_period_seconds: int = 60):

    if output_path is None:
      date_started = datetime.now().isoformat()
      output_path = os.path.join('../network_sniffer/output', 'network_sniffer',
                                 date_started.replace(':', '-').replace('.', '-') + '_' + str(
                                   collection_period_seconds))
      os.makedirs(output_path, exist_ok=True)

    self.flush_every_n = 1

    self.notifications_queue = queue.Queue()
    self.heartbeats_queue = queue.Queue()
    self.payloads_queue = queue.Queue()

    self.output_path = output_path
    self.files = {
      MS_TYPE.HB: os.path.join(output_path, 'heartbeats.ndjson'),
      MS_TYPE.PL: os.path.join(output_path, 'payloads.ndjson'),
      MS_TYPE.NT: os.path.join(output_path, 'notifications.ndjson')
    }
    self._threads = []
    self.start()

  def on_heartbeat(self, session: Session, node_addr: str, heartbeat: dict):
    self.heartbeats_queue.put_nowait(heartbeat)
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
    self.payloads_queue.put_nowait(payload.data)
    return

  def on_notification(self, session, address, notification):
    self.notifications_queue.put_nowait(notification.data)
    return

  def start(self):
    self.date_started = datetime.now().isoformat()
    self.is_running = True

    self._threads.append(
      threading.Thread(target=self.writer_loop, args=(self.heartbeats_queue, MS_TYPE.HB), daemon=False))
    self._threads.append(
      threading.Thread(target=self.writer_loop, args=(self.payloads_queue, MS_TYPE.PL), daemon=False))
    self._threads.append(
      threading.Thread(target=self.writer_loop, args=(self.notifications_queue, MS_TYPE.NT), daemon=False))

    for thread in self._threads:
      thread.start()

  def stop(self):
    self.date_stopped = datetime.now().isoformat()
    self.is_running = False
    for thread in self._threads:
      thread.join()

  def writer_loop(self, q, ms_type):
    buffer = []
    filename = self.files[ms_type]
    first_item_written = False

    with open(filename, 'a') as f:
      f.seek(0, os.SEEK_END)

      try:
        while self.is_running or not q.empty():
          try:
            item = q.get(timeout=1)
            buffer.append(item)
            if len(buffer) >= self.flush_every_n:
              for item in buffer:
                try:
                  f.write(json.dumps(item) + '\n')
                except Exception as e:
                  print(f"Error writing {ms_type} data to file {filename}: {e}")
              buffer.clear()
              f.flush()
          except Exception as e:
            continue
          # end try get from queue
        # end while loop
      except Exception as e:
        print(f"Error in writer loop for {ms_type}: {e}")
      finally:
        if len(buffer):
          for item in buffer:
            try:
              f.write(json.dumps(item) + '\n')
            except Exception as e:
              print(f"Error writing {ms_type} data to file {filename}: {e}")
        f.flush()
    return

  def write_log_file(self):
    filename = os.path.join(self.output_path, f"network_sniffer_{self.date_started}.log")
    with open(filename, 'w') as f:
      f.write(f"Network Sniffer started at {self.date_started}\n")
      f.write(f"Network Sniffer stopped at {self.date_stopped}\n")
      f.write(f"Heartbeats written to: {self.files[MS_TYPE.HB]}\n")
      f.write(f"Payloads written to: {self.files[MS_TYPE.PL]}\n")
      f.write(f"Notifications written to: {self.files[MS_TYPE.NT]}\n")
      f.flush()
    return

def run_network_sniffer(collection_period_seconds: int = 60):
  date_started = datetime.now().isoformat()

  output_path = os.path.join('output', 'network_sniffer', date_started.replace(':', '-').replace('.', '-') + '_' + str(
    collection_period_seconds))
  os.makedirs(output_path, exist_ok=True)

  sniffer = NetworkSniffer(output_path, collection_period_seconds=collection_period_seconds)

  session = Session(
    on_heartbeat=sniffer.on_heartbeat,
    on_payload=sniffer.on_payload,
    on_notification=sniffer.on_notification,
    verbosity=3,
  )

  session.log.log_file = os.path.join(output_path, f"network_sniffer_{date_started}.log")

  session.P(
    f"Session started at {date_started}, collecting messages for {collection_period_seconds} seconds...")

  session.wait(seconds=collection_period_seconds, close_session=True)
  session.close()
  session.P("Session finished successfully!", color='g')
  sniffer.stop()
  sniffer.write_log_file()
  session.P("Script run successfully!")


if __name__ == '__main__':
  SNIFFER_COLLECTION_PERIOD_SECONDS = 1800
  run_network_sniffer(collection_period_seconds=SNIFFER_COLLECTION_PERIOD_SECONDS)
