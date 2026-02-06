# BaseLogger Modifications

This document describes only the modifications made in `ratio1/logging/base_logger.py`: what changed, why it changed, and how the new flow works.

## Why `BaseLogger` Was Changed

The original `BaseLogger` persistence path executed synchronous full-file rewrites directly from `_logger`, while holding the logger lock. Under concurrent `log.P(...)` calls, this created a hot critical section where:

- lock wait time scaled with thread count and file size
- producer latency was coupled to disk latency
- throughput degraded as logs grew

The goal of the changes was to keep producer-side logging cheap and predictable while preserving functional behavior.

## Summary of What Changed

The `BaseLogger` changes were introduced in two levels.

### B.1 Minimal Behavioral Change

- Added dynamic save trigger policy in `_logger`:
  - flush when idle gap since previous log call is greater than `1s`
  - otherwise flush every `100` unsaved lines
- Introduced internal tracking of pending unsaved lengths instead of writing on every call

This reduced save frequency significantly but still kept writes in the producer path.

### B.2 Extended Architectural Change

- Replaced producer-thread synchronous persistence with async queue-based persistence
- Replaced rewrite-heavy persistence with append-only delta writes
- Added bounded queue, writer thread, and telemetry counters
- Added configurable flush policy and optional repeat suppression
- Added safe shutdown path for writer drain

## Data Structures Added in `BaseLogger`

The following internal fields were added to support async persistence:

- Flush policy:
  - `_save_idle_seconds`
  - `_save_buffer_len`
  - `_error_flush_immediate`
- Producer enqueue cursors:
  - `_last_enqueued_app_len`
  - `_last_enqueued_err_len`
- Per-file append offsets:
  - `_save_file_offsets`
- Writer queue/thread:
  - `_writer_queue_maxsize`
  - `_writer_queue`
  - `_writer_stop_event`
  - `_writer_thread`
- Telemetry:
  - `_writer_dropped_lines`
  - `_writer_queue_high_watermark`
  - `_writer_batches_written`
  - `_writer_lines_written`
  - `_writer_latency_ms`
- Optional rate control:
  - `_rate_limit_enabled`
  - `_rate_limit_window_seconds`
  - `_rate_limit_max_repeats`
  - `_rate_limit_state`
  - `_rate_limit_suppressed_messages`

## New/Updated Methods and Behavior

### Producer Path

- `_logger(...)`
  - now decides whether to flush based on idle/buffer policy
  - enqueue-based flush (`_flush_pending_logs_async`) replaces direct save calls
  - supports immediate error-triggered flush path
  - optional suppression via `_should_emit_log(...)`

### Persistence Control

- `configure_flush_policy(...)`
  - runtime control of idle threshold, buffer size, and immediate error flush
- `configure_rate_control(...)`
  - runtime control for repeat suppression
- `get_log_writer_telemetry()`
  - returns queue/latency/drop counters for observability

### Writer Lifecycle

- `_init_log_writer()`
  - starts daemon writer thread and registers `atexit` shutdown hook
- `_shutdown_log_writer(timeout=...)`
  - forces final enqueue, signals stop, and joins writer thread
- `_log_writer_loop()`
  - consumes queued delta tasks and executes `_save_log(...)`

### Queue and Delta Handling

- `_enqueue_save_task(...)`
  - queues delta segments
  - forced path can fallback to direct write when queue is full
  - non-forced overflow increments dropped-lines telemetry
- `_flush_pending_logs_async(force=...)`
  - computes unsaved delta ranges for app/error logs and enqueues them
- `_sync_enqueued_log_lengths()`
  - clamps enqueue cursors after truncation/rotation
- `_should_save_logs(elapsed_since_last_call)`
  - returns flush decision from idle/buffer policy

### Persistence Implementation

- `_save_log(...)` signature expanded:
  - added `start_idx`, `end_idx`, `force_rewrite`
- append-only delta mode:
  - default mode writes only unsaved range in append mode
  - updates `_save_file_offsets` per file
- compatibility mode:
  - HTML output still forces full rewrite to preserve wrappers

### Rotation Compatibility

- `_check_log_size()`
  - now forces pending flush before list reset and path rotation
  - resets enqueue cursors on list truncation
- `_generate_log_path()`
  - initializes save offset for new normal-log file
- `_generate_error_log_path()`
  - initializes save offset for new error-log file

## End-to-End Flow (New)

1. `P(...)` -> `_logger(...)` acquires logger lock.
2. Message is appended in memory (`app_log`, optionally `err_log`).
3. Flush decision is evaluated:
   - idle gap
   - buffer threshold
   - immediate error policy
4. Unsaved ranges are enqueued to writer queue.
5. Writer thread persists ranges via `_save_log(...)`.
6. Telemetry counters are updated for queue depth, latency, and drops.
7. On shutdown, pending work is force-enqueued and writer thread is drained.

## Tradeoffs Introduced

- Normal logs are eventually persisted, not always immediately persisted.
- Under extreme sustained pressure, non-forced queue overflows can drop lines.
- Forced/error paths preserve stronger durability by allowing fallback write.
- Added complexity in exchange for strong concurrency scalability.

## Compatibility Notes

- Public logging calls (`P`, `p`, `log`) are unchanged.
- Existing callers do not need API changes.
- HTML log mode behavior is preserved via forced rewrite path.

## Operational Guidance

- Monitor `get_log_writer_telemetry()` in production, especially:
  - `dropped_lines`
  - `queue_high_watermark`
  - `write_latency_p95_ms`
- Keep immediate error flush enabled unless there is a clear reason to relax it.
- Tune `configure_flush_policy(...)` per workload profile.
