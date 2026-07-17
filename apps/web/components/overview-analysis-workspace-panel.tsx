import { ChevronRight, FolderOpen } from "lucide-react";

import type {
  AnalysisWorkspaceFileSummary,
  AnalysisWorkspaceFilesSummary,
} from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { analysisWorkspaceSummaryHint } from "../lib/overview-analysis-workspace-copy";
import { Bi } from "./bilingual-text";
import { OverviewAnalysisWorkspaceBrowser } from "./overview-analysis-workspace-browser";

export { analysisWorkspaceSummaryHint } from "../lib/overview-analysis-workspace-copy";

type OverviewAnalysisWorkspacePanelProps = {
  locale: Locale;
  workspaceFiles: AnalysisWorkspaceFilesSummary | null;
  selectedFile: AnalysisWorkspaceFileSummary | null;
  selectedPath: string;
  runId: string;
  tenantSlug: string;
  projectId: string;
  /** details = expandable disclosure (default); body = content only for modal hosts */
  presentation?: "details" | "body";
};

export function OverviewAnalysisWorkspacePanel({
  locale,
  workspaceFiles,
  selectedFile,
  selectedPath,
  runId,
  tenantSlug,
  projectId,
  presentation = "details",
}: OverviewAnalysisWorkspacePanelProps) {
  if (!workspaceFiles) {
    const body = (
      <section>
        <p className="form-hint">
          <Bi zh="开始分析后，这里会显示计划、笔记与候选文件。" en="After analysis starts, plan, notes, and candidate files appear here." />
        </p>
      </section>
    );
    if (presentation === "body") {
      return body;
    }
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
        <div className="overview-details-content">{body}</div>
      </details>
    );
  }

  if (!workspaceFiles.ok) {
    const body = (
      <section>
        <p>{workspaceFiles.message || tx(locale, "无法加载工作区文件。", "Could not load workspace files.")}</p>
      </section>
    );
    if (presentation === "body") {
      return body;
    }
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
        <div className="overview-details-content">{body}</div>
      </details>
    );
  }

  const summaryHint = analysisWorkspaceSummaryHint(locale, workspaceFiles);

  const body = (
    <section data-workspace-panel={presentation}>
      <p className="form-hint">
        <Bi
          zh="智能分析写入的项目文件夹（计划 / 源切片 / 笔记 / 候选）。拆解结果会自动写入素材库，可直接在资产库使用。"
          en="Project analysis folder (plan / source slices / notes / candidates). Results are auto-imported into the asset library."
        />
      </p>
      <OverviewAnalysisWorkspaceBrowser
        locale={locale}
        presentation={presentation}
        projectId={projectId}
        runId={runId}
        selectedFile={selectedFile}
        selectedPath={selectedPath}
        tenantSlug={tenantSlug}
        workspaceFiles={workspaceFiles}
      />
    </section>
  );

  if (presentation === "body") {
    return body;
  }

  return (
    <details className="overview-details overview-analysis-workspace">
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
      <div className="overview-details-content">{body}</div>
    </details>
  );
}
