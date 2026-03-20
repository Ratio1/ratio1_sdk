# Ratio1 SDK Payload Capture and Bloat Analysis Task
This document is planning-only. It is intended to be copied into the `ratio1_sdk` repository and executed there by an agent. The goal is to produce an evidence-backed `_todo/PAYLOADS_SDK_RESULTS.md` from passive mainnet listening so the SDK-side view can be compared with core-side findings in this repo's `PAYLOADS.md`.

## Goal
Build a minimal SDK tutorial that listens to mainnet traffic in read-only mode, records bounded payload samples, analyzes wire-size and content composition, and writes a reusable `_todo/PAYLOADS_SDK_RESULTS.md` with concrete low-hanging-fruit optimization candidates.

## Why This Exists
`PAYLOADS.md` in the core repo is mostly code-path analysis. It needs a companion measurement pass from the SDK edge:
- what payloads actually look like on mainnet
- which message classes dominate bytes
- which fields dominate bytes inside each message class
- which repeated, empty, legacy, or diagnostic fields are cheap optimization wins
- which findings belong in core runtime changes versus SDK-side usage guidance

## Constraints
- Work inside the `ratio1_sdk` repository only.
- Prefer the repo's existing tutorial or examples structure. Do not invent a new layout if the repo already has one.
- Use passive, read-only listening only. Do not send payloads, commands, or configuration changes to mainnet.
- Do not require committing secrets, private keys, or raw sensitive data into the repo.
- Keep capture bounded by both time and message count.
- Do not commit raw payload dumps, images, or large binary blobs. Commit only sanitized summaries and small example excerpts.
- If mainnet access is blocked, auth-gated, or unsafe, stop cleanly and produce a blocked `_todo/PAYLOADS_SDK_RESULTS.md` with exact blocker details.

## Required Deliverables
1. A basic tutorial or example script in the SDK repo that:
   - connects to mainnet using the SDK's normal public-listening path
   - listens for payload traffic
   - records bounded per-message measurements needed for analysis
   - writes local capture artifacts ignored by git
2. A generated `_todo/PAYLOADS_SDK_RESULTS.md`.
3. Any tiny helper module needed for aggregation or sanitization.
4. A short run command in the tutorial doc or script header.

## Non-Goals
- No broker tuning.
- No protocol redesign.
- No large visualization stack.
- No long-running daemon or service.
- No production SDK API redesign in this task.

## Success Criteria
- A fresh SDK checkout can run one documented command and capture a bounded sample.
- The tutorial produces enough structured data to rank the heaviest payload classes and fields.
- `_todo/PAYLOADS_SDK_RESULTS.md` contains measured findings, not guesses.
- The results clearly separate:
  - observed mainnet facts
  - SDK-local parsing limitations
  - likely core-runtime bloat sources
  - immediate low-risk optimization candidates

## Recommended Task Contract
```yaml
task_id: SDK-PAYLOADS-20260318-001
attempt: 1
owner_role: docs-owner
goal: Measure real mainnet payload composition from the Ratio1 SDK side and generate _todo/PAYLOADS_SDK_RESULTS.md.
write_scope:
  - tutorial/example files in the SDK repo
  - helper analysis files in the SDK repo
  - _todo/PAYLOADS_SDK_RESULTS.md
constraints:
  - passive read-only mainnet listening only
  - bounded sample collection
  - no committed secrets
  - no committed raw payload archives
expected_artifacts:
  - runnable tutorial
  - local capture artifact path
  - _todo/PAYLOADS_SDK_RESULTS.md
success_criteria:
  - tutorial runs or reports a precise blocker
  - results doc contains measured size and field analysis
terminal_state: submitted|working|input-required|auth-required|completed|canceled|failed|rejected
```

## Implementation Plan
1. Inspect the SDK repo first.
   - Find the established examples or tutorials area.
   - Find the simplest public mainnet listener path already supported by the SDK.
   - Reuse existing session, listener, or callback primitives instead of building a custom client from scratch.
2. Add one minimal tutorial.
   - Name it according to SDK conventions.
   - Its purpose is measurement, not application behavior.
   - It should listen only long enough to gather a bounded sample.
3. Record a compact local artifact.
   - Use JSONL, CSV, or both under a local ignored path.
   - One row per observed message is preferred.
   - Do not store full raw message bodies by default.
4. Add an analysis pass.
   - It may run inline at the end of the tutorial or as a tiny follow-up script.
   - It must generate `_todo/PAYLOADS_SDK_RESULTS.md`.
5. Keep the result reproducible.
   - The results doc must state the exact command, sample window, message count, and any filters applied.

## What To Capture Per Message
At minimum, collect these fields when available:
- local receive timestamp
- SDK event class or callback type
- total serialized size in bytes
- uncompressed size if both compressed and decoded views are available
- sender node or address
- destination if present
- stream name
- plugin signature
- instance id
- message type or payload category
- whether the message looks like heartbeat, notification, command, or business payload
- top-level keys
- count of top-level keys
- list of large fields over a threshold such as `>1KB`
- size by top-level field
- count of `_C_*` fields
- count of `_P_*` fields
- presence of `IMG`, `IMG_ORIG`, `HISTORY`, `DCT_STATS`, `COMM_STATS`, `ACTIVE_PLUGINS`, `CONFIG_STREAMS`, `EE_WHITELIST`, `TAGS`, `ID_TAGS`
- whether fields are empty or default-like

If the SDK exposes the decoded message only, measure the decoded JSON representation consistently and say so in the results.

## Required Aggregations
The analysis must compute:
- total messages and total bytes
- bytes by message class
- bytes by sender
- bytes by stream and signature when available
- top 20 largest messages
- top 20 largest fields across all messages
- field presence frequency
- empty-field frequency
- `_C_*` and `_P_*` contribution estimates
- image-field contribution estimates
- repeated diagnostic-section contribution estimates
- duplicate or near-duplicate message-shape counts by key set

## Required Questions To Answer
`_todo/PAYLOADS_SDK_RESULTS.md` must answer these:
1. What message classes dominate total bytes on mainnet from the SDK listener perspective?
2. Are the largest payloads dominated by images, metadata, histories, heartbeat diagnostics, or something else?
3. Which top-level fields are the clearest low-hanging-fruit candidates for reduction?
4. How much apparent bloat comes from repeated empty/default fields?
5. How much apparent bloat comes from `_C_*` and `_P_*` metadata expansion?
6. Do heartbeat-like messages still expose heavy sections in practice from the SDK side?
7. Which findings clearly map back to core repo candidates already listed in `PAYLOADS.md`?
8. Which findings suggest new SDK-side guidance, helpers, or defaults?

## Suggested Low-Hanging-Fruit Heuristics
Mark a finding as low-hanging fruit when one or more of these are true:
- a field is large and present very often
- a field is often empty or default-like but still transmitted
- a field is duplicated under multiple names
- a field is diagnostic-only and changes slowly
- a field expands linearly with capture metadata or history length
- a field can be replaced by a count, hash, pointer, or digest with little compatibility risk

## Safety and Sanitization Rules
- Do not paste full payloads into the results doc.
- If you include examples, truncate strings and replace binary-heavy values with placeholders such as `<base64 184KB>`.
- Hash or redact sender-specific identifiers if policy or privacy requires it, but keep enough shape information to compare message families.
- Keep committed artifacts small.

## Required Output File
Generate `_todo/PAYLOADS_SDK_RESULTS.md` with this structure:

```md
# Ratio1 SDK Payload Capture Results

## Scope
- SDK repo revision:
- Tutorial/example path:
- Capture command:
- Analysis command:
- Network:
- Capture window:
- Message count:
- Any filters:

## Environment and Limits
- SDK/session setup used:
- Auth or public-access assumptions:
- Sample stop conditions:
- Known blind spots:

## Executive Summary
- 3 to 7 short findings with measured numbers

## Protocol Bandwidth Evaluation
- average observed bytes per second and bytes per minute across the whole capture window
- average messages per second and average bytes per message
- table: message class | avg bytes/s | avg msg/s | byte share
- notes separating SDK callback-view expansion costs from confirmed raw-wire costs

## Byte Distribution
- table: message class | count | total bytes | avg bytes | p95 bytes | max bytes
- table: top senders or sources by bytes
- table: top streams/signatures by bytes when available

## Top Heavy Fields
- table: field | messages present | total estimated bytes | avg bytes when present | notes

## Field Families
### `_C_*` metadata
### `_P_*` runtime/debug fields
### image fields
### heartbeat-style diagnostic sections
### history/result fields
### empty/default fields

## Largest Message Examples
- sanitized summaries only

## Low-Hanging-Fruit Candidates
1. candidate
   - evidence:
   - likely owner: core | sdk | shared
   - expected impact:
   - compatibility risk:
2. candidate

## Mapping Back To Core PAYLOADS.md
- core finding reference -> sdk evidence
- core finding reference -> contradicted / confirmed / needs refinement

## Open Questions
- blocked or ambiguous items

## Artifacts
- local JSONL/CSV path:
- any ignored raw scratch path:

## Verification
- command: ...
  result: pass|fail|blocked
  evidence: ...
```

## Verification Expectations
Minimum verification inside the SDK repo:
- manual diff review of the tutorial and results doc
- link/path sanity check
- one real run of the tutorial, or a precise blocked report

If the SDK repo has its own unit or lint commands and the touched files fit that scope, run them too.

## Handoff Back To This Core Repo
When the SDK-side task is complete, bring back:
- the final `_todo/PAYLOADS_SDK_RESULTS.md`
- the exact SDK commit or branch used
- the tutorial path and run command
- any blockers or auth assumptions
- the list of core `PAYLOADS.md` items that were confirmed, weakened, or contradicted

The desired end state is to use `_todo/PAYLOADS_SDK_RESULTS.md` together with this repo's `PAYLOADS.md`:
- `PAYLOADS.md` explains likely runtime causes
- `_todo/PAYLOADS_SDK_RESULTS.md` shows what actually dominates bytes on the wire from the SDK observer side
