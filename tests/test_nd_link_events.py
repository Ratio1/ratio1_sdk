import unittest
from types import SimpleNamespace
from unittest import mock

from eth_abi import encode
from eth_utils import keccak
from hexbytes import HexBytes
from web3 import Web3

from ratio1.bc.evm import _EVMMixin


ND = Web3.to_checksum_address("0x" + "11" * 20)
OWNER = Web3.to_checksum_address("0x" + "22" * 20)
OLD_NODE = Web3.to_checksum_address("0x" + "33" * 20)
NEW_NODE = Web3.to_checksum_address("0x" + "44" * 20)


def _raw_log(signature, owner, license_id, node, block_number, log_index):
  return {
    "address": ND,
    "topics": [
      HexBytes(keccak(text=signature)),
      HexBytes(encode(["address"], [owner])),
      HexBytes(encode(["uint256"], [license_id])),
    ],
    "data": HexBytes(encode(["address"], [node])),
    "blockNumber": block_number,
    "logIndex": log_index,
    "transactionIndex": 0,
    "transactionHash": HexBytes("0x" + "aa" * 32),
    "blockHash": HexBytes("0x" + "bb" * 32),
  }


class _DummyEngine(_EVMMixin):
  def P(self, message, **kwargs):
    pass


class TestNdLinkEvents(unittest.TestCase):

  def setUp(self):
    self.engine = _DummyEngine()
    self.get_logs = mock.Mock()
    w3 = SimpleNamespace(eth=SimpleNamespace(
      contract=Web3().eth.contract,
      get_logs=self.get_logs,
      block_number=1234,
    ))
    self.engine._get_web3_vars = mock.Mock(return_value=SimpleNamespace(
      w3=w3, network="devnet", rpc_url="http://rpc.local", nd_contract_address=ND,
    ))

  def test_decodes_relink_events_in_chain_order_with_one_call(self):
    self.get_logs.return_value = [
      _raw_log("LinkNode(address,uint256,address)", OWNER, 7, NEW_NODE, 100, 5),
      _raw_log("UnlinkNode(address,uint256,address)", OWNER, 7, OLD_NODE, 100, 4),
    ]

    events = self.engine.web3_get_nd_link_events(90, 110)

    self.assertEqual(events, [
      {"event": "UnlinkNode", "license_id": 7, "owner": OWNER, "node_address": OLD_NODE,
       "block_number": 100, "log_index": 4},
      {"event": "LinkNode", "license_id": 7, "owner": OWNER, "node_address": NEW_NODE,
       "block_number": 100, "log_index": 5},
    ])
    self.get_logs.assert_called_once()
    params = self.get_logs.call_args.args[0]
    self.assertEqual(params["address"], ND)
    self.assertEqual((params["fromBlock"], params["toBlock"]), (90, 110))
    self.assertEqual(len(params["topics"][0]), 2)

  def test_returns_block_number(self):
    self.assertEqual(self.engine.web3_get_block_number(), 1234)


if __name__ == "__main__":
  unittest.main()
