/**
 * Overview page — main entry point for project overview, seed upload, and task monitoring.
 *
 * Two states:
 * 1. Default: Hero panel + Recent projects + Upload + Analysis results
 * 2. Processing: Hero + Workflow stream + Task focus card
 */

import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useProjectCatalog } from "@/hooks/use-project-catalog";
import { useSeedUpload } from "@/hooks/use-seed-upload";
import { deleteProject } from "@/api/project";
import type { Project } from "@/types/project";

import HeroPanel from "./hero-panel";
import RecentProjects from "./recent-projects";
import TaskFocusCard from "./task-focus-card";
import InlineWorkflowStream from "./inline-workflow-stream";
import RetryFailedSegmentsBanner from "./retry-failed-segments-banner";
import SeedUploadPanel from "./seed-upload-panel";
import SeedAnalysisPanel from "./seed-analysis-panel";

/* ---------- Component ---------- */

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const { projects, refreshProjects, isLoading: projectsLoading } = useProjectCatalog();
  const upload = useSeedUpload();

  const isProcessing = upload.uploadPhase !== "idle";
  const recentProjects = useMemo(() => projects.slice(0, 4), [projects]);
  const latestProject = useMemo(() => projects[0] ?? null, [projects]);
  const latestProjectWithResults = useMemo(
    () =>
      projects.find(
        (p) => p.status && p.status.includes("completed"),
      ) ?? null,
    [projects],
  );

  const focusProjectName = useMemo(() => {
    if (upload.uploadPhase !== "idle") {
      return upload.projectName.trim() || latestProject?.name || "当前卷宗";
    }
    return latestProject?.name || "当前卷宗";
  }, [upload.uploadPhase, upload.projectName, latestProject]);

  const [projectActionError, setProjectActionError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  const focusError = upload.error || projectActionError;

  /* ---- Refresh ---- */
  const handleRefresh = useCallback(() => {
    setProjectActionError("");
    refreshProjects();
  }, [refreshProjects]);

  /* ---- Scroll to upload ---- */
  const scrollToUpload = useCallback(() => {
    const el = document.getElementById("seed-upload-anchor");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }, []);

  /* ---- Delete project ---- */
  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast.success("项目已删除");
    },
    onError: (err: Error) => {
      setProjectActionError(err.message || "删除项目失败");
      setDeleteTarget(null);
    },
  });

  const handleDeleteProject = useCallback((project: Project) => {
    setDeleteTarget(project);
  }, []);

  const handleRejoinProject = useCallback(
    (project: Project) => {
      if (!project.seed_task_id) {
        toast.error("该项目未记录正在运行的任务 ID，无法重新接入。");
        return;
      }
      void upload
        .rejoinActiveTask({
          taskId: project.seed_task_id,
          projectId: project.id,
          projectName: project.name,
        })
        .catch((err: unknown) => {
          console.warn("[overview] rejoinActiveTask failed", err);
        });
    },
    [upload],
  );

  /* ---- Workflow error recovery ---- */
  const activeProject = useMemo(
    () => projects.find((p) => p.id === upload.completedProjectId) ?? null,
    [projects, upload.completedProjectId],
  );

  const handleDismissWorkflow = useCallback(() => {
    upload.dismissError();
  }, [upload]);

  const handleContinueWorkflow = useCallback(() => {
    const projectId = upload.completedProjectId || activeProject?.id || "";
    if (!projectId) {
      toast.error("无法定位项目 ID，无法继续分析。");
      return;
    }
    const toastId = toast.loading("正在尝试断点续传...");
    void upload
      .continueFromCheckpoint({
        projectId,
        projectName: activeProject?.name || upload.projectName,
        seedTaskId: activeProject?.seed_task_id || upload.taskId || null,
      })
      .then((result) => {
        if (result === "nothing") {
          toast.info("没有可继续的断点，请选择重新开始。", { id: toastId });
        } else if (result === "rejoined") {
          toast.success("已重新接入正在运行的后台任务。", { id: toastId });
        } else if (result === "retried") {
          toast.success("已触发对失败段落的断点续传。", { id: toastId });
        } else {
          toast.dismiss(toastId);
        }
      })
      .catch((err: unknown) => {
        console.warn("[overview] continueFromCheckpoint failed", err);
        toast.error(err instanceof Error ? err.message : "断点续传失败", {
          id: toastId,
        });
      });
  }, [upload, activeProject]);

  const handleRerunWorkflow = useCallback(() => {
    const projectId = upload.completedProjectId || activeProject?.id || "";
    if (!projectId) {
      toast.error("无法定位项目 ID，无法重新开始。");
      return;
    }
    const toastId = toast.loading("正在重新启动分析...");
    void upload
      .rerunSeed(projectId)
      .then(() => {
        toast.success("已提交重新开始请求，后台任务正在启动。", { id: toastId });
      })
      .catch((err: unknown) => {
        console.warn("[overview] rerunSeed failed", err);
        toast.error(err instanceof Error ? err.message : "重新开始失败", {
          id: toastId,
        });
      });
  }, [upload, activeProject]);

  /* ---- Per-project continue / rerun (idle view project cards) ---- */
  const handleContinueProject = useCallback(
    (project: Project) => {
      const toastId = toast.loading(`正在尝试断点续传「${project.name}」...`);
      void upload
        .continueFromCheckpoint({
          projectId: project.id,
          projectName: project.name,
          seedTaskId: project.seed_task_id || null,
        })
        .then((result) => {
          if (result === "nothing") {
            toast.info("没有可继续的断点，请选择重新开始。", { id: toastId });
          } else if (result === "rejoined") {
            toast.success("已重新接入正在运行的后台任务。", { id: toastId });
          } else if (result === "retried") {
            toast.success("已触发对失败段落的断点续传。", { id: toastId });
          } else {
            toast.dismiss(toastId);
          }
        })
        .catch((err: unknown) => {
          console.warn("[overview] continueFromCheckpoint failed", err);
          toast.error(err instanceof Error ? err.message : "断点续传失败", {
            id: toastId,
          });
        });
    },
    [upload],
  );

  const handleRerunProject = useCallback(
    (project: Project) => {
      const toastId = toast.loading(`正在重新启动「${project.name}」...`);
      void upload
        .rerunSeed(project.id)
        .then(() => {
          toast.success("已提交重新开始请求。", { id: toastId });
        })
        .catch((err: unknown) => {
          console.warn("[overview] rerunSeed failed", err);
          toast.error(err instanceof Error ? err.message : "重新开始失败", {
            id: toastId,
          });
        });
    },
    [upload],
  );

  const confirmDelete = useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id);
    }
  }, [deleteTarget, deleteMutation]);

  return (
    <div className="w-full space-y-3">
      {/* ========== Initial load skeleton ========== */}
      {projectsLoading && projects.length === 0 && !isProcessing && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_0.7fr] gap-2.5">
            <Skeleton className="h-36 rounded-lg" />
            <Skeleton className="h-36 rounded-lg" />
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-lg" />
            ))}
          </div>
          <Skeleton className="h-48 rounded-lg" />
        </div>
      )}

      {/* ========== Idle state ========== */}
      {!isProcessing && (
        <>
          {/* Hero + Focus card side by side */}
          <section className="grid grid-cols-1 lg:grid-cols-[1fr_0.7fr] gap-2.5 items-start">
            <HeroPanel
              projects={projects}
              uploadPhase={upload.uploadPhase}
              activeStageLabel={upload.activeStage.label}
              errorMessage={projectActionError}
              onRefresh={handleRefresh}
              onStartNew={scrollToUpload}
            />
            <TaskFocusCard
              projectName={focusProjectName}
              uploadPhase={upload.uploadPhase}
              taskStatus={upload.taskStatus}
              activeStage={upload.activeStage}
              taskMetrics={upload.taskMetrics}
              timeline={upload.timeline}
              statusText={upload.statusText}
              errorMessage={focusError}
            />
          </section>

          {/* Recent projects */}
          <RecentProjects
            projects={recentProjects}
            onDeleteProject={handleDeleteProject}
            onRejoinProject={handleRejoinProject}
            onContinueProject={handleContinueProject}
            onRerunProject={handleRerunProject}
          />

          {/* Upload + Analysis */}
          <section
            className={`grid gap-2.5 items-start ${
              latestProjectWithResults
                ? "grid-cols-1 lg:grid-cols-2"
                : "grid-cols-1"
            }`}
          >
            <div id="seed-upload-anchor">
              <SeedUploadPanel initiallyExpanded={upload.uploadPhase === "idle"} />
            </div>
            {latestProjectWithResults && (
              <div className="rounded-xl border bg-white/70 p-3">
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div>
                    <div className="font-mono text-xs text-muted-foreground">
                      结果
                    </div>
                    <h3 className="font-serif text-lg font-semibold">
                      最新分析结果
                    </h3>
                  </div>
                  <span className="font-mono text-xs text-muted-foreground">
                    {latestProjectWithResults.name}
                  </span>
                </div>
                <SeedAnalysisPanel
                  projects={projects}
                  projectId={latestProjectWithResults.id || ""}
                />
              </div>
            )}
          </section>
        </>
      )}

      {/* ========== Processing state ========== */}
      {isProcessing && (
        <>
          <HeroPanel
            projects={projects}
            uploadPhase={upload.uploadPhase}
            activeStageLabel={upload.activeStage.label}
            errorMessage={projectActionError}
            onRefresh={handleRefresh}
            onStartNew={scrollToUpload}
          />

          <RetryFailedSegmentsBanner
            retry={upload.sequentialReadingRetry}
            projectId={upload.completedProjectId}
            taskStatus={upload.taskStatus}
            uploadBusy={upload.uploadBusy}
            onRetry={(pid) => {
              upload.retrySegments(pid).catch((err) => {
                console.warn("[overview] retrySegments failed", err);
              });
            }}
          />

          <section className="grid grid-cols-1 lg:grid-cols-[1fr_0.35fr] gap-2.5 items-start">
            <InlineWorkflowStream
              taskId={upload.taskId}
              timeline={upload.timeline}
              activeStageKey={upload.activeStage.key}
              taskStatus={upload.taskStatus}
              uploadPhase={upload.uploadPhase}
              taskMetrics={upload.taskMetrics}
              errorMessage={upload.error}
              canResume={!!(upload.completedProjectId || activeProject?.id)}
              onDismiss={handleDismissWorkflow}
              onContinue={handleContinueWorkflow}
              onRerun={handleRerunWorkflow}
            />
            <div className="sticky top-4">
              <TaskFocusCard
                projectName={focusProjectName}
                uploadPhase={upload.uploadPhase}
                taskStatus={upload.taskStatus}
                activeStage={upload.activeStage}
                taskMetrics={upload.taskMetrics}
                timeline={upload.timeline}
                statusText={upload.statusText}
                errorMessage={focusError}
              />
            </div>
          </section>
        </>
      )}

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? `确认删除项目「${deleteTarget.name}」吗？`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
