import { Feather } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { ProjectSessionGate } from "./project-session-gate";
import { WorkbenchNavDrawer } from "./workbench-nav-drawer";
import { WorkbenchNav } from "./workbench-nav-rail";

import "./project-header.css";

/**
 * Project workspace shell — the shared chrome around all seven workbenches.
 *
 * Layout: a top bar (back-to-shelf + project context), a fixed primary nav
 * rail on the left (the seven mandated sections), and the workbench content
 * area on the right. The session gate resolves real membership before mounting
 * workbenches that read the selected tenant.
 */
export default function ProjectWorkspaceLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  return <Shell params={params}>{children}</Shell>;
}

async function Shell({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;

  return (
    <ProjectSessionGate key={projectId} projectId={projectId}>
    <div className="flex h-dvh flex-col overflow-hidden bg-paper">
      {/* ── Top bar ────────────────────────────────────────────────── */}
      {/* The header's inner box carries the same max-width and gutter as the
          body below, so the nav rail's vertical border meets the header's
          bottom border instead of floating free on wide screens. */}
      <header className="shrink-0 border-b border-line bg-paper/85 backdrop-blur-md">
        <div className="project-header-inner mx-auto flex h-14 w-full max-w-[1600px] items-center gap-4 px-5">
          <div className="flex min-w-0 shrink-0 items-center gap-3">
            <Link
              href="/workspace"
              className="flex min-h-11 min-w-11 items-center justify-center gap-2.5 rounded-control transition-opacity hover:opacity-80"
              aria-label="返回书架"
            >
              <span className="grid size-8 place-items-center rounded-control bg-accent text-panel shadow-accent">
                <Feather className="size-3.5" aria-hidden />
              </span>
              <span className="hidden font-brush text-lg text-ink sm:block">
                墨鱼小说
              </span>
            </Link>
            <span aria-hidden className="h-4 w-px bg-line" />
            <nav
              aria-label="面包屑"
              className="hidden min-w-0 items-center gap-1.5 text-sm stack:flex"
            >
              <Link
                href="/workspace"
                className="shrink-0 text-muted transition-colors hover:text-accent"
              >
                书架
              </Link>
            </nav>
            {/* Phone band: the rail is gone, so navigation lives in a drawer. */}
            <WorkbenchNavDrawer projectId={projectId} />
          </div>

          {/* One shared slot for the active workbench's context. The writer
              portals its chapter switcher / word count / save state / new-chapter
              here. The shared header wraps its controls on narrow screens.
              Empty on the other sections. */}
          <div id="project-topbar-slot" className="flex min-w-0 flex-1 items-center gap-3" />
        </div>
      </header>

      {/* ── Body: nav rail + workbench content ─────────────────────── */}
      {/* Use the height left by the responsive header; workbenches scroll inside. */}
      <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 overflow-hidden">
        {/* The nav rail owns its width: the client island flips data-collapsed
            on this aside, and the inline style below transitions between the
            expanded/collapsed spacing tokens. */}
        <aside
          data-collapsed="false"
          className="nav-rail-aside hidden h-full shrink-0 overflow-hidden border-r border-line-soft py-5 stack:block"
        >
          <WorkbenchNav projectId={projectId} />
        </aside>
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
    </ProjectSessionGate>
  );
}
