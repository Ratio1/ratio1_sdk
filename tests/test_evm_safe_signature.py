import unittest
from unittest import mock

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak
from web3 import Web3

from ratio1.bc.evm import _EVMMixin
from ratio1.const.base import BCctbase


class _DummyEngine(_EVMMixin):
  def __init__(self):
    self.web3 = mock.Mock()
    self.messages = []

  def P(self, message, **kwargs):
    self.messages.append(message)


class TestEthSafeSignatureVerification(unittest.TestCase):

  def setUp(self):
    self.engine = _DummyEngine()

  def test_eth_verify_message_signature_recovers_eoa(self):
    private_key = "0x" + "1" * 64
    message = "hello-world"
    signed = Account.sign_message(
      encode_defunct(primitive=message.encode("utf-8")),
      private_key=private_key,
    )
    signature = signed.signature.hex()
    if not signature.startswith("0x"):
      signature = "0x" + signature

    recovered = self.engine.eth_verify_message_signature(
      values=[message],
      types=["string"],
      signature=signature,
      no_hash=True,
    )

    self.assertEqual(recovered.lower(), Account.from_key(private_key).address.lower())

  def test_eth_verify_message_signature_uses_safe_fallback_on_recover_error(self):
    safe_address = "0x" + "ab" * 20
    message = "safe-signature-message"
    signature = "0x" + "11" * 65

    contract = mock.Mock()
    self.engine.web3.eth.contract.return_value = contract
    contract.functions.isValidSignature.return_value.call.return_value = b"\x16\x26\xba\x7e"

    with mock.patch("ratio1.bc.evm.Account.recover_message", side_effect=Exception("recover failed")):
      recovered = self.engine.eth_verify_message_signature(
        values=[message],
        types=["string"],
        signature=signature,
        expected_signer=safe_address,
        no_hash=True,
      )

    expected_hash = keccak(
      b"\x19Ethereum Signed Message:\n"
      + str(len(message.encode("utf-8"))).encode("utf-8")
      + message.encode("utf-8")
    )
    expected_sig_bytes = bytes.fromhex(signature[2:])

    self.assertEqual(recovered, Web3.to_checksum_address(safe_address))
    self.engine.web3.eth.contract.assert_called_once_with(
      address=Web3.to_checksum_address(safe_address),
      abi=self.engine._SAFE_SIGNATURE_ABI,
    )
    contract.functions.isValidSignature.assert_called_once_with(expected_hash, expected_sig_bytes)

  def test_eth_verify_message_signature_uses_safe_fallback_on_recovered_mismatch(self):
    private_key = "0x" + "2" * 64
    message = "safe-mismatch"
    signature = Account.sign_message(
      encode_defunct(primitive=message.encode("utf-8")),
      private_key=private_key,
    ).signature.hex()
    if not signature.startswith("0x"):
      signature = "0x" + signature
    safe_address = "0x" + "cd" * 20

    with mock.patch.object(self.engine, "_eth_verify_safe_signature", return_value=True) as safe_check:
      recovered = self.engine.eth_verify_message_signature(
        values=[message],
        types=["string"],
        signature=signature,
        expected_signer=safe_address,
        no_hash=True,
      )

    self.assertEqual(recovered, Web3.to_checksum_address(safe_address))
    safe_check.assert_called_once()

  def test_eth_verify_message_signature_returns_none_when_safe_fallback_fails(self):
    private_key = "0x" + "3" * 64
    message = "safe-fail"
    signature = Account.sign_message(
      encode_defunct(primitive=message.encode("utf-8")),
      private_key=private_key,
    ).signature.hex()
    if not signature.startswith("0x"):
      signature = "0x" + signature
    safe_address = "0x" + "ef" * 20

    with mock.patch.object(self.engine, "_eth_verify_safe_signature", return_value=False):
      recovered = self.engine.eth_verify_message_signature(
        values=[message],
        types=["string"],
        signature=signature,
        expected_signer=safe_address,
        no_hash=True,
      )

    self.assertIsNone(recovered)

  def test_eth_verify_payload_signature_default_does_not_pass_expected_signer(self):
    self.engine.safe_dict_to_json = lambda payload, indent=0: "payload-json"
    self.engine.is_valid_eth_address = lambda address: True
    payload = {
      BCctbase.ETH_SENDER: "0x" + "ab" * 20,
      BCctbase.ETH_SIGN: "0x" + "11" * 65,
      "k": "v",
    }

    with mock.patch.object(self.engine, "eth_verify_text_signature", return_value=payload[BCctbase.ETH_SENDER]) as verify_text:
      result = self.engine.eth_verify_payload_signature(payload=payload, no_hash=True)

    self.assertEqual(result, payload[BCctbase.ETH_SENDER])
    self.assertIsNone(verify_text.call_args.kwargs["expected_signer"])

  def test_eth_verify_payload_signature_verify_safe_passes_expected_signer(self):
    self.engine.safe_dict_to_json = lambda payload, indent=0: "payload-json"
    self.engine.is_valid_eth_address = lambda address: True
    payload = {
      BCctbase.ETH_SENDER: "0x" + "cd" * 20,
      BCctbase.ETH_SIGN: "0x" + "22" * 65,
      "k": "v",
    }

    with mock.patch.object(self.engine, "eth_verify_text_signature", return_value=payload[BCctbase.ETH_SENDER]) as verify_text:
      result = self.engine.eth_verify_payload_signature(
        payload=payload,
        no_hash=True,
        verify_safe=True,
      )

    self.assertEqual(result, payload[BCctbase.ETH_SENDER])
    self.assertEqual(
      verify_text.call_args.kwargs["expected_signer"].lower(),
      payload[BCctbase.ETH_SENDER].lower(),
    )


if __name__ == "__main__":
  unittest.main()
