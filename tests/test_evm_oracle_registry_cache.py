"""Offline checks for shared registry freshness, isolation and concurrency."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ratio1.bc import evm


ORACLE = "0x000000000000000000000000000000000000dEaD"
OTHER = "0x0000000000000000000000000000000000000001"


class OracleRegistryCacheTests(unittest.TestCase):
  def setUp(self):
    self.cache = patch.dict(evm._ORACLE_REGISTRY_CACHE, clear=True)
    self.cache.start()
    self.addCleanup(self.cache.stop)
    self.clock = patch.object(evm, "monotonic", return_value=100).start()
    self.addCleanup(patch.stopall)
    self.web3 = patch.object(evm, "Web3").start()
    self.w3 = Mock()
    self.contract = self.w3.eth.contract.return_value
    self.oracles = self.contract.functions.getOracles.return_value.call
    self.dauth = self.contract.functions.getDAuthOracles.return_value.call
    self.oracles.return_value = [ORACLE]
    self.dauth.return_value = [ORACLE]
    self.engine = evm._EVMMixin()
    self.vars = SimpleNamespace(
      network="devnet", rpc_url="https://rpc.invalid", w3=self.w3,
      controller_contract_address=OTHER, dauth_oracle_registry_address=ORACLE,
    )
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
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE))
    self.clock.return_value = 699
    self.assertTrue(self.engine.web3_is_dauth_oracle(ORACLE.lower()))
    self.dauth.assert_called_once()
    self.clock.return_value = 700
    self.dauth.side_effect = RuntimeError("RPC unavailable")
    with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
      self.engine.web3_is_dauth_oracle(ORACLE)
    self.dauth.side_effect = None
    self.dauth.return_value = []
    self.assertFalse(self.engine.web3_is_dauth_oracle(ORACLE))
    self.assertEqual(self.engine.web3_get_dauth_oracles(), [])
    self.assertEqual(self.dauth.call_count, 3)
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
    self.oracles.side_effect = RuntimeError("RPC unavailable")
    with self.assertRaisesRegex(RuntimeError, "RPC unavailable"):
      self.engine.web3_get_oracles()
    self.oracles.side_effect = None
    self.assertEqual(self.engine.web3_get_oracles(), [ORACLE])
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


if __name__ == "__main__":
  unittest.main()
