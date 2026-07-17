"use client";

import { useEffect, useState, type MouseEvent } from "react";

import type {
  AnalysisWorkspaceFileSummary,
  AnalysisWorkspaceFilesSummary,
} from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

type OkWorkspaceFile = Extract<AnalysisWorkspaceFileSummary, { ok: true }>;

type OverviewAnalysisWorkspaceBrowserProps = {
  locale: Locale;
  workspaceFiles: Extract<AnalysisWorkspaceFilesSummary, { ok: true }>;
  selectedFile: AnalysisWorkspaceFileSummary | null;
  selectedPath: string;
  runId: string;
  tenantSlug: string;
  projectId: string;
  presentation: "details" | "body";
};

/**
 * Interactive workspace file list + preview.
 * Uses client fetch + history.replaceState so modal hosts do not RSC-remount on each click.
 */
export function OverviewAnalysisWorkspaceBrowser({
  locale,
  workspaceFiles,
  selectedFile,
  selectedPath,
  runId,
  tenantSlug,
  projectId,
  presentation,
}: OverviewAnalysisWorkspaceBrowserProps) {
  const [activePath, setActivePath] = useState(selectedPath);
  const [activeFile, setActiveFile] = useState(selectedFile);
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    setActivePath(selectedPath);
    setActiveFile(selectedFile);
    setLoadError("");
  }, [selectedPath, selectedFile]);

  const files = workspaceFiles.items.filter((item): item is OkWorkspaceFile => item.ok);

  async function selectFile(event: MouseEvent<HTMLAnchorElement>, file: OkWorkspaceFile) {
    event.preventDefault();
    if (file.path === activePath && activeFile && activeFile.ok) {
      return;
    }

    setActivePath(file.path);
    setLoadingPath(file.path);
    setLoadError("");

    const url = new URL(window.location.href);
    url.searchParams.set("runId", file.run_id || runId);
    url.searchParams.set("workspacePath", file.path);
    if (presentation === "body") {
      url.searchParams.set("board", "workspace");
    }
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);

    try {
      const response = await fetch(
        `/api/analysis-workspace/${encodeURIComponent(tenantSlug)}/${encodeURIComponent(projectId)}?` +
          new URLSearchParams({
            runId: file.run_id || runId,
            path: file.path,
          }).toString(),
        { cache: "no-store" },
      );
      const payload = (await response.json().catch(() => null)) as AnalysisWorkspaceFileSummary | null;
      if (!response.ok || !payload || !payload.ok) {
        setLoadError(tx(locale, "无法加载文件预览。", "Could not load file preview."));
        setActiveFile(null);
      } else {
        setActiveFile(payload);
      }
    } catch {
      setLoadError(tx(locale, "无法加载文件预览。", "Could not load file preview."));
      setActiveFile(null);
    } finally {
      setLoadingPath(null);
    }
  }

  if (files.length === 0) {
    return <p className="form-hint"><Bi zh="工作区尚无文件。" en="No workspace files yet." /></p>;
  }

  return (
    <div className="overview-analysis-workspace-grid">
      <ul className="overview-analysis-file-tree">
        {files.map((file) => (
          <li key={file.file_id} data-kind={file.kind} data-active={file.path === activePath ? "true" : "false"}>
            <a
              href={`?runId=${encodeURIComponent(file.run_id)}&workspacePath=${encodeURIComponent(file.path)}${presentation === "body" ? "&board=workspace" : ""}`}
              onClick={(event) => {
                void selectFile(event, file);
              }}
            >
              <span className="overview-analysis-file-path">{file.path}</span>
              <span className="overview-analysis-file-meta">
                {file.kind} · {file.size_bytes} B
              </span>
            </a>
          </li>
        ))}
      </ul>
      <div className="overview-analysis-file-preview" aria-busy={loadingPath ? "true" : "false"}>
        {loadingPath ? (
          <p className="form-hint"><Bi zh="正在加载预览…" en="Loading preview…" /></p>
        ) : loadError ? (
          <p className="form-hint">{loadError}</p>
        ) : activeFile && activeFile.ok ? (
          <>
            <header>
              <strong>{activeFile.path}</strong>
              <span>{activeFile.kind}</span>
            </header>
            <pre>{activeFile.content_text || tx(locale, "（无文本预览）", "(no text preview)")}</pre>
          </>
        ) : (
          <p className="form-hint">
            <Bi zh="选择左侧文件以预览内容。" en="Select a file on the left to preview." />
          </p>
        )}
      </div>
    </div>
  );
}
