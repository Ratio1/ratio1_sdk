# AGENTS

## Objectives
- Provide a Python SDK for the Ratio1 network so clients can build and deploy low-code job/pipeline workloads to Ratio1 Edge Nodes.
- Offer tooling for node discovery, auth (dAuth), and cooperative execution across nodes.
- Ship a CLI for interacting with the network and node management workflows.

## Repository Structure
- `ratio1/`: main Python package
- `ratio1/base/`: core session/pipeline/instance abstractions and plugin templates
- `ratio1/bc/`: blockchain, dAuth, and EVM-related logic
- `ratio1/default/`: default implementations (MQTT session and instance defaults)
- `ratio1/cli/`: CLI implementation (entrypoint for `r1ctl`)
- `ratio1/ipfs/`: IPFS/R1FS helpers and integrations
- `ratio1/logging/`: logging mixins and upload/download helpers
- `ratio1/const/`: constants and shared enums
- `ratio1/utils/`: utility helpers (env loading, tooling, oracles)
- `tutorials/`: runnable examples and usage patterns
- `README.md`: high-level overview and quick start
- `r1ctl.MD`: CLI manual (nepctl/r1ctl usage)
- `pyproject.toml`: packaging metadata and CLI script entrypoint

## Module Responsibilities
- `ratio1/base/generic_session.py`: session lifecycle, node discovery, request/response flow
- `ratio1/base/pipeline.py`: pipeline definitions, command sending, and transaction tracking
- `ratio1/base/instance.py`: instance-level control and command orchestration
- `ratio1/base/plugin_template.py`: remote execution template and plugin API surface
- `ratio1/bc/base.py`: signing/verification utilities and dAuth autoconfiguration
- `ratio1/bc/evm.py`: EVM interactions and transaction wait utilities
- `ratio1/ipfs/r1fs.py`: IPFS/R1FS client utilities and request wrappers
- `ratio1/cli/`: `r1ctl` command implementations and user-facing CLI flows

## Key Entry Points
- `ratio1/__init__.py`: exports `Session`, `Pipeline`, `Instance`, `CustomPluginTemplate`, presets, and helpers.
- CLI: `r1ctl` -> `ratio1.cli.cli:main` (see `r1ctl.MD` for commands).

## Development Notes
- dAuth is used for auto-configuration; network calls should set explicit timeouts.
- `template.env` and `.env` are used for local config and secrets.
- Docs mention `nepctl` while packaging registers `r1ctl`; confirm expected CLI naming when updating docs.

## Living Architecture Memory (Update This Section)
- This section is a shared, living memory. Update it whenever you discover critical behavior, contracts, or architecture details.
- Core objects: `Session` manages comms and callbacks; `Pipeline` (aka Stream) groups plugin instances; `Instance` represents a plugin instance; `CustomPluginTemplate` mirrors on-edge plugin APIs for remote execution.
- Addressing and IDs: node address prefix is `0xai_`; session `name` becomes `INITIATOR_ID` and `SESSION_ID`; `EE_PAYLOAD_PATH` is `[node_id, pipeline_name, signature, instance_id]` and currently uses node alias rather than address (see TODO in `ratio1/base/generic_session.py`).
- Message flow: default MQTT uses three communicators (payloads, heartbeats/ctrl, notifications) with separate threads/queues; message handling is JSON -> optional decrypt -> formatter decode -> dispatch to session/pipeline/instance callbacks and transaction/response handlers.
- Formatting: payloads can specify `EE_FORMATTER`; decoding is via `IOFormatterWrapper` with plugin locations (default `plugins.io_formatters`).
- Comms channels: topics are defined by `CONFIG_CHANNEL`, `CTRL_CHANNEL`, `NOTIF_CHANNEL`, `PAYLOADS_CHANNEL`; `root_topic` formats templates (code default `naeural`, override via `EE_ROOT_TOPIC`; docs mention `ratio1` so verify when editing); `SUBTOPIC` can be `address` or `alias`.
- Encryption/signing: `DefaultBlockEngine` is `BaseBCEllipticCurveEngine` (ECDSA secp256k1); payloads can be signed and AES-GCM encrypted; multi-recipient encryption is supported; encryption metadata uses `EE_IS_ENCRYPTED` and `EE_ENCRYPTED_DATA`.
- dAuth auto-configuration: `dauth_autocomplete` POSTs to dAuth URL (from `EE_DAUTH_URL` or EVM network defaults) with signed payload; may populate `EE_*` env keys and whitelist addresses; requests use explicit timeouts.
- Node discovery and permissions: heartbeats/netconfig update `_dct_can_send_to_node`; only whitelisted or un-secured nodes are allowed; net-config requests are sent to `admin_pipeline` + `NET_CONFIG_MONITOR` and throttled by `SDK_NETCONFIG_REQUEST_DELAY` (300s).
- Pipeline and instance config: configs are normalized to uppercase; pipeline config embeds `PLUGINS`; `attach_*` flows use heartbeat-provided config; command flows are via `COMMANDS.*` and notifications resolve `Transaction` responses.
- Webapp pipelines: `WebappPipeline` extracts `APP_URL` or `NGROK_URL` from payloads; supports tunnel engines `ngrok` and `cloudflare`.
- Deeploy (remote app deployment): `GenericSession` signs and sends Deeploy API requests for container apps, custom code, and Telegram bots; API base URLs come from EVM network config (`EE_DEEPLOY_API_URL`).
- IPFS/R1FS: `R1FSEngine` manages uploads/downloads via IPFS relay; key envs include `EE_IPFS_RELAY`, `EE_SWARM_KEY_CONTENT_BASE64`, `EE_IPFS_RELAY_API`, and cert/credentials; uses `_local_cache/_output` for transfers.
- CLI and config: `r1ctl` uses argparse and `CLI_COMMANDS`; user config stored in `~/.ratio1/config`; `reset_config` copies `.env` when present; alias default is `R1SDK` (`EE_SDK_ALIAS`).
- Payload helpers: `Payload` extends dict and can decode base64 images via `get_images_as_np` and `get_images_as_PIL`.
- Logger persistence (2026-02): `BaseLogger` uses asynchronous append-only persistence with a bounded writer queue/thread; producer path enqueues deltas via tracked indexes (`start_idx`/`end_idx`) instead of synchronous full-file rewrites; flush policy is configurable (`idle_seconds`, buffered line threshold, immediate error flush), optional repeat suppression exists, and telemetry is exposed via `get_log_writer_telemetry` (queue depth/high watermark, dropped lines, write latency p50/p95).
- Logger benchmarking: `xperimental/logger/logger_tester.py` runs deterministic threaded stress tests and emits timestamped stage reports/metrics; includes optional CI pass/fail mode via `--ci` and a deterministic post-run quality check that validates at least 50 threads x 200 lines (`THREAD-{idx}-LINE-{line}`) are fully persisted in log file(s).
- Logger durability/backpressure edge behavior (2026-02): `_enqueue_save_task` can call `_save_log` synchronously when `force=True` and the writer queue is full (critical-path durability fallback); non-forced queue overflow increments dropped-line telemetry and advances enqueue cursors (lines are counted as dropped, not retried).
- Logger flush trigger nuance (2026-02): idle flush policy is evaluated from `_logger(...)` calls; a burst that stops below buffer threshold relies on the next producer call (or shutdown flush) to trigger enqueue.

## Update Log (append-only)
- 2025-12-22: Added `request_timeout` to `dauth_autocomplete` to prevent hanging HTTP requests.
- 2025-12-22: Expanded AGENTS repo structure notes and flagged `nepctl`/`r1ctl` naming mismatch.
- 2026-02-06: Added living architecture memory with core flows, comms model, security, and deployment notes.
- 2026-02-06: Added logger throughput architecture updates (async append writer, flush policy, telemetry, CI benchmark mode).
- 2026-02-06: Added deterministic logger quality-check mode (50-thread/200-line minimum persistence verification).
- 2026-02-06: Documented logger queue-full fallback semantics and idle-trigger flush nuance in living architecture memory.
- (add new entries here)
