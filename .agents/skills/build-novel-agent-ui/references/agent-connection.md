# Agent connection and event protocol

## Contents

1. Recommended topology
2. Run state machine
3. Event model
4. Reliability rules
5. Artifact concurrency
6. Security and privacy

## Recommended topology

For a web client, prefer:

- REST/RPC commands for creating, canceling, approving, and retrying runs;
- SSE for ordered server-to-client run events when the client rarely sends mid-stream data;
- WebSocket only when frequent bidirectional control, collaborative presence, or live voice requires it;
- normal persistence endpoints for projects, chapters, entities, and versions.

Keep a single normalized client adapter even if transports differ. Components must consume domain events and selectors, not raw SSE/WebSocket messages.

## Run state machine

Use explicit terminal and non-terminal states:

```text
queued -> planning -> running -> waiting_user -> running -> completed
                         |             |          |
                         +-> paused ---+          +-> failed
                         +------------------------> canceled
```

- `queued`: accepted but not started.
- `planning`: determining bounded work; do not expose raw private reasoning.
- `running`: producing activity, tool results, or artifact patches.
- `waiting_user`: approval or missing information blocks progress.
- `paused`: execution intentionally suspended and resumable.
- `completed`, `failed`, `canceled`: terminal states.

Never infer terminal success merely because a stream closed.

## Event model

Every event needs `eventId`, `runId`, `sequence`, `type`, `createdAt`, and typed `payload`. Useful event families:

- `run.created`, `run.status`, `run.heartbeat`, `run.completed`, `run.failed`;
- `message.delta`, `message.completed`;
- `activity.started`, `activity.updated`, `activity.completed`;
- `tool.started`, `tool.progress`, `tool.completed`, `tool.failed`;
- `artifact.snapshot`, `artifact.patch`, `artifact.completed`;
- `approval.requested`, `approval.resolved`;
- `usage.updated`, `warning.raised`.

Use [../assets/agent-events.ts](../assets/agent-events.ts) as a starting contract when no equivalent exists.

### Activity display

Show user-legible summaries such as “Checking character timeline” or “Preparing a revision patch.” Allow technical tool details in a collapsible inspector. Do not expose raw chain-of-thought or label it “thinking.”

### Tool calls

For each tool call, show:

- human-readable name and status;
- safe arguments or scope, with secrets removed;
- elapsed time for slow calls;
- concise result summary;
- retry or inspect action when useful.

## Reliability rules

- Generate an idempotency key before `createRun`; reuse it after ambiguous network failure.
- Persist the latest processed event cursor. Reconnect with `Last-Event-ID` or equivalent.
- Deduplicate by `eventId`; order by `sequence`; tolerate delayed events.
- Fetch an authoritative run snapshot after reconnect, tab wake, or sequence gap.
- Distinguish `offline`, `reconnecting`, `stream_interrupted`, and `run_failed` in copy and actions.
- Abort client fetches on unmount without canceling server work unless the user explicitly cancels.
- Send cancellation to the server and wait for authoritative acknowledgment.
- Keep partial output marked as incomplete after interruption.
- Use bounded exponential backoff with jitter; stop retrying terminal or authorization errors.
- Do not let a stale stream update a newly selected run.

## Artifact concurrency

Every patch should carry:

- `artifactId`;
- `baseVersion`;
- operation or diff payload;
- new provisional version or checksum;
- originating `runId`.

If `baseVersion` differs from the user’s current version, stop automatic application. Offer compare/merge, apply to a copy, or rerun against current text. Preserve user selections and unsaved edits.

Use snapshots to recover, patches for efficient streaming, and immutable version records for history. Coalesce high-frequency patches before rendering to avoid cursor movement and layout thrash.

## Security and privacy

- Never send an entire manuscript when the selected scope is sufficient.
- Show the active context set and allow users to remove items before a run.
- Redact tokens, provider keys, private headers, and sensitive tool arguments from events and logs.
- Require server authorization for every project, run, artifact, and event stream; a guessed ID must not grant access.
- Sanitize rendered Markdown/HTML and isolate generated interactive content.
- Treat model-generated URLs, citations, and tool outputs as untrusted data.
