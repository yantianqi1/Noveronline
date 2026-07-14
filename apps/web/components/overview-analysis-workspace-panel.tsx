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
      <section className="panel overview-analysis-workspace" aria-labelledby="analysis-workspace-heading">
        <h3 id="analysis-workspace-heading">
          <Bi zh="分析工作区" en="Analysis workspace" />
        </h3>
        <p className="form-hint">
          <Bi zh="开始分析后，这里会显示计划、笔记与候选文件。" en="After analysis starts, plan, notes, and candidate files appear here." />
        </p>
      </section>
    );
  }

  if (!workspaceFiles.ok) {
    return (
      <section className="panel overview-analysis-workspace error-box" aria-labelledby="analysis-workspace-heading">
        <h3 id="analysis-workspace-heading">
          <Bi zh="分析工作区" en="Analysis workspace" />
        </h3>
        <p>{workspaceFiles.message || tx(locale, "无法加载工作区文件。", "Could not load workspace files.")}</p>
      </section>
    );
  }

  const files = workspaceFiles.items.filter((item): item is Extract<AnalysisWorkspaceFileSummary, { ok: true }> => item.ok);

  return (
    <section className="panel overview-analysis-workspace" aria-labelledby="analysis-workspace-heading">
      <h3 id="analysis-workspace-heading">
        <Bi zh="分析工作区" en="Analysis workspace" />
      </h3>
      <p className="form-hint">
        <Bi
          zh="Pi 智能体写入的项目分析文件夹（计划 / 源切片 / 笔记 / 候选）。候选结果默认非正典，需你在资产/就绪路径中确认。"
          en="Project analysis folder written by the Pi agent (plan / source slices / notes / candidates). Candidates are non-canon until you accept them."
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
  );
}
