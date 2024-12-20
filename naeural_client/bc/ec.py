import base64
import hashlib
import os
import binascii
import zlib
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from web3 import Web3
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from eth_account.messages import encode_defunct

from .base import BaseBlockEngine, VerifyMessage, BCct



class BaseBCEllipticCurveEngine(BaseBlockEngine):
  MAX_ADDRESS_VALUE = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
  
  
  def _get_pk(self, private_key : ec.EllipticCurvePrivateKey) -> ec.EllipticCurvePublicKey:
    """
    Simple wrapper to generate pk from sk


    Returns
    -------
    public_key : EllipticCurvePublicKey
    
    """
    return super(BaseBCEllipticCurveEngine, self)._get_pk(private_key)

  
  def _sk_to_text(
      self, 
      private_key :  ec.EllipticCurvePrivateKey, 
      password=None, 
      fn=None
    ):
    """
    Serialize a EllipticCurvePrivateKey as text

    Parameters
    ----------
    private_key : EllipticCurvePrivateKey
      the secret key object.
      
    password: str
      password to be used for sk serialization
      
    fn: str:
      text file where to save the pk

    Returns
    -------
      the sk as text string

    """
    return super(BaseBCEllipticCurveEngine, self)._sk_to_text(
      private_key=private_key, 
      password=password, 
      fn=fn
    ) 
  
  #############################################################################
  ##
  ##          MANDATORY DEFINITIONS:
  ##
  #############################################################################

  def _create_new_sk(self) -> ec.EllipticCurvePrivateKey:
    """
    Simple wrapper to generated pk


    Returns
    -------
    private_key : EllipticCurvePrivateKey
    
    """
    private_key = ec.generate_private_key(curve=ec.SECP256K1())
    return private_key

  def _create_new_sk_from_words(self, words: list[str]) -> ec.EllipticCurvePrivateKey:
      """
      Simple wrapper to generate pk using a seed

      Parameters
      ----------
      words : list[str]
          The words to be used as seed.

      Returns
      -------
      private_key : EllipticCurvePrivateKey
      """
      
      seedString = ';'.join(words)
      
      encodedString = seedString.encode()
      
      # Hash the seed to ensure it has enough entropy
      digest = hashlib.sha256(encodedString).digest()
      
      # Convert the hash to an integer
      private_value = int.from_bytes(digest, 'big')
      
      # Ensure the integer is within the valid range for the curve
      private_value = private_value % self.MAX_ADDRESS_VALUE

      # Create the private key from the integer
      private_key = ec.derive_private_key(private_value, ec.SECP256K1(), default_backend())
      return private_key
  
  def _sign(
      self, 
      data : bytes, 
      private_key : ec.EllipticCurvePrivateKey, 
      text=False
    ):
    """
    Sign a binary message with Elliptic Curve
    

    Parameters
    ----------
    data : bytes
      the binary message.
      
    private_key : ec.EllipticCurvePrivateKey
      the private key object.
      
    text : bool, optional
      return the signature as text. The default is False.

    Returns
    -------
    signature as text or binary

    """
    signature = private_key.sign(
      data=data,
      signature_algorithm=ec.ECDSA(hashes.SHA256())
      )
    txt_signature = self._binary_to_text(signature)
    return txt_signature if text else signature
    
  def _verify(
      self, 
      public_key : ec.EllipticCurvePublicKey, 
      signature : bytes, 
      data : bytes
    ):
    """
    Verifies a `EllipticCurvePublicKey` signature on a binary `data` package
    

    Parameters
    ----------
    public_key : ec.EllipticCurvePublicKey
      the pk object.
      
    signature : bytes
      the binary signature.
      
    data : bytes
      the binary message.


    Returns
    -------
    result: VerifyMessage 
      contains `result.valid` and `result.message`

    """
    result = VerifyMessage()
    try:
      public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
      result.valid = True
      result.message = '<Signature OK>'
    except Exception as exp:
      err = str(exp)
      if len(err) == 0:
        err = exp.__class__.__name__
      result.message = err
      result.valid = False      
    return result    
  
  def _pk_to_address(self, public_key):
    """
    Given a EllipticCurvePublicKey object will return the simple text address


    Parameters
    ----------
    public_key : ec.EllipticCurvePublicKey
      the pk object.
      
    Returns
    -------
      text address      
    
    """
    data = public_key.public_bytes(
      encoding=serialization.Encoding.X962,
      format=serialization.PublicFormat.CompressedPoint,
    )
    txt = BCct.ADDR_PREFIX + self._binary_to_text(data)
    return txt


  def _address_to_pk(self, address):
    """
    Given a address will return the EllipticCurvePublicKey object


    Parameters
    ----------
    address : str
      the text address (pk).


    Returns
    -------
    pk : EllipticCurvePublicKey
      the pk object.

    """
    try:
      simple_address = self._remove_prefix(address)
      bpublic_key = self._text_to_binary(simple_address)
      public_key = ec.EllipticCurvePublicKey.from_encoded_point(
        curve=ec.SECP256K1(), 
        data=bpublic_key
      )
    except Exception as exp:
      self.P(f"Error converting address <{address}>to pk: {exp}", color='r')
      raise exp
    return public_key
  

  def __derive_shared_key(self, peer_public_key : str, info : str = BCct.DEFAULT_INFO, debug : bool = False):
    """
    Derives a shared key using own private key and peer's public key.

    Parameters
    ----------
    private_key : cryptography.hazmat.primitives.asymmetric.ec.EllipticCurvePrivateKey
        The private key to use for derivation.
    peer_public_key : cryptography.hazmat.primitives.asymmetric.ec.EllipticCurvePublicKey
        The peer's public key.
    
    Returns
    -------
    bytes
        The derived shared key.
    """
    if info is not None:
      info = info.encode()
    private_key = self.private_key
    shared_key = private_key.exchange(ec.ECDH(), peer_public_key)
    if debug:
      print('sk-pk-shared_key: ', binascii.hexlify(shared_key).decode('utf-8'))
    derived_key = HKDF(
      algorithm=hashes.SHA256(),
      length=32,
      salt=None,
      info=info,
      backend=default_backend()
    ).derive(shared_key)
    if debug:
      print('derived-shared_key: ', base64.b64encode(derived_key))
    return derived_key


  def _encrypt(
    self, 
    plaintext: str, 
    receiver_address: str, 
    compressed: bool = True, # compressed is always True
    embed_compressed: bool = True, # embed_compressed is always True
    info: str = BCct.DEFAULT_INFO, 
    debug: bool = False,
  ):
    """
    Encrypts plaintext using the sender's private key and receiver's public key, 
    then base64 encodes the output.

    Parameters
    ----------
    receiver_address : str
        The receiver's address
        
    plaintext : str
        The plaintext to encrypt.
        
    compressed : bool, optional
        Whether to compress the plaintext before encryption. The default is True.
        
    embed_compressed : bool, optional
        Whether to embed the compressed flag in the encrypted data. The default is True.

    Returns
    -------
    str
        The base64 encoded nonce and ciphertext.
    """
    
    if compressed:
      to_encrypt_data = zlib.compress(plaintext.encode())
      compressed_flag = (1).to_bytes(1, byteorder='big')
    else:
      to_encrypt_data = plaintext.encode()
      compressed_flag = (0).to_bytes(1, byteorder='big')
      
    receiver_pk = self._address_to_pk(receiver_address)
    shared_key = self.__derive_shared_key(receiver_pk, info=info, debug=debug)
    aesgcm = AESGCM(shared_key)
    nonce = os.urandom(12)  # Generate a unique nonce for each encryption
    ciphertext = aesgcm.encrypt(nonce, to_encrypt_data, None)
    if embed_compressed:
      encrypted_data = nonce + compressed_flag + ciphertext
    else:
      encrypted_data = nonce + ciphertext  # Prepend the nonce to the ciphertext
    #end if      
    return base64.b64encode(encrypted_data).decode()  # Encode to base64
  
    
  
  def _decrypt(
    self, 
    encrypted_data_b64 : str, 
    sender_address : str, 
    decompress: bool = False, # decompress is only used if embed_compressed is False
    embed_compressed: bool = True,
    info: str = BCct.DEFAULT_INFO, 
    debug: bool = False
  ):
    """
    Decrypts base64 encoded encrypted data using the receiver's private key.
    
    The structure of the encrypted data is:
    - 12 bytes nonce
    - 1 byte compressed flag 
    - 13:... The ciphertext

    Parameters
    ----------        
    encrypted_data_b64 : str
        The base64 encoded nonce and ciphertext.
        
    sender_address : str
        The sender's address.
        
    decompress : bool, optional
        Whether to decompress the plaintext after decryption. The default is False as the decompression flag is embedded in the encrypted data.
        
    embed_compressed : bool, optional
        Whether the compressed flag is embedded in the encrypted data. The default is True.
        
        
    Returns
    -------
    str
        The decrypted plaintext.

    """
    try:
        
      sender_pk = self._address_to_pk(sender_address)
      encrypted_data = base64.b64decode(encrypted_data_b64)  # Decode from base64
      nonce = encrypted_data[:12]  # Extract the nonce      

      if embed_compressed:
        start_data = 13
        compressed_flag_byte = encrypted_data[12:13]
        compressed_flag = int.from_bytes(compressed_flag_byte, byteorder='big')
      else:
        start_data = 12
        compressed_flag = None      

      ciphertext = encrypted_data[start_data:]  # The rest is the ciphertext
      shared_key = self.__derive_shared_key(sender_pk, info=info, debug=debug)
      aesgcm = AESGCM(shared_key)
      plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
      if (embed_compressed and compressed_flag) or (not embed_compressed and decompress):
        plaintext = zlib.decompress(plaintext)          
      
      result = plaintext.decode()
    except Exception as exc:
      if debug:
        self.P("Error decrypting from <{}> (compressed_flag `{}`): {}".format(
          sender_address, compressed_flag, exc), color='r'
        )
      result = None
    return result
  

  ## Multi destination encryption
  def encrypt_for_multi(
    self, 
    plaintext: str, 
    receiver_addresses: list, 
    info: str = BCct.DEFAULT_INFO, 
    debug: bool = False
  ):
    """
    Encrypts plaintext for multiple receivers.
    
    The overall approach is to encrypt the plaintext with a symmetric key, 
    then encrypt the symmetric key with the public key of each receiver.

    Parameters
    ----------
    plaintext : str
        The plaintext to encrypt.
        
    receiver_addresses : list
        List of receiver addresses.

    Returns
    -------
    str
        The base64 encoded encrypted package.
    """
    to_encrypt_data = zlib.compress(plaintext.encode())
    compressed_flag = (1).to_bytes(1, byteorder='big')
    
    # Generate a random symmetric key
    symmetric_key = os.urandom(32)  # 256-bit key
    
    # Encrypt the plaintext with the symmetric key
    nonce = os.urandom(12)
    aesgcm = AESGCM(symmetric_key)
    ciphertext = aesgcm.encrypt(nonce, to_encrypt_data, None)
    
    # For each receiver, encrypt the symmetric key
    encrypted_keys = []
    for receiver_address in receiver_addresses:
      receiver_pk = self._address_to_pk(receiver_address)
      shared_key = self.__derive_shared_key(receiver_pk, info=info, debug=debug)
      # Use shared_key to encrypt the symmetric key
      aesgcm_shared = AESGCM(shared_key)
      nonce_shared = os.urandom(12)
      encrypted_symmetric_key = aesgcm_shared.encrypt(nonce_shared, symmetric_key, None)
      full_enc_key = nonce_shared + encrypted_symmetric_key
      encrypted_keys.append({
        'a': receiver_address,  # Address of the receiver
        'k': full_enc_key.hex() # Encrypted symmetric key
      })
    
    # Package the encrypted symmetric keys and the ciphertext
    encrypted_package = {
      'M': True,                  # Multi-recipient flag
      'c': compressed_flag.hex(), # Compressed flag
      'n': nonce.hex(),           # Nonce
      'd': ciphertext.hex(),      # Ciphertext
      'k': encrypted_keys         # Encrypted symmetric keys
    }
    
    # Convert to JSON, compress, and base64 encode
    enc_data = json.dumps(encrypted_package)
    enc_data_compressed = zlib.compress(enc_data.encode())
    enc_data_compressed_b64 = base64.b64encode(enc_data_compressed).decode()
    return enc_data_compressed_b64


  def decrypt_for_multi(
      self,
      encrypted_data_b64: str,
      sender_address: str,
      info: str = BCct.DEFAULT_INFO,
      debug: bool = False
  ):
    """
    Decrypts data encrypted for multiple receivers.

    Parameters
    ----------
    encrypted_data_b64 : str
      The base64 encoded encrypted package as produced by encrypt_for_multi.
    
    sender_address : str
      The sender's address (public key address) used to derive the shared key.
    
    info : str, optional
      Additional info used in the HKDF for shared key derivation.
    
    debug : bool, optional
      If True, prints debug information.

    Returns
    -------
    str or None
      The decrypted plaintext as a string, or None if decryption fails.
    """
    try:
      # 1. Base64 decode
      enc_data_compressed = base64.b64decode(encrypted_data_b64)

      # 2. Decompress the JSON structure
      enc_data_json = zlib.decompress(enc_data_compressed).decode()

      # 3. Parse JSON
      encrypted_package = json.loads(enc_data_json)

      # Expecting keys: 'M', 'c', 'n', 'd', 'k'
      # 'M' = True indicates multi-recipient
      if 'M' not in encrypted_package or encrypted_package['M'] != True:
        if debug:
          self.P("Not a multi-recipient package.", color='y')
        return None

      # 'c' = compressed flag (hex)
      compressed_flag_hex = encrypted_package['c']
      compressed_flag = int(compressed_flag_hex, 16)

      # 'n' = nonce (hex)
      nonce = bytes.fromhex(encrypted_package['n'])

      # 'd' = ciphertext (hex)
      ciphertext = bytes.fromhex(encrypted_package['d'])

      # 'k' = list of encrypted symmetric keys
      encrypted_keys = encrypted_package['k']

      # 4. Identify this receiver's encrypted symmetric key
      my_address = self.address
      my_encrypted_key_hex = None
      for ek in encrypted_keys:
        if ek['a'] == my_address:
          my_encrypted_key_hex = ek['k']
          break

      if my_encrypted_key_hex is None:
        if debug:
          self.P("No encrypted symmetric key for this receiver.", color='r')
        return None

      # Decode the encrypted symmetric key
      my_encrypted_key = bytes.fromhex(my_encrypted_key_hex)

      # The first 12 bytes are nonce_shared, rest is encrypted symmetric key
      nonce_shared = my_encrypted_key[:12]
      encrypted_symmetric_key = my_encrypted_key[12:]

      # 5. Derive shared key using sender's public key
      sender_pk = self._address_to_pk(sender_address)
      shared_key = self.__derive_shared_key(sender_pk, info=info, debug=debug)

      # 6. Decrypt the symmetric key
      aesgcm_shared = AESGCM(shared_key)
      symmetric_key = aesgcm_shared.decrypt(nonce_shared, encrypted_symmetric_key, None)

      # 7. Decrypt the ciphertext using the symmetric key
      aesgcm = AESGCM(symmetric_key)
      plaintext = aesgcm.decrypt(nonce, ciphertext, None)

      # 8. Decompress the plaintext if compressed_flag == 1
      if compressed_flag == 1:
        plaintext = zlib.decompress(plaintext)

      return plaintext.decode()

    except Exception as exc:
      if debug:
        self.P(f"Error decrypting multi scenario: {exc}", color='r')
      return None


  def encrypt(
    self, 
    plaintext: str, 
    receiver_address: any, 
    info: str = BCct.DEFAULT_INFO, 
    debug: bool = False,
    **kwargs
  ):
    """
    Encrypts plaintext using the sender's private key and receiver's public key, 
    then base64 encodes the output.

    Parameters
    ----------
    plaintext : str
        The plaintext to encrypt.

    receiver_address : str or list[str]
        The receiver's address or list of multiple receivers addresses.
        
        
    Obsolete:          
      compressed : bool, optional
          Whether to compress the plaintext before encryption. The default is True.
          
      embed_compressed : bool, optional
          Whether to embed the compressed flag in the encrypted data. The default is True.

    Returns
    -------
    str
        The base64 encoded nonce and ciphertext.
    """  
    assert isinstance(receiver_address, (str, list)), "receiver_address must be a string or a list of strings."
    if isinstance(receiver_address, list):
      return self.encrypt_for_multi(
        plaintext=plaintext, 
        receiver_addresses=receiver_address, 
        info=info, 
        debug=debug
      )      
    return self._encrypt(
      plaintext=plaintext, 
      receiver_address=receiver_address, 
      compressed=True, 
      embed_compressed=True, 
      info=info, 
      debug=debug,      
    )


  def decrypt(  
    self,
    encrypted_data_b64: str,
    sender_address: str,
    info: str = BCct.DEFAULT_INFO,
    debug: bool = False,
    is_multi: bool = True
  ):
    """
    Decrypts data encrypted for a single or multi  receiver.

    Parameters
    ----------
    encrypted_data_b64 : str
      The base64 encoded encrypted data.
    
    sender_address : str
      The sender's address (public key address) used to derive the shared key.
    
    info : str, optional
      Additional info used in the HKDF for shared key derivation.
    
    debug : bool, optional
      If True, prints debug information.
    
    is_multi : bool, optional
      If True, decrypts as multi-recipient package.

    Returns
    -------
    str or None
      The decrypted plaintext as a string, or None if decryption fails.
    """
    result = None
    if is_multi:
      result = self.decrypt_for_multi(encrypted_data_b64, sender_address, info=info, debug=debug)
    if result is None:
      result = self._decrypt(encrypted_data_b64, sender_address, decompress=True, embed_compressed=True, info=info, debug=debug)  
    return result
  
  
  ## end multi destination encryption
  
  
  ### ETH

  def _get_eth_address(self, pk=None):
    if pk is None:
      pk = self.public_key
    raw_public_key = pk.public_numbers()

    # Compute Ethereum-compatible address
    x = raw_public_key.x.to_bytes(32, 'big')
    y = raw_public_key.y.to_bytes(32, 'big')
    uncompressed_key = b'\x04' + x + y
    keccak_hash = keccak(uncompressed_key[1:])  # Remove 0x04 prefix
    eth_address = "0x" + keccak_hash[-20:].hex()
    eth_address = to_checksum_address(eth_address)
    return eth_address    
  
  def _get_eth_account(self):
    private_key_bytes = self.private_key.private_numbers().private_value.to_bytes(32, 'big')
    return Account.from_key(private_key_bytes)
  
  
  def node_address_to_eth_address(self, address):
    """
    Converts a node address to an Ethereum address.

    Parameters
    ----------
    address : str
        The node address convert.

    Returns
    -------
    str
        The Ethereum address.
    """
    public_key = self._address_to_pk(address)
    return self._get_eth_address(pk=public_key)
    

  
  def eth_hash_message(self, types, values, as_hex=False):
    """
    Hashes a message using the keccak256 algorithm.

    Parameters
    ----------
    types : list
        The types of the values.
        
    values : list of any
        The values to hash.

    Returns
    -------
    bytes
        The hash of the message in hexadecimal format.
    """
    message = Web3.solidity_keccak(types, values)
    if as_hex:
      return message.hex()
    return message
  
  
  def eth_sign_message(self, types, values):
    """
    Signs a message using the private key.

    Parameters
    ----------
    types : list
        The types of the values.
        
    values : list of any
        The values to sign.

    Returns
    -------
    str
        The signature of the message.
    """
    message_hash = self.eth_hash_message(types, values, as_hex=False)
    signable_message = encode_defunct(primitive=message_hash)
    signed_message = Account.sign_message(signable_message, private_key=self.eth_account.key)
    if hasattr(signed_message, "message_hash"): # backward compatibility
      signed_message_hash = signed_message.message_hash
    else:
      signed_message_hash = signed_message.messageHash
    return {
        "message_hash": message_hash.hex(),
        "r": hex(signed_message.r),
        "s": hex(signed_message.s),
        "v": signed_message.v,
        "signature": signed_message.signature.hex(),
        "signed_message": signed_message_hash.hex(),
        "sender" : self.eth_address,
    }
    
  def eth_sign_text(self, message, signature_only=True):
    """
    Signs a text message using the private key.

    Parameters
    ----------
    message : str
        The message to sign.
        
    signature_only : bool, optional
        Whether to return only the signature. The default is True

    Returns
    -------
    str
        The signature of the message.
    """
    types = ["string"]
    values = [message]
    result = self.eth_sign_message(types, values)
    if signature_only:
      return result["signature"]
    return result
    
    
    
  def eth_sign_node_epochs(self, node, epochs, epochs_vals, signature_only=True):
    """
    Signs the node availability

    Parameters
    ----------
    node : str
        The node address.
        
    epochs : list of int
        The epochs to sign.
        
    epochs_vals : list of int
        The values for each epoch.
        
    signature_only : bool, optional
        Whether to return only the signature. The default is True.

    Returns
    -------
    str
        The signature of the message.
    """
    types = ["string", "uint256[]", "uint256[]"]
    values = [node, epochs, epochs_vals]
    result = self.eth_sign_message(types, values)
    if signature_only:
      return result["signature"]
    return result
  
  
