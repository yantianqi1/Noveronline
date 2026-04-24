/**
 * RecentProjects — grid of recent project cards with delete and navigation.
 */

import { useNavigate } from "react-router";
import { Trash2, Link2, Radio, RotateCcw, RefreshCcw } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { relinkProjectData } from "@/api/project";
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

const RELINK_ELIGIBLE_STATUSES = new Set(["ontology_generated", "failed"]);

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
  onRejoinProject?: (project: Project) => void;
  onContinueProject?: (project: Project) => void;
  onRerunProject?: (project: Project) => void;
}

/* ---------- Component ---------- */

export default function RecentProjects({
  projects,
  onDeleteProject,
  onRejoinProject,
  onContinueProject,
  onRerunProject,
}: RecentProjectsProps) {
  const navigate = useNavigate();

  const relinkMutation = useMutation({
    mutationFn: (projectId: string) => relinkProjectData(projectId),
    onSuccess: () => {
      toast.success("正在重新打通数据，请在任务面板查看进度。");
    },
    onError: (err: Error) => {
      toast.error(err.message || "启动数据打通失败");
    },
  });

  if (projects.length === 0) return null;

  function handleCardClick(item: Project): void {
    // Primary click for stuck/in-progress projects: try the smart
    // "continue from checkpoint" path (rejoin live task if possible,
    // otherwise retry failed segments). Falls back to /assets for
    // completed projects without a graph.
    const INCOMPLETE_STATUSES = new Set([
      "created",
      "seed_processing",
      "ontology_generated",
      "graph_building",
    ]);
    if (item.status && INCOMPLETE_STATUSES.has(item.status)) {
      if (onContinueProject) {
        onContinueProject(item);
        return;
      }
      if (item.seed_task_id && onRejoinProject) {
        onRejoinProject(item);
        return;
      }
    }
    navigate(`/assets?project_id=${item.id}`);
  }

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
        {projects.map((item) => {
          const canRelink = RELINK_ELIGIBLE_STATUSES.has(item.status);
          const isSeedProcessing = item.status === "seed_processing";
          const isRecoverable = isSeedProcessing || item.status === "failed";
          const canRejoin = isSeedProcessing && !!item.seed_task_id && !!onRejoinProject;
          const canContinue = isRecoverable && !!onContinueProject;
          const canRerun = isRecoverable && !!onRerunProject;
          return (
          <Card
            key={item.id}
            className="cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => handleCardClick(item)}
          >
            <CardContent className="p-3 flex flex-col gap-1.5 h-full">
              {/* Top row: status + actions */}
              <div className="flex items-center justify-between gap-1.5">
                <Badge variant={statusVariant(item.status)} className="text-[11px]">
                  {formatProjectStatus(item.status)}
                </Badge>
                <div className="flex items-center gap-0.5">
                  {canRejoin && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-primary"
                      title="重新接入正在运行的任务"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRejoinProject?.(item);
                      }}
                    >
                      <Radio className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {canContinue && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-primary"
                      title="断点续传（先重新接入活着的任务，否则重读失败段落）"
                      onClick={(e) => {
                        e.stopPropagation();
                        onContinueProject?.(item);
                      }}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {canRerun && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-amber-600"
                      title="使用已上传的文件重新从头开始分析"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRerunProject?.(item);
                      }}
                    >
                      <RefreshCcw className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {canRelink && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-muted-foreground hover:text-amber-600"
                      title="重新打通数据（档案库 / 图谱 / 索引）"
                      disabled={relinkMutation.isPending}
                      onClick={(e) => {
                        e.stopPropagation();
                        relinkMutation.mutate(item.id);
                      }}
                    >
                      <Link2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
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
                {isRecoverable ? (
                  <div className="flex items-center gap-2">
                    {canContinue && (
                      <Button
                        variant="link"
                        size="sm"
                        className="text-[11px] h-auto p-0 text-primary"
                        onClick={(e) => {
                          e.stopPropagation();
                          onContinueProject?.(item);
                        }}
                      >
                        断点续传
                      </Button>
                    )}
                    {canRerun && (
                      <Button
                        variant="link"
                        size="sm"
                        className="text-[11px] h-auto p-0 text-amber-700"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRerunProject?.(item);
                        }}
                      >
                        重新开始
                      </Button>
                    )}
                  </div>
                ) : (
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
                )}
              </div>
            </CardContent>
          </Card>
          );
        })}
      </div>
    </section>
  );
}
