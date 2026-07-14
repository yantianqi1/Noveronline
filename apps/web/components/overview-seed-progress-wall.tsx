"use client";

import {
  Check,
  ChevronDown,
  ChevronRight,
  RotateCcw,
  X,
  XCircle,
} from "lucide-react";
import {
  useEffect,
  useId,
  useState,
  type ReactNode,
} from "react";

import type {
  WorkflowRunSummary,
} from "../lib/api";
import { Bi, StatusValue } from "./bilingual-text";
import { WorkflowProgress } from "./workflow-progress";

export type SeedProgressStage = {
  id: string;
  label: string;
  state: "pending" | "active" | "done" | "failed";
};

export type SeedActivityLogLine = {
  id: string;
  tone: "running" | "done" | "failed" | "info";
  message: string;
  timeLabel: string | null;
};

type OverviewSeedProgressWallProps = {
  cancelSeedRunAction: (formData: FormData) => Promise<void>;
  cancelSeedRunEnabled: boolean;
  completed: boolean;
  displayProgress: number;
  failureHint: string | null;
  failureRecoveryHref?: string;
  interrupted: boolean;
  retrySeedRunAction: (formData: FormData) => Promise<void>;
  retrySeedRunEnabled: boolean;
  runTone: string;
  selectedRunId: string;
  selectedSeedRun: Extract<WorkflowRunSummary, { ok: true }>;
  stageStates: SeedProgressStage[];
  runOverview: ReactNode;
};

/**
 * Collapsible Seed analysis "wall": compact when idle/completed, expands with
 * motion for active or failed runs. Full stage rail only when expanded.
 * Failed runs use a dense computer-frame card (no giant empty panels).
 */
export function OverviewSeedProgressWall({
  cancelSeedRunAction,
  cancelSeedRunEnabled,
  completed,
  displayProgress,
  failureHint,
  failureRecoveryHref = "",
  interrupted,
  retrySeedRunAction,
  retrySeedRunEnabled,
  runTone,
  selectedRunId,
  selectedSeedRun,
  stageStates,
  runOverview,
}: OverviewSeedProgressWallProps) {
  const panelId = useId();
  const status = selectedSeedRun.status;
  const isFailed = status === "failed";
  const shouldAutoExpand = status === "queued"
    || status === "running"
    || status === "failed"
    || status === "cancelled";

  const [userExpanded, setUserExpanded] = useState<boolean | null>(null);

  // New or status-changing tasks reset manual pin so active/failed pop out again.
  useEffect(() => {
    setUserExpanded(null);
  }, [selectedRunId, status]);

  const expanded = userExpanded ?? shouldAutoExpand;
  const previewStages = stageStates.slice(0, 2);

  const titleNode = completed
    ? <Bi zh="拆解完成，已自动入库" en="Analysis complete — auto-imported" />
    : interrupted
      ? <Bi zh="继续中断的分析" en="Continue the interrupted analysis" />
      : <Bi zh="故事分析正在推进" en="Story analysis is in progress" />;

  const summaryHint = completed
    ? (
      <Bi
        zh="拆解完成后会自动写入素材库。下方可预览结果，完整条目请到资产库查看。"
        en="Results are auto-imported into the library. Preview them below, or open Assets for the full set."
      />
    )
    : interrupted
      ? (
        <Bi zh="任务未完成，可重试；已有内容不会被删除。" en="The run did not finish. Retry keeps existing work." />
      )
      : null;

  const headlineStatus = completed
    ? <Bi zh="已完成" en="Completed" />
    : interrupted
      ? selectedSeedRun.status === "cancelled"
        ? <Bi zh="已取消" en="Cancelled" />
        : <Bi zh="失败" en="Failed" />
      : selectedSeedRun.status === "queued"
        ? <Bi zh="排队中" en="Queued" />
        : <Bi zh="进行中" en="In progress" />;

  function toggleExpanded() {
    setUserExpanded(!expanded);
  }

  return (
    <div
      className="overview-status-stage"
      data-density={isFailed || interrupted ? "compact" : "default"}
      data-expanded={expanded ? "true" : "false"}
      data-run-state={status}
      data-tone={runTone}
      data-wall="seed-progress"
    >
      <div className="overview-status-stage-intro">
        <div className="overview-status-stage-intro-row">
          <p className="overview-next-copy">
            <strong>{titleNode}</strong>
          </p>
          <button
            type="button"
            className="overview-status-wall-toggle"
            aria-controls={panelId}
            aria-expanded={expanded}
            onClick={toggleExpanded}
          >
            {expanded
              ? <Bi zh="收起进度" en="Collapse progress" />
              : <Bi zh="展开进度" en="Expand progress" />}
            <ChevronDown
              aria-hidden="true"
              className="overview-status-wall-toggle-icon"
              data-expanded={expanded ? "true" : "false"}
              size={16}
              strokeWidth={2}
            />
          </button>
        </div>
        {summaryHint ? (
          <p className="form-hint overview-status-stage-summary">{summaryHint}</p>
        ) : null}
      </div>

      <div
        className="overview-status-wall-preview"
        data-visible={expanded ? "false" : "true"}
        hidden={expanded}
      >
        <ol className="overview-status-wall-preview-stages">
          {previewStages.map((stage) => (
            <li data-state={stage.state} key={stage.id}>
              <span className="overview-stage-item">
                <span className="overview-stage-marker" aria-hidden="true" data-state={stage.state}>
                  {stage.state === "done" ? <Check size={11} strokeWidth={2.6} /> : null}
                  {stage.state === "failed" ? <X size={11} strokeWidth={2.6} /> : null}
                  {stage.state === "active" ? <span className="overview-stage-pulse" /> : null}
                </span>
                <span className="overview-stage-label">{stage.label}</span>
              </span>
            </li>
          ))}
          <li className="overview-status-wall-ellipsis" aria-hidden="true">
            <span className="overview-status-wall-ellipsis-dot" />
            <span className="overview-status-wall-ellipsis-dot" />
            <span className="overview-status-wall-ellipsis-dot" />
          </li>
        </ol>
        <div className="overview-status-wall-preview-meta">
          <span className="status-pill overview-status-dot" data-tone={runTone}>
            {headlineStatus}
          </span>
          <span className="form-hint">
            <Bi zh={`进度 ${displayProgress}%`} en={`Progress ${displayProgress}%`} />
          </span>
          {interrupted && retrySeedRunEnabled ? (
            <form action={retrySeedRunAction} className="overview-status-wall-preview-action">
              <input type="hidden" name="runId" value={selectedRunId} />
              <button className="overview-soft-action" type="submit">
                <RotateCcw aria-hidden="true" size={14} />
                <Bi zh="重试" en="Retry" />
              </button>
            </form>
          ) : null}
          {completed ? (
            <a className="overview-next-link overview-status-wall-preview-link" href="#analysis-candidates-heading">
              <Bi zh="查看拆解结果" en="View analysis results" />
              <ChevronRight aria-hidden="true" size={16} />
            </a>
          ) : null}
        </div>
      </div>

      <div
        id={panelId}
        className="overview-status-wall-body"
        data-expanded={expanded ? "true" : "false"}
        aria-hidden={expanded ? undefined : true}
      >
        <div className="overview-status-wall-body-inner">
          <div
            className="overview-status-pipeline"
            aria-live={expanded ? "polite" : "off"}
            data-density={isFailed || interrupted ? "compact" : "default"}
          >
            <WorkflowProgress
              className="overview-seed-progress"
              currentLabel={<StatusValue value={selectedSeedRun.status} />}
              progressLabel={<Bi zh={`进度 ${displayProgress}%`} en={`Progress ${displayProgress}%`} />}
              stages={stageStates.map((stage) => ({
                ...stage,
                label: (
                  <span className="overview-stage-item">
                    <span className="overview-stage-marker" aria-hidden="true" data-state={stage.state}>
                      {stage.state === "done" ? <Check size={11} strokeWidth={2.6} /> : null}
                      {stage.state === "failed" ? <X size={11} strokeWidth={2.6} /> : null}
                      {stage.state === "active" ? <span className="overview-stage-pulse" /> : null}
                    </span>
                    <span className="overview-stage-label">{stage.label}</span>
                  </span>
                ),
              }))}
              title={<Bi zh="分析进度" en="Analysis progress" />}
            />

            <div
              className="overview-status-card"
              data-density={isFailed || interrupted ? "compact" : "default"}
              data-tone={runTone}
            >
              <div className="overview-status-card-glow" aria-hidden="true" />
              <div className="overview-status-card-top">
                <div className="overview-status-card-title">
                  <span className="overview-status-kicker"><Bi zh="当前任务" en="Current run" /></span>
                  <strong className="overview-status-headline">{headlineStatus}</strong>
                  <p className="overview-status-sub">
                    <Bi zh={`进度 ${displayProgress}%`} en={`Progress ${displayProgress}%`} />
                  </p>
                  {isFailed && failureHint ? (
                    <div className="overview-status-failure-banner" data-animated="true">
                      <p className="overview-status-failure-line">
                        <Bi zh={failureHint} en={failureHint} />
                      </p>
                      <div className="overview-status-failure-actions">
                        {retrySeedRunEnabled ? (
                          <form action={retrySeedRunAction}>
                            <input type="hidden" name="runId" value={selectedRunId} />
                            <button className="overview-soft-action" type="submit">
                              <RotateCcw aria-hidden="true" size={14} />
                              <Bi zh="立即重试" en="Retry now" />
                            </button>
                          </form>
                        ) : null}
                        {failureRecoveryHref ? (
                          <a className="overview-next-link" href={failureRecoveryHref}>
                            <Bi zh="打开模型设置" en="Open model settings" />
                            <ChevronRight aria-hidden="true" size={16} />
                          </a>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
                <div className="overview-run-actions overview-run-actions-soft">
                  <form action={cancelSeedRunAction}>
                    <input type="hidden" name="runId" value={selectedRunId} />
                    <button className="danger-action overview-soft-action" disabled={!cancelSeedRunEnabled} type="submit">
                      <XCircle aria-hidden="true" size={16} />
                      <Bi zh="取消任务" en="Cancel analysis" />
                    </button>
                  </form>
                  <form action={retrySeedRunAction}>
                    <input type="hidden" name="runId" value={selectedRunId} />
                    <button className="overview-soft-action" disabled={!retrySeedRunEnabled} type="submit">
                      <RotateCcw aria-hidden="true" size={16} />
                      <Bi zh="重试任务" en="Retry analysis" />
                    </button>
                  </form>
                  {completed ? (
                    <a className="overview-next-link" href="#analysis-candidates-heading">
                      <Bi zh="查看拆解结果" en="View analysis results" />
                      <ChevronRight aria-hidden="true" size={18} />
                    </a>
                  ) : null}
                </div>
              </div>
              {runOverview}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
