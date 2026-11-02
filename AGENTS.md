# ratio1_sdk agent guide

This is the root contract for coding agents in `ratio1_sdk`. It holds only stable,
repository-specific rules. Read the linked references when your task touches their area:

- [Runtime notes](docs/runtime-notes.md): non-obvious behavior and contracts, by subsystem.
- [Agent workflows](docs/agent-workflows.md): ownership areas, the single-agent loop and
  actor-critic review.
- [`r1ctl.MD`](r1ctl.MD): the CLI manual.

## Core context

`ratio1_sdk` is the `ratio1` Python package: the client SDK for the Ratio1 network (sessions,
pipelines and plugin instances over MQTT, dAuth, EVM and signing, Deeploy, R1FS/IPFS) and the
`r1ctl` CLI (`ratio1.cli.cli:main`). `naeural_core` and `edge_node` also import it as their
blockchain engine, logger and MQTT wrapper, so changes here can change node behavior. Sibling
directories with those names are independent checkouts: commit there separately.

- Python 3.10 or newer; packaging uses `hatchling`.
- The SDK talks to real networks. MQTT, dAuth, EVM, Deeploy, oracle and R1FS calls can change
  operator state, so automated checks never exercise them against live services.
- Every network call needs an explicit timeout.

## Repository map

- `ratio1/base/`: `GenericSession`, pipelines, instances, payloads, transactions.
- `ratio1/comm/`: `MQTTWrapper`, heartbeat observation, bounded message buffers.
- `ratio1/bc/`: block engine, signing and verification, dAuth clients, EVM and oracle registry.
- `ratio1/default/`: the default MQTT session and plugin-instance helpers.
- `ratio1/cli/`: `r1ctl`; `ratio1/ipfs/`: R1FS engine and IPFS setup; `ratio1/logging/`: logger.
- `ratio1/const/`: constants, environment keys, payload keys and network defaults.
- `tests/`: offline unit tests. `tutorials/`: runnable examples. `_todo/`: plans and generated
  result markdowns (never the repo root). `xperimental/`: harnesses and experiments.

## Verification

```bash
python -m compileall ratio1
python -m unittest discover -s tests -p 'test_*.py'
python -m unittest discover -s tests -p 'test_mqtt_broker_failover.py'
```

- Run the suite with `-s tests`: test modules import each other by bare name.
- `test_mqtt_channel_qos.py` imports `tomllib`, so the full suite needs Python 3.11 or newer.
- Live MQTT tests skip unless `EE_TEST_MQTT_HOST` (and optionally `EE_TEST_MQTT_PORT`) point to an
  isolated broker. Never point them at a production broker.
- CLI parser changes: build the parser with `ratio1.cli.cli.build_parser()`. Do not run `main()` or
  `python -m ratio1.cli.cli -h` in checks: `main()` creates config and cache under `HOME`.
- Logger flush or throughput changes: `python xperimental/logger/logger_tester.py --ci`.
- Changes to real network behavior (session, comms, dAuth, Deeploy, R1FS) also need a written
  manual validation plan, since no safe automated substitute exists.
- Report each check as pass, fail or blocked, with one line of evidence. Never weaken a test or
  production behavior to get a pass.

## Releases

Every push to `main` runs `.github/workflows/python-publish.yml`, which syncs `pyproject.toml`
from `ratio1/_ver.py` and publishes that version to PyPI.

- Bump `__VER__` in `ratio1/_ver.py` in each change that should ship, then run
  `python ratio1/_ver.py` to sync `pyproject.toml`. `ratio1.__version__` comes from `_ver.py`.
- A push that keeps the published version makes the publish run fail; that is expected for
  docs-only pushes.
- Deploy SDK changes that `naeural_core` depends on before the matching Core change.

## Conventions

- Two-space indentation; NumPy-style docstrings on new or modified functions and classes; comment
  network-safety branches, state transitions and serialization.
- Constants and environment keys come from `ratio1/const/`, not string literals.
- Public CLI commands, environment variables, payload keys, topics and exported symbols are API:
  renaming one means updating docs, tutorials and dependents in the same change.
- `README.md`, `r1ctl.MD`, `pyproject.toml` and `ratio1/cli/` must agree on CLI names. The README
  still documents the legacy `nepctl` name and links a missing `nepctl.md`.
- Conventional Commit subjects (`feat:`, `fix:`, `docs:`, `chore:`) under 72 characters.

## Safety boundaries

- Never print, log or commit secrets: `.env`, PEM files, swarm keys, tokens, API keys, dAuth secret
  bundles, or client config under `~/.ratio1`.
- Operator commands are manual only: `restart`, `shutdown`, `oracle-rollout`, Deeploy launch and
  close, and mutating R1FS/IPFS operations.
- Changes to message routing, signing or encryption metadata, whitelist rules, Deeploy request
  shapes or R1FS bootstrap need actor-critic review before handoff.

## Git

- Branch from an up-to-date `main` and open a PR unless the user asks for a direct push.
- Stage exact paths; never commit `_local_cache/`, generated reports or unrelated changes.
- Do not force-push shared branches or rewrite pushed history without approval.

## Keeping this guidance useful

This file and the references are loaded into agents' context, so every line has a cost.

- Add a fact only when it is durable, not obvious from the code, and likely to prevent a mistake.
- Put it in the matching section of [runtime notes](docs/runtime-notes.md), not here. Edit or
  delete the entry it replaces; do not append corrections or dated logs.
- Keep task progress, measurements and investigations in the PR, `_todo/` or the issue tracker.
- Update this file when commands, boundaries, the release flow or the layout change.
