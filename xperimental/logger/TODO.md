# Logger Optimization TODO

## Scope
- Target file: `ratio1/logging/base_logger.py`
- Validation harness: `xperimental/logger/logger_tester.py`
- Baseline artifacts reviewed:
- `xperimental/logger/20260206_230125_QUICK_CHECK_REPORT.md`
- `xperimental/logger/20260206_230139_QUICK_QC_REPORT.md`
- `xperimental/logger/20260206_230425_ANALYZE_REPORT.md`

## Goals
- Keep producer-path latency low under concurrency.
- Preserve durability guarantees for error/shutdown/rotation paths.
- Reduce writer I/O overhead without changing public Logger API.
- Improve observability for queue pressure and force-fallback behavior.

## Plan
1. Extend telemetry with pressure and fallback counters.
- Add counters for:
- force queue-full fallback writes (`_save_log` outside writer thread)
- non-force queue-full drop events
- flush trigger reasons (`idle`, `buffer`, `error_immediate`, `shutdown`, `rotation`)
- Expose them through `get_log_writer_telemetry()`.
- Add these fields to `logger_tester.py` JSON/Markdown outputs.
- Acceptance: overload scenarios clearly show where pressure occurred and how often fallback paths were used.

2. Implement writer-side micro-batching and task coalescing.
- In `_log_writer_loop()`, drain more than one queue item per wake-up (bounded batch).
- Coalesce adjacent ranges for the same `(log_ref, log_file)` before calling `_save_log`.
- Keep task ordering constraints intact for each file.
- Acceptance: lower `_save_count` and lower write latency p95 in `logger_tester.py` at same total line volume.

3. Reduce lock impact of force-fallback writes.
- Current force path can call `_save_log` directly when queue is full.
- Add a second-chance blocking enqueue window before direct fallback.
- If direct fallback remains necessary, capture metrics and keep it limited to critical paths.
- Acceptance: logger lock wait p95 remains stable under forced-pressure tests; no missing tokens in quality check.

4. Add idle-time flush when producers go silent.
- Current idle policy is evaluated only when `_logger(...)` is called.
- Add a lightweight periodic check in writer lifecycle to flush unsaved deltas after idle threshold even without new log calls.
- Acceptance: after a short burst then silence, lines are persisted within bounded delay (`idle_seconds + tick_interval`).

5. Add adaptive backpressure controls.
- Dynamically tune enqueue behavior when queue depth passes high watermark.
- Candidate behavior:
- temporarily increase batch threshold to reduce queue item churn
- optionally auto-enable duplicate suppression for repeated identical messages
- Restore configured settings when queue pressure clears.
- Acceptance: lower drop incidence and stable producer p95 under sustained high-thread scenarios.

6. Expand benchmark matrix and CI checks.
- Add dedicated scenarios in `logger_tester.py`:
- small queue size stress (intentional pressure)
- rotation stress (small `max_lines`)
- error-heavy burst path (frequent immediate flush)
- high-concurrency sustained profile (100+ threads)
- Add pass/fail checks for:
- deterministic quality check success
- acceptable p95 producer latency
- bounded or zero dropped lines in nominal profiles
- Acceptance: reproducible metrics and clear regression signal in CI mode.

## Out Of Scope
- Public API changes for `Logger.P`, `Logger.log`, or caller integration.
- Changes to unrelated modules outside logger persistence path.
