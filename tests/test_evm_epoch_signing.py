import unittest
from unittest import mock

from ratio1.bc.evm import _EVMMixin
from ratio1.const.base import ETHVarTypes


class _DummyEngine(_EVMMixin):
  pass


class TestEthNodeEpochSigning(unittest.TestCase):

  def setUp(self):
    self.engine = _DummyEngine()

  def test_eth_sign_node_epochs_signs_contiguous_packed_range(self):
    self.engine.eth_sign_message = mock.Mock(
      return_value={
        "signature": "0x" + "11" * 65,
        "eth_signed_data": [
          ETHVarTypes.ETH_ADDR,
          ETHVarTypes.ETH_INT,
          ETHVarTypes.ETH_INT,
          ETHVarTypes.ETH_BYTES,
        ],
      }
    )

    result = self.engine.eth_sign_node_epochs(
      node="0x000000000000000000000000000000000000dEaD",
      epochs=[245, 246, 247],
      epochs_vals=[1, 2, 255],
      signature_only=False,
    )

    self.assertEqual(result["from_epoch"], 245)
    self.assertEqual(result["to_epoch"], 247)
    self.assertEqual(result["packed_availabilities"], "0x0102ff")
    self.engine.eth_sign_message.assert_called_once_with(
      [
        ETHVarTypes.ETH_ADDR,
        ETHVarTypes.ETH_INT,
        ETHVarTypes.ETH_INT,
        ETHVarTypes.ETH_BYTES,
      ],
      ["0x000000000000000000000000000000000000dEaD", 245, 247, "0x0102ff"],
    )

  def test_eth_sign_node_epochs_rejects_gapped_epochs(self):
    with self.assertRaisesRegex(ValueError, "contiguous"):
      self.engine.eth_sign_node_epochs(
        node="0x000000000000000000000000000000000000dEaD",
        epochs=[245, 247, 248],
        epochs_vals=[1, 2, 3],
      )

  def test_eth_sign_node_epochs_rejects_unsorted_epochs(self):
    with self.assertRaisesRegex(ValueError, "contiguous"):
      self.engine.eth_sign_node_epochs(
        node="0x000000000000000000000000000000000000dEaD",
        epochs=[246, 245, 247],
        epochs_vals=[1, 2, 3],
      )

  def test_eth_sign_node_epochs_rejects_mismatched_epoch_values(self):
    with self.assertRaisesRegex(ValueError, "same length"):
      self.engine.eth_sign_node_epochs(
        node="0x000000000000000000000000000000000000dEaD",
        epochs=[245, 246, 247],
        epochs_vals=[1, 2],
      )

  def test_eth_sign_node_epochs_rejects_invalid_availability_byte(self):
    with self.assertRaisesRegex(ValueError, "Invalid epoch availability"):
      self.engine.eth_sign_node_epochs(
        node="0x000000000000000000000000000000000000dEaD",
        epochs=[245, 246, 247],
        epochs_vals=[1, 256, 3],
      )


if __name__ == "__main__":
  unittest.main()
