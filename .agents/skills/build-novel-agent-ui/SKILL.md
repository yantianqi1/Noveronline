---
name: build-novel-agent-ui
description: Design, implement, refactor, or audit polished frontends for novel-writing agents and other long-running creative agents. Use when Codex must build a writing studio, connect a frontend to an agent backend, stream run/tool/artifact events, add human approvals and revision workflows, improve an AI-generated interface, establish React/Next.js UI architecture, or turn a generic chat screen into a production-quality agent workspace.
---

# Build Novel Agent UI

Build a calm Agent-first editorial workspace in which the continuous task thread is the primary interaction and manuscripts remain durable, separately addressable artifacts. Treat visual design, agent connectivity, resilience, and writing-domain workflows as one system.

## Choose the operating mode

- **Audit**: inspect the existing UI and agent path, reproduce failures, and report prioritized findings. Do not change files unless asked.
- **Design**: produce the screen map, interaction model, event contract, component tree, tokens, and implementation plan.
- **Build/refactor**: implement the smallest complete vertical slice, verify it with real agent states, then extend it.

## Follow this workflow

1. **Inspect before choosing a stack.** Read project instructions, package manifests, routes, styling, backend handlers, schemas, and tests. Preserve established conventions and unrelated user changes.
2. **Trace one real user journey end to end.** Prefer “open chapter → ask for revision → stream activity → review diff → accept/reject” over a gallery of disconnected screens.
3. **Define the frontend/backend contract before polishing.** Identify commands, event transport, persistent entities, run states, cancellation, approval, reconnect, and artifact version semantics. Read [agent-connection.md](references/agent-connection.md).
4. **Select the product shell.** Default to a modern agent workspace: project navigation, a continuous task thread with a persistent composer, and a sibling artifact workspace for manuscript, structure, review, and planning. Read [product-architecture.md](references/product-architecture.md).
5. **Implement a vertical slice.** Include loading, empty, streaming, waiting-for-user, success, failure, cancel, and reconnect states. Never demonstrate connectivity using only fake timers if a backend exists.
6. **Apply the design system.** Reuse the project’s tokens when coherent; otherwise adapt [editorial-tokens.css](assets/editorial-tokens.css) and [design-system.md](references/design-system.md).
7. **Build domain components, not generic dashboard cards.** Read [component-specs.md](references/component-specs.md) for writing-specific components and state requirements.
8. **Verify proportionally to risk.** Run relevant type checks, lint, tests, and build. Exercise the real journey at desktop and narrow widths. Use [quality-gates.md](references/quality-gates.md) before handoff.

## Enforce the agent interaction rules

- Keep the artifact workspace stable while agent activity streams in the thread; never make prose jump because status text grows.
- Represent every run with an explicit state machine. A spinner is not a state model.
- Make long-running work cancellable; make failed and interrupted work retryable or resumable.
- Preserve `runId`, `threadId`, event cursor, artifact version, and idempotency key across reconnects.
- Stream concise activity summaries, tool names, affected files/chapters, and outcomes. Never expose private chain-of-thought.
- Require explicit confirmation before destructive rewrites, bulk deletion, publishing, spending money, or external side effects.
- Render artifact changes as patches or diffs with accept/reject controls; do not silently replace authored text.
- Keep user edits authoritative. Detect version conflicts and offer compare, merge, or duplicate instead of last-write-wins.
- Make source-of-truth ownership clear: server owns runs and persisted artifacts; client owns ephemeral presentation and drafts until saved.
- Provide keyboard and screen-reader access to every action available by pointer.

For a new TypeScript contract, adapt [agent-events.ts](assets/agent-events.ts); do not copy it blindly over an existing backend schema.

## Enforce the visual rules

- Design for sustained writing sessions: quiet surfaces, strong typography, low visual noise, and one dominant canvas.
- Use an editorial hierarchy, not a SaaS analytics dashboard. Prefer sections, dividers, tabs, and typography over nested cards.
- Use one accent family plus semantic colors. Do not use decorative gradients, glassmorphism, excessive pills, emoji icons, or glowing AI effects unless the product already has that visual language.
- Keep body text readable at `16px` or larger, prose measure near `65–78ch`, and interactive targets at least `40px`.
- Use a serif for manuscript content and a sans-serif for controls only when both support the required writing languages.
- Animate state changes with restrained `120–220ms` transitions; respect reduced-motion settings.
- Use skeletons only where geometry is known. Use precise status copy for agent work instead of indefinite decorative loaders.
- Do not ship dead buttons, placeholder menus, fake model selectors, decorative graphs, or controls with missing error states.

## Prefer these implementation patterns

- Preserve the existing framework. For a new React project, prefer TypeScript, Next.js or Vite, Tailwind or CSS variables, Radix/shadcn primitives, and a thin typed agent client.
- In MiroFish-Novel, `apps/web` is the only frontend. Never recreate the retired root `frontend/`, start a Vite compatibility UI, copy the blue legacy theme, or use retired Writer screenshots as a baseline.
- Use **assistant-ui** for production chat/thread runtime, **AI Elements** for copy-owned AI components, and **CopilotKit/AG-UI** when the agent must control application state or render generative UI. Treat Agent TARS, OpenAgents, AionUi, Claude Artifacts, Manus, and Devin as interaction references, not dependencies by default.
- Keep transport parsing separate from presentation. Normalize backend events into a frontend store, then render selectors from that store.
- Keep server state, editor state, and ephemeral UI state separate. Do not put the entire application in one context provider.
- Lazy-load heavy editor, diff, diagram, and preview code. Virtualize long timelines and large chapter lists.
- Read [implementation-guide.md](references/implementation-guide.md) for folder structure, selection criteria, and license notes.

## Handoff requirements

Report the user-visible outcome first. Then list changed files, the real journey verified, checks run, and any backend assumptions or remaining risks. Include screenshots only when they materially help review. Do not claim the UI is connected unless a real request/event path was exercised or clearly identify the mocked boundary.
