/**
 * RecentProjects — grid of recent project cards with delete and navigation.
 */

import { useNavigate } from "react-router";
import { Trash2 } from "lucide-react";

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

function statusVariant(
  status: string,
): "destructive" | "default" | "secondary" | "outline" {
  if (status === "failed") return "destructive";
  if (status?.includes("completed")) return "default";
  return "secondary";
}

/* ---------- Props ---------- */

interface RecentProjectsProps {
  projects: Project[];
  onDeleteProject: (project: Project) => void;
}

/* ---------- Component ---------- */

export default function RecentProjects({
  projects,
  onDeleteProject,
}: RecentProjectsProps) {
  const navigate = useNavigate();

  if (projects.length === 0) return null;

  return (
    <section className="w-full space-y-2.5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-serif font-semibold">最近卷宗</h3>
        <Button
          variant="link"
          size="sm"
          className="text-xs h-auto p-0"
          onClick={() => navigate("/assets")}
        >
          查看全部
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {projects.map((item) => (
          <Card
            key={item.id}
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => navigate(`/assets?project_id=${item.id}`)}
          >
            <CardContent className="p-3 flex flex-col gap-1.5 h-full">
              {/* Top row: status + delete */}
              <div className="flex items-center justify-between gap-1.5">
                <Badge variant={statusVariant(item.status)} className="text-[11px]">
                  {formatProjectStatus(item.status)}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteProject(item);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>

              {/* Project info */}
              <div className="flex flex-col gap-1 flex-1">
                <div className="font-bold text-sm text-foreground truncate">
                  {item.name}
                </div>
                <div className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                  {item.analysis_goal || "无明确分析目标"}
                </div>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between pt-1.5 mt-auto border-t text-[11px]">
                <span className="font-mono text-muted-foreground">
                  {item.id.slice(0, 8)}
                </span>
                <Button
                  variant="link"
                  size="sm"
                  className="text-[11px] h-auto p-0"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/assets?project_id=${item.id}`);
                  }}
                >
                  详情
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
