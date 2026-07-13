# Implementation guide and project references

## Contents

1. Stack selection
2. Suggested module structure
3. State and performance
4. Reference projects
5. License rules

## Stack selection

Preserve the current stack unless migration is explicitly requested. For greenfield web work, default to:

For MiroFish-Novel specifically, use only the existing Next.js app under `apps/web`. The retired root `frontend/` and its Vite application must remain absent.

- TypeScript with strict mode;
- React with Next.js or Vite;
- semantic CSS variables plus Tailwind or CSS Modules;
- Radix/shadcn primitives for accessible foundations;
- a mature editor such as Lexical, ProseMirror/Tiptap, or CodeMirror selected by document requirements;
- TanStack Query or framework-native server cache for persisted resources;
- a small normalized store for live agent runs and event cursors;
- schema validation at the network boundary.

Choose AI UI layers intentionally:

| Need | Prefer |
|---|---|
| Chat/thread runtime, attachments, branching | assistant-ui |
| Copy-owned shadcn-style AI components | Vercel AI Elements |
| Agent changes application state or renders generative UI | CopilotKit / AG-UI |
| LangGraph prototype with minimal setup | LangGraph Agent Chat UI |
| Custom writing studio with little chat | native domain components plus a thin agent adapter |

Do not combine several libraries merely to show sophistication. Use the smallest set that owns distinct responsibilities.

## Suggested module structure

Adapt names to the repository:

```text
src/
  app/                         routes and screen composition
  features/
    manuscript/                editor, selection, versions, diffs
    outline/                   outline and scene planning
    story-bible/               characters, world, relationships
    agent-runs/                run store, timeline, approvals
  components/
    ui/                        accessible generic primitives
    agent/                     reusable agent presentation
  lib/
    agent-client/              commands, stream parser, reconnect
    schemas/                   runtime network validation
    persistence/               drafts and client recovery
  styles/                      semantic tokens and global styles
  tests/                       integration and journey tests
```

Keep feature components close to their domain. Do not create a giant `components/` folder or a single `AgentContext` containing editor, auth, navigation, runs, and network state.

## State and performance

- Normalize runs by ID and retain only bounded event history in hot memory.
- Batch high-frequency token and patch events using animation frames or short buffers.
- Memoize selectors, not whole pages.
- Virtualize long run histories, event timelines, chapter trees, and search results.
- Lazy-load the rich editor, large diff engines, diagrams, and generated previews.
- Persist composer drafts and last event cursor locally; persist canonical content on the server.
- Add error boundaries around generated content, editor plugins, and agent inspectors.
- Avoid storing derived display strings in the server state.
- Prefer contract/integration tests for stream ordering, reconnect, cancellation, approvals, and version conflicts.

## Reference projects

Use these as pattern libraries, not wholesale visual templates:

- [assistant-ui](https://github.com/assistant-ui/assistant-ui): thread runtime, streaming, attachments, interruption, reusable React primitives.
- [Vercel AI Elements](https://github.com/vercel/ai-elements): composable shadcn-style message, reasoning, tool, source, and workflow components.
- [CopilotKit](https://github.com/CopilotKit/CopilotKit): generative UI, human-in-the-loop, and shared application state.
- [LangGraph Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui): LangGraph integration and agent state interactions.
- [Agent TARS / UI-TARS Desktop](https://github.com/bytedance/UI-TARS-desktop): live execution, event stream, browser/computer operation, tool inspection.
- [OpenAgents Workspace](https://github.com/openagents-org/openagents): persistent multi-agent threads, shared files/browser, agent roster and mentions.
- [AionUi](https://github.com/iOfficeAI/AionUi): local desktop cowork shell, multi-agent execution, files, and long-running tasks.
- [OpenLoaf](https://github.com/OpenLoaf/OpenLoaf): project-centric multi-agent workspace, canvas, file tree, terminal, and task board.
- [Claude Artifacts](https://www.anthropic.com/news/projects): conversation plus side-by-side durable artifact.
- [Manus](https://manus.im/), [Genspark](https://www.genspark.ai/), and [Devin](https://cognition.ai/blog/introducing-devin): commercial references for run observability, deliverables, workspaces, and intervention.

## License rules

- Prefer MIT, Apache-2.0, BSD, ISC, or similarly permissive dependencies when commercial reuse matters.
- Record every copied component, font, icon set, code snippet, and asset in the project’s dependency/license inventory.
- Treat visual inspiration as inspiration: do not copy proprietary assets, logos, illustrations, trade dress, or pixel-identical layouts.
- assistant-ui and CopilotKit are MIT; Vercel AI Elements, Agent TARS/UI-TARS Desktop, OpenAgents, and AionUi are Apache-2.0 at the linked repositories when this reference was authored.
- OpenLoaf is AGPL-3.0 with a commercial-license option; do not copy it into a closed-source product without reviewing obligations.
- Dify uses a custom license based on Apache-2.0 with additional conditions. Open WebUI has changed licensing/branding terms over time. Review their current repository terms before reuse.
- Verify current licenses at implementation time; project licenses can change.
