/**
 * Overview page — main entry point for project overview, seed upload, and task monitoring.
 *
 * Two states:
 * 1. Default: Hero panel + Recent projects + Upload + Analysis results
 * 2. Processing: Hero + Workflow stream + Task focus card
 */

import { useCallback, useMemo, useRef, useState } from "react";
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

          <section className="grid grid-cols-1 lg:grid-cols-[1fr_0.35fr] gap-2.5 items-start">
            <InlineWorkflowStream
              taskId={upload.taskId}
              timeline={upload.timeline}
              activeStageKey={upload.activeStage.key}
              taskStatus={upload.taskStatus}
              uploadPhase={upload.uploadPhase}
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
