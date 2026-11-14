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
# Seconds a failed registry read is remembered. A number of its own, not the SDK's constant: a change of that
# constant must fail here.
FAILURE_TTL = 60


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
    """Start with an empty registry cache, a test clock at second 100 and two registries of one address each."""
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
    once that failure is no longer remembered the registry is read again and its new, empty list answers."""
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
    # The failed read is remembered for 60 s. The test clock stood still while it failed, so the registry is read
    # again from second 760 on; before, the next question read it at once.
    self.clock.return_value = 700 + FAILURE_TTL
    # The read answers again.
    self.dauth.side_effect = None
    # The registry is empty now.
    self.dauth.return_value = []
    # The address has left the registry.
    self.assertFalse(self.engine.web3_is_dauth_oracle(ORACLE))
    # The kept list is the empty one.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [])
    # Three reads: the first, the failed one, and the one after the 60 s.
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
    """A registry whose very first read fails is read again once that failure is no longer remembered, and then
    answers."""
    # The first read of the registry fails.
    self.oracles.side_effect = RuntimeError("RPC unavailable")
    # The caller gets that error.
    with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
      # The first question for this registry.
      self.engine.web3_get_oracles()
    # The endpoint answers again.
    self.oracles.side_effect = None
    # The failure of second 100 is remembered for 60 s; before, the next question read the registry at once.
    self.clock.return_value = 100 + FAILURE_TTL
    # The registry is read again and its list returned.
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

  def test_a_failed_read_is_made_once_a_minute_and_answered_with_its_error_meanwhile(self):
    """While the list is expired and the registry's read fails, the read is made once per 60 s counted from its
    failure; every question in between gets the error of that read, without a read, and never the expired list."""
    # The list is read and kept at second 100.
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    # Ten minutes later it has expired.
    self.clock.return_value = 700

    def unanswered():
      """
      Stand in for a registry read the endpoint never answers: 20 s pass, then the read ends with an error.

      Returns
      -------
      None
        Nothing is returned: the call always raises.

      Raises
      ------
      _Unanswered
        Always, after the test clock moved 20 s on.

      Examples
      --------
      >>> self.clock.return_value = 700
      >>> unanswered()
      Traceback (most recent call last):
      _Unanswered: no answer
      >>> self.clock.return_value
      720
      """
      # Two tries of 10 s pass on the test clock while the read waits.
      self.clock.return_value += 20
      # The read ends without an answer.
      raise _Unanswered("no answer")

    # From now on the registry's read fails after 20 s.
    self.dauth.side_effect = unanswered
    # The question that finds the list expired makes the read and gets its error.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 700; the read fails at second 720.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # Right after the failure, and one second before 60 s have passed since it (not since the read began).
    for second in (720, 720 + FAILURE_TTL - 1):
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
    # No read was made for those four questions: one read answered, one failed. Before, each made the read again.
    self.assertEqual(self.dauth.call_count, 2)
    # 60 s after the failure the memory is over.
    self.clock.return_value = 720 + FAILURE_TTL
    # The next question makes the read again, and it fails again.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 780; this read fails at second 800.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # That was the third read.
    self.assertEqual(self.dauth.call_count, 3)
    # Its failure is remembered anew: the question that follows is answered with it.
    with self.assertRaisesRegex(_Unanswered, "no answer"):
      # Asked at second 800, inside the new 60 s.
      self.engine.web3_is_dauth_oracle(ORACLE)
    # Still three reads.
    self.assertEqual(self.dauth.call_count, 3)

  def test_a_read_that_answers_again_ends_the_memory_and_lets_the_error_go(self):
    """Once the 60 s are over and the read answers, the new list is returned and kept for ten minutes from that
    read, and the error object of the failed read is no longer held."""
    # The list is read and kept at second 100.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [ORACLE])
    # Ten minutes later it has expired.
    self.clock.return_value = 700
    # The error the registry's read ends with from now on.
    error = _Unanswered("no answer")
    # The stand-in raises this one object.
    self.dauth.side_effect = error
    # The question that finds the list expired gets the error.
    with self.assertRaises(_Unanswered):
      # The read that fails, at second 700.
      self.engine.web3_get_dauth_oracles()
    # The endpoint answers again at once, with another list.
    self.dauth.side_effect, self.dauth.return_value = None, [OTHER]
    # One second before the 60 s are over.
    self.clock.return_value = 700 + FAILURE_TTL - 1
    # The registry is not read yet: the question still gets the remembered error. This is the price of the memory.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # Two reads so far: the first and the failed one.
    self.assertEqual(self.dauth.call_count, 2)
    # The 60 s are over.
    self.clock.return_value = 700 + FAILURE_TTL
    # The registry is read and its new list returned.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [OTHER])
    # One second before ten minutes have passed since that read.
    self.clock.return_value = 700 + FAILURE_TTL + 599
    # Answered from the kept list.
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [OTHER])
    # Three reads: no further one.
    self.assertEqual(self.dauth.call_count, 3)
    # Ten minutes after that read.
    self.clock.return_value = 700 + FAILURE_TTL + 600
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
    """Two threads ask while the registry's read fails: one makes the read, the other waits for the registry's
    lock, gets the same error when the read ends and makes no read of its own."""
    # Both threads ask at the same moment.
    ready = Barrier(2)

    def unanswered():
      """
      Stand in for a registry read that takes a fifth of a second and then fails.

      Returns
      -------
      None
        Nothing is returned: the call always raises.

      Raises
      ------
      _Unanswered
        Always, after 0.2 s.

      Examples
      --------
      >>> unanswered()
      Traceback (most recent call last):
      _Unanswered: no answer
      """
      # Far longer than the other thread needs to reach the registry's lock and wait for it.
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

    # The registry's read fails after 0.2 s.
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
    # One read for the two of them. Before, the thread that had waited for the lock made its own.
    self.oracles.assert_called_once()

  def test_a_failed_read_of_one_registry_does_not_hold_the_other(self):
    """A failed read is remembered for its own registry only, also when it was that registry's very first read:
    the other registry, whose kept list has expired, is read and answers."""
    # The oracle registry is read and kept at second 100; the dAuth registry is not read yet.
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    # Ten minutes later the oracle registry's list has expired.
    self.clock.return_value = 700
    # The dAuth registry's read fails.
    self.dauth.side_effect = _Unanswered("no answer")
    # Its first question gets the error.
    with self.assertRaises(_Unanswered):
      # The very first read of the dAuth registry.
      self.engine.web3_get_dauth_oracles()
    # The oracle registry is read again and answers: the other registry's failure does not stand in for it.
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
    # The dAuth registry's failure is still remembered.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # One read of the dAuth registry (before, its second question made the failing read again) and two of the
    # oracle registry.
    self.assertEqual((self.dauth.call_count, self.oracles.call_count), (1, 2))

  def test_one_line_is_logged_per_failed_read_and_none_per_question_answered_from_it(self):
    """A failed read writes one log line that names the registry method, the network, the 60 s and the error, cut
    to 400 characters; the questions answered from its memory write none."""
    # The dAuth registry's read fails.
    self.dauth.side_effect = _Unanswered("no answer")
    # Three questions: one read, two answers from its memory.
    for _ in range(3):
      # Each gets the error.
      with self.assertRaises(_Unanswered):
        # One question.
        self.engine.web3_get_dauth_oracles()
    # One line for the three of them. Before, a failed read wrote none.
    self.assertEqual(self.engine.P.call_count, 1)
    # The line's text.
    line = self.engine.P.call_args.args[0]
    # What its reader needs: which registry, on which network, for how long it is not read, and why.
    for part in ("getDAuthOracles", "devnet", "60 s", "_Unanswered('no answer')"):
      # Each is in the line.
      self.assertIn(part, line)
    # The 60 s are over, and the next read fails with a text of 1000 characters.
    self.clock.return_value, self.dauth.side_effect = 100 + FAILURE_TTL, _Unanswered("x" * 1000)
    # The question that makes that read.
    with self.assertRaises(_Unanswered):
      # The second failed read.
      self.engine.web3_get_dauth_oracles()
    # One more line.
    self.assertEqual(self.engine.P.call_count, 2)
    # The error's text is what follows the line's last ": ".
    shown = self.engine.P.call_args.args[0].rpartition(": ")[2]
    # Cut to 400 characters: the class name, the opening bracket and quote, and the start of the text.
    self.assertEqual(shown, ("_Unanswered('" + "x" * 1000)[:400])

  def test_the_error_answered_from_the_memory_does_not_grow_with_the_questions(self):
    """The error a question gets from the memory of a failed read arrives with a traceback of the same length
    however many questions were answered with it before."""
    # The dAuth registry's read fails.
    self.dauth.side_effect = _Unanswered("no answer")
    # The question that makes the read.
    with self.assertRaises(_Unanswered):
      # The read that fails.
      self.engine.web3_get_dauth_oracles()
    # Five more questions, each answered from the memory: the length of the traceback each one's error has.
    lengths = [_traceback_entries(self.engine.web3_get_dauth_oracles) for _ in range(5)]
    # No read was made for them. Before, each made the read again.
    self.assertEqual(self.dauth.call_count, 1)
    # Each got an error.
    self.assertGreater(lengths[0], 0)
    # The fifth is as long as the first: the frames of earlier questions are not kept in the error object.
    self.assertEqual(lengths, lengths[:1] * 5)

  def test_an_interrupted_read_is_not_remembered_and_the_error_of_the_next_one_is(self):
    """A read ended by an interrupt of the program (Ctrl-C in an interactive session), which is no error of the
    read, is not remembered: the next question makes the read, and the error of that read is remembered."""
    # The read is interrupted.
    self.dauth.side_effect = KeyboardInterrupt()
    # The interrupt reaches the caller.
    with self.assertRaises(KeyboardInterrupt):
      # The interrupted read.
      self.engine.web3_get_dauth_oracles()
    # From now on the read fails with an error.
    self.dauth.side_effect = _Unanswered("no answer")
    # The next question is not answered with the interrupt: it makes the read and gets that read's error.
    with self.assertRaises(_Unanswered):
      # The second read.
      self.engine.web3_get_dauth_oracles()
    # That error is remembered.
    with self.assertRaises(_Unanswered):
      # Answered from the memory.
      self.engine.web3_get_dauth_oracles()
    # Two reads: the interrupted one and the failed one. Before, the third question made a third read.
    self.assertEqual(self.dauth.call_count, 2)


if __name__ == "__main__":
  unittest.main()
