# Quality gates

Do not call a frontend complete until the applicable gates pass.

## Functional integration

- A real command reaches the intended backend handler.
- Run identifiers and event cursors survive navigation and reconnect.
- Ordered streaming, duplicate events, missing events, and stream closure are handled.
- Cancel, retry/resume, approval, and rejection reach authoritative server state.
- Partial output is labeled and retained safely after interruption.
- Artifact patches use base versions and surface conflicts.
- User edits are never silently overwritten by agent output.
- Authentication expiry and forbidden resources have recoverable UI.

## Writing workflow

- Chapter/scene navigation preserves unsaved work and selection where possible.
- Selected context is visible before submission.
- Agent proposals are distinguishable from canonical manuscript text.
- Accept/reject works at the promised granularity.
- Version history identifies user and agent changes.
- Continuity results link to precise manuscript locations.
- Export/publish actions are explicit and confirmed when destructive or external.

## Visual quality

- The Agent thread is the dominant task surface and the manuscript remains a stable sibling artifact.
- No horizontal overflow at supported breakpoints.
- Long titles, Chinese/English mixed text, empty data, and large lists remain usable.
- Loading geometry does not cause major layout shift.
- Interactive states include hover, focus, active, disabled, loading, and error.
- Light/dark themes, if offered, have independently checked contrast.
- Icons come from one coherent family and have accessible names.
- No dead controls, fake progress, placeholder menus, or decorative dashboard clutter remain.

## Accessibility

- Primary journey is keyboard-completable.
- Focus remains visible and moves intentionally after dialogs, sheets, and approvals.
- Landmarks, headings, labels, and dialog names are meaningful.
- Status changes use restrained live-region announcements.
- Color is not the only indicator for run state or diff semantics.
- Reduced motion is respected.
- Target sizes and text contrast meet the product’s accessibility baseline.

## Performance and resilience

- Streaming does not rerender the full editor or move its cursor.
- Long timelines and project trees remain responsive.
- Heavy editor/diff modules are not in the initial route unless required.
- Offline/reconnecting/interrupted states are distinguishable.
- Reloading during a run restores authoritative state.
- Generated Markdown/HTML is sanitized and isolated where needed.

## Verification matrix

At minimum, test:

| Journey | Desktop | Narrow/mobile | Keyboard | Failure/reconnect |
|---|---:|---:|---:|---:|
| Open and edit chapter | ✓ | ✓ | ✓ | n/a |
| Submit scoped agent task | ✓ | ✓ | ✓ | ✓ |
| Observe and cancel run | ✓ | ✓ | ✓ | ✓ |
| Resolve approval | ✓ | ✓ | ✓ | ✓ |
| Review and accept/reject diff | ✓ | ✓ | ✓ | conflict case |

Run the repository’s relevant type check, lint, unit/integration tests, and production build. If a check cannot run, state why and report the strongest alternative evidence. Never claim visual verification from source inspection alone.
