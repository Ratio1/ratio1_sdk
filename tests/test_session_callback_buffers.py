import unittest
from threading import Lock

from ratio1.base.generic_session import GenericSession
from ratio1.comm.message_buffer import ObservableMessageBuffer


class _JoinProbe:
  def __init__(self, buffers):
    self.buffers = buffers
    self.joined = False

  def join(self):
    self.joined = True
    for buffer in self.buffers:
      if not buffer.snapshot().closed:
        raise AssertionError("callback admission was still open during join")


class TestSessionCallbackBuffers(unittest.TestCase):

  def test_callback_queue_size_accepts_numeric_config_strings(self):
    self.assertEqual(GenericSession._normalize_callback_queue_size("7"), 7)
    self.assertEqual(GenericSession._normalize_callback_queue_size(7), 7)

    for invalid in (True, False, "", "0", "-1", "not-a-number", 0, -1):
      with self.subTest(invalid=invalid):
        with self.assertRaises(ValueError):
          GenericSession._normalize_callback_queue_size(invalid)

  def test_session_creates_bounded_buffers_for_every_callback_channel(self):
    session = object.__new__(GenericSession)
    session._callback_queue_size = 7

    session._GenericSession__create_user_callback_threads()
    try:
      for buffer in [
        session._payload_messages,
        session._notif_messages,
        session._hb_messages,
      ]:
        self.assertIsInstance(buffer, ObservableMessageBuffer)
        self.assertEqual(buffer.capacity, 7)
    finally:
      session._GenericSession__release_callback_threads()

  def test_shutdown_closes_all_admission_before_joining_consumers(self):
    session = object.__new__(GenericSession)
    buffers = [ObservableMessageBuffer(capacity=1) for _ in range(3)]
    session._payload_messages, session._notif_messages, session._hb_messages = buffers
    session._payload_thread = _JoinProbe(buffers)
    session._notif_thread = _JoinProbe(buffers)
    session._hb_thread = _JoinProbe(buffers)
    session._GenericSession__running_callback_threads = True

    session._GenericSession__release_callback_threads()

    self.assertTrue(all(buffer.snapshot().closed for buffer in buffers))
    self.assertTrue(session._payload_thread.joined)
    self.assertTrue(session._notif_thread.joined)
    self.assertTrue(session._hb_thread.joined)

  def test_callback_processing_success_and_failure_are_separately_counted(self):
    session = object.__new__(GenericSession)
    session._payload_messages = ObservableMessageBuffer(capacity=2)
    session._notif_messages = ObservableMessageBuffer(capacity=1)
    session._hb_messages = ObservableMessageBuffer(capacity=1)
    session._payload_messages.try_append("first")
    session._payload_messages.try_append("second")
    session._GenericSession__running_callback_threads = False
    session._callback_outcomes_lock = Lock()
    session._callback_outcomes = {
      channel: {"processed": 0, "processing_failed": 0}
      for channel in ["payload", "notification", "heartbeat"]
    }
    calls = []

    def process(message, callback, source):
      calls.append(message)
      if message == "first":
        raise RuntimeError("expected callback failure")

    session._GenericSession__on_message_default_callback = process

    session._GenericSession__handle_messages(
      session._payload_messages,
      lambda *args: None,
      source="payload",
    )

    status = session.get_callback_queue_status()
    self.assertEqual(calls, ["first", "second"])
    self.assertEqual(status["payload"]["processed"], 1)
    self.assertEqual(status["payload"]["processing_failed"], 1)
    self.assertEqual(status["payload"]["depth"], 0)


if __name__ == "__main__":
  unittest.main()
