import json
import base64
import datetime
import datetime as dt
import inspect
import os
import uuid
from copy import deepcopy


from ratio1 import Logger, const
from ratio1.const.base import BCct

try:
  import numpy as np
except Exception:
  np = None

try:
  import torch
except Exception:
  torch = None
from ratio1.bc import DefaultBlockEngine

SIGN_CANON_V_KEY = getattr(BCct, "SIGN_CANON_V", "SIGN_CANON_V")
TEST_MODE = os.environ.get("RATIO1_TEST_MODE", "workspace")
COMPAT_FIXTURE_PATH = os.environ.get("RATIO1_COMPAT_FIXTURE")


class _LegacyComplexJsonEncoder(json.JSONEncoder):
  """
  Test-local copy of the legacy encoder so the script can run against
  installed releases that do not export the private workspace symbol.
  """
  def default(self, obj):
    if np is not None and isinstance(obj, np.integer):
      return int(obj)
    elif np is not None and isinstance(obj, np.floating):
      return float(obj)
    elif np is not None and isinstance(obj, np.ndarray):
      return obj.tolist()
    elif isinstance(obj, datetime.datetime):
      return obj.strftime("%Y-%m-%d %H:%M:%S")
    else:
      return super(_LegacyComplexJsonEncoder, self).default(obj)

  def iterencode(self, o, _one_shot=False):
    markers = {} if self.check_circular else None
    _encoder = json.encoder.encode_basestring_ascii if self.ensure_ascii else json.encoder.encode_basestring

    def floatstr(o, allow_nan=self.allow_nan, _repr=float.__repr__, _inf=json.encoder.INFINITY, _neginf=-json.encoder.INFINITY):
      if o != o:
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

    indent = self.indent
    if indent is not None and not isinstance(indent, str):
      indent = ' ' * indent

    _iterencode = json.encoder._make_iterencode(
      markers, self.default, _encoder, indent, floatstr,
      self.key_separator, self.item_separator, self.sort_keys,
      self.skipkeys, _one_shot
    )
    return _iterencode(o, 0)


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

  def _old_style_verify(engine, payload):
    """
    Simulate a pre-SIGN_CANON_V verifier that hashes unknown fields as data.
    """
    old_non_data_fields = {
      BCct.SIGN,
      BCct.SENDER,
      BCct.HASH,
      BCct.ETH_SIGN,
      BCct.ETH_SENDER,
    }
    old_data = {k: payload[k] for k in payload if k not in old_non_data_fields}
    bdata_json = engine._dict_to_json(
      deepcopy(old_data),
      replace_nan=True,
      inplace=True,
    ).encode("utf-8")
    bin_hexdigest, hexdigest = engine._compute_hash(bdata_json)
    received_digest = payload.get(BCct.HASH)
    if received_digest is not None and hexdigest != received_digest:
      return False, "Corrupted digest!"

    bsignature = engine._text_to_binary(payload[BCct.SIGN])
    pk = engine._address_to_pk(payload[BCct.SENDER])
    verify_msg = engine._verify(
      public_key=pk,
      signature=bsignature,
      data=bin_hexdigest if received_digest is not None else bdata_json,
    )
    return verify_msg.valid, verify_msg.message

  def _dump_fixture(path, payload_current, payload_current_noneth):
    fixture = {
      "payload_current": _fixture_sanitize(payload_current),
      "payload_current_noneth": _fixture_sanitize(payload_current_noneth),
    }
    with open(path, "w", encoding="utf-8") as fh:
      json.dump(fixture, fh, indent=2, sort_keys=True)

  def _dump_legacy_fixture(path, payload_legacy, payload_legacy_noneth=None):
    fixture = {
      "payload_legacy": _fixture_sanitize(payload_legacy),
    }
    if payload_legacy_noneth is not None:
      fixture["payload_legacy_noneth"] = _fixture_sanitize(payload_legacy_noneth)
    with open(path, "w", encoding="utf-8") as fh:
      json.dump(fixture, fh, indent=2, sort_keys=True)

  def _verify_fixture(engine_eth, engine_noneth, fixture_path):
    with open(fixture_path, "r", encoding="utf-8") as fh:
      fixture = json.load(fh)

    payload_current = fixture["payload_current"]
    payload_current_noneth = fixture["payload_current_noneth"]

    result_eth = engine_eth.verify(deepcopy(payload_current))
    print(f"\n\ncompat check 1 (installed verifier on workspace v2 payload): {result_eth}\n\n")
    assert result_eth.valid, result_eth

    result_noneth = engine_noneth.verify(deepcopy(payload_current_noneth))
    print(
      f"\n\ncompat check 2 (installed non-ETH verifier on workspace v2 payload): "
      f"{result_noneth}\n\n"
    )
    assert result_noneth.valid, result_noneth

  def _verify_legacy_fixture(engine, engine_noneth, fixture_path):
    with open(fixture_path, "r", encoding="utf-8") as fh:
      fixture = json.load(fh)

    payload_legacy = fixture["payload_legacy"]
    payload_legacy_noneth = fixture.get("payload_legacy_noneth")

    result_legacy = engine.verify(deepcopy(payload_legacy))
    print(f"\n\ncompat check 3 (workspace verifier on installed legacy payload): {result_legacy}\n\n")
    assert result_legacy.valid, result_legacy

    if payload_legacy_noneth is not None:
      result_legacy_noneth = engine_noneth.verify(deepcopy(payload_legacy_noneth))
      print(
        f"\n\ncompat check 4 (workspace non-ETH verifier on installed legacy payload): "
        f"{result_legacy_noneth}\n\n"
      )
      assert result_legacy_noneth.valid, result_legacy_noneth

  def _fixture_sanitize(obj):
    if np is not None:
      if isinstance(obj, np.integer):
        return int(obj)
      if isinstance(obj, np.floating):
        as_float = float(obj)
        if as_float != as_float or as_float in (float("inf"), float("-inf")):
          return None
        return as_float
      if isinstance(obj, np.ndarray):
        return [_fixture_sanitize(v) for v in obj.tolist()]
    if isinstance(obj, datetime.datetime):
      return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, dict):
      return {str(k): _fixture_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
      return [_fixture_sanitize(v) for v in obj]
    if isinstance(obj, float):
      if obj != obj or obj in (float("inf"), float("-inf")):
        return None
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

  eng_noneth = DefaultBlockEngine(
    log=l,
    name="default-noneth",
    config={
      "PEM_FILE": "default-noneth.pem",
      "PASSWORD": None,
      "PEM_,LOCATION": "data",
    },
    eth_enabled=False,
  )

  supports_canon_attrs = hasattr(eng2, "SIGN_CANON_V_CURRENT") and hasattr(eng2, "SIGN_CANON_V_LEGACY")
  supports_include_sign_canon = "include_sign_canon" in inspect.signature(eng1.compute_hash).parameters
  supports_stats = hasattr(eng2, "_verify_canon_stats")
  workspace_checks_enabled = (
    TEST_MODE != "release"
    and supports_canon_attrs
    and supports_include_sign_canon
    and supports_stats
  )

  if TEST_MODE == "release-compat":
    if not COMPAT_FIXTURE_PATH:
      raise RuntimeError("RATIO1_COMPAT_FIXTURE is required for release-compat mode")
    _verify_fixture(eng2, eng_noneth, COMPAT_FIXTURE_PATH)
    raise SystemExit(0)

  if TEST_MODE == "workspace-compat":
    if not COMPAT_FIXTURE_PATH:
      raise RuntimeError("RATIO1_COMPAT_FIXTURE is required for workspace-compat mode")
    _verify_legacy_fixture(eng2, eng_noneth, COMPAT_FIXTURE_PATH)
    raise SystemExit(0)
  
  # Current (v2) signing path, includes SIGN_CANON_V in the hashed payload.
  data1 = deepcopy(dct_data)
  if torch is not None:
    data1["torch_tensor"] = torch.tensor([1.0, 2.0, 3.0])
  str_for_hash1 = eng1._generate_data_for_hash(data1, replace_nan=True)
  print(f"\n\n{str_for_hash1}\n\n")
  sign1 = eng1.sign(data1)
  print(f"sign canon v: {data1.get(SIGN_CANON_V_KEY)}")
  msg1 = l.safe_dumps_json(data1, replace_nan=False, ensure_ascii=False)
  print(f"\n\n{msg1}\n\n")
  
  
  msg2 = msg1
  data2 = json.loads(msg2)
  str_for_hash2 = eng2._generate_data_for_hash(data2, replace_nan=True)
  print(f"\n\n{str_for_hash2}\n\n")
  result = eng2.verify(data2)
  print(f"\n\ncheck 1: {result}\n\n")
  assert result.valid

  # Simulate an older SDK instance that does not know SIGN_CANON_V as metadata.
  old_ok, old_msg = _old_style_verify(eng2, data2)
  print(f"\n\ncheck 1b (old verifier on current payload): {(old_ok, old_msg)}\n\n")
  assert old_ok, old_msg

  # Same backward-compatibility check for the non-ETH verifier path.
  data2_noneth = deepcopy(data2)
  data2_noneth.pop(BCct.ETH_SENDER, None)
  data2_noneth.pop(BCct.ETH_SIGN, None)
  old_noneth_ok, old_noneth_msg = _old_style_verify(eng_noneth, data2_noneth)
  print(f"\n\ncheck 1c (old non-ETH verifier on current payload): {(old_noneth_ok, old_noneth_msg)}\n\n")
  assert old_noneth_ok, old_noneth_msg

  if TEST_MODE == "emit-compat-fixture":
    if not COMPAT_FIXTURE_PATH:
      raise RuntimeError("RATIO1_COMPAT_FIXTURE is required for emit-compat-fixture mode")
    _dump_fixture(COMPAT_FIXTURE_PATH, data2, data2_noneth)
    print(f"\n\ncompat fixture written to {COMPAT_FIXTURE_PATH}\n\n")
    raise SystemExit(0)

  if workspace_checks_enabled:
    stats_after_v2 = deepcopy(eng2._verify_canon_stats)
    sender_stats = stats_after_v2["by_sender"][data2[BCct.SENDER]]
    assert stats_after_v2["total"][eng2.SIGN_CANON_V_CURRENT] >= 1
    assert sender_stats[eng2.SIGN_CANON_V_CURRENT] >= 1

  # Explicitly drop SIGN_CANON_V from a current message to show that the
  # unversioned fallback does not verify current signed payloads.
  if workspace_checks_enabled:
    data3 = deepcopy(data2)
    del data3[SIGN_CANON_V_KEY]
    result2 = eng2.verify(data3)
    print(f"\n\ncheck 2 (no SIGN_CANON_V on current payload): {result2}\n\n")
    assert not result2.valid

  # Direct-sign path without digest should still verify for v2 payloads.
  if workspace_checks_enabled:
    data5 = deepcopy(dct_data)
    sign5 = eng1.sign(data5, use_digest=False)
    result5 = eng2.verify(data5)
    print(f"\n\ncheck 2b (v2 use_digest=False): {result5}\n\n")
    assert sign5 == data5[BCct.SIGN]
    assert result5.valid

  # v2 signing with add_data=False should still hash staged SIGN_CANON_V correctly.
  if workspace_checks_enabled:
    data6 = deepcopy(dct_data)
    sign6 = eng1.sign(data6, add_data=False)
    assert SIGN_CANON_V_KEY not in data6
    data6[BCct.SIGN] = sign6
    data6[BCct.SENDER] = eng1.address
    data6[SIGN_CANON_V_KEY] = eng1.SIGN_CANON_V_CURRENT
    data6[BCct.HASH] = eng1.compute_hash(
      {**deepcopy(dct_data), SIGN_CANON_V_KEY: eng1.SIGN_CANON_V_CURRENT},
      include_sign_canon=True,
    )
    result6 = eng2.verify(data6)
    print(f"\n\ncheck 2c (v2 add_data=False): {result6}\n\n")
    assert result6.valid

  if TEST_MODE == "emit-legacy-fixture":
    if not COMPAT_FIXTURE_PATH:
      raise RuntimeError("RATIO1_COMPAT_FIXTURE is required for emit-legacy-fixture mode")
    data_legacy_noneth = deepcopy(dct_data)
    eng_noneth.sign(data_legacy_noneth)
    _dump_legacy_fixture(COMPAT_FIXTURE_PATH, data2, data_legacy_noneth)
    print(f"\n\nlegacy compat fixture written to {COMPAT_FIXTURE_PATH}\n\n")
    raise SystemExit(0)

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
  assert result3.valid
  # With SIGN_CANON_V=v1 => should verify via legacy path only
  data4[SIGN_CANON_V_KEY] = "v1"
  result4 = eng2.verify(data4)
  print(f"\n\ncheck 4 (legacy v1): {result4}\n\n")
  assert result4.valid

  if workspace_checks_enabled:
    stats_after_v1 = deepcopy(eng2._verify_canon_stats)
    sender_stats_v1 = stats_after_v1["by_sender"][data4[BCct.SENDER]]
    assert stats_after_v1["total"][eng2.SIGN_CANON_V_LEGACY] >= 1
    assert sender_stats_v1[eng2.SIGN_CANON_V_LEGACY] >= 1

  # Unknown canon version must fail cleanly.
  if workspace_checks_enabled:
    data7 = deepcopy(data2)
    data7[SIGN_CANON_V_KEY] = "v99"
    result7 = eng2.verify(data7)
    print(f"\n\ncheck 5 (unknown canon version): {result7}\n\n")
    assert not result7.valid

    data7_sign = deepcopy(dct_data)
    data7_sign[SIGN_CANON_V_KEY] = "v99"
    try:
      eng1.sign(data7_sign)
      raise AssertionError("sign() accepted an unknown signing canon version")
    except ValueError as exc:
      print(f"\n\ncheck 5b (sign rejects unknown canon version): {exc}\n\n")
      assert "Unknown signing canon version" in str(exc)

  # Mismatched labels must fail.
  if workspace_checks_enabled:
    data8 = deepcopy(data2)
    data8[SIGN_CANON_V_KEY] = eng2.SIGN_CANON_V_LEGACY
    result8 = eng2.verify(data8)
    print(f"\n\ncheck 6 (v2 payload mislabeled as v1): {result8}\n\n")
    assert not result8.valid

    data9 = deepcopy(data4)
    data9[SIGN_CANON_V_KEY] = eng2.SIGN_CANON_V_CURRENT
    result9 = eng2.verify(data9)
    print(f"\n\ncheck 7 (v1 payload mislabeled as v2): {result9}\n\n")
    assert not result9.valid

  if TEST_MODE == "release" and not workspace_checks_enabled:
    print("\n\nworkspace-only checks skipped for installed release\n\n")
  
  
  
  
  
  
  
  
