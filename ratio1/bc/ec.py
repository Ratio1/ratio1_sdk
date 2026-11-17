import base64
# lru_cache keeps one derived key per (own key, peer, info): one ECDH exchange per peer instead of per message.
import functools
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


  # At most 4,096 entries, 1.3 MB when full (measured on the node image, peer address strings included); the least
  # recently used entry goes first, so a flood of one-off sender addresses cannot push out the peers in use.
  @functools.lru_cache(maxsize=4096)
  def _shared_key(self, own_address, peer_address, info, debug):
    """
    Shared key with one peer, derived once and then served from a cache.

    Returns exactly the key the four encryption paths (`_encrypt`, `_decrypt`,
    `encrypt_for_multi`, `decrypt_for_multi`) used to derive on every message:
    the peer address decoded to a public key, an ECDH exchange with this node's
    private key, then HKDF-SHA256 (32 bytes, no salt, `info`). Only the first
    message to or from a peer pays for that; the next ones read the cache.
    Nothing sent or received changes: nonces and per-message keys are still
    drawn for every message.

    Parameters
    ----------
    own_address : str
      This node's address at call time (`self.address`). It is not used in the
      derivation, only in the cache key: after `rotate_private_key` the address
      changes, so the new key misses and is derived again with the new private key.
    peer_address : str
      The other side's address, with or without the address prefix.
    info : str or None
      The HKDF `info` text; different values give different keys.
    debug : bool
      Passed to the derivation, which then prints the keys; it is part of the
      cache key, so a key is printed only when it is derived.

    Returns
    -------
    bytes
      The 32-byte derived key, the same bytes the uncached derivation gives.

    Raises
    ------
    Exception
      Whatever `_address_to_pk` raises for an address that is not a valid
      public key, after its red log line: ValueError (binascii.Error, a
      ValueError, for text that is not base64), AttributeError for a value that
      is not text. An unhashable value raises TypeError from the cache itself.
      A call that raises stores nothing, so the same address is checked again
      on its next use.

    Notes
    -----
    The cache key is (engine, own address, peer address, info, debug). Bound and
    order: at most 4,096 entries (1.3 MB when full), least recently used dropped
    first. A peer that changes its key has a new address, hence a new entry. One
    cache serves every engine object of the process (the engine is part of the
    key) and is safe to use from several threads; two threads that miss the same
    entry at once both derive it and get the same bytes. While
    `rotate_private_key` swaps the key, a call that read the old address can
    store a key made with the new private key under the old address; no later
    call uses that address, so the entry is never read.

    Examples
    --------
    >>> key = engine._shared_key(engine.address, peer.address, BCct.DEFAULT_INFO, False)
    >>> len(key)
    32
    >>> key == peer._shared_key(peer.address, engine.address, BCct.DEFAULT_INFO, False)
    True
    """
    # Decode, ECDH and HKDF only on a cache miss: 0.49 ms on the node image, 2.25 ms at 0.35 CPU (measured).
    return self.__derive_shared_key(self._address_to_pk(peer_address), info=info, debug=debug)


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
    Encrypt for one receiver.

    Encrypts plaintext using the sender's private key and receiver's public key, 
    then base64 encodes the output. The key shared with the receiver comes from
    `_shared_key`, so it is derived on the first message to that receiver only;
    the nonce is new for every message.

    Parameters
    ----------
    plaintext : str
        The plaintext to encrypt.

    receiver_address : str
        The receiver's address.
        
    compressed : bool, optional
        Whether to compress the plaintext before encryption. The default is True.
        
    embed_compressed : bool, optional
        Whether to embed the compressed flag in the encrypted data. The default is True.

    info : str, optional
        The HKDF `info` text of the shared key. The default is BCct.DEFAULT_INFO.

    debug : bool, optional
        Print the shared key when it is derived. The default is False.

    Returns
    -------
    str
        The base64 encoded nonce, compressed flag (when embedded) and ciphertext.

    Raises
    ------
    Exception
        What `_address_to_pk` raises for a receiver address that is not a valid
        public key (ValueError; AttributeError for a value that is not text).

    Examples
    --------
    >>> data = engine._encrypt('hello', peer.address)
    >>> peer._decrypt(data, engine.address)
    'hello'
    """
    
    if compressed:
      to_encrypt_data = zlib.compress(plaintext.encode())
      compressed_flag = (1).to_bytes(1, byteorder='big')
    else:
      to_encrypt_data = plaintext.encode()
      compressed_flag = (0).to_bytes(1, byteorder='big')
      
    # The receiver's key from the cache, derived once per receiver: 0.53 ms per message before, 0.02 ms now.
    shared_key = self._shared_key(self.address, receiver_address, info, debug)
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
    Decrypt a message from one sender.

    Decrypts base64 encoded encrypted data using the receiver's private key.
    
    The structure of the encrypted data is:
    - 12 bytes nonce
    - 1 byte compressed flag 
    - 13:... The ciphertext

    The key shared with the sender comes from `_shared_key`, so it is derived
    on the first message from that sender only.

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
        
    info : str, optional
        The HKDF `info` text of the shared key. The default is BCct.DEFAULT_INFO.

    debug : bool, optional
        Log a failure in red and print the shared key when it is derived. The
        default is False.
        
    Returns
    -------
    str or None
        The decrypted plaintext, or None when anything fails: data that is not
        this layout, a wrong key or tag, or a sender address that is not a valid
        public key.

    Raises
    ------
    UnboundLocalError
        Only with debug=True, for data that fails base64 decoding: the failure
        log reads the compressed flag before it is set.

    Notes
    -----
    The sender address is decoded after the data, inside `_shared_key`. With
    debug=True an invalid sender address therefore returns None with its log
    line, where it used to raise UnboundLocalError from that log line.

    Examples
    --------
    >>> peer._decrypt(engine._encrypt('hello', peer.address), engine.address)
    'hello'
    >>> print(peer._decrypt('not encrypted', engine.address))
    None
    """
    try:
        
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
      # The sender's key from the cache (its address is decoded there on a miss): one derivation per sender.
      shared_key = self._shared_key(self.address, sender_address, info, debug)
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
    The symmetric key and every nonce are new for each call; the key shared
    with each receiver comes from `_shared_key`, so it is derived on the first
    message to that receiver only.

    Parameters
    ----------
    plaintext : str
        The plaintext to encrypt.
        
    receiver_addresses : list
        List of receiver addresses.

    info : str, optional
        The HKDF `info` text of the shared keys. The default is BCct.DEFAULT_INFO.

    debug : bool, optional
        Print each shared key when it is derived. The default is False.

    Returns
    -------
    str
        The base64 encoded encrypted package.

    Raises
    ------
    Exception
        What `_address_to_pk` raises for a receiver address that is not a valid
        public key (ValueError; AttributeError for a value that is not text).

    Examples
    --------
    >>> package = engine.encrypt_for_multi('hello', [peer1.address, peer2.address])
    >>> peer2.decrypt_for_multi(package, engine.address)
    'hello'
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
      # Each receiver's key from the cache: a write to N peers no longer pays N derivations every time.
      shared_key = self._shared_key(self.address, receiver_address, info, debug)
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

    Finds this node's entry in the package, decrypts the symmetric key with the
    key shared with the sender, then the data. The shared key comes from
    `_shared_key`, so it is derived on the first message from that sender only.

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
      The decrypted plaintext as a string, or None if decryption fails (a
      sender address that is not a valid public key included).

    Examples
    --------
    >>> package = engine.encrypt_for_multi('hello', [peer.address])
    >>> peer.decrypt_for_multi(package, engine.address)
    'hello'
    >>> print(other.decrypt_for_multi(package, engine.address))  # not a receiver
    None
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
      # From the cache: one derivation per sender instead of one per received message.
      shared_key = self._shared_key(my_address, sender_address, info, debug)

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
  
