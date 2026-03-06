import json
import base64
import datetime as dt
import uuid
from copy import deepcopy


from ratio1 import Logger, const
from ratio1.const.base import BCct
from ratio1.bc.base import _LegacyComplexJsonEncoder

try:
  import numpy as np
except Exception:
  np = None

try:
  import torch
except Exception:
  torch = None
from ratio1.bc import DefaultBlockEngine


if __name__ == '__main__':
  
  # Baseline data matching the pre-existing PYTHON_MESSAGE signature (keep minimal/stable)
  _PYTHON_MESSAGE_DATA = {
    "9": 9,
    "2": 2,
    "3": 3,
    "10": {
      "2": 2,
      "100": 100,
      "1": 1
    },
  }

  # Expanded payload to exercise multiple serialization paths and edge cases
  _BASE_DATA = {
    "9": 9,
    "2": 2,
    "3": 3,
    "10": {
      "2": 2,
      "100": 100,
      "1": 1
    },
    "float_simple": 1.23,
    "float_intlike": 1.0,
    "float_exp": 1e-7,
    "float_neg": -0.25,
    "datetime": dt.datetime(2026, 3, 6, 0, 0, 0),
    "uuid_str": str(uuid.uuid4()),
    "bytes_b64": base64.b64encode(b"ratio1-test-bytes").decode(),
  }
  # Add numpy-specific values if available (np floats, arrays, NaN/Inf)
  if np is not None:
    _BASE_DATA.update({
      "np_float64": np.float64(9.99),
      "np_float32": np.float32(3.5),
      "np_array": np.array([[1, 2], [3, 4]]),
      "np_nan": np.nan,
      "np_inf": np.inf,
      "np_ninf": -np.inf,
    })

  _DATA = deepcopy(_BASE_DATA)
  
  PYTHON_MESSAGE = {
    **_PYTHON_MESSAGE_DATA,
    "EE_SIGN": "MEQCIEIz_Nfy9CJ0GYW1V7Iw0uFJAVzu1TnOWkCVYnrt8PNHAiB0JCk_pgzGGIMz-KIvOCC_BzbGB8jxkAb_OwPX7AQTyA==",
    "EE_SENDER": "0xai_AuN2SENcYNzRgbPUHVCFe6W1q-vieUKap2VY9mU_Fljy",
    "EE_HASH": "7d72cf5bd6cda16c86dfb2c2c4983464edda5bf78e1ca3a21139f5037454c6f3"
  }
   
  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )

  eng2_noneth = DefaultBlockEngine(
    eth_enabled=False,
    log=l, name="test1", 
    config={
        "PEM_FILE"     : "test1.pem",
        "PASSWORD"     : None,      
        "PEM_,LOCATION" : "data"
      }    
  )

  eng3_eth = DefaultBlockEngine(
    eth_enabled=True,
    log=l, name="test2", 
    config={
        "PEM_FILE"     : "test2.pem",
        "PASSWORD"     : None,      
        "PEM_,LOCATION" : "data"
      }    
  )
  
  v1 = eng1.verify(PYTHON_MESSAGE)
  l.P(f"check 1: {v1}", color='r' if not v1.valid else 'g')

  # Legacy signing helper (v1 canon). Uses sanitized data for legacy JSON compatibility.
  def _legacy_sanitize(obj):
    if np is not None:
      if isinstance(obj, np.floating):
        return float(obj)
      if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, dict):
      return {k: _legacy_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
      return [_legacy_sanitize(v) for v in obj]
    return obj

  # Legacy encoder can't emit valid JSON for np.float64 (it writes "np.float64(9.99)").
  # Convert numpy scalars to plain Python numbers for legacy signing tests.
  data_legacy = _legacy_sanitize(deepcopy(_BASE_DATA))
  bdata_json, bin_hexdigest, hexdigest = eng1.compute_hash(
    data_legacy,
    return_all=True,
    replace_nan=True,
    encoder_cls=_LegacyComplexJsonEncoder,
  )
  legacy_signature = eng1._sign(
    data=bin_hexdigest,
    private_key=eng1._BaseBlockEngine__private_key,
    text=True,
  )
  data_legacy[BCct.SIGN] = legacy_signature
  data_legacy[BCct.SENDER] = eng1.address
  data_legacy[BCct.HASH] = hexdigest
  # Intentionally leave SIGN_CANON_V unset to test fallback
  v1b = eng1.verify(data_legacy)
  l.P(f"check 1b (legacy no SIGN_CANON_V): {v1b}", color='r' if not v1b.valid else 'g')
  data_legacy[BCct.SIGN_CANON_V] = "v1"
  v1c = eng1.verify(data_legacy)
  l.P(f"check 1c (legacy v1): {v1c}", color='r' if not v1c.valid else 'g')
  
  data = deepcopy(_BASE_DATA)
  # Add torch tensor only for current (v2) signing path; legacy encoder omits torch handling
  if torch is not None:
    data["torch_tensor"] = torch.tensor([1.0, 2.0, 3.0])
  eng1.sign(data)
  l.P(f"sign canon v: {data.get(BCct.SIGN_CANON_V)}")
  l.P(f"data: {data}")
  
  v2 = eng2_noneth.verify(data)
  l.P(f"check 2.1: {v2}", color='r' if not v2.valid else 'g')
  eng2_noneth.set_eth_flag(True)
  v2 = eng2_noneth.verify(data)
  l.P(f"check 2.2: {v2}", color='r' if not v2.valid else 'g')
  eng2_noneth.set_eth_flag(False)
  
  v3 = eng3_eth.verify(data)
  l.P(f"check 3: {v3}", color='r' if not v3.valid else 'g')  
  
  
  data_noneth = deepcopy(_DATA)
  eng2_noneth.sign(data_noneth)
  l.P(f"sign canon v: {data_noneth.get(BCct.SIGN_CANON_V)}")
  l.P(f"data: {data_noneth}")
  
  v4 = eng1.verify(data_noneth)
  l.P(f"check 4: {v4}", color='r' if not v4.valid else 'g')
  
  v5 = eng3_eth.verify(data_noneth)
  l.P(f"check 5: {v5}", color='r' if not v5.valid else 'g')
