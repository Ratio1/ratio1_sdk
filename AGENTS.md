# AGENTS

## Objectives
- Provide a Python SDK for the Ratio1 network so clients can build and deploy low-code job/pipeline workloads to Ratio1 Edge Nodes.
- Offer tooling for node discovery, auth (dAuth), and cooperative execution across nodes.
- Ship a CLI for interacting with the network and node management workflows.

## Repository Structure
- `ratio1/`: main Python package
- `ratio1/base/`: core session/pipeline/instance abstractions and plugin templates
- `ratio1/bc/`: blockchain and dAuth/EVM-related logic
- `ratio1/default/`: default implementations (e.g., MQTT-based session)
- `ratio1/cli/`: CLI implementation (entrypoint for `r1ctl`)
- `ratio1/ipfs/`: IPFS/R1FS helpers and integrations
- `ratio1/logging/`: logging mixins and upload/download helpers
- `ratio1/const/`: constants and shared enums
- `ratio1/utils/`: utility helpers (env loading, tooling)
- `tutorials/`: runnable examples and usage patterns
- `README.md`: high-level overview and quick start
- `r1ctl.MD`: CLI manual (nepctl/r1ctl usage)
- `pyproject.toml`: packaging metadata and CLI script entrypoint

## Key Entry Points
- `ratio1/__init__.py`: exports `Session`, `Pipeline`, `Instance`, `CustomPluginTemplate`, presets, and helpers.
- CLI: `r1ctl` -> `ratio1.cli.cli:main` (see `r1ctl.MD` for commands).

## Development Notes
- dAuth is used for auto-configuration; network calls should set explicit timeouts.
- `template.env` and `.env` are used for local config and secrets.

## Update Log (append-only)
- 2025-12-22: Added `request_timeout` to `dauth_autocomplete` to prevent hanging HTTP requests.
- (add new entries here)
