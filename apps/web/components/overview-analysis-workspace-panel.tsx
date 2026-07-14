import { ChevronRight, FolderOpen } from "lucide-react";

import type {
  AnalysisWorkspaceFileSummary,
  AnalysisWorkspaceFilesSummary,
} from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

type OverviewAnalysisWorkspacePanelProps = {
  locale: Locale;
  workspaceFiles: AnalysisWorkspaceFilesSummary | null;
  selectedFile: AnalysisWorkspaceFileSummary | null;
  selectedPath: string;
  runId: string;
  tenantSlug: string;
  projectId: string;
};

export function OverviewAnalysisWorkspacePanel({
  locale,
  workspaceFiles,
  selectedFile,
  selectedPath,
}: OverviewAnalysisWorkspacePanelProps) {
  if (!workspaceFiles) {
    return (
      <details className="overview-details overview-analysis-workspace">
        <summary>
          <FolderOpen aria-hidden="true" size={18} strokeWidth={1.8} />
          <span>
            <strong id="analysis-workspace-heading">
              <Bi zh="分析工作区" en="Analysis workspace" />
            </strong>
            <small><Bi zh="开始分析后显示" en="Appears after analysis starts" /></small>
          </span>
          <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
        </summary>
        <div className="overview-details-content">
          <section>
            <p className="form-hint">
              <Bi zh="开始分析后，这里会显示计划、笔记与候选文件。" en="After analysis starts, plan, notes, and candidate files appear here." />
            </p>
          </section>
        </div>
      </details>
    );
  }

  if (!workspaceFiles.ok) {
    return (
      <details className="overview-details overview-analysis-workspace error-box" open>
        <summary>
          <FolderOpen aria-hidden="true" size={18} strokeWidth={1.8} />
          <span>
            <strong id="analysis-workspace-heading">
              <Bi zh="分析工作区" en="Analysis workspace" />
            </strong>
            <small><Bi zh="加载失败" en="Failed to load" /></small>
          </span>
          <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
        </summary>
        <div className="overview-details-content">
          <section>
            <p>{workspaceFiles.message || tx(locale, "无法加载工作区文件。", "Could not load workspace files.")}</p>
          </section>
        </div>
      </details>
    );
  }

  const files = workspaceFiles.items.filter((item): item is Extract<AnalysisWorkspaceFileSummary, { ok: true }> => item.ok);
  const summaryHint =
    files.length === 0
      ? tx(locale, "尚无文件", "No files yet")
      : tx(locale, `${files.length} 个文件`, `${files.length} files`);

  return (
    <details className="overview-details overview-analysis-workspace" open={files.length > 0 || undefined}>
      <summary>
        <FolderOpen aria-hidden="true" size={18} strokeWidth={1.8} />
        <span>
          <strong id="analysis-workspace-heading">
            <Bi zh="分析工作区" en="Analysis workspace" />
          </strong>
          <small>{summaryHint}</small>
        </span>
        <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
      </summary>
      <div className="overview-details-content">
        <section>
          <p className="form-hint">
            <Bi
              zh="Pi 智能体写入的项目分析文件夹（计划 / 源切片 / 笔记 / 候选）。拆解结果会自动写入素材库，可直接在资产库使用。"
              en="Project analysis folder written by the Pi agent (plan / source slices / notes / candidates). Results are auto-imported into the asset library."
            />
          </p>
          {files.length === 0 ? (
            <p className="form-hint"><Bi zh="工作区尚无文件。" en="No workspace files yet." /></p>
          ) : (
            <div className="overview-analysis-workspace-grid">
              <ul className="overview-analysis-file-tree">
                {files.map((file) => (
                  <li key={file.file_id} data-kind={file.kind} data-active={file.path === selectedPath ? "true" : "false"}>
                    <a href={`?runId=${encodeURIComponent(file.run_id)}&workspacePath=${encodeURIComponent(file.path)}`}>
                      <span className="overview-analysis-file-path">{file.path}</span>
                      <span className="overview-analysis-file-meta">
                        {file.kind} · {file.size_bytes} B
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
              <div className="overview-analysis-file-preview">
                {selectedFile && selectedFile.ok ? (
                  <>
                    <header>
                      <strong>{selectedFile.path}</strong>
                      <span>{selectedFile.kind}</span>
                    </header>
                    <pre>{selectedFile.content_text || tx(locale, "（无文本预览）", "(no text preview)")}</pre>
                  </>
                ) : (
                  <p className="form-hint">
                    <Bi zh="选择左侧文件以预览内容。" en="Select a file on the left to preview." />
                  </p>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </details>
  );
}
