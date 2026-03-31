# AGENTS

## Scope and Authority
- This file is the authoritative repo-local source for repository purpose and runtime constraints, logical module and file ownership, safe-edit boundaries, required verification commands, and handoff and escalation rules.
- Review this file whenever module boundaries change, verification commands change, new incident semantics are introduced, or new operator commands or deployment paths are added.
- When code, docs, packaging metadata, and this file disagree, treat the mismatch as work to resolve or hand off explicitly. Do not silently pick one source and move on.
- Delegated work must use a structured task payload and a structured handoff envelope. Free-form prose alone is not sufficient for durable handoff.

## External Guidance Basis (2026-03 Review)
- A2A / Agent2Agent protocol guidance informed the task contract, agent-card shape, task states, artifact-oriented handoffs, explicit cancellation, and progress update rules.
- Anthropic guidance on effective agents and tool-writing informed the single-agent loop, evaluator-optimizer pattern, and the rule to keep loops simple and scoped to one concern at a time.
- OpenAI guidance on handoffs and repository-local instructions informed the structured handoff envelope and the requirement that repo instructions encode verification and context.
- Critique-and-revise literature and OpenAI CriticGPT informed the actor-critic workflow: implementation and critique are separate responsibilities, and disagreements are resolved with executable evidence.
- Primary references used for this 2026-03 update:
  - `https://a2a-protocol.org/latest/specification/`
  - `https://a2a-protocol.org/latest/topics/life-of-a-task/`
  - `https://a2a-protocol.org/latest/topics/streaming-and-async/`
  - `https://www.anthropic.com/engineering/building-effective-agents`
  - `https://www.anthropic.com/engineering/writing-tools-for-agents`
  - `https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents`
  - `https://openai.github.io/openai-agents-python/handoffs/`
  - `https://openai.com/business/guides-and-resources/how-openai-uses-codex/`
  - `https://openai.com/index/finding-gpt4s-mistakes-with-gpt-4/`
  - `https://arxiv.org/abs/2303.17651`
  - `https://arxiv.org/abs/2303.11366`

## Objectives
- Provide a Python SDK for the Ratio1 network so clients can build and deploy low-code job and pipeline workloads to Ratio1 Edge Nodes.
- Offer tooling for node discovery, auth (`dAuth`), and cooperative execution across nodes.
- Ship a CLI for interacting with the network and node-management workflows.

## Runtime Constraints
- Python runtime target is `>=3.10`; packaging uses `hatchling`.
- The SDK is networked by design. MQTT, dAuth, EVM, Deeploy, oracle, and IPFS/R1FS flows can touch real operator state and must not be exercised casually in automated verification.
- Network calls must use explicit timeouts. This is a repository rule, not an optional convention.
- Never commit or print secrets from `.env`, `template.env`, PEM files, swarm keys, Telegram tokens, API keys, or generated client config under `~/.ratio1`.
- CLI entrypoint invocations can initialize config under `HOME` and create cache directories. Smoke tests must avoid mutating operator state.
- Commands with operator impact are manual-only unless the task explicitly asks for them and the target environment is known safe: `restart`, `shutdown`, `oracle-rollout`, Deeploy launch and close flows, and mutating R1FS/IPFS operations.
- The R1FS same-host relay workaround remains opt-in. Do not flip its default behavior without transfer-path evidence, not just control-plane reachability.
- Release changes must keep runtime version metadata aligned across `ratio1/_ver.py`, `ratio1/__init__.py`, and `pyproject.toml`.

## Repository Structure
- `ratio1/`: main Python package
- `ratio1/base/`: core session, pipeline, instance, payload, and plugin abstractions
- `ratio1/bc/`: blockchain, dAuth, EVM, and signing logic
- `ratio1/cli/`: CLI implementation for `r1ctl`
- `ratio1/comm/`: transport wrappers and communicator abstractions
- `ratio1/const/`: constants, environment keys, payload keys, and network defaults
- `ratio1/default/`: default session and plugin-instance implementations
- `ratio1/io_formatter/`: payload formatter discovery and implementations
- `ratio1/ipfs/`: IPFS and R1FS helpers plus setup scripts
- `ratio1/logging/`: logger core, mixins, upload, and download helpers
- `ratio1/utils/`: config, dotenv, comm, and oracle helpers
- `tutorials/`: runnable examples and deployment patterns
- `_todo/`: planning markdowns, generated result markdowns, and other durable task artifacts that should not live at the repo root
- `xperimental/logger/`: logger stress and CI benchmark harness
- `README.md`: high-level overview and quick start
- `r1ctl.MD`: CLI manual
- `pyproject.toml`: packaging metadata and CLI script entrypoint

## Logical Ownership and Write Scope
- Ownership labels here are logical domains, not human owners. A task should name one primary domain owner and should avoid widening write scope without updating the task contract.

| Logical owner | Owned files / write scope | Responsibility | Extra care required |
| --- | --- | --- | --- |
| `core-session` | `ratio1/base/generic_session.py`, `ratio1/base/pipeline.py`, `ratio1/base/instance.py`, `ratio1/base/plugin_template.py`, `ratio1/base/responses.py`, `ratio1/base/transaction.py`, `ratio1/default/session/`, `ratio1/comm/` | Session lifecycle, message routing, callbacks, transactions, transport integration | Message semantics, callback ordering, payload-path contracts, peering checks, and any network side effects |
| `blockchain-auth` | `ratio1/bc/`, `ratio1/const/evm_net.py`, `ratio1/const/environment.py` | Signing, verification, dAuth, network metadata, EVM interaction | Explicit timeouts, signature compatibility, address handling, network defaults |
| `cli-operator` | `ratio1/cli/`, `r1ctl.MD`, CLI sections in `README.md`, `pyproject.toml` script entrypoint | Operator-facing command surface and CLI documentation | Avoid destructive operator actions in tests; keep command names, help, and docs synchronized |
| `ipfs-r1fs` | `ratio1/ipfs/`, `ratio1/ipfs/ipfs_setup/`, R1FS tutorials | IPFS startup, relay behavior, transfer lifecycle, cache layout | Bootstrap and addr-filter changes, daemon restarts, same-host workaround semantics, transfer proof vs false positives |
| `plugins-deploy` | Deeploy and webapp helpers in `ratio1/base/generic_session.py`, `ratio1/base/webapp_pipeline.py`, `ratio1/default/instance/`, `ratio1/const/plugins/`, deployment tutorials | Webapp, HTTP, Telegram, custom code, and container deployment flows | Token handling, API payload compatibility, tunnel semantics, manual operator validation |
| `logging-telemetry` | `ratio1/logging/`, `xperimental/logger/` | Logger durability, buffering, throughput, telemetry, upload and download helpers | Backpressure behavior, flush timing, queue overflow semantics, benchmark evidence |
| `formatting-payloads` | `ratio1/io_formatter/`, `ratio1/base/payload/`, payload-format constants | Formatter lookup and payload decoding | Backward compatibility for formatter names and payload field handling |
| `docs-examples` | `README.md`, `r1ctl.MD`, `tutorials/`, `AGENTS.md` | User guidance, examples, and operator documentation | Example commands must not imply unsafe defaults; docs must track real command names and runtime constraints |
| `release-packaging` | `pyproject.toml`, `ratio1/_ver.py`, `ratio1/__init__.py` | Package metadata, exported version, CLI registration | Version drift, release naming, public entrypoint stability |

## Safe-Edit Boundaries
- Keep changes inside the declared write scope. If a fix requires crossing into another logical owner, update the task contract and request critic or integrator review.
- Do not rename or repurpose public CLI commands, environment variables, payload keys, topic names, or exported SDK symbols without updating docs, tutorials, and this file in the same change.
- Do not run destructive node-management commands or live deployment flows as part of routine verification.
- Preserve operator safety. Smoke tests must prefer parser construction, imports, static verification, and dry-run style checks over live-network commands.
- Keep planning-only markdowns and generated result markdowns under `_todo/`. Do not add new root-level task or results markdowns unless the task explicitly requires an exception.
- Treat `README.md`, `r1ctl.MD`, `pyproject.toml`, and `ratio1/cli/` as a sync set for CLI naming and entrypoint changes.
- Treat `ratio1/_ver.py`, `ratio1/__init__.py`, and `pyproject.toml` as a sync set for version changes.
- Changes to message routing, encryption metadata, whitelist semantics, Deeploy request shapes, R1FS/IPFS bootstrap logic, or incident semantics require critic review before handoff.
- If a task uncovers an architecture or safety fact that future agents need, update `Living Architecture Memory` or `Lessons Learned` in the same change.

## Required Verification Commands
- There is no comprehensive repo-wide unit test suite today. Agents must run the smallest non-destructive executable checks that fit the touched area, and must explicitly call out remaining gaps.
- Minimum checks by change area:

| Change area | Required commands | Notes |
| --- | --- | --- |
| Any Python code under `ratio1/` | `python -m compileall ratio1` | Required baseline syntax and import-level smoke check |
| CLI parser or command-shape changes | `python - <<'PY'\nfrom ratio1.cli.cli import build_parser\nparser = build_parser()\nhelp_text = parser.format_help()\nassert 'get' in help_text\nassert 'config' in help_text\nassert 'restart' in help_text\nassert 'shutdown' in help_text\nprint('cli-parser-ok')\nPY` | Use `build_parser()`. Do not call `ratio1.cli.cli:main` for smoke tests because `main()` initializes config under `HOME` |
| CLI naming or CLI docs changes | `rg -n "\\br1ctl\\b|\\bnepctl\\b" README.md r1ctl.MD pyproject.toml ratio1/cli -S` | Confirm whether dual naming is intentional or drift |
| Logger core or flush-path changes | `python xperimental/logger/logger_tester.py --help` | Baseline harness sanity check |
| Logger durability or throughput changes | `python xperimental/logger/logger_tester.py --ci` | If this cannot be run in the current environment, handoff must state why |
| Release or packaging changes | `python - <<'PY'\nimport tomllib\nimport ratio1\nwith open('pyproject.toml', 'rb') as fh:\n    data = tomllib.load(fh)\nassert data['project']['version'] == ratio1.version, (data['project']['version'], ratio1.version)\nprint('version-sync-ok')\nPY` | Required before release handoff |
| Docs or tutorials for operator commands or deployment paths | `python -m compileall ratio1` and relevant grep or parser checks above | There is no safe fully-automated substitute for live deployment validation |

- Manual validation plan is required, but not automatically runnable, for changes in `core-session`, `blockchain-auth`, `ipfs-r1fs`, or `plugins-deploy` that alter real network behavior.
- A valid handoff must state which commands were run, what evidence was reviewed, and what could not be verified safely.

## Python Coding Contract
- Match the repository's 2-space indentation for Python code and keep implementations production-grade rather than prototype-grade.
- Any modified, created, or refactored Python code must include clear, extended NumPy-style docstrings on touched classes, functions, and methods.
- Add descriptive inline comments for non-trivial control flow, state transitions, network-safety branches, serialization logic, and other contract-sensitive code paths.
- Prefer explicit helper names and branch structure over terse cleverness when network behavior, auth state, or payload compatibility is involved.

## Single-Agent Loop
- Required loop for bounded solo work: `plan -> implement -> test -> critique -> revise -> verify`.
- Rules for the loop:
  - One concern per loop. Split unrelated fixes into separate loops or separate tasks.
  - Environment feedback comes before stylistic feedback. Check runtime behavior, parser behavior, logs, or executable evidence before discussing naming or formatting polish.
  - Critique must prioritize correctness, safety, rollback risk, alert-noise risk, and missing tests before style.
  - `verify` must use an independent check whenever possible, not just re-reading the patch.
- Stop and escalate when any of the following occurs:
  - two failed loops on the same concern without new evidence
  - write scope must expand beyond the task contract
  - verification requires live credentials, live node mutation, or unsafe deployment
  - repo sources disagree in a way that changes behavior and the correct source is unclear
  - rollback risk is high and cannot be reduced with a bounded change

## Actor-Critic Workflow
- Use actor-critic when the change touches behavior that is safety-sensitive, operator-facing, or likely to regress silently.
- Actor responsibilities:
  - implement the change inside a bounded write scope
  - run the required verification commands for that scope
  - produce changed files, evidence, and a structured handoff envelope
- Critic responsibilities:
  - focus on correctness, safety, alert-noise risk, rollback strategy, and missing or weak tests
  - challenge unsupported assumptions and false-positive evidence
  - avoid rewriting the entire patch unless explicitly assigned implementation scope
- Integrator or test-executor responsibilities:
  - resolve disagreements using executable evidence, not preference
  - rerun targeted verification or add the smallest necessary reproducer
  - decide whether the task is `completed`, `failed`, `canceled`, or needs escalation
- If actor and critic disagree and no executable evidence can be produced safely, escalate rather than arguing from intuition.

## A2A-Style Task Contract
- Every delegated task must carry a structured payload. YAML or JSON is preferred.
- Minimum required fields:
  - `task_id`: stable identifier used across retries and handoffs
  - `goal`: what is being changed or verified
  - `owner`: logical owner or assigned role
  - `write_scope`: allowed files or directories
  - `constraints`: safety, runtime, or scope constraints
  - `required_inputs`: issue statement, relevant files, prior evidence, and dependency context
  - `expected_artifacts`: patch, review notes, logs, docs update, or manual-validation plan
  - `status`: `submitted`, `working`, `input-required`, `completed`, `failed`, or `canceled`
  - `terminal_state`: target end state for the task
- Long-running tasks must emit checkpoints at each meaningful state transition and at least every 30 minutes if still active.
- Retries should be idempotent where possible:
  - reuse the same `task_id`
  - state what can be safely rerun
  - avoid duplicate side effects on remote nodes or deployment systems
- Cancellations must be explicit and safe:
  - set `status: canceled`
  - state whether partial edits exist
  - state whether cleanup was performed or intentionally deferred

### Task Contract Template
```yaml
task_id: R1-AREA-0001
goal: >
  One-sentence description of the bounded change or investigation.
owner: actor
write_scope:
  - ratio1/cli/
constraints:
  - No live node mutations
  - Keep CLI docs synchronized
required_inputs:
  - issue summary
  - relevant files
  - prior failures or logs
expected_artifacts:
  - patch
  - verification notes
  - handoff envelope
status: submitted
terminal_state: completed
```

## Required Handoff Envelope
- Every handoff and every terminal state update must use this envelope. Use YAML or JSON.
- Minimum required fields:
  - `task_id`
  - `current_status`
  - `changed_files`
  - `tests_run`
  - `evidence_reviewed`
  - `open_risks`
  - `next_recommended_action`
- Strongly recommended additional fields:
  - `owner`
  - `write_scope`
  - `manual_validation_needed`
  - `rollback_notes`

### Handoff Envelope Template
```yaml
task_id: R1-AREA-0001
current_status: completed
owner: actor
write_scope:
  - ratio1/cli/
changed_files:
  - ratio1/cli/cli_commands.py
  - r1ctl.MD
tests_run:
  - python -m compileall ratio1
  - python - <<'PY'
    from ratio1.cli.cli import build_parser
    parser = build_parser()
    assert 'restart' in parser.format_help()
    print('cli-parser-ok')
    PY
evidence_reviewed:
  - CLI parser help text
  - diff for command docs and entrypoint text
open_risks:
  - README still uses legacy naming in untouched sections
next_recommended_action: >
  Align remaining README references to the chosen CLI name and rerun the naming grep.
manual_validation_needed: none
rollback_notes: revert doc and parser changes together
```

## Agent Cards

### Agent Card: `single-agent-implementer`
- Role name: `single-agent-implementer`
- Objective: execute one bounded concern end-to-end using the required solo loop
- Owned files / write scope: task-declared bounded scope; should stay within one logical owner whenever possible
- Required inputs and context: issue statement, touched files, prior failures, verification requirements, relevant entries from `Living Architecture Memory` and `Lessons Learned`
- Expected outputs / artifacts: patch, verification evidence, handoff envelope, AGENTS update if new reusable knowledge is discovered
- Allowed tools: repo search, file reads, bounded code edits, non-destructive local commands, targeted primary-source web review when external behavior is unstable
- Escalation triggers: repeated failed loops, scope expansion, unsafe validation requirement, contradictory evidence

### Agent Card: `actor`
- Role name: `actor`
- Objective: implement the requested change and run the required checks inside a bounded write scope
- Owned files / write scope: files explicitly assigned in the task contract
- Required inputs and context: task contract, current repo state, required verification commands, prior related handoffs
- Expected outputs / artifacts: patch, verification logs, changed-file list, risks, rollback notes
- Allowed tools: repo search, file reads, code edits in owned scope, non-destructive local verification commands, targeted external docs review when requested
- Escalation triggers: need to edit outside owned scope, tests require unsafe live operations, blocked by conflicting repo contracts

### Agent Card: `critic`
- Role name: `critic`
- Objective: evaluate actor output for correctness, safety, alert-noise risk, rollback hazards, and missing tests
- Owned files / write scope: no default write scope; may suggest fixes or take a narrowly-assigned follow-up patch if explicitly delegated
- Required inputs and context: task contract, actor patch, verification evidence, relevant architecture-memory entries
- Expected outputs / artifacts: prioritized findings, missing-evidence list, approval or escalation recommendation
- Allowed tools: repo search, file reads, diff review, non-destructive verification commands, targeted reproducer commands
- Escalation triggers: evidence does not support the claimed behavior, rollback risk is unclear, or safe verification is impossible

### Agent Card: `integrator-test-executor`
- Role name: `integrator-test-executor`
- Objective: resolve actor-critic disagreements and close the task using executable evidence
- Owned files / write scope: only the union of already-touched files unless a wider scope is explicitly approved
- Required inputs and context: actor handoff envelope, critic findings, verification requirements, current diff
- Expected outputs / artifacts: final decision, targeted fix if needed, final verification result, terminal handoff envelope
- Allowed tools: repo search, file reads, bounded code edits, verification commands, diff inspection
- Escalation triggers: disagreement cannot be resolved with safe evidence, required validation is external or destructive, change needs wider redesign

### Agent Card: `docs-release-steward`
- Role name: `docs-release-steward`
- Objective: keep docs, examples, entrypoints, and version metadata aligned with behavior
- Owned files / write scope: `README.md`, `r1ctl.MD`, `AGENTS.md`, tutorials, `pyproject.toml`, `ratio1/_ver.py`, `ratio1/__init__.py`
- Required inputs and context: behavior change summary, affected commands or APIs, naming decisions, release version intent
- Expected outputs / artifacts: synchronized docs or metadata patch, grep or version-sync evidence, open-risk note for unresolved drift
- Allowed tools: repo search, file reads, bounded docs or metadata edits, parser smoke checks, version-alignment checks
- Escalation triggers: command naming is ambiguous, runtime and packaging disagree, docs would require claiming unverified behavior

## Worked Examples

### Example: Single-Agent Task
```yaml
task_contract:
  task_id: R1-DOCS-0001
  goal: Align CLI documentation with the selected public command name.
  owner: single-agent-implementer
  write_scope:
    - README.md
    - r1ctl.MD
    - AGENTS.md
  constraints:
    - No live CLI execution through main()
  required_inputs:
    - grep output for r1ctl vs nepctl
  expected_artifacts:
    - docs patch
    - grep evidence
  status: working
  terminal_state: completed
loop:
  - plan: isolate naming drift
  - implement: update docs in bounded scope
  - test: rerun naming grep
  - critique: check for stale examples and entrypoint mismatch
  - revise: fix remaining stale references
  - verify: confirm grep output matches intended naming policy
```

### Example: Actor-Critic Task
```yaml
task_contract:
  task_id: R1-LOG-0007
  goal: Adjust logger flush behavior without regressing durability.
  owner: actor
  write_scope:
    - ratio1/logging/base_logger.py
    - xperimental/logger/logger_tester.py
  constraints:
    - Preserve queue-full durability fallback semantics
    - Keep deterministic quality check intact
  expected_artifacts:
    - patch
    - logger benchmark evidence
    - critic review
actor_handoff:
  current_status: completed
  changed_files:
    - ratio1/logging/base_logger.py
  tests_run:
    - python -m compileall ratio1
    - python xperimental/logger/logger_tester.py --ci
critic_focus:
  - correctness of enqueue and flush thresholds
  - false-positive pass conditions in benchmark output
  - rollback risk if queue pressure increases
integrator_rule:
  - if actor and critic disagree, rerun logger benchmark or add a smaller reproducer and decide from evidence
```

### Example: A2A Cross-Agent Handoff
```yaml
task_contract:
  task_id: R1-CLI-0012
  goal: Add a new read-only CLI subcommand and document it.
  owner: actor
  write_scope:
    - ratio1/cli/
  constraints:
    - No operator side effects
    - Docs update is required before completion
  expected_artifacts:
    - parser patch
    - docs handoff to docs-release-steward
actor_to_docs_handoff:
  task_id: R1-CLI-0012
  current_status: completed
  changed_files:
    - ratio1/cli/cli_commands.py
    - ratio1/cli/cli.py
  tests_run:
    - python -m compileall ratio1
    - python - <<'PY'
      from ratio1.cli.cli import build_parser
      parser = build_parser()
      assert 'inspect' in parser.format_help()
      print('cli-parser-ok')
      PY
  evidence_reviewed:
    - parser help text
  open_risks:
    - r1ctl.MD does not yet mention the new subcommand
  next_recommended_action: Update README and r1ctl.MD, then rerun the naming grep.
```

## Lessons Learned
- Use this section for durable, reusable failures and validated fixes so future agents do not repeat them.

### Template
- Date:
- Area:
- Failure or false-positive pattern:
- Rollback hazard:
- Validated fix or guardrail:
- Evidence:
- Follow-up:

### Current Lessons
- 2026-03-13
  - Area: `ratio1/ipfs/r1fs.py`
  - Failure or false-positive pattern: local same-host relay control-plane connectivity was not sufficient evidence for successful block transfer
  - Rollback hazard: enabling the workaround by default can make transfers look healthy while data movement still fails
  - Validated fix or guardrail: keep the workaround opt-in and require exact-local-multiaddr proof before applying filters
  - Evidence: same-host relay investigations captured in `Living Architecture Memory`
  - Follow-up: only revisit default behavior with transfer-path proof
- 2026-03-17
  - Area: CLI smoke testing
  - Failure or false-positive pattern: invoking `python -m ratio1.cli.cli -h` runs `maybe_init_config()` and mutates `HOME`
  - Rollback hazard: automated checks can overwrite or create operator config unexpectedly
  - Validated fix or guardrail: use `build_parser()` for parser smoke tests; if main-entry testing is unavoidable, isolate `HOME`
  - Evidence: local verification during this AGENTS update
  - Follow-up: keep CLI smoke-test instructions side-effect aware
- 2026-03-17
  - Area: release metadata
  - Failure or false-positive pattern: runtime version and packaging version can drift because `ratio1/_ver.py` is not automatically kept in sync with `pyproject.toml`
  - Rollback hazard: release artifacts and reported package version diverge
  - Validated fix or guardrail: require an explicit version-sync verification before release handoff
  - Evidence: local check showed `pyproject.toml=3.2.25` while `ratio1.version=3.5.15`
  - Follow-up: align the files in the next release-focused change
- 2026-03-17
  - Area: CLI naming
  - Failure or false-positive pattern: docs and examples can keep legacy `nepctl` references while packaging registers `r1ctl`
  - Rollback hazard: operators follow docs that do not match the installed entrypoint
  - Validated fix or guardrail: treat `README.md`, `r1ctl.MD`, `pyproject.toml`, and `ratio1/cli/` as a sync set and rerun the naming grep on every CLI-doc change
  - Evidence: repo grep during this AGENTS update
  - Follow-up: decide whether the repo supports dual naming intentionally or should fully converge on `r1ctl`
- 2026-03-18
  - Area: task and result markdown placement
  - Failure or false-positive pattern: planning docs and generated result markdowns can drift into the repo root, leaving `_todo/` incomplete and making task artifacts harder to find
  - Rollback hazard: future agents rerun or update the wrong markdown path and silently recreate root-level files the repo is trying to retire
  - Validated fix or guardrail: keep planning-only markdowns and generated result markdowns under `_todo/`, and point tutorial defaults there when they emit durable markdown artifacts
  - Evidence: local repo state showed `_todo/PAYLOADS_SDK.md` and `_todo/TODOs.md` while the payload capture tutorial still defaulted to `PAYLOADS_SDK_RESULTS.md` at the repo root
  - Follow-up: align any remaining durable result markdown generators with the `_todo/` convention when they are touched

## Key Entry Points
- `ratio1/__init__.py`: exports `Session`, `Pipeline`, `Instance`, `CustomPluginTemplate`, presets, version, and helpers
- CLI: `r1ctl -> ratio1.cli.cli:main`

## Living Architecture Memory (Update This Section)
- This section is shared, durable memory. Update it whenever you discover critical behavior, contracts, or architecture details.
- Core objects: `Session` manages comms and callbacks; `Pipeline` (aka Stream) groups plugin instances; `Instance` represents a plugin instance; `CustomPluginTemplate` mirrors on-edge plugin APIs for remote execution.
- Addressing and IDs: node address prefix is `0xai_`; session `name` becomes `INITIATOR_ID` and `SESSION_ID`; `EE_PAYLOAD_PATH` is `[node_id, pipeline_name, signature, instance_id]` and currently uses node alias rather than address (see TODO in `ratio1/base/generic_session.py`).
- Message flow: default MQTT uses three communicators (payloads, heartbeats and ctrl, notifications) with separate threads and queues; message handling is JSON -> optional decrypt -> formatter decode -> dispatch to session, pipeline, and instance callbacks plus transaction and response handlers.
- Formatting: payloads can specify `EE_FORMATTER`; decoding is via `IOFormatterWrapper` with plugin locations (default `plugins.io_formatters`).
- Comms channels: topics are defined by `CONFIG_CHANNEL`, `CTRL_CHANNEL`, `NOTIF_CHANNEL`, `PAYLOADS_CHANNEL`; `root_topic` formats templates (code default `naeural`, override via `EE_ROOT_TOPIC`; docs mention `ratio1` so verify when editing); `SUBTOPIC` can be `address` or `alias`.
- Encryption and signing: `DefaultBlockEngine` is `BaseBCEllipticCurveEngine` (ECDSA secp256k1); payloads can be signed and AES-GCM encrypted; multi-recipient encryption is supported; encryption metadata uses `EE_IS_ENCRYPTED` and `EE_ENCRYPTED_DATA`.
- dAuth auto-configuration: `dauth_autocomplete` POSTs to dAuth URL (from `EE_DAUTH_URL` or EVM network defaults) with signed payload; may populate `EE_*` env keys and whitelist addresses; requests use explicit timeouts.
- Node discovery and permissions: heartbeats and netconfig update `_dct_can_send_to_node`; only whitelisted or unsecured nodes are allowed; net-config requests are sent to `admin_pipeline` plus `NET_CONFIG_MONITOR` and throttled by `SDK_NETCONFIG_REQUEST_DELAY` (`300s`).
- Pipeline and instance config: configs are normalized to uppercase; pipeline config embeds `PLUGINS`; `attach_*` flows use heartbeat-provided config; command flows are via `COMMANDS.*` and notifications resolve `Transaction` responses.
- Webapp pipelines: `WebappPipeline` extracts `APP_URL` or `NGROK_URL` from payloads; supports tunnel engines `ngrok` and `cloudflare`.
- Deeploy (remote app deployment): `GenericSession` signs and sends Deeploy API requests for container apps, custom code, and Telegram bots; API base URLs come from EVM network config (`EE_DEEPLOY_API_URL`).
- IPFS and R1FS: `R1FSEngine` manages uploads and downloads via IPFS relay; key envs include `EE_IPFS_RELAY`, `EE_SWARM_KEY_CONTENT_BASE64`, `EE_IPFS_RELAY_API`, and cert or credentials; uses `_local_cache/_output` for transfers.
- R1FS startup workaround (2026-03): `R1FSEngine.maybe_start_ipfs()` includes an opt-in same-host relay workaround gated by `EE_R1FS_SAMEHOST_RELAY_FIX`; it proves same-host reachability by disconnecting any existing relay session, dialing the container-gateway relay multiaddr, and requiring `ipfs swarm peers` to show the relay on that exact local multiaddr before applying filters or bootstrap changes. It persists a marker in `${IPFS_PATH}/.r1fs_samehost_relay_fix.json`, merges `Swarm.AddrFilters`, re-adds a local bootstrap entry, and performs a controlled daemon restart only when config changes require it. The same marker file also caches recent negative proof results for the same relay and gateway tuple so off-host containers can skip repeated proof attempts for a bounded TTL. The workaround is disabled by default because local-path control-plane success did not reliably imply successful block transfer.
- CLI and config: `r1ctl` uses argparse and `CLI_COMMANDS`; user config is stored in `~/.ratio1/config`; `reset_config` copies `.env` when present; alias default is `R1SDK` (`EE_SDK_ALIAS`).
- CLI smoke-test side effect (2026-03): `ratio1.cli.cli:main()` calls `maybe_init_config()` before parsing commands, so even `-h` can create config and cache directories under `HOME`; parser smoke tests should import `build_parser()` instead of executing `main()`.
- Payload helpers: `Payload` extends `dict` and can decode base64 images via `get_images_as_np` and `get_images_as_PIL`.
- Heartbeat callback expansion (2026-03): heartbeat v2 messages keep `ENCODED_DATA` and also merge the decompressed heartbeat body into the same callback dict in `GenericSession.__on_heartbeat()`, so callback-level size measurements double-count that section relative to raw wire unless `ENCODED_DATA` is excluded explicitly.
- Durable task artifacts (2026-03): planning-only markdowns and generated result markdowns belong under `_todo/`; capture tutorials or analysis scripts that emit durable markdown reports should default there instead of the repo root.
- Logger persistence (2026-02): `BaseLogger` uses asynchronous append-only persistence with a bounded writer queue and thread; producer path enqueues deltas via tracked indexes (`start_idx` and `end_idx`) instead of synchronous full-file rewrites; flush policy is configurable (`idle_seconds`, buffered line threshold, immediate error flush), optional repeat suppression exists, and telemetry is exposed via `get_log_writer_telemetry` (queue depth or high watermark, dropped lines, write latency p50 and p95).
- Logger benchmarking: `xperimental/logger/logger_tester.py` runs deterministic threaded stress tests and emits timestamped stage reports and metrics; includes optional CI pass or fail mode via `--ci` and a deterministic post-run quality check that validates at least `50` threads x `200` lines (`THREAD-{idx}-LINE-{line}`) are fully persisted in log file(s).
- Logger durability and backpressure edge behavior (2026-02): `_enqueue_save_task` can call `_save_log` synchronously when `force=True` and the writer queue is full (critical-path durability fallback); non-forced queue overflow increments dropped-line telemetry and advances enqueue cursors (lines are counted as dropped, not retried).
- Logger flush trigger nuance (2026-02): idle flush policy is evaluated from `_logger(...)` calls; a burst that stops below buffer threshold relies on the next producer call or shutdown flush to trigger enqueue.
- Release metadata drift (2026-03): runtime version comes from `ratio1/_ver.py` and may diverge from `pyproject.toml` unless the sync script is run; release changes must verify both.

## Update Log (Append-Only)
- 2025-12-22: Added `request_timeout` to `dauth_autocomplete` to prevent hanging HTTP requests.
- 2025-12-22: Expanded AGENTS repo structure notes and flagged `nepctl` and `r1ctl` naming mismatch.
- 2026-02-06: Added living architecture memory with core flows, comms model, security, and deployment notes.
- 2026-02-06: Added logger throughput architecture updates (async append writer, flush policy, telemetry, CI benchmark mode).
- 2026-02-06: Added deterministic logger quality-check mode (`50`-thread and `200`-line minimum persistence verification).
- 2026-02-06: Documented logger queue-full fallback semantics and idle-trigger flush nuance in living architecture memory.
- 2026-03-11: Documented the feature-gated R1FS same-host relay workaround, marker file, bootstrap and filter merge behavior, and controlled daemon restart path.
- 2026-03-11: Updated the R1FS same-host relay workaround contract to assume container runtime and default to enabled unless explicitly disabled.
- 2026-03-12: Added bounded negative caching for failed same-host relay proofs to avoid repeated startup delays on off-host containers.
- 2026-03-12: Tightened same-host relay proof semantics to require disconnect plus reconnect on the exact local multiaddr before filters are applied.
- 2026-03-13: Reverted the R1FS same-host relay workaround to opt-in by default after testing showed local-path peer connectivity could still fail block transfer.
- 2026-03-17: Rewrote AGENTS.md as the authoritative repo policy for runtime constraints, logical ownership, safe-edit boundaries, verification commands, structured handoffs, and escalation.
- 2026-03-17: Added A2A-style task contracts, required handoff envelopes, single-agent loop rules, actor-critic workflow, agent cards, worked examples, and lessons-learned templates.
- 2026-03-17: Recorded CLI smoke-test side effects, release-version drift checks, and the current `nepctl` vs `r1ctl` documentation risk.
- 2026-03-18: Documented the heartbeat v2 callback expansion behavior so SDK-side payload-size analyses do not treat retained `ENCODED_DATA` as pure wire cost.
- 2026-03-18: Recorded the `_todo/` convention for planning and result markdowns and aligned the SDK payload capture tutorial to emit its result markdown there by default.
