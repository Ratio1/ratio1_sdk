import unittest
from types import SimpleNamespace
from unittest import mock

from web3 import Web3

from ratio1.bc.evm import _EVMMixin


class _DummyEngine(_EVMMixin):
  def __init__(self):
    self.messages = []

  def P(self, message, **kwargs):
    self.messages.append(message)


class TestCspEscrowOwnerTransferEvent(unittest.TestCase):

  def setUp(self):
    self.engine = _DummyEngine()
    self.manager = Web3.to_checksum_address("0x" + "11" * 20)
    self.escrow = Web3.to_checksum_address("0x" + "22" * 20)
    self.old_owner = Web3.to_checksum_address("0x" + "33" * 20)
    self.new_owner = Web3.to_checksum_address("0x" + "44" * 20)
    self.contract = mock.Mock()
    self.web3 = mock.Mock()
    self.web3.eth.contract.return_value = self.contract
    self.web3.eth.get_transaction_receipt.return_value = {
      "status": 1,
      "blockNumber": 123,
    }
    self.web3_vars = SimpleNamespace(
      w3=self.web3,
      rpc_url="http://rpc.local",
      network="devnet",
      poai_manager_address=self.manager,
    )
    self.engine._get_web3_vars = mock.Mock(return_value=self.web3_vars)
    self.contract.functions.escrowToOwner.return_value.call.return_value = self.new_owner

  def _event(self, log_index=7, address=None):
    return {
      "address": address or self.manager,
      "logIndex": log_index,
      "args": {
        "escrow": self.escrow,
        "oldOwner": self.old_owner,
        "newOwner": self.new_owner,
      },
    }

  def _set_events(self, events):
    event_filter = mock.Mock()
    event_filter.process_receipt.return_value = events
    self.contract.events.CspEscrowOwnerTransferred.return_value = event_filter

  def test_resolves_valid_transfer_event_and_confirms_current_owner(self):
    self._set_events([self._event()])

    result = self.engine.web3_get_csp_escrow_owner_transfer_from_tx("0xabc")

    self.assertEqual(result["network"], "devnet")
    self.assertEqual(result["tx_hash"], "0xabc")
    self.assertEqual(result["log_index"], 7)
    self.assertEqual(result["block_number"], 123)
    self.assertEqual(result["escrow"], self.escrow)
    self.assertEqual(result["old_owner"], self.old_owner)
    self.assertEqual(result["new_owner"], self.new_owner)
    self.contract.functions.escrowToOwner.assert_called_once_with(self.escrow)

  def test_requires_log_index_when_transaction_has_multiple_transfer_events(self):
    self._set_events([self._event(log_index=7), self._event(log_index=8)])

    with self.assertRaisesRegex(ValueError, "Multiple"):
      self.engine.web3_get_csp_escrow_owner_transfer_from_tx("0xabc")

  def test_uses_requested_log_index(self):
    self._set_events([self._event(log_index=7), self._event(log_index=8)])

    result = self.engine.web3_get_csp_escrow_owner_transfer_from_tx("0xabc", log_index=8)

    self.assertEqual(result["log_index"], 8)

  def test_rejects_failed_transaction_receipt(self):
    self.web3.eth.get_transaction_receipt.return_value = {"status": 0}
    self._set_events([self._event()])

    with self.assertRaisesRegex(ValueError, "did not succeed"):
      self.engine.web3_get_csp_escrow_owner_transfer_from_tx("0xabc")

  def test_rejects_transfer_event_when_current_owner_no_longer_matches(self):
    self.contract.functions.escrowToOwner.return_value.call.return_value = self.old_owner
    self._set_events([self._event()])

    with self.assertRaisesRegex(ValueError, "currently owned"):
      self.engine.web3_get_csp_escrow_owner_transfer_from_tx("0xabc")


if __name__ == "__main__":
  unittest.main()
