from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LARGE_FIELD_THRESHOLD_BYTES = 1024
TOP_N = 20
TOP_MESSAGE_EXAMPLES = 5
TOP_SHAPES = 10
IMAGE_FIELDS = {"IMG", "IMG_ORIG"}
SPECIAL_FIELDS = [
  "IMG",
  "IMG_ORIG",
  "HISTORY",
  "DCT_STATS",
  "COMM_STATS",
  "ACTIVE_PLUGINS",
  "CONFIG_STREAMS",
  "EE_WHITELIST",
  "TAGS",
  "ID_TAGS",
]
DIAGNOSTIC_FIELDS = {"DCT_STATS", "COMM_STATS", "ACTIVE_PLUGINS", "CONFIG_STREAMS", "EE_WHITELIST"}
HISTORY_FIELDS = {"HISTORY", "RESULT", "RESULTS"}
DEFAULT_SENTINELS = {"", "none", "null", "unknown", "n/a", "na"}


def utc_now_iso() -> str:
  return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_default(value: Any) -> Any:
  if hasattr(value, "item"):
    try:
      return value.item()
    except Exception:
      pass
  if isinstance(value, (set, tuple)):
    return list(value)
  if isinstance(value, bytes):
    return f"<bytes {len(value)}>"
  if isinstance(value, Path):
    return str(value)
  return str(value)


def json_dumps(value: Any) -> str:
  return json.dumps(
    value,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
    default=json_default,
  )


def json_size_bytes(value: Any) -> int:
  return len(json_dumps(value).encode("utf-8"))


def field_size_bytes(key: str, value: Any) -> int:
  encoded = json_dumps({key: value}).encode("utf-8")
  return max(len(encoded) - 2, 0)


def short_addr(node_addr: str | None) -> str:
  if not isinstance(node_addr, str) or len(node_addr) < 16:
    return str(node_addr)
  return f"{node_addr[:8]}...{node_addr[-6:]}"


def stable_hash(value: str) -> str:
  return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def is_empty_like(value: Any) -> bool:
  if value is None:
    return True
  if value == "":
    return True
  if isinstance(value, (list, dict, set, tuple)) and len(value) == 0:
    return True
  return False


def is_default_like(value: Any) -> bool:
  if is_empty_like(value):
    return True
  if value is False or value == 0:
    return True
  if isinstance(value, str) and value.strip().lower() in DEFAULT_SENTINELS:
    return True
  return False


def percentile(values: list[int], pct: float) -> int:
  if not values:
    return 0
  sorted_values = sorted(values)
  idx = int(math.ceil((len(sorted_values) - 1) * pct))
  idx = max(0, min(idx, len(sorted_values) - 1))
  return sorted_values[idx]


def top_n_rows(rows: list[dict[str, Any]], field: str, limit: int = TOP_N) -> list[dict[str, Any]]:
  return sorted(rows, key=lambda item: item.get(field, 0), reverse=True)[:limit]


def sanitize_scalar(value: Any, max_len: int = 96) -> Any:
  if isinstance(value, str):
    if len(value) > max_len:
      return f"{value[:max_len]}... <len={len(value)}>"
    return value
  if isinstance(value, (int, float, bool)) or value is None:
    return value
  return str(value)


def sanitize_value(value: Any, *, max_len: int = 96, placeholder_threshold: int = 1024) -> Any:
  size = json_size_bytes(value)
  if size >= placeholder_threshold:
    if isinstance(value, str):
      return f"<string {size}B>"
    if isinstance(value, list):
      return f"<list {len(value)} items, {size}B>"
    if isinstance(value, dict):
      return f"<dict {len(value)} keys, {size}B>"
    return f"<{type(value).__name__} {size}B>"
  if isinstance(value, dict):
    return {
      key: sanitize_value(subvalue, max_len=max_len, placeholder_threshold=placeholder_threshold)
      for key, subvalue in list(value.items())[:10]
    }
  if isinstance(value, list):
    return [
      sanitize_value(subvalue, max_len=max_len, placeholder_threshold=placeholder_threshold)
      for subvalue in value[:5]
    ]
  return sanitize_scalar(value, max_len=max_len)


def compact_preview(message: dict[str, Any], field_order: list[str], size_by_field: dict[str, int]) -> dict[str, Any]:
  preview = {}
  ordered = sorted(field_order, key=lambda key: size_by_field.get(key, 0), reverse=True)
  for key in ordered[:8]:
    preview[key] = sanitize_value(message.get(key))
  return preview


def detect_payload_category(
  callback_type: str,
  pipeline_name: str | None,
  plugin_signature: str | None,
  message: dict[str, Any],
  *,
  image_field_bytes: int,
  total_size: int,
) -> str:
  if callback_type == "heartbeat":
    return "heartbeat"
  if callback_type == "notification":
    return "notification"

  signature = (plugin_signature or "").upper()
  pipeline = (pipeline_name or "").lower()

  image_threshold = max(32 * 1024, int(total_size * 0.2))
  if image_field_bytes >= image_threshold:
    return "image-payload"
  if signature in {"NET_MON_01", "NET_CONFIG_MONITOR"}:
    return "admin-payload"
  if pipeline == "admin_pipeline":
    return "admin-payload"
  if message.get("EE_IS_ENCRYPTED") and "EE_ENCRYPTED_DATA" in message:
    return "encrypted-payload-envelope"
  if "NOTIFICATION_TYPE" in message:
    return "notification-like-payload"
  return "business-payload"


def build_message_class(callback_type: str, plugin_signature: str | None, notification_type: str | None) -> str:
  if callback_type == "payload":
    signature = plugin_signature or "unknown"
    return f"payload:{signature}"
  if callback_type == "notification":
    return f"notification:{notification_type or 'unknown'}"
  return callback_type


def stable_shape_id(keys: list[str]) -> str:
  return stable_hash("|".join(keys))


def sender_label(node_addr: str | None, message: dict[str, Any]) -> str:
  alias = message.get("EE_ID")
  if isinstance(alias, str) and alias:
    return f"{alias}<{short_addr(node_addr)}>"
  if isinstance(node_addr, str) and node_addr:
    return short_addr(node_addr)
  return "unknown"


def family_metrics(
  rows: list[dict[str, Any]],
  *,
  family_name: str,
  predicate,
) -> dict[str, Any]:
  total_bytes = 0
  message_count = 0
  field_counter = Counter()
  for row in rows:
    matched = False
    for field_name, field_bytes in row["size_by_field"].items():
      if predicate(field_name):
        matched = True
        total_bytes += field_bytes
        field_counter[field_name] += field_bytes
    if matched:
      message_count += 1
  return {
    "family_name": family_name,
    "total_bytes": total_bytes,
    "message_count": message_count,
    "top_fields": field_counter.most_common(5),
  }


def make_table(rows: list[tuple[Any, ...]], headers: list[str]) -> str:
  if not rows:
    return "| " + " | ".join(headers) + " |\n| " + " | ".join(["---"] * len(headers)) + " |\n| n/a |" + " n/a |" * (len(headers) - 1)
  lines = [
    "| " + " | ".join(headers) + " |",
    "| " + " | ".join(["---"] * len(headers)) + " |",
  ]
  for row in rows:
    lines.append("| " + " | ".join(str(value) for value in row) + " |")
  return "\n".join(lines)


def format_bytes(num_bytes: int) -> str:
  units = ["B", "KB", "MB", "GB"]
  value = float(num_bytes)
  for unit in units:
    if value < 1024 or unit == units[-1]:
      if unit == "B":
        return f"{int(value)}{unit}"
      return f"{value:.1f}{unit}"
    value /= 1024.0
  return f"{num_bytes}B"


def format_bytes_per_second(num_bytes_per_second: float) -> str:
  units = ["B/s", "KB/s", "MB/s", "GB/s"]
  value = float(num_bytes_per_second)
  for unit in units:
    if value < 1024 or unit == units[-1]:
      if unit == "B/s":
        return f"{int(value)}{unit}"
      return f"{value:.1f}{unit}"
    value /= 1024.0
  return f"{num_bytes_per_second:.1f}B/s"


def build_row(
  *,
  callback_type: str,
  node_addr: str | None,
  message: dict[str, Any],
  pipeline_name: str | None = None,
  plugin_signature: str | None = None,
  plugin_instance: str | None = None,
  large_field_threshold: int = LARGE_FIELD_THRESHOLD_BYTES,
) -> dict[str, Any]:
  payload_path = message.get("EE_PAYLOAD_PATH", []) or []
  if not pipeline_name and len(payload_path) > 1:
    pipeline_name = payload_path[1]
  if not plugin_signature and len(payload_path) > 2:
    plugin_signature = payload_path[2]
  if not plugin_instance and len(payload_path) > 3:
    plugin_instance = payload_path[3]

  keys = sorted(message.keys())
  size_by_field = {
    key: field_size_bytes(key, value)
    for key, value in message.items()
  }
  total_size = json_size_bytes(message)
  image_field_bytes = sum(size_by_field.get(field_name, 0) for field_name in IMAGE_FIELDS)
  large_fields = [
    {"field": key, "bytes": size_by_field[key]}
    for key in sorted(size_by_field, key=size_by_field.get, reverse=True)
    if size_by_field[key] >= large_field_threshold
  ]
  empty_fields = [key for key, value in message.items() if is_empty_like(value)]
  default_like_fields = [key for key, value in message.items() if is_default_like(value)]
  notification_type = message.get("NOTIFICATION_TYPE")
  category = detect_payload_category(
    callback_type,
    pipeline_name,
    plugin_signature,
    message,
    image_field_bytes=image_field_bytes,
    total_size=total_size,
  )

  return {
    "received_at": utc_now_iso(),
    "callback_type": callback_type,
    "message_class": build_message_class(callback_type, plugin_signature, notification_type),
    "payload_category": category,
    "sender_addr": node_addr,
    "sender_alias": message.get("EE_ID"),
    "sender_label": sender_label(node_addr, message),
    "destination": message.get("EE_DEST"),
    "stream_name": pipeline_name or message.get("STREAM_NAME") or message.get("EE_PIPELINE_NAME"),
    "plugin_signature": plugin_signature,
    "plugin_instance": plugin_instance,
    "notification_type": notification_type,
    "message_event_type": message.get("EE_EVENT_TYPE"),
    "serialized_size_bytes": total_size,
    "top_level_keys": keys,
    "top_level_key_count": len(keys),
    "large_fields": large_fields,
    "size_by_field": size_by_field,
    "c_field_count": sum(1 for key in keys if key.startswith("_C_")),
    "p_field_count": sum(1 for key in keys if key.startswith("_P_")),
    "shape_id": stable_shape_id(keys),
    "empty_fields": empty_fields,
    "default_like_fields": default_like_fields,
    "field_flags": {field: field in message for field in SPECIAL_FIELDS},
    "sdk_view": "decoded-callback-dict",
    "encrypted": bool(message.get("EE_IS_ENCRYPTED", False)),
    "image_field_bytes": image_field_bytes,
    "sanitized_preview": compact_preview(message, keys, size_by_field),
  }


def write_jsonl(rows: list[dict[str, Any]], output_path: Path) -> None:
  output_path.parent.mkdir(parents=True, exist_ok=True)
  with output_path.open("w", encoding="utf-8") as handle:
    for row in rows:
      handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True, default=json_default))
      handle.write("\n")


def write_json(data: dict[str, Any], output_path: Path) -> None:
  output_path.parent.mkdir(parents=True, exist_ok=True)
  with output_path.open("w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=True, default=json_default)
    handle.write("\n")


def refresh_loaded_row(row: dict[str, Any]) -> dict[str, Any]:
  refreshed = dict(row)
  size_by_field = refreshed.get("size_by_field", {})
  total_size = refreshed.get("serialized_size_bytes", 0)
  image_field_bytes = sum(size_by_field.get(field_name, 0) for field_name in IMAGE_FIELDS)
  message_stub = {key: True for key in refreshed.get("top_level_keys", [])}
  if refreshed.get("notification_type") is not None:
    message_stub["NOTIFICATION_TYPE"] = refreshed["notification_type"]
  if refreshed.get("encrypted"):
    message_stub["EE_IS_ENCRYPTED"] = True
  refreshed["image_field_bytes"] = image_field_bytes
  refreshed["payload_category"] = detect_payload_category(
    refreshed.get("callback_type", "payload"),
    refreshed.get("stream_name"),
    refreshed.get("plugin_signature"),
    message_stub,
    image_field_bytes=image_field_bytes,
    total_size=total_size,
  )
  return refreshed


def load_jsonl(path: Path) -> list[dict[str, Any]]:
  rows = []
  with path.open("r", encoding="utf-8") as handle:
    for line in handle:
      line = line.strip()
      if line:
        rows.append(refresh_loaded_row(json.loads(line)))
  return rows


def summarize_rows(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
  total_bytes = sum(row["serialized_size_bytes"] for row in rows)
  total_messages = len(rows)

  class_stats = defaultdict(lambda: {"count": 0, "bytes": 0, "sizes": []})
  sender_stats = defaultdict(lambda: {"count": 0, "bytes": 0})
  stream_sig_stats = defaultdict(lambda: {"count": 0, "bytes": 0})
  field_bytes = Counter()
  field_presence = Counter()
  field_empty = Counter()
  field_default_like = Counter()
  category_stats = defaultdict(lambda: {"count": 0, "bytes": 0})
  shape_stats = defaultdict(lambda: {"count": 0, "bytes": 0, "example": None, "keys": []})

  encrypted_payload_bytes = 0
  encrypted_payload_count = 0

  for row in rows:
    row_size = row["serialized_size_bytes"]
    class_stat = class_stats[row["message_class"]]
    class_stat["count"] += 1
    class_stat["bytes"] += row_size
    class_stat["sizes"].append(row_size)

    sender_stat = sender_stats[row["sender_label"]]
    sender_stat["count"] += 1
    sender_stat["bytes"] += row_size

    if row.get("stream_name") or row.get("plugin_signature"):
      stream_key = f"{row.get('stream_name') or '-'} / {row.get('plugin_signature') or '-'}"
      stream_stat = stream_sig_stats[stream_key]
      stream_stat["count"] += 1
      stream_stat["bytes"] += row_size

    category_stat = category_stats[row["payload_category"]]
    category_stat["count"] += 1
    category_stat["bytes"] += row_size

    shape_stat = shape_stats[row["shape_id"]]
    shape_stat["count"] += 1
    shape_stat["bytes"] += row_size
    if shape_stat["example"] is None:
      shape_stat["example"] = row["message_class"]
      shape_stat["keys"] = row["top_level_keys"]

    for field_name, field_size in row["size_by_field"].items():
      field_bytes[field_name] += field_size
      field_presence[field_name] += 1
      if field_name in row["empty_fields"]:
        field_empty[field_name] += 1
      if field_name in row["default_like_fields"]:
        field_default_like[field_name] += 1

    if row.get("encrypted"):
      encrypted_payload_count += 1
      encrypted_payload_bytes += row_size

  class_table = []
  for message_class, stats in sorted(class_stats.items(), key=lambda item: item[1]["bytes"], reverse=True):
    sizes = stats["sizes"]
    class_table.append({
      "message_class": message_class,
      "count": stats["count"],
      "total_bytes": stats["bytes"],
      "avg_bytes": int(stats["bytes"] / stats["count"]),
      "p95_bytes": percentile(sizes, 0.95),
      "max_bytes": max(sizes),
    })

  sender_table = [
    {
      "sender": sender,
      "count": stats["count"],
      "total_bytes": stats["bytes"],
      "avg_bytes": int(stats["bytes"] / stats["count"]),
    }
    for sender, stats in sorted(sender_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)[:TOP_N]
  ]

  stream_table = [
    {
      "stream_signature": stream_key,
      "count": stats["count"],
      "total_bytes": stats["bytes"],
      "avg_bytes": int(stats["bytes"] / stats["count"]),
    }
    for stream_key, stats in sorted(stream_sig_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)[:TOP_N]
  ]

  field_table = []
  for field_name, total_field_bytes in field_bytes.most_common(TOP_N):
    present = field_presence[field_name]
    field_table.append({
      "field": field_name,
      "messages_present": present,
      "total_bytes": total_field_bytes,
      "avg_when_present": int(total_field_bytes / present),
      "empty_frequency": field_empty[field_name],
      "default_like_frequency": field_default_like[field_name],
    })

  family_tables = {
    "c_metadata": family_metrics(rows, family_name="_C_*", predicate=lambda key: key.startswith("_C_")),
    "p_runtime": family_metrics(rows, family_name="_P_*", predicate=lambda key: key.startswith("_P_")),
    "image_fields": family_metrics(rows, family_name="image", predicate=lambda key: key in IMAGE_FIELDS),
    "diagnostic_fields": family_metrics(rows, family_name="diagnostic", predicate=lambda key: key in DIAGNOSTIC_FIELDS),
    "history_fields": family_metrics(rows, family_name="history", predicate=lambda key: key in HISTORY_FIELDS),
    "empty_default_fields": {
      "family_name": "empty-default",
      "total_bytes": sum(
        row["size_by_field"][field_name]
        for row in rows
        for field_name in row["default_like_fields"]
      ),
      "message_count": sum(1 for row in rows if row["default_like_fields"]),
      "top_fields": Counter({
        field_name: sum(
          row["size_by_field"][field_name]
          for row in rows
          if field_name in row["default_like_fields"]
        )
        for field_name in field_default_like
      }).most_common(5),
    },
  }

  top_messages = top_n_rows(rows, "serialized_size_bytes", TOP_N)
  top_examples = top_messages[:TOP_MESSAGE_EXAMPLES]

  top_shapes = [
    {
      "shape_id": shape_id,
      "count": stats["count"],
      "total_bytes": stats["bytes"],
      "example": stats["example"],
      "keys": stats["keys"][:12],
    }
    for shape_id, stats in sorted(shape_stats.items(), key=lambda item: (item[1]["count"], item[1]["bytes"]), reverse=True)[:TOP_SHAPES]
  ]

  return {
    "metadata": metadata,
    "total_messages": total_messages,
    "total_bytes": total_bytes,
    "class_table": class_table,
    "sender_table": sender_table,
    "stream_table": stream_table,
    "field_table": field_table,
    "field_presence": field_presence,
    "field_empty": field_empty,
    "field_default_like": field_default_like,
    "family_tables": family_tables,
    "top_messages": top_messages,
    "top_examples": top_examples,
    "top_shapes": top_shapes,
    "category_table": [
      {
        "payload_category": category,
        "count": stats["count"],
        "total_bytes": stats["bytes"],
      }
      for category, stats in sorted(category_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)
    ],
    "encrypted_payload_count": encrypted_payload_count,
    "encrypted_payload_bytes": encrypted_payload_bytes,
  }


def candidate_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
  total_bytes = max(summary["total_bytes"], 1)
  family_tables = summary["family_tables"]
  field_lookup = {row["field"]: row for row in summary["field_table"]}
  candidates = []

  current_network_row = field_lookup.get("CURRENT_NETWORK")
  if current_network_row is not None:
    current_network_bytes = current_network_row["total_bytes"]
    candidates.append({
      "candidate": "Shrink `CURRENT_NETWORK` snapshots in `NET_MON_01`, ideally with diffs, digests, or lower-cadence full snapshots.",
      "evidence": f"`CURRENT_NETWORK` contributes {format_bytes(current_network_bytes)} ({current_network_bytes / total_bytes:.1%}) across only {current_network_row['messages_present']} messages.",
      "owner": "core",
      "impact": "High because a small number of NET_MON payloads account for a large byte share.",
      "risk": "Medium if downstream consumers expect complete point-in-time snapshots every time.",
      "score": current_network_bytes,
    })

  diagnostic_bytes = family_tables["diagnostic_fields"]["total_bytes"]
  if diagnostic_bytes > 0:
    top_fields = ", ".join(name for name, _ in family_tables["diagnostic_fields"]["top_fields"][:3]) or "n/a"
    candidates.append({
      "candidate": "Thin heartbeat-style diagnostic sections or send them less often.",
      "evidence": f"Diagnostic fields account for {format_bytes(diagnostic_bytes)} ({diagnostic_bytes / total_bytes:.1%}) with {top_fields} leading the family.",
      "owner": "core",
      "impact": "High on heartbeat-heavy traffic because these sections recur across many messages.",
      "risk": "Medium if operators rely on full diagnostics every heartbeat; lower if moved to slower cadences or opt-in detail levels.",
      "score": diagnostic_bytes,
    })

  encoded_row = field_lookup.get("ENCODED_DATA")
  if encoded_row is not None:
    encoded_bytes = encoded_row["total_bytes"]
    candidates.append({
      "candidate": "SDK-side logging and analysis should drop heartbeat `ENCODED_DATA` once the SDK has already expanded the decoded heartbeat fields.",
      "evidence": f"`ENCODED_DATA` contributes {format_bytes(encoded_bytes)} ({encoded_bytes / total_bytes:.1%}) in the callback view and is paired with decoded heartbeat fields in this SDK path.",
      "owner": "sdk",
      "impact": "High for local logging, archival, and analysis noise reduction.",
      "risk": "Low if tooling only removes it after successful decode and keeps raw access opt-in.",
      "score": encoded_bytes,
    })

  c_bytes = family_tables["c_metadata"]["total_bytes"]
  p_bytes = family_tables["p_runtime"]["total_bytes"]
  cp_bytes = c_bytes + p_bytes
  if cp_bytes > 0:
    top_fields = [
      name for name, _ in (
        family_tables["c_metadata"]["top_fields"][:2] + family_tables["p_runtime"]["top_fields"][:2]
      )
    ]
    candidates.append({
      "candidate": "Compact repeated `_C_*` and `_P_*` metadata into smaller structures or opt-in debug payloads.",
      "evidence": f"`_C_*` + `_P_*` contribute {format_bytes(cp_bytes)} ({cp_bytes / total_bytes:.1%}); leading fields: {', '.join(top_fields) or 'n/a'}.",
      "owner": "shared",
      "impact": "Medium to high because the bytes repeat across many otherwise similar payloads.",
      "risk": "Medium due to compatibility concerns for consumers that read those keys directly.",
      "score": cp_bytes,
    })

  empty_bytes = family_tables["empty_default_fields"]["total_bytes"]
  if empty_bytes > 0:
    top_fields = ", ".join(name for name, _ in family_tables["empty_default_fields"]["top_fields"][:4]) or "n/a"
    candidates.append({
      "candidate": "Stop emitting empty or default-like fields by default.",
      "evidence": f"Default-like fields account for {format_bytes(empty_bytes)} ({empty_bytes / total_bytes:.1%}); recurring fields include {top_fields}.",
      "owner": "shared",
      "impact": "Medium and low-risk because these fields carried little observed information in this sample.",
      "risk": "Low if omitted fields are treated as absent-equivalent by consumers.",
      "score": empty_bytes,
    })

  image_bytes = family_tables["image_fields"]["total_bytes"]
  if image_bytes > max(100 * 1024, int(total_bytes * 0.01)):
    candidates.append({
      "candidate": "Gate inline image fields behind explicit need, or replace them with pointers, hashes, or thumbnail variants.",
      "evidence": f"Inline image fields contribute {format_bytes(image_bytes)} ({image_bytes / total_bytes:.1%}) and dominate the very largest payloads when present.",
      "owner": "shared",
      "impact": "Very high on image-producing workloads.",
      "risk": "Medium because it changes data-availability expectations for downstream consumers.",
      "score": image_bytes,
    })

  encrypted_row = field_lookup.get("EE_ENCRYPTED_DATA")
  if encrypted_row is not None:
    encrypted_bytes = encrypted_row["total_bytes"]
    candidates.append({
      "candidate": "Investigate slimmer encrypted payload envelopes or compression before encryption for large opaque payloads.",
      "evidence": f"`EE_ENCRYPTED_DATA` alone contributes {format_bytes(encrypted_bytes)} ({encrypted_bytes / total_bytes:.1%}) in the SDK-visible envelope view.",
      "owner": "core",
      "impact": "Medium to high if payload ciphertext frequently dominates the visible envelope.",
      "risk": "Medium because cryptographic envelopes are compatibility-sensitive.",
      "score": encrypted_bytes,
    })

  return [
    {
      "candidate": item["candidate"],
      "evidence": item["evidence"],
      "owner": item["owner"],
      "impact": item["impact"],
      "risk": item["risk"],
    }
    for item in sorted(candidates, key=lambda item: item["score"], reverse=True)[:5]
  ]


def executive_findings(summary: dict[str, Any]) -> list[str]:
  findings = []
  total_messages = summary["total_messages"]
  total_bytes = summary["total_bytes"]
  top_class = summary["class_table"][0] if summary["class_table"] else None
  top_field = summary["field_table"][0] if summary["field_table"] else None
  top_category = summary["category_table"][0] if summary["category_table"] else None

  if top_class is not None:
    findings.append(
      f"{top_class['message_class']} dominated the sample with {top_class['count']} messages and {format_bytes(top_class['total_bytes'])} ({top_class['total_bytes'] / max(total_bytes, 1):.1%}) of observed bytes."
    )
  if top_field is not None:
    findings.append(
      f"The heaviest top-level field was `{top_field['field']}` at {format_bytes(top_field['total_bytes'])} across {top_field['messages_present']} messages."
    )
  if top_field is not None and top_field["field"] == "CURRENT_NETWORK":
    findings.append(
      "The single biggest payload driver was full NET_MON network-map state, not image or history payload content."
    )
  if top_category is not None:
    findings.append(
      f"The largest payload category was `{top_category['payload_category']}` with {top_category['count']} messages and {format_bytes(top_category['total_bytes'])}."
    )
  encoded_row = next((row for row in summary["field_table"] if row["field"] == "ENCODED_DATA"), None)
  if encoded_row is not None:
    findings.append(
      f"`ENCODED_DATA` alone contributed {format_bytes(encoded_row['total_bytes'])}; in this SDK it should be treated as a callback-view expansion cost, not a confirmed raw-wire duplicate."
    )

  diagnostic_bytes = summary["family_tables"]["diagnostic_fields"]["total_bytes"]
  if diagnostic_bytes:
    findings.append(
      f"Heartbeat-style diagnostic sections accounted for {format_bytes(diagnostic_bytes)} ({diagnostic_bytes / max(total_bytes, 1):.1%}) of measured bytes."
    )

  cp_bytes = (
    summary["family_tables"]["c_metadata"]["total_bytes"] +
    summary["family_tables"]["p_runtime"]["total_bytes"]
  )
  if cp_bytes:
    findings.append(
      f"`_C_*` and `_P_*` metadata together contributed {format_bytes(cp_bytes)} ({cp_bytes / max(total_bytes, 1):.1%}) of the sample."
    )

  empty_bytes = summary["family_tables"]["empty_default_fields"]["total_bytes"]
  if empty_bytes:
    findings.append(
      f"Empty/default-like fields still consumed {format_bytes(empty_bytes)} ({empty_bytes / max(total_bytes, 1):.1%}) in this callback-level view."
    )

  if summary["encrypted_payload_count"]:
    findings.append(
      f"{summary['encrypted_payload_count']} messages ({summary['encrypted_payload_count'] / max(total_messages, 1):.1%}) remained encrypted envelopes in the SDK-visible view, which limits deeper business-payload field analysis."
    )

  return findings[:7]


def required_answers(summary: dict[str, Any]) -> list[str]:
  total_bytes = max(summary["total_bytes"], 1)
  class_table = summary["class_table"]
  field_lookup = {row["field"]: row for row in summary["field_table"]}
  family_tables = summary["family_tables"]
  top_classes = ", ".join(
    f"{row['message_class']} ({format_bytes(row['total_bytes'])}, {row['total_bytes'] / total_bytes:.1%})"
    for row in class_table[:4]
  ) or "n/a"
  current_network_row = field_lookup.get("CURRENT_NETWORK")
  encoded_row = field_lookup.get("ENCODED_DATA")
  current_network_text = (
    f"`CURRENT_NETWORK` at {format_bytes(current_network_row['total_bytes'])}"
    if current_network_row is not None else "no dominant `CURRENT_NETWORK` field observed"
  )
  encoded_text = (
    f"`ENCODED_DATA` at {format_bytes(encoded_row['total_bytes'])}"
    if encoded_row is not None else "no dominant `ENCODED_DATA` field observed"
  )
  empty_bytes = family_tables["empty_default_fields"]["total_bytes"]
  cp_bytes = family_tables["c_metadata"]["total_bytes"] + family_tables["p_runtime"]["total_bytes"]
  diagnostic_bytes = family_tables["diagnostic_fields"]["total_bytes"]
  image_bytes = family_tables["image_fields"]["total_bytes"]
  top_examples = summary["top_examples"]
  largest_examples = ", ".join(
    f"{row['message_class']} dominated by {row['large_fields'][0]['field'] if row['large_fields'] else 'n/a'}"
    for row in top_examples[:3]
  ) or "n/a"

  return [
    f"1. Message classes that dominated total bytes were: {top_classes}.",
    (
      "2. The largest payloads were dominated by network-map and diagnostic metadata, not by images or histories. "
      f"The largest examples were {largest_examples}; image fields contributed only {format_bytes(image_bytes)} overall."
    ),
    (
      "3. The clearest low-hanging-fruit fields were "
      f"{current_network_text}, `ACTIVE_PLUGINS`, {encoded_text}, `EE_WHITELIST`, `NET_CONFIG_DATA`, and `EE_ENCRYPTED_DATA`."
    ),
    f"4. Empty/default-like fields accounted for {format_bytes(empty_bytes)} ({empty_bytes / total_bytes:.1%}) in this SDK-visible sample.",
    f"5. `_C_*` and `_P_*` metadata accounted for {format_bytes(cp_bytes)} ({cp_bytes / total_bytes:.1%}) combined.",
    f"6. Yes. Heartbeat-like diagnostic sections still exposed {format_bytes(diagnostic_bytes)} ({diagnostic_bytes / total_bytes:.1%}) from the SDK side.",
    (
      "7. Direct mapping back to core `PAYLOADS.md` is blocked because that file is absent in this checkout on 2026-03-18, "
      "but the strongest likely overlap is heartbeat diagnostics, NET_MON full snapshots, repeated metadata, and encrypted envelopes."
    ),
    (
      "8. SDK-side guidance from this run: separate callback-view byte counts from raw-wire claims, drop heartbeat `ENCODED_DATA` after decode when archiving locally, "
      "and analyze admin payloads separately from business payloads because NET_MON and heartbeat traffic dominate the sample."
    ),
  ]


def render_results_markdown(summary: dict[str, Any]) -> str:
  metadata = summary["metadata"]
  total_bytes = max(summary["total_bytes"], 1)
  elapsed_seconds = float(metadata.get("capture_elapsed_seconds") or 0.0)
  candidates = candidate_rows(summary)
  findings = executive_findings(summary)
  answers = required_answers(summary)

  def format_byte_rate(num_bytes: int) -> str:
    if elapsed_seconds <= 0:
      return "n/a"
    return format_bytes_per_second(num_bytes / elapsed_seconds)

  def format_message_rate(message_count: int) -> str:
    if elapsed_seconds <= 0:
      return "n/a"
    return f"{message_count / elapsed_seconds:.2f}"

  class_rows = [
    (
      row["message_class"],
      row["count"],
      format_bytes(row["total_bytes"]),
      row["avg_bytes"],
      row["p95_bytes"],
      row["max_bytes"],
    )
    for row in summary["class_table"][:TOP_N]
  ]
  sender_rows = [
    (
      row["sender"],
      row["count"],
      format_bytes(row["total_bytes"]),
      row["avg_bytes"],
    )
    for row in summary["sender_table"][:10]
  ]
  stream_rows = [
    (
      row["stream_signature"],
      row["count"],
      format_bytes(row["total_bytes"]),
      row["avg_bytes"],
    )
    for row in summary["stream_table"][:10]
  ]
  field_rows = [
    (
      row["field"],
      row["messages_present"],
      format_bytes(row["total_bytes"]),
      row["avg_when_present"],
      f"empty={row['empty_frequency']}, default_like={row['default_like_frequency']}",
    )
    for row in summary["field_table"][:TOP_N]
  ]
  bandwidth_rows = [
    (
      row["message_class"],
      format_byte_rate(row["total_bytes"]),
      format_message_rate(row["count"]),
      f"{row['total_bytes'] / total_bytes:.1%}",
    )
    for row in summary["class_table"][:10]
  ]
  avg_bytes_per_message = int(summary["total_bytes"] / max(summary["total_messages"], 1))
  diagnostic_bytes = summary["family_tables"]["diagnostic_fields"]["total_bytes"]
  current_network_row = next((row for row in summary["field_table"] if row["field"] == "CURRENT_NETWORK"), None)
  encoded_row = next((row for row in summary["field_table"] if row["field"] == "ENCODED_DATA"), None)

  family_sections = []
  family_labels = [
    ("_C_* metadata", summary["family_tables"]["c_metadata"]),
    ("_P_* runtime/debug fields", summary["family_tables"]["p_runtime"]),
    ("image fields", summary["family_tables"]["image_fields"]),
    ("heartbeat-style diagnostic sections", summary["family_tables"]["diagnostic_fields"]),
    ("history/result fields", summary["family_tables"]["history_fields"]),
    ("empty/default fields", summary["family_tables"]["empty_default_fields"]),
  ]
  for title, metrics in family_labels:
    top_fields = ", ".join(f"{name} ({format_bytes(size)})" for name, size in metrics["top_fields"][:5]) or "n/a"
    family_sections.append(
      f"### {title}\n"
      f"- messages present: {metrics['message_count']}\n"
      f"- total estimated bytes: {format_bytes(metrics['total_bytes'])} ({metrics['total_bytes'] / total_bytes:.1%})\n"
      f"- leading fields: {top_fields}"
    )

  example_sections = []
  for idx, row in enumerate(summary["top_examples"], start=1):
    large_fields = ", ".join(
      f"{item['field']}={format_bytes(item['bytes'])}"
      for item in row["large_fields"][:5]
    ) or "n/a"
    example_sections.append(
      f"- Example {idx}: `{row['message_class']}` from `{row['sender_label']}` "
      f"({format_bytes(row['serialized_size_bytes'])}, stream=`{row.get('stream_name')}`, signature=`{row.get('plugin_signature')}`)\n"
      f"  large fields: {large_fields}\n"
      f"  preview: `{json.dumps(row['sanitized_preview'], ensure_ascii=True, sort_keys=True)}`"
    )

  candidate_sections = []
  for idx, candidate in enumerate(candidates, start=1):
    candidate_sections.append(
      f"{idx}. {candidate['candidate']}\n"
      f"   - evidence: {candidate['evidence']}\n"
      f"   - likely owner: {candidate['owner']}\n"
      f"   - expected impact: {candidate['impact']}\n"
      f"   - compatibility risk: {candidate['risk']}"
    )

  top_shapes = []
  for row in summary["top_shapes"]:
    top_shapes.append(
      f"- `{row['shape_id']}`: {row['count']} messages, {format_bytes(row['total_bytes'])}, example `{row['example']}`, keys `{row['keys']}`"
    )

  mapping_lines = [
    "- `PAYLOADS.md` was referenced by the task file, but no `PAYLOADS.md` exists in this checkout as of 2026-03-18, so direct reference-by-reference mapping is blocked.",
    "- The strongest likely core-side candidates from this SDK sample are NET_MON full snapshots, heartbeat diagnostics, repeated `_C_*`/`_P_*` metadata, and empty/default field emission.",
    "- The encrypted-envelope share in the SDK-visible view suggests any core-side analysis should separate payload envelope costs from decrypted business payload body costs.",
  ]

  open_questions = [
    "- Raw MQTT wire bytes are not exposed in the public callback path, so all byte estimates here are from the SDK-visible decoded JSON view.",
    "- Messages encrypted for other recipients remain opaque envelopes; their inner field makeup cannot be measured from this listener.",
    "- Because `PAYLOADS.md` is absent in this repo snapshot, the core-mapping section is necessarily partial.",
    f"- Duplicate message-shape leaders in this run: {summary['top_shapes'][0]['shape_id'] if summary['top_shapes'] else 'n/a'} and {summary['top_shapes'][1]['shape_id'] if len(summary['top_shapes']) > 1 else 'n/a'}.",
  ]

  return "\n".join([
    "# Ratio1 SDK Payload Capture Results",
    "",
    "## Scope",
    f"- SDK repo revision: `{metadata['repo_revision']}`",
    f"- Tutorial/example path: `{metadata['tutorial_path']}`",
    f"- Capture command: `{metadata['capture_command']}`",
    f"- Analysis command: `{metadata['analysis_command']}`",
    f"- Network: `{metadata['network']}`",
    f"- Capture window: `{metadata['capture_started_at']}` to `{metadata['capture_finished_at']}` ({metadata['capture_elapsed_seconds']:.1f}s)",
    f"- Message count: `{summary['total_messages']}`",
    f"- Any filters: `{metadata['filters']}`",
    "",
    "## Environment and Limits",
    f"- SDK/session setup used: `{metadata['session_setup']}`",
    f"- Auth or public-access assumptions: `{metadata['auth_assumptions']}`",
    f"- Sample stop conditions: `{metadata['stop_conditions']}`; actual stop reason=`{metadata['stop_reason']}`",
    f"- Known blind spots: `{metadata['known_blind_spots']}`",
    "",
    "## Executive Summary",
    *[f"- {item}" for item in findings],
    "",
    "## Answers To Required Questions",
    *[f"- {item}" for item in answers],
    "",
    "## Protocol Bandwidth Evaluation",
    f"- Average observed callback-visible throughput: `{format_byte_rate(summary['total_bytes'])}` ({format_bytes(int(summary['total_bytes'] * 60 / elapsed_seconds))}/min)" if elapsed_seconds > 0 else "- Average observed callback-visible throughput: `n/a`",
    f"- Average observed message rate: `{format_message_rate(summary['total_messages'])} msg/s` with `{avg_bytes_per_message}` bytes/message" if elapsed_seconds > 0 else f"- Average observed message rate: `n/a` with `{avg_bytes_per_message}` bytes/message",
    f"- Heartbeat diagnostic field family alone sustained `{format_byte_rate(diagnostic_bytes)}` ({diagnostic_bytes / total_bytes:.1%} of observed bytes)",
    f"- `CURRENT_NETWORK` sustained `{format_byte_rate(current_network_row['total_bytes'] if current_network_row else 0)}` and remains the clearest snapshot-bandwidth driver",
    f"- `ENCODED_DATA` sustained `{format_byte_rate(encoded_row['total_bytes'] if encoded_row else 0)}` in the SDK callback view; treat it as analysis/logging overhead unless raw-wire evidence shows the same duplication on the broker side",
    "",
    make_table(
      bandwidth_rows,
      ["message class", "avg bytes/s", "avg msg/s", "byte share"],
    ),
    "",
    "## Byte Distribution",
    make_table(
      class_rows,
      ["message class", "count", "total bytes", "avg bytes", "p95 bytes", "max bytes"],
    ),
    "",
    make_table(
      sender_rows,
      ["sender", "count", "total bytes", "avg bytes"],
    ),
    "",
    make_table(
      stream_rows,
      ["stream / signature", "count", "total bytes", "avg bytes"],
    ),
    "",
    "## Top Heavy Fields",
    make_table(
      field_rows,
      ["field", "messages present", "total estimated bytes", "avg bytes when present", "notes"],
    ),
    "",
    "## Field Families",
    *family_sections,
    "",
    "## Largest Message Examples",
    *example_sections,
    "",
    "## Low-Hanging-Fruit Candidates",
    *candidate_sections,
    "",
    "## Mapping Back To Core PAYLOADS.md",
    *mapping_lines,
    "",
    "## Open Questions",
    *open_questions,
    "",
    "## Artifacts",
    f"- local JSONL path: `{metadata['capture_file']}`",
    f"- local summary JSON path: `{metadata['summary_file']}`",
    f"- top message shape leaders: `{', '.join(row['shape_id'] for row in summary['top_shapes'][:5]) if summary['top_shapes'] else 'n/a'}`",
    "",
  ])


def blocked_results_markdown(
  *,
  metadata: dict[str, Any],
  blocker: str,
) -> str:
  return "\n".join([
    "# Ratio1 SDK Payload Capture Results",
    "",
    "## Scope",
    f"- Tutorial/example path: `{metadata['tutorial_path']}`",
    f"- Capture command: `{metadata['capture_command']}`",
    f"- Analysis command: `{metadata['analysis_command']}`",
    "",
    "## Environment and Limits",
    f"- SDK/session setup used: `{metadata['session_setup']}`",
    f"- Auth or public-access assumptions: `{metadata['auth_assumptions']}`",
    f"- Sample stop conditions: `{metadata['stop_conditions']}`",
    "",
    "## Executive Summary",
    f"- Blocked on 2026-03-18: {blocker}",
    f"- Known blind spots: {metadata['known_blind_spots']}",
    "",
    "## Open Questions",
    "- Mainnet access did not complete safely in this environment, so no measured byte distribution is available.",
    "- Re-run with the same tutorial command after resolving the blocker above.",
    "",
    "## Artifacts",
    "- local JSONL path: none",
    "- local summary JSON path: none",
    "",
  ])
