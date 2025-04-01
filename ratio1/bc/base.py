import os
import base64
import json
import binascii
import numpy as np
import datetime
import uuid
import requests

from collections import defaultdict
from hashlib import sha256, md5
from threading import Lock
from copy import deepcopy

try:
  from ver import __VER__ as app_version
except:
  app_version = None
try:
  from naeural_core.main.ver import __VER__ as core_version
except:
  core_version = None



from cryptography.hazmat.primitives import serialization

from ..utils.config import get_user_folder


from ..const.base import (
  BCctbase, BCct, 
  DAUTH_SUBKEY, DAUTH_ENV_KEY,
  DAUTH_NONCE, dAuth,
)

from .evm import _EVMMixin, Web3, EE_VPN_IMPL
from .chain import _ChainMixin

EVM_COMMENT = " # "
INVALID_COMMENT = " # INVALID: "
  
  
class _DotDict(dict):
  __getattr__ = dict.__getitem__
  __setattr__ = dict.__setitem__
  __delattr__ = dict.__delitem__
  
  
class VerifyMessage(_DotDict):
  def __init__(self):
    self.valid = False
    self.message = None
    self.sender = None
    
    
ALL_NON_DATA_FIELDS = [val for key, val in BCctbase.__dict__.items() if key[0] != '_']

NO_ETH_NON_DATA_FIELDS = [
  val for key, val in BCctbase.__dict__.items() 
  if key[0] != '_' and not key.startswith('ETH_')
]

def replace_nan_inf(data, inplace=False):
  assert isinstance(data, (dict, list)), "Only dictionaries and lists are supported"
  if inplace:
    d = data
  else:
    d = deepcopy(data)    
  stack = [d]
  while stack:
    current = stack.pop()
    for key, value in current.items():
      if isinstance(value, dict):
        stack.append(value)
      elif isinstance(value, list):
        for item in value:
          if isinstance(item, dict):
            stack.append(item)
      elif isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        current[key] = None
  return d 

class _SimpleJsonEncoder(json.JSONEncoder):
  """
  Used to help jsonify numpy arrays or lists that contain numpy data types.
  """
  def default(self, obj):
    if isinstance(obj, np.integer):
      return int(obj)
    elif isinstance(obj, np.floating):
      return float(obj)
    elif isinstance(obj, np.ndarray):
      return obj.tolist()
    elif isinstance(obj, np.ndarray):
      return obj.tolist()
    elif isinstance(obj, datetime.datetime):
      return obj.strftime("%Y-%m-%d %H:%M:%S")
    else:
      return super(_SimpleJsonEncoder, self).default(obj)

class _ComplexJsonEncoder(json.JSONEncoder):
  def default(self, obj):
    if isinstance(obj, np.integer):
      return int(obj)
    elif isinstance(obj, np.floating):
      return float(obj)
    elif isinstance(obj, np.ndarray):
      return obj.tolist()
    elif isinstance(obj, datetime.datetime):
      return obj.strftime("%Y-%m-%d %H:%M:%S")
    else:
      return super(_ComplexJsonEncoder, self).default(obj)

  def iterencode(self, o, _one_shot=False):
    """Encode the given object and yield each string representation as available."""
    if self.check_circular:
      markers = {}
    else:
      markers = None
    if self.ensure_ascii:
      _encoder = json.encoder.encode_basestring_ascii
    else:
      _encoder = json.encoder.encode_basestring
    
    def floatstr(o, allow_nan=self.allow_nan, _repr=float.__repr__, _inf=json.encoder.INFINITY, _neginf=-json.encoder.INFINITY):
      if o != o:  # Check for NaN
        text = 'null'
      elif o == _inf:
        text = 'null'
      elif o == _neginf:
        text = 'null'
      else:
        return repr(o).rstrip('0').rstrip('.') if '.' in repr(o) else repr(o)

      if not allow_nan:
        raise ValueError("Out of range float values are not JSON compliant: " + repr(o))
      
      return text

    _iterencode = json.encoder._make_iterencode(
      markers, self.default, _encoder, self.indent, floatstr,
      self.key_separator, self.item_separator, self.sort_keys,
      self.skipkeys, _one_shot
    )
    return _iterencode(o, 0)

## RIPEMD160

# Message schedule indexes for the left path.
ML = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
    3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
    1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
    4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13
]

# Message schedule indexes for the right path.
MR = [
    5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
    6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
    15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
    8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
    12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11
]

# Rotation counts for the left path.
RL = [
    11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
    7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
    11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
    11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
    9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6
]

# Rotation counts for the right path.
RR = [
    8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
    9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
    9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
    15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
    8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11
]

# K constants for the left path.
KL = [0, 0x5a827999, 0x6ed9eba1, 0x8f1bbcdc, 0xa953fd4e]

# K constants for the right path.
KR = [0x50a28be6, 0x5c4dd124, 0x6d703ef3, 0x7a6d76e9, 0]


def fi(x, y, z, i):
    """The f1, f2, f3, f4, and f5 functions from the specification."""
    if i == 0:
        return x ^ y ^ z
    elif i == 1:
        return (x & y) | (~x & z)
    elif i == 2:
        return (x | ~y) ^ z
    elif i == 3:
        return (x & z) | (y & ~z)
    elif i == 4:
        return x ^ (y | ~z)
    else:
        assert False


def rol(x, i):
    """Rotate the bottom 32 bits of x left by i bits."""
    return ((x << i) | ((x & 0xffffffff) >> (32 - i))) & 0xffffffff


def compress(h0, h1, h2, h3, h4, block):
    """Compress state (h0, h1, h2, h3, h4) with block."""
    # Left path variables.
    al, bl, cl, dl, el = h0, h1, h2, h3, h4
    # Right path variables.
    ar, br, cr, dr, er = h0, h1, h2, h3, h4
    # Message variables.
    x = [int.from_bytes(block[4*i:4*(i+1)], 'little') for i in range(16)]

    # Iterate over the 80 rounds of the compression.
    for j in range(80):
        rnd = j >> 4
        # Perform left side of the transformation.
        al = rol(al + fi(bl, cl, dl, rnd) + x[ML[j]] + KL[rnd], RL[j]) + el
        al, bl, cl, dl, el = el, al, bl, rol(cl, 10), dl
        # Perform right side of the transformation.
        ar = rol(ar + fi(br, cr, dr, 4 - rnd) + x[MR[j]] + KR[rnd], RR[j]) + er
        ar, br, cr, dr, er = er, ar, br, rol(cr, 10), dr

    # Compose old state, left transform, and right transform into new state.
    return h1 + cl + dr, h2 + dl + er, h3 + el + ar, h4 + al + br, h0 + bl + cr


def ripemd160(data):
    """Compute the RIPEMD-160 hash of data."""
    # Initialize state.
    state = (0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0)
    # Process full 64-byte blocks in the input.
    for b in range(len(data) >> 6):
        state = compress(*state, data[64*b:64*(b+1)])
    # Construct final blocks (with padding and size).
    pad = b"\x80" + b"\x00" * ((119 - len(data)) & 63)
    fin = data[len(data) & ~63:] + pad + (8 * len(data)).to_bytes(8, 'little')
    # Process final blocks.
    for b in range(len(fin) >> 6):
        state = compress(*state, fin[64*b:64*(b+1)])
    # Produce output.
    return b"".join((h & 0xffffffff).to_bytes(4, 'little') for h in state)
  
# END ## RIPEMD160  

class BaseBlockEngine(
  _EVMMixin,
  _ChainMixin,
):
  """
  This multiton (multi-singleton via key) is the base workhorse of the private blockchain. 
  
  Parameters
  ----------
  
  name: str
    the name of the engine. Used to create the private key file name.
    
  config: dict
    the configuration dict that contains the PEM_FILE, PASSWORD, PEM_LOCATION keys
    for configuring the private key file access
    
  log: Logger object
    the Logger object
    
  ensure_ascii_payloads: bool
    flag that controls if the payloads are encoded as ascii or not. Default `False` for JS compatibility.

  user_config: bool
    flag that controls if the keys are stored in the user private folder or in the data folder of the _local_cache
  
  """
  _lock: Lock = Lock()
  _whitelist_lock : Lock = Lock()
  __instances = {}
  
  def __new__(
    cls, 
    name, 
    log, 
    config={}, 
    ensure_ascii_payloads=False, 
    verbosity=1, 
    user_config=False,   
    eth_enabled=True, 
  ):
    with cls._lock:
      if name not in cls.__instances:
        instance = super(BaseBlockEngine, cls).__new__(cls)
        instance._build(
          name=name, log=log, config=config, 
          ensure_ascii_payloads=ensure_ascii_payloads,
          verbosity=verbosity,
          user_config=user_config,
          eth_enabled=eth_enabled,
        )
        cls.__instances[name] = instance
      else:
        instance = cls.__instances[name]
    return instance
  
  def _build(
      self, 
      name, 
      config:dict, 
      log=None, 
      ensure_ascii_payloads=False,
      verbosity=1,
      user_config=False,
      eth_enabled=True,
    ):

    self.__name = name
    assert log is not None, "Logger object was not provided!"      
      
    self.log = log
    
    self._first_checks_done = defaultdict(lambda: False) # used to store the first check results
    
    self.__private_key = None
    self.__verbosity = verbosity
    self.__public_key = None    
    self.__password = config.get(BCct.K_PASSWORD)    
    self.__config = config
    self.__ensure_ascii_payloads = ensure_ascii_payloads
    
    self._eth_enabled = eth_enabled
    
    if user_config:
      user_folder = get_user_folder()
      pem_fn = str(user_folder / BCct.USER_PEM_FILE)
      self.P(f"Home config selected. Setting pem_fn to {pem_fn}")
    else:
      pem_name = config.get(BCct.K_PEM_FILE, BCct.DEFAULT_PEM_FILE)
      pem_folder = config.get(BCct.K_PEM_LOCATION, BCct.DEFAULT_PEM_LOCATION)
      pem_fn = os.path.join(log.get_target_folder(pem_folder), pem_name)
      self.P(f"Arbitrary config selected. Setting pem_fn to {pem_fn}")
    #endif pem is defined in ~/.ratio1/ or in the data folder of the _local_cache
    self.__pem_file = pem_fn
    self._init()
    return


  def P(self, s, color=None, boxed=False, verbosity=1, **kwargs):
    if verbosity > self.__verbosity:
      return
    if not boxed:
      s = "<BC:{}> ".format(self.__name) + s
    return self.log.P(
      s, 
      color=color or 'd', 
      boxed=boxed, 
      **kwargs
    )
    return
  
  
  @property
  def eth_enabled(self):
    return self._eth_enabled


  def set_eth_flag(self, value):    
    if value != self._eth_enabled:
      self._eth_enabled = value
      self.log.P("Changed eth_enabled to {}".format(value), color='d')
    return


  @property
  def name(self):
    return self.__name

  
  @property
  def eth_address(self):
    return self.__eth_address


  @property
  def eth_account(self):
    return self.__eth_account


  def _init(self):
    self.P(
      f"Initializing BC-engine (ETH_ENABLED={self._eth_enabled})...", verbosity=1
    )

    if True:
      self.P("Initializing private blockchain:\n{}".format(
        json.dumps(self.__config, indent=4)), verbosity=1
      )
    if self.__pem_file is not None:
      try:
        full_path = os.path.abspath(self.__pem_file)
        self.P("Trying to load sk from {}".format(full_path), verbosity=1)
        self.__private_key = self._text_to_sk(
          source=self.__pem_file,
          from_file=True,
          password=self.__password,
        )
        self.P("  Loaded sk from {}".format(full_path), verbosity=1)        
      except:
        self.P("  Failed to load sk from {}".format(full_path), color='r', verbosity=1)

    if self.__private_key is None:
      self.P("Creating new private key", verbosity=1)
      self.__private_key = self._create_new_sk()
      self._sk_to_text(
        private_key=self.__private_key,
        password=self.__password,
        fn=self.__pem_file,
      )
    
    os.environ[BCct.K_USER_CONFIG_PEM_FILE] = os.path.abspath(self.__pem_file)
    
    self.__public_key = self._get_pk(private_key=self.__private_key)    
    self.__address = self._pk_to_address(self.__public_key)
    ### Ethereum
    self.__eth_address = self._get_eth_address()
    self.__eth_account = self._get_eth_account()
    ### end Ethereum
    if self._eth_enabled:
      self.P(
        "{} / ETH: {} ({})".format(self.address, self.eth_address, self.evm_network), boxed=True, verbosity=1,
        color='g'
      )
    else:
      self.P("Address: {}".format(self.address), boxed=True, color='g', verbosity=1)
    self.P("Allowed list of senders: {}".format(self.allowed_list), verbosity=1)
    return
  
  @property
  def private_key(self):
    return self.__private_key
  
  
  @property
  def public_key(self):
    return self.private_key.public_key()
  
 
  @staticmethod
  def _compute_hash(data : bytes, method='SHA256'):
    """
    Computes the hash of a `bytes` data message

    Parameters
    ----------
    data : bytes
      the input message usually obtained from a bynary jsoned dict.
      
    method : str, optional
      the hash algo. The default is 'HASH160'.


    Returns
    -------
    result : bytes, str
      hash both in bin and text format.

    """
    result = None, None
    method = method.upper()
    assert method in ['HASH160', 'SHA256', 'MD5']
        
    if method == 'MD5':
      hash_obj = md5(data)
      result = hash_obj.digest(), hash_obj.hexdigest()
    elif method == 'SHA256':
      hash_obj = sha256(data)
      result = hash_obj.digest(), hash_obj.hexdigest()
    elif method == 'HASH160':
      hb_sha256 = sha256(data).digest()
      hb_h160 = ripemd160(hb_sha256)
      result = hb_h160, binascii.hexlify(hb_h160).decode()
    return result  
  
  
  @staticmethod
  def _binary_to_text(data : bytes, method='base64'):
    """
    Encodes a bytes message as text

    Parameters
    ----------
    data : bytes
      the binary data, usually a signature, hash, etc.
      
    method : str, optional
      the method - 'base64' or other. The default is 'base64'.


    Returns
    -------
    txt : str
      the base64 or hexlified text.

    """
    assert isinstance(data, bytes)
    if method == 'base64':
      txt = base64.urlsafe_b64encode(data).decode()
    else:
      txt = binascii.hexlify(data).decode()
    return txt
  
  
  @staticmethod
  def _text_to_binary(text : str, method='base64'):
    """
    Convert from str/text to binary

    Parameters
    ----------
    text : str
      the message.
      
    method : str, optional
      the conversion method. The default is 'base64'.


    Returns
    -------
    data : bytes
      the decoded binary message.

    """
    assert isinstance(text, str), "Cannot convert non text to binary"
    if method == 'base64':
      data = base64.urlsafe_b64decode(text)
    else:
      data = binascii.unhexlify(text)
    return data  

  
  @staticmethod
  def _get_pk(private_key):
    """
    Simple wrapper to generate pk from sk


    Returns
    -------
    public_key : pk
    
    """
    return private_key.public_key()
  
  
  def _get_allowed_file(self):
    """
    Return the file path for the autorized addresses
    """
    folder = self.log.base_folder
    path = os.path.join(folder, BCct.AUTHORISED_ADDRS)
    return path  
  
  
  def address_is_valid(self, address, return_error=False):
    """
    Checks if an address is valid

    Parameters
    ----------
    address : str
      the text address.

    Returns
    -------
    bool
      True if the address is valid.

    """
    result = False
    msg = ""
    try:
      pk = self._address_to_pk(address)
      result = False if pk is None else True
    except Exception as exc:
      result = False
      msg = str(exc)
    if return_error:
      return result, msg
    return result
  
  
  def add_address_to_allowed(self, address : any):
    """
    Adds a new address or a list of addresses to the allowed list
    """
    changed = False
    if isinstance(address, str):
      address = [address]
    #endif
    if isinstance(address, list) and len(address) > 0:
      # self.P(f"Adding addresses to the allowed list:\n{address}", verbosity=1)
      # now check addresses
      lst_lines = []
      lst_addrs = []
      lst_names = []
      whitelist = self.whitelist_with_prefixes
      for addr in address:
        addr = addr.strip()
        parts = addr.split()
        if len(parts) == 0:
          continue
        addr = parts[0]
        name = parts[1] if len(parts) > 1 else ""
        is_valid, valid_msg = self.address_is_valid(addr, return_error=True)
        if not is_valid:
          self.P("WARNING: address <{}> is not valid. Ignoring.".format(addr), color='r')
          addr = "# " + addr
          name = name + INVALID_COMMENT + valid_msg
          continue # skip invalid address or go forward and add it ...
        else:
          addr = self.maybe_add_prefix(addr)
          if addr in whitelist:
            self.P("WARNING: address <{}> already in the allowed list. Ignoring.".format(addr), color='r')
            continue
          eth = self.node_address_to_eth_address(addr)
          name = name + EVM_COMMENT + eth          
        str_line = "{}{}".format(addr, ("  " + name) if len(name)>0 else "")
        lst_lines.append(str_line)
        lst_addrs.append(addr)
        lst_names.append(name)
        #endif
      #endfor
      if len(lst_lines) > 0:
        with self._whitelist_lock:
          fn = self._get_allowed_file()
          with open(fn, 'rt') as fh:
            lst_existing = fh.readlines()
          #endwith
        for line, addr, name in zip(lst_lines, lst_addrs, lst_names):
          if line not in lst_existing:
            changed = True
            lst_existing.append(line)
            self.P("Address <{}> added to the allowed list.".format(addr), color='g')
        #endfor
        if changed:
          with self._whitelist_lock:
            fn = self._get_allowed_file()
            with open(fn, 'wt') as fh:
              for line in lst_existing:
                line = line.strip()
                if line != "":
                  fh.write(f"{line}\n")
              #endfor each address in modified whitelist
            #endwith open file
          #endwith lock
        #endif changed
      #endif addresses received ok
    return changed


  def _load_and_maybe_create_allowed(self, return_names=False, return_prefix=False):
    lst_final = []
    lst_names = []
    with self._whitelist_lock:
      try:
        fn = self._get_allowed_file()
        lst_allowed = []
        if os.path.isfile(fn):
          with open(fn, 'rt') as fh:
            lst_allowed = fh.readlines()
        else:
          full_path = os.path.abspath(fn)
          self.P("WARNING: no `{}` file found. Creating empty one.".format(full_path), verbosity=1)
          with open(fn, 'wt') as fh:
            fh.write('\n')
        lst_allowed = [x.strip() for x in lst_allowed]
        lst_allowed = [x for x in lst_allowed if x != '']
        lst_lines_to_write = []
        needs_rewrite = False
        for allowed_tuple in lst_allowed:
          parts = allowed_tuple.split()
          if len(parts) == 0:
            continue
          allowed = parts[0]
          if allowed.startswith("#"):
            # skip comments but keep them if we re-write the file
            lst_lines_to_write.append(allowed_tuple)
            continue
          allowed = self._remove_prefix(allowed)
          name = parts[1] if len(parts) > 1 else ""
          is_valid, valid_msg = self.address_is_valid(allowed, return_error=True)
          if not is_valid:
            self.P("WARNING: address <{}> is not valid. Commenting {} from allowed list.".format(
              allowed, allowed_tuple), color='r'
            )
            needs_rewrite = True
            error_line = "# " + allowed_tuple + INVALID_COMMENT + valid_msg
            lst_lines_to_write.append(error_line)
          else:
            if return_prefix:
              allowed = self.maybe_add_prefix(allowed)
            lst_final.append(allowed)
            lst_names.append(name)
            if len(parts) < 3:
              eth = self.node_address_to_eth_address(allowed)
              allowed_tuple = allowed_tuple + EVM_COMMENT + eth
              needs_rewrite = True 
            lst_lines_to_write.append(allowed_tuple)
              
        if needs_rewrite:
          with open(fn, 'wt') as fh:
            for line in lst_lines_to_write:
              fh.write(f"{line}\n")
      except Exception as exc:
        self.P(f"ERROR: failed to load the allowed list of addresses: {exc}", color='r')
      #endtry
    #endwith
    if return_names:
      return lst_final, lst_names
    return lst_final
  
        
  def _remove_prefix(self, address):
    """
    Removes the prefix from the address

    Parameters
    ----------
    address : str
      the text address.

    Returns
    -------
    address : str
      the address without the prefix.
    """
    if address.startswith(BCct.ADDR_PREFIX):
      address = address[len(BCct.ADDR_PREFIX):]
    elif address.startswith(BCct.ADDR_PREFIX_OLD):
      address = address[len(BCct.ADDR_PREFIX_OLD):]
    return address
  
  def _add_prefix(self, address):
    """
    Adds the prefix to the address

    Parameters
    ----------
    address : str
      the text address.

    Returns
    -------
    address : str
      the address with the prefix.
    """
    address = self._remove_prefix(address)
    address = BCct.ADDR_PREFIX + address  
    return address
  
  
  
  def _get_binary_pk(self, pubic_key=None):
    """
    Returns the public key object

    Returns
    -------
    pk : pk
      the public key object.

    """
    if pubic_key is None:
      public_key = self.__public_key
    data = public_key.public_bytes(
      encoding=serialization.Encoding.DER, # will encode the full pk information 
      format=serialization.PublicFormat.SubjectPublicKeyInfo, # used with DER
    )    
    return data
  
  
  def _pkdata_to_addr(self, pkdata):
    txt = BCct.ADDR_PREFIX + self._binary_to_text(pkdata)
    return txt
  

  
  def _pk_to_address(self, public_key):
    """
    Given a pk object will return the simple text address.
    
    OBS: Should be overwritten in particular implementations using X962


    Parameters
    ----------
    public_key : pk
      the pk object.
      
    Returns
    -------
      text address      
    
    """
    data = self._get_binary_pk(public_key)
    txt = self._pkdata_to_addr(data)
    return txt


  def _address_to_pk(self, address):
    """
    Given a address will return the pk object
    
    OBS: Should be overwritten in particular implementations using X962


    Parameters
    ----------
    address : str
      the text address (pk).


    Returns
    -------
    pk : pk
      the pk object.

    """
    simple_address = self._remove_prefix(address)
    bpublic_key = self._text_to_binary(simple_address)
    # below works for DER / SubjectPublicKeyInfo
    public_key = serialization.load_der_public_key(bpublic_key)
    return public_key
  
  
  def _text_to_sk(self, source, from_file=False, password=None):
    """
    Construct a EllipticCurvePrivateKey from a text sk

    Parameters
    ----------
    source : str
      the text secret key or the file name if `from_file == True`.
      
    from_file: bool
      flag that allows source to be a file
      

    Returns
    -------
      sk

    """
    if from_file and os.path.isfile(source):
      self.P("Reading SK from '{}'".format(source), verbosity=2)
      with open(source, 'rt') as fh:
        data = fh.read()
    else:
      data = source
    
    bdata = data.encode()
    if password:
      pass_data = password.encode()
    else:
      pass_data = None
    private_key = serialization.load_pem_private_key(bdata, pass_data)
    return private_key
  
  def _sk_to_text(self, private_key, password=None, fn=None):
    """
    Serialize a sk as text

    Parameters
    ----------
    private_key : sk
      the secret key object.
      
    password: str
      password to be used for sk serialization
      
    fn: str:
      text file where to save the pk

    Returns
    -------
      the sk as text string

    """
    if password:
      encryption_algorithm = serialization.BestAvailableEncryption(password.encode())
    else:
      encryption_algorithm = serialization.NoEncryption()
      
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption_algorithm        
    )     
    str_pem = pem.decode()
    if fn is not None:
      full_path = os.path.abspath(fn)
      self.P("Writing PEM-encoded key to {}".format(full_path), color='g', verbosity=2)
      with open(fn, 'wt') as fh:
        fh.write(str_pem)
    return str_pem  
  
  
  def _dict_to_json(self, dct_data, replace_nan=True, inplace=True, indent=0):
    if replace_nan:
      dct_safe_data = replace_nan_inf(dct_data, inplace=inplace)
    else:
      dct_safe_data = dct_data
      
    dumps_config = dict(
      cls=_ComplexJsonEncoder, 
      separators=(',',':'),
      ensure_ascii=self.__ensure_ascii_payloads,
    )
    if indent > 0:
      dumps_config['indent'] = indent    
    # we dump the data to a string then we reload and sort as there might
    # be some issues with the sorting if we have int keys that will be sorted
    # then recovered as string keys
    str_data = json.dumps(dct_safe_data, **dumps_config)
    # we reload the data to ensure 
    dct_reload = json.loads(str_data)
    # in order to ensure the data is sorted we dump it again to a string
    # IMPORTANT: we need to use the same dumps_config as before !
    str_data = json.dumps(dct_reload, sort_keys=True, **dumps_config) 
    return str_data
  
  def _create_new_sk(self):
    """
    Simple wrapper to generated pk


    Returns
    -------
    private_key : sk
    
    """
    raise NotImplementedError()
    

  
  def _verify(self, public_key, signature : bytes, data : bytes):
    """
    Verifies a `pk` signature on a binary `data` package
    

    Parameters
    ----------
    public_key : pk type
      the pk object.
      
    signature : bytes
      the binary signature.
      
    data : bytes
      the binary message.


    Returns
    -------
    result: _DotDict 
      contains `result.ok` and `result.message`

    """
    raise NotImplementedError()

  
  
  def _sign(self, data : bytes, private_key, text=False):
    """
    Sign a binary message with Elliptic Curve
    

    Parameters
    ----------
    data : bytes
      the binary message.
      
    private_key : pk
      the private key object.
      
    text : bool, optional
      return the signature as text. The default is False.

    Returns
    -------
    signature as text or binary

    """
    raise NotImplementedError()  
  
      
  
  #############################################################################
  ####                                                                     ####
  ####                          Public functions                           ####
  ####                                                                     ####
  #############################################################################
  
  
  def contains_current_address(self, lst_addresses):
    """
    Checks if the current address is in the list of addresses

    Parameters
    ----------
    lst_addresses : list
      the list of addresses.

    Returns
    -------
    bool
      True if the current address is in the list.

    """
    return self.address_in_list(self.address, lst_addresses)
  
  def address_in_list(self, node_address, lst_addresses):
    """
    Checks if the address is in the list of addresses

    Parameters
    ----------
    node_address : str
      the address.
      
    lst_addresses : list
      the list of addresses.

    Returns
    -------
    bool
      True if the address is in the list.

    """
    node_address = self._remove_prefix(node_address)
    lst = [self._remove_prefix(x) for x in lst_addresses if x is not None]
    return node_address in lst
  
  @property
  def address(self):
    """Returns the public address"""
    return self.__address
    
  
  @property
  def address_no_prefix(self):
    """Returns the public address without the prefix"""
    return self._remove_prefix(self.address)
  
  @property
  def allowed_list(self):
    """Returns the allowed command senders (non-prefixed) for the current node"""
    return self._load_and_maybe_create_allowed(return_names=False, return_prefix=False)
  
  @property
  def whitelist(self):
    """Returns the allowed command senders for the current node"""
    return self.allowed_list
  
  @property
  def whitelist_with_names(self):
    """
    Returns a tuple with the allowed list (prefixed) and a list with names
    """
    return self._load_and_maybe_create_allowed(return_names=True, return_prefix=True)
  
  
  @property
  def whitelist_with_prefixes(self):
    """
    Returns the allowed command senders (prefixed) for the current node
    """
    return self._load_and_maybe_create_allowed(return_names=False, return_prefix=True)

  
  def maybe_remove_prefix(self, address):
    """
    Removes the prefix from the address

    Parameters
    ----------
    address : str
      the text address.

    Returns
    -------
    address : str
      the address without the prefix.
    """
    return self._remove_prefix(address)  
  

  def maybe_add_prefix(self, address):
    """
    Adds the prefix to the address

    Parameters
    ----------
    address : str
      the text address.

    Returns
    -------
    address : str
      the address with the prefix.
    """
    return self._add_prefix(address)
    
  
  def dict_digest(self, dct_data, return_str=True):
    """Generates the hash of a dict object given as parameter"""
    str_data = self._dict_to_json(dct_data, replace_nan=True)
    bin_hex_hash, hex_hash = self._compute_hash(str_data.encode())
    if return_str:
      return hex_hash
    else:
      return bin_hex_hash
  
  
  def save_sk(self, fn, password=None):
    """
    Saves the SK with or without password

    Parameters
    ----------
    fn : str
      SK file name.
    password : str, optional
      optional password. The default is None.

    Returns
    -------
    fn : str
      saved file name.

    """
    self.P("Serializing the private key...", verbosity=2)
    _ = self._sk_to_text(
      private_key=self.__private_key,
      password=password,
      fn=fn
    )
    return fn
  
  
  def _generate_data_for_hash(self, dct_data, replace_nan=True):
    """
    Will convert the dict to json (removing the non-data fields) and return the json string. 
    The dict will be modified inplace to replace NaN and Inf with None.
    """
    assert isinstance(dct_data, dict), "Cannot compute hash on non-dict data"
    if self.eth_enabled:
      dct_only_data = {k:dct_data[k] for k in dct_data if k not in ALL_NON_DATA_FIELDS}
    else:
      dct_only_data = {k:dct_data[k] for k in dct_data if k not in NO_ETH_NON_DATA_FIELDS}
    #endif
    str_data = self._dict_to_json(
      dct_only_data, 
      replace_nan=replace_nan, 
      inplace=True # will replace inplace the np.nan and np.inf with None
    )
    return str_data
  
  def safe_dict_to_json(self, dct_data, replace_nan=True, indent=0):
    """
    Will convert the dict to json (removing the non-data fields) and return the json string. 
    The dict will be modified inplace to replace NaN and Inf with None.
    """
    assert isinstance(dct_data, dict), "Cannot compute hash on non-dict data"
    str_data = self._dict_to_json(
      dct_data, 
      replace_nan=replace_nan, 
      inplace=True, # will replace inplace the np.nan and np.inf with None
      indent=indent
    )
    return str_data
    
  
  def compute_hash(self, dct_data, return_all=False, replace_nan=True):
    """
    Computes the hash of a dict object

    Parameters
    ----------
    dct_data : dict
      the input message as a dict.
      
    return_all: bool, optional
      if `True` will return the binary hash as well. Default `False`
      
    replace_nan: bool, optional
      will replace inplace `np.nan` and `np.inf` with `None` before hashing. Default `True`

    Returns
    -------
    result : str or tuple(bytes, bytes, str) if `return_all` is `True`
      
    """
    str_data = self._generate_data_for_hash(dct_data, replace_nan=replace_nan)
    bdata = bytes(str_data, 'utf-8')
    bin_hexdigest, hexdigest = self._compute_hash(bdata)
    if return_all:
      result = bdata, bin_hexdigest, hexdigest
    else:
      result = hexdigest
    return result
  
  
  def sign(self, dct_data: dict, add_data=True, use_digest=True, replace_nan=True, eth_sign=False) -> str:
    """
    Generates the signature for a dict object.
    Does not add the signature to the dict object


    Parameters
    ----------
    dct_data : dict
      the input message as a dict.
      
    add_data: bool, optional
      will add signature and address to the data dict (also digest if required). Default `True`
      
    use_digest: bool, optional  
      will compute data hash and sign only on hash
      
    replace_nan: bool, optional
      will replace `np.nan` and `np.inf` with `None` before signing. 
      
    eth_sign: bool, optional
      will also sign the data with the Ethereum account. Default `False`

    Returns
    -------
      text signature

        
      IMPORTANT: 
        It is quite probable that the same sign(sk, hash) will generate different signatures

    """
    result = None
    assert isinstance(dct_data, dict), "Cannot sign on non-dict data"
    
    bdata, bin_hexdigest, hexdigest = self.compute_hash(
      dct_data, 
      return_all=True, 
      replace_nan=replace_nan,
    )
    text_data = bdata.decode()
    if use_digest:
      bdata = bin_hexdigest # to-sign data is the hash
    # finally sign either full or just hash
    result = self._sign(data=bdata, private_key=self.__private_key, text=True)
    if add_data:
      # now populate dict
      dct_data[BCct.SIGN] = result
      dct_data[BCct.SENDER] = self.address
      
      if self._eth_enabled:
        dct_data[BCct.ETH_SENDER] = self.eth_address
        ### add eth signature
        dct_data[BCct.ETH_SIGN] = "0xBEEF"
        if eth_sign:
          eth_sign_info = self.eth_sign_text(text_data, signature_only=False)
          # can be replaced with dct_data[BCct.ETH_SIGN] = self.eth_sign_text(bdata.decode(), signature_only=True)
          eth_sign = eth_sign_info.get('signature')
          dct_data[BCct.ETH_SIGN] = eth_sign
        ### end eth signature
      if use_digest:
        dct_data[BCct.HASH] = hexdigest
    return result
    
  
  
  def verify(
      self, 
      dct_data: dict, 
      signature: str=None, 
      sender_address: str=None, 
      return_full_info=True,
      verify_allowed=False,
      replace_nan=True,
      log_hash_sign_fails=True,
    ):
    """
    Verifies the signature validity of a given text message

    Parameters
    ----------
    dct_data : dict
      dict object that needs to be verified against the signature.
        
    signature : str, optional
      the text encoded signature. Extracted from dict if missing
      
    sender_address : str, optional
      the text encoded public key. Extracted from dict if missing
      
    return_full_info: bool, optional
      if `True` will return more than `True/False` for signature verification
      
    verify_allowed: bool, optional
      if true will also check if the address is allowed by calling `check_allowed`
      
    replace_nan: bool, optional
      will replace `np.nan` and `np.inf` with `None` before verifying. Default `True`
    
    log_hash_sign_fails: bool, optional
      if `True` will log the verification failures for hash and signature issues. Default `True`
    

    Returns
    -------
    bool / VerifyMessage
      returns `True` if signature verifies else `False`. 
      returns `VerifyMessage` structure if return_full_info (default `True`)

    """
    result = False
    
    bdata_json, bin_hexdigest, hexdigest = self.compute_hash(
      dct_data, 
      return_all=True,
      replace_nan=replace_nan,
    )

    if signature is None:
      signature = dct_data.get(BCct.SIGN)
    
    if sender_address is None:
      sender_address = dct_data.get(BCct.SENDER)          
    
    verify_msg = VerifyMessage()
    verify_msg.sender = sender_address
    
    received_digest = dct_data.get(BCct.HASH)
    if received_digest:
      # we need to verify hash and then verify signature on hash      
      if hexdigest != received_digest:
        verify_msg.message = "Corrupted digest!"
        verify_msg.valid = False
      #endif hash failed
      bdata = bin_hexdigest
    else:
      # normal signature on data
      bdata = bdata_json
    #endif has hash or not
    
    if verify_msg.message is None:            
      try:
        assert sender_address is not None, 'Sender address is NULL'
        assert signature is not None, 'Signature is NULL'
        
        bsignature = self._text_to_binary(signature)
        pk = self._address_to_pk(sender_address)
        verify_msg = self._verify(public_key=pk, signature=bsignature, data=bdata)
      except Exception as exc:
        verify_msg.message = str(exc)
        verify_msg.valid = False
    #endif check if signature failed already from digesting

    verify_msg.sender = sender_address
    
    if not verify_msg.valid:
      if log_hash_sign_fails and signature is not None and sender_address is not None:
        self.P("Signature failed on msg from {}: {}".format(
          sender_address, verify_msg.message
          ), color='r', verbosity=1,
        )
    elif verify_allowed and verify_msg.valid:
      if not self.is_allowed(sender_address):
        verify_msg.message = "Signature ok but address {} not in {}.".format(sender_address, BCct.AUTHORISED_ADDRS)
        verify_msg.valid = False
      #endif not allowed
    #endif ok but authorization required
    
    if return_full_info:
      result = verify_msg
    else:
      result = verify_msg.ok
    return result
  
  
  def is_allowed(self, sender_address: str):
    to_search_address = self._remove_prefix(sender_address)
    is_allowed = to_search_address in self.allowed_list or to_search_address == self._remove_prefix(self.address)
    return is_allowed
  
  
  def encrypt(self, data, destination):
    """
    Encrypts the data for a given destination

    Parameters
    ----------
    data : dict
      the data to be encrypted.
      
    destination : str
      the destination address.

    Returns
    -------
    None.

    """
    raise NotImplementedError()
      
  def decrypt(self, data):
    """
    Decrypts the data

    Parameters
    ----------
    data : dict
      the data to be decrypted.

    Returns
    -------
    None.

    """
    raise NotImplementedError()
  
  
  

  def dauth_autocomplete(
    self, 
    dauth_endp=None, 
    add_env=True, 
    debug=False, 
    max_tries=5,
    network=None,
    return_full_data=False,
    debug_data=False,
    **kwargs
  ):
    """
    Autocompletes the environment with the dAuth information.
    Parameters
    ----------
    dauth_endp
    add_env
    debug
    max_tries
    network
    kwargs

    Returns
    -------
    None if the URL is invalid or the request failed.
    dict with the dAuth information if the request got status 200(if errors occured, but
    the status is still 200, an empty dictionary will be returned).
    """
    if EE_VPN_IMPL:
      return None # must return None not empty dict for VPNs
    #endif EE_VPN_IMPL
    
    from ratio1._ver import __VER__ as sdk_version
      
    MIN_LEN = 10
    # Default result in case of invalid URL should be None
    # An empty dict will mean that the URL is valid, but the node
    # does not have a license associated with it.
    dct_env = None
    done = False
    tries = 0
    in_env = False
    url = dauth_endp
    dct_response = {}

    # Network handling
    if network is None:
      network = self.evm_network

    # URL handling
    if not isinstance(url, str) or len(url) < MIN_LEN:
      if DAUTH_ENV_KEY in os.environ:
        in_env = True
        url = os.environ[DAUTH_ENV_KEY]
      else:
        network_data = self.get_network_data(network)
        url = network_data[dAuth.EvmNetData.DAUTH_URL_KEY]
      #endif not in env
      
    if isinstance(url, str) and len(url) > MIN_LEN:
      # Valid URL
      if dauth_endp is None:
        if in_env:
          self.P("Found dAuth URL in environment: '{}'".format(url))
        else:
          self.P("Using default dAuth URL: '{}'".format(url))
      eth_short = self.eth_address[:6] + '...' + self.eth_address[-4:]
      while not done:
        self.P(f"<{eth_short}> ({network}) dAuth with `{url}`... (try {tries + 1} / {max_tries})")
        try:
          if debug_data:
            to_send = {
              DAUTH_NONCE : str(uuid.uuid4())[:8],
              dAuth.DAUTH_SENDER_APP_VER  : app_version,
              dAuth.DAUTH_SENDER_SDK_VER  : sdk_version,
              dAuth.DAUTH_SENDER_CORE_VER : core_version,
              **kwargs,
            }
          else:
            to_send = {
              **kwargs,
              DAUTH_NONCE : str(uuid.uuid4())[:8],
              dAuth.DAUTH_SENDER_APP_VER  : app_version,
              dAuth.DAUTH_SENDER_SDK_VER  : sdk_version,
              dAuth.DAUTH_SENDER_CORE_VER : core_version,
            }
          ######
          if len(kwargs) == 0:
            to_send[dAuth.DAUTH_SENDER_ALIAS] = dAuth.DAUTH_SENDER_ALIAS_DEFAULT
          ######
          self.sign(to_send)    
          json_to_send = {'body' : to_send}
          if debug:
            self.P(f"Sending to dAuth URL: {url}\n{json.dumps(json_to_send, indent=2)}")   
          response = requests.post(url, json=json_to_send)
          if response.status_code == 200:
            dct_response = response.json()
            dct_result = dct_response.get('result', {}) or {}
            dct_dauth = dct_result.get(DAUTH_SUBKEY, {}) or {}
            server_alias = dct_result.get(
              dAuth.DAUTH_SERVER_ALIAS, dAuth.DAUTH_ALIAS_UNK
            )
            server_addr = dct_result.get(
              BCctbase.SENDER, dAuth.DAUTH_ADDR_UNK
            )
            if debug:
              self.P(f"Response received from {server_alias} <{server_addr}>:\n {json.dumps(dct_response, indent=2)}")
            else:
              self.P(f"Response received from {server_alias} <{server_addr}>,")
            ver_result = self.verify(dct_result)
            if ver_result.valid:
              self.P(f"Signature from {server_alias} <{server_addr}> is valid.", color='g')
            else:
              self.P(f"Signature from {server_alias} <{server_addr}> is INVALID: {ver_result}", color='r')
              # Invalid response signature, thus return {}
              return {}

            # whitelist
            whitelist = dct_dauth.pop(dAuth.DAUTH_WHITELIST, [])
            if isinstance(whitelist, (str, list)) and len(whitelist) > 0:
              if isinstance(whitelist, str):
                whitelist = [whitelist]
              self.P(f"Found {len(whitelist)} whitelist addresses in dAuth response.", color='y')
              self.add_address_to_allowed(whitelist)
            else:
              self.P(f"No whitelist addresses found in dAuth response.", color='d')
            # end whitelist

            error = dct_dauth.get('error', None)

            dct_env = {k : v for k,v in dct_dauth.items() if k.startswith(dAuth.DAUTH_ENV_KEYS_PREFIX)}
            if len(dct_env) > 0:
              self.P("Found {} keys in dAuth response.".format(len(dct_env)), color='g')
              for k, v in dct_env.items():
                try:
                  if not isinstance(v, str):
                    v = json.dumps(v)
                except:
                  v = str(v)
                if k not in os.environ:
                  self.P(f"  Adding key `{k}{'=' + str(v) + ' ({})'.format(type(v).__name__) if debug else ''}` to env.", color='y')
                else:
                  self.P(f"  Overwrite  `{k}{'=' + str(v) + ' ({})'.format(type(v).__name__) if debug else ''}` in env.", color='y')
                if add_env:
                  os.environ[k] = v
                #endif add to env
              #endfor each key in dAuth response
              if error is not None:
                self.P(f"Server message: {error}", color='y')
            else:
              self.P(f"dAuth rejected node: {error}", color='r')
            done = True
          else:
            self.P(f"Error in dAuth response: {response.status_code} - {response.text}", color='r')
        except Exception as exc:
          self.P(f"Error in dAuth URL request: {exc}. Received: {dct_response}", color='r')
          # Request failed somewhere so dct_env will be set again to None.
          dct_env = None
        #end try
        tries += 1
        if tries >= max_tries:
          done = True    
      #end while
    else:
      # Invalid URL, thus dct_env will remain None
      self.P(f"dAuth URL is not valid: {url}", color='r')
    #end if url is valid
    if return_full_data:
      return dct_response
    return dct_env
