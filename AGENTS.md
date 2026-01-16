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

## Update Log (append-only)
- 2025-12-22: Added `request_timeout` to `dauth_autocomplete` to prevent hanging HTTP requests.
- 2025-12-22: Expanded AGENTS repo structure notes and flagged `nepctl`/`r1ctl` naming mismatch.
- (add new entries here)
