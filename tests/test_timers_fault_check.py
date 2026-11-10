"""Verify that start_timer scans its section for faults only when the started timer is faulty."""
import unittest
from unittest import mock

from ratio1.logging.logger_mixins.timers_mixin import _TimersMixin


class _TimersHarness(_TimersMixin):
  """The timers mixin with the few Logger attributes it reads."""
  DEBUG = True
  is_main_thread = True
  config_data = None

  def __init__(self):
    self.messages = []
    super().__init__()

  def P(self, msg, **kwargs):
    self.messages.append(msg)


class TestTimersFaultCheck(unittest.TestCase):
  """Cover the healthy lap and the faulty-timer report of start_timer."""

  def setUp(self):
    self.log = _TimersHarness()
    scan = mock.patch.object(
      self.log, "_get_section_faulty_timers", wraps=self.log._get_section_faulty_timers
    )
    self.scan = scan.start()
    self.addCleanup(scan.stop)

  def test_balanced_laps_do_not_scan_the_section(self):
    """Nested start/stop pairs never pay for a section scan."""
    for _ in range(3):
      self.log.start_timer("outer", section="s")
      self.log.start_timer("inner", section="s")
      self.log.end_timer("inner", section="s")
      self.log.end_timer("outer", section="s")

    self.scan.assert_not_called()
    self.assertEqual(self.log.messages, [])

  def test_timer_started_twice_is_reported_once(self):
    """A timer started again without a stop is still reported, once per section."""
    for _ in range(3):
      self.log.start_timer("leaky", section="s")

    self.assertEqual(self.scan.call_count, 1)
    self.assertEqual(self.log.messages[0], "Something is wrong with the timers in section 's':")
    self.assertTrue(self.log.messages[1].startswith("  leaky: "))
    self.assertEqual(len(self.log.messages), 2)


if __name__ == "__main__":
  unittest.main()
