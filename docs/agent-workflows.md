# Agent workflows and ownership

Detailed execution guidance for coding agents in `ratio1_sdk`. The root
[`AGENTS.md`](../AGENTS.md) stays the concise contract. Areas are logical domains, not people:
name one primary area per task and widen scope deliberately.

## Ownership areas

| Area | Owns | Extra care |
| --- | --- | --- |
| Session and comms | `ratio1/base/generic_session.py`, `pipeline.py`, `instance.py`, `transaction.py`, `ratio1/default/session/`, `ratio1/comm/` | message semantics, callback order, payload paths, peering checks, network side effects |
| Blockchain and auth | `ratio1/bc/`, `ratio1/const/evm_net.py`, `ratio1/const/environment.py` | timeouts, signature compatibility across versions, address handling, network defaults |
| CLI | `ratio1/cli/`, `r1ctl.MD`, CLI parts of `README.md`, the `pyproject.toml` entrypoint | no operator side effects in tests; names and docs in sync |
| R1FS/IPFS | `ratio1/ipfs/`, R1FS tutorials | bootstrap and address filters, daemon restarts, proof of block transfer |
| Deploy and webapps | Deeploy helpers in `generic_session.py`, `webapp_pipeline.py`, `ratio1/default/instance/`, `ratio1/const/plugins/` | tokens, API payload compatibility, tunnels, manual validation |
| Logging | `ratio1/logging/`, `xperimental/logger/` | backpressure, flush timing, overflow, benchmark evidence |
| Payload formats | `ratio1/io_formatter/`, `ratio1/base/payload/` | formatter names and payload field compatibility |
| Docs and release | `README.md`, `r1ctl.MD`, `tutorials/`, `AGENTS.md`, `docs/`, `pyproject.toml`, `ratio1/_ver.py` | version sync, commands that really exist, no unsafe defaults in examples |

## Single-agent loop

Use this by default, one concern per loop.

1. **Plan:** outcome, write scope, assumptions and the narrowest useful check.
2. **Implement:** the smallest coherent change.
3. **Test:** the narrow check first, then broaden with the regression risk.
4. **Critique:** environment feedback first (failures, parser output, logs), then behavior,
   security, operator noise, rollback and maintainability.
5. **Revise:** only what evidence or a concrete risk justifies.
6. **Verify:** an independent check, not a re-read of the patch; hand off results and open risks.

Escalate after two loops on the same concern without new evidence, when scope must grow, when
proof needs live credentials or node changes, or when sources disagree in a way that changes
behavior.

## Actor-critic review

Use it for routing, signing, encryption, whitelist, Deeploy, R1FS bootstrap and other changes
likely to regress silently.

1. The actor states scope, invariants, rollback and planned checks, then implements and tests.
2. The critic reviews independently and backs each finding with a failing command, a spec mismatch
   or a concrete scenario. Style preferences do not block.
3. The integrator settles disagreements by running the evidence; without safe evidence, escalate.
4. The actor fixes supported findings only and reruns the affected checks.

## Handoffs

A handoff names the goal, the current status (working, blocked, completed or failed), changed
files, each check as pass, fail or blocked with evidence, what needs manual validation, rollback
notes, open risks and the next recommended action.
