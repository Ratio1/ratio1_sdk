import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from eth_account import Account
from eth_utils import keccak
from web3 import Web3
from web3.exceptions import TransactionNotFound, Web3RPCError

from ratio1.bc.evm import _EVMMixin


class _Engine(_EVMMixin):
  pass


class PreparedNodeUpdateTests(unittest.TestCase):
  def setUp(self):
    self.engine = _Engine()
    self.account = Account.create()
    self.engine.eth_address = self.account.address
    self.engine._get_eth_account = mock.Mock(return_value=self.account)
    self.engine.P = mock.Mock()
    self.eth = mock.Mock()
    self.eth.account = Account
    self.eth.chain_id = 12345
    self.eth.gas_price = 10
    self.eth.get_balance.return_value = 10 ** 18
    self.eth.get_transaction_count.return_value = 4
    self.tx_fn = self.eth.contract.return_value.functions.submitNodeUpdate.return_value
    self.tx_fn.build_transaction.side_effect = lambda fields: {
      **fields, "to": "0x" + "11" * 20, "data": "0x1234", "value": 0,
    }
    self.eth.send_raw_transaction.side_effect = lambda raw: keccak(raw)
    self.engine._get_web3_vars = mock.Mock(return_value=SimpleNamespace(
      w3=SimpleNamespace(eth=self.eth), network="devnet", rpc_url="offline",
      poai_manager_address="0x" + "11" * 20,
    ))

  def prepare(self):
    return self.engine.web3_prepare_node_update(7, ["0x" + "22" * 20], network="devnet")

  def test_prepare_signs_without_broadcast_and_descriptor_survives_json(self):
    descriptor = json.loads(json.dumps(self.prepare()))
    self.eth.send_raw_transaction.assert_not_called()
    raw = Web3.to_bytes(hexstr=descriptor["raw_transaction"])
    self.assertEqual(Account.recover_transaction(raw), self.account.address)
    self.assertEqual(descriptor["transaction_hash"], Web3.to_hex(keccak(raw)))
    self.assertEqual(descriptor["chain_id"], 12345)
    self.assertEqual(descriptor["nonce"], 4)
    self.assertEqual(descriptor["network"], "devnet")
    self.assertNotIn(self.account.key.hex(), json.dumps(descriptor))
    self.eth.get_transaction_count.assert_called_once_with(self.account.address, "pending")
    self.engine._get_web3_vars.assert_called_once_with("devnet", request_timeout=30)
    self.engine.P.assert_not_called()

  def test_broadcast_reuses_exact_bytes_after_serialization(self):
    descriptor = json.loads(json.dumps(self.prepare()))
    self.eth.get_transaction_count.reset_mock()
    for _ in range(2):
      result = self.engine.web3_send_prepared_transaction(descriptor["raw_transaction"], network="devnet")
      self.assertEqual(result, descriptor["transaction_hash"])
    expected_bytes = Web3.to_bytes(hexstr=descriptor["raw_transaction"])
    self.assertEqual(self.eth.send_raw_transaction.call_args_list,
                     [mock.call(expected_bytes), mock.call(expected_bytes)])
    self.eth.get_transaction_count.assert_not_called()

  def test_known_transaction_returns_persisted_hash_but_other_rpc_errors_propagate(self):
    descriptor = self.prepare()
    self.eth.send_raw_transaction.side_effect = Web3RPCError("already known")
    self.assertEqual(self.engine.web3_send_prepared_transaction(descriptor["raw_transaction"]),
                     descriptor["transaction_hash"])
    self.eth.send_raw_transaction.side_effect = Web3RPCError("nonce too low")
    with self.assertRaises(Web3RPCError):
      self.engine.web3_send_prepared_transaction(descriptor["raw_transaction"])

  def test_broadcast_rejects_wrong_rpc_hash(self):
    descriptor = self.prepare()
    self.eth.send_raw_transaction.side_effect = None
    self.eth.send_raw_transaction.return_value = bytes(32)
    with self.assertRaisesRegex(ValueError, "does not match"):
      self.engine.web3_send_prepared_transaction(descriptor["raw_transaction"])

  def test_receipt_distinguishes_pending_success_and_mined_failure(self):
    tx_hash = self.prepare()["transaction_hash"]
    self.eth.get_transaction_receipt.side_effect = TransactionNotFound("pending")
    self.assertIsNone(self.engine.web3_get_transaction_receipt(tx_hash))
    self.eth.get_transaction_receipt.side_effect = None
    for status in (0, 1):
      self.eth.get_transaction_receipt.return_value = {
        "transactionHash": Web3.to_bytes(hexstr=tx_hash), "status": status, "blockNumber": 100,
      }
      self.assertEqual(self.engine.web3_get_transaction_receipt(tx_hash), {
        "transaction_hash": tx_hash, "status": status, "block_number": 100,
      })

  def test_receipt_transport_error_is_not_pending(self):
    tx_hash = self.prepare()["transaction_hash"]
    self.eth.get_transaction_receipt.side_effect = TimeoutError("offline timeout")
    with self.assertRaises(TimeoutError):
      self.engine.web3_get_transaction_receipt(tx_hash)

  def test_receipt_rejects_wrong_hash_and_missing_status(self):
    tx_hash = self.prepare()["transaction_hash"]
    for receipt in (
      {"transactionHash": bytes(32), "status": 1, "blockNumber": 100},
      {"transactionHash": Web3.to_bytes(hexstr=tx_hash), "blockNumber": 100},
    ):
      self.eth.get_transaction_receipt.return_value = receipt
      with self.assertRaises(ValueError):
        self.engine.web3_get_transaction_receipt(tx_hash)

  def test_rpc_provider_receives_explicit_timeout(self):
    self.engine.log = SimpleNamespace(str_to_date=lambda value: datetime(2020, 1, 1))
    with mock.patch("ratio1.bc.evm.Web3") as web3_class:
      _EVMMixin._get_web3_vars(self.engine, "devnet", request_timeout=9)
    self.assertEqual(web3_class.HTTPProvider.call_args.kwargs,
                     {"request_kwargs": {"timeout": 9}})

  def test_invalid_prepared_input_never_calls_rpc(self):
    self.engine._get_web3_vars.reset_mock()
    for raw in (None, "", "0x", "not-hex"):
      with self.subTest(raw=raw):
        with self.assertRaises(ValueError):
          self.engine.web3_send_prepared_transaction(raw)
    self.engine._get_web3_vars.assert_not_called()

  def test_existing_submit_uses_pending_nonce_and_preserves_receipt_behavior(self):
    receipt = SimpleNamespace(transactionHash=bytes.fromhex("ab" * 32), status=1)
    self.eth.wait_for_transaction_receipt.return_value = receipt
    result = self.engine.web3_submit_node_update(7, [], wait_for_tx=True, return_receipt=True, timeout=9)
    self.assertIs(result, receipt)
    self.eth.get_transaction_count.assert_called_once_with(self.account.address, "pending")
    self.assertEqual(self.eth.wait_for_transaction_receipt.call_args.kwargs, {"timeout": 9})


if __name__ == "__main__":
  unittest.main()
