# Shared Contracts

This package is the language-neutral contract boundary between the Go control
plane, the Pi writer runtime, and the Web replay client. JSON Schema is the
authoritative representation; `src/index.js` only exposes the stable names for
runtime consumers.

Covered boundaries:

- `writer-workflow-input`: Go `TemporalWriterStarter` to Pi
  `PiWriterRunWorkflow`.
- `writer-tool-request`: Pi orchestrator to a tenant/project-scoped read or
  runtime-owned draft tool.
- `writer-runtime-event`: Pi activity to the shared `workflow_events` ledger.
- `writer-public-event`: Go replay reader to the Web writer workbench.

Run `npm test` from this directory. The test suite validates fixtures emitted
by Go, Python, and Node, rejects invalid payloads, and checks the current Go,
Pi, and Web consumers for contract drift.

The schemas intentionally do not contain provider credentials or prompt/body
fields. Those remain private trace data and are not part of the public replay
contract.
