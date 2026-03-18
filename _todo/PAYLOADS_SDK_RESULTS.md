# Ratio1 SDK Payload Capture Results

## Scope
- SDK repo revision: `7a97bd27deda689efc5b8ebbe8dac063a2bffb04`
- Tutorial/example path: `tutorials/ex27_payload_capture.py`
- Capture command: `python tutorials/ex27_payload_capture.py --seconds 600 --max-messages 30000`
- Analysis command: `python tutorials/ex27_payload_capture.py --analyze-only --capture-file <capture.jsonl>`
- Network: `mainnet`
- Capture window: `2026-03-18T18:18:30+00:00` to `2026-03-18T18:28:34+00:00` (604.0s)
- Message count: `14451`
- Any filters: `none`

## Environment and Limits
- SDK/session setup used: `Session(name='sdk-payload-capture', silent=True, auto_configuration=True, run_dauth=True, use_home_folder=False, local_cache_base_folder=<repo>)`
- Auth or public-access assumptions: `Used the SDK's normal dAuth-backed public listening path on mainnet. No pipelines, commands, or config mutations were issued by this tutorial.`
- Sample stop conditions: `600s wall clock or 30000 messages, whichever comes first`; actual stop reason=`time-window`
- Known blind spots: `Callback-level JSON view only; raw MQTT wire bytes and payload internals for messages encrypted to other recipients are not observable here.`

## Executive Summary
- heartbeat dominated the sample with 12447 messages and 166.5MB (58.4%) of observed bytes.
- The heaviest top-level field was `CURRENT_NETWORK` at 107.0MB across 196 messages.
- The single biggest payload driver was full NET_MON network-map state, not image or history payload content.
- The largest payload category was `heartbeat` with 12447 messages and 166.5MB.
- `ENCODED_DATA` alone contributed 50.3MB; in this SDK it should be treated as a callback-view expansion cost, not a confirmed raw-wire duplicate.
- Heartbeat-style diagnostic sections accounted for 80.1MB (28.1%) of measured bytes.
- `_C_*` and `_P_*` metadata together contributed 436.7KB (0.1%) of the sample.

## Answers To Required Questions
- 1. Message classes that dominated total bytes were: heartbeat (166.5MB, 58.4%), payload:NET_MON_01 (109.5MB, 38.4%), payload:NET_CONFIG_MONITOR (6.5MB, 2.3%), payload:CHAIN_STORE_BASE (1.6MB, 0.6%).
- 2. The largest payloads were dominated by network-map and diagnostic metadata, not by images or histories. The largest examples were payload:NET_MON_01 dominated by CURRENT_NETWORK, payload:NET_MON_01 dominated by CURRENT_NETWORK, payload:NET_MON_01 dominated by CURRENT_NETWORK; image fields contributed only 8.3KB overall.
- 3. The clearest low-hanging-fruit fields were `CURRENT_NETWORK` at 107.0MB, `ACTIVE_PLUGINS`, `ENCODED_DATA` at 50.3MB, `EE_WHITELIST`, `NET_CONFIG_DATA`, and `EE_ENCRYPTED_DATA`.
- 4. Empty/default-like fields accounted for 4.2MB (1.5%) in this SDK-visible sample.
- 5. `_C_*` and `_P_*` metadata accounted for 436.7KB (0.1%) combined.
- 6. Yes. Heartbeat-like diagnostic sections still exposed 80.1MB (28.1%) from the SDK side.
- 7. Direct mapping back to core `PAYLOADS.md` is blocked because that file is absent in this checkout on 2026-03-18, but the strongest likely overlap is heartbeat diagnostics, NET_MON full snapshots, repeated metadata, and encrypted envelopes.
- 8. SDK-side guidance from this run: separate callback-view byte counts from raw-wire claims, drop heartbeat `ENCODED_DATA` after decode when archiving locally, and analyze admin payloads separately from business payloads because NET_MON and heartbeat traffic dominate the sample.

## Protocol Bandwidth Evaluation
- Average observed callback-visible throughput: `483.6KB/s` (28.3MB/min)
- Average observed message rate: `23.93 msg/s` with `20698` bytes/message
- Heartbeat diagnostic field family alone sustained `135.7KB/s` (28.1% of observed bytes)
- `CURRENT_NETWORK` sustained `181.4KB/s` and remains the clearest snapshot-bandwidth driver
- `ENCODED_DATA` sustained `85.3KB/s` in the SDK callback view; treat it as analysis/logging overhead unless raw-wire evidence shows the same duplication on the broker side

| message class | avg bytes/s | avg msg/s | byte share |
| --- | --- | --- | --- |
| heartbeat | 282.2KB/s | 20.61 | 58.4% |
| payload:NET_MON_01 | 185.7KB/s | 0.32 | 38.4% |
| payload:NET_CONFIG_MONITOR | 10.9KB/s | 1.09 | 2.3% |
| payload:CHAIN_STORE_BASE | 2.8KB/s | 0.44 | 0.6% |
| notification:NORMAL | 1.8KB/s | 1.32 | 0.4% |
| payload:CONTAINER_APP_RUNNER | 127B/s | 0.06 | 0.0% |
| notification:ABNORMAL FUNCTIONING | 114B/s | 0.08 | 0.0% |
| payload:CUSTOM_EXEC_01 | 10B/s | 0.00 | 0.0% |
| payload:REST_CUSTOM_EXEC_01 | 8B/s | 0.00 | 0.0% |

## Byte Distribution
| message class | count | total bytes | avg bytes | p95 bytes | max bytes |
| --- | --- | --- | --- | --- | --- |
| heartbeat | 12447 | 166.5MB | 14023 | 17906 | 20326 |
| payload:NET_MON_01 | 196 | 109.5MB | 585864 | 600765 | 601154 |
| payload:NET_CONFIG_MONITOR | 658 | 6.5MB | 10291 | 16748 | 29887 |
| payload:CHAIN_STORE_BASE | 265 | 1.6MB | 6453 | 7439 | 7526 |
| notification:NORMAL | 796 | 1.0MB | 1376 | 1416 | 1416 |
| payload:CONTAINER_APP_RUNNER | 38 | 75.0KB | 2019 | 2047 | 2047 |
| notification:ABNORMAL FUNCTIONING | 46 | 67.4KB | 1500 | 1645 | 1645 |
| payload:CUSTOM_EXEC_01 | 3 | 6.1KB | 2091 | 2092 | 2092 |
| payload:REST_CUSTOM_EXEC_01 | 2 | 4.8KB | 2466 | 2467 | 2467 |

| sender | count | total bytes | avg bytes |
| --- | --- | --- | --- |
| r1s-ssj<0xai_A-r...Co_8Lj> | 75 | 8.4MB | 117312 |
| r1s-01<0xai_Aj1...QT74if> | 75 | 8.3MB | 116419 |
| r1s-ai01<0xai_A16...pv6WZZ> | 74 | 7.9MB | 112368 |
| r1s-bcps<0xai_AlK...clxVCj> | 74 | 7.8MB | 111232 |
| r1s-mene-01<0xai_AyN...AAj7A2> | 74 | 7.8MB | 109841 |
| r1s-archicava<0xai_A3r...On2ihk> | 74 | 7.7MB | 109793 |
| r1s-sbt<0xai_AkF...vn24LK> | 74 | 7.7MB | 109717 |
| r1s-04<0xai_AgN...m_piYJ> | 74 | 7.7MB | 109435 |
| r1s-03<0xai_Apk...I_I9z7> | 74 | 7.7MB | 109389 |
| r1s-db<0xai_A_b...WbiMiF> | 73 | 7.3MB | 105571 |

| stream / signature | count | total bytes | avg bytes |
| --- | --- | --- | --- |
| admin_pipeline / NET_MON_01 | 196 | 109.5MB | 585864 |
| admin_pipeline / NET_CONFIG_MONITOR | 658 | 6.5MB | 10291 |
| admin_pipeline / CHAIN_STORE_BASE | 265 | 1.6MB | 6453 |
| admin_pipeline / - | 796 | 1.0MB | 1376 |
| pg_service_b2_e00937a / CONTAINER_APP_RUNNER | 20 | 39.0KB | 1995 |
| keytrail-nati_5144838 / CONTAINER_APP_RUNNER | 18 | 36.0KB | 2046 |
| admin_pipeline / REST_CUSTOM_EXEC_01 | 2 | 4.8KB | 2466 |
| custom_code_remote / CUSTOM_EXEC_01 | 2 | 4.1KB | 2091 |
| custom_code_remote_1 / CUSTOM_EXEC_01 | 1 | 2.0KB | 2091 |

## Top Heavy Fields
| field | messages present | total estimated bytes | avg bytes when present | notes |
| --- | --- | --- | --- | --- |
| CURRENT_NETWORK | 196 | 107.0MB | 572437 | empty=0, default_like=0 |
| ACTIVE_PLUGINS | 12447 | 54.0MB | 4552 | empty=0, default_like=0 |
| ENCODED_DATA | 12447 | 50.3MB | 4239 | empty=0, default_like=0 |
| EE_WHITELIST | 12447 | 14.1MB | 1190 | empty=0, default_like=0 |
| COMM_STATS | 12447 | 8.2MB | 687 | empty=0, default_like=0 |
| GPU_INFO | 12447 | 4.3MB | 365 | empty=0, default_like=0 |
| TEMPERATURE_INFO | 12447 | 4.3MB | 358 | empty=0, default_like=0 |
| DCT_STATS | 12447 | 3.5MB | 293 | empty=0, default_like=0 |
| EE_ENCRYPTED_DATA | 569 | 3.5MB | 6413 | empty=0, default_like=0 |
| NET_CONFIG_DATA | 354 | 2.9MB | 8680 | empty=0, default_like=0 |
| EE_SIGN | 14451 | 1.5MB | 107 | empty=0, default_like=0 |
| LOOPS_TIMINGS | 12447 | 1.2MB | 101 | empty=0, default_like=0 |
| R1FS_RELAY | 12447 | 1.2MB | 99 | empty=0, default_like=0 |
| EE_HASH | 14451 | 1.0MB | 76 | empty=0, default_like=0 |
| CURRENT_RANKING | 196 | 1.0MB | 5441 | empty=0, default_like=0 |
| VERSION | 12447 | 961.9KB | 79 | empty=0, default_like=0 |
| DEVICE_LOG | 12447 | 948.1KB | 78 | empty=0, default_like=0 |
| ERROR_LOG | 12447 | 923.8KB | 76 | empty=0, default_like=0 |
| EE_SENDER | 14451 | 889.1KB | 63 | empty=0, default_like=0 |
| EE_ETH_SENDER | 14451 | 846.7KB | 60 | empty=0, default_like=0 |

## Field Families
### _C_* metadata
- messages present: 552
- total estimated bytes: 262.8KB (0.1%)
- leading fields: _C_cap_signature (25.3KB), _C_cap_time (22.6KB), _C_use_local_comms_only (16.7KB), _C_cap_elapsed_time (16.5KB), _C_current_interval (14.0KB)
### _P_* runtime/debug fields
- messages present: 593
- total estimated bytes: 173.9KB (0.1%)
- leading fields: _P_ALERT_HELPER (38.8KB), _P_PLUGIN_LOOP_RESOLUTION (20.7KB), _P_PLUGIN_REAL_RESOLUTION (18.3KB), _P_DATASET_BUILDER_USED (18.0KB), _P_DEBUG_SAVE_PAYLOAD (16.8KB)
### image fields
- messages present: 564
- total estimated bytes: 8.3KB (0.0%)
- leading fields: IMG_ORIG (8.3KB)
### heartbeat-style diagnostic sections
- messages present: 12447
- total estimated bytes: 80.1MB (28.1%)
- leading fields: ACTIVE_PLUGINS (54.0MB), EE_WHITELIST (14.1MB), COMM_STATS (8.2MB), DCT_STATS (3.5MB), CONFIG_STREAMS (231.0KB)
### history/result fields
- messages present: 0
- total estimated bytes: 0B (0.0%)
- leading fields: n/a
### empty/default fields
- messages present: 14451
- total estimated bytes: 4.2MB (1.5%)
- leading fields: SB_IMPLEMENTATION (338.7KB), MODIFIED_BY_ADDR (323.7KB), EE_IS_ENCRYPTED (303.9KB), INITIATOR_ADDR (295.5KB), MODIFIED_BY_ID (295.5KB)

## Largest Message Examples
- Example 1: `payload:NET_MON_01` from `r1s-bcps<0xai_AlK...clxVCj>` (587.1KB, stream=`admin_pipeline`, signature=`NET_MON_01`)
  large fields: CURRENT_NETWORK=559.7KB, CURRENT_ALERTED=11.7KB, CURRENT_RANKING=5.6KB, WHITELIST_MAP=3.0KB, MESSAGE=2.3KB
  preview: `{"CURRENT_ALERTED": "<dict 208 keys, 11965B>", "CURRENT_NETWORK": "<dict 209 keys, 573065B>", "CURRENT_RANKING": "<list 264 items, 5766B>", "EE_SIGN": "MEUCIHg65HzZamlGcVsd116OboEmM1DUc0RK6bO8kZ8i06C3AiEA1PKxWmUzsYo-SA90TouDtPica3hjAs_0vWKFSip87Ts=", "MESSAGE": "<string 2359B>", "STATUS": "<string 2359B>", "WHITELIST_MAP": "<dict 62 keys, 3091B>", "_P_ALERT_HELPER": "A=0, N=0, CT=NA, E=A[0, 1]=0.50 (in 49.7s) vs >=0.75 LstCh:1075.7s "}`
- Example 2: `payload:NET_MON_01` from `r1s-ai01<0xai_A16...pv6WZZ>` (587.0KB, stream=`admin_pipeline`, signature=`NET_MON_01`)
  large fields: CURRENT_NETWORK=559.7KB, CURRENT_ALERTED=11.7KB, CURRENT_RANKING=5.6KB, WHITELIST_MAP=3.0KB, MESSAGE=2.3KB
  preview: `{"CURRENT_ALERTED": "<dict 208 keys, 11965B>", "CURRENT_NETWORK": "<dict 209 keys, 573073B>", "CURRENT_RANKING": "<list 264 items, 5757B>", "EE_SIGN": "MEUCIQCDlUwyHol9f99fYVc3S2edESq9HU36Hi-CPHkdVs511wIgLNMju2LpRJc_6eVxKMXC4DEqb5f9k-4P0s4aITwa1Ag=", "MESSAGE": "<string 2359B>", "STATUS": "<string 2359B>", "WHITELIST_MAP": "<dict 62 keys, 3091B>", "_P_ALERT_HELPER": "A=0, N=0, CT=NA, E=A[0, 1]=0.50 (in 50.4s) vs >=0.75 LstCh:859.2s "}`
- Example 3: `payload:NET_MON_01` from `r1s-ai01<0xai_A16...pv6WZZ>` (587.0KB, stream=`admin_pipeline`, signature=`NET_MON_01`)
  large fields: CURRENT_NETWORK=559.6KB, CURRENT_ALERTED=11.7KB, CURRENT_RANKING=5.6KB, WHITELIST_MAP=3.0KB, MESSAGE=2.3KB
  preview: `{"CURRENT_ALERTED": "<dict 208 keys, 11965B>", "CURRENT_NETWORK": "<dict 209 keys, 573051B>", "CURRENT_RANKING": "<list 264 items, 5757B>", "EE_SIGN": "MEUCIQChr3IkmOM8HaLZkYyO1rLBfrgvF0cN-ThwjwpCv8GuSwIgJERqGUtRkMQZp9aH6xXlVh74a_dDyPQbN-E7Bylknx0=", "MESSAGE": "<string 2359B>", "STATUS": "<string 2359B>", "WHITELIST_MAP": "<dict 62 keys, 3091B>", "_P_ALERT_HELPER": "A=0, N=0, CT=NA, E=A[0, 1]=0.50 (in 42.7s) vs >=0.75 LstCh:1006.6s "}`
- Example 4: `payload:NET_MON_01` from `r1s-bcps<0xai_AlK...clxVCj>` (587.0KB, stream=`admin_pipeline`, signature=`NET_MON_01`)
  large fields: CURRENT_NETWORK=559.6KB, CURRENT_ALERTED=11.7KB, CURRENT_RANKING=5.6KB, WHITELIST_MAP=3.0KB, MESSAGE=2.3KB
  preview: `{"CURRENT_ALERTED": "<dict 208 keys, 11965B>", "CURRENT_NETWORK": "<dict 209 keys, 573053B>", "CURRENT_RANKING": "<list 264 items, 5755B>", "EE_SIGN": "MEYCIQDfx4md5PaVrm1TsUMJzCrW-tWnpqNha1tJn04CuCWnLAIhALu5h4PAHwLaUN89WNfXBKZKrWW61x2vnNNntk5Wx99v", "MESSAGE": "<string 2359B>", "STATUS": "<string 2359B>", "WHITELIST_MAP": "<dict 62 keys, 3091B>", "_P_ALERT_HELPER": "A=0, N=0, CT=NA, E=A[0, 1]=0.50 (in 50.1s) vs >=0.75 LstCh:503.6s "}`
- Example 5: `payload:NET_MON_01` from `r1s-sprt<0xai_A6r...N8DC8K>` (587.0KB, stream=`admin_pipeline`, signature=`NET_MON_01`)
  large fields: CURRENT_NETWORK=559.6KB, CURRENT_ALERTED=11.7KB, CURRENT_RANKING=5.6KB, WHITELIST_MAP=3.0KB, MESSAGE=2.3KB
  preview: `{"CURRENT_ALERTED": "<dict 208 keys, 11965B>", "CURRENT_NETWORK": "<dict 209 keys, 573042B>", "CURRENT_RANKING": "<list 264 items, 5764B>", "EE_SIGN": "MEMCH1zCzkPR4OQFLRGTTOT4RRUpXaWB5350WwJhOF1md24CIAbShYU7BTbTDJ1ZgIhTYY8dREJCTMT5dVN9nniawvU1", "MESSAGE": "<string 2359B>", "STATUS": "<string 2359B>", "WHITELIST_MAP": "<dict 62 keys, 3091B>", "_P_ALERT_HELPER": "A=0, N=0, CT=NA, E=A[0, 1]=0.50 (in 56.2s) vs >=0.75 LstCh:732.6s "}`

## Low-Hanging-Fruit Candidates
1. Shrink `CURRENT_NETWORK` snapshots in `NET_MON_01`, ideally with diffs, digests, or lower-cadence full snapshots.
   - evidence: `CURRENT_NETWORK` contributes 107.0MB (37.5%) across only 196 messages.
   - likely owner: core
   - expected impact: High because a small number of NET_MON payloads account for a large byte share.
   - compatibility risk: Medium if downstream consumers expect complete point-in-time snapshots every time.
2. Thin heartbeat-style diagnostic sections or send them less often.
   - evidence: Diagnostic fields account for 80.1MB (28.1%) with ACTIVE_PLUGINS, EE_WHITELIST, COMM_STATS leading the family.
   - likely owner: core
   - expected impact: High on heartbeat-heavy traffic because these sections recur across many messages.
   - compatibility risk: Medium if operators rely on full diagnostics every heartbeat; lower if moved to slower cadences or opt-in detail levels.
3. SDK-side logging and analysis should drop heartbeat `ENCODED_DATA` once the SDK has already expanded the decoded heartbeat fields.
   - evidence: `ENCODED_DATA` contributes 50.3MB (17.6%) in the callback view and is paired with decoded heartbeat fields in this SDK path.
   - likely owner: sdk
   - expected impact: High for local logging, archival, and analysis noise reduction.
   - compatibility risk: Low if tooling only removes it after successful decode and keeps raw access opt-in.
4. Stop emitting empty or default-like fields by default.
   - evidence: Default-like fields account for 4.2MB (1.5%); recurring fields include SB_IMPLEMENTATION, MODIFIED_BY_ADDR, EE_IS_ENCRYPTED, INITIATOR_ADDR.
   - likely owner: shared
   - expected impact: Medium and low-risk because these fields carried little observed information in this sample.
   - compatibility risk: Low if omitted fields are treated as absent-equivalent by consumers.
5. Investigate slimmer encrypted payload envelopes or compression before encryption for large opaque payloads.
   - evidence: `EE_ENCRYPTED_DATA` alone contributes 3.5MB (1.2%) in the SDK-visible envelope view.
   - likely owner: core
   - expected impact: Medium to high if payload ciphertext frequently dominates the visible envelope.
   - compatibility risk: Medium because cryptographic envelopes are compatibility-sensitive.

## Mapping Back To Core PAYLOADS.md
- `PAYLOADS.md` was referenced by the task file, but no `PAYLOADS.md` exists in this checkout as of 2026-03-18, so direct reference-by-reference mapping is blocked.
- The strongest likely core-side candidates from this SDK sample are NET_MON full snapshots, heartbeat diagnostics, repeated `_C_*`/`_P_*` metadata, and empty/default field emission.
- The encrypted-envelope share in the SDK-visible view suggests any core-side analysis should separate payload envelope costs from decrypted business payload body costs.

## Open Questions
- Raw MQTT wire bytes are not exposed in the public callback path, so all byte estimates here are from the SDK-visible decoded JSON view.
- Messages encrypted for other recipients remain opaque envelopes; their inner field makeup cannot be measured from this listener.
- Because `PAYLOADS.md` is absent in this repo snapshot, the core-mapping section is necessarily partial.
- Duplicate message-shape leaders in this run: 400c5b0c82 and cc24350f2d.

## Artifacts
- local JSONL path: `_local_cache/payload_capture/20260318T181829+0000_mainnet_14451msg.jsonl`
- local summary JSON path: `_local_cache/payload_capture/20260318T181829+0000_mainnet_14451msg_summary.json`
- top message shape leaders: `400c5b0c82, cc24350f2d, f5764b6d5b, 071cdbbb12, 2fa7332558`
