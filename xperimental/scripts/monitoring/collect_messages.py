import json
import os

from datetime import datetime

from ratio1 import Session, Payload


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


if __name__ == '__main__':
  COLLECTION_PERIOD_SECONDS = 3600
  # create a naive message handler
  sniffer = MessageHandler()

  start_date_iso = datetime.now().isoformat()
  # create a session
  session = Session(
    on_heartbeat=sniffer.on_heartbeat,
    on_payload=sniffer.on_payload,
    on_notification=sniffer.on_notification,
    verbosity=3,
  )

  session.wait(seconds=COLLECTION_PERIOD_SECONDS, close_session=True)
  session.P("Session finished successfully!", color='g')

  folder_name = f"messages_{start_date_iso}_{COLLECTION_PERIOD_SECONDS}"
  os.makedirs(folder_name, exist_ok = True)

  session.P("Script run successfully!")
  session.close()
