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
      <CardContent className="px-3 py-2 space-y-1.5">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-baseline gap-2 min-w-0 flex-1">
            <h1 className="font-serif text-sm font-bold text-foreground shrink-0">总览</h1>
            {projects.length === 0 ? (
              <p className="text-xs text-muted-foreground truncate">
                上传一部小说，开始你的第一次分析。
              </p>
            ) : (
              <p className="text-xs text-muted-foreground truncate">
                共 <strong className="font-mono">{projects.length}</strong> 卷 · 焦点
                <strong className="ml-1">{latestProjectName}</strong>
              </p>
            )}
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Badge variant="secondary" className="text-[11px] px-1.5 py-0 h-5">
              {latestProjectStatus}
            </Badge>
            <Badge variant="secondary" className="text-[11px] px-1.5 py-0 h-5">
              {activeStageLabel || "等待启动"}
            </Badge>
            <Button size="sm" className="h-6 px-2 text-xs" onClick={onStartNew}>
              <Plus className="mr-1 h-3 w-3" />
              新分析
            </Button>
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={onRefresh}>
              <RefreshCw className="h-3 w-3" />
            </Button>
          </div>
        </div>

        {errorMessage && (
          <p className="rounded bg-destructive/10 px-2 py-1 text-[11px] font-mono text-destructive">
            {errorMessage}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
