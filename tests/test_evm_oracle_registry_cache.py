"""Offline checks for shared registry freshness, isolation and concurrency, and for the memory of a failed read."""
# The collector is run before a test checks that the error object of a failed read is no longer held.
import gc
import unittest
# A weak reference tells whether that error object is still held.
import weakref
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
# The stand-in for a slow registry read sleeps a fraction of a second.
from time import sleep
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ratio1.bc import evm


ORACLE = "0x000000000000000000000000000000000000dEaD"
OTHER = "0x0000000000000000000000000000000000000001"
# How many times the time a failed registry read took its error is remembered. A number of its own, not the SDK's
# constant: a change of that constant must fail here.
FAILURE_FACTOR = 3


class _Unanswered(Exception):
  """
  The error of a failed registry read in these tests.

  A class of its own, so that a test can tell the error of the read from every other error, and a class written
  in Python, so that a weak reference can tell whether the object is still held.

  Examples
  --------
  >>> raise _Unanswered("no answer")
  Traceback (most recent call last):
  _Unanswered: no answer
  """


def _traceback_entries(question):
  """
  Ask one registry question and count the entries of the traceback its error arrives with.

  Parameters
  ----------
  question : callable
    The question, called without arguments; it is expected to raise ``_Unanswered``.

  Returns
  -------
  int
    The number of entries of the error's traceback where the error is caught; 0 when nothing was raised.

  Notes
  -----
  The error is caught here and not with ``assertRaises``, which resets the traceback of what it catches.

  Examples
  --------
  >>> _traceback_entries(engine.web3_get_oracles)   # the registry's read fails
  3
  """
  try:
    # The question whose error is measured.
    question()
  except _Unanswered as error:
    # No entry counted yet; the walk starts at the outermost entry.
    entries, step = 0, error.__traceback__
    # One entry per frame the error passed on its way here.
    while step is not None:
      # One more entry, then the next inner one.
      entries, step = entries + 1, step.tb_next
    # The length of the traceback as the asker sees it.
    return entries
  # Nothing was raised: no traceback.
  return 0


class OracleRegistryCacheTests(unittest.TestCase):
  def setUp(self):
    """
    Start with an empty registry cache, a test clock at second 100 and two registries of one address each.

    Empties the process-wide registry cache (its content is restored after the test), replaces the cache's
    monotonic clock by one that reads second 100 until a test moves it, and replaces the client library so that
    no real RPC client is built. The engine under test resolves every network to one endpoint whose oracle and
    dAuth registry reads each return one address.

    Returns
    -------
    None

    Examples
    --------
    >>> self.engine.web3_get_oracles()   # in a test, right after setUp: one read
    ['0x000000000000000000000000000000000000dEaD']
    """
    # The process-wide cache, emptied for this test.
    self.cache = patch.dict(evm._ORACLE_REGISTRY_CACHE, clear=True)
    # In force from here on.
    self.cache.start()
    # The cache gets its content back after the test.
    self.addCleanup(self.cache.stop)
    # The cache's clock: second 100 until a test moves it.
    self.clock = patch.object(evm, "monotonic", return_value=100).start()
    # Every patch started here ends with the test.
    self.addCleanup(patch.stopall)
    # The client library is replaced, so no test builds a real RPC client.
    self.web3 = patch.object(evm, "Web3").start()
    # The RPC client the engine is given.
    self.w3 = Mock()
    # The contract object that client hands out for any address.
    self.contract = self.w3.eth.contract.return_value
    # The read of the oracle registry.
    self.oracles = self.contract.functions.getOracles.return_value.call
    # The read of the dAuth registry.
    self.dauth = self.contract.functions.getDAuthOracles.return_value.call
    # The oracle registry holds one address.
    self.oracles.return_value = [ORACLE]
    # So does the dAuth registry.
    self.dauth.return_value = [ORACLE]
    # The EVM part of the engine under test.
    self.engine = evm._EVMMixin()
    # The log call the full engine gives the EVM part: it records the line a failed read writes.
    self.engine.P = Mock()
    # The network, endpoint, client and contract addresses every read resolves to.
    self.vars = SimpleNamespace(
      network="devnet", rpc_url="https://rpc.invalid", w3=self.w3,
      controller_contract_address=OTHER, dauth_oracle_registry_address=ORACLE,
    )
    # The engine resolves its network to them without reading the environment.
    self.engine._get_web3_vars = Mock(return_value=self.vars)

  def failing_read(self, seconds, error):
    """
    Build the stand-in for a registry read that takes ``seconds`` on the test clock and then fails.

    Parameters
    ----------
    seconds : float
      The time the read takes: the test clock moves on by it before the error is raised.
    error : BaseException
      The error the read ends with; every call raises this one object.

    Returns
    -------
    callable
      The stand-in, to be set as the ``side_effect`` of a registry's read.

    Examples
    --------
    >>> self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    >>> self.engine.web3_get_dauth_oracles()   # the test clock is 20 s further on when this raises
    Traceback (most recent call last):
    _Unanswered: no answer
    """
    def read():
      """
      Let the read's time pass on the test clock, then fail.

      Returns
      -------
      None
        Nothing is returned: the call always raises.

      Raises
      ------
      BaseException
        The ``error`` given to ``failing_read``.

      Examples
      --------
      >>> read()
      Traceback (most recent call last):
      _Unanswered: no answer
      """
      # The time the read takes passes on the test clock.
      self.clock.return_value += seconds
      # The read ends with its error.
      raise error

    # The stand-in for a registry's read.
    return read

  def test_lists_are_shared_between_engines_and_callers_get_copies(self):
    second = evm._EVMMixin()
    second._get_web3_vars = self.engine._get_web3_vars
    for name, call in (("web3_get_oracles", self.oracles), ("web3_get_dauth_oracles", self.dauth)):
      with self.subTest(method=name):
        getattr(self.engine, name)().clear()
        self.assertEqual(getattr(second, name)(), [ORACLE])
        self.assertEqual(call.call_count, 1)
    self.web3.assert_not_called()
    self.web3.HTTPProvider.assert_not_called()

  def test_refresh_at_ten_minutes_and_failure_never_grants_stale_membership(self):
    """The kept list answers for ten minutes; a read that then fails raises, and the expired list grants nothing;
    a read that failed in no time is made again by the next question, and its new, empty list answers."""
    # The first question reads the registry: a member.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    # One second before the ten minutes are over.
    self.clock.return_value = 699
    # Answered from the kept list, whatever the letter case of the address.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE.lower()))
    # Still the one read.
    self.dauth.assert_called_once()
    # Ten minutes after the read the list has expired.
    self.clock.return_value = 700
    # The registry's read now fails.
    self.dauth.side_effect = RuntimeError("RPC unavailable")
    # The question gets the error of the read, not the membership the expired list would grant.
    with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
      # The question that finds the list expired.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # The read failed in no time on the test clock, so its error is remembered for no time: the next question
    # reads the registry again at once. The read answers again.
    self.dauth.side_effect = None
    # The registry is empty now.
    self.dauth.return_value = []
    # The address has left the registry.
    self.assertFalse(self.engine.web3_is_dauth_oracle(ORACLE))
    # The kept list is the empty one.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [])
    # Three reads: the first, the failed one, and the one right after it.
    self.assertEqual(self.dauth.call_count, 3)
    # Membership is answered from the list: the contract's own membership method is never called.
    self.contract.functions.isDAuthOracle.assert_not_called()

  def test_network_rpc_and_contract_have_separate_cache_entries(self):
    self.engine.web3_get_oracles()
    for field, value in (("network", "testnet"), ("rpc_url", "https://other.invalid"),
                         ("controller_contract_address", ORACLE)):
      with self.subTest(field=field):
        original = getattr(self.vars, field)
        setattr(self.vars, field, value)
        self.oracles.return_value = [OTHER]
        self.assertEqual(self.engine.web3_get_oracles(), [OTHER])
        setattr(self.vars, field, original)
        self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    self.assertEqual(self.oracles.call_count, 4)

  def test_failed_initial_fetch_can_retry(self):
    """A registry whose very first read fails in no time is read again by the next question, and then answers."""
    # The first read of the registry fails.
    self.oracles.side_effect = RuntimeError("RPC unavailable")
    # The caller gets that error.
    with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
      # The first question for this registry.
      self.engine.web3_get_oracles()
    # The endpoint answers again.
    self.oracles.side_effect = None
    # The read failed in no time on the test clock, so it is remembered for no time: the registry is read again at
    # once and its list returned.
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    # Two reads: the failed one and this one.
    self.assertEqual(self.oracles.call_count, 2)

  def test_concurrent_readers_share_refresh_without_blocking_other_registry(self):
    ready = Barrier(5)
    entered = Event()
    release = Event()

    def fetch():
      entered.set()
      if not release.wait(3):
        raise TimeoutError("Test did not release registry refresh")
      return [ORACLE]

    def read():
      ready.wait(timeout=3)
      return self.engine.web3_get_oracles()

    self.oracles.side_effect = fetch
    with ThreadPoolExecutor(max_workers=5) as pool:
      pending = [pool.submit(read) for _ in range(4)]
      try:
        ready.wait(timeout=3)
        self.assertTrue(entered.wait(3))
        independent = pool.submit(self.engine.web3_get_dauth_oracles)
        self.assertEqual(independent.result(timeout=3), [ORACLE])
      finally:
        release.set()
      self.assertEqual([future.result(timeout=3) for future in pending], [[ORACLE]] * 4)
    self.oracles.assert_called_once()

  def test_membership_preserves_invalid_address_and_vpn_guards(self):
    with self.assertRaisesRegex(AssertionError, "Invalid Ethereum address"):
      self.engine.web3_is_dauth_oracle("invalid")
    self.engine.P = Mock()
    with patch.object(evm, "EE_VPN_IMPL", True):
      self.assertFalse(self.engine.web3_is_dauth_oracle(ORACLE))
    self.dauth.assert_not_called()

  def test_a_slow_failed_read_is_held_three_times_the_time_it_took_and_no_longer(self):
    """While the list is expired, a read that fails after 20 s is not made again for 60 s counted from its failure,
    and one that fails after 7 s for 21 s; every question in between gets the error of that read, without a read,
    and never the expired list."""
    # The list is read and kept at second 100.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    # Ten minutes later it has expired.
    self.clock.return_value = 700
    # From now on the registry's read takes 20 s, as two tries of 10 s do, and ends without an answer.
    self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    # The question that finds the list expired makes the read and gets its error.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 700; the read fails at second 720.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # Right after the failure, and one second before three times 20 s have passed since it (not since the read
    # began).
    for second in (720, 720 + FAILURE_FACTOR * 20 - 1):
      # The moment of the next two questions.
      self.clock.return_value = second
      # A membership question gets the read's error: neither the True of the expired list nor a False.
      with self.assertRaisesRegex(_Unanswered, "no answer"):
        # Answered from the memory of the failed read.
        self.engine.web3_is_dauth_oracle(ORACLE)
      # A question for the list gets it too: neither the expired list nor an empty one.
      with self.assertRaisesRegex(_Unanswered, "no answer"):
        # Answered from the memory of the failed read.
        self.engine.web3_get_dauth_oracles()
    # No read was made for those four questions: one read answered, one failed. Without a memory each made the
    # read again.
    self.assertEqual(self.dauth.call_count, 2)
    # 60 s after the failure the memory is over.
    self.clock.return_value = 720 + FAILURE_FACTOR * 20
    # The read now takes 7 s before it fails.
    self.dauth.side_effect = self.failing_read(7, _Unanswered("no answer"))
    # The next question makes the read again.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 780; this read fails at second 787.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # That was the third read.
    self.assertEqual(self.dauth.call_count, 3)
    # One second before three times 7 s have passed since that failure.
    self.clock.return_value = 787 + FAILURE_FACTOR * 7 - 1
    # Still answered with its error.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 807, from the memory.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # Still three reads.
    self.assertEqual(self.dauth.call_count, 3)
    # 21 s after the failure: a read of 7 s is not held for the 60 s of the read of 20 s.
    self.clock.return_value = 787 + FAILURE_FACTOR * 7
    # The question makes the read again.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 808.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # The fourth read.
    self.assertEqual(self.dauth.call_count, 4)

  def test_a_fast_failed_read_is_made_again_after_its_own_short_time(self):
    """A read that fails after an eighth of a second is remembered for three eighths: half a second after it was
    asked the registry is read again, and answers if the endpoint does."""
    # The list is read and kept at second 100.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    # Ten minutes later it has expired.
    self.clock.return_value = 700
    # The registry's read fails after 0.125 s, as an error answer of the endpoint does.
    self.dauth.side_effect = self.failing_read(0.125, _Unanswered("error answer"))
    # The question that finds the list expired gets the error.
    with self.assertRaisesRegex(_Unanswered, "error answer"):
      # Asked at second 700; the read fails at second 700.125.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # A sixteenth of a second before three times 0.125 s have passed since the failure.
    self.clock.return_value = 700.125 + FAILURE_FACTOR * 0.125 - 0.0625
    # Still answered with the error.
    with self.assertRaisesRegex(_Unanswered, "error answer"):
      # Asked at second 700.4375, from the memory.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # Two reads: the first and the failed one.
    self.assertEqual(self.dauth.call_count, 2)
    # The endpoint answers again.
    self.dauth.side_effect = None
    # 0.375 s after the failure.
    self.clock.return_value = 700.125 + FAILURE_FACTOR * 0.125
    # The registry is read again and answers: one failed read of an eighth of a second cost half a second, not
    # the minute a read of 20 s is held.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    # The third read.
    self.assertEqual(self.dauth.call_count, 3)

  def test_a_step_of_the_wall_clock_does_not_change_how_long_a_failed_read_is_held(self):
    """The time a failed read took is not read from the wall clock: with the wall clock set an hour forward, or an
    hour back, while the read is made, a read of 8 s is held 24 s."""
    # The wall clock as the time module gives it: second 1,000,000 until a read moves it.
    wall = patch("time.time", return_value=1_000_000.0).start()
    # The dAuth registry with the wall clock set forward during its read, the oracle registry with it set back.
    for call, question, step in ((self.dauth, self.engine.web3_get_dauth_oracles, 3600),
                                 (self.oracles, self.engine.web3_get_oracles, -3600)):
      # Each case reports on its own.
      with self.subTest(step=step):
        # Each case starts at second 100 of the test clock.
        self.clock.return_value = 100

        def stepped():
          """
          Stand in for a registry read of 8 s during which the wall clock is set by ``step`` seconds.

          Returns
          -------
          None
            Nothing is returned: the call always raises.

          Raises
          ------
          _Unanswered
            Always, after the test clock moved 8 s on and the wall clock ``step`` s.

          Examples
          --------
          >>> stepped()
          Traceback (most recent call last):
          _Unanswered: no answer
          """
          # The read takes 8 s.
          self.clock.return_value += 8
          # Meanwhile the wall clock is set.
          wall.return_value += step
          # The read ends without an answer.
          raise _Unanswered("no answer")

        # The registry's read fails that way.
        call.side_effect = stepped
        # The registry's first question gets the error.
        with self.assertRaises(_Unanswered):
          # Asked at second 100; the read fails at second 108.
          question()
        # One second before three times 8 s have passed since the failure.
        self.clock.return_value = 108 + FAILURE_FACTOR * 8 - 1
        # Still answered with the error: a wall clock set back did not end the memory early.
        with self.assertRaises(_Unanswered):
          # Asked at second 131, from the memory.
          question()
        # The one read.
        self.assertEqual(call.call_count, 1)
        # 24 s after the failure.
        self.clock.return_value = 108 + FAILURE_FACTOR * 8
        # The read is made again: a wall clock set forward did not stretch the memory to hours.
        with self.assertRaises(_Unanswered):
          # Asked at second 132.
          question()
        # The second read.
        self.assertEqual(call.call_count, 2)

  def test_a_read_that_answers_again_ends_the_memory_and_lets_the_error_go(self):
    """Once the memory of a failed read is over and the read answers, the new list is returned and kept for ten
    minutes from that read, and the error object of the failed read is no longer held."""
    # The list is read and kept at second 100.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [ORACLE])
    # Ten minutes later it has expired.
    self.clock.return_value = 700
    # The error the registry's read ends with.
    error = _Unanswered("no answer")
    # The read takes 20 s and raises this one object.
    self.dauth.side_effect = self.failing_read(20, error)
    # The question that finds the list expired gets the error.
    with self.assertRaises(_Unanswered):
      # Asked at second 700; the read fails at second 720.
      self.engine.web3_get_dauth_oracles()
    # The endpoint answers again at once, with another list.
    self.dauth.side_effect, self.dauth.return_value = None, [OTHER]
    # One second before the 60 s of that read are over.
    self.clock.return_value = 720 + FAILURE_FACTOR * 20 - 1
    # The registry is not read yet: the question still gets the remembered error. This is the price of the memory.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # Two reads so far: the first and the failed one.
    self.assertEqual(self.dauth.call_count, 2)
    # The 60 s are over.
    self.clock.return_value = 720 + FAILURE_FACTOR * 20
    # The registry is read and its new list returned.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [OTHER])
    # One second before ten minutes have passed since that read, made at second 780.
    self.clock.return_value = 780 + 599
    # Answered from the kept list.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [OTHER])
    # Three reads: no further one.
    self.assertEqual(self.dauth.call_count, 3)
    # Ten minutes after that read.
    self.clock.return_value = 780 + 600
    # The list has expired and the registry is read again: the old failure does not stand in the way.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [OTHER])
    # The fourth read.
    self.assertEqual(self.dauth.call_count, 4)
    # A weak reference to the error object: it does not keep it.
    held = weakref.ref(error)
    # The test lets go of it.
    del error
    # Objects that only refer to each other are removed.
    gc.collect()
    # Nothing holds the error any more, so neither the frames it refers to: the cache let it go when the read
    # answered.
    self.assertIsNone(held())

  def test_two_threads_asking_at_once_share_one_failed_read(self):
    """Two threads ask while the registry's read fails slowly: one makes the read, the other waits for the
    registry's lock, gets the same error when the read ends and makes no read of its own."""
    # Both threads ask at the same moment.
    ready = Barrier(2)

    def unanswered():
      """
      Stand in for a registry read of 20 s that fails; it takes a fifth of a second of real time.

      Returns
      -------
      None
        Nothing is returned: the call always raises.

      Raises
      ------
      _Unanswered
        Always, after 20 s of the test clock and 0.2 s of real time.

      Examples
      --------
      >>> unanswered()
      Traceback (most recent call last):
      _Unanswered: no answer
      """
      # The read takes 20 s on the test clock, so its error is remembered for 60 s.
      self.clock.return_value += 20
      # In real time, far longer than the other thread needs to reach the registry's lock and wait for it.
      sleep(0.2)
      # The read ends without an answer.
      raise _Unanswered("no answer")

    def ask():
      """
      Ask for the oracle registry on the calling thread, once both threads are ready.

      Returns
      -------
      list
        The registry's addresses; not reached here, as the read fails.

      Raises
      ------
      _Unanswered
        The error of the failed read.

      Examples
      --------
      >>> ask()
      Traceback (most recent call last):
      _Unanswered: no answer
      """
      # Wait for the other thread, 3 s at most.
      ready.wait(timeout=3)
      # The question.
      return self.engine.web3_get_oracles()

    # The registry's read fails that way.
    self.oracles.side_effect = unanswered
    # Two threads.
    with ThreadPoolExecutor(max_workers=2) as pool:
      # Both ask.
      pending = [pool.submit(ask) for _ in range(2)]
      # Each of the two answers.
      for future in pending:
        # Both get the error of the read.
        with self.assertRaisesRegex(_Unanswered, "no answer"):
          # The asker's result, 3 s at most.
          future.result(timeout=3)
    # One read for the two of them. Without a memory the thread that had waited for the lock made its own.
    self.oracles.assert_called_once()

  def test_a_failed_read_of_one_registry_does_not_hold_the_other(self):
    """A failed read is remembered for its own registry only, also when it was that registry's very first read:
    the other registry, whose kept list has expired, is read and answers."""
    # The oracle registry is read and kept at second 100; the dAuth registry is not read yet.
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    # Ten minutes later the oracle registry's list has expired.
    self.clock.return_value = 700
    # The dAuth registry's read takes 20 s and fails.
    self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    # Its first question gets the error.
    with self.assertRaises(_Unanswered):
      # The very first read of the dAuth registry: asked at second 700, failed at second 720.
      self.engine.web3_get_dauth_oracles()
    # The oracle registry is read again and answers: the other registry's failure does not stand in for it.
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    # The dAuth registry's failure is still remembered.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # One read of the dAuth registry (without a memory its second question made the failing read again) and two
    # of the oracle registry.
    self.assertEqual((self.dauth.call_count, self.oracles.call_count), (1, 2))

  def test_one_line_is_logged_when_a_registry_stops_answering_and_none_until_it_answered_again(self):
    """The first failed read of a registry writes one log line that names the registry method, the network, the
    time the read took and the error, cut to 400 characters; the questions answered from its memory and the
    failed reads that follow write none, until the registry has answered and fails again."""
    # The dAuth registry's read takes 20 s and fails.
    self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    # Three questions: one read (asked at second 100, failed at second 120), two answers from its memory.
    for _ in range(3):
      # Each gets the error.
      with self.assertRaises(_Unanswered):
        # One question.
        self.engine.web3_get_dauth_oracles()
    # One line for the three of them.
    self.assertEqual(self.engine.P.call_count, 1)
    # The line's text.
    line = self.engine.P.call_args.args[0]
    # What its reader needs: which registry, on which network, how long the read took, and why it failed.
    for part in ("getDAuthOracles", "devnet", "after 20.000 s", "_Unanswered('no answer')"):
      # Each is in the line.
      self.assertIn(part, line)
    # The 60 s of that read are over.
    self.clock.return_value = 120 + FAILURE_FACTOR * 20
    # The question that makes the read again; it fails again, at second 200.
    with self.assertRaises(_Unanswered):
      # The second failed read in a row.
      self.engine.web3_get_dauth_oracles()
    # No line for it: the registry has not answered in between. A line per failed read would be a line per
    # question for a read that fails in milliseconds.
    self.assertEqual(self.engine.P.call_count, 1)
    # The 60 s of the second read are over, and the endpoint answers.
    self.clock.return_value, self.dauth.side_effect = 200 + FAILURE_FACTOR * 20, None
    # The registry is read and answers, at second 260.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [ORACLE])
    # Ten minutes later that list has expired, and the read fails with a text of 1000 characters.
    self.clock.return_value, self.dauth.side_effect = 260 + 600, self.failing_read(20, _Unanswered("x" * 1000))
    # The question that makes that read.
    with self.assertRaises(_Unanswered):
      # The first failed read since the registry answered.
      self.engine.web3_get_dauth_oracles()
    # One more line: two in all, none for the read that answered.
    self.assertEqual(self.engine.P.call_count, 2)
    # The error's text is what follows the line's last ": ".
    shown = self.engine.P.call_args.args[0].rpartition(": ")[2]
    # Cut to 400 characters: the class name, the opening bracket and quote, and the start of the text.
    self.assertEqual(shown, ("_Unanswered('" + "x" * 1000)[:400])

  def test_the_error_answered_from_the_memory_does_not_grow_with_the_questions(self):
    """The error a question gets from the memory of a failed read arrives with a traceback of the same length
    however many questions were answered with it before."""
    # The dAuth registry's read takes 20 s and fails.
    self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    # The question that makes the read.
    with self.assertRaises(_Unanswered):
      # The read that fails.
      self.engine.web3_get_dauth_oracles()
    # Five more questions, each answered from the memory: the length of the traceback each one's error has.
    lengths = [_traceback_entries(self.engine.web3_get_dauth_oracles) for _ in range(5)]
    # No read was made for them.
    self.assertEqual(self.dauth.call_count, 1)
    # Each got an error.
    self.assertGreater(lengths[0], 0)
    # The fifth is as long as the first: the frames of earlier questions are not kept in the error object.
    self.assertEqual(lengths, lengths[:1] * 5)

  def test_each_question_answered_from_the_memory_gets_an_error_of_its_own_with_no_other_callers_context(self):
    """Each question answered from the memory gets an error object of its own, of the read's type and text, that
    carries neither the error another caller was handling when it asked nor the cause of the failed read; and the
    memory does not hold the error, or the frames, of the call whose read failed."""
    def read():
      """
      Stand in for a registry read of 20 s that fails with an error caused by another one, as a timeout is.

      Returns
      -------
      None
        Nothing is returned: the call always raises.

      Raises
      ------
      _Unanswered
        Always, after 20 s of the test clock, with a ``ConnectionError`` as its cause.

      Examples
      --------
      >>> read()
      Traceback (most recent call last):
      _Unanswered: no answer
      """
      # The read takes 20 s on the test clock, so its error is remembered for 60 s.
      self.clock.return_value += 20
      try:
        # The transport's own error.
        raise ConnectionError("connection reset")
      except ConnectionError as cause:
        # The read's error, caused by it.
        raise _Unanswered("no answer") from cause

    # The dAuth registry's read fails that way.
    self.dauth.side_effect = read
    # The question that makes the read.
    with self.assertRaises(_Unanswered) as failed:
      # The read that fails, at second 120.
      self.engine.web3_get_dauth_oracles()
    # The read's own error goes to its caller, with its cause.
    self.assertIsInstance(failed.exception.__cause__, ConnectionError)
    # A weak reference to it: it does not keep it.
    held = weakref.ref(failed.exception)
    # The test lets go of it.
    del failed
    # Objects that only refer to each other are removed.
    gc.collect()
    # Nothing holds it: the memory keeps a copy, so neither the error nor the frames of the failed call stay.
    self.assertIsNone(held())
    try:
      # Caller A handles an error of its own, whose text stands for request data, when it asks.
      raise ValueError("caller A's own error")
    except ValueError:
      # A's question, answered from the memory.
      with self.assertRaises(_Unanswered) as asked_by_a:
        # A asks.
        self.engine.web3_get_dauth_oracles()
    # Caller B asks with nothing being handled.
    with self.assertRaises(_Unanswered) as asked_by_b:
      # B asks.
      self.engine.web3_get_dauth_oracles()
    # B's error, as B would log it.
    error = asked_by_b.exception
    # Not A's object: before, every question raised one shared object.
    self.assertIsNot(error, asked_by_a.exception)
    # The read's type and text.
    self.assertEqual((type(error), str(error)), (_Unanswered, "no answer"))
    # No context and no cause: neither A's handled error (which a shared object kept) nor the read's cause.
    self.assertEqual((error.__context__, error.__cause__), (None, None))
    # One read for the three questions.
    self.assertEqual(self.dauth.call_count, 1)

  def test_an_interrupted_read_is_not_remembered_and_the_error_of_the_next_one_is(self):
    """A read ended by an interrupt of the program (Ctrl-C in an interactive session), which is no error of the
    read, is not remembered however long it took: the next question makes the read, and the error of that read
    is remembered."""
    # The read is interrupted after 20 s.
    self.dauth.side_effect = self.failing_read(20, KeyboardInterrupt())
    # The interrupt reaches the caller.
    with self.assertRaises(KeyboardInterrupt):
      # The interrupted read.
      self.engine.web3_get_dauth_oracles()
    # From now on the read fails with an error after 20 s.
    self.dauth.side_effect = self.failing_read(20, _Unanswered("no answer"))
    # The next question is not answered with the interrupt: it makes the read and gets that read's error.
    with self.assertRaises(_Unanswered):
      # The second read.
      self.engine.web3_get_dauth_oracles()
    # That error is remembered.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # Two reads: the interrupted one and the failed one.
    self.assertEqual(self.dauth.call_count, 2)


if __name__ == "__main__":
  unittest.main()
