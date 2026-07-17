import type { AnalysisWorkspaceFilesSummary } from "../lib/api";
import { type Locale, tx } from "../lib/locale";

export function analysisWorkspaceSummaryHint(
  locale: Locale,
  workspaceFiles: AnalysisWorkspaceFilesSummary | null,
) {
  if (!workspaceFiles) {
    return tx(locale, "开始分析后显示", "Appears after analysis starts");
  }
  if (!workspaceFiles.ok) {
    return tx(locale, "加载失败", "Failed to load");
  }
  const count = workspaceFiles.items.filter((item) => item.ok).length;
  return count === 0
    ? tx(locale, "尚无文件", "No files yet")
    : tx(locale, `${count} 个文件`, `${count} files`);
}
