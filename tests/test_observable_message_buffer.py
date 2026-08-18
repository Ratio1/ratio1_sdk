import threading
import unittest

from ratio1.comm.message_buffer import ObservableMessageBuffer


class _Clock:
  def __init__(self, value=0.0):
    self.value = value

  def __call__(self):
    return self.value


class TestObservableMessageBuffer(unittest.TestCase):

  def test_full_buffer_rejects_newest_and_preserves_fifo_prefix(self):
    clock = _Clock(10.0)
    buffer = ObservableMessageBuffer(capacity=2, clock=clock)

    self.assertTrue(buffer.try_append("first"))
    clock.value = 11.0
    self.assertTrue(buffer.try_append("second"))
    clock.value = 12.0
    self.assertFalse(buffer.try_append("rejected"))

    self.assertEqual(buffer.popleft(), "first")
    self.assertEqual(buffer.popleft(), "second")
    snapshot = buffer.snapshot(now=12.0)
    self.assertEqual(snapshot.admitted, 2)
    self.assertEqual(snapshot.rejected_full, 1)
    self.assertEqual(snapshot.dequeued, 2)
    self.assertEqual(snapshot.depth, 0)
    self.assertEqual(snapshot.high_water_mark, 2)
    self.assertTrue(snapshot.degraded)
    self.assertTrue(snapshot.conserved)

  def test_oldest_age_reads_only_the_head_timestamp(self):
    clock = _Clock(100.0)
    buffer = ObservableMessageBuffer(capacity=3, clock=clock)
    buffer.try_append("oldest")
    clock.value = 101.0
    buffer.try_append("newer")

    snapshot = buffer.snapshot(now=106.5)

    self.assertEqual(snapshot.oldest_age_seconds, 6.5)
    self.assertEqual(snapshot.depth, 2)

  def test_close_rejects_new_admission_and_wakes_waiter(self):
    buffer = ObservableMessageBuffer(capacity=2)
    received = []
    waiter = threading.Thread(
      target=lambda: received.append(buffer.get(timeout=1.0)),
      daemon=True,
    )
    waiter.start()
    buffer.close(discard=False)
    waiter.join(timeout=1.0)

    self.assertFalse(waiter.is_alive())
    self.assertEqual(received, [None])
    self.assertFalse(buffer.try_append("after-close"))
    snapshot = buffer.snapshot()
    self.assertTrue(snapshot.closed)
    self.assertEqual(snapshot.rejected_closed, 1)
    self.assertEqual(snapshot.rejected_full, 0)

  def test_discard_on_close_is_terminally_conserved(self):
    buffer = ObservableMessageBuffer(capacity=2)
    buffer.try_append("one")
    buffer.try_append("two")

    buffer.close(discard=True)

    snapshot = buffer.snapshot()
    self.assertEqual(snapshot.discarded_on_close, 2)
    self.assertEqual(snapshot.depth, 0)
    self.assertTrue(snapshot.conserved)


if __name__ == "__main__":
  unittest.main()
