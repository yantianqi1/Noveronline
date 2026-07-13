# Component specifications

## Contents

1. Application shell
2. Writing components
3. Agent components
4. Shared state requirements

## Application shell

### `ProjectNavigator`

Show volumes, chapters, scenes, story bible, research, and run history. Support keyboard navigation, active location, reorder where authorized, unsaved/conflict badges, and loading/empty/error states. Virtualize large trees.

### `ManuscriptCanvas`

Own the primary editor or reader. Preserve selection during streaming events, expose word count and save state, support comments/suggestions, and separate canonical text from provisional agent output. Never couple cursor state to the run timeline renderer.

### `AgentRail`

Show selected run, compact activity, approvals, outputs, and context. It must be collapsible/resizable on desktop and a drawer/tab on smaller widths. Keep cancel/retry/approve actions stable.

### `AgentComposer`

Support multiline input, context chips, attachments, scope/mode, send, stop, and draft persistence. Disable only with a visible reason. `Enter`/`Shift+Enter` behavior must be documented and accessible.

## Writing components

### `ContextChip`

Represent selected chapter range, character, world entry, style guide, source, or file. Include type, readable label, remove action, and optional stale/conflict warning. Do not expose internal database IDs.

### `OutlineBoard`

Represent acts, chapters, scenes, and beats with hierarchy rather than a flat kanban by default. Support keyboard reorder and show generation/revision status without turning the board into analytics.

### `StoryEntityPanel`

Render canonical facts, aliases, relationships, arc notes, and references back to manuscript locations. Agent suggestions must be visually distinct until accepted.

### `RevisionDiff`

Show base and proposed versions, changed scope, agent summary, per-hunk accept/reject, keyboard operation, and conflict handling. Provide unified view for prose and split view where width allows. Never use color alone.

### `VersionHistory`

Show immutable versions with author (`user`, `agent`, `import`), timestamp, summary, and restore/compare actions. Restoring should create a new version rather than erase history.

### `ContinuityIssueList`

Group issues by severity and entity; link to exact prose; allow ignore, resolve, and create-revision actions. Include evidence and distinguish verified fact from model inference.

## Agent components

### `RunHeader`

Show task title, current state, elapsed time, affected scope, and primary recovery action. Avoid fake percentage unless the backend provides meaningful bounded progress.

### `ActivityTimeline`

Use one row per meaningful action, not per token. Rows need status icon, concise summary, time, and optional details. Collapse successful routine tools; keep warnings, failures, approvals, and artifact changes prominent.

### `ToolCallCard`

Show safe scope/arguments, progress, result summary, error, and retry/inspect when applicable. Secrets and raw large payloads must never render by default.

### `ApprovalCard`

State exactly what will happen, affected artifacts/external systems, reversibility, and alternatives. Actions need clear verbs such as “Replace 3 selected scenes” rather than “Continue.” Remain persistent until resolved.

### `ArtifactOutput`

Represent draft, outline, report, image, export, or patch with preview, status, provenance, and open/review action. Partially streamed artifacts must be labeled incomplete.

### `ConnectionBanner`

Distinguish offline, reconnecting, stream interrupted, authentication expired, and server unavailable. Include persistent recovery actions and never rely only on a transient toast.

## Shared state requirements

Every asynchronous component must deliberately implement:

- idle or empty;
- initial loading;
- live streaming/progress;
- waiting for user;
- partial/interrupted;
- success;
- recoverable error;
- terminal error;
- canceled;
- unauthorized/forbidden where relevant.

For each state, define label, icon, available actions, persistence behavior, and screen-reader announcement. If a component cannot explain its behavior in these states, its contract is incomplete.
