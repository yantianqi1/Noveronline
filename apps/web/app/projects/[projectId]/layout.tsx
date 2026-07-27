import { Feather } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { WorkbenchNavDrawer } from "./workbench-nav-drawer";
import { WorkbenchNav } from "./workbench-nav-rail";

/**
 * Project workspace shell — the shared chrome around all seven workbenches.
 *
 * Layout: a top bar (back-to-shelf + project context), a fixed primary nav
 * rail on the left (the seven mandated sections), and the workbench content
 * area on the right. Server component; the nav rail is the only client island.
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
    <div className="flex h-screen flex-col overflow-hidden bg-paper">
      {/* ── Top bar ────────────────────────────────────────────────── */}
      {/* The header's inner box carries the same max-width and gutter as the
          body below, so the nav rail's vertical border meets the header's
          bottom border instead of floating free on wide screens. */}
      <header className="shrink-0 border-b border-line bg-paper/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-[1600px] items-center justify-between gap-4 px-5">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href="/workspace"
              className="flex items-center gap-2.5 rounded-control transition-opacity hover:opacity-80"
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
              <span aria-hidden className="text-muted-soft">
                /
              </span>
              <span className="truncate font-medium text-ink">项目工作台</span>
            </nav>
            {/* Phone band: the rail is gone, so navigation lives in a drawer. */}
            <WorkbenchNavDrawer projectId={projectId} />
          </div>
        </div>
      </header>

      {/* ── Body: nav rail + workbench content ─────────────────────── */}
      {/* The app chrome pins to the viewport: header is h-14, the body takes
          exactly the remaining viewport height (100dvh − 3.5rem), and each
          workbench scrolls internally, so the whole page never scrolls. dvh
          tracks the visible viewport, not the layout viewport. */}
      <div className="mx-auto flex h-[calc(100dvh-3.5rem)] w-full max-w-[1600px] overflow-hidden">
        <aside className="hidden h-full w-rail-nav shrink-0 overflow-y-auto border-r border-line-soft py-5 stack:block">
          <WorkbenchNav projectId={projectId} />
        </aside>
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
