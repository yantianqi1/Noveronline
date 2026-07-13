import { Bi } from "./bilingual-text";

export function ProjectWorkspaceLoading() {
  return (
    <div className="workspace-loading-root">
      <div className="workspace-loading" role="status" aria-live="polite" aria-busy="true">
        <span className="sr-only"><Bi zh="正在加载内容" en="Loading content" /></span>
        <header className="workspace-loading-header" aria-hidden="true">
          <span className="workspace-loading-kicker" />
          <span className="workspace-loading-title" />
          <span className="workspace-loading-status" />
        </header>
        <div className="workspace-loading-grid" aria-hidden="true">
          <main>
            <span className="workspace-loading-panel workspace-loading-panel-primary" />
            <span className="workspace-loading-panel" />
          </main>
          <aside>
            <span className="workspace-loading-panel workspace-loading-panel-rail" />
          </aside>
        </div>
      </div>
    </div>
  );
}
