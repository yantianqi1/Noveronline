# Product architecture

## Contents

1. Product principle
2. Default information architecture
3. Writing-domain model
4. Core journeys
5. Responsive behavior

## Product principle

Make the Agent thread the primary work interaction and keep the manuscript as a durable artifact. A user should always know:

- where they are in the book;
- what the agent is doing;
- which context the agent can see;
- what changed;
- whether a change has been saved, accepted, or published.

Agent-first does not mean chat-only. Writing work has durable structure, versions, entities, and artifacts that must remain addressable outside the thread.

## Default information architecture

Use an Agent-first workspace when the existing product has no stronger pattern:

| Region | Purpose | Typical contents |
|---|---|---|
| Top bar | Global orientation | Project title, save/sync state, search, command palette, export/share |
| Left navigation | Durable book structure | Volumes, chapters, scenes, characters, world bible, research, run history |
| Main thread | Work interaction | Author instructions, run progress, tool activity, candidate prose, approvals and recovery |
| Artifact workspace | Durable output | Manuscript, chapter structure, diff review, planning, preview |
| Persistent composer | Intent entry | Prompt, mode, selected context, attachments, send/cancel |

Do not show all artifact modes at full density simultaneously. Give the thread the primary task flow and expose manuscript, structure, review, and studio content through mutually exclusive artifact tabs. On narrow screens, show thread first and artifact second rather than shrinking both.

### Recommended screens

- Project home: recent chapters, unresolved continuity issues, active runs, writing goal.
- Writing studio: continuous Agent thread plus a sibling artifact workspace.
- Outline board: act/chapter/scene hierarchy with drag and keyboard reorder.
- Story bible: characters, locations, factions, rules, relationships, glossary.
- Revision review: before/after diff, rationale summary, accept by hunk or selection.
- Run history: searchable tasks with status, duration, affected artifacts, and recovery actions.
- Settings: model/provider, style guide, safety, export, integrations. Keep it out of the writing flow.

## Writing-domain model

Keep product entities explicit even if the backend names differ:

- `Project`: book-level settings, language, genre, voice, style guide.
- `Manuscript`: ordered volumes/chapters/scenes and current published/saved version.
- `OutlineNode`: act, chapter, scene, beat, goal, conflict, outcome.
- `StoryEntity`: character, location, faction, object, rule, relationship.
- `KnowledgeSource`: research note, upload, URL, citation, user instruction.
- `AgentThread`: durable conversation scoped to a project or artifact.
- `AgentRun`: one asynchronous execution with status, events, approvals, and outputs.
- `ArtifactVersion`: immutable snapshot or patch with author, base version, and timestamp.
- `Suggestion`: proposed change that can be accepted, rejected, or edited.

Do not store the manuscript only as chat messages. Do not infer durable entities exclusively from rendered prose.

## Core journeys

### Revise selected text

1. User selects prose and invokes “revise”.
2. Composer shows the selected range and style context as removable chips.
3. Agent run appears immediately in the primary thread with cancel available.
4. Streaming activity remains concise; editor selection stays stable.
5. Agent returns a patch based on the selected version.
6. Diff view offers accept/reject per hunk and accept-all only when safe.
7. Accepted edits create a new artifact version; rejected text remains unchanged.

### Draft a chapter

1. User chooses an outline node and confirms relevant characters/world entries.
2. Agent creates a run and streams a structured plan before or alongside drafting.
3. Draft is written into a provisional artifact, not directly over the canonical chapter.
4. User reviews and promotes the draft to the manuscript.

### Continuity check

1. User chooses scope: current scene, chapter, arc, or entire manuscript.
2. Agent reports progress by scope segment without exposing hidden reasoning.
3. Results group by severity and entity, each linked to exact text locations.
4. Suggested fixes create reviewable patches rather than direct mutation.

## Responsive behavior

- `>= 1280px`: project navigation + primary thread + artifact workspace.
- `768–1279px`: collapsible navigation; thread and artifact keep usable minimum widths.
- `< 768px`: one primary surface at a time; thread comes first and artifact modes use tabs/sheets.
- Keep composer reachable above the mobile keyboard and preserve draft input during navigation.
- Never render desktop three-column density by shrinking everything.
