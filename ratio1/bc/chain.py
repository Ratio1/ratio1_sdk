import os
import base64

class _ChainMixin:
  def create_r1_token(self) -> str:
    """
    Create an online-usable token with the format "r1_<encoded>"
    that encapsulates both the SDK address (omitting '0x') and a nonce.
    """
    # Encode the SDK address (sans '0x') as UTF-8
    addr_bytes = self.address_no_prefix.encode('utf-8')

    # Generate an 8-byte random nonce
    nonce_bytes = os.urandom(8)

    # Add a delimiter (0x00) between address and nonce
    raw_data = addr_bytes + b'\x00' + nonce_bytes

    # Base64-encode the combined data
    encoded_part = base64.urlsafe_b64encode(raw_data).decode('utf-8')
    return f"r1_{encoded_part}"

  def check_r1_token(self, token: str, return_nonce: bool = False):
    """
    Verify the token’s format ("r1_<encoded>"), extract address and nonce.

    Parameters
    ----------
    token : str
      The token string (must start with "r1_").

    return_nonce : bool, optional
      If True, return (address, nonce). If False, return only address.

    Returns
    -------
    str or tuple
      - If return_nonce is False, returns the address (with "0x" prefix if needed).
      - If return_nonce is True, returns (address_str, nonce_hex).

    Raises
    ------
    ValueError
      If the token is malformed or doesn't start with "r1_".
    """
    if not token.startswith("r1_"):
      raise ValueError("Invalid token format. Missing 'r1_' prefix.")

    encoded_part = token[len("r1_"):]
    try:
      raw_data = base64.urlsafe_b64decode(encoded_part.encode('utf-8'))
    except Exception:
      raise ValueError("Invalid token: base64 decoding failed.")

    # Find our delimiter (0x00) separating address bytes from nonce
    delimiter_index = raw_data.find(b'\x00')
    if delimiter_index == -1 or delimiter_index == len(raw_data) - 1:
      raise ValueError("Invalid token structure: missing or misplaced delimiter.")

    addr_bytes = raw_data[:delimiter_index]
    nonce_bytes = raw_data[delimiter_index + 1:]

    # Convert the address bytes back to string. Optionally re-add "0x" if your logic requires.
    address_str = addr_bytes.decode('utf-8')
    address_str = self.maybe_add_prefix(address_str)

    # Convert the nonce to a hex string
    nonce_hex = nonce_bytes.hex()

    if return_nonce:
      return address_str, nonce_hex
    return address_str
