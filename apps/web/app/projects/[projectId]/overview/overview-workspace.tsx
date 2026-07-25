"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  cancelSeedRun,
  deleteSourceFile,
  fetchOverview,
  fetchReadiness,
  fetchSeedRunEvents,
  fetchSeedRuns,
  fetchSourceFiles,
  OverviewError,
  readProjectSelection,
  retrySeedRun,
  startSeedRun,
  type ProjectSelection,
} from "@/lib/api/overview-client";
import { fetchCsrfToken } from "@/lib/api/session";
import { fetchAssets } from "@/lib/api/asset-client";
import { presentError } from "@/lib/present-error";
import type { AssetRecord } from "@/lib/api/asset-types";
import { uploadSourceFile, type UploadPhase } from "@/lib/api/upload";
import { reduceSeedProgress, type SeedProgress } from "@/lib/api/seed";
import type {
  ProjectOverview,
  ReadinessSnapshot,
  SeedRun,
  SourceFile,
  WorkflowEvent,
} from "@/lib/api/overview-types";

import { OverviewHeader } from "./overview-header";
import { UploadPanel } from "./upload-panel";
import { SeedProgressPanel } from "./seed-progress-panel";
import { ReadinessRail } from "./readiness-rail";
import { ActivityRail } from "./activity-rail";
import { OverviewEmpty } from "./overview-empty";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

const POLL_INTERVAL_MS = 2500;

/**
 * The Overview workbench ("书案") — import source text and run Seed analysis
 * in one surface. Orchestrates data loading, upload, run start/cancel/retry,
 * and live progress polling, then lays out the header / upload / progress /
 * readiness / activity regions.
 */
export function OverviewWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<ProjectSelection | null>(null);

  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [readiness, setReadiness] = useState<ReadinessSnapshot | null>(null);
  const [sourceFiles, setSourceFiles] = useState<SourceFile[]>([]);
  const [seedRuns, setSeedRuns] = useState<SeedRun[]>([]);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [assets, setAssets] = useState<AssetRecord[]>([]);

  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [deletingUploadId, setDeletingUploadId] = useState<string | null>(null);

  // The run to feature in the progress panel. While something is live, that's
  // the live run; otherwise the MOST RECENT terminal run (seedRuns is already
  // newest-first). Picking by recency — not just the first row — keeps the
  // panel honest when a newer completed/failed run supersedes an older failure.
  const activeRun: SeedRun | null =
    seedRuns.find((run) => isLiveStatus(run.status)) ?? mostRecentRun(seedRuns);

  const lastEventIdRef = useRef<string | undefined>(undefined);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(
    async (sel: ProjectSelection) => {
      const [ov, rd, files, runs, assetList] = await Promise.all([
        fetchOverview(sel.project_id, sel.tenant_id),
        fetchReadiness(sel.project_id, sel.tenant_id).catch(() => null),
        fetchSourceFiles(sel.project_id, sel.tenant_id),
        fetchSeedRuns(sel.project_id, sel.tenant_id),
        fetchAssets(sel.project_id, sel.tenant_id).catch(() => []),
      ]);
      setOverview(ov);
      setReadiness(rd);
      setSourceFiles(files);
      setSeedRuns(runs);
      setAssets(assetList);
    },
    [],
  );

  // Initial load: resolve the selection, then fetch everything.
  useEffect(() => {
    const sel = readProjectSelection();
    if (!sel || sel.project_id !== projectId) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        await loadAll(sel);
        const token = await fetchCsrfToken().catch(() => null);
        if (!cancelled) {
          setCsrfToken(token);
          setState({ status: "ready" });
        }
      } catch (error) {
        if (!cancelled) {
          if (error instanceof OverviewError && error.status === 401) {
            router.replace("/login");
            return;
          }
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "加载失败，请重试。",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, loadAll, router]);

  // Load the active run's event log (once per run), then poll only while live.
  const activeRunId = activeRun?.run_id;
  const activeRunLive = activeRun ? isLiveStatus(activeRun.status) : false;
  useEffect(() => {
    if (state.status !== "ready" || !selection || !activeRunId) {
      return;
    }

    let cancelled = false;
    // Always load the event log once so completed/failed runs render their
    // stage history (not just live ones).
    void (async () => {
      try {
        const initial = await fetchSeedRunEvents(
          selection.project_id,
          selection.tenant_id,
          activeRunId,
        );
        if (cancelled) return;
        if (initial.length > 0) {
          lastEventIdRef.current = initial[initial.length - 1].event_id;
          setEvents(initial);
        }
      } catch {
        // ignore — stage history just won't render
      }
    })();

    if (!activeRunLive) {
      return () => {
        cancelled = true;
      };
    }

    const tick = async () => {
      try {
        const [runs, newEvents] = await Promise.all([
          fetchSeedRuns(selection.project_id, selection.tenant_id),
          fetchSeedRunEvents(
            selection.project_id,
            selection.tenant_id,
            activeRunId,
            lastEventIdRef.current,
          ),
        ]);
        if (cancelled) return;
        setSeedRuns(runs);
        if (newEvents.length > 0) {
          lastEventIdRef.current = newEvents[newEvents.length - 1].event_id;
          setEvents((prev) => mergeEvents(prev, newEvents));
        }
        // Refresh counts when the run reaches a terminal state.
        const current = runs.find((r) => r.run_id === activeRunId);
        if (current && !isLiveStatus(current.status)) {
          const [ov, rd, assetList] = await Promise.all([
            fetchOverview(selection.project_id, selection.tenant_id),
            fetchReadiness(selection.project_id, selection.tenant_id).catch(() => null),
            fetchAssets(selection.project_id, selection.tenant_id).catch(() => []),
          ]);
          setOverview(ov);
          setReadiness(rd);
          setAssets(assetList);
        } else {
          // Still live: keep the readiness tiles streaming as assets land.
          const assetList = await fetchAssets(selection.project_id, selection.tenant_id).catch(
            () => null,
          );
          if (assetList) setAssets(assetList);
        }
      } catch {
        // A failed poll is non-fatal; the next tick retries.
      }
    };

    pollTimerRef.current = setInterval(() => {
      void tick();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, selection, activeRunId, activeRunLive]);

  const progress: SeedProgress = reduceSeedProgress(activeRun, events);

  async function handleUpload(file: File) {
    if (!selection || !csrfToken) return;
    setUploadError(null);
    setActionError(null);
    setUploadPhase("hashing");
    try {
      await uploadSourceFile({
        projectId: selection.project_id,
        tenantId: selection.tenant_id,
        csrfToken,
        file,
        onPhase: setUploadPhase,
      });
      const files = await fetchSourceFiles(selection.project_id, selection.tenant_id);
      setSourceFiles(files);
      const ov = await fetchOverview(selection.project_id, selection.tenant_id);
      setOverview(ov);
    } catch (error) {
      setUploadError(presentError(error, "上传失败，请重试。"));
    } finally {
      setUploadPhase(null);
    }
  }

  async function handleStart(uploadId: string) {
    if (!selection || !csrfToken) return;
    setActionError(null);
    setEvents([]);
    lastEventIdRef.current = undefined;
    try {
      await startSeedRun(selection.project_id, selection.tenant_id, csrfToken, uploadId);
      const runs = await fetchSeedRuns(selection.project_id, selection.tenant_id);
      setSeedRuns(runs);
    } catch (error) {
      setActionError(presentError(error, "启动分析失败，请重试。"));
    }
  }

  async function handleDelete(uploadId: string) {
    if (!selection || !csrfToken) return;
    setActionError(null);
    setDeletingUploadId(uploadId);
    try {
      await deleteSourceFile(selection.project_id, selection.tenant_id, csrfToken, uploadId);
      // Drop it locally right away, then reconcile with the server list so the
      // panel never re-shows a row the user just removed.
      setSourceFiles((prev) => prev.filter((file) => file.upload_id !== uploadId));
      const [files, ov] = await Promise.all([
        fetchSourceFiles(selection.project_id, selection.tenant_id),
        fetchOverview(selection.project_id, selection.tenant_id).catch(() => null),
      ]);
      setSourceFiles(files);
      if (ov) setOverview(ov);
    } catch (error) {
      setActionError(presentError(error, "删除原文失败，请重试。"));
    } finally {
      setDeletingUploadId(null);
    }
  }

  async function handleCancel(runId: string) {
    if (!selection || !csrfToken) return;
    setBusyRunId(runId);
    try {
      await cancelSeedRun(selection.project_id, selection.tenant_id, csrfToken, runId);
      const runs = await fetchSeedRuns(selection.project_id, selection.tenant_id);
      setSeedRuns(runs);
    } catch (error) {
      setActionError(presentError(error, "取消失败。"));
    } finally {
      setBusyRunId(null);
    }
  }

  async function handleRetry(runId: string) {
    if (!selection || !csrfToken) return;
    setBusyRunId(runId);
    setEvents([]);
    lastEventIdRef.current = undefined;
    try {
      await retrySeedRun(selection.project_id, selection.tenant_id, csrfToken, runId);
      const runs = await fetchSeedRuns(selection.project_id, selection.tenant_id);
      setSeedRuns(runs);
    } catch (error) {
      setActionError(presentError(error, "重试失败。"));
    } finally {
      setBusyRunId(null);
    }
  }

  if (state.status === "loading") {
    return <OverviewSkeleton />;
  }
  if (state.status === "no-selection") {
    return <NoSelection onBack={() => router.push("/workspace")} />;
  }
  if (state.status === "error") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">书案暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  const hasSource = sourceFiles.length > 0;
  const hasRun = seedRuns.length > 0;

  return (
    <div className="mx-auto w-full max-w-[1240px] px-8 py-8">
      <OverviewHeader overview={overview} readiness={readiness} progress={progress} hasRun={hasRun} />

      {!hasSource && !hasRun ? (
        <OverviewEmpty
          onUpload={handleUpload}
          uploadPhase={uploadPhase}
          uploadError={uploadError}
          canAct={Boolean(csrfToken)}
        />
      ) : (
        <div className="mt-5 flex flex-col gap-4">
          {/* Row 1 — readiness ledger leads | source import */}
          <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1.18fr_.82fr]">
            <ReadinessRail readiness={readiness} overview={overview} assets={assets} />
            <UploadPanel
              sourceFiles={sourceFiles}
              onUpload={handleUpload}
              onStart={handleStart}
              onDelete={handleDelete}
              uploadPhase={uploadPhase}
              uploadError={uploadError}
              actionError={actionError}
              canAct={Boolean(csrfToken)}
              analysisRunning={Boolean(activeRun && isLiveStatus(activeRun.status))}
              deletingId={deletingUploadId}
            />
          </div>

          {/* Row 2 — full-width analysis compass */}
          <SeedProgressPanel
            progress={progress}
            run={activeRun}
            events={events}
            busy={Boolean(activeRun && busyRunId === activeRun.run_id)}
            onCancel={handleCancel}
            onRetry={handleRetry}
            canAct={Boolean(csrfToken)}
          />

          {/* Row 3 — recent analyses */}
          <ActivityRail runs={seedRuns} progress={progress} activeRunId={activeRun?.run_id} />
        </div>
      )}
    </div>
  );
}

function isLiveStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === "running" || s === "queued" || s === "pending" || s === "in_progress";
}

/** The terminal run to feature: prefer a completed run, else the most recent. */
function mostRecentRun(runs: SeedRun[]): SeedRun | null {
  if (runs.length === 0) return null;
  const stamp = (run: SeedRun) => run.created_at || run.updated_at || "";
  const byRecency = (a: SeedRun, b: SeedRun) => (stamp(a) >= stamp(b) ? a : b);
  const completed = runs.filter((run) => run.status.toLowerCase() === "completed");
  if (completed.length > 0) {
    return completed.reduce(byRecency, completed[0]);
  }
  return runs.reduce(byRecency, runs[0]);
}

function mergeEvents(existing: WorkflowEvent[], incoming: WorkflowEvent[]): WorkflowEvent[] {
  if (incoming.length === 0) return existing;
  const seen = new Set(existing.map((e) => e.event_id));
  const merged = [...existing];
  for (const event of incoming) {
    if (!seen.has(event.event_id)) merged.push(event);
  }
  merged.sort((a, b) => a.sequence - b.sequence);
  return merged;
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        工作台需要知道你正在处理哪个项目。回到书架，挑一部作品再进来。
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-6 rounded-[10px] border border-line bg-panel px-5 py-2.5 text-[13.5px] font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
      >
        返回书架
      </button>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-8 py-8">
      <div className="space-y-3">
        <div className="h-3 w-20 animate-pulse rounded bg-line-soft" />
        <div className="h-9 w-64 animate-pulse rounded bg-line-soft" />
        <div className="h-4 w-96 animate-pulse rounded bg-line-soft" />
      </div>
      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.55fr_1fr]">
        <div className="h-[320px] animate-pulse rounded-card border border-line bg-panel" />
        <div className="h-[320px] animate-pulse rounded-card border border-line bg-panel" />
      </div>
    </div>
  );
}
