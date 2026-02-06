#!/usr/bin/env python3
import argparse
import json
import math
import os
import platform
import random
import re
import socket
import threading
import time

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ratio1 import Logger
from ratio1.logging.base_logger import _LOGGER_LOCK_ID


def _pct(values: List[float], percentile: float) -> float:
  """
  Compute a percentile with linear interpolation.

  Parameters
  ----------
  values : list of float
    Sample values.
  percentile : float
    Percentile in ``[0.0, 1.0]``.

  Returns
  -------
  float
    Interpolated percentile value, or ``0.0`` for empty input.
  """
  if not values:
    return 0.0
  # Sort once, then interpolate between adjacent ranks.
  sorted_values = sorted(values)
  if len(sorted_values) == 1:
    return sorted_values[0]
  rank = (len(sorted_values) - 1) * percentile
  lower = int(math.floor(rank))
  upper = int(math.ceil(rank))
  if lower == upper:
    return sorted_values[lower]
  return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (rank - lower)


def _summarize_ms(values_seconds: List[float]) -> Dict[str, float]:
  """
  Summarize latency-like samples measured in seconds.

  Parameters
  ----------
  values_seconds : list of float
    Raw sample values expressed in seconds.

  Returns
  -------
  dict
    Statistical summary in milliseconds (`count`, `p50`, `p95`, `p99`,
    `max`, and arithmetic mean).
  """
  if not values_seconds:
    return {
      "count": 0,
      "p50_ms": 0.0,
      "p95_ms": 0.0,
      "p99_ms": 0.0,
      "max_ms": 0.0,
      "mean_ms": 0.0,
    }
  # Convert to milliseconds before percentile aggregation for report readability.
  values_ms = [v * 1000.0 for v in values_seconds]
  return {
    "count": len(values_ms),
    "p50_ms": _pct(values_ms, 0.50),
    "p95_ms": _pct(values_ms, 0.95),
    "p99_ms": _pct(values_ms, 0.99),
    "max_ms": max(values_ms),
    "mean_ms": sum(values_ms) / len(values_ms),
  }


def _fmt(x: float) -> str:
  """
  Format a floating-point value with fixed 3-decimal precision.

  Parameters
  ----------
  x : float
    Numeric value to format.

  Returns
  -------
  str
    String formatted as ``"{x:.3f}"``.
  """
  return f"{x:.3f}"


@dataclass
class ScenarioResult:
  """
  Container for one benchmark scenario result.

  Attributes
  ----------
  thread_count : int
    Number of producer threads used in the scenario.
  duration_s : float
    Measured scenario runtime in seconds.
  total_calls : int
    Total `log.P` calls completed across all threads.
  calls_per_sec : float
    Aggregate throughput.
  latency_summary_ms : dict
    `log.P` latency summary in milliseconds.
  lock_wait_summary_ms : dict
    Lock wait summary in milliseconds.
  save_duration_summary_ms : dict
    `_save_log` duration summary in milliseconds.
  save_count : int
    Number of `_save_log` invocations observed.
  save_calls_per_sec : float
    Save operation rate.
  log_lines_before : int
    In-memory normal log lines before scenario start.
  log_lines_after : int
    In-memory normal log lines after scenario end.
  log_file_size_before_bytes : int
    On-disk normal log file size before scenario start.
  log_file_size_after_bytes : int
    On-disk normal log file size after scenario end.
  throttling_start_s : float or None
    First detected throttling bucket start time (if detected).
  throttling_scale_drop_pct : float
    Relative throughput drop versus scenario start bucket.
  evolution : list of dict
    Bucketized time-series view for throughput/latency evolution.
  join_timeout_threads : int
    Count of worker threads not joined before timeout.
  """
  thread_count: int
  duration_s: float
  total_calls: int
  calls_per_sec: float
  latency_summary_ms: Dict[str, float]
  lock_wait_summary_ms: Dict[str, float]
  save_duration_summary_ms: Dict[str, float]
  save_count: int
  save_calls_per_sec: float
  log_lines_before: int
  log_lines_after: int
  log_file_size_before_bytes: int
  log_file_size_after_bytes: int
  throttling_start_s: Optional[float]
  throttling_scale_drop_pct: float
  evolution: List[Dict[str, float]]
  join_timeout_threads: int


class LoggerInstrumentation:
  """
  Runtime instrumentation wrapper for `Logger`.

  The class monkey-patches selected logger methods in order to measure lock
  acquisition waits and `_save_log` call durations without changing the logger
  API used by the benchmark workers.
  """

  def __init__(self, logger: Logger):
    """
    Initialize instrumentation state.

    Parameters
    ----------
    logger : Logger
      Shared logger instance used by the benchmark.
    """
    self.logger = logger
    self._mutex = threading.Lock()
    self.lock_wait_events: List[Tuple[float, float]] = []
    self.save_events: List[Tuple[float, float, str, int]] = []
    self._orig_lock_resource = logger.lock_resource
    self._orig_save_log = logger._save_log
    self._installed = False

  def install(self):
    """
    Install runtime wrappers around lock/save methods.

    Returns
    -------
    None
      Method wrappers are bound directly to the logger instance.
    """
    if self._installed:
      return

    def lock_resource_wrapper(logger_self, str_res):
      # Measure lock acquisition latency only for the main logger lock.
      t0 = time.perf_counter()
      result = self._orig_lock_resource(str_res)
      if str_res == _LOGGER_LOCK_ID:
        t1 = time.perf_counter()
        with self._mutex:
          self.lock_wait_events.append((t1, t1 - t0))
      return result

    def save_log_wrapper(logger_self, log, log_file, DEBUG_ERRORS=False, *args, **kwargs):
      # Capture end-to-end save duration regardless of new optional kwargs.
      t0 = time.perf_counter()
      result = self._orig_save_log(log, log_file, DEBUG_ERRORS=DEBUG_ERRORS, *args, **kwargs)
      t1 = time.perf_counter()
      with self._mutex:
        self.save_events.append((t1, t1 - t0, str(log_file), len(log)))
      return result

    self.logger.lock_resource = lock_resource_wrapper.__get__(self.logger, self.logger.__class__)
    self.logger._save_log = save_log_wrapper.__get__(self.logger, self.logger.__class__)
    self._installed = True

  def uninstall(self):
    """
    Restore original logger methods.

    Returns
    -------
    None
      Idempotent cleanup for instrumentation wrappers.
    """
    if not self._installed:
      return
    self.logger.lock_resource = self._orig_lock_resource
    self.logger._save_log = self._orig_save_log
    self._installed = False

  def event_slices(
    self,
    lock_start_idx: int,
    lock_end_idx: int,
    save_start_idx: int,
    save_end_idx: int,
  ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float, str, int]]]:
    """
    Return event windows for one scenario.

    Parameters
    ----------
    lock_start_idx : int
      Start index in lock event list.
    lock_end_idx : int
      End index in lock event list.
    save_start_idx : int
      Start index in save event list.
    save_end_idx : int
      End index in save event list.

    Returns
    -------
    tuple
      Two copied slices: lock events and save events.
    """
    with self._mutex:
      lock_slice = list(self.lock_wait_events[lock_start_idx:lock_end_idx])
      save_slice = list(self.save_events[save_start_idx:save_end_idx])
    return lock_slice, save_slice


class LoggerTester:
  """
  Deterministic threaded stress harness for Ratio1 logger throughput.

  The harness drives one shared logger across multiple thread scenarios,
  captures contention/persistence metrics, and emits both machine-readable
  JSON and human-readable Markdown reports.
  """

  def __init__(
    self,
    run_seconds: int = 60,
    thread_scenarios: Optional[List[int]] = None,
    min_delay_ms: int = 1,
    max_delay_ms: int = 100,
    seed: int = 1337,
    bucket_seconds: int = 5,
    stage_name: str = "STAGE_A",
    output_dir: str = "xperimental/logger",
    base_folder: str = "/tmp/r1sdk_logger_bench",
    app_folder: str = "logger_throughput",
    quality_check_enabled: bool = True,
    quality_check_threads: int = 50,
    quality_check_lines_per_thread: int = 200,
    quality_check_join_timeout_seconds: float = 30.0,
    quality_check_flush_timeout_seconds: float = 30.0,
  ):
    """
    Configure benchmark runtime defaults.

    Parameters
    ----------
    run_seconds : int, optional
      Duration per scenario.
    thread_scenarios : list of int or None, optional
      Thread counts to execute sequentially.
    min_delay_ms : int, optional
      Minimum per-worker delay between log calls.
    max_delay_ms : int, optional
      Maximum per-worker delay between log calls.
    seed : int, optional
      Base deterministic RNG seed.
    bucket_seconds : int, optional
      Width for time-bucket evolution tables.
    stage_name : str, optional
      Label used in output filenames and log messages.
    output_dir : str, optional
      Folder for generated reports and metrics.
    base_folder : str, optional
      Logger base folder used for benchmark files.
    app_folder : str, optional
      Logger app subfolder used for benchmark files.
    quality_check_enabled : bool, optional
      Whether to execute post-run deterministic line-integrity validation.
    quality_check_threads : int, optional
      Number of threads used by the deterministic quality check (minimum 50).
    quality_check_lines_per_thread : int, optional
      Number of deterministic lines emitted per quality-check thread.
    quality_check_join_timeout_seconds : float, optional
      Max wait for quality-check worker joins.
    quality_check_flush_timeout_seconds : float, optional
      Max wait for async writer queue drain during quality check.
    """
    self.run_seconds = run_seconds
    self.thread_scenarios = thread_scenarios or [1, 10, 30, 60, 100]
    self.min_delay_s = min_delay_ms / 1000.0
    self.max_delay_s = max_delay_ms / 1000.0
    self.seed = seed
    self.bucket_seconds = bucket_seconds
    self.stage_name = stage_name
    self.output_dir = output_dir
    self.base_folder = base_folder
    self.app_folder = app_folder
    self.quality_check_enabled = quality_check_enabled
    self.quality_check_threads = quality_check_threads
    self.quality_check_lines_per_thread = quality_check_lines_per_thread
    self.quality_check_join_timeout_seconds = quality_check_join_timeout_seconds
    self.quality_check_flush_timeout_seconds = quality_check_flush_timeout_seconds
    self.logger: Optional[Logger] = None
    self.instrument: Optional[LoggerInstrumentation] = None

  def _new_logger(self) -> Logger:
    """
    Create the shared benchmark logger instance.

    Returns
    -------
    Logger
      Logger configured for filesystem persistence with silent console output.
    """
    # Keep one shared logger instance per full stage run.
    os.makedirs(self.base_folder, exist_ok=True)
    logger_name = f"LoggerBench-{self.stage_name}-{datetime.now().strftime('%H%M%S')}"
    return Logger(
      lib_name=logger_name,
      base_folder=self.base_folder,
      app_folder=self.app_folder,
      show_time=True,
      no_folders_no_save=False,
      silent=True,
      DEBUG=False,
    )

  def _sample_log_file_size(self) -> int:
    """
    Read current on-disk size of the active normal log file.

    Returns
    -------
    int
      File size in bytes, or `0` when unavailable.
    """
    if not self.logger or not getattr(self.logger, "log_file", None):
      return 0
    try:
      return os.path.getsize(self.logger.log_file)
    except OSError:
      # Transient size lookup failures are treated as zero-size samples.
      return 0

  def _collect_stage_log_files(self) -> List[str]:
    """
    Collect active stage log files potentially holding benchmark output.

    Returns
    -------
    list of str
      Sorted absolute file paths for current logger normal/error log parts.
    """
    if not self.logger:
      return []
    logs_folder = self.logger.get_logs_folder()
    if not logs_folder or not os.path.isdir(logs_folder):
      return []

    prefix = f"{self.logger.file_prefix}_{self.logger.log_suffix}_"
    files: List[str] = []
    for file_name in sorted(os.listdir(logs_folder)):
      if not file_name.startswith(prefix):
        continue
      if file_name.endswith("_log.txt") or file_name.endswith("_error_log.txt"):
        files.append(os.path.join(logs_folder, file_name))
    return files

  def _wait_for_log_flush(self, timeout_seconds: float) -> bool:
    """
    Force enqueue of pending deltas and wait for writer drain.

    Parameters
    ----------
    timeout_seconds : float
      Maximum wait duration.

    Returns
    -------
    bool
      ``True`` when queue drains within timeout.
    """
    if not self.logger:
      return True

    # Ensure producer-side pending lines are queued before waiting.
    with self.logger.managed_lock_logger():
      if getattr(self.logger, "_save_enabled", False):
        self.logger._flush_pending_logs_async(force=True)

    writer_queue = getattr(self.logger, "_writer_queue", None)
    if writer_queue is None:
      return True

    deadline = time.perf_counter() + max(0.1, timeout_seconds)
    while time.perf_counter() < deadline:
      # Queue is considered drained only when both size and unfinished counters are zero.
      if writer_queue.qsize() == 0 and writer_queue.unfinished_tasks == 0:
        return True
      time.sleep(0.05)
    return False

  def _run_quality_check(self) -> Dict[str, object]:
    """
    Execute deterministic line-integrity validation after benchmark scenarios.

    The check starts at least 50 workers, each writing at
    least 200 deterministic lines following the format
    ``THREAD-{thread_idx}-LINE-{line_idx}``. After workers finish, the method
    scans log files and verifies every expected token is present.

    Returns
    -------
    dict
      Quality-check verdict and diagnostics including missing tokens.
    """
    assert self.logger is not None

    start_ts = time.perf_counter()
    # Enforce the requested minimum of 50 deterministic worker threads.
    thread_count = max(50, int(self.quality_check_threads))
    # Enforce the requested minimum of 200 deterministic lines per worker.
    lines_per_thread = max(200, int(self.quality_check_lines_per_thread))
    join_timeout_s = max(1.0, float(self.quality_check_join_timeout_seconds))
    flush_timeout_s = max(1.0, float(self.quality_check_flush_timeout_seconds))

    start_barrier = threading.Barrier(thread_count + 1)
    worker_counts = [0 for _ in range(thread_count)]

    def worker(thread_idx: int):
      try:
        # Barrier keeps deterministic workers aligned in start time.
        start_barrier.wait(timeout=10.0)
      except threading.BrokenBarrierError:
        return
      for line_idx in range(lines_per_thread):
        token = f"THREAD-{thread_idx}-LINE-{line_idx}"
        self.logger.P(token, show=False)
        worker_counts[thread_idx] += 1

    workers = [
      threading.Thread(target=worker, args=(thread_idx,), daemon=True, name=f"qc-{thread_idx}")
      for thread_idx in range(thread_count)
    ]
    for worker_thread in workers:
      worker_thread.start()

    barrier_ok = True
    try:
      start_barrier.wait(timeout=10.0)
    except threading.BrokenBarrierError:
      barrier_ok = False

    # Join workers with explicit timeout to avoid indefinite waits.
    join_deadline = time.perf_counter() + join_timeout_s
    alive = True
    while alive and time.perf_counter() < join_deadline:
      alive = False
      for worker_thread in workers:
        worker_thread.join(timeout=0.05)
        if worker_thread.is_alive():
          alive = True

    unfinished_threads = sum(1 for worker_thread in workers if worker_thread.is_alive())
    flush_ok = self._wait_for_log_flush(timeout_seconds=flush_timeout_s)

    log_files = self._collect_stage_log_files()
    line_token_pattern = re.compile(r"THREAD-(\d+)-LINE-(\d+)")
    seen_tokens = set()
    scanned_lines = 0
    for log_file in log_files:
      try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
          for raw_line in handle:
            scanned_lines += 1
            match = line_token_pattern.search(raw_line)
            if match is None:
              continue
            seen_tokens.add(f"THREAD-{int(match.group(1))}-LINE-{int(match.group(2))}")
      except OSError:
        continue

    expected_tokens = {
      f"THREAD-{thread_idx}-LINE-{line_idx}"
      for thread_idx in range(thread_count)
      for line_idx in range(lines_per_thread)
    }
    missing_tokens = sorted(expected_tokens - seen_tokens)

    # Worker counts are validated as a second signal against silent worker failures.
    min_worker_count = min(worker_counts) if worker_counts else 0
    passed = (
      barrier_ok and
      unfinished_threads == 0 and
      flush_ok and
      min_worker_count >= lines_per_thread and
      len(missing_tokens) == 0
    )

    return {
      "enabled": True,
      "passed": passed,
      "thread_count": thread_count,
      "lines_per_thread": lines_per_thread,
      "expected_line_count": len(expected_tokens),
      "observed_token_count": len(seen_tokens),
      "missing_count": len(missing_tokens),
      "missing_examples": missing_tokens[:20],
      "worker_counts": worker_counts,
      "min_worker_count": min_worker_count,
      "unfinished_threads": unfinished_threads,
      "barrier_ok": barrier_ok,
      "flush_ok": flush_ok,
      "log_files_checked": log_files,
      "scanned_lines": scanned_lines,
      "duration_s": time.perf_counter() - start_ts,
    }

  def _build_evolution(
    self,
    latencies: List[Tuple[float, float]],
    lock_waits: List[Tuple[float, float]],
    saves: List[Tuple[float, float, str, int]],
    monitor_samples: List[Tuple[float, int, int, int]],
    duration_s: float,
  ) -> List[Dict[str, float]]:
    """
    Build time-bucketed evolution metrics for one scenario.

    Parameters
    ----------
    latencies : list of tuple
      Per-call tuples `(relative_timestamp_s, latency_s)`.
    lock_waits : list of tuple
      Lock-wait tuples `(relative_timestamp_s, wait_s)`.
    saves : list of tuple
      Save tuples `(relative_timestamp_s, duration_s, file, log_len)`.
    monitor_samples : list of tuple
      Periodic snapshots `(relative_timestamp_s, app_lines, err_lines, file_size)`.
    duration_s : float
      Scenario duration in seconds.

    Returns
    -------
    list of dict
      One dict per bucket with throughput/latency/save summaries.
    """
    bucket_count = max(1, int(math.ceil(duration_s / self.bucket_seconds)))
    rows: List[Dict[str, float]] = []
    for bucket_idx in range(bucket_count):
      # Build per-bucket slices from call, lock, and save streams.
      start = bucket_idx * self.bucket_seconds
      end = min((bucket_idx + 1) * self.bucket_seconds, duration_s + 1e-9)
      bucket_lat = [lat for ts, lat in latencies if start <= ts < end]
      bucket_lock = [wait for ts, wait in lock_waits if start <= ts < end]
      bucket_saves = [dur for ts, dur, _, _ in saves if start <= ts < end]
      bucket_calls = len(bucket_lat)
      bucket_dur = max(end - start, 1e-9)
      row = {
        "bucket_start_s": start,
        "bucket_end_s": end,
        "calls": bucket_calls,
        "calls_per_sec": bucket_calls / bucket_dur,
        "latency_p50_ms": _pct([x * 1000.0 for x in bucket_lat], 0.50) if bucket_lat else 0.0,
        "latency_p95_ms": _pct([x * 1000.0 for x in bucket_lat], 0.95) if bucket_lat else 0.0,
        "latency_p99_ms": _pct([x * 1000.0 for x in bucket_lat], 0.99) if bucket_lat else 0.0,
        "lock_wait_p95_ms": _pct([x * 1000.0 for x in bucket_lock], 0.95) if bucket_lock else 0.0,
        "save_count": len(bucket_saves),
        "save_p95_ms": _pct([x * 1000.0 for x in bucket_saves], 0.95) if bucket_saves else 0.0,
      }
      if monitor_samples:
        # Add trailing size/line snapshots to correlate latency with log growth.
        in_bucket = [
          sample for sample in monitor_samples
          if start <= sample[0] <= end
        ]
        if in_bucket:
          row["log_lines_last"] = float(in_bucket[-1][1])
          row["log_file_size_last_bytes"] = float(in_bucket[-1][3])
        else:
          row["log_lines_last"] = 0.0
          row["log_file_size_last_bytes"] = 0.0
      rows.append(row)
    return rows

  def _detect_throttling(self, evolution: List[Dict[str, float]]) -> Tuple[Optional[float], float]:
    """
    Detect sustained throughput degradation in evolution buckets.

    Parameters
    ----------
    evolution : list of dict
      Bucketized metrics produced by `_build_evolution`.

    Returns
    -------
    tuple
      `(start_time_s, drop_percent)` where `start_time_s` may be `None`
      when no sustained throttling pattern is detected.
    """
    if len(evolution) < 3:
      return None, 0.0
    base = max(evolution[0]["calls_per_sec"], 1e-9)
    lowest = min(row["calls_per_sec"] for row in evolution)
    scale_drop_pct = max(0.0, 100.0 * (1.0 - lowest / base))
    threshold = 0.70 * base
    # Require two consecutive degraded buckets to reduce false positives.
    for i in range(1, len(evolution) - 1):
      if evolution[i]["calls_per_sec"] < threshold and evolution[i + 1]["calls_per_sec"] < threshold:
        return evolution[i]["bucket_start_s"], scale_drop_pct
    return None, scale_drop_pct

  def run_scenario(self, thread_count: int, scenario_idx: int) -> ScenarioResult:
    """
    Execute one full benchmark scenario.

    Parameters
    ----------
    thread_count : int
      Number of worker threads sharing one logger instance.
    scenario_idx : int
      Scenario index used to derive deterministic per-thread RNG seeds.

    Returns
    -------
    ScenarioResult
      Aggregated metrics and evolution tables for the scenario.
    """
    assert self.logger is not None
    assert self.instrument is not None
    logger = self.logger
    instrument = self.instrument

    # Track absolute timestamps so instrumentation streams can be aligned later.
    scenario_start_abs = time.perf_counter()
    lock_start_idx = len(instrument.lock_wait_events)
    save_start_idx = len(instrument.save_events)

    log_lines_before = len(logger.app_log)
    file_size_before = self._sample_log_file_size()

    # Shared stop flag and per-thread local capture buffers avoid lock pressure.
    stop_event = threading.Event()
    join_deadline_s = 15.0
    worker_latencies: List[List[Tuple[float, float]]] = [[] for _ in range(thread_count)]
    worker_counts = [0 for _ in range(thread_count)]

    def worker(thread_idx: int):
      # Deterministic RNG per worker keeps sleep pattern reproducible.
      rng = random.Random(self.seed + scenario_idx * 1000 + thread_idx)
      calls = 0
      local_latencies: List[Tuple[float, float]] = []
      while not stop_event.is_set():
        t0 = time.perf_counter()
        msg = f"bench stage={self.stage_name} th={thread_count} idx={thread_idx} call={calls}"
        # The measured critical call under test.
        logger.P(msg, show=False)
        t1 = time.perf_counter()
        local_latencies.append((t0 - scenario_start_abs, t1 - t0))
        calls += 1
        delay = rng.uniform(self.min_delay_s, self.max_delay_s)
        if stop_event.wait(delay):
          break
      worker_latencies[thread_idx] = local_latencies
      worker_counts[thread_idx] = calls

    monitor_samples: List[Tuple[float, int, int, int]] = []

    def monitor():
      # Coarse periodic snapshots expose file growth across scenario lifetime.
      while not stop_event.wait(1.0):
        t = time.perf_counter() - scenario_start_abs
        monitor_samples.append((
          t,
          len(logger.app_log),
          len(logger.err_log),
          self._sample_log_file_size(),
        ))
      t = time.perf_counter() - scenario_start_abs
      monitor_samples.append((
        t,
        len(logger.app_log),
        len(logger.err_log),
        self._sample_log_file_size(),
      ))

    monitor_thread = threading.Thread(target=monitor, name=f"monitor-{thread_count}", daemon=True)
    workers = [
      threading.Thread(target=worker, args=(i,), name=f"bench-{thread_count}-{i}", daemon=True)
      for i in range(thread_count)
    ]

    monitor_thread.start()
    for th in workers:
      th.start()

    # Explicit bounded runtime loop prevents indefinite benchmark sessions.
    end_deadline = scenario_start_abs + float(self.run_seconds)
    while True:
      now = time.perf_counter()
      if now >= end_deadline:
        break
      # Bounded sleep keeps stop timing precise without busy waiting.
      time.sleep(min(0.25, end_deadline - now))

    stop_event.set()
    join_deadline = time.perf_counter() + join_deadline_s
    alive = True
    while alive and time.perf_counter() < join_deadline:
      alive = False
      for th in workers:
        th.join(timeout=0.05)
        if th.is_alive():
          alive = True
    monitor_thread.join(timeout=2.0)

    join_timeout_threads = sum(1 for th in workers if th.is_alive())

    scenario_end_abs = time.perf_counter()
    duration_s = max(1e-9, scenario_end_abs - scenario_start_abs)

    # Slice instrumentation streams to scenario-local windows.
    lock_end_idx = len(instrument.lock_wait_events)
    save_end_idx = len(instrument.save_events)
    lock_events_slice, save_events_slice = instrument.event_slices(
      lock_start_idx,
      lock_end_idx,
      save_start_idx,
      save_end_idx,
    )

    latencies_flat: List[Tuple[float, float]] = []
    for per_thread in worker_latencies:
      latencies_flat.extend(per_thread)

    lock_waits_rel = [(ts - scenario_start_abs, wait) for ts, wait in lock_events_slice]
    save_events_rel = [
      (ts - scenario_start_abs, dur, log_file, log_len)
      for ts, dur, log_file, log_len in save_events_slice
    ]

    # Aggregate scenario-level KPI summaries.
    total_calls = sum(worker_counts)
    calls_per_sec = total_calls / duration_s
    latency_summary = _summarize_ms([lat for _, lat in latencies_flat])
    lock_wait_summary = _summarize_ms([wait for _, wait in lock_waits_rel])
    save_duration_summary = _summarize_ms([dur for _, dur, _, _ in save_events_rel])
    save_count = len(save_events_rel)
    save_calls_per_sec = save_count / duration_s

    evolution = self._build_evolution(
      latencies=latencies_flat,
      lock_waits=lock_waits_rel,
      saves=save_events_rel,
      monitor_samples=monitor_samples,
      duration_s=duration_s,
    )
    throttling_start_s, throttling_scale_drop_pct = self._detect_throttling(evolution)

    log_lines_after = len(logger.app_log)
    file_size_after = self._sample_log_file_size()

    return ScenarioResult(
      thread_count=thread_count,
      duration_s=duration_s,
      total_calls=total_calls,
      calls_per_sec=calls_per_sec,
      latency_summary_ms=latency_summary,
      lock_wait_summary_ms=lock_wait_summary,
      save_duration_summary_ms=save_duration_summary,
      save_count=save_count,
      save_calls_per_sec=save_calls_per_sec,
      log_lines_before=log_lines_before,
      log_lines_after=log_lines_after,
      log_file_size_before_bytes=file_size_before,
      log_file_size_after_bytes=file_size_after,
      throttling_start_s=throttling_start_s,
      throttling_scale_drop_pct=throttling_scale_drop_pct,
      evolution=evolution,
      join_timeout_threads=join_timeout_threads,
    )

  def _hardware_runtime_notes(self) -> Dict[str, str]:
    """
    Capture host/runtime notes included in reports.

    Returns
    -------
    dict
      Environment metadata used for reproducibility context.
    """
    return {
      "timestamp": datetime.now().isoformat(),
      "hostname": socket.gethostname(),
      "platform": platform.platform(),
      "python_version": platform.python_version(),
      "python_implementation": platform.python_implementation(),
      "cpu_count": str(os.cpu_count()),
      "bench_run_seconds": str(self.run_seconds),
      "thread_scenarios": ",".join(str(x) for x in self.thread_scenarios),
      "delay_ms_range": f"{int(self.min_delay_s * 1000)}-{int(self.max_delay_s * 1000)}",
      "seed": str(self.seed),
      "bucket_seconds": str(self.bucket_seconds),
      "base_folder": self.base_folder,
      "app_folder": self.app_folder,
      "quality_check_enabled": str(self.quality_check_enabled),
      "quality_check_threads": str(max(50, int(self.quality_check_threads))),
      "quality_check_lines_per_thread": str(max(200, int(self.quality_check_lines_per_thread))),
    }

  def _serialize_result(self, result: ScenarioResult) -> Dict:
    """
    Convert dataclass result into JSON-serializable dictionary.

    Parameters
    ----------
    result : ScenarioResult
      Scenario result object.

    Returns
    -------
    dict
      Plain dictionary representation.
    """
    return {
      "thread_count": result.thread_count,
      "duration_s": result.duration_s,
      "total_calls": result.total_calls,
      "calls_per_sec": result.calls_per_sec,
      "latency_summary_ms": result.latency_summary_ms,
      "lock_wait_summary_ms": result.lock_wait_summary_ms,
      "save_duration_summary_ms": result.save_duration_summary_ms,
      "save_count": result.save_count,
      "save_calls_per_sec": result.save_calls_per_sec,
      "log_lines_before": result.log_lines_before,
      "log_lines_after": result.log_lines_after,
      "log_file_size_before_bytes": result.log_file_size_before_bytes,
      "log_file_size_after_bytes": result.log_file_size_after_bytes,
      "throttling_start_s": result.throttling_start_s,
      "throttling_scale_drop_pct": result.throttling_scale_drop_pct,
      "evolution": result.evolution,
      "join_timeout_threads": result.join_timeout_threads,
    }

  def _diagnose(self, results: List[ScenarioResult]) -> List[str]:
    """
    Generate concise bottleneck diagnosis lines per scenario.

    Parameters
    ----------
    results : list of ScenarioResult
      Scenario outputs to inspect.

    Returns
    -------
    list of str
      Human-readable diagnosis bullet lines.
    """
    lines: List[str] = []
    for res in results:
      dominant = "none"
      save_p95 = res.save_duration_summary_ms["p95_ms"]
      lock_p95 = res.lock_wait_summary_ms["p95_ms"]
      lat_p95 = res.latency_summary_ms["p95_ms"]
      if save_p95 > 1.0 and lock_p95 > 1.0:
        dominant = "save I/O under logger lock"
      elif lock_p95 > 1.0:
        dominant = "lock contention"
      elif lat_p95 > 1.0:
        dominant = "call path overhead"

      throttle = (
        f"starts around {res.throttling_start_s:.1f}s"
        if res.throttling_start_s is not None
        else "not strongly detected"
      )
      lines.append(
        f"- {res.thread_count} threads: dominant bottleneck `{dominant}`; throttling {throttle}; "
        f"throughput drop={res.throttling_scale_drop_pct:.1f}% within scenario."
      )
    return lines

  def _render_report(
    self,
    notes: Dict[str, str],
    results: List[ScenarioResult],
    report_path: str,
    metrics_path: str,
    quality_check_result: Optional[Dict[str, object]] = None,
  ) -> str:
    """
    Render Markdown report for one benchmark stage.

    Parameters
    ----------
    notes : dict
      Environment/runtime context metadata.
    results : list of ScenarioResult
      Scenario outputs included in the report.
    report_path : str
      Destination markdown file path.
    metrics_path : str
      Path to companion JSON metrics payload.
    quality_check_result : dict or None, optional
      Deterministic integrity check output when enabled.

    Returns
    -------
    str
      Rendered markdown content.
    """
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    header = [
      f"# {self.stage_name} Logger Throughput Report",
      "",
      f"- Generated: `{datetime.now().isoformat()}`",
      f"- Report path: `{report_path}`",
      f"- Metrics path: `{metrics_path}`",
      "",
      "## Test Parameters",
      "",
    ]
    for key, value in notes.items():
      header.append(f"- {key}: `{value}`")

    # Section 1: top-line scenario KPI table.
    summary_table = [
      "",
      "## Raw Scenario Metrics",
      "",
      "| Threads | Duration(s) | Calls | Calls/sec | log.P p50 ms | p95 ms | p99 ms | max ms | lock p95 ms | _save count | _save p95 ms | throttle start s |",
      "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for res in results:
      summary_table.append(
        "| {threads} | {dur} | {calls} | {cps} | {p50} | {p95} | {p99} | {mx} | {lock_p95} | {save_count} | {save_p95} | {throttle} |".format(
          threads=res.thread_count,
          dur=_fmt(res.duration_s),
          calls=res.total_calls,
          cps=_fmt(res.calls_per_sec),
          p50=_fmt(res.latency_summary_ms["p50_ms"]),
          p95=_fmt(res.latency_summary_ms["p95_ms"]),
          p99=_fmt(res.latency_summary_ms["p99_ms"]),
          mx=_fmt(res.latency_summary_ms["max_ms"]),
          lock_p95=_fmt(res.lock_wait_summary_ms["p95_ms"]),
          save_count=res.save_count,
          save_p95=_fmt(res.save_duration_summary_ms["p95_ms"]),
          throttle=_fmt(res.throttling_start_s) if res.throttling_start_s is not None else "n/a",
        )
      )

    # Section 2: log size growth and save frequency view.
    growth_table = [
      "",
      "## Log Growth and Save Behavior",
      "",
      "| Threads | Log lines before | Log lines after | Log file bytes before | Log file bytes after | _save/sec | join timeouts |",
      "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for res in results:
      growth_table.append(
        "| {threads} | {lb} | {la} | {fb} | {fa} | {save_ps} | {timeouts} |".format(
          threads=res.thread_count,
          lb=res.log_lines_before,
          la=res.log_lines_after,
          fb=res.log_file_size_before_bytes,
          fa=res.log_file_size_after_bytes,
          save_ps=_fmt(res.save_calls_per_sec),
          timeouts=res.join_timeout_threads,
        )
      )

    # Section 3: time evolution table per thread scenario.
    evolution_sections = ["", "## Evolution Tables (5s Buckets)", ""]
    for res in results:
      evolution_sections.append(f"### Threads={res.thread_count}")
      evolution_sections.append("")
      evolution_sections.append(
        "| Bucket start s | Bucket end s | Calls | Calls/sec | Lat p50 ms | Lat p95 ms | Lat p99 ms | Lock p95 ms | Save count | Save p95 ms | Log lines(last) | File bytes(last) |"
      )
      evolution_sections.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
      for row in res.evolution:
        evolution_sections.append(
          "| {bs} | {be} | {calls} | {cps} | {lp50} | {lp95} | {lp99} | {lock95} | {save_count} | {save95} | {lines} | {bytesz} |".format(
            bs=_fmt(row["bucket_start_s"]),
            be=_fmt(row["bucket_end_s"]),
            calls=int(row["calls"]),
            cps=_fmt(row["calls_per_sec"]),
            lp50=_fmt(row["latency_p50_ms"]),
            lp95=_fmt(row["latency_p95_ms"]),
            lp99=_fmt(row["latency_p99_ms"]),
            lock95=_fmt(row["lock_wait_p95_ms"]),
            save_count=int(row["save_count"]),
            save95=_fmt(row["save_p95_ms"]),
            lines=int(row.get("log_lines_last", 0.0)),
            bytesz=int(row.get("log_file_size_last_bytes", 0.0)),
          )
        )
      evolution_sections.append("")

    # Section 4: short diagnosis summary.
    diagnosis = [
      "## Concise Diagnosis",
      "",
      "- Baseline contention source is inferred from lock wait and save timing correlation.",
      "- Potential throttling is flagged when consecutive buckets drop below 70% of initial throughput.",
      "",
    ]
    diagnosis.extend(self._diagnose(results))

    quality_section: List[str] = []
    if quality_check_result is not None:
      quality_section.extend([
        "",
        "## Deterministic Quality Check",
        "",
        f"- enabled: `{quality_check_result.get('enabled', False)}`",
        f"- passed: `{quality_check_result.get('passed', False)}`",
        f"- threads: `{quality_check_result.get('thread_count', 0)}`",
        f"- lines/thread: `{quality_check_result.get('lines_per_thread', 0)}`",
        f"- expected lines: `{quality_check_result.get('expected_line_count', 0)}`",
        f"- observed tokens: `{quality_check_result.get('observed_token_count', 0)}`",
        f"- missing tokens: `{quality_check_result.get('missing_count', 0)}`",
        f"- flush_ok: `{quality_check_result.get('flush_ok', False)}`",
        f"- unfinished threads: `{quality_check_result.get('unfinished_threads', 0)}`",
        f"- scanned lines: `{quality_check_result.get('scanned_lines', 0)}`",
        "",
      ])
      missing_examples = quality_check_result.get("missing_examples", [])
      if missing_examples:
        quality_section.append(f"- missing examples: `{', '.join(missing_examples[:10])}`")
        quality_section.append("")

    content = "\n".join(
      header + summary_table + growth_table + evolution_sections + diagnosis + quality_section
    ) + "\n"
    with open(report_path, "w", encoding="utf-8") as fh:
      fh.write(content)
    return content

  def run(self) -> Dict:
    """
    Execute all configured scenarios and persist artifacts.

    Returns
    -------
    dict
      Stage payload containing report path, metrics path, and serialized
      scenario outputs.
    """
    notes = self._hardware_runtime_notes()
    self.logger = self._new_logger()
    self.instrument = LoggerInstrumentation(self.logger)
    self.instrument.install()

    results: List[ScenarioResult] = []
    quality_check_result: Optional[Dict[str, object]] = None
    try:
      # Keep scenario order stable for consistent A/B comparisons.
      for idx, thread_count in enumerate(self.thread_scenarios):
        results.append(self.run_scenario(thread_count=thread_count, scenario_idx=idx))
      if self.quality_check_enabled:
        # Post-run integrity check validates deterministic per-thread line durability.
        quality_check_result = self._run_quality_check()
    finally:
      self.instrument.uninstall()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(self.output_dir, f"{ts}_{self.stage_name}_REPORT.md")
    metrics_path = os.path.join(self.output_dir, f"{ts}_{self.stage_name}_METRICS.json")

    self._render_report(
      notes=notes,
      results=results,
      report_path=report_path,
      metrics_path=metrics_path,
      quality_check_result=quality_check_result,
    )

    payload = {
      "stage_name": self.stage_name,
      "notes": notes,
      "results": [self._serialize_result(x) for x in results],
      "quality_check": quality_check_result,
      "report_path": report_path,
      "metrics_path": metrics_path,
    }
    with open(metrics_path, "w", encoding="utf-8") as fh:
      json.dump(payload, fh, indent=2)
    return payload


def parse_args():
  """
  Parse CLI arguments for the logger benchmark harness.

  Returns
  -------
  argparse.Namespace
    Parsed command-line options.
  """
  parser = argparse.ArgumentParser(description="Ratio1 logger throughput benchmark")
  parser.add_argument("--stage-name", default="STAGE_A", help="Stage label used in output filenames")
  parser.add_argument("--run-seconds", type=int, default=60, help="Duration per scenario")
  parser.add_argument(
    "--thread-scenarios",
    default="1,10,30,60,100",
    help="Comma-separated thread counts",
  )
  parser.add_argument("--min-delay-ms", type=int, default=1, help="Min per-call sleep in ms")
  parser.add_argument("--max-delay-ms", type=int, default=100, help="Max per-call sleep in ms")
  parser.add_argument("--seed", type=int, default=1337, help="RNG seed")
  parser.add_argument("--bucket-seconds", type=int, default=5, help="Bucket size for evolution tables")
  parser.add_argument("--output-dir", default="xperimental/logger", help="Report output folder")
  parser.add_argument("--base-folder", default="/tmp/r1sdk_logger_bench", help="Logger base folder")
  parser.add_argument("--app-folder", default="logger_throughput", help="Logger app folder")
  parser.add_argument(
    "--skip-quality-check",
    action="store_true",
    help="Disable deterministic 50-thread line-integrity quality check",
  )
  parser.add_argument(
    "--quality-check-threads",
    type=int,
    default=50,
    help="Number of threads used by deterministic quality check (minimum enforced: 50)",
  )
  parser.add_argument(
    "--quality-check-lines-per-thread",
    type=int,
    default=200,
    help="Deterministic lines emitted per quality-check thread (min enforced: 200)",
  )
  parser.add_argument(
    "--quality-check-join-timeout-seconds",
    type=float,
    default=30.0,
    help="Maximum wait for quality-check worker joins",
  )
  parser.add_argument(
    "--quality-check-flush-timeout-seconds",
    type=float,
    default=30.0,
    help="Maximum wait for quality-check async writer drain",
  )
  parser.add_argument("--ci", action="store_true", help="Enable CI pass/fail checks")
  parser.add_argument(
    "--ci-min-calls-per-sec-high",
    type=float,
    default=300.0,
    help="Minimum allowed calls/sec for the highest thread scenario when --ci is enabled",
  )
  parser.add_argument(
    "--ci-max-p95-latency-ms-high",
    type=float,
    default=400.0,
    help="Maximum allowed p95 log.P latency (ms) for the highest thread scenario when --ci is enabled",
  )
  return parser.parse_args()


def main():
  """
  Entrypoint for stage benchmark execution.

  Returns
  -------
  None
    Prints JSON payloads with generated artifact paths and optional CI status.
  """
  args = parse_args()
  thread_scenarios = [int(x.strip()) for x in args.thread_scenarios.split(",") if x.strip()]
  tester = LoggerTester(
    run_seconds=args.run_seconds,
    thread_scenarios=thread_scenarios,
    min_delay_ms=args.min_delay_ms,
    max_delay_ms=args.max_delay_ms,
    seed=args.seed,
    bucket_seconds=args.bucket_seconds,
    stage_name=args.stage_name,
    output_dir=args.output_dir,
    base_folder=args.base_folder,
    app_folder=args.app_folder,
    quality_check_enabled=not args.skip_quality_check,
    quality_check_threads=args.quality_check_threads,
    quality_check_lines_per_thread=args.quality_check_lines_per_thread,
    quality_check_join_timeout_seconds=args.quality_check_join_timeout_seconds,
    quality_check_flush_timeout_seconds=args.quality_check_flush_timeout_seconds,
  )
  payload = tester.run()
  quality_result = payload.get("quality_check")
  if quality_result is not None:
    print(json.dumps({
      "quality_check_enabled": quality_result.get("enabled", False),
      "quality_check_passed": quality_result.get("passed", False),
      "thread_count": quality_result.get("thread_count", 0),
      "lines_per_thread": quality_result.get("lines_per_thread", 0),
      "missing_count": quality_result.get("missing_count", 0),
      "unfinished_threads": quality_result.get("unfinished_threads", 0),
      "flush_ok": quality_result.get("flush_ok", False),
    }, indent=2))
    if not quality_result.get("passed", False):
      raise SystemExit(3)

  if args.ci:
    # CI mode validates only the highest-concurrency scenario against thresholds.
    high_threads = max(thread_scenarios)
    high_result = None
    for result in payload["results"]:
      if result["thread_count"] == high_threads:
        high_result = result
        break
    if high_result is None:
      raise RuntimeError("Highest thread scenario not found in benchmark results")

    high_cps = high_result["calls_per_sec"]
    high_p95 = high_result["latency_summary_ms"]["p95_ms"]
    # Threshold checks are explicit and deterministic for regression gating.
    ci_pass = (
      high_cps >= args.ci_min_calls_per_sec_high and
      high_p95 <= args.ci_max_p95_latency_ms_high
    )
    print(json.dumps({
      "ci_enabled": True,
      "ci_pass": ci_pass,
      "high_threads": high_threads,
      "calls_per_sec": high_cps,
      "p95_latency_ms": high_p95,
      "min_calls_per_sec_required": args.ci_min_calls_per_sec_high,
      "max_p95_latency_ms_allowed": args.ci_max_p95_latency_ms_high,
    }, indent=2))
    if not ci_pass:
      raise SystemExit(2)

  print(json.dumps({
    "stage_name": payload["stage_name"],
    "report_path": payload["report_path"],
    "metrics_path": payload["metrics_path"],
  }, indent=2))


if __name__ == "__main__":
  main()
