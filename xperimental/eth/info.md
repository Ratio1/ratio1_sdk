```python

from eth_abi import encode
from eth_utils import keccak, to_bytes
from web3 import Web3

class AvailabilityDto:
    def __init__(self, epoch: int, availability: int):
        self.epoch = epoch
        self.availability = availability


class AvailabilitySigner:
    def __init__(self, private_key: str):
        self.private_key = private_key
        self.web3 = Web3()

    def encode_availability(self, availability: AvailabilityDto) -> bytes:
        """
        Encodes an availability object into ABI-compliant byte format.
        """
        return encode(['uint256', 'uint256'], [availability.epoch, availability.availability])

    def concatenate_availabilities(self, availabilities: list[AvailabilityDto]) -> bytes:
        """
        Concatenates the encoded availabilities into a single byte sequence.
        """
        encoded_bytes = [self.encode_availability(avail) for avail in availabilities]
        return b''.join(encoded_bytes)

    def hash_message(self, address: str, license_id: int, node_hash: str, concatenated_bytes: bytes) -> bytes:
        """
        Hashes the provided inputs using Keccak256.
        """
        # Solidity's address type is 20 bytes; ensure it is converted correctly
        address_bytes = self.web3.toBytes(hexstr=address)
        license_id_bytes = encode(['uint256'], [license_id])
        node_hash_bytes = node_hash.encode('utf-8')
        
        packed_data = address_bytes + license_id_bytes + node_hash_bytes + concatenated_bytes
        return keccak(packed_data)

    def sign_availabilities(self, address: str, license_id: int, node_hash: str, availabilities: list[AvailabilityDto]) -> str:
        """
        Signs the hashed message using the private key.
        """
        concatenated_bytes = self.concatenate_availabilities(availabilities)
        message_hash = self.hash_message(address, license_id, node_hash, concatenated_bytes)
        signature = self.web3.eth.account.sign_message(to_bytes(message_hash), private_key=self.private_key)
        return signature.signature.hex()


# Example Usage
if __name__ == "__main__":
    private_key = "YOUR_PRIVATE_KEY_HERE"  # Replace with your private key
    signer = AvailabilitySigner(private_key)

    address = "0x1234567890abcdef1234567890abcdef12345678"  # Example address
    license_id = 42
    node_hash = "node-hash-example"

    availabilities = [
        AvailabilityDto(epoch=1, availability=100),
        AvailabilityDto(epoch=2, availability=200),
    ]

    signed_message = signer.sign_availabilities(address, license_id, node_hash, availabilities)
    print("Signed Message:", signed_message)
```


```python

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from eth_hash.auto import keccak  # Install with `pip install eth-hash`
import binascii
import json

def generate_keys():
    # Generate private and public keys
    sk = ec.generate_private_key(curve=ec.SECP256K1())
    pk = sk.public_key()
    raw_public_key = pk.public_numbers()

    # Compute Ethereum-compatible address
    x = raw_public_key.x.to_bytes(32, 'big')
    y = raw_public_key.y.to_bytes(32, 'big')
    uncompressed_key = b'\x04' + x + y
    keccak_hash = keccak(uncompressed_key[1:])  # Remove 0x04 prefix
    eth_address = "0x" + keccak_hash[-20:].hex()

    return sk, eth_address

def sign_message(sk, message):
    # Prepare Ethereum-specific message hash
    message_json = json.dumps(message, separators=(',', ':'))  # Serialize array as compact JSON
    message_bytes = message_json.encode()
    prefixed_message = b"\x19Ethereum Signed Message:\n" + str(len(message_bytes)).encode() + message_bytes
    hashed_message = keccak(prefixed_message)

    # Sign the hashed message
    signature = sk.sign(hashed_message, ec.ECDSA(hashes.SHA256()))
    r, s = ec.utils.decode_dss_signature(signature)

    # Compute Ethereum-specific v value
    v = 27 + ((sk.public_key().public_numbers().y & 1) ^ (r > (1 << 255)))

    return (r, s, v), hashed_message

def verify_signature(eth_address, message, signature):
    r, s, v = signature

    # Prepare the hashed message
    message_json = json.dumps(message, separators=(',', ':'))
    message_bytes = message_json.encode()
    prefixed_message = b"\x19Ethereum Signed Message:\n" + str(len(message_bytes)).encode() + message_bytes
    hashed_message = keccak(prefixed_message)

    # Reconstruct public key from signature
    from eth_keys import keys  # Install with `pip install eth-keys`
    from eth_utils import decode_hex  # Install with `pip install eth-utils`

    signature_bytes = r.to_bytes(32, 'big') + s.to_bytes(32, 'big') + bytes([v - 27])
    public_key = keys.ecdsa_recover(hashed_message, keys.Signature(signature_bytes))

    # Compute Ethereum address from recovered public key
    recovered_address = "0x" + keccak(public_key.to_bytes()[1:])[-20:].hex()

    return eth_address.lower() == recovered_address.lower()

# Example Usage
if __name__ == "__main__":
    # Generate keys and Ethereum address
    sk, eth_address = generate_keys()
    print("Generated Ethereum Address:", eth_address)

    # Sign a message
    message = ["value1", "value2", "value3"]
    signature, hashed_message = sign_message(sk, message)
    print("Signature (r, s, v):", signature)

    # Verify the signature
    is_valid = verify_signature(eth_address, message, signature)
    print("Is signature valid?", is_valid)
```

