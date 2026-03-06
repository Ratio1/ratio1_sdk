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
  
  # Mixed-key nested dict for ordering + int-key normalization cases
  faulty_stuff = {  
    0: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
    4: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},  
    5: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
    6: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},  
    3333: {'something': 'wrong', 'number': 22, 'sss': [222, 'ppp']},
  }
  
  # Expanded payload to exercise multiple serialization paths and edge cases
  dct_data = {
    "faulty_stuff": faulty_stuff,
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
    dct_data.update({
      "np_float64": np.float64(9.99),
      "np_float32": np.float32(3.5),
      "np_array": np.array([[1, 2], [3, 4]]),
      "np_nan": np.nan,
      "np_inf": np.inf,
      "np_ninf": -np.inf,
    })

  # Legacy encoder can't emit valid JSON for np.float64 (it writes "np.float64(9.99)").
  # Convert numpy scalars to plain Python numbers for legacy signing tests.
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
  
  
  l = Logger("ENC", base_folder=".", app_folder="_local_cache")
  eng1 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )  

  eng2 = DefaultBlockEngine(
    log=l, 
    name="default",
    config={}
  )  
  
  # Current (v2) signing path, includes torch if available
  data1 = deepcopy(dct_data)
  if torch is not None:
    data1["torch_tensor"] = torch.tensor([1.0, 2.0, 3.0])
  str_for_hash1 = eng1._generate_data_for_hash(data1, replace_nan=True)
  print(f"\n\n{str_for_hash1}\n\n")
  sign1 = eng1.sign(data1)
  print(f"sign canon v: {data1.get(BCct.SIGN_CANON_V)}")
  msg1 = l.safe_dumps_json(data1, replace_nan=False, ensure_ascii=False)
  print(f"\n\n{msg1}\n\n")
  
  
  msg2 = msg1
  data2 = json.loads(msg2)
  str_for_hash2 = eng2._generate_data_for_hash(data2, replace_nan=True)
  print(f"\n\n{str_for_hash2}\n\n")
  result = eng2.verify(data2)
  print(f"\n\ncheck 1: {result}\n\n")

  # Verify fallback path for unversioned payloads (simulate legacy)
  data3 = deepcopy(data2)
  if BCct.SIGN_CANON_V in data3:
    del data3[BCct.SIGN_CANON_V]
  result2 = eng2.verify(data3)
  print(f"\n\ncheck 2 (no SIGN_CANON_V): {result2}\n\n")

  # Explicit legacy signing (v1 canon) and verify
  data4 = _legacy_sanitize(deepcopy(dct_data))
  if torch is not None:
    # Ensure legacy path does not include torch objects (legacy encoder omits torch handling)
    data4.pop("torch_tensor", None)
  bdata_json, bin_hexdigest, hexdigest = eng1.compute_hash(
    data4,
    return_all=True,
    replace_nan=True,
    encoder_cls=_LegacyComplexJsonEncoder,
  )
  legacy_signature = eng1._sign(
    data=bin_hexdigest,
    private_key=eng1._BaseBlockEngine__private_key,
    text=True,
  )
  data4[BCct.SIGN] = legacy_signature
  data4[BCct.SENDER] = eng1.address
  data4[BCct.HASH] = hexdigest
  # No SIGN_CANON_V => should still verify via fallback
  result3 = eng2.verify(data4)
  print(f"\n\ncheck 3 (legacy no SIGN_CANON_V): {result3}\n\n")
  # With SIGN_CANON_V=v1 => should verify via legacy path only
  data4[BCct.SIGN_CANON_V] = "v1"
  result4 = eng2.verify(data4)
  print(f"\n\ncheck 4 (legacy v1): {result4}\n\n")
  
  
  
  
  
  
  
  
