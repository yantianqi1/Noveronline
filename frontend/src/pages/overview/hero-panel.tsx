/**
 * HeroPanel — project count, latest project name, status badges, and action buttons.
 */

import { RefreshCw, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Project } from "@/types/project";

/* ---------- Display helpers ---------- */

const PROJECT_STATUS_TEXT: Record<string, string> = {
  created: "已创建",
  seed_processing: "种子分析中",
  ontology_generated: "本体已生成",
  graph_building: "图谱构建中",
  graph_completed: "图谱已完成",
  completed: "已完成",
  failed: "失败",
};

function formatProjectStatus(status: string): string {
  return PROJECT_STATUS_TEXT[status] || "状态未知";
}

/* ---------- Props ---------- */

interface HeroPanelProps {
  projects: Project[];
  uploadPhase: string;
  activeStageLabel: string;
  errorMessage: string;
  onRefresh: () => void;
  onStartNew: () => void;
}

/* ---------- Component ---------- */

export default function HeroPanel({
  projects,
  uploadPhase,
  activeStageLabel,
  errorMessage,
  onRefresh,
  onStartNew,
}: HeroPanelProps) {
  const latestProject = projects[0] ?? null;
  const latestProjectName = latestProject?.name || "未命名卷宗";
  const latestProjectStatus = latestProject
    ? formatProjectStatus(latestProject.status)
    : "等待投放小说";

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* Top row */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h1 className="font-serif text-xl font-bold text-foreground">总览</h1>
            {projects.length === 0 ? (
              <p className="mt-1 text-sm text-muted-foreground">
                上传一部小说，开始你的第一次分析。
              </p>
            ) : (
              <p className="mt-1 text-sm text-muted-foreground">
                共 <strong className="font-mono">{projects.length}</strong> 卷，焦点：
                <strong>{latestProjectName}</strong>
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <Badge variant="secondary" className="text-xs">
              <span className="font-mono mr-1 text-muted-foreground">状态</span>
              {latestProjectStatus}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              <span className="font-mono mr-1 text-muted-foreground">阶段</span>
              {activeStageLabel || "等待启动"}
            </Badge>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button size="sm" onClick={onStartNew}>
            <Plus className="mr-1.5 h-4 w-4" />
            开始分析新小说
          </Button>
          <Button variant="ghost" size="sm" onClick={onRefresh}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            刷新
          </Button>
        </div>

        {/* Error message */}
        {errorMessage && (
          <p className="mt-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs font-mono text-destructive">
            {errorMessage}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
