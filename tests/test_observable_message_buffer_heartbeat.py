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

  def test_oldest_age_reads_head_timestamp_without_scanning(self):
    clock = _Clock(100.0)
    buffer = ObservableMessageBuffer(capacity=3, clock=clock)
    buffer.try_append("oldest")
    clock.value = 101.0
    buffer.try_append("newer")

    snapshot = buffer.snapshot(now=106.5)

    self.assertEqual(snapshot.oldest_age_seconds, 6.5)
    self.assertEqual(snapshot.depth, 2)
    self.assertTrue(snapshot.conserved)

  def test_waiting_consumer_is_notified_by_admission(self):
    buffer = ObservableMessageBuffer(capacity=1)
    consumed = []

    consumer = threading.Thread(
      target=lambda: consumed.append(buffer.get(timeout=1.0)),
      daemon=True,
    )
    consumer.start()
    self.assertTrue(buffer.try_append("heartbeat"))
    consumer.join(timeout=1.0)

    self.assertFalse(consumer.is_alive())
    self.assertEqual(consumed, ["heartbeat"])

  def test_concurrent_producers_remain_exactly_conserved(self):
    messages_per_producer = 500
    producer_count = 8
    buffer = ObservableMessageBuffer(
      capacity=messages_per_producer * producer_count,
    )

    def produce(producer_id):
      for sequence in range(messages_per_producer):
        self.assertTrue(buffer.try_append((producer_id, sequence)))

    producers = [
      threading.Thread(target=produce, args=(producer_id,))
      for producer_id in range(producer_count)
    ]
    for producer in producers:
      producer.start()
    for producer in producers:
      producer.join(timeout=2.0)

    snapshot = buffer.snapshot()
    self.assertEqual(snapshot.admitted, producer_count * messages_per_producer)
    self.assertEqual(snapshot.depth, producer_count * messages_per_producer)
    self.assertEqual(snapshot.rejected_full, 0)
    self.assertTrue(snapshot.conserved)

  def test_close_wakes_waiter_and_clear_is_accounted_as_discarded(self):
    buffer = ObservableMessageBuffer(capacity=2)
    buffer.try_append("one")
    buffer.try_append("two")
    buffer.close(discard=True)

    snapshot = buffer.snapshot()
    self.assertTrue(snapshot.closed)
    self.assertEqual(snapshot.discarded_on_close, 2)
    self.assertEqual(snapshot.depth, 0)
    self.assertTrue(snapshot.conserved)
    self.assertIsNone(buffer.get(timeout=0.01))

  def test_closed_buffer_rejection_is_distinct_from_queue_full(self):
    buffer = ObservableMessageBuffer(capacity=1)
    buffer.close()

    self.assertFalse(buffer.try_append("late"))

    snapshot = buffer.snapshot()
    self.assertEqual(snapshot.rejected_closed, 1)
    self.assertEqual(snapshot.rejected_full, 0)
    self.assertTrue(snapshot.conserved)


if __name__ == "__main__":
  unittest.main()
