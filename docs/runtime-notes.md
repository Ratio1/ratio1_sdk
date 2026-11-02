# Runtime notes

Non-obvious behavior and contracts that are easy to break, grouped by subsystem. Read the section
for the area you change. Keep each entry current: edit or delete it when the code changes.

## Sessions and addressing

- `Session` owns comms and callbacks, `Pipeline` groups plugin instances, `Instance` is one plugin
  instance, and `CustomPluginTemplate` mirrors the on-node plugin API for remote code.
- Node addresses use the `0xai_` prefix. The session `name` becomes `INITIATOR_ID` and
  `SESSION_ID`. `EE_PAYLOAD_PATH` is `[node, pipeline, signature, instance]` and still carries the
  node alias, not the address (TODO in `ratio1/base/generic_session.py`).
- Pipeline and instance configs are normalized to uppercase; pipeline config embeds `PLUGINS`.
  `attach_*` flows use the config reported in heartbeats; notifications resolve `Transaction`s.
- Heartbeats and net-config update `_dct_can_send_to_node`: only whitelisted or unsecured nodes are
  sendable. Net-config requests go to `admin_pipeline`/`NET_CONFIG_MONITOR`, at most every
  `SDK_NETCONFIG_REQUEST_DELAY` (300 s) per node.

## MQTT and comms

- The default session has three communicators (payloads, heartbeats plus control, notifications),
  each with its own thread and queue. Inbound handling is JSON, optional decrypt, formatter decode
  (`EE_FORMATTER` through `IOFormatterWrapper`), then session, pipeline, instance and transaction
  callbacks.
- Topics come from `CONFIG_CHANNEL`, `CTRL_CHANNEL`, `NOTIF_CHANNEL` and `PAYLOADS_CHANNEL`. The code
  default root topic is `naeural` (override with `EE_ROOT_TOPIC`); `SUBTOPIC` is `address` or
  `alias`.
- Receive callbacks admit into a bounded FIFO that rejects the newest message without blocking
  Paho; saturation and post-close rejections are counted separately. It is process-local, not
  durable.
- Readiness, SUBACK waiters and publish accounting belong to one client generation. Take the client
  lock before subscription/lifecycle locks and keep Paho calls and waits outside them. A handoff
  that returns after its generation retired is abandoned, not pending. Publish states (local
  rejection, Paho handoff, QoS completion, abandoned) never prove the node executed anything.
- Initial subscriptions run before the session main-loop thread starts, so cancellation reads a
  sticky shutdown request, not the running flag. Test the first constructor connection explicitly:
  later reconnects can hide missing startup subscriptions (`tests/test_mqtt_session_startup_live.py`).
- Broker failover: dAuth's `EE_MQTT_HOSTS` (JSON array) becomes `HOSTS` only when the primary equals
  `EE_MQTT_HOST`; an explicit `HOSTS`, including `[]`, wins. `MQTTWrapper` picks candidates per
  communicator without changing shared config, tries all before reporting a failed burst, and
  retries the last good endpoint first. Candidates must share port, auth, TLS and network. Test with
  `tests/test_mqtt_broker_failover.py` plus the lifecycle and startup tests.
- QoS config keeps the historical `int(value)` conversion, then checks `[0, 1, 2]`: bools, numeric
  floats (truncated) and integer strings like `01`, `+1`, `0_1` pass; `"true"`, `"1.0"` and
  out-of-range values fail. Do not reuse this leniency for TLS or new settings
  (`tests/test_mqtt_channel_qos.py`).
- Addressed payloads (`EE_DESTINATION`) fan out only when the payload channel has an addressed topic
  template such as `TARGETED_TOPIC`; otherwise the SDK sends one broadcast.
  `EE_DISABLE_ADDRESSED_PAYLOAD_SUBS` is the receive-side rollout flag.

## Heartbeats and observation modes

- `Session` defaults to `full_network` (global CTRL subscription). `selected_nodes` subscribes to
  exact addressed CTRL topics and checks signed raw heartbeat identity and freshness before
  formatter decoding. `summary_discovery` has no CTRL subscription and learns nodes only from fresh
  signed `NET_MON_01` payloads by configured trusted addresses. Modes are fixed for a session's
  lifetime, never fall back to global CTRL, and report status through
  `get_heartbeat_observation_status()`.
- Formatter decoding can overwrite routing fields. In `summary_discovery`, reject decoded NetMon
  messages without raw-envelope authorization before discovery or callbacks; tests must leave the
  worker filter unset so it cannot hide a missing guard.
- Heartbeat v2 callbacks keep `ENCODED_DATA` and also merge the decompressed body into the same
  dict, so callback-level sizes double-count that section compared with the wire.

## Signing, encryption and dAuth

- `DefaultBlockEngine` is ECDSA secp256k1; payloads can be signed and AES-GCM encrypted, also to
  several recipients (`EE_IS_ENCRYPTED`, `EE_ENCRYPTED_DATA`).
- Signing canon `v2` includes `SIGN_CANON_V` in the signed hash, so older SDKs that hash unknown
  fields still verify it; `v1` stays supported. Without `SIGN_CANON_V`, verification tries the
  current encoder without that field, then `v1`. Stats buckets are `v1`, `v2` and `unversioned`
  (a verification path, not a wire version). Cross-version checks: `xperimental/sign/test_sign2.py`.
- Canon verification stats use one coalescing background writer. Hot-path callers can pass
  `persist_canon_stats=False` and flush after their worker drains.
- `dauth_autocomplete` posts a signed request to `EE_DAUTH_URL` (or the network default) with a
  timeout; it may fill `EE_*` environment keys and whitelist addresses.
- `get_dauth_job_secret_bundle(job_id, revision=None)` signs the immutable
  `DEEPLOY_SPECS.secret_revision` and validates the response and decrypted bundle against it.
  Omitting the revision is allowed only for existing unversioned pipelines; explicit revisions
  never fall back. Rejections carry `retryable`: authorization, revocation and malformed responses
  raise `ValueError`; transport, unavailable replicas and registry RPC failures raise
  `RuntimeError`. The placeholder is `DAUTH_SECRET_PLACEHOLDER` (`__R1_DAUTH_SECRET__`).
- `reconcile_dauth_job_secrets()` sends signed lifecycle prepare/status/commit/revoke/delete and
  reconcile requests, binds replies to the operation, plan and action, and returns redacted configs
  and their CID, never bundles. It never retries: a timeout can follow a successful write, and
  Core's coordinator journal owns recovery.
- dAuth clients never log request bodies, response bodies or secret values.
- Oracle registry reads in `ratio1/bc/evm.py` share a 600-second process-wide cache per network,
  RPC endpoint, contract and method, also used by `web3_is_dauth_oracle`. Refreshes serialize per
  entry, an expired snapshot never authorizes after a failed refresh, and registry changes can take
  ten minutes to appear (`tests/test_evm_oracle_registry_cache.py`).

## Deeploy and webapps

- Deeploy HTTP helpers need a caller-persisted `request_id` and a paid `job_id`. A timeout means
  acceptance is unknown: retry the same intent and ID or check `deeploy_get_deployment_status`.
  HTTP 202 means durably accepted, not ready. `deeploy_close` needs `expected_revision` and deletes
  the whole job. `deeploy_get_read_auth` signs only a nonce; the server authorizes each poll result.
- API base URLs come from the EVM network config (`EE_DEEPLOY_API_URL`).
- `WebappPipeline` reads `APP_URL` or `NGROK_URL` from payloads; tunnel engines are `ngrok` and
  `cloudflare`.

## R1FS and IPFS

- `R1FSEngine` transfers through an IPFS relay configured by `EE_IPFS_RELAY`,
  `EE_SWARM_KEY_CONTENT_BASE64` and `EE_IPFS_RELAY_API`; downloads land under `_local_cache/_output`.
- The same-host relay workaround is opt-in (`EE_R1FS_SAMEHOST_RELAY_FIX`), because local
  control-plane reachability did not prove block transfer. It requires the relay to appear on the
  exact local multiaddr before changing filters or bootstrap, records state in
  `${IPFS_PATH}/.r1fs_samehost_relay_fix.json` (including cached negative proofs) and restarts the
  daemon only when config changed. Enable it by default only with transfer-path evidence.

## CLI and logging

- `r1ctl` stores user config in `~/.ratio1/config`; `reset_config` copies `.env` when present; the
  default alias is `R1SDK` (`EE_SDK_ALIAS`).
- On Windows, `os.execv` splits a multi-word `python -c` payload, so `r1ctl update` passes a
  whitespace-free base64 launcher (`ratio1/cli/package_update.py`). Keep a Windows process
  replacement check whenever the updater changes.
- `BaseLogger` persists asynchronously through a bounded writer queue, enqueuing deltas by index.
  Flushes trigger on idle time, buffered lines or errors; idle flush is evaluated on the next log
  call, so a quiet burst waits for the next call or shutdown. A forced save with a full queue saves
  synchronously; a non-forced overflow counts the lines as dropped. Telemetry:
  `get_log_writer_telemetry`.
- `xperimental/logger/logger_tester.py --ci` stress-tests the logger and checks that at least 50
  threads × 200 lines are fully persisted.
