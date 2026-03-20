"""
ex27_payload_capture.py
-----------------------

Capture a bounded passive sample of Ratio1 mainnet traffic from the SDK callback
surface, store sanitized per-message measurements under `_local_cache`, and
generate `_todo/PAYLOADS_SDK_RESULTS.md`.

This tutorial only listens. It does not create pipelines, send commands, or
modify remote node configuration. The SDK still performs its normal connection
and dAuth startup path.

Recommended command from a fresh checkout:
  HOME="$(mktemp -d)" python tutorials/ex27_payload_capture.py --seconds 60 --max-messages 2500

Re-analyze an existing capture:
  python tutorials/ex27_payload_capture.py --analyze-only --capture-file _local_cache/payload_capture/<capture>.jsonl
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Lock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from ratio1 import Session  # noqa: E402
from tutorials.payload_capture_utils import (  # noqa: E402
  LARGE_FIELD_THRESHOLD_BYTES,
  blocked_results_markdown,
  build_row,
  json_default,
  load_jsonl,
  render_results_markdown,
  summarize_rows,
  utc_now_iso,
  write_json,
  write_jsonl,
)


DEFAULT_SECONDS = 60
DEFAULT_MAX_MESSAGES = 2500
DEFAULT_OUTPUT_DIR = REPO_ROOT / "_local_cache" / "payload_capture"
DEFAULT_RESULTS_PATH = REPO_ROOT / "_todo" / "PAYLOADS_SDK_RESULTS.md"
TUTORIAL_PATH = Path("tutorials/ex27_payload_capture.py")


def parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Passively capture bounded SDK-visible mainnet traffic and generate _todo/PAYLOADS_SDK_RESULTS.md.",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=(
      "Examples:\n"
      "  HOME=\"$(mktemp -d)\" python tutorials/ex27_payload_capture.py --seconds 60 --max-messages 2500\n"
      "  python tutorials/ex27_payload_capture.py --analyze-only --capture-file _local_cache/payload_capture/<capture>.jsonl\n"
    ),
  )
  parser.add_argument("--seconds", type=int, default=DEFAULT_SECONDS, help="Maximum capture duration in seconds.")
  parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES, help="Maximum total callback messages to record.")
  parser.add_argument(
    "--large-field-threshold",
    type=int,
    default=LARGE_FIELD_THRESHOLD_BYTES,
    help="Field-size threshold in bytes for the per-message large-field list.",
  )
  parser.add_argument(
    "--output-dir",
    default=str(DEFAULT_OUTPUT_DIR),
    help="Directory for ignored local capture artifacts.",
  )
  parser.add_argument(
    "--results-path",
    default=str(DEFAULT_RESULTS_PATH),
    help="Path for the generated markdown report.",
  )
  parser.add_argument(
    "--capture-file",
    help="Existing JSONL capture to re-analyze instead of listening again.",
  )
  parser.add_argument(
    "--analyze-only",
    action="store_true",
    help="Skip live capture and regenerate the markdown report from --capture-file.",
  )
  parser.add_argument(
    "--session-name",
    default="sdk-payload-capture",
    help="Explicit session alias so the tutorial does not depend on writing ~/.ratio1/config.",
  )
  return parser.parse_args()


def git_revision() -> str:
  try:
    result = subprocess.run(
      ["git", "rev-parse", "HEAD"],
      cwd=REPO_ROOT,
      capture_output=True,
      text=True,
      check=True,
    )
    return result.stdout.strip()
  except Exception:
    return "unknown"


def exact_command() -> str:
  return "python " + " ".join(shlex.quote(arg) for arg in sys.argv)


def capture_command_from_args(args: argparse.Namespace) -> str:
  command = ["python", str(TUTORIAL_PATH)]
  if args.seconds != DEFAULT_SECONDS:
    command.extend(["--seconds", str(args.seconds)])
  if args.max_messages != DEFAULT_MAX_MESSAGES:
    command.extend(["--max-messages", str(args.max_messages)])
  if args.large_field_threshold != LARGE_FIELD_THRESHOLD_BYTES:
    command.extend(["--large-field-threshold", str(args.large_field_threshold)])
  if Path(args.output_dir) != DEFAULT_OUTPUT_DIR:
    command.extend(["--output-dir", args.output_dir])
  if Path(args.results_path) != DEFAULT_RESULTS_PATH:
    command.extend(["--results-path", args.results_path])
  if args.session_name != "sdk-payload-capture":
    command.extend(["--session-name", args.session_name])
  return " ".join(shlex.quote(part) for part in command)


class CaptureCollector:
  def __init__(self, large_field_threshold: int) -> None:
    self.large_field_threshold = large_field_threshold
    self.rows: list[dict] = []
    self._lock = Lock()

  def total_messages(self) -> int:
    with self._lock:
      return len(self.rows)

  def observe(
    self,
    *,
    callback_type: str,
    node_addr: str | None,
    message: dict,
    pipeline_name: str | None = None,
    plugin_signature: str | None = None,
    plugin_instance: str | None = None,
  ) -> None:
    row = build_row(
      callback_type=callback_type,
      node_addr=node_addr,
      message=message,
      pipeline_name=pipeline_name,
      plugin_signature=plugin_signature,
      plugin_instance=plugin_instance,
      large_field_threshold=self.large_field_threshold,
    )
    with self._lock:
      self.rows.append(row)

  def snapshot(self) -> list[dict]:
    with self._lock:
      return list(self.rows)


def write_report(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(content, encoding="utf-8")


def metadata_template(args: argparse.Namespace) -> dict:
  session_setup = (
    f"Session(name={args.session_name!r}, silent=True, auto_configuration=True, "
    "run_dauth=True, use_home_folder=False, local_cache_base_folder=<repo>)"
  )
  return {
    "repo_revision": git_revision(),
    "tutorial_path": str(TUTORIAL_PATH),
    "capture_command": exact_command(),
    "analysis_command": "python tutorials/ex27_payload_capture.py --analyze-only --capture-file <capture.jsonl>",
    "network": "mainnet",
    "capture_started_at": None,
    "capture_finished_at": None,
    "capture_elapsed_seconds": 0.0,
    "filters": "none",
    "session_setup": session_setup,
    "auth_assumptions": (
      "Used the SDK's normal dAuth-backed public listening path on mainnet. "
      "No pipelines, commands, or config mutations were issued by this tutorial."
    ),
    "stop_conditions": f"{args.seconds}s wall clock or {args.max_messages} messages, whichever comes first",
    "stop_reason": "not-started",
    "known_blind_spots": (
      "Callback-level JSON view only; raw MQTT wire bytes and payload internals for "
      "messages encrypted to other recipients are not observable here."
    ),
    "capture_file": "n/a",
    "summary_file": "n/a",
  }


def run_capture(args: argparse.Namespace) -> tuple[list[dict], dict]:
  output_dir = Path(args.output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  collector = CaptureCollector(large_field_threshold=args.large_field_threshold)
  metadata = metadata_template(args)
  metadata["capture_started_at"] = utc_now_iso()

  session = None
  started_monotonic = time.monotonic()

  def on_payload(session_obj, node_addr, pipeline_name, plugin_signature, plugin_instance, payload):
    collector.observe(
      callback_type="payload",
      node_addr=node_addr,
      message=payload.data,
      pipeline_name=pipeline_name,
      plugin_signature=plugin_signature,
      plugin_instance=plugin_instance,
    )

  def on_heartbeat(session_obj, node_addr, heartbeat):
    collector.observe(
      callback_type="heartbeat",
      node_addr=node_addr,
      message=heartbeat,
    )

  def on_notification(session_obj, node_addr, notification):
    collector.observe(
      callback_type="notification",
      node_addr=node_addr,
      message=notification,
    )

  try:
    session = Session(
      name=args.session_name,
      on_payload=on_payload,
      on_heartbeat=on_heartbeat,
      on_notification=on_notification,
      silent=True,
      use_home_folder=False,
      local_cache_base_folder=str(REPO_ROOT),
      local_cache_app_folder="_local_cache",
      auto_configuration=True,
      run_dauth=True,
    )
    metadata["network"] = getattr(session.bc_engine, "evm_network", "unknown")

    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
      if collector.total_messages() >= args.max_messages:
        metadata["stop_reason"] = "max-messages"
        break
      time.sleep(0.25)
    else:
      metadata["stop_reason"] = "time-window"
  finally:
    if session is not None:
      session.close(close_pipelines=False, wait_close=True)

  rows = collector.snapshot()
  finished_monotonic = time.monotonic()
  metadata["capture_finished_at"] = utc_now_iso()
  metadata["capture_elapsed_seconds"] = round(finished_monotonic - started_monotonic, 2)

  timestamp = metadata["capture_started_at"].replace(":", "").replace("-", "")
  stem = f"{timestamp}_{metadata['network']}_{len(rows)}msg"
  capture_file = output_dir / f"{stem}.jsonl"
  summary_file = output_dir / f"{stem}_summary.json"
  metadata["capture_file"] = str(capture_file.relative_to(REPO_ROOT))
  metadata["summary_file"] = str(summary_file.relative_to(REPO_ROOT))

  write_jsonl(rows, capture_file)
  return rows, metadata


def analyze_capture(rows: list[dict], metadata: dict, results_path: Path) -> dict:
  summary = summarize_rows(rows, metadata)
  summary_path = REPO_ROOT / metadata["summary_file"]
  write_json(summary, summary_path)
  write_report(results_path, render_results_markdown(summary))
  return summary


def infer_capture_timing(rows: list[dict]) -> dict[str, str | float | None]:
  timestamps = []
  for row in rows:
    received_at = row.get("received_at")
    if not isinstance(received_at, str):
      continue
    try:
      timestamps.append(datetime.fromisoformat(received_at))
    except ValueError:
      continue

  if not timestamps:
    return {
      "capture_started_at": "from-artifact",
      "capture_finished_at": "from-artifact",
      "capture_elapsed_seconds": 0.0,
    }

  started_at = min(timestamps)
  finished_at = max(timestamps)
  return {
    "capture_started_at": started_at.isoformat(),
    "capture_finished_at": finished_at.isoformat(),
    "capture_elapsed_seconds": round(max((finished_at - started_at).total_seconds(), 0.0), 2),
  }


def load_existing_summary_metadata(summary_file: Path) -> dict | None:
  if not summary_file.exists():
    return None
  try:
    with summary_file.open(encoding="utf-8") as fh:
      data = json.load(fh)
  except Exception:
    return None
  metadata = data.get("metadata")
  if isinstance(metadata, dict):
    return metadata
  return None


def has_valid_capture_metadata(metadata: dict | None) -> bool:
  if not isinstance(metadata, dict):
    return False
  if float(metadata.get("capture_elapsed_seconds") or 0.0) <= 0:
    return False
  capture_command = metadata.get("capture_command")
  if isinstance(capture_command, str) and "--analyze-only" in capture_command:
    return False
  return True


def reconstruct_capture_metadata(args: argparse.Namespace, rows: list[dict]) -> dict:
  metadata = metadata_template(args)
  metadata.update(infer_capture_timing(rows))
  metadata["capture_command"] = capture_command_from_args(args)
  elapsed_seconds = float(metadata.get("capture_elapsed_seconds") or 0.0)
  if len(rows) >= args.max_messages:
    metadata["stop_reason"] = "max-messages"
  elif elapsed_seconds >= max(args.seconds - 5, 0):
    metadata["stop_reason"] = "time-window"
  else:
    metadata["stop_reason"] = "reconstructed-from-artifact"
  return metadata


def analyze_only(args: argparse.Namespace, results_path: Path) -> dict:
  if not args.capture_file:
    raise ValueError("--capture-file is required with --analyze-only")
  capture_file = Path(args.capture_file)
  if not capture_file.is_absolute():
    capture_file = REPO_ROOT / capture_file
  rows = load_jsonl(capture_file)
  summary_file = capture_file.with_name(capture_file.stem + "_summary.json")
  existing_metadata = load_existing_summary_metadata(summary_file)
  if has_valid_capture_metadata(existing_metadata):
    metadata = metadata_template(args)
    metadata.update(existing_metadata)
  else:
    metadata = reconstruct_capture_metadata(args, rows)
  metadata["capture_file"] = str(capture_file.relative_to(REPO_ROOT))
  metadata["summary_file"] = str(summary_file.relative_to(REPO_ROOT))
  return analyze_capture(rows, metadata, results_path)


def main() -> int:
  args = parse_args()
  results_path = Path(args.results_path)
  if not results_path.is_absolute():
    results_path = REPO_ROOT / results_path

  try:
    if args.analyze_only:
      summary = analyze_only(args, results_path)
    else:
      rows, metadata = run_capture(args)
      summary = analyze_capture(rows, metadata, results_path)
    print(
      "capture-complete",
      {
        "messages": summary["total_messages"],
        "bytes": summary["total_bytes"],
        "results_path": str(results_path.relative_to(REPO_ROOT)),
        "capture_file": summary["metadata"]["capture_file"],
        "summary_file": summary["metadata"]["summary_file"],
      },
      flush=True,
    )
    return 0
  except Exception as exc:
    metadata = metadata_template(args)
    blocker = f"{type(exc).__name__}: {exc}"
    write_report(results_path, blocked_results_markdown(metadata=metadata, blocker=blocker))
    print(json_default({"status": "blocked", "blocker": blocker}), flush=True)
    return 1


if __name__ == "__main__":
  raise SystemExit(main())
