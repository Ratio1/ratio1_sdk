import os

from eth_account import Account
from eth_utils import keccak, to_checksum_address
from eth_account.messages import encode_defunct

from ..const.base import EE_VPN_IMPL_ENV_KEY, dAuth

EE_VPN_IMPL = str(os.environ.get(EE_VPN_IMPL_ENV_KEY, False)).lower() in [
  'true', '1', 'yes', 'y', 't', 'on'
]

if EE_VPN_IMPL:
  class Web3:
    """
    VPS enabled. Web3 is not available.
    """
else:
  from web3 import Web3



class _EVMMixin:
  
  
  @staticmethod
  def is_valid_evm_address(address: str) -> bool:
    """
    Check if the input string is a valid Ethereum (EVM) address using basic heuristics.

    Parameters
    ----------
    address : str
        The address string to verify.

    Returns
    -------
    bool
        True if `address` meets the basic criteria for an EVM address, False otherwise.
    """
    # Basic checks:
    # A) Must start with '0x'
    # B) Must be exactly 42 characters in total
    # C) All remaining characters must be valid hexadecimal digits
    if not address.startswith("0x"):
      return False
    if len(address) != 42:
      return False
    
    hex_part = address[2:]
    # Ensure all characters in the hex part are valid hex digits
    return all(c in "0123456789abcdefABCDEF" for c in hex_part)
  
  @staticmethod
  def is_valid_eth_address(address: str) -> bool:
    """
    Check if the input string is a valid Ethereum (EVM) address using basic heuristics.

    Parameters
    ----------
    address : str
        The address string to verify.

    Returns
    -------
    bool
        True if `address` meets the basic criteria for an EVM address, False otherwise.
    """
    return _EVMMixin.is_valid_evm_address(address)
  
  
  @staticmethod
  def get_evm_network() -> str:
    """
    Get the current network

    Returns
    -------
    str
      the network name.

    """
    return os.environ.get(dAuth.DAUTH_NET_ENV_KEY, dAuth.DAUTH_SDK_NET_DEFAULT)
  
  @property
  def evm_network(self):
    return self.get_evm_network()
  
  def get_network_data(self, network=None):
    assert isinstance(network, str) and network.lower() in dAuth.EVM_NET_DATA, f"Invalid network: {network}"
    return dAuth.EVM_NET_DATA[network.lower()]

    
  def web3_is_node_licensed(self, address : str, network=None, debug=False) -> bool:
    """
    Check if the address is allowed to send commands to the node

    Parameters
    ----------
    address : str
      the address to check.
    """
    if EE_VPN_IMPL:
      self.P("VPN implementation. Skipping Ethereum check.", color='r')
      return False
    
    if network is None:
      network = self.evm_network
    
    assert self.is_valid_eth_address(address), "Invalid Ethereum address"
    
    network_data = self.get_network_data(network)
    
    contract_address = network_data[dAuth.EvmNetData.DAUTH_ND_ADDR_KEY]
    rpc_url = network_data[dAuth.EvmNetData.DAUTH_RPC_KEY]
          
    if debug:
      self.P(f"Checking if {address} ({network}) is allowed via {rpc_url}...")
    
    w3 = Web3(Web3.HTTPProvider(rpc_url)) 

    contract_abi = dAuth.DAUTH_ABI_IS_NODE_ACTIVE

    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

    result = contract.functions.isNodeActive(address).call()
    return result


  def web3_get_oracles(self, network=None, debug=False) -> list:
    """
    Get the list of oracles from the contract

    Parameters
    ----------
    network : str, optional
      the network to use. The default is None.

    Returns
    -------
    list
      the list of oracles addresses.

    """
    if network is None:
      network = self.evm_network

    network_data = self.get_network_data(network)
    
    contract_address = network_data[dAuth.EvmNetData.DAUTH_ND_ADDR_KEY]
    rpc_url = network_data[dAuth.EvmNetData.DAUTH_RPC_KEY]

    if debug:
      self.P(f"Getting oracles for {network} via {rpc_url}...")
    
    w3 = Web3(Web3.HTTPProvider(rpc_url)) 

    contract_abi = dAuth.DAUTH_ABI_GET_SIGNERS

    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

    result = contract.functions.getSigners().call()
    return result
  

  
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
  
  def is_node_address_in_eth_addresses(self, node_address: str, lst_eth_addrs) -> bool:
    """
    Check if the node address is in the list of Ethereum addresses

    Parameters
    ----------
    node_address : str
      the node address.
      
    lst_eth_addrs : list
      list of Ethereum addresses.

    Returns
    -------
    bool
      True if the node address is in the list of Ethereum addresses.

    """
    eth_addr = self.node_address_to_eth_address(node_address)
    return eth_addr in lst_eth_addrs


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
        "eth_signed_data" : types,
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
    
    
    
  def eth_sign_node_epochs(
    self, 
    node, 
    epochs, 
    epochs_vals, 
    signature_only=True, 
    use_evm_node_addr=True
  ):
    """
    Signs the node availability

    Parameters
    ----------
    node : str
        The node address to sign. Either the node address or the Ethereum address based on `use_evm_node_addr`.
        
    epochs : list of int
        The epochs to sign.
        
    epochs_vals : list of int
        The values for each epoch.
        
    signature_only : bool, optional
        Whether to return only the signature. The default is True.
        
    use_evm_node_addr : bool, optional
        Whether to use the Ethereum address of the node. The default is True.

    Returns
    -------
    str
        The signature of the message.
    """
    if use_evm_node_addr:
      types = ["address", "uint256[]", "uint256[]"]  
    else:
      types = ["string", "uint256[]", "uint256[]"]
    values = [node, epochs, epochs_vals]
    result = self.eth_sign_message(types, values)
    if signature_only:
      return result["signature"]
    return result
  
    
  